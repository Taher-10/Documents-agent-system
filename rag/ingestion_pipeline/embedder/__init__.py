"""
embedder/__init__.py
─────────────────────
Public API for the embedder package (Phase 7a).

Responsibility: convert List[NormChunk] → List[EmbeddedChunk] using
Ollama (primary) or sentence-transformers (fallback).

Usage:
    from embedder import EmbedderService, EmbeddedChunk
"""
from .embedder import EmbedderService
from .models import EmbeddedChunk, EmbeddingResult

__all__ = ["EmbedderService", "EmbeddedChunk", "EmbeddingResult"]
