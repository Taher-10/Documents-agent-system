"""
enricher/__init__.py
─────────────────────
Public API for the enricher package (Phase 5).

Responsibility: add TF-IDF keywords and BM25 tokens to NormChunks produced
by the chunker.  The Enricher is stateful — it pre-computes corpus IDF at
construction time.

What this package does NOT do:
  • Chunk creation (Phase 4)   → see chunker package
  • Registry output (Phase 6)  → see registry package

Usage:
  from enricher import Enricher
  enricher = Enricher(chunks)
  enricher.enrich(chunks)
"""

from .enricher import Enricher

__all__ = ["Enricher"]
