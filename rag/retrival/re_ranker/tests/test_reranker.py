"""
re_ranker/tests/test_reranker.py
─────────────────────────────────
Integration tests for Reranker — Step 5.

Uses the real cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 model.
The model is loaded once via a module-scoped fixture (cold load ~5–10s on warm cache).

Run:
    pytest rag/retrival/re_ranker/tests/test_reranker.py -v
"""
import pytest

from rag.retrival.models import RetrievedChunk
from rag.retrival.re_ranker.reranker import Reranker


# ── Module-scoped fixture (load model once for all tests) ─────────────────────

@pytest.fixture(scope="module")
def reranker() -> Reranker:
    return Reranker()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_chunk(chunk_id: str, text: str) -> RetrievedChunk:
    """Minimal valid RetrievedChunk with the given id and text."""
    return RetrievedChunk(
        chunk_id=chunk_id,
        norm_id="ISO9001",
        norm_full="ISO 9001:2015",
        norm_version="2015",
        clause_number="7.2",
        clause_title="Competence",
        parent_clause="7",
        page_number=12,
        chunk_index=1,
        total_chunks=1,
        text=text,
        token_count=len(text.split()),
        content_type="normative",
        shall_count=2,
        should_count=1,
        has_requirements=True,
        has_permissions=False,
        has_recommendations=False,
        has_capabilities=False,
        keywords=["competence", "training"],
        related_clauses=["7.1", "7.3"],
        embedding_model="nomic-embed-text",
        language="EN",
    )


# ── Test 1: EN relevance ordering ─────────────────────────────────────────────

def test_relevant_chunk_ranked_higher_en(reranker: Reranker) -> None:
    """Relevant chunk must rank above an irrelevant chunk for an English query."""
    query = "The company trains all new employees on quality procedures"
    relevant = _make_chunk(
        "c_relevant",
        "The organization shall determine the necessary competence of persons doing work "
        "under its control that affects the quality management system performance. "
        "The organization shall take actions to acquire the necessary competence, "
        "and evaluate the effectiveness of those actions, including training and "
        "on-the-job learning.",
    )
    irrelevant = _make_chunk(
        "c_irrelevant",
        "The organization shall retain documented information as evidence of the results "
        "of the calibration or verification of monitoring and measurement equipment. "
        "Measurement traceability shall be maintained.",
    )
    result = reranker.rerank(query, [irrelevant, relevant])
    assert result[0].chunk_id == "c_relevant", (
        f"Expected relevant chunk to rank first. "
        f"Scores — c_relevant: {relevant.rerank_score:.4f}, "
        f"c_irrelevant: {irrelevant.rerank_score:.4f}"
    )


# ── Test 2: FR query → EN chunk (multilingual) ────────────────────────────────

def test_relevant_chunk_ranked_higher_fr_query(reranker: Reranker) -> None:
    """Relevant chunk must rank above an irrelevant chunk for a French query (cross-lingual)."""
    query_fr = "L'entreprise forme tous les nouveaux employés sur les procédures qualité"
    relevant = _make_chunk(
        "c_relevant",
        "The organization shall determine the necessary competence of persons doing work "
        "under its control that affects the quality management system performance. "
        "The organization shall take actions to acquire the necessary competence, "
        "and evaluate the effectiveness of those actions, including training and "
        "on-the-job learning.",
    )
    irrelevant = _make_chunk(
        "c_irrelevant",
        "The organization shall retain documented information as evidence of the results "
        "of the calibration or verification of monitoring and measurement equipment. "
        "Measurement traceability shall be maintained.",
    )
    result = reranker.rerank(query_fr, [irrelevant, relevant])
    assert result[0].chunk_id == "c_relevant", (
        f"Expected relevant chunk to rank first for FR query. "
        f"Scores — c_relevant: {relevant.rerank_score:.4f}, "
        f"c_irrelevant: {irrelevant.rerank_score:.4f}"
    )


# ── Test 3: scores assigned (no 0.0 placeholders remain) ─────────────────────

def test_scores_assigned(reranker: Reranker) -> None:
    """Every chunk in the result must have rerank_score != 0.0 after reranking."""
    chunks = [
        _make_chunk("c1", "The organization shall maintain a documented quality management system."),
        _make_chunk("c2", "Top management shall demonstrate leadership and commitment to the QMS."),
        _make_chunk("c3", "The organization shall determine external and internal issues relevant to its purpose."),
    ]
    result = reranker.rerank("quality management responsibilities", chunks)
    for chunk in result:
        assert chunk.rerank_score != 0.0, (
            f"chunk {chunk.chunk_id} still has placeholder score 0.0 after reranking"
        )


# ── Test 4: sort order is descending ─────────────────────────────────────────

def test_sort_order_descending(reranker: Reranker) -> None:
    """Returned list must be sorted by rerank_score descending."""
    chunks = [
        _make_chunk("c1", "The organization shall maintain a documented quality management system."),
        _make_chunk("c2", "Top management shall demonstrate leadership and commitment to the QMS."),
        _make_chunk("c3", "The organization shall determine external and internal issues relevant to its purpose."),
        _make_chunk("c4", "Documented information shall be controlled to ensure it is available and suitable for use."),
    ]
    result = reranker.rerank("management leadership quality system", chunks)
    for i in range(len(result) - 1):
        assert result[i].rerank_score >= result[i + 1].rerank_score, (
            f"Sort order violated at position {i}: "
            f"score {result[i].rerank_score:.4f} < {result[i+1].rerank_score:.4f}"
        )


# ── Test 5: empty input guard ─────────────────────────────────────────────────

def test_empty_input_guard(reranker: Reranker) -> None:
    """rerank() with an empty candidate list must return [] without error."""
    result = reranker.rerank("any query about ISO standards", [])
    assert result == []


# ── Test 6: non-rerank_score fields are unchanged ────────────────────────────

def test_input_passthrough(reranker: Reranker) -> None:
    """All RetrievedChunk fields other than rerank_score must be unchanged after reranking."""
    original_text = "The organization shall determine competence requirements for all personnel."
    chunk = _make_chunk("c1", original_text)
    original_rrf = chunk.rrf_score         # 0.0 default
    original_dense = chunk.dense_score     # -1.0 default
    original_sparse = chunk.sparse_score   # -1.0 default

    result = reranker.rerank("training and competence", [chunk])

    assert result[0].chunk_id == "c1"
    assert result[0].text == original_text
    assert result[0].norm_id == "ISO9001"
    assert result[0].clause_number == "7.2"
    assert result[0].rrf_score == original_rrf
    assert result[0].dense_score == original_dense
    assert result[0].sparse_score == original_sparse
    assert result[0].rerank_score != 0.0   # was populated by reranker
