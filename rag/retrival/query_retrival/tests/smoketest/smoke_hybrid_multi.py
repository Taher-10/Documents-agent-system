"""
query_retrival/smoke_hybrid_multi.py
──────────────────────────────────────
Full end-to-end smoke test: QueryTransformer → HybridRetriever (real scenario).

Runs the same 15 test cases as smoke_dense_multi.py but through the complete
production pipeline:
  raw_query → QueryTransformer.transform()  (HyDE + ISO vocab + BM25 tokens)
            → HybridRetriever.retrieve()    (dense + sparse + RRF)

Per-test output includes:
  - hyde_used flag and iso_vocab_hits from the transformer
  - Number of BM25 tokens generated
  - Top-3 retrieved clause numbers
  - Pass/fail vs threshold

Baseline comparison table is printed at the end:
  Dense-only (bm25_tokens=[]) | Hybrid (smoke_dense_multi naive) | Full pipeline (this test)

Requires:
  - Qdrant running on localhost:6333  (override QDRANT_HOST / QDRANT_PORT)
  - Ollama running on localhost:11434 with nomic-embed-text pulled
    (override OLLAMA_URL / OLLAMA_EMBED_MODEL)
  - LLM for HyDE (override LLM_PROVIDER / see llm_client.py)
  - 'norms' collection with 'dense' + 'sparse' named vector slots ingested

Run:
    python rag/retrival/query_retrival/tests/smoketest/smoke_hybrid_multi.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

import requests
from qdrant_client import QdrantClient

from rag.retrival.models import TransformedQuery, RetrievedChunk
from rag.retrival.query_retrival.retriever import HybridRetriever, EmptyCorpusError
from rag.retrival.query_transformer.Querytransformer import transform

# Re-use the canonical test cases and display helpers from smoke_dense_multi
sys.path.insert(0, os.path.dirname(__file__))
from smoke_dense_multi import TESTS, TestCase, DIFF_ICON, _sep, _truncate

# ── Config ────────────────────────────────────────────────────────────────────

QDRANT_HOST  = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT  = int(os.getenv("QDRANT_PORT", "6333"))
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
LANGUAGE     = "FR"
NORM_FILTER  = ["ISO9001"]
RETRIEVE_K   = 10


# ── Inline embedder ───────────────────────────────────────────────────────────

class _OllamaEmbedder:
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


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class HybridResult:
    tc: TestCase
    passed: bool
    top3: List[str]
    matched_at: Optional[int]
    hyde_used: bool
    iso_vocab_hits: List[str]
    bm25_token_count: int
    embed_text_preview: str   # first 80 chars of what was actually embedded
    error: Optional[str]


# ── Runner ────────────────────────────────────────────────────────────────────

async def run_tests(retriever: HybridRetriever) -> List[HybridResult]:
    results: List[HybridResult] = []

    for tc in TESTS:
        # Full production pipeline: QueryTransformer → TransformedQuery
        try:
            tq: TransformedQuery = await transform(
                query_text=tc.query,
                norm_filter=NORM_FILTER,
                language=LANGUAGE,
            )
        except Exception as exc:
            results.append(HybridResult(
                tc=tc, passed=False, top3=[], matched_at=None,
                hyde_used=False, iso_vocab_hits=[], bm25_token_count=0,
                embed_text_preview="", error=f"transform() failed: {type(exc).__name__}: {exc}",
            ))
            continue

        # HybridRetriever with the transformer output
        try:
            chunks = await retriever.retrieve(tq, top_k=RETRIEVE_K)
        except EmptyCorpusError as exc:
            results.append(HybridResult(
                tc=tc, passed=False, top3=[], matched_at=None,
                hyde_used=tq.hyde_used, iso_vocab_hits=tq.iso_vocab_hits,
                bm25_token_count=len(tq.bm25_tokens),
                embed_text_preview=tq.embed_text[:80],
                error=f"EmptyCorpusError: {exc}",
            ))
            continue
        except Exception as exc:
            results.append(HybridResult(
                tc=tc, passed=False, top3=[], matched_at=None,
                hyde_used=tq.hyde_used, iso_vocab_hits=tq.iso_vocab_hits,
                bm25_token_count=len(tq.bm25_tokens),
                embed_text_preview=tq.embed_text[:80],
                error=f"{type(exc).__name__}: {exc}",
            ))
            continue

        top3 = [c.clause_number for c in chunks[:3]]
        matched_at = None
        for i, chunk in enumerate(chunks[:tc.top_k_pass], start=1):
            if any(chunk.clause_number.startswith(pfx) for pfx in tc.expected_any):
                matched_at = i
                break

        results.append(HybridResult(
            tc=tc,
            passed=matched_at is not None,
            top3=top3,
            matched_at=matched_at,
            hyde_used=tq.hyde_used,
            iso_vocab_hits=tq.iso_vocab_hits,
            bm25_token_count=len(tq.bm25_tokens),
            embed_text_preview=tq.embed_text[:80],
            error=None,
        ))

    return results


# ── Display helpers ───────────────────────────────────────────────────────────

def print_detail(r: HybridResult) -> None:
    icon = "✓" if r.passed else "✗"
    diff = DIFF_ICON.get(r.tc.difficulty, " ")
    print(f"\n  {icon} {diff} {r.tc.name}")
    print(f"     fmt={r.tc.fmt:<25} difficulty={r.tc.difficulty}  threshold=top-{r.tc.top_k_pass}")
    print(f"     expected ∈ {r.tc.expected_any}")

    if r.error:
        print(f"     ERROR: {r.error}")
        return

    # Transformer diagnostics
    hyde_flag = "YES" if r.hyde_used else "no"
    print(f"     hyde={hyde_flag:<4}  bm25_tokens={r.bm25_token_count}  "
          f"iso_hits={r.iso_vocab_hits or '[]'}")
    if r.hyde_used:
        print(f"     embed_text: \"{r.embed_text_preview}…\"")

    print(f"     top-3 results: {r.top3}")
    if r.matched_at:
        print(f"     match at rank {r.matched_at}")
    else:
        print(f"     NO MATCH in top-{r.tc.top_k_pass}")

    query_preview = _truncate(r.tc.query.replace("\n", " "))
    print(f"     query: \"{query_preview}\"")


def print_comparison_table(results: List[HybridResult]) -> None:
    """Side-by-side comparison table vs known baselines."""
    # Dense-only baseline (bm25_tokens=[]) — from prior run
    dense_only = {
        1: "✓ r1", 2: "✓ r1", 3: "✓ r1", 4: "✓ r1", 5: "✓ r1",
        6: "✓ r1", 7: "✓ r6", 8: "✓ r1", 9: "✓ r1", 10: "✓ r1",
        11: "✓ r3", 12: "✓ r1", 13: "✓ r1", 14: "✓ r5", 15: "✓ r2",
    }
    # Naive hybrid baseline (bm25_tokens=text.lower().split()) — smoke_dense_multi
    naive_hybrid = {
        1: "✓ r1", 2: "✓ r1", 3: "✓ r1", 4: "✓ r1", 5: "✓ r1",
        6: "✓ r1", 7: "✗ —",  8: "✓ r1", 9: "✓ r1", 10: "✓ r1",
        11: "✗ —", 12: "✓ r1", 13: "✓ r2", 14: "✓ r5", 15: "✓ r2",
    }

    _sep("═", 80)
    print(" Comparison table: Dense-only | Naive hybrid | Full pipeline (this run)")
    _sep("═", 80)
    hdr = f"{'#':<4} {'Test':<38} {'Dense-only':^12} {'Naive hybrid':^13} {'Full pipeline':^14}"
    print(hdr)
    _sep()

    for i, r in enumerate(results, start=1):
        diff = DIFF_ICON.get(r.tc.difficulty, " ")
        name = _truncate(r.tc.name, 38)
        d = dense_only.get(i, "?")
        n = naive_hybrid.get(i, "?")

        if r.error:
            fp = "✗ ERR"
        elif r.matched_at:
            fp = f"✓ r{r.matched_at}"
        else:
            fp = "✗ —"

        # Highlight regressions (was passing, now failing)
        flag = ""
        was_passing_dense = d.startswith("✓")
        was_passing_naive = n.startswith("✓")
        is_passing = fp.startswith("✓")
        if not is_passing and (was_passing_dense or was_passing_naive):
            flag = " ← REGR"
        elif is_passing and (not was_passing_dense and not was_passing_naive):
            flag = " ← FIXED"
        elif is_passing and (not was_passing_naive):
            flag = " ← FIXED"

        print(f"{diff}{i:<3} {name:<38} {d:^12} {n:^13} {fp:^14}{flag}")

    _sep("═", 80)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    print()
    _sep("═", 80)
    print(" Full Pipeline Smoke Test — QueryTransformer + HybridRetriever")
    print(f" Corpus   : ISO 9001 · language={LANGUAGE} · Qdrant {QDRANT_HOST}:{QDRANT_PORT}")
    print(f" Embedder : {OLLAMA_MODEL} via {OLLAMA_URL}")
    print(f" Pipeline : transform() [HyDE + ISO vocab + BM25] → retrieve() [dense+sparse+RRF]")
    print(f" Tests    : {len(TESTS)}  "
          f"(easy={sum(1 for t in TESTS if t.difficulty=='easy')}  "
          f"medium={sum(1 for t in TESTS if t.difficulty=='medium')}  "
          f"hard={sum(1 for t in TESTS if t.difficulty=='hard')})")
    print(f" Legend   : ○ easy  ◑ medium  ● hard")
    _sep("═", 80)

    embedder  = _OllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)
    qdrant    = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    retriever = HybridRetriever(embedder=embedder, qdrant=qdrant)

    print("\nRunning tests (HyDE calls may add ~15 s per short query) …")
    results = await run_tests(retriever)

    # ── Per-result detail ──
    _sep()
    for r in results:
        print_detail(r)

    # ── Summary ──
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    hyde_count = sum(1 for r in results if r.hyde_used)

    print()
    _sep()
    print(f"\n RESULTS: {len(passed)}/{len(results)} passed  "
          f"(HyDE triggered on {hyde_count}/{len(results)} queries)\n")

    if failed:
        print(" Failed tests:")
        for r in failed:
            diff = DIFF_ICON.get(r.tc.difficulty, " ")
            print(f"   ✗ {diff} {r.tc.name}")
            if r.error:
                print(f"        error: {r.error}")
            else:
                print(f"        top-3={r.top3}  expected ∈ {r.tc.expected_any} in top-{r.tc.top_k_pass}")
        print()

    by_diff: dict = {"easy": [], "medium": [], "hard": []}
    for r in results:
        by_diff[r.tc.difficulty].append(r.passed)
    print(" Score by difficulty:")
    for d, outcomes in by_diff.items():
        n_pass = sum(outcomes); total = len(outcomes)
        bar = "█" * n_pass + "░" * (total - n_pass)
        print(f"   {DIFF_ICON[d]} {d:<8} {n_pass}/{total}  {bar}")

    print()
    overall = len(passed) / len(results) * 100
    if overall == 100:
        print(f" 🟢 All tests passed ({overall:.0f}%)")
    elif overall >= 80:
        print(f" 🟡 Most tests passed ({overall:.0f}%)")
    else:
        print(f" 🔴 Too many failures ({overall:.0f}%) — investigate pipeline")

    # ── Comparison table ──
    print()
    print_comparison_table(results)
    print()

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
