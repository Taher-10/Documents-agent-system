"""
query_retrival/smoke_compare.py
────────────────────────────────
Full-pipeline comparison smoke test: Dense-only vs Hybrid.

Runs all 15 test cases from smoke_dense_multi.py through the real
QueryTransformer.transform() pipeline (HyDE + ISO vocab injection +
BM25 tokenisation), then retrieves with both:

  Path A — transform() → DenseRetriever   (dense cosine only)
  Path B — transform() → HybridRetriever  (dense + sparse + RRF)

Each test case shows:
  • The TransformedQuery metadata (HyDE used, ISO vocab hits)
  • Top-3 clause numbers for each path
  • Pass/fail for each path
  • Whether the ranked order differed between paths

Run:
    python rag/retrival/query_retrival/tests/smoketest/smoke_compare.py

Override hosts:
    QDRANT_HOST=myhost QDRANT_PORT=6333 OLLAMA_URL=http://myhost:11434 \\
        python rag/retrival/query_retrival/tests/smoketest/smoke_compare.py
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


# ── Test case definition ──────────────────────────────────────────────────────

@dataclass
class TestCase:
    name: str
    query: str
    expected_any: List[str]
    top_k_pass: int
    difficulty: str
    fmt: str


TESTS: List[TestCase] = [

    # ── Easy — direct clause-name queries ────────────────────────────────────

    TestCase(
        name="1. Direct: revue de direction",
        query="revue de direction",
        expected_any=["9.3"],
        top_k_pass=3,
        difficulty="easy",
        fmt="keyword",
    ),
    TestCase(
        name="2. Direct: audit interne",
        query="audit interne",
        expected_any=["9.2"],
        top_k_pass=3,
        difficulty="easy",
        fmt="keyword",
    ),
    TestCase(
        name="3. Direct: non-conformité action corrective",
        query="non-conformité action corrective",
        expected_any=["10.2"],
        top_k_pass=3,
        difficulty="easy",
        fmt="keyword",
    ),
    TestCase(
        name="4. Direct: politique qualité",
        query="politique qualité objectifs",
        expected_any=["5.2", "6.2"],
        top_k_pass=3,
        difficulty="easy",
        fmt="keyword",
    ),
    TestCase(
        name="5. Direct: domaine application SMQ",
        query="domaine d'application système de management de la qualité",
        expected_any=["4.3", "4.4"],
        top_k_pass=3,
        difficulty="easy",
        fmt="short phrase",
    ),

    # ── Medium — operational business language ────────────────────────────────

    TestCase(
        name="6. Operational: réunion annuelle direction",
        query=(
            "Notre direction générale se réunit chaque année pour évaluer "
            "l'adéquation et l'efficacité de notre système de management de la qualité "
            "et décider des actions d'amélioration à mettre en place."
        ),
        expected_any=["9.3"],
        top_k_pass=5,
        difficulty="medium",
        fmt="operational sentence",
    ),
    TestCase(
        name="7. Operational: lot défectueux en production",
        query=(
            "Un lot de pièces fabriquées présente un défaut dimensionnel détecté "
            "en fin de ligne. L'équipe qualité doit décider si ces pièces peuvent "
            "être retravaillées, acceptées en dérogation ou mises au rebut."
        ),
        expected_any=["8.7", "10.2"],
        top_k_pass=8,
        difficulty="medium",
        fmt="operational scenario",
    ),
    TestCase(
        name="8. Operational: évaluation fournisseurs externes",
        query=(
            "Nous devons sélectionner et évaluer nos sous-traitants et fournisseurs "
            "extérieurs pour nous assurer que les produits et services qu'ils fournissent "
            "sont conformes à nos exigences."
        ),
        expected_any=["8.4"],
        top_k_pass=5,
        difficulty="medium",
        fmt="operational sentence",
    ),
    TestCase(
        name="9. Operational: formation compétences personnel",
        query=(
            "Notre responsable des ressources humaines identifie chaque année les besoins "
            "en formation du personnel afin de s'assurer que chaque employé possède "
            "les compétences nécessaires pour réaliser son travail."
        ),
        expected_any=["7.2"],
        top_k_pass=5,
        difficulty="medium",
        fmt="operational sentence",
    ),
    TestCase(
        name="10. Operational: collecte indicateurs performance",
        query=(
            "Notre responsable qualité collecte chaque trimestre les données sur les "
            "réclamations clients, les taux de défaut et les délais de livraison pour "
            "analyser les tendances et évaluer la performance des processus."
        ),
        expected_any=["9.1"],
        top_k_pass=5,
        difficulty="medium",
        fmt="operational paragraph",
    ),

    # ── Hard — semantic bridging required ─────────────────────────────────────

    TestCase(
        name="11. Hard: risques opportunités processus",
        query=(
            "Avant le lancement d'un nouveau projet, notre équipe analyse les facteurs "
            "susceptibles d'empêcher l'atteinte des objectifs et identifie également "
            "les situations favorables à exploiter pour améliorer nos résultats."
        ),
        expected_any=["6.1"],
        top_k_pass=5,
        difficulty="hard",
        fmt="operational paragraph",
    ),
    TestCase(
        name="12. Hard: cycle conception nouveau produit",
        query=(
            "Lors du développement d'un nouveau service logiciel, notre équipe passe "
            "par des revues de conception intermédiaires, des tests de validation avec "
            "des utilisateurs pilotes, puis une validation finale avant déploiement."
        ),
        expected_any=["8.3"],
        top_k_pass=5,
        difficulty="hard",
        fmt="long operational paragraph",
    ),
    TestCase(
        name="13. Hard: réclamation client livraison non conforme",
        query=(
            "Un client a signalé que la livraison reçue ne correspondait pas aux "
            "spécifications contractuelles. Notre équipe doit documenter l'incident, "
            "analyser la cause racine et mettre en place des mesures pour éviter "
            "toute récurrence."
        ),
        expected_any=["10.2", "8.7", "8.5", "8.2"],
        top_k_pass=5,
        difficulty="hard",
        fmt="long operational scenario",
    ),

    # ── Normative (ISO-style phrasing) ────────────────────────────────────────

    TestCase(
        name="14. Normative: programme audit documenté",
        query=(
            "L'organisme doit établir, mettre en œuvre et tenir à jour un ou plusieurs "
            "programmes d'audit, en prenant en compte l'importance des processus concernés "
            "et les résultats des audits précédents."
        ),
        expected_any=["9.2"],
        top_k_pass=5,
        difficulty="medium",
        fmt="normative ISO phrasing",
    ),
    TestCase(
        name="15. Normative: enjeux contexte organisme",
        query=(
            "L'organisme doit déterminer les enjeux externes et internes pertinents "
            "pour sa finalité et son orientation stratégique, et qui influencent sa "
            "capacité à atteindre les résultats attendus de son système de management."
        ),
        expected_any=["4.1"],
        top_k_pass=3,
        difficulty="medium",
        fmt="normative ISO phrasing",
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
    top3 = [c.clause_number for c in chunks[:3]]
    matched_at = None
    for i, chunk in enumerate(chunks[:tc.top_k_pass], start=1):
        if any(chunk.clause_number.startswith(pfx) for pfx in tc.expected_any):
            matched_at = i
            break
    return PathResult(passed=matched_at is not None, top3=top3, matched_at=matched_at, error=None)

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
    rank = f"rank {r.matched_at}" if r.matched_at else f"NO MATCH in top-{r.matched_at or '?'}"
    return f"top-3: {r.top3}  │  {rank}"

def print_detail(r: CompareResult) -> None:
    overall_icon = "✓" if (r.dense.passed or r.hybrid.passed) else "✗"
    diff_icon = DIFF_ICON.get(r.tc.difficulty, " ")
    print(f"\n  {overall_icon} {diff_icon} {r.tc.name}")
    print(f"     fmt={r.tc.fmt:<28} difficulty={r.tc.difficulty}  threshold=top-{r.tc.top_k_pass}")
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
