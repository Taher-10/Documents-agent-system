"""
re_ranker/reranker.py
──────────────────────
Step 5 — Cross-encoder Reranker

Receives the top-k candidates from HybridRetriever ordered by RRF score,
re-scores each (query, chunk) pair using a cross-encoder model, and returns
the full list sorted by rerank_score descending.

Model: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
  - 12-layer MiniLM fine-tuned on mMARCO (26 languages, FR + EN strong)
  - Handles French queries against English ISO norm chunks (cross-lingual)
  - Output: raw logits (not normalized). Higher = more relevant.

The rerank() method takes query_text: str (not TransformedQuery).
No truncation. top_k_rerank truncation belongs to ContextAssembler.
"""
from __future__ import annotations

from typing import List

from sentence_transformers import CrossEncoder

from rag.retrival.models import RetrievedChunk


class Reranker:
    """
    Cross-encoder reranker (Step 5).

    Loads the model eagerly at __init__ — fails fast at startup if the model
    is missing or corrupt.

    Parameters
    ----------
    model_name : str
        HuggingFace model identifier.
        Default: 'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1' (multilingual).
    """

    DEFAULT_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._model = CrossEncoder(model_name)

    def rerank(
        self,
        query_text: str,
        candidates: List[RetrievedChunk],
    ) -> List[RetrievedChunk]:
        """
        Score each (query_text, chunk.text) pair and return candidates sorted
        by rerank_score descending.

        Steps:
          1. Guard  — return [] immediately if candidates is empty.
          2. Score  — single batch CrossEncoder.predict() call.
          3. Assign — set rerank_score = float(score) on each chunk.
          4. Sort   — sort candidates in-place by rerank_score descending.

        Parameters
        ----------
        query_text : TransformedQuery.original_query — never pass embed_text.
        candidates : List[RetrievedChunk] from HybridRetriever.

        Returns
        -------
        Full list with rerank_score populated, sorted descending. No truncation.
        """
        if not candidates:
            return []

        pairs = [[query_text, chunk.text] for chunk in candidates]
        scores = self._model.predict(pairs)

        for chunk, score in zip(candidates, scores):
            chunk.rerank_score = float(score)

        candidates.sort(key=lambda c: c.rerank_score, reverse=True)
        return candidates
