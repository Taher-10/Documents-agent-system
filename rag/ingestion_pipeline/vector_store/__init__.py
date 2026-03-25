"""
vector_store/__init__.py
─────────────────────────
Public API for the vector_store package (Phase 7b).

Responsibility: receive List[EmbeddedChunk] from the embedder and
persist vectors + metadata into a Qdrant collection.

Usage:
    from vector_store import VectorStoreManager
"""
from .qdrant_store import VectorStoreManager

__all__ = ["VectorStoreManager"]
