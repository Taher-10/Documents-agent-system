"""
query_retrival/retriever.py
────────────────────────────
Step 4 — Hybrid Qdrant Retriever (Dense + Sparse + RRF)

Implements HybridRetriever using Qdrant's Prefetch + FusionQuery(RRF) pattern:
  - Prefetch 1: dense cosine similarity on the 'dense' named vector
  - Prefetch 2: BM25 sparse similarity on the 'sparse' named vector
  - Outer query: FusionQuery(fusion=Fusion.RRF) re-ranks the merged candidate list

DenseRetriever is kept as a backward-compat alias for HybridRetriever.

Execution order inside retrieve() — strictly one async I/O call before Qdrant:
  1. embed_text()         — async, Ollama/sentence-transformers call
  2. encode_query()       — sync, pure BM25 token → SparseVector (no I/O)
  3. qdrant.query_points() — synchronous, Prefetch + FusionQuery

Score assignment follows design.md §Score preservation Option A:
  dense_score  = -1.0  (sentinel — Prefetch+FusionQuery does not expose per-vector scores)
  sparse_score = -1.0  (sentinel)
  rrf_score    = ScoredPoint.score  (the fused RRF score from Qdrant)
  rerank_score = 0.0   (Reranker populates this in the next component)

Prerequisite: the Qdrant collection must have BOTH 'dense' and 'sparse' named
vector slots.  Unit tests with mocked Qdrant are not affected by this requirement.

Dependency rule: imports only from qdrant_client, query_retrival.embedder,
and the top-level models module.  No transformer, enricher, or ingestion imports.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List

from qdrant_client import QdrantClient
from qdrant_client.models import (
    ScoredPoint,
    Prefetch,
    FusionQuery,
    Fusion,
    SparseVector,
)

from rag.retrival.models import RetrievedChunk, TransformedQuery
from rag.shared.bm25.bm25_encoder import BM25SparseEncoder

# EmbedderService is only needed for type hints — importing it at runtime pulls
# in chunker.models (an ingestion-pipeline package not present here).
# Duck-typing is sufficient: any object with an async embed_text(str) method works.
if TYPE_CHECKING:
    from query_retrival.embedder import EmbedderService


# ── Exception ────────────────────────────────────────────────────────────────

class EmptyCorpusError(Exception):
    """
    Raised when Qdrant returns zero results for a retrieval query.

    Two root causes produce zero results (see design.md §Empty corpus guard):
      Situation A — corpus not loaded: ingestion pipeline was never run or failed.
      Situation B — filter mismatch: norm_id stored in Qdrant does not match the
                    value in norm_filter (e.g. "ISO 9001" vs "ISO9001").

    The message always includes the filter values so the caller can diagnose
    which situation applies without inspecting Qdrant directly.

    Never return an empty list in place of this exception — silent empty results
    cause the RAG engine to produce a compliance report with no citations.
    """


# ── Payload → RetrievedChunk ─────────────────────────────────────────────────

def _scored_point_to_chunk(point: ScoredPoint) -> RetrievedChunk:
    """
    Convert a Qdrant ScoredPoint into a RetrievedChunk.

    Reads every required field directly from point.payload with no fallback.
    A missing key raises KeyError immediately — the NormChunk payload schema
    is contractual and a missing field indicates an ingestion bug, not a
    retrieval edge case.

    The point id (UUID string) is used as chunk_id.
    """
    p = point.payload  # type: ignore[union-attr]
    return RetrievedChunk(
        # Identity
        chunk_id=str(point.id),

        # Provenance
        norm_id=p["norm_id"],
        norm_full=p["norm_full"],
        norm_version=p["norm_version"],
        clause_number=p["clause_number"],
        clause_title=p["clause_title"],
        parent_clause=p["parent_clause"],
        page_number=p["page_number"],
        chunk_index=p["chunk_index"],
        total_chunks=p["total_chunks"],

        # Content
        text=p["text"],
        token_count=p["token_count"],

        # Classification
        content_type=p["content_type"],

        # Modal vocabulary
        shall_count=p["shall_count"],
        should_count=p["should_count"],
        has_requirements=p["has_requirements"],
        has_permissions=p["has_permissions"],
        has_recommendations=p["has_recommendations"],
        has_capabilities=p["has_capabilities"],

        # Retrieval enrichment
        keywords=p["keywords"],
        related_clauses=p["related_clauses"],

        # Embedding provenance
        embedding_model=p["embedding_model"],

        # Language
        language=p["language"],

        # Scores — Option A
        dense_score=-1.0,
        sparse_score=-1.0,
        rrf_score=point.score,
        rerank_score=0.0,
    )


# ── Retriever ────────────────────────────────────────────────────────────────

class HybridRetriever:
    """
    Hybrid Qdrant retriever: dense + sparse + RRF fusion (Step 4).

    Uses Qdrant's Prefetch + FusionQuery(RRF) pattern:
      - Prefetch 1: dense cosine similarity on the 'dense' named vector
      - Prefetch 2: BM25 sparse similarity on the 'sparse' named vector
      - Outer query: FusionQuery(fusion=Fusion.RRF) re-ranks candidates

    Graceful degradation: if query.bm25_tokens is empty, the sparse Prefetch
    is omitted and only the dense Prefetch is used.  This is a degenerate case
    and not expected in normal operation.

    Prerequisite: the Qdrant collection must have BOTH 'dense' and 'sparse'
    named vector slots configured.  Unit tests with mocked Qdrant are not
    affected by this requirement.

    Parameters
    ----------
    embedder : EmbedderService (or any object with async embed_text(str) -> List[float])
        Shared embedder instance.  embed_text() is called once per retrieve()
        call — no other I/O happens before the Qdrant query.
    qdrant : QdrantClient
        Synchronous Qdrant client pointed at the correct host/port.
    """

    def __init__(self, embedder: Any, qdrant: QdrantClient) -> None:
        self._embedder = embedder
        self._qdrant = qdrant

    async def retrieve(
        self,
        query: TransformedQuery,
        top_k: int = 15,
        collection: str = "norms",
    ) -> List[RetrievedChunk]:
        """
        Execute a hybrid (dense + sparse + RRF) search and return top-k chunks.

        Execution order (strictly enforced — only one async I/O call before Qdrant):
          1. embed_text(query.embed_text)          — async, single Ollama call
          2. BM25SparseEncoder.encode_query(...)   — sync, pure, no I/O
          3. Build prefetch list (dense always; sparse when bm25_tokens non-empty)
          4. qdrant.query_points(Prefetch + RRF)   — single sync Qdrant round-trip
          5. Empty guard → EmptyCorpusError
          6. Map each ScoredPoint → RetrievedChunk

        prefetch_limit = max(20, top_k * 2) gives RRF enough candidates from both
        lists to produce a meaningful fusion (RRF needs overlap to be effective).

        Parameters
        ----------
        query      : TransformedQuery produced by QueryTransformer.transform().
        top_k      : Number of chunks to return.  Default 15.
        collection : Qdrant collection name.  Default "norms".

        Returns
        -------
        List[RetrievedChunk] of length ≤ top_k, ranked by RRF fused score
        (stored in rrf_score; dense_score and sparse_score are -1.0 sentinels).

        Raises
        ------
        EmptyCorpusError
            When Qdrant returns zero results.
        """
        # Step 1 — embed (only async I/O before Qdrant)
        dense_vector: List[float] = await self._embedder.embed_text(query.embed_text)

        # Step 2 — sparse encode (sync, pure, no I/O)
        sparse_indices, sparse_values = BM25SparseEncoder.encode_query(
            query.bm25_tokens
        )

        # Step 3 — build prefetch list
        prefetch_limit = max(20, top_k * 2)

        prefetches = [
            Prefetch(
                query=dense_vector,
                using="dense",
                filter=query.qdrant_filter,
                limit=prefetch_limit,
            ),
        ]

        if sparse_indices:
            # Skip sparse Prefetch when no tokens — an empty SparseVector
            # contributes nothing useful and the degenerate case is not expected
            # in normal operation.
            prefetches.append(
                Prefetch(
                    query=SparseVector(
                        indices=sparse_indices,
                        values=sparse_values,
                    ),
                    using="sparse",
                    filter=query.qdrant_filter,
                    limit=prefetch_limit,
                )
            )

        # Step 4 — single hybrid Qdrant call (Prefetch + RRF fusion)
        # Note: filter goes on each Prefetch, NOT on the outer query_points call.
        # Note: no using= on the outer call — FusionQuery has no named vector slot.
        response = self._qdrant.query_points(
            collection_name=collection,
            prefetch=prefetches,
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        results: List[ScoredPoint] = response.points

        # Step 5 — empty guard
        if not results:
            raise EmptyCorpusError(
                f"No results from '{collection}'. "
                f"norm_filter={query.norm_filter}, language='{query.language}', "
                f"query='{query.original_query[:80]}'. "
                f"Possible causes: corpus not ingested, filter mismatch "
                f"(check norm_id values in Qdrant payload), or 'sparse' named "
                f"vector slot missing from collection."
            )

        # Step 6 — map to RetrievedChunk
        return [_scored_point_to_chunk(r) for r in results]


# Backward-compat alias — smoke tests and external callers import DenseRetriever
DenseRetriever = HybridRetriever
