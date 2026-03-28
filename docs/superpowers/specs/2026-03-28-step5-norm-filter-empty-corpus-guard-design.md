# Step 5 — Norm Filter & Empty Corpus Guard: Tests Design

**Date:** 2026-03-28
**Branch:** Retrival-mastering
**Scope:** Unit tests for `HybridRetriever` norm filter behavior and `EmptyCorpusError` guard, plus the minimal model and retriever changes required to make those tests meaningful.

---

## Context

Step 5 of the retrieval pipeline (norm filter + empty corpus guard) is already implemented in `retriever.py`:
- `EmptyCorpusError` is defined and raised when Qdrant returns zero results
- The filter is applied on each `Prefetch` object, not the outer `query_points` call

What is missing: unit tests that verify this behavior. Two scenarios must be covered explicitly:
1. A correct `norm_filter` returns results
2. A deliberately wrong `norm_filter` value (`"WRONG_ID"`) produces `EmptyCorpusError`, not an empty list

---

## Change Surface

| File | Change |
|---|---|
| `rag/retrival/models.py` | Add `norm_filter: List[str]` field to `TransformedQuery` |
| `rag/retrival/query_transformer/Querytransformer.py` | Populate `norm_filter` in the returned `TransformedQuery` |
| `rag/retrival/query_retrival/retriever.py` | Include `query.norm_filter` in `EmptyCorpusError` message |
| `rag/retrival/query_retrival/tests/test_hybrid_retriever.py` | New file — two test classes |

---

## Model Change: `TransformedQuery`

Add `norm_filter: List[str]` to `TransformedQuery` in `models.py`.

**Rationale:** `TransformedQuery` is the diagnostic contract between the transformer and the retriever. It already carries `original_query` and `language` for diagnostic purposes. `norm_filter` fits naturally alongside these. Storing the raw list (not the compiled Qdrant `Filter` object) lets the retriever include readable values like `["WRONG_ID"]` in the error message, enabling clean assertion of `"WRONG_ID" in str(exc)`.

The alternative — serializing `query.qdrant_filter` (a Qdrant `Filter` object) — produces verbose internal representation that does not cleanly contain the original string values.

---

## Error Message Change: `EmptyCorpusError`

The current message in `retriever.py` includes `language` and `original_query` but not the filter values. Update to include `query.norm_filter` so callers can diagnose Situation B (filter mismatch) without inspecting Qdrant directly.

```
No results from '{collection}'.
norm_filter={query.norm_filter}, language='{query.language}', query='{query.original_query[:80]}'.
Possible causes: corpus not ingested, filter mismatch
(check norm_id values in Qdrant payload), or 'sparse' named
vector slot missing from collection.
```

---

## Test File: `test_hybrid_retriever.py`

**Location:** `rag/retrival/query_retrival/tests/test_hybrid_retriever.py`

**Framework:** `unittest.IsolatedAsyncioTestCase` (stdlib, no extra dependencies)

### Structure

```
_make_payload()                            # module-level helper: minimal valid NormChunk payload dict
_make_transformed_query(norm_filter)       # module-level helper: builds TransformedQuery directly

TestHybridRetrieverSuccess                 (IsolatedAsyncioTestCase)
  setUp()    — AsyncMock embedder, MagicMock qdrant with 1 ScoredPoint response
  test_correct_filter_returns_chunks

TestHybridRetrieverEmptyCorpusGuard        (IsolatedAsyncioTestCase)
  setUp()    — AsyncMock embedder, MagicMock qdrant with empty response
  test_wrong_filter_raises_empty_corpus_error
```

### Mocking strategy

| Dependency | Mock type | Value |
|---|---|---|
| `embedder.embed_text()` | `AsyncMock` | `[0.1] * 768` |
| `qdrant.query_points()` | `MagicMock` | `response.points = [ScoredPoint(...)]` or `[]` |

`TransformedQuery` is constructed directly — no call to `QueryTransformer.transform()`. The retriever is being tested, not the transformer.

### Success case assertions (`norm_filter=["ISO9001"]`)

- `result` is a non-empty list
- `result[0].norm_id == "ISO9001"`
- `result[0].rrf_score == 0.42` (the score set on the mock ScoredPoint)
- `result[0].dense_score == -1.0` (sentinel confirmed)
- `result[0].sparse_score == -1.0` (sentinel confirmed)

### Empty corpus guard assertions (`norm_filter=["WRONG_ID"]`)

- `EmptyCorpusError` is raised
- `"WRONG_ID"` appears in `str(exc)`

### What is NOT tested

- Filter placement on `Prefetch` vs outer `query_points` call — behavioral tests only; placement is a performance optimization, not a correctness property observable from the output.
- Mock call args inspection for filter structure — would couple the test to implementation details.

---

## Test helper: `_make_payload()`

Must supply all fields read by `_scored_point_to_chunk()` with no fallback (KeyError on missing fields is intentional). Minimal valid values:

```python
norm_id, norm_full, norm_version, clause_number, clause_title,
parent_clause, page_number, chunk_index, total_chunks,
text, token_count, content_type,
shall_count, should_count,
has_requirements, has_permissions, has_recommendations, has_capabilities,
keywords, related_clauses, embedding_model, language
```

---

## Running the tests

```bash
pytest rag/retrival/query_retrival/tests/test_hybrid_retriever.py -v
```

The full suite (all three unit test files) remains:

```bash
pytest rag/shared/vocabulary/tests/test_scanner.py \
       rag/retrival/query_transformer/tests/test_transform.py \
       rag/retrival/query_retrival/tests/test_sparse_encoder_query.py \
       rag/retrival/query_retrival/tests/test_hybrid_retriever.py -v
```
