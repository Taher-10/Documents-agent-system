"""
chunker/__init__.py
────────────────────
Public API for the chunker package (Phase 4).

Responsibility: convert ClauseSpan lists (from the segmenter) into fully
populated NormChunk objects, ready for Phase 5 enrichment.

What this package does NOT do:
  • Retrieval enrichment (TF-IDF / BM25) → see enricher package
  • Registry output                       → see registry package

Downstream packages import from here:
  from chunker import assemble_norm_chunks, NormChunk, build_chunk_id
"""

from .assembler import assemble_norm_chunks, build_chunk_id
from .models import NormChunk

__all__ = [
    "assemble_norm_chunks",
    "build_chunk_id",
    "NormChunk",
]
