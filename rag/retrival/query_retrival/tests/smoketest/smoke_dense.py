"""
query_retrival/smoke_dense.py
──────────────────────────────
Live integration smoke test for DenseRetriever (Step 3).

Requires:
  - Qdrant running on localhost:6333 (override with QDRANT_HOST / QDRANT_PORT)
  - Ollama running on localhost:11434 with nomic-embed-text pulled
    (override with OLLAMA_URL / OLLAMA_EMBED_MODEL)
  - 'norms' collection populated with ISO 9001 EN chunks

Pass criterion:
  At least one of the top-3 results has clause_number starting with "9.3".
  ISO 9001 §9.3 is the management review clause — it must be in the top 3
  for the query "management review" or the dense pipeline has a problem.

Run:
    python query_retrival/smoke_dense.py

With custom hosts:
    QDRANT_HOST=myhost QDRANT_PORT=6333 OLLAMA_URL=http://myhost:11434 python query_retrival/smoke_dense.py

Note on EmbedderService:
  The full EmbedderService (in embedder/embedder.py) imports chunker.models from
  the ingestion pipeline, which is not present in this repo.  The smoke test
  uses a self-contained _embed() helper that makes the identical Ollama HTTP call
  (POST /api/embeddings) with no ingestion-pipeline dependencies.
"""
from __future__ import annotations

import asyncio
import os
import sys

import requests

# smoketest/ → tests/ → query_retrival/ → retrival/  (where models.py lives)
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from models import TransformedQuery
from query_retrival.retriever import DenseRetriever, EmptyCorpusError

# ── Config ────────────────────────────────────────────────────────────────────

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
# Note: only FR data is currently ingested; EN collection is empty.
# "revue de direction" is the French equivalent of "management review" (ISO 9001 §9.3).
QUERY_TEXT = "revue de direction"
LANGUAGE = "FR"
TOP_K = 10  # retrieve top-10, check top-3 for §9.3


# ── Inline embedder ───────────────────────────────────────────────────────────

class _OllamaEmbedder:
    """
    Minimal embedder that wraps Ollama /api/embeddings for the smoke test.

    Identical HTTP call to EmbedderService.embed_text() but without the
    ingestion-pipeline dependency chain (chunker.models, NormChunk, etc.).
    """

    def __init__(self, base_url: str, model: str) -> None:
        self._endpoint = f"{base_url}/api/embeddings"
        self._model = model

    async def embed_text(self, text: str) -> list:
        resp = await asyncio.to_thread(
            requests.post,
            self._endpoint,
            json={"model": self._model, "prompt": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_query(text: str, language: str = "FR") -> TransformedQuery:
    qdrant_filter = Filter(
        must=[
            FieldCondition(key="norm_id", match=MatchValue(value="ISO9001")),
            FieldCondition(key="language", match=MatchValue(value=language)),
        ]
    )
    return TransformedQuery(
        embed_text=text,
        bm25_tokens=text.lower().split(),
        qdrant_filter=qdrant_filter,
        hyde_used=False,
        iso_vocab_hits=[],
        original_query=text,
        language=language,
    )


def _sep(char: str = "─", width: int = 72) -> None:
    print(char * width)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    print()
    _sep("═")
    print("Dense Retriever — Smoke Test")
    print(f"Query     : '{QUERY_TEXT}'")
    print(f"Qdrant    : {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"Ollama    : {OLLAMA_URL}  model={OLLAMA_MODEL}")
    print(f"Norm      : ISO9001  language={LANGUAGE}")
    print(f"top_k     : {TOP_K}  (pass criterion: §9.3 in top 3)")
    _sep("═")
    print()

    embedder = _OllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    retriever = DenseRetriever(embedder=embedder, qdrant=qdrant)
    query = _build_query(QUERY_TEXT, language=LANGUAGE)

    print("Embedding and searching …\n")
    try:
        chunks = await retriever.retrieve(query, top_k=TOP_K)
    except EmptyCorpusError as exc:
        print(f"[FAIL] EmptyCorpusError — {exc}")
        print()
        print("Diagnose:")
        print("  Situation A — run the ingestion pipeline first.")
        print("  Situation B — check that norm_id in Qdrant payload is exactly 'ISO9001'.")
        return 1
    except Exception as exc:
        print(f"[FAIL] Unexpected error: {type(exc).__name__}: {exc}")
        return 1

    _sep()
    print(f"{'Rank':<6} {'clause_number':<16} {'rrf_score':<12} clause_title")
    _sep()
    for i, chunk in enumerate(chunks, start=1):
        marker = " ← §9.3" if chunk.clause_number.startswith("9.3") else ""
        print(
            f"{i:<6} {chunk.clause_number:<16} {chunk.rrf_score:<12.4f} "
            f"{chunk.clause_title}{marker}"
        )
    _sep()
    print()

    top3 = chunks[:3]
    passed = any(c.clause_number.startswith("9.3") for c in top3)

    if passed:
        matched = [c.clause_number for c in top3 if c.clause_number.startswith("9.3")]
        print(f"[PASS] §9.3 chunk(s) in top 3: {matched}")
    else:
        top3_numbers = [c.clause_number for c in top3]
        print(f"[FAIL] §9.3 not in top 3. Top-3 clause numbers: {top3_numbers}")
        print()
        print("Debug checklist:")
        print("  1. Confirm nomic-embed-text is the ingestion model (check embedding_model in a §9.3 payload).")
        print("  2. Verify embed_text() is called with no mismatched prefix vs ingestion.")
        print("  3. Pull a §9.3 chunk from Qdrant and confirm its text contains 'management review'.")
        print("  4. Check the 'norms' collection vector config — dense vector name must match.")

    print()
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
