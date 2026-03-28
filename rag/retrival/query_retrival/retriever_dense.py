"""
query_retrival/retriever_dense.py
────────────────────────────
Dense-Only Qdrant Retriever

Implements DenseRetriever, the first executable slice of the Hybrid Retriever.
Only a single dense vector query is issued at this stage; sparse + RRF fusion
is added in Step 4.  The interface and score conventions are already set to
their final shapes so Step 4 is an extension, not a rewrite.

Execution order inside retrieve() — strictly one I/O call before Qdrant:
  1. embed_text()   — async, single Ollama/sentence-transformers call
  2. qdrant.search() — synchronous, dense cosine similarity search

Score assignment follows design.md §Score preservation Option A:
  dense_score  = -1.0  (sentinel — not independently available from Prefetch+FusionQuery;
                        kept as sentinel even here so Step 4 transition is trivial)
  sparse_score = -1.0  (sentinel)
  rrf_score    = ScoredPoint.score  (cosine similarity in this step;
                        becomes the true RRF fused score after Step 4)
  rerank_score = 0.0   (Reranker populates this in the next component)

Dependency rule: imports only from qdrant_client, query_retrival.embedder,
and the top-level models module.  No transformer, enricher, or ingestion imports.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List

from qdrant_client import QdrantClient
from qdrant_client.models import ScoredPoint

from rag.retrival.models import RetrievedChunk, TransformedQuery

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

class DenseRetriever:
    """
    Dense-only Qdrant retriever (Step 3 of design.md development sequence).

    Produces a list of RetrievedChunk objects ranked by cosine similarity.
    The public interface and score field conventions match the final hybrid
    retriever so that Step 4 (sparse + RRF) is an additive change.

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
        top_k: int = 10,
        collection: str = "norms",
    ) -> List[RetrievedChunk]:
        """
        Execute a dense vector search and return the top-k chunks.

        Steps (in strict order — no I/O between embed and Qdrant):
        1. Embed query.embed_text → dense_vector  (single async call)
        2. qdrant.search()        → ScoredPoint list
        3. Empty guard            → EmptyCorpusError if no results
        4. Map each ScoredPoint   → RetrievedChunk

        Parameters
        ----------
        query      : TransformedQuery produced by QueryTransformer.transform().
                     query.embed_text is passed directly to embed_text() —
                     no prefix is added here (symmetric with ingestion, which
                     also uses no search_document: prefix).
        top_k      : Number of chunks to return.  Default 10.
        collection : Qdrant collection name.  Default "norms".

        Returns
        -------
        List[RetrievedChunk] of length top_k, ranked by cosine similarity
        (stored in rrf_score; dense_score and sparse_score are -1.0 sentinels).

        Raises
        ------
        EmptyCorpusError
            When Qdrant returns zero results.  Inspect the message to diagnose
            corpus-not-loaded (Situation A) vs filter-mismatch (Situation B).
        """
        # Step 1 — embed (only I/O before Qdrant)
        dense_vector: List[float] = await self._embedder.embed_text(query.embed_text)

        # Step 2 — dense search (qdrant-client >= 1.7: query_points replaces search)
        # using="dense" — the norms collection stores named vectors; "dense" is the
        # dense vector slot set at ingestion time.
        response = self._qdrant.query_points(
            collection_name=collection,
            query=dense_vector,
            using="dense",
            query_filter=query.qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
        results: List[ScoredPoint] = response.points

        # Step 3 — empty guard
        if not results:
            raise EmptyCorpusError(
                f"No results from collection '{collection}'. "
                f"norm_filter={query.norm_filter}, language='{query.language}', "
                f"query='{query.original_query[:80]}'. "
                f"Possible causes: corpus not ingested, filter mismatch "
                f"(check norm_id values in Qdrant payload)."
            )

        # Step 4 — map to RetrievedChunk
        return [_scored_point_to_chunk(r) for r in results]
