"""
embedder/models.py
───────────────────
Phase 7 — EmbeddedChunk: thin pipeline hand-off type.

EmbeddedChunk is never persisted on its own.  It exists only in memory
between EmbedderService.embed_chunks() and VectorStoreManager.upsert_chunks().

Dependency rule: imports only NormChunk from chunker.models and the
standard library.  No Pydantic, no async libs, no Qdrant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from chunker.models import NormChunk


@dataclass
class EmbeddedChunk:
    """
    Thin wrapper pairing a NormChunk with its computed embedding vector.

    Fields
    ------
    chunk          : The original NormChunk (same object reference — not copied).
                     chunk.embedding_model is already set by EmbedderService before
                     this object is constructed.
    vector         : Dense float vector produced by the embedding model.  Length
                     equals the model's output dimension (e.g. 768 for nomic-embed-text).
    sparse_indices : Integer indices for the Qdrant SparseVector, sorted ascending.
                     Derived from chunk.bm25_tokens via BM25SparseEncoder (MD5 hash
                     modulo SPARSE_DIM).  Empty list when bm25_tokens is empty.
    sparse_values  : BM25 scores parallel to sparse_indices.  All values > 0.0.
                     Empty list when bm25_tokens is empty.
    """

    chunk: NormChunk
    vector: List[float]
    sparse_indices: List[int] = field(default_factory=list)
    sparse_values: List[float] = field(default_factory=list)


@dataclass
class EmbeddingResult:
    """
    Structured output of EmbedderService.embed_chunks().

    Replaces the bare List[EmbeddedChunk] return so that callers can
    detect and act on partial failures rather than silently losing chunks.

    Fields
    ------
    embedded      : Successfully embedded chunks — may be a subset of the
                    eligible input if individual requests failed after retries.
    failed_chunks : NormChunks that could not be embedded after all retries.
                    Empty list on full success.
    failure_rate  : len(failed_chunks) / total_eligible, in [0.0, 1.0].
                    Returns 0.0 when no eligible chunks exist (no division by zero).
    """

    embedded: List[EmbeddedChunk]
    failed_chunks: List[NormChunk]
    failure_rate: float
