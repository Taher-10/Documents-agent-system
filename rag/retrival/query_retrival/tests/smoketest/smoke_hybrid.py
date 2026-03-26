"""
query_retrival/smoke_hybrid.py
────────────────────────────────
Live integration smoke test for HybridRetriever (Step 4 — Dense + Sparse + RRF).

Runs the same "revue de direction" query in two modes and compares rankings:
  A. Dense-only  — bm25_tokens=[] forces single Prefetch (dense path)
  B. Hybrid      — full bm25_tokens from simple tokenisation

If the ordering changes between A and B, sparse is contributing to ranking.
If the ordering is identical, either the 'sparse' named vector slot is missing
from the Qdrant collection, or the sparse vectors were not populated during
ingestion.

Requires:
  - Qdrant running on localhost:6333 (override with QDRANT_HOST / QDRANT_PORT)
  - Ollama running on localhost:11434 with nomic-embed-text pulled
    (override with OLLAMA_URL / OLLAMA_EMBED_MODEL)
  - 'norms' collection with BOTH 'dense' AND 'sparse' named vector slots
  - FR chunks ingested with sparse BM25 vectors

Pass criterion:
  At least one of the top-3 hybrid results has clause_number starting with "9.3".

Ordering-change criterion (proof that sparse contributes):
  The ranked clause list for hybrid must differ from dense-only.

Run:
    python query_retrival/smoke_hybrid.py

Prerequisite check for sparse vector slot:
    python -c "
    from qdrant_client import QdrantClient
    c = QdrantClient(host='localhost', port=6333)
    info = c.get_collection('norms')
    print('sparse_vectors:', info.config.params.sparse_vectors)
    "
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
from query_retrival.retriever import HybridRetriever, EmptyCorpusError

# ── Config ────────────────────────────────────────────────────────────────────

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

QUERY_TEXT = "revue de direction"
LANGUAGE = "FR"
TOP_K = 10  # retrieve top-10, check top-3 for §9.3


# ── Inline embedder ───────────────────────────────────────────────────────────

class _OllamaEmbedder:
    """Minimal embedder for smoke tests — identical HTTP call to EmbedderService."""

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

def _build_qdrant_filter(language: str) -> Filter:
    return Filter(
        must=[
            FieldCondition(key="norm_id", match=MatchValue(value="ISO9001")),
            FieldCondition(key="language", match=MatchValue(value=language)),
        ]
    )


def _build_dense_only_query(text: str, language: str = "FR") -> TransformedQuery:
    """TransformedQuery with no BM25 tokens — forces single dense Prefetch."""
    return TransformedQuery(
        embed_text=text,
        bm25_tokens=[],        # empty → sparse Prefetch skipped
        qdrant_filter=_build_qdrant_filter(language),
        hyde_used=False,
        iso_vocab_hits=[],
        original_query=text,
        language=language,
    )


def _build_hybrid_query(text: str, language: str = "FR") -> TransformedQuery:
    """TransformedQuery with real BM25 tokens — enables both Prefetches."""
    # Simple tokenisation: lowercase split + ISO vocab hint.
    # In production this comes from QueryTransformer.transform(); here we keep
    # it self-contained to avoid the async transform() call in the smoke test.
    base_tokens = text.lower().split()
    # Add common ISO management-review tokens to exercise the sparse path
    extra = ["revue", "direction", "management", "système", "qualité"]
    tokens = list(dict.fromkeys(base_tokens + extra))  # deduplicate, preserve order
    return TransformedQuery(
        embed_text=text,
        bm25_tokens=tokens,
        qdrant_filter=_build_qdrant_filter(language),
        hyde_used=False,
        iso_vocab_hits=["management review"],
        original_query=text,
        language=language,
    )


def _sep(char: str = "─", width: int = 72) -> None:
    print(char * width)


def _print_results(label: str, chunks: list) -> None:
    _sep()
    print(f"{label}")
    _sep()
    print(f"{'Rank':<6} {'clause_number':<16} {'rrf_score':<12} clause_title")
    _sep()
    for i, chunk in enumerate(chunks, start=1):
        marker = " ← §9.3" if chunk.clause_number.startswith("9.3") else ""
        print(
            f"{i:<6} {chunk.clause_number:<16} {chunk.rrf_score:<12.5f} "
            f"{chunk.clause_title}{marker}"
        )
    _sep()
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    print()
    _sep("═")
    print("Hybrid Retriever — Smoke Test  (Dense + Sparse + RRF)")
    print(f"Query     : '{QUERY_TEXT}'")
    print(f"Qdrant    : {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"Ollama    : {OLLAMA_URL}  model={OLLAMA_MODEL}")
    print(f"Norm      : ISO9001  language={LANGUAGE}")
    print(f"top_k     : {TOP_K}  (pass criterion: §9.3 in top 3 for hybrid run)")
    _sep("═")
    print()

    embedder = _OllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    retriever = HybridRetriever(embedder=embedder, qdrant=qdrant)

    # ── Section A — Dense-only (bm25_tokens=[]) ──────────────────────────────
    print("Section A: Dense-only run (bm25_tokens=[], single Prefetch) …\n")
    query_dense = _build_dense_only_query(QUERY_TEXT, language=LANGUAGE)
    try:
        chunks_dense = await retriever.retrieve(query_dense, top_k=TOP_K)
    except EmptyCorpusError as exc:
        print(f"[FAIL] EmptyCorpusError (dense-only): {exc}")
        _print_diagnose()
        return 1
    except Exception as exc:
        print(f"[FAIL] Unexpected error (dense-only): {type(exc).__name__}: {exc}")
        return 1

    _print_results("Dense-only results", chunks_dense)

    # ── Section B — Hybrid (dense + sparse + RRF) ─────────────────────────────
    print("Section B: Hybrid run (dense + sparse + RRF, two Prefetches) …\n")
    query_hybrid = _build_hybrid_query(QUERY_TEXT, language=LANGUAGE)
    try:
        chunks_hybrid = await retriever.retrieve(query_hybrid, top_k=TOP_K)
    except EmptyCorpusError as exc:
        print(f"[FAIL] EmptyCorpusError (hybrid): {exc}")
        print()
        print("Likely cause: 'sparse' named vector slot missing from 'norms' collection.")
        print("Run the prerequisite check in the module docstring to verify.")
        return 1
    except Exception as exc:
        print(f"[FAIL] Unexpected error (hybrid): {type(exc).__name__}: {exc}")
        return 1

    _print_results("Hybrid results (Dense + Sparse + RRF)", chunks_hybrid)

    # ── Comparison ────────────────────────────────────────────────────────────
    dense_order = [c.clause_number for c in chunks_dense[:5]]
    hybrid_order = [c.clause_number for c in chunks_hybrid[:5]]

    _sep("═")
    print("Ordering comparison (top-5 clause numbers):")
    print(f"  Dense-only : {dense_order}")
    print(f"  Hybrid     : {hybrid_order}")
    _sep()
    print()

    if dense_order == hybrid_order:
        print("[WARN] Ordering UNCHANGED — sparse may not be contributing.")
        print("       Possible reasons:")
        print("         1. 'sparse' named vector slot not configured in 'norms' collection")
        print("         2. Sparse vectors were not stored during ingestion")
        print("         3. bm25_tokens tokens have zero overlap with stored BM25 vocabulary")
        print("       Run the prerequisite check in the module docstring to verify.")
        print()
    else:
        print("[INFO] Ordering CHANGED ✓ — both dense and sparse signals are contributing.")
        changed_positions = [
            i + 1 for i, (d, h) in enumerate(zip(dense_order, hybrid_order)) if d != h
        ]
        print(f"       Positions where ranking changed: {changed_positions}")
        print()

    # ── Pass criterion ────────────────────────────────────────────────────────
    top3_hybrid = chunks_hybrid[:3]
    passed = any(c.clause_number.startswith("9.3") for c in top3_hybrid)

    if passed:
        matched = [c.clause_number for c in top3_hybrid if c.clause_number.startswith("9.3")]
        print(f"[PASS] §9.3 chunk(s) in hybrid top 3: {matched}")
    else:
        top3_numbers = [c.clause_number for c in top3_hybrid]
        print(f"[FAIL] §9.3 not in hybrid top 3. Top-3 clause numbers: {top3_numbers}")
        print()
        print("Debug checklist:")
        print("  1. Confirm nomic-embed-text is the ingestion model.")
        print("  2. Check that sparse vectors were stored at ingestion time.")
        print("  3. Verify the 'sparse' slot name matches the ingestion slot name.")

    print()
    return 0 if passed else 1


def _print_diagnose() -> None:
    print()
    print("Diagnose:")
    print("  Situation A — run the ingestion pipeline first.")
    print("  Situation B — check that norm_id in Qdrant payload is exactly 'ISO9001'.")
    print("  Situation C — verify 'norms' collection has both 'dense' and 'sparse' slots.")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
