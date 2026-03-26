"""
chunker/models.py
──────────────────
NormChunk — the primary output data class of the chunker package (Phase 4).

A NormChunk represents one retrieval unit extracted from a single ISO clause
(or a paragraph-split portion of a clause if the clause exceeds MAX_CHUNK_WORDS).

Each chunk carries:
  • Full provenance (which standard, clause, page, split index)
  • Raw text and word-count
  • Normative classification (ContentType from the segmenter)
  • Modal vocabulary counts (shall / should / may / can)
  • Retrieval metadata (keywords, related clause references)
  • BM25 token list (not stored in ChromaDB — local retrieval only)

Dependency rule: the only import from the pipeline is ContentType from
segmenter.models. No chunker-internal logic is imported here; this file
is a pure data-contract module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from segmenter.models import ContentType


@dataclass
class NormChunk:
    """
    A single retrieval unit produced from one ISO clause (or clause part).

    Fields are grouped by concern:

    Identity
    --------
    chunk_id : Canonical identifier built by build_chunk_id() — never construct
               this string manually elsewhere.
               Format: {standard_id}_{clause_id}_{partN}_p{page}
               Example: "n9001_8.5.1_part1_p23"

    Provenance
    ----------
    norm_id       : Short norm identifier, e.g. "ISO9001".
    norm_full     : Human-readable label, e.g. "ISO 9001:2015".
    norm_version  : Publication year string, e.g. "2015".
    clause_number : Clause identifier, e.g. "8.5.1".
    clause_title  : Verbatim heading, e.g. "Control of production and service provision".
    parent_clause : Direct parent clause ID, e.g. "8.5".  Empty string for top-level clauses.
    page_number   : PDF page where this chunk's text begins.
    chunk_index   : 1-based index within the clause (1 of N if clause was split).
    total_chunks  : N — equals 1 when no split occurred.

    Content
    -------
    text        : The raw markdown text slice for this chunk.
    token_count : Word count of text (approximated as whitespace-split tokens).

    Classification
    --------------
    content_type : ContentType enum value determined by modal verb analysis.

    Modal vocabulary
    ----------------
    shall_count        : Count of SHALL / doit / doivent occurrences.
    should_count       : Count of SHOULD / il convient / devrait occurrences.
    has_requirements   : True when shall_count > 0.
    has_permissions    : True when 'may' / 'peut' is present.
    has_recommendations: True when should_count > 0.
    has_capabilities   : True when 'can' is present (modal sense).

    Retrieval enrichment  (populated by Phase 5 — Enricher)
    ----------------------
    keywords       : Top-5 TF-IDF terms (may include bigrams).
    related_clauses: Clause references extracted from the text body.

    Embedding provenance  (set during embedding step, outside this pipeline)
    ---------------------
    embedding_model: Name of the embedding model used; empty until set.

    Language  (set by the caller — API layer passes "EN" or "FR")
    --------
    language: ISO 639-1 language code of the document ("EN" or "FR").
              Empty until set by the ingestion API endpoint.

    BM25-only  (sparse in Qdrant)
    ---------
    bm25_tokens: .
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    chunk_id: str

    # ── Provenance ────────────────────────────────────────────────────────────
    norm_id: str
    norm_full: str
    norm_version: str
    clause_number: str
    clause_title: str
    parent_clause: str
    page_number: int
    chunk_index: int
    total_chunks: int

    # ── Content ───────────────────────────────────────────────────────────────
    text: str
    token_count: int

    # ── Classification ────────────────────────────────────────────────────────
    content_type: ContentType

    # ── Modal vocabulary ──────────────────────────────────────────────────────
    shall_count: int
    should_count: int
    has_requirements: bool
    has_permissions: bool
    has_recommendations: bool
    has_capabilities: bool

    # ── Retrieval enrichment ──────────────────────────────────────────────────
    keywords: List[str]
    related_clauses: List[str]

    # ── Embedding provenance ──────────────────────────────────────────────────
    embedding_model: str = ""

    # ── Language  (set by the API caller, not by the pipeline) ───────────────
    language: str = ""

    # ── BM25 ───────────────────────────────────
    bm25_tokens: List[str] = field(
        default_factory=list,
        metadata={"chroma": False},
    )
