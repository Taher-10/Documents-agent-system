"""
service.py
==========
RetrievalService — unified entry point for the full retrieval pipeline.

Pipeline (in order):
    1. QueryTransformer.transform()  — sync, no I/O
    2. HybridRetriever.retrieve()   — async (Ollama embed + Qdrant RRF)
    3. Reranker.rerank()            — sync (cross-encoder batch scoring)
    4. Truncate to top_k_rerank

Public API
----------
    RetrievalService(embedder, qdrant, reranker, collection, top_k, top_k_rerank)
    await service.retrieve(query, norm_filter, language, top_k, top_k_rerank, clause_families, specific_clauses) -> List[RetrievedChunk]
    await service.close()
"""

from __future__ import annotations

from typing import Any, List

from qdrant_client import QdrantClient

from rag.retrival.models import RetrievedChunk
from rag.retrival.query_retrival import HybridRetriever
from rag.retrival.query_transformer import transform
from rag.retrival.re_ranker import Reranker


class RetrievalService:
    """Orchestrates Transform → HybridRetrieve → Rerank into one call."""

    def __init__(
        self,
        embedder: Any,
        qdrant: QdrantClient,
        reranker: Reranker,
        collection: str = "norms",
        top_k: int = 15,
        top_k_rerank: int = 5,
    ) -> None:
        self._retriever = HybridRetriever(embedder=embedder, qdrant=qdrant)
        self._reranker = reranker
        self._embedder = embedder
        self._collection = collection
        self._top_k = top_k
        self._top_k_rerank = top_k_rerank

    async def retrieve(
        self,
        query: str,
        norm_filter: List[str],
        language: str,
        top_k: int | None = None,
        top_k_rerank: int | None = None,
        clause_families: List[str] = [],
        specific_clauses: List[str] = [],
    ) -> List[RetrievedChunk]:
        """Run the full retrieval pipeline and return top reranked chunks.

        Args:
            query:            Raw user query string.
            norm_filter:      Non-empty list of norm IDs to restrict search (e.g. ["ISO9001"]).
            language:         "EN" or "FR".
            top_k:            Candidate pool size for retriever. Overrides instance default.
            top_k_rerank:     Number of chunks to return after reranking. Overrides instance default.
            clause_families:  Optional top-level clause families for hard Qdrant filter
                              (e.g. ["8"] matches all of 8, 8.1, 8.5.1, …).
            specific_clauses: Optional sub-clause IDs for soft BM25 token boost
                              (e.g. ["8.5"] injects "8" and "5" into the token set).

        Returns:
            List of RetrievedChunk sorted by rerank_score descending, length <= top_k_rerank.

        Raises:
            ValueError:        If norm_filter is empty (from QueryTransformer).
            EmptyCorpusError:  If Qdrant returns zero results for the query/filter combination.
        """
        effective_top_k = top_k if top_k is not None else self._top_k
        effective_top_k_rerank = top_k_rerank if top_k_rerank is not None else self._top_k_rerank

        # Step 1 — transform (sync)
        tq = transform(query, norm_filter, language, clause_families, specific_clauses)

        # Step 2 — hybrid retrieve (async)
        chunks = await self._retriever.retrieve(
            tq, top_k=effective_top_k, collection=self._collection
        )

        # Step 3 — rerank (sync); uses original_query, not embed_text
        ranked = self._reranker.rerank(tq.original_query, chunks)

        # Step 4 — truncate
        return ranked[:effective_top_k_rerank]

    async def close(self) -> None:
        """Release async resources (embedder HTTP client)."""
        await self._embedder.close()
