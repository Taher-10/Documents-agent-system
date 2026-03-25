"""
vector_store/qdrant_store.py
─────────────────────────────
Phase 7b — VectorStoreManager

Upserts EmbeddedChunk objects into a Qdrant vector database collection.

Design decisions
----------------
• Idempotent: point ID = uuid.uuid5(NAMESPACE_DNS, chunk_id) — deterministic,
  so re-running the pipeline replaces existing points instead of duplicating.
• Auto-create collection: if the named collection does not exist it is created
  using the vector dimension taken from the first embedding in the batch.
• Distance metric: COSINE (standard for semantic similarity search).
• text IS included in the payload — required for RAG context retrieval.
• bm25_tokens is EXCLUDED — local-only field, never sent to Qdrant.
• List[str] fields are comma-joined for Qdrant payload compatibility.
• ContentType enum stored as .value string.
• All Qdrant failures emit UserWarning and return 0 — never halt the pipeline.

Dependency rule: imports from embedder.models (EmbeddedChunk) and the
standard library + qdrant_client.  No chunker, segmenter, enricher, or
registry imports (all chunk fields are accessed via EmbeddedChunk.chunk).
"""
from __future__ import annotations

import os
import uuid
import warnings
from typing import List, Optional, Set

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from embedder.models import EmbeddedChunk


_QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
_QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
_QDRANT_API_KEY: Optional[str] = os.getenv("QDRANT_API_KEY") or None

# Reserved point ID used as a collection-level sentinel that stores the
# embedding model name written at collection creation time.
# Never derived from any chunk_id → zero collision risk.
_SENTINEL_POINT_ID: str = "00000000-0000-0000-0000-000000000001"


class VectorStoreManager:
    """
    Write EmbeddedChunks into a Qdrant collection.

    Lifecycle
    ---------
    1. Instantiate once per pipeline run.
    2. Call upsert_chunks(embedded_chunks, collection_name) one or more times.
    3. The client connection is reused across calls (no explicit close needed
       for the synchronous QdrantClient).
    """

    def __init__(self) -> None:
        """
        Initialise the Qdrant client from environment variables.

        QDRANT_HOST    (default: "localhost")
        QDRANT_PORT    (default: 6333)
        QDRANT_API_KEY (optional — set for Qdrant Cloud)
        """
        self._client = QdrantClient(
            host=_QDRANT_HOST,
            port=_QDRANT_PORT,
            api_key=_QDRANT_API_KEY,
        )
        self._vector_size: Optional[int] = None
        self._created_collections: Set[str] = set()

    # ── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _chunk_id_to_point_id(chunk_id: str) -> str:
        """
        Derive a deterministic UUID string from a chunk_id.

        uuid.uuid5 is collision-resistant in the chunk_id namespace and
        compatible with Qdrant's UUID point ID format.  Calling this twice
        with the same chunk_id always yields the same UUID → idempotent upserts.
        """
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))

    def _write_sentinel(
        self, collection_name: str, model_name: str, vector_size: int
    ) -> None:
        """
        Write the model-name sentinel point into a newly created collection.

        The sentinel is a single Qdrant point with a fixed reserved UUID and a
        zero-vector (never used for similarity search).  Its payload records the
        embedding model so that future runs can detect model-space mismatches.

        Called immediately after create_collection() inside _ensure_collection().
        Failures are silently swallowed — the sentinel is best-effort.
        """
        from embedder.config import SPARSE_DIM
        try:
            self._client.upsert(
                collection_name=collection_name,
                points=[
                    PointStruct(
                        id=_SENTINEL_POINT_ID,
                        vector={
                            "dense": [0.0] * vector_size,
                            "sparse": SparseVector(indices=[], values=[]),
                        },
                        payload={
                            "sentinel": True,
                            "embedding_model": model_name,
                            "sparse_dim": SPARSE_DIM,
                        },
                    )
                ],
            )
        except Exception:
            pass  # Sentinel write failure must never break the pipeline.

    def _read_sentinel_payload(self, collection_name: str) -> Optional[dict]:
        """
        Retrieve the full payload dict from the sentinel point.

        Returns None when:
        • The collection has no sentinel (legacy collection).
        • The Qdrant retrieve call fails for any reason.
        """
        try:
            hits = self._client.retrieve(
                collection_name=collection_name,
                ids=[_SENTINEL_POINT_ID],
                with_payload=True,
            )
            if hits:
                return hits[0].payload
        except Exception:
            pass
        return None

    def _read_sentinel_model(self, collection_name: str) -> Optional[str]:
        """Thin wrapper around _read_sentinel_payload for backward compat."""
        payload = self._read_sentinel_payload(collection_name)
        return payload.get("embedding_model") if payload else None

    def _collection_exists(self, collection_name: str) -> bool:
        """Return True if the collection already exists in Qdrant."""
        try:
            return collection_name in {
                c.name for c in self._client.get_collections().collections
            }
        except Exception:
            return False

    def validate_model_consistency(
        self, collection_name: str, model_name: str
    ) -> None:
        """
        Guard against inserting vectors from a different embedding space.

        Reads the sentinel point written at collection creation time and
        compares the stored model name to *model_name*.

        Raises
        ------
        RuntimeError
            If the stored model name does not match *model_name*.
            Callers should delete the collection or switch to the original
            model before retrying.

        Emits UserWarning (no raise) for legacy collections that pre-date
        the sentinel mechanism.
        """
        from embedder.config import SPARSE_DIM

        # New collection — will be created fresh with a sentinel on first upsert.
        if not self._collection_exists(collection_name):
            return

        payload = self._read_sentinel_payload(collection_name)
        if payload is None:
            warnings.warn(
                f"[VectorStoreManager] Collection '{collection_name}' has no sentinel "
                "— model consistency cannot be guaranteed (legacy collection).",
                UserWarning,
                stacklevel=2,
            )
            return

        stored_model = payload.get("embedding_model")
        if stored_model != model_name:
            raise RuntimeError(
                f"[VectorStoreManager] Embedding model mismatch in '{collection_name}': "
                f"stored='{stored_model}', current='{model_name}'. "
                "Delete the collection or switch to the original model to fix."
            )

        stored_dim = payload.get("sparse_dim")
        if stored_dim is None:
            warnings.warn(
                f"[VectorStoreManager] Collection '{collection_name}' sentinel is missing "
                "'sparse_dim' — sparse index consistency cannot be guaranteed.",
                UserWarning,
                stacklevel=2,
            )
        elif stored_dim != SPARSE_DIM:
            raise RuntimeError(
                f"[VectorStoreManager] SPARSE_DIM mismatch in '{collection_name}': "
                f"stored={stored_dim}, current={SPARSE_DIM}. "
                "All stored sparse indices are invalid. Delete the collection and re-run."
            )

    def _ensure_collection(self, collection_name: str, vector_size: int, model_name: str = "") -> None:
        """
        Create the Qdrant collection if it does not already exist.

        Uses a local _created_collections cache to avoid a round-trip on
        every batch after the first successful check.  When a new collection
        is created, writes the sentinel point immediately so that future runs
        can validate model consistency.

        On any Qdrant API failure: emits UserWarning, does NOT raise.
        """
        if collection_name in self._created_collections:
            return
        try:
            existing = {c.name for c in self._client.get_collections().collections}
            if collection_name not in existing:
                self._client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        "dense": VectorParams(
                            size=vector_size,
                            distance=Distance.COSINE,
                        ),
                    },
                    sparse_vectors_config={
                        "sparse": SparseVectorParams(
                            index=SparseIndexParams(on_disk=False),
                        ),
                    },
                )
                if model_name:
                    self._write_sentinel(collection_name, model_name, vector_size)
            self._created_collections.add(collection_name)
        except Exception as exc:
            warnings.warn(
                f"[VectorStoreManager] Could not ensure collection "
                f"'{collection_name}': {exc}",
                UserWarning,
                stacklevel=3,
            )

    @staticmethod
    def _build_payload(embedded: EmbeddedChunk) -> dict:
        """
        Build the Qdrant point payload dict from an EmbeddedChunk.

        Serialisation rules
        -------------------
        • List[str] → comma-joined str  (empty list → "")
        • ContentType enum → .value string
        • bool, int, str → stored directly
        • text INCLUDED  — required for RAG retrieval
        • bm25_tokens EXCLUDED — local-only, never stored in Qdrant
        """
        chunk = embedded.chunk
        return {
            "chunk_id":            chunk.chunk_id,
            "norm_id":             chunk.norm_id,
            "norm_full":           chunk.norm_full,
            "norm_version":        chunk.norm_version,
            "clause_number":       chunk.clause_number,
            "clause_title":        chunk.clause_title,
            "parent_clause":       chunk.parent_clause,
            "page_number":         chunk.page_number,
            "chunk_index":         chunk.chunk_index,
            "total_chunks":        chunk.total_chunks,
            "text":                chunk.text,
            "token_count":         chunk.token_count,
            "content_type":        chunk.content_type.value,
            "shall_count":         chunk.shall_count,
            "should_count":        chunk.should_count,
            "has_requirements":    chunk.has_requirements,
            "has_permissions":     chunk.has_permissions,
            "has_recommendations": chunk.has_recommendations,
            "has_capabilities":    chunk.has_capabilities,
            "keywords":            ",".join(chunk.keywords),
            "related_clauses":     ",".join(chunk.related_clauses),
            "embedding_model":     chunk.embedding_model,
            "language":            chunk.language,
            # bm25_tokens → intentionally excluded
        }

    # ── Public API ───────────────────────────────────────────────────────────

    def upsert_chunks(
        self,
        embedded_chunks: List[EmbeddedChunk],
        collection_name: str = "norms",
    ) -> int:
        """
        Upsert a list of EmbeddedChunks into Qdrant.

        Steps
        -----
        1. Return 0 immediately if the list is empty.
        2. Auto-detect vector_size from the first embedding.
        3. Ensure the collection exists (create if absent, COSINE distance).
        4. Build PointStruct list: id=deterministic UUID, vector, payload.
        5. Call client.upsert() — idempotent by point UUID.
        6. On Qdrant exception: emit UserWarning, return 0.
        7. Return len(embedded_chunks) on success.

        Parameters
        ----------
        embedded_chunks : List produced by EmbedderService.embed_chunks().
        collection_name : Target Qdrant collection (default: "norms").

        Returns
        -------
        int — count of chunks successfully upserted (0 on failure).
        """
        if not embedded_chunks:
            return 0

        vector_size = len(embedded_chunks[0].vector)
        model_name = embedded_chunks[0].chunk.embedding_model
        self._ensure_collection(collection_name, vector_size, model_name)

        points = [
            PointStruct(
                id=self._chunk_id_to_point_id(e.chunk.chunk_id),
                vector={
                    "dense": e.vector,
                    "sparse": SparseVector(
                        indices=e.sparse_indices,
                        values=e.sparse_values,
                    ),
                },
                payload=self._build_payload(e),
            )
            for e in embedded_chunks
        ]

        try:
            self._client.upsert(collection_name=collection_name, points=points)
        except Exception as exc:
            warnings.warn(
                f"[VectorStoreManager] Upsert to '{collection_name}' failed: {exc}",
                UserWarning,
                stacklevel=2,
            )
            return 0

        return len(embedded_chunks)
