from dataclasses import dataclass, field
from typing import List
from qdrant_client.models import Filter  # type: ignore

@dataclass
class TransformedQuery:
    """The output of the Query Transformer, carrying everything the retriever needs."""

    embed_text: str
    
    bm25_tokens: List[str]

    qdrant_filter: Filter

    hyde_used: bool

    iso_vocab_hits: List[str]

    original_query: str

    language: str  # "EN" or "FR" — determines vocabulary and HyDE prompt language


@dataclass
class RetrievedChunk:
    """
    One Qdrant result converted into the data contract the Reranker consumes.

    All payload fields mirror NormChunk exactly (types match what Qdrant stores).
    The four score fields follow Option A from design.md §Score preservation:
      - dense_score / sparse_score: -1.0 sentinel (not available from Prefetch+FusionQuery)
      - rrf_score: populated from Qdrant ScoredPoint.score at construction time
      - rerank_score: 0.0 placeholder, populated by the Reranker in the next component

    The -1.0 sentinel is intentional: distinguishable from 0.0 which is a valid
    (very poor) real match score.

    content_type is str, not ContentType enum — Qdrant stores it as a plain string
    and importing the ingestion-pipeline enum here would create a cross-package
    dependency that does not belong in the retrieval layer.

    bm25_tokens is omitted — it is an ingestion-only artefact not needed at retrieval.
    """

    # Identity
    chunk_id: str

    # Provenance
    norm_id: str
    norm_full: str
    norm_version: str
    clause_number: str
    clause_title: str
    parent_clause: str       # empty string for top-level clauses
    page_number: int
    chunk_index: int         # 1-based index within the clause
    total_chunks: int        # equals 1 when no split occurred

    # Content
    text: str
    token_count: int

    # Classification
    content_type: str        # e.g. "normative" — stored as string in Qdrant

    # Modal vocabulary
    shall_count: int
    should_count: int
    has_requirements: bool
    has_permissions: bool
    has_recommendations: bool
    has_capabilities: bool

    # Retrieval enrichment
    keywords: List[str]        # top-5 TF-IDF terms
    related_clauses: List[str]

    # Embedding provenance
    embedding_model: str

    # Language
    language: str              # "EN" or "FR"

    # Scores — only rrf_score is known at retrieval time
    dense_score: float = -1.0    # sentinel: not returned by Prefetch+FusionQuery
    sparse_score: float = -1.0   # sentinel: not returned by Prefetch+FusionQuery
    rrf_score: float = 0.0       # set from Qdrant ScoredPoint.score
    rerank_score: float = 0.0    # set by Reranker; 0.0 until then
