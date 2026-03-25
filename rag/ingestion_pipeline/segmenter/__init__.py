"""
segmenter/__init__.py
──────────────────────
Public API for the segmenter package (Phases 1–3).

Responsibilities of this package:
  • Phase 1 — Page resolution: PageTracker maps character offsets to PDF pages.
  • Phase 2 — Boundary detection: detect_clause_boundaries() splits markdown
    into clause ranges using heading_positions from the ParsedDocument.
  • Phase 3 — Tree construction: construct_clause_tree() assembles the flat
    clause list into a recursive hierarchy.

What this package does NOT do:
  • NormChunk assembly  → see chunker package
  • Retrieval enrichment → see enricher package
  • Registry output     → see registry package

Downstream packages import types from here:
  from segmenter import ClauseSpan, ClauseNode, ContentType, PageTracker
  from segmenter import detect_clause_boundaries, construct_clause_tree
"""

from .iso_segmenter import construct_clause_tree, detect_clause_boundaries
from .models import (
    EXPECTED_LEAF_COUNTS,
    NORM_ID_MAP,
    NORM_VERSION_MAP,
    STANDARD_ID_MAP,
    ClauseNode,
    ClauseSpan,
    ContentType,
)
from .page_tracker import PageTracker

__all__ = [
    # Functions
    "detect_clause_boundaries",
    "construct_clause_tree",
    # Data types
    "ClauseSpan",
    "ClauseNode",
    "ContentType",
    "PageTracker",
    # Constants (re-exported for downstream consumers)
    "STANDARD_ID_MAP",
    "NORM_ID_MAP",
    "NORM_VERSION_MAP",
    "EXPECTED_LEAF_COUNTS",
]
