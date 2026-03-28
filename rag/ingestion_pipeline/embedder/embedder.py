"""
embedder/embedder.py
─────────────────────
Phase 7a — EmbedderService

Converts a list of NormChunks into EmbeddedChunk objects by calling:
  Primary:  Ollama embedding REST API  (async httpx, batched, with retry)
  Fallback: sentence-transformers paraphrase-multilingual-mpnet-base-v2

Graceful degradation policy
----------------------------
• If Ollama is unreachable at __init__ time: load sentence-transformers once
  (one-time ~3–8s cost), emit UserWarning, set _use_ollama=False.
• If an individual request fails after all retries: it is recorded in
  EmbeddingResult.failed_chunks — partial results are always returned.
• embed_chunks() never raises; threshold enforcement is the caller's job
  (pipeline.py raises RuntimeError when failure_rate exceeds critical limit).

Concurrency note
----------------
Ollama /api/embeddings accepts ONE prompt per request (unlike OpenAI).
Within each batch of EMBED_BATCH_SIZE texts, all requests are fired via
asyncio.gather() on a single persistent AsyncClient (connection pooling).
A Semaphore (MAX_CONCURRENT_REQUESTS, default 10) caps the number of
requests active simultaneously to avoid saturating Ollama.

Retry strategy
--------------
Up to EMBED_MAX_RETRIES attempts per request with exponential backoff + jitter:
  delay = min(BASE * 2^attempt, MAX_DELAY) + uniform(0, JITTER)
Non-retryable 4xx errors (e.g. 400, 404) fail immediately without sleeping.
Retryable: 429, 5xx, timeouts, connection errors.

Dependency rule: imports from embedder.models (EmbeddedChunk, EmbeddingResult),
chunker.models (NormChunk), embedder.config, and async/standard library.
No segmenter, enricher, registry, or vector_store imports.
"""
from __future__ import annotations

import asyncio
import random
import warnings
from typing import List, Optional

import httpx

from rag.ingestion_pipeline.chunker.models import NormChunk
from rag.shared.bm25.bm25_encoder import BM25SparseEncoder
from .config import (
    EMBED_BATCH_SIZE,
    EMBED_CONTENT_TYPES,
    EMBED_MAX_RETRIES,
    EMBED_RETRY_BASE_DELAY,
    EMBED_RETRY_JITTER,
    EMBED_RETRY_MAX_DELAY,
    MAX_CONCURRENT_REQUESTS,
    OLLAMA_EMBED_ENDPOINT,
    OLLAMA_EMBED_MODEL,
)
from .models import EmbeddedChunk, EmbeddingResult


def _batched(items: list, size: int):
    """Yield successive sub-lists of length *size*."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


class EmbedderService:
    """
    Embed NormChunk objects into dense vectors.

    Lifecycle
    ---------
    1. Instantiate once per pipeline run.
    2. Call await embed_chunks(chunks) to get EmbeddingResult.
    3. Call await close() to release the httpx connection pool.
    """

    def __init__(self) -> None:
        """
        Determine which backend to use and prepare it.

        Steps
        -----
        1. Probe Ollama with a synchronous 3-second GET.
        2. Reachable → _use_ollama=True, create persistent AsyncClient.
        3. Unreachable → _use_ollama=False, load sentence-transformers fallback.
        """
        self._use_ollama: bool = False
        self._http_client: Optional[httpx.AsyncClient] = None
        self._fallback_model = None
        self._model_name: str = ""
        # Semaphore is created lazily inside the running event loop.
        self._semaphore: Optional[asyncio.Semaphore] = None

        if self._probe_ollama():
            self._use_ollama = True
            self._http_client = httpx.AsyncClient(timeout=30.0)
            self._model_name = OLLAMA_EMBED_MODEL
        else:
            warnings.warn(
                "[EmbedderService] Ollama unreachable — loading sentence-transformers "
                "fallback model 'paraphrase-multilingual-mpnet-base-v2'. "
                "This takes 3–8 s on first load.",
                UserWarning,
                stacklevel=2,
            )
            self._fallback_model = self._load_fallback()
            self._model_name = "paraphrase-multilingual-mpnet-base-v2"

    # ── Init helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _probe_ollama() -> bool:
        """
        Synchronous probe to check if Ollama is reachable.

        Sends a GET to the base Ollama URL with a 3-second timeout.
        Returns True if any HTTP response is received (even 4xx/5xx means
        Ollama is up but the endpoint may differ — still prefer Ollama).
        Returns False on connection error or timeout.
        """
        base_url = OLLAMA_EMBED_ENDPOINT.split("/api/")[0]
        try:
            httpx.get(base_url, timeout=3.0)
            return True
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            return False

    @staticmethod
    def _load_fallback():
        """
        Load the sentence-transformers fallback model.

        Import is deferred so that missing sentence-transformers does not
        break the module on import — ImportError is surfaced here with a
        clear message.
        """
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Install it with: pip install sentence-transformers>=2.7.0"
            ) from exc
        return SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")

    # ── Concurrency helper ───────────────────────────────────────────────────

    def _get_semaphore(self) -> asyncio.Semaphore:
        """
        Return the shared semaphore, creating it lazily on first access.

        Lazy creation is required because asyncio.Semaphore() must be
        instantiated inside a running event loop (not in __init__).
        """
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        return self._semaphore

    # ── Private embedding helpers ────────────────────────────────────────────

    @staticmethod
    def _build_embedding_text(chunk: NormChunk) -> str:
        """
        Build the string that will be sent to the embedding model.

        The "search_document: " instruction prefix is required by nomic-embed-text
        to route document vectors into the correct asymmetric retrieval subspace.
        The corresponding query side must use "search_query: " (Task 8).
        A structured clause identity prefix further anchors clauses sharing
        normative vocabulary (shall, documented information, …) to distinct
        vectors in the embedding space.

        Format: "search_document: {norm_full} clause {clause_number} {clause_title}: {text}"
        """
        return (
            f"search_document: {chunk.norm_full} clause {chunk.clause_number} "
            f"{chunk.clause_title}: {chunk.text}"
        )

    async def _embed_single_ollama(self, text: str, model: str) -> List[float]:
        """
        Embed one text via Ollama with concurrency control and retry.

        Concurrency: the semaphore limits total active requests to
        MAX_CONCURRENT_REQUESTS (default 10) across all concurrent tasks.

        Retry schedule (EMBED_MAX_RETRIES=5, base=0.5 s):
          attempt 0: ~0.5 s delay before next
          attempt 1: ~1.0 s
          attempt 2: ~2.0 s
          attempt 3: ~4.0 s
          attempt 4: raises last exception

        Non-retryable 4xx (400, 401, 403, 404 …) are re-raised immediately.
        Retryable: 429 Too Many Requests, 5xx, timeouts, connection errors.

        Raises the last exception on exhaustion so the caller (embed_chunks)
        can record it per-chunk via asyncio.gather(return_exceptions=True).
        """
        last_exc: Exception = RuntimeError("no attempts made")
        async with self._get_semaphore():
            for attempt in range(EMBED_MAX_RETRIES):
                try:
                    resp = await self._http_client.post(  # type: ignore[union-attr]
                        OLLAMA_EMBED_ENDPOINT,
                        json={"model": model, "prompt": text},
                    )
                    resp.raise_for_status()
                    return resp.json()["embedding"]
                except httpx.HTTPStatusError as exc:
                    # Non-retryable 4xx: fail immediately without sleeping.
                    if 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                        raise
                    last_exc = exc
                except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as exc:
                    last_exc = exc
                except Exception as exc:
                    last_exc = exc

                if attempt < EMBED_MAX_RETRIES - 1:
                    delay = min(
                        EMBED_RETRY_BASE_DELAY * (2 ** attempt),
                        EMBED_RETRY_MAX_DELAY,
                    ) + random.uniform(0, EMBED_RETRY_JITTER)
                    await asyncio.sleep(delay)

        raise last_exc

    async def _embed_batch_ollama(
        self, texts: List[str], model: str
    ) -> list:
        """
        Embed a batch of texts via Ollama concurrently.

        Uses asyncio.gather with return_exceptions=True so that individual
        request failures surface as Exception objects in the result list
        rather than aborting the entire batch.  The semaphore inside
        _embed_single_ollama caps concurrency across all tasks.
        """
        tasks = [self._embed_single_ollama(t, model) for t in texts]
        return list(await asyncio.gather(*tasks, return_exceptions=True))

    def _embed_batch_fallback(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of texts with the sentence-transformers fallback.

        encode() is synchronous and handles its own internal batching.
        """
        vectors = self._fallback_model.encode(
            texts,
            batch_size=EMBED_BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [v.tolist() for v in vectors]

    # ── Public API ───────────────────────────────────────────────────────────

    async def embed_chunks(
        self,
        chunks: List[NormChunk],
        collection: str = "norms",
    ) -> EmbeddingResult:
        """
        Phase 7a entry point: embed all eligible NormChunks.

        Steps
        -----
        1. Filter to chunks whose content_type.value is in EMBED_CONTENT_TYPES.
        2. Divide into batches of EMBED_BATCH_SIZE.
        3. Embed each batch (Ollama async or sentence-transformers sync).
        4. On whole-batch failure: emit UserWarning, record all chunks as failed.
        5. On per-chunk failure (return_exceptions=True): record chunk as failed.
        6. Set chunk.embedding_model = self._model_name for each success.
        7. Return EmbeddingResult with embedded, failed_chunks, failure_rate.

        Parameters
        ----------
        chunks     : Full NormChunk list from the pipeline.
        collection : Passed through for log context only; not used here.

        Returns
        -------
        EmbeddingResult — never raises.
        """
        eligible = [c for c in chunks if c.content_type.value in EMBED_CONTENT_TYPES]
        total = len(eligible)
        results: List[EmbeddedChunk] = []
        failed: List[NormChunk] = []

        # BM25SparseEncoder requires the full eligible corpus for Pass 1 (DF/avgdl).
        # Instantiated once here so every encode() call shares the same IDF statistics.
        bm25_encoder = BM25SparseEncoder(eligible)

        for batch_num, batch in enumerate(_batched(eligible, EMBED_BATCH_SIZE), start=1):
            texts = [self._build_embedding_text(c) for c in batch]
            try:
                if self._use_ollama:
                    raw = await self._embed_batch_ollama(texts, self._model_name)
                else:
                    raw = self._embed_batch_fallback(texts)
            except Exception as exc:
                warnings.warn(
                    f"[EmbedderService] Batch {batch_num} failed — skipping "
                    f"{len(batch)} chunks: {exc}",
                    UserWarning,
                    stacklevel=2,
                )
                failed.extend(batch)
                continue

            for chunk, item in zip(batch, raw):
                if isinstance(item, Exception):
                    failed.append(chunk)
                else:
                    chunk.embedding_model = self._model_name
                    sparse_indices, sparse_values = bm25_encoder.encode(chunk)
                    results.append(EmbeddedChunk(
                        chunk=chunk,
                        vector=item,
                        sparse_indices=sparse_indices,
                        sparse_values=sparse_values,
                    ))

        failure_rate = len(failed) / total if total > 0 else 0.0
        return EmbeddingResult(
            embedded=results,
            failed_chunks=failed,
            failure_rate=failure_rate,
        )

    async def embed_text(self, text: str) -> List[float]:
        """
        Embed a single raw string. Used by the Hybrid Retriever at query time.

        Unlike embed_chunks(), this method applies NO prefix of its own —
        the caller is responsible for formatting the string (e.g. TransformedQuery
        prepends the query-side prefix before calling this).

        Raises on failure — there is no partial result for a single string.

        Parameters
        ----------
        text : The fully-formatted string to embed.

        Returns
        -------
        List[float] — dense vector of length equal to the model's output dimension.
        """
        if self._use_ollama:
            return await self._embed_single_ollama(text, self._model_name)
        else:
            return self._embed_batch_fallback([text])[0]

    async def close(self) -> None:
        """
        Release the httpx AsyncClient connection pool.

        Must be called after all embedding is done to avoid ResourceWarning
        from unclosed connections.  No-op when using the fallback model.
        """
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
