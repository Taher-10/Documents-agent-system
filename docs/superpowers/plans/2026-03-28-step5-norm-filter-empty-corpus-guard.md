# Step 5 — Norm Filter & Empty Corpus Guard: Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write unit tests verifying that `HybridRetriever` returns chunks on a correct `norm_filter` and raises `EmptyCorpusError` (with the filter value in the message) on a wrong one — and make the minimal model/retriever changes to support those tests.

**Architecture:** TDD — write the failing test file first, then add `norm_filter: List[str]` to `TransformedQuery`, then update the `EmptyCorpusError` message to include the filter value. All four files change; the test file drives the other three.

**Tech Stack:** Python 3.12 | `unittest.IsolatedAsyncioTestCase` | `unittest.mock.AsyncMock` / `MagicMock` | `qdrant_client` | `pytest`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `rag/retrival/query_retrival/tests/test_hybrid_retriever.py` | **Create** | Two test classes: success path + empty corpus guard |
| `rag/retrival/models.py` | **Modify** | Add `norm_filter: List[str]` to `TransformedQuery` |
| `rag/retrival/query_transformer/Querytransformer.py` | **Modify** | Populate `norm_filter` in returned `TransformedQuery` |
| `rag/retrival/query_retrival/retriever.py` | **Modify** | Include `query.norm_filter` in `EmptyCorpusError` message |

---

## Task 1: Write the failing test file

**Files:**
- Create: `rag/retrival/query_retrival/tests/test_hybrid_retriever.py`

- [ ] **Step 1: Create the test file**

```python
"""
query_retrival/tests/test_hybrid_retriever.py
──────────────────────────────────────────────
Unit tests for HybridRetriever — Step 5: norm filter and empty corpus guard.

Two behavioral scenarios:
  1. Correct norm_filter → results returned with expected fields
  2. Wrong norm_filter value ("WRONG_ID") → EmptyCorpusError raised,
     message contains the filter value

Framework: unittest.IsolatedAsyncioTestCase (stdlib — no extra dependencies)
Mocking:   AsyncMock for embedder.embed_text, MagicMock for qdrant.query_points

Run:
    pytest rag/retrival/query_retrival/tests/test_hybrid_retriever.py -v
"""
import unittest
from unittest.mock import AsyncMock, MagicMock

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from rag.retrival.models import TransformedQuery
from rag.retrival.query_retrival.retriever import EmptyCorpusError, HybridRetriever


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_payload(norm_id: str = "ISO9001") -> dict:
    """
    Minimal valid NormChunk payload dict.

    All fields are required by _scored_point_to_chunk — a missing key raises
    KeyError immediately (intentional: missing fields indicate an ingestion bug).
    """
    return {
        "norm_id": norm_id,
        "norm_full": "ISO 9001:2015",
        "norm_version": "2015",
        "clause_number": "8.1",
        "clause_title": "Planification et maîtrise opérationnelles",
        "parent_clause": "8",
        "page_number": 23,
        "chunk_index": 1,
        "total_chunks": 1,
        "text": "L'organisme doit planifier, mettre en oeuvre, maîtriser...",
        "token_count": 42,
        "content_type": "normative",
        "shall_count": 3,
        "should_count": 0,
        "has_requirements": True,
        "has_permissions": False,
        "has_recommendations": False,
        "has_capabilities": False,
        "keywords": ["planification", "maîtrise", "opérationnelle"],
        "related_clauses": ["6.1", "9.1"],
        "embedding_model": "nomic-embed-text",
        "language": "FR",
    }


def _make_transformed_query(norm_filter: list) -> TransformedQuery:
    """
    Build a minimal TransformedQuery directly — no QueryTransformer.transform() call.

    The retriever is being tested, not the transformer.  A real qdrant_filter
    is constructed so the object is valid, but the mock Qdrant ignores it.
    """
    return TransformedQuery(
        embed_text="search_query: audit interne",
        bm25_tokens=["audit", "interne"],
        qdrant_filter=Filter(
            must=[FieldCondition(key="norm_id", match=MatchValue(value=norm_filter[0]))]
        ),
        hyde_used=False,
        iso_vocab_hits=["audit"],
        original_query="audit interne",
        language="FR",
        norm_filter=norm_filter,
    )


# ── Test classes ──────────────────────────────────────────────────────────────

class TestHybridRetrieverSuccess(unittest.IsolatedAsyncioTestCase):
    """Correct norm_filter returns a populated RetrievedChunk list."""

    def setUp(self):
        self.mock_embedder = MagicMock()
        self.mock_embedder.embed_text = AsyncMock(return_value=[0.1] * 768)

        mock_point = MagicMock()
        mock_point.id = "test-uuid-123"
        mock_point.score = 0.42
        mock_point.payload = _make_payload(norm_id="ISO9001")

        mock_response = MagicMock()
        mock_response.points = [mock_point]

        self.mock_qdrant = MagicMock(spec=QdrantClient)
        self.mock_qdrant.query_points.return_value = mock_response

        self.retriever = HybridRetriever(
            embedder=self.mock_embedder,
            qdrant=self.mock_qdrant,
        )

    async def test_correct_filter_returns_chunks(self):
        query = _make_transformed_query(norm_filter=["ISO9001"])
        result = await self.retriever.retrieve(query, top_k=10)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].norm_id, "ISO9001")
        self.assertAlmostEqual(result[0].rrf_score, 0.42)
        self.assertAlmostEqual(result[0].dense_score, -1.0)
        self.assertAlmostEqual(result[0].sparse_score, -1.0)


class TestHybridRetrieverEmptyCorpusGuard(unittest.IsolatedAsyncioTestCase):
    """Wrong norm_filter value raises EmptyCorpusError with filter value in message."""

    def setUp(self):
        self.mock_embedder = MagicMock()
        self.mock_embedder.embed_text = AsyncMock(return_value=[0.1] * 768)

        mock_response = MagicMock()
        mock_response.points = []

        self.mock_qdrant = MagicMock(spec=QdrantClient)
        self.mock_qdrant.query_points.return_value = mock_response

        self.retriever = HybridRetriever(
            embedder=self.mock_embedder,
            qdrant=self.mock_qdrant,
        )

    async def test_wrong_filter_raises_empty_corpus_error(self):
        query = _make_transformed_query(norm_filter=["WRONG_ID"])

        with self.assertRaises(EmptyCorpusError) as ctx:
            await self.retriever.retrieve(query, top_k=10)

        self.assertIn("WRONG_ID", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run to verify the test file fails**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/retrival/query_retrival/tests/test_hybrid_retriever.py -v
```

Expected: `TypeError: TransformedQuery.__init__() got an unexpected keyword argument 'norm_filter'`

---

## Task 2: Add `norm_filter` to `TransformedQuery` and populate it in `Querytransformer.py`

These two changes are coupled — adding a required field without populating it immediately breaks the existing transformer tests. Do both in this task.

**Files:**
- Modify: `rag/retrival/models.py`
- Modify: `rag/retrival/query_transformer/Querytransformer.py`

- [ ] **Step 1: Add `norm_filter: List[str]` to `TransformedQuery` in `models.py`**

Current `TransformedQuery` ends at line 21 (`language: str`). Add the new field after `language`:

```python
@dataclass
class TransformedQuery:
    """The output of the Query Transformer, carrying everything the retriever needs."""

    embed_text: str

    bm25_tokens: List[str]

    qdrant_filter: Filter

    hyde_used: bool

    iso_vocab_hits: List[str]

    original_query: str

    language: str  # "EN" or "FR" — determines vocabulary and HyDE prompt language

    norm_filter: List[str]  # raw norm IDs passed to transform(), preserved for diagnostics
```

- [ ] **Step 2: Populate `norm_filter` in `Querytransformer.py`**

In `transform()`, the `return TransformedQuery(...)` block currently ends at `language=language,` (line 159). Add `norm_filter=norm_filter` to it:

```python
    return TransformedQuery(
        embed_text=embed_text,
        bm25_tokens=bm25_tokens,
        qdrant_filter=qdrant_filter,
        hyde_used=False,
        iso_vocab_hits=iso_vocab_hits,
        original_query=query_text,
        language=language,
        norm_filter=norm_filter,
    )
```

- [ ] **Step 3: Run the retriever tests — success test passes, guard test fails**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/retrival/query_retrival/tests/test_hybrid_retriever.py -v
```

Expected:
```
PASSED  TestHybridRetrieverSuccess::test_correct_filter_returns_chunks
FAILED  TestHybridRetrieverEmptyCorpusGuard::test_wrong_filter_raises_empty_corpus_error
AssertionError: 'WRONG_ID' not found in '...'
```

- [ ] **Step 4: Run the existing transformer tests to confirm they still pass**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/retrival/query_transformer/tests/test_transform.py -v
```

Expected: all tests PASS (no regressions)

---

## Task 3: Update `EmptyCorpusError` message to include the filter value

**Files:**
- Modify: `rag/retrival/query_retrival/retriever.py`

- [ ] **Step 1: Update the `EmptyCorpusError` raise in `retriever.py`**

Replace the `raise EmptyCorpusError(...)` block at lines 252–258 with:

```python
        # Step 5 — empty guard
        if not results:
            raise EmptyCorpusError(
                f"No results from '{collection}'. "
                f"norm_filter={query.norm_filter}, language='{query.language}', "
                f"query='{query.original_query[:80]}'. "
                f"Possible causes: corpus not ingested, filter mismatch "
                f"(check norm_id values in Qdrant payload), or 'sparse' named "
                f"vector slot missing from collection."
            )
```

- [ ] **Step 2: Run both retriever tests — both must pass**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/retrival/query_retrival/tests/test_hybrid_retriever.py -v
```

Expected:
```
PASSED  TestHybridRetrieverSuccess::test_correct_filter_returns_chunks
PASSED  TestHybridRetrieverEmptyCorpusGuard::test_wrong_filter_raises_empty_corpus_error
```

---

## Task 4: Run the full unit test suite and commit

**Files:** none (verification + commit only)

- [ ] **Step 1: Run all four unit test files together**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/shared/vocabulary/tests/test_scanner.py \
       rag/retrival/query_transformer/tests/test_transform.py \
       rag/retrival/query_retrival/tests/test_sparse_encoder_query.py \
       rag/retrival/query_retrival/tests/test_hybrid_retriever.py -v
```

Expected: all tests PASS, zero failures, zero errors.

- [ ] **Step 2: Commit**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
git add rag/retrival/models.py \
        rag/retrival/query_transformer/Querytransformer.py \
        rag/retrival/query_retrival/retriever.py \
        rag/retrival/query_retrival/tests/test_hybrid_retriever.py
git commit -m "feat: Step 5 — norm filter tests + norm_filter on TransformedQuery + EmptyCorpusError message"
```
