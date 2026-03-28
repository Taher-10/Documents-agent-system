"""
vocabulary.py  (query_transformer shim)
========================================
Re-exports the ISO vocabulary dictionaries and build_lookup helper from their
canonical home in rag.shared.vocabulary.

The vocabulary data has been moved to rag/shared/vocabulary/vocabulary.py so
that both the ingestion enricher (Phase 5) and the retrieval query transformer
can use the same vocabulary without a cross-layer import.

This file is kept for backward compatibility — existing imports of the form:
    from rag.retrival.query_transformer.vocabulary import ISO_VOCABULARY_EN
continue to work unchanged.
"""

from rag.shared.vocabulary.vocabulary import (  # noqa: F401
    ISO_VOCABULARY_EN,
    ISO_VOCABULARY_FR,
    build_lookup,
)

__all__ = ["ISO_VOCABULARY_EN", "ISO_VOCABULARY_FR", "build_lookup"]
