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

    TestCase(
        name="1. Analyse contexte organisation",
        query=(
            "L'organisation analyse régulièrement les facteurs internes et externes "
            "susceptibles d’influencer ses performances, tout en identifiant les parties "
            "intéressées pertinentes telles que les clients, autorités réglementaires "
            "et partenaires, ainsi que leurs exigences évolutives."
        ),
        expected_any=["4.1", "4.2"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    TestCase(
        name="2. Engagement direction système",
        query=(
            "La direction démontre son engagement en intégrant le système de management "
            "dans les processus métiers, en promouvant l’approche processus et en "
            "soutenant les initiatives liées à la qualité et à l’environnement."
        ),
        expected_any=["5.1"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    TestCase(
        name="3. Politique alignée stratégie",
        query=(
            "Une politique qualité et environnementale est définie, communiquée et alignée "
            "avec la stratégie globale de l’entreprise, incluant des engagements envers "
            "la conformité réglementaire et l’amélioration continue."
        ),
        expected_any=["5.2"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    TestCase(
        name="4. Identification risques opportunités",
        query=(
            "Les risques et opportunités liés aux processus, aux aspects environnementaux "
            "et aux obligations de conformité sont identifiés et pris en compte afin "
            "d’assurer l’atteinte des résultats attendus."
        ),
        expected_any=["6.1"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    TestCase(
        name="5. Objectifs mesurables pilotés",
        query=(
            "Des objectifs mesurables sont établis à différents niveaux de l’organisation, "
            "avec des indicateurs de performance, des échéances définies et des méthodes "
            "de suivi adaptées."
        ),
        expected_any=["6.2"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    TestCase(
        name="6. Gestion ressources et compétences",
        query=(
            "L’organisation met à disposition les ressources nécessaires et s’assure que "
            "le personnel est compétent sur la base de formations, d’expériences et "
            "d’évaluations périodiques de leur efficacité."
        ),
        expected_any=["7.1", "7.2"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    TestCase(
        name="7. Sensibilisation et communication",
        query=(
            "Les employés sont sensibilisés à la politique et aux objectifs, tandis que "
            "les communications internes et externes sont structurées et cohérentes avec "
            "les exigences réglementaires."
        ),
        expected_any=["7.3", "7.4"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    TestCase(
        name="8. Maîtrise information documentée",
        query=(
            "Les informations documentées sont correctement contrôlées, incluant leur "
            "création, mise à jour, diffusion et conservation afin d’éviter toute "
            "utilisation de versions obsolètes."
        ),
        expected_any=["7.5"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    TestCase(
        name="9. Maîtrise opérationnelle globale",
        query=(
            "Les processus opérationnels sont planifiés, mis en œuvre et contrôlés, y compris "
            "les activités externalisées, afin de garantir la conformité des produits et la "
            "réduction des impacts environnementaux."
        ),
        expected_any=["8.1"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    TestCase(
        name="10. Suivi et analyse performance",
        query=(
            "L’organisation surveille et mesure ses performances à l’aide d’indicateurs "
            "pertinents, analyse les résultats et évalue la conformité aux exigences "
            "applicables."
        ),
        expected_any=["9.1"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    TestCase(
        name="11. Programme audit interne",
        query=(
            "Des audits internes sont planifiés et réalisés pour vérifier la conformité "
            "du système de management et son efficacité par rapport aux exigences définies."
        ),
        expected_any=["9.2"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    TestCase(
        name="12. Amélioration continue système",
        query=(
            "L’organisation améliore en continu son système de management en s’appuyant "
            "sur les résultats de performance, les audits et les actions correctives."
        ),
        expected_any=["10.3"],
        top_k_pass=10,
        difficulty="hard",
        fmt="semantic scenario",
    ),

    # ── PARTIAL / FAILURE CASES ──

    TestCase(
        name="13. Absence calibration équipements",
        query=(
            "Les उपकरणs de mesure sont utilisés dans les processus mais aucune procédure "
            "de calibration ou de vérification n’est définie pour garantir la validité des résultats."
        ),
        expected_any=["7.1.5"],
        top_k_pass=10,
        difficulty="hard",
        fmt="gap detection",
    ),

    TestCase(
        name="14. Compétence non démontrée",
        query=(
            "Le personnel occupe des postes critiques mais aucune preuve de formation, "
            "qualification ou évaluation de compétence n’est disponible."
        ),
        expected_any=["7.2"],
        top_k_pass=10,
        difficulty="hard",
        fmt="gap detection",
    ),

    TestCase(
        name="15. Absence approche risques",
        query=(
            "Les processus sont exécutés sans identification formelle des risques et "
            "opportunités pouvant impacter les résultats attendus."
        ),
        expected_any=["6.1"],
        top_k_pass=10,
        difficulty="hard",
        fmt="gap detection",
    ),

    TestCase(
        name="16. Documents non contrôlés",
        query=(
            "Des documents existent mais il n’existe aucun mécanisme de gestion des versions, "
            "ni de contrôle d’accès ou d’archivage fiable."
        ),
        expected_any=["7.5"],
        top_k_pass=10,
        difficulty="hard",
        fmt="gap detection",
    ),

    TestCase(
        name="17. Absence action corrective",
        query=(
            "Des non-conformités sont détectées mais aucune démarche structurée n’est mise en place "
            "pour identifier les causes racines et éviter leur réapparition."
        ),
        expected_any=["10.2"],
        top_k_pass=10,
        difficulty="hard",
        fmt="gap detection",
    ),

    TestCase(
        name="18. Absence mesure performance",
        query=(
            "Les activités sont réalisées sans indicateurs de performance ni analyse des résultats, "
            "ce qui empêche toute évaluation objective."
        ),
        expected_any=["9.1"],
        top_k_pass=10,
        difficulty="hard",
        fmt="gap detection",
    ),

    TestCase(
        name="19. Absence audit interne",
        query=(
            "Aucun audit interne n’est réalisé pour vérifier la conformité du système de management "
            "aux exigences ISO."
        ),
        expected_any=["9.2"],
        top_k_pass=10,
        difficulty="hard",
        fmt="gap detection",
    ),

    TestCase(
        name="20. Engagement direction insuffisant",
        query=(
            "La direction définit des politiques mais ne participe pas activement à leur mise en œuvre "
            "ni à leur intégration dans les processus de l’organisation."
        ),
        expected_any=["5.1"],
        top_k_pass=10,
        difficulty="hard",
        fmt="gap detection",
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
            tq = await transform(tc.query, norm_filter=NORM_FILTER, language=LANGUAGE)
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