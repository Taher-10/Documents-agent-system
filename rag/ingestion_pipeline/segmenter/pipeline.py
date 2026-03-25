"""
pipeline.py
────────────
Top-level orchestrator for the ISO standard segmenter.


  segment_document(doc)
      Executes Phases 1–5 in sequence.  No file I/O.  Use this for testing
      or when you need the result without writing registry output.

  segment(doc, output_dir)
      Full pipeline (Phases 1–6).  Calls segment_document(), then validates
      chunks (Phase 6a) and writes the registry JSON (Phase 6b).

  embed_and_store(result, collection)
      Phase 7 — opt-in embedding and Qdrant upsert.  Activate by setting
      EMBEDDING_ENABLED=true.  Never raises; failures are UserWarnings.

Data flow
---------
  ParsedDocument
    → Phase 1  PageTracker.page_at()                — offset → page mapping
    → Phase 2  detect_clause_boundaries()           → List[ClauseSpan]
    → Phase 3  construct_clause_tree()              → ClauseNode (root)
    → SegmenterResult

SegmenterResult
---------------
  standard_id : Human-readable standard label, e.g. "ISO 9001:2015".
  tree        : ClauseNode root — full recursive clause hierarchy.
  chunks      : List[NormChunk] — enriched retrieval units.

Design rule: this module contains NO business logic.  Its only job is
orchestration — calling each phase in order and assembling the final result.
If a phase needs to change, only that phase's module changes.

Dependency rule: this is the only module that imports from all four packages.
No other module may import from pipeline.py.
"""

from __future__ import annotations

import asyncio
import warnings
from dataclasses import dataclass
from typing import List

from parser.document import ParsedDocument

from segmenter import (
    STANDARD_ID_MAP,
    ClauseNode,
    PageTracker,
    construct_clause_tree,
    detect_clause_boundaries,
)


def segment_document(doc: ParsedDocument, language: str = "") -> SegmenterResult:
    """
    Execute the core ingestion pipeline (Phases 1–5).  No file I/O.

    Use this entry point for:
      • Unit testing — results are in-memory only.
      • Embedding pipelines that manage their own output.
      • Any caller that does not need registry JSON.

    Phases executed
    ---------------
    1. PageTracker construction  — O(n log n) sort on page_map keys.
    2. Clause boundary detection — heading_positions → List[ClauseSpan].
    3. Clause tree construction  — ClauseSpan list → ClauseNode tree.
    4. NormChunk assembly        — ClauseSpan list → List[NormChunk].
    5. Retrieval enrichment      — TF-IDF keywords + BM25 tokens.

    Parameters
    ----------
    doc      : ParsedDocument produced by parse_iso_pdf().
    language : ISO 639-1 code of the document language ("EN" or "FR").
               Stamped onto every NormChunk.  Empty string when not provided.
               The ingestion API will pass this value; use it directly here
               until that layer exists.

    Returns
    -------
    SegmenterResult — fully populated, keywords and bm25_tokens set.
    """
    # Phase 1 — build page resolver from parser's page_map
    tracker = PageTracker(doc.page_map)

    # Phase 2 — detect clause boundaries from heading_positions
    spans = detect_clause_boundaries(doc)

    # Phase 3 — assemble flat spans into a recursive clause tree
    tree = construct_clause_tree(spans, doc.markdown, doc.standard_id)
