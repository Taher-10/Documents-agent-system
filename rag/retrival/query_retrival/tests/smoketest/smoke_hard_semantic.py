"""
query_retrival/smoke_hard_compare.py
────────────────────────────────────
Hard semantic comparison: Dense-only vs Hybrid (ISO 9001 — FR)

Focus:
  • Only HARD semantic bridging queries
  • Stress test HyDE + hybrid retrieval

Run:
    python rag/retrival/query_retrival/tests/smoketest/smoke_hard_compare.py
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
from rag.retrival.query_retrival.retriever_dense import DenseRetriever, EmptyCorpusError as DenseEmptyCorpusError
from rag.retrival.query_retrival.retriever import HybridRetriever, EmptyCorpusError as HybridEmptyCorpusError
from rag.retrival.query_transformer.Querytransformer import transform


# ── Config ────────────────────────────────────────────────────────────────────

QDRANT_HOST  = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT  = int(os.getenv("QDRANT_PORT", "6333"))
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
LANGUAGE     = "FR"
NORM_FILTER  = ["ISO9001"]
RETRIEVE_K   = 10
RECALL_K = 10


# ── TestCase ──────────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    name: str
    query: str
    expected_any: List[str]
    top_k_pass: int
    difficulty: str
    fmt: str


# ── HARD TESTS (20) ───────────────────────────────────────────────────────────

TESTS: List[TestCase] = [

## ─────────────────── SUPPORT (suite) ───────────────────

TestCase(
    name="14. 7.5 Information documentée (non conforme)",
    query=(
        "7.5 Information documentée\n"
        "Les procédures environnementales existent, cependant elles ne sont pas "
        "révisées régulièrement et certaines versions obsolètes restent utilisées "
        "au sein des opérations."
    ),
    expected_any=["7.5"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph_non_conformity",
),

TestCase(
    name="15. 7.4 Communication",
    query=(
        "7.4 Communication\n"
        "L’organisation établit des processus pour assurer la communication interne "
        "et externe relative à son système de management environnemental, y compris "
        "avec les autorités réglementaires."
    ),
    expected_any=["7.4"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph",
),

# ─────────────────── OPÉRATION ───────────────────

TestCase(
    name="16. 8.1 Maîtrise opérationnelle",
    query=(
        "8.1 Planification et maîtrise opérationnelle\n"
        "Les processus sont planifiés et contrôlés afin de garantir que les activités "
        "sont réalisées dans des conditions maîtrisées, réduisant ainsi les impacts "
        "environnementaux significatifs."
    ),
    expected_any=["8.1"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph",
),

TestCase(
    name="17. 8.1 Cycle de vie (partiel)",
    query=(
        "8.1 Planification et maîtrise opérationnelle\n"
        "L’organisation considère certains aspects du cycle de vie des produits, "
        "notamment la phase de production, mais néglige les impacts liés à la fin de vie."
    ),
    expected_any=["8.1"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph_partial",
),

TestCase(
    name="18. 8.1 Absence de maîtrise (non conforme)",
    query=(
        "8.1 Planification et maîtrise opérationnelle\n"
        "Aucun contrôle opérationnel formel n’est mis en place pour gérer les "
        "aspects environnementaux identifiés."
    ),
    expected_any=["8.1"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph_non_conformity",
),

TestCase(
    name="19. 8.2 Préparation aux urgences",
    query=(
        "8.2 Préparation et réponse aux situations d’urgence\n"
        "Des procédures sont établies pour identifier les situations d’urgence "
        "potentielles et y répondre efficacement afin de prévenir ou atténuer "
        "les impacts environnementaux."
    ),
    expected_any=["8.2"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph",
),

TestCase(
    name="20. 8.2 Urgences non gérées (non conforme)",
    query=(
        "8.2 Préparation et réponse aux situations d’urgence\n"
        "L’organisation ne dispose d’aucun plan documenté pour gérer les situations "
        "d’urgence environnementale telles que les déversements accidentels."
    ),
    expected_any=["8.2"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph_non_conformity",
),

# ─────────────────── PERFORMANCE ───────────────────

TestCase(
    name="21. 9.1 Surveillance et mesure",
    query=(
        "9.1 Surveillance, mesure, analyse et évaluation\n"
        "Les paramètres environnementaux clés, tels que les émissions et la consommation "
        "d’énergie, sont surveillés et analysés afin d’évaluer la performance environnementale."
    ),
    expected_any=["9.1"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph",
),

TestCase(
    name="22. 9.1 Absence de suivi (non conforme)",
    query=(
        "9.1 Surveillance, mesure, analyse et évaluation\n"
        "Aucun indicateur environnemental n’est défini et aucune surveillance systématique "
        "n’est réalisée."
    ),
    expected_any=["9.1"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph_non_conformity",
),

TestCase(
    name="23. 9.1.2 Évaluation conformité",
    query=(
        "9.1.2 Évaluation de la conformité\n"
        "L’organisation évalue périodiquement sa conformité aux exigences légales "
        "et autres exigences applicables."
    ),
    expected_any=["9.1.2"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph",
),

TestCase(
    name="24. 9.2 Audit interne",
    query=(
        "9.2 Audit interne\n"
        "Des audits internes sont réalisés à intervalles planifiés afin de vérifier "
        "la conformité et l’efficacité du système de management environnemental."
    ),
    expected_any=["9.2"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph",
),

TestCase(
    name="25. 9.2 Audit absent (non conforme)",
    query=(
        "9.2 Audit interne\n"
        "Aucun audit interne n’est réalisé pour évaluer le système environnemental."
    ),
    expected_any=["9.2"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph_non_conformity",
),

TestCase(
    name="26. 9.3 Revue de direction",
    query=(
        "9.3 Revue de direction\n"
        "La direction examine régulièrement le système de management environnemental "
        "afin de garantir sa pertinence, son adéquation et son efficacité."
    ),
    expected_any=["9.3"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph",
),

# ─────────────────── AMÉLIORATION ───────────────────

TestCase(
    name="27. 10.2 Non-conformité et action corrective",
    query=(
        "10.2 Non-conformité et action corrective\n"
        "Lorsqu’une non-conformité survient, l’organisation met en œuvre des actions "
        "correctives pour en éliminer la cause et éviter sa récurrence."
    ),
    expected_any=["10.2"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph",
),

TestCase(
    name="28. 10.2 Non-conformité non traitée",
    query=(
        "10.2 Non-conformité et action corrective\n"
        "Les incidents environnementaux sont identifiés mais aucune action corrective "
        "n’est mise en place pour en traiter les causes."
    ),
    expected_any=["10.2"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph_non_conformity",
),

TestCase(
    name="29. 10.3 Amélioration continue",
    query=(
        "10.3 Amélioration continue\n"
        "L’organisation améliore continuellement la pertinence et l’efficacité "
        "de son système de management environnemental."
    ),
    expected_any=["10.3"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph",
),

TestCase(
    name="30. 10.3 Amélioration absente (non conforme)",
    query=(
        "10.3 Amélioration continue\n"
        "Aucune action n’est entreprise pour améliorer le système de management "
        "environnemental au fil du temps."
    ),
    expected_any=["10.3"],
    top_k_pass=10,
    difficulty="hard",
    fmt="paragraph_non_conformity",
),

]
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
class PathResult:
    passed: bool
    top3: List[str]
    matched_at: Optional[int]
    error: Optional[str]


@dataclass
class CompareResult:
    tc: TestCase
    tq: Optional[TransformedQuery]   # None if transform() failed
    transform_error: Optional[str]
    dense: PathResult
    hybrid: PathResult


# ── Helpers ───────────────────────────────────────────────────────────────────

DIFF_ICON = {"easy": "○", "medium": "◑", "hard": "●"}

def _sep(char: str = "─", width: int = 84) -> None:
    print(char * width)

def _truncate(s: str, n: int = 70) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"

def _eval_path(chunks: List[RetrievedChunk], tc: TestCase) -> PathResult:
    top10 = [c.clause_number for c in chunks[:RECALL_K]]
    top3  = [c.clause_number for c in chunks[:3]]

    matched_at = None
    for i, chunk in enumerate(chunks[:RECALL_K], start=1):
        if any(chunk.clause_number.startswith(pfx) for pfx in tc.expected_any):
            matched_at = i
            break

    return PathResult(
        passed=matched_at is not None,
        top3=top3,
        matched_at=matched_at,
        error=None
    )
def _error_path(msg: str) -> PathResult:
    return PathResult(passed=False, top3=[], matched_at=None, error=msg)


# ── Runner ────────────────────────────────────────────────────────────────────

async def run_tests(
    dense_retriever: DenseRetriever,
    hybrid_retriever: HybridRetriever,
) -> List[CompareResult]:
    results: List[CompareResult] = []

    for tc in TESTS:
        # Step 1 — shared transform (full pipeline: HyDE + ISO vocab + BM25)
        tq: Optional[TransformedQuery] = None
        transform_error: Optional[str] = None
        try:
            tq = transform(tc.query, norm_filter=NORM_FILTER, language=LANGUAGE)
        except Exception as exc:
            transform_error = f"{type(exc).__name__}: {exc}"
            results.append(CompareResult(
                tc=tc, tq=None, transform_error=transform_error,
                dense=_error_path("transform failed"),
                hybrid=_error_path("transform failed"),
            ))
            continue

        # Step 2 — Dense-only retrieve
        try:
            dense_chunks = await dense_retriever.retrieve(tq, top_k=RETRIEVE_K)
            dense_result = _eval_path(dense_chunks, tc)
        except DenseEmptyCorpusError as exc:
            dense_result = _error_path(f"EmptyCorpusError: {exc}")
        except Exception as exc:
            dense_result = _error_path(f"{type(exc).__name__}: {exc}")

        # Step 3 — Hybrid retrieve (same TransformedQuery)
        try:
            hybrid_chunks = await hybrid_retriever.retrieve(tq, top_k=RETRIEVE_K)
            hybrid_result = _eval_path(hybrid_chunks, tc)
        except HybridEmptyCorpusError as exc:
            hybrid_result = _error_path(f"EmptyCorpusError: {exc}")
        except Exception as exc:
            hybrid_result = _error_path(f"{type(exc).__name__}: {exc}")

        results.append(CompareResult(
            tc=tc, tq=tq, transform_error=None,
            dense=dense_result, hybrid=hybrid_result,
        ))

    return results


# ── Print per-result detail ───────────────────────────────────────────────────

def _pass_icon(r: PathResult) -> str:
    return "✓" if r.passed else "✗"

def _rank_str(r: PathResult) -> str:
    if r.error:
        return f"ERROR: {r.error}"
    rank = f"rank {r.matched_at}" if r.matched_at else f"NO MATCH in top-{RECALL_K}"
    return f"top-3: {r.top3}  │  {rank}"

def print_detail(r: CompareResult) -> None:
    overall_icon = "✓" if (r.dense.passed or r.hybrid.passed) else "✗"
    diff_icon = DIFF_ICON.get(r.tc.difficulty, " ")
    print(f"\n  {overall_icon} {diff_icon} {r.tc.name}")
    print(f"     fmt={r.tc.fmt:<28} difficulty={r.tc.difficulty}  threshold=top-{RECALL_K} (recall mode)")
    print(f"     expected ∈ {r.tc.expected_any}")

    query_preview = _truncate(r.tc.query.replace("\n", " "))
    print(f"     query: \"{query_preview}\"")

    if r.transform_error:
        print(f"     TRANSFORM ERROR: {r.transform_error}")
        return

    assert r.tq is not None
    hyde_str = "YES" if r.tq.hyde_used else "no"
    vocab_preview = r.tq.iso_vocab_hits[:5] if r.tq.iso_vocab_hits else []
    print(f"     HyDE={hyde_str}  iso_vocab_hits={vocab_preview}")
    print(f"     bm25_tokens ({len(r.tq.bm25_tokens)}): {sorted(r.tq.bm25_tokens)}")

    dense_mark = _pass_icon(r.dense)
    hybrid_mark = _pass_icon(r.hybrid)
    print(f"     Dense-only  {dense_mark}  │  {_rank_str(r.dense)}")
    print(f"     Hybrid      {hybrid_mark}  │  {_rank_str(r.hybrid)}")

    # Ranking diff
    if not r.dense.error and not r.hybrid.error:
        if r.dense.top3 == r.hybrid.top3:
            print(f"     Ranking diff: NO  (top-3 identical)")
        else:
            changed = [
                i + 1 for i, (d, h) in enumerate(zip(r.dense.top3, r.hybrid.top3)) if d != h
            ]
            print(f"     Ranking diff: YES  (positions {changed} changed)")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    print()
    _sep("═", 84)
    print(" Full Pipeline Comparison — Dense-only vs Hybrid")
    print(f" Corpus   : ISO 9001 · language={LANGUAGE} · Qdrant {QDRANT_HOST}:{QDRANT_PORT}")
    print(f" Embedder : {OLLAMA_MODEL} via {OLLAMA_URL}")
    print(f" Tests    : {len(TESTS)}  (easy={sum(1 for t in TESTS if t.difficulty=='easy')}  "
          f"medium={sum(1 for t in TESTS if t.difficulty=='medium')}  "
          f"hard={sum(1 for t in TESTS if t.difficulty=='hard')})")
    print(f" Legend   : ○ easy  ◑ medium  ● hard")
    _sep("═", 84)

    embedder       = _OllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)
    qdrant         = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    dense_retriever  = DenseRetriever(embedder=embedder, qdrant=qdrant)
    hybrid_retriever = HybridRetriever(embedder=embedder, qdrant=qdrant)

    print("\nRunning tests (transform + dense + hybrid per case) …")
    results = await run_tests(dense_retriever, hybrid_retriever)

    # ── Per-result detail ──
    _sep()
    for r in results:
        print_detail(r)

    # ── Summary ──────────────────────────────────────────────────────────────
    dense_passed  = [r for r in results if r.dense.passed]
    hybrid_passed = [r for r in results if r.hybrid.passed]

    ranking_diffs = sum(
        1 for r in results
        if not r.dense.error and not r.hybrid.error and r.dense.top3 != r.hybrid.top3
    )

    print()
    _sep("═", 84)
    print(f"\n RESULTS")
    print(f"   Dense-only : {len(dense_passed)}/{len(results)} passed")
    print(f"   Hybrid     : {len(hybrid_passed)}/{len(results)} passed")
    print(f"   Ranking changed in {ranking_diffs}/{len(results)} test cases "
          f"(sparse signal active)")
    print()

    # Score by difficulty
    by_diff: dict = {"easy": [], "medium": [], "hard": []}
    for r in results:
        by_diff[r.tc.difficulty].append((r.dense.passed, r.hybrid.passed))

    print(" Score by difficulty:")
    print(f"   {'':8}  {'Dense':>6}  {'Hybrid':>6}  bar (Dense░ / Hybrid█)")
    for d, pairs in by_diff.items():
        n = len(pairs)
        nd = sum(p[0] for p in pairs)
        nh = sum(p[1] for p in pairs)
        bar_d = "░" * nd + " " * (n - nd)
        bar_h = "█" * nh + " " * (n - nh)
        icon = DIFF_ICON[d]
        print(f"   {icon} {d:<8}  {nd}/{n}      {nh}/{n}      [{bar_d}] [{bar_h}]")

    print()
    # Failed tests
    failed_dense  = [r for r in results if not r.dense.passed]
    failed_hybrid = [r for r in results if not r.hybrid.passed]
    if failed_dense or failed_hybrid:
        all_failed = {r.tc.name for r in failed_dense} | {r.tc.name for r in failed_hybrid}
        print(" Failed cases:")
        for r in results:
            d_fail = not r.dense.passed
            h_fail = not r.hybrid.passed
            if d_fail or h_fail:
                label = []
                if d_fail:  label.append("dense")
                if h_fail:  label.append("hybrid")
                diff_icon = DIFF_ICON.get(r.tc.difficulty, " ")
                print(f"   ✗ {diff_icon} {r.tc.name}  [{', '.join(label)} failed]")
        print()

    # Overall status
    dense_pct  = len(dense_passed)  / len(results) * 100
    hybrid_pct = len(hybrid_passed) / len(results) * 100

    for label, pct in [("Dense-only", dense_pct), ("Hybrid    ", hybrid_pct)]:
        if pct == 100:
            print(f" 🟢 {label}: All tests passed ({pct:.0f}%)")
        elif pct >= 80:
            print(f" 🟡 {label}: Most tests passed ({pct:.0f}%)")
        else:
            print(f" 🔴 {label}: Too many failures ({pct:.0f}%) — investigate pipeline")

    print()
    _sep("═", 84)
    print()
    return 0 if (len(dense_passed) == len(results) and len(hybrid_passed) == len(results)) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))