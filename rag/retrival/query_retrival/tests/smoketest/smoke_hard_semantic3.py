"""
smoke_hard_semantic3.py
────────────────────────────────────────────────────────────────────────────
3 cas de test sélectionnés — comparaison Dense vs Hybride vs Hybride+Reranker
ISO 9001:2015 · langue=FR

  • 03 (easy)   – 4.3  Déclaration du domaine d'application
  • 43 (expert) – 8.5.3 Correction actionnable (propriété client)
  • 46 (expert) – 8.1 / 7.5.2 Procédure non datée, sans responsable

Run:
    python rag/retrival/query_retrival/tests/smoketest/smoke_hard_semantic3.py
"""

from __future__ import annotations

import asyncio
import copy
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
from rag.retrival.re_ranker.reranker import Reranker


# ── Config ────────────────────────────────────────────────────────────────────

QDRANT_HOST   = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT   = int(os.getenv("QDRANT_PORT", "6333"))
OLLAMA_URL    = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL  = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
LANGUAGE      = "FR"
NORM_FILTER   = ["ISO9001"]
RETRIEVE_K    = 10   # candidates fetched by Dense and Hybrid
RERANK_TOP_K  = 15   # candidates passed to Reranker (>=RETRIEVE_K)
RECALL_K      = 10


# ── TestCase ──────────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    name: str
    query: str
    expected_any: List[str]
    top_k_pass: int
    difficulty: str
    fmt: str


# ── Selected test cases ───────────────────────────────────────────────────────

from dataclasses import dataclass
from typing import List


@dataclass
class TestCase:
    name: str
    query: str
    expected_any: List[str]
    top_k_pass: int
    difficulty: str
    fmt: str


# ── REAL DOCUMENT SECTION TESTS — Gestion des gabarits ──────────────────────

TESTS: List[TestCase] = [

    TestCase(
        name="1. Objet - gestion et optimisation des gabarits",
        query=(
            "L'objet de cette procédure est la maîtrise et l'optimisation de la gestion "
            "des gabarits de tout type. Ils peuvent être fournis par le client ou conçus en interne."
        ),
        expected_any=["8.5.1", "8.5.3"],
        top_k_pass=10,
        difficulty="hard",
        fmt="full_section_real_doc",
    ),

    TestCase(
        name="2. Description de la procédure - création maintien identification",
        query=(
            "Cette procédure décrit comment créer, vérifier, et maintenir les gabarits en très bon état. "
            "Elle décrit aussi comment s'assurer que les gabarits sont correctement identifiés et mis à "
            "disposition à leur point d'utilisation."
        ),
        expected_any=["8.5.1", "8.5.2", "8.5.4", "7.1.5"],
        top_k_pass=10,
        difficulty="hard",
        fmt="full_section_real_doc",
    ),

    TestCase(
        name="3. Domaine d'application - unités et services concernés",
        query=(
            "Cette procédure s'applique aux unités et services de production, "
            "Indus / méthodes et contrôles."
        ),
        expected_any=["4.3", "8.5.1"],
        top_k_pass=10,
        difficulty="hard",
        fmt="full_section_real_doc",
    ),

    TestCase(
        name="4. Définitions - procédure et gabarit",
        query=(
            "Procédure : Manière spécifiée d'effectuer une activité ou un processus. "
            "Gabarit : un moyen de contrôle ou de fabrication permettant d'éliminer les "
            "risques de nonconformité des produits et des opérations."
        ),
        expected_any=["8.5.1", "7.1.5"],
        top_k_pass=10,
        difficulty="hard",
        fmt="full_section_real_doc",
    ),

    TestCase(
        name="5. Références - registres et processus liés",
        query=(
            "Registre des Gabarits sur QALITAS, registre des gabarits de JEHIER, "
            "processus Méthodes et industrialisation, processus Planification et suivi Production."
        ),
        expected_any=["7.5", "8.5.1"],
        top_k_pass=10,
        difficulty="hard",
        fmt="full_section_real_doc",
    ),

    TestCase(
        name="6. Description générale - QALITAS Excel et identification",
        query=(
            "La gestion des gabarits se fait sur QALITAS pour les gabarits hors JEHIER. "
            "Pour les gabarits de JEHIER, la gestion se fait sur un fichier Excel géré par "
            "le Responsable Atelier JEHIER. Les gabarits des clients sont identifiés par des "
            "codes fournis par les clients. Les gabarits internes, conçus et fabriqués par "
            "l'entreprise, sont identifiés par le service méthodes et communiqués au service qualité."
        ),
        expected_any=["7.5", "8.5.2", "8.5.3"],
        top_k_pass=10,
        difficulty="hard",
        fmt="full_section_real_doc",
    ),

    TestCase(
        name="7. Gestion des gabarits externes clients - section complète",
        query=(
            "A la réception d'un nouveau gabarit d'un client [Hors JEHIER], le Responsable "
            "Méthodes / Industrialisation désigné communique l'information au Responsable qualité. "
            "Ce dernier l'enregistre sur QALITAS. Il doit obligatoirement renseigner au minimum "
            "les champs : [Propriétaire, la date de réception, l'état à la réception, la catégorie, "
            "Le responsable des interventions, l'emplacement de référence]. Le Responsable Méthodes / "
            "Industrialisation désigné doit valider le gabarit en le vérifiant par rapport aux exigences "
            "client [spécifications techniques des produits, plans] et par rapport à son état à la réception "
            "[Exploitable / Utilisable, référencé, Complet]. Le gabarit est mis à la disposition dans "
            "l'emplacement de référence. Le Responsable Qualité désigné doit planifier les interventions "
            "de vérification du gabarit sur QALITAS, en spécifiant le responsable, les dates prévues et "
            "la fréquence semestrielle des vérifications. Une étiquette d'identification doit accompagner "
            "le gabarit tout au long de son utilisation dans les postes de travail. Selon la fréquence de "
            "vérification, le Responsable Qualité doit vérifier le gabarit et mettre à jour son état sur "
            "QALITAS. En cas de perte, endommagement, besoin de modification ou changement du gabarit, "
            "le responsable désigné doit envoyer un mail au client pour la réception d'un nouveau gabarit. "
            "On ne pourra utiliser le gabarit sans dérogation explicite de la part du client. A la réception "
            "d'un gabarit de remplacement, l'ancien est désactivé sur QALITAS. L'ancien gabarit est identifié "
            "par une étiquette portant la mention PERIME et il sera aussitôt isolé. Il ne pourra être détruit "
            "sans l'accord et l'information du client. Chaque trois ans, un inventaire des gabarits non conformes "
            "des clients est assuré et le client est contacté pour destruction ou renvoi."
        ),
        expected_any=["7.5", "7.1.5", "8.5.1", "8.5.2", "8.5.3", "8.5.4"],
        top_k_pass=10,
        difficulty="hard",
        fmt="full_section_real_doc",
    ),

    TestCase(
        name="8. Gestion des gabarits internes - section complète",
        query=(
            "Le Responsable Méthodes / Industrialisation désigné fait la conception du gabarit "
            "pour la réalisation du produit conformément aux exigences du client ainsi que pour "
            "le contrôle final. Il identifie le gabarit par un code interne communiqué au responsable "
            "qualité. L'enregistrement sur QALITAS se fait par le Responsable Qualité avec les champs "
            "obligatoires : propriétaire, date de fabrication, état à la fabrication, catégorie, "
            "responsable des interventions et emplacement de référence. Le Responsable Méthodes / "
            "Industrialisation valide le gabarit par rapport aux exigences client ou internes et à son "
            "état à la fabrication. Le gabarit est mis à disposition dans l'emplacement de référence. "
            "Une fois validé, le Responsable Qualité planifie les interventions de vérification du "
            "gabarit sur QALITAS avec responsable, dates prévues et fréquence semestrielle. En parallèle, "
            "il effectue chaque mois une vérification tournante pour s'assurer que les gabarits, qu'ils "
            "soient utilisés ou non, sont bien présents et rangés à leur place. Une étiquette d'identification "
            "accompagne le gabarit tout au long de son utilisation. Selon la fréquence de vérification, "
            "le Responsable Qualité désigné doit vérifier le gabarit et mettre à jour son état sur QALITAS. "
            "En cas de perte, endommagement, besoin de modification ou changement du gabarit, un autre gabarit "
            "doit être élaboré et la nouvelle conception redéclenche les étapes décrites. On ne pourra utiliser "
            "le gabarit sans dérogation explicite du Responsable Méthodes / Industrialisation et / ou du "
            "Directeur Production. A la fabrication d'un gabarit de remplacement, l'ancien est désactivé sur "
            "QALITAS. L'ancien gabarit non conforme est identifié par une étiquette portant la mention PERIME "
            "et il sera aussitôt isolé. Il ne pourra être détruit sans l'accord du Directeur de Production."
        ),
        expected_any=["7.5", "7.1.5", "8.5.1", "8.5.2", "8.5.4"],
        top_k_pass=10,
        difficulty="hard",
        fmt="full_section_real_doc",
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


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class PathResult:
    passed: bool
    top3: List[str]
    matched_at: Optional[int]
    error: Optional[str]


@dataclass
class CompareResult:
    tc: TestCase
    tq: Optional[TransformedQuery]
    transform_error: Optional[str]
    dense: PathResult
    hybrid: PathResult
    reranked: PathResult


# ── Helpers ───────────────────────────────────────────────────────────────────

DIFF_ICON = {"easy": "○", "medium": "◑", "hard": "●", "expert": "★"}

def _sep(char: str = "─", width: int = 84) -> None:
    print(char * width)

def _truncate(s: str, n: int = 70) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"

def _eval_path(chunks: List[RetrievedChunk], tc: TestCase) -> PathResult:
    top3 = [c.clause_number for c in chunks[:3]]
    matched_at = None
    for i, chunk in enumerate(chunks[:RECALL_K], start=1):
        if any(chunk.clause_number.startswith(pfx) for pfx in tc.expected_any):
            matched_at = i
            break
    return PathResult(passed=matched_at is not None, top3=top3,
                      matched_at=matched_at, error=None)

def _error_path(msg: str) -> PathResult:
    return PathResult(passed=False, top3=[], matched_at=None, error=msg)


# ── Runner ────────────────────────────────────────────────────────────────────

async def run_tests(
    dense_retriever: DenseRetriever,
    hybrid_retriever: HybridRetriever,
    reranker: Reranker,
) -> List[CompareResult]:
    results: List[CompareResult] = []
    for tc in TESTS:
        tq: Optional[TransformedQuery] = None
        transform_error: Optional[str] = None
        try:
            tq = transform(tc.query, norm_filter=NORM_FILTER, language=LANGUAGE)
        except Exception as exc:
            transform_error = f"{type(exc).__name__}: {exc}"
            err = _error_path("transform failed")
            results.append(CompareResult(tc=tc, tq=None,
                transform_error=transform_error,
                dense=err, hybrid=err, reranked=err))
            continue

        # Dense
        try:
            dense_chunks = await dense_retriever.retrieve(tq, top_k=RETRIEVE_K)
            dense_result = _eval_path(dense_chunks, tc)
        except DenseEmptyCorpusError as exc:
            dense_result = _error_path(f"EmptyCorpusError: {exc}")
        except Exception as exc:
            dense_result = _error_path(f"{type(exc).__name__}: {exc}")

        # Hybrid
        try:
            hybrid_chunks = await hybrid_retriever.retrieve(tq, top_k=RERANK_TOP_K)
            hybrid_result = _eval_path(hybrid_chunks, tc)
        except HybridEmptyCorpusError as exc:
            hybrid_chunks = []
            hybrid_result = _error_path(f"EmptyCorpusError: {exc}")
        except Exception as exc:
            hybrid_chunks = []
            hybrid_result = _error_path(f"{type(exc).__name__}: {exc}")

        # Hybrid + Reranker
        # Deep-copy so reranker's in-place score mutation does not affect
        # the hybrid_chunks used for hybrid_result evaluation above.
        try:
            candidates = copy.deepcopy(hybrid_chunks)
            reranked_chunks = reranker.rerank(tc.query, candidates)
            reranked_result = _eval_path(reranked_chunks, tc)
        except Exception as exc:
            reranked_result = _error_path(f"{type(exc).__name__}: {exc}")

        results.append(CompareResult(tc=tc, tq=tq, transform_error=None,
                                     dense=dense_result,
                                     hybrid=hybrid_result,
                                     reranked=reranked_result))
    return results


# ── Print per-result detail ───────────────────────────────────────────────────

def _pass_icon(r: PathResult) -> str:
    return "✓" if r.passed else "✗"

def _rank_str(r: PathResult) -> str:
    if r.error:
        return f"ERROR: {r.error}"
    rank = f"rank {r.matched_at}" if r.matched_at else f"PAS DE CORRESPONDANCE dans top-{RECALL_K}"
    return f"top-3: {r.top3}  │  {rank}"

def print_detail(r: CompareResult) -> None:
    overall_icon = "✓" if (r.dense.passed or r.hybrid.passed or r.reranked.passed) else "✗"
    diff_icon = DIFF_ICON.get(r.tc.difficulty, " ")
    print(f"\n  {overall_icon} {diff_icon} {r.tc.name}")
    print(f"     fmt={r.tc.fmt:<28} difficulté={r.tc.difficulty}  seuil=top-{RECALL_K} (mode recall)")
    print(f"     attendu ∈ {r.tc.expected_any}")
    query_preview = _truncate(r.tc.query.replace("\n", " "))
    print(f"     requête : \"{query_preview}\"")

    if r.transform_error:
        print(f"     ERREUR DE TRANSFORMATION : {r.transform_error}")
        return

    assert r.tq is not None
    hyde_str = "OUI" if r.tq.hyde_used else "non"
    vocab_preview = r.tq.iso_vocab_hits[:5] if r.tq.iso_vocab_hits else []
    print(f"     HyDE={hyde_str}  iso_vocab_hits={vocab_preview}")
    print(f"     bm25_tokens ({len(r.tq.bm25_tokens)}) : {sorted(r.tq.bm25_tokens)}")

    print(f"     Dense seul  {_pass_icon(r.dense)}    │  {_rank_str(r.dense)}")
    print(f"     Hybride     {_pass_icon(r.hybrid)}    │  {_rank_str(r.hybrid)}")
    print(f"     Hybrid+Rrk  {_pass_icon(r.reranked)}    │  {_rank_str(r.reranked)}")

    # Show reranker impact vs hybrid
    if not r.hybrid.error and not r.reranked.error:
        if r.hybrid.top3 == r.reranked.top3:
            print(f"     Reranker impact : AUCUN  (top-3 identique à Hybride)")
        else:
            changed = [i + 1 for i, (h, rr) in enumerate(zip(r.hybrid.top3, r.reranked.top3)) if h != rr]
            print(f"     Reranker impact : OUI   (positions {changed} modifiées)")
            print(f"       Hybride   top-3 : {r.hybrid.top3}")
            print(f"       Hybrid+Rk top-3 : {r.reranked.top3}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    print()
    _sep("═", 84)
    print(" Comparaison Pipeline Complet — Dense vs Hybride vs Hybride+Reranker")
    print(f" Corpus   : ISO 9001 · langue={LANGUAGE} · Qdrant {QDRANT_HOST}:{QDRANT_PORT}")
    print(f" Embedder : {OLLAMA_MODEL} via {OLLAMA_URL}")
    print(f" Reranker : {Reranker.DEFAULT_MODEL}")
    n_easy   = sum(1 for t in TESTS if t.difficulty == "easy")
    n_expert = sum(1 for t in TESTS if t.difficulty == "expert")
    print(f" Tests    : {len(TESTS)}  (facile={n_easy}  expert={n_expert})")
    print(f" Légende  : ○ facile  ★ expert")
    _sep("═", 84)

    print("\nChargement du Reranker (cross-encoder) …")
    reranker = Reranker()
    print("  Reranker prêt.")

    embedder         = _OllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)
    qdrant           = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    dense_retriever  = DenseRetriever(embedder=embedder, qdrant=qdrant)
    hybrid_retriever = HybridRetriever(embedder=embedder, qdrant=qdrant)

    print("\nLancement des tests (transform + dense + hybride + reranker par cas) …")
    results = await run_tests(dense_retriever, hybrid_retriever, reranker)

    _sep()
    for r in results:
        print_detail(r)

    dense_passed    = [r for r in results if r.dense.passed]
    hybrid_passed   = [r for r in results if r.hybrid.passed]
    reranked_passed = [r for r in results if r.reranked.passed]

    print()
    _sep("═", 84)
    print(f"\n RÉSULTATS")
    print(f"   Dense seul   : {len(dense_passed)}/{len(results)} passés")
    print(f"   Hybride      : {len(hybrid_passed)}/{len(results)} passés")
    print(f"   Hybrid+Rrk   : {len(reranked_passed)}/{len(results)} passés")
    print()

    by_diff: dict = {"easy": [], "medium": [], "hard": [], "expert": []}
    for r in results:
        by_diff[r.tc.difficulty].append((r.dense.passed, r.hybrid.passed, r.reranked.passed))

    labels_fr = {"easy": "facile", "medium": "moyen", "hard": "difficile", "expert": "expert"}
    print(" Score par niveau de difficulté :")
    print(f"   {'':10}  {'Dense':>6}  {'Hybride':>7}  {'Hybrid+Rk':>9}  barre (Dense░ / Hybrid█ / Rerank▓)")
    for d, triples in by_diff.items():
        n = len(triples)
        if n == 0:
            continue
        nd  = sum(t[0] for t in triples)
        nh  = sum(t[1] for t in triples)
        nrr = sum(t[2] for t in triples)
        bar_d  = "░" * nd  + " " * (n - nd)
        bar_h  = "█" * nh  + " " * (n - nh)
        bar_rr = "▓" * nrr + " " * (n - nrr)
        icon = DIFF_ICON[d]
        print(f"   {icon} {labels_fr[d]:<10}  {nd}/{n}      {nh}/{n}        {nrr}/{n}       [{bar_d}] [{bar_h}] [{bar_rr}]")

    print()
    failed_any = [r for r in results if not r.dense.passed and not r.hybrid.passed and not r.reranked.passed]
    if failed_any:
        print(" Cas échoués (aucune path ne passe) :")
        for r in failed_any:
            diff_icon = DIFF_ICON.get(r.tc.difficulty, " ")
            print(f"   ✗ {diff_icon} {r.tc.name}")
        print()

    all_passed = len(reranked_passed) == len(results)
    dense_pct    = len(dense_passed)    / len(results) * 100
    hybrid_pct   = len(hybrid_passed)   / len(results) * 100
    reranked_pct = len(reranked_passed) / len(results) * 100

    for label, pct in [("Dense seul  ", dense_pct), ("Hybride     ", hybrid_pct), ("Hybrid+Rrk  ", reranked_pct)]:
        if pct == 100:
            print(f" 🟢 {label}: Tous les tests passés ({pct:.0f}%)")
        elif pct >= 67:
            print(f" 🟡 {label}: La plupart des tests passés ({pct:.0f}%)")
        else:
            print(f" 🔴 {label}: Trop d'échecs ({pct:.0f}%) — investiguer le pipeline")

    print()
    _sep("═", 84)
    print()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
