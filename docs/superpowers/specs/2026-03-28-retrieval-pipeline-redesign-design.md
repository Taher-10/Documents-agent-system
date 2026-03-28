# Retrieval Pipeline Redesign — Design Spec
**Date:** 2026-03-28
**Branch:** Retrival-mastering
**Status:** Approved

---

## Background

Diagnosis of the hybrid retrieval pipeline identified six issues ranked by impact. This spec covers the four issues selected for this phase (Option C — structural redesign):

| Issue | Rank | Action |
|---|---|---|
| "NC" substring false-positive → 90% wrong vocabulary injection | CRITICAL | Fix: word-boundary matching |
| HyDE quality insufficient on llama3.2:3b | HIGH | Fix: remove HyDE, vocabulary-only expansion |
| `min_vocab_terms=3` TEST flag over-triggers HyDE | MEDIUM | Fix: removed with HyDE |
| nomic-embed-text asymmetric prefixes unused | LOW | Fix: add both sides + re-ingest |
| RRF untuned (3-call ablation arch) | MEDIUM | Deferred to Phase 5 evaluation |
| BM25 tokenization asymmetry | — | Not a problem — all 12 unit tests pass |

---

## Goal

Improve hybrid retrieval accuracy on hard semantic queries while eliminating false sparse signals, without introducing LLM latency or new pipeline dependencies.

**Success criteria:**
- `smoke_compare.py` (15 queries): hybrid ≥ 14/15
- `smoke_hard_semantic.py` (20 queries): hybrid ≥ 18/20
- `test_sparse_encoder_query.py` (12 unit tests): 12/12 pass (no regression)
- No `await transform(...)` callsite left un-updated

---

## Architecture After This Phase

```
raw_query
  → QueryTransformer.transform()          ← sync (was async)
      1. build_norm_filter()              — unchanged
      2. scan_iso_vocabulary()            — word-boundary matching (NC fix)
      3. tokenize_for_bm25()              — unchanged
      4. augment_bm25_tokens()            — unchanged
      5. prepend "search_query: "         — NEW (Stage 2)
      → TransformedQuery (hyde_used=False always)
  → HybridRetriever.retrieve()            — unchanged
      1. embed_text("search_query: {text}")
      2. BM25SparseEncoder.encode_query()
      3. Qdrant Prefetch + RRF
      → List[RetrievedChunk]
```

### Change Summary

| File | Stage | Change |
|---|---|---|
| `rag/shared/vocabulary/scanner.py` | 1 | `form in text_lower` → word-boundary regex with pattern cache |
| `rag/retrival/query_transformer/Querytransformer.py` | 1 | Remove HyDE functions; `transform()` becomes sync; prepend `"search_query: "` in Stage 2 |
| `rag/ingestion_pipeline/embedder/embedder.py` | 2 | `_build_embedding_text()` prepends `"search_document: "` |
| Qdrant `norms` collection | 2 | Drop + full re-ingest |

---

## Stage 1 — Correctness Fixes (no re-ingestion)

### Fix 1: NC word-boundary matching — `scanner.py`

**Root cause:** `form.lower() in text_lower` matches "NC" inside "influencer", "performances", "tendances", "fonctions", "lancement", injecting `non-conformité` into BM25 tokens for unrelated queries. Confirmed in 18/20 hard semantic queries.

**Fix:** Replace substring `in` check with a compiled word-boundary regex per surface form.

Pattern per form: `re.compile(r'\b' + re.escape(form.lower()) + r'\b')`

Cache compiled patterns in a module-level dict `_FORM_PATTERNS: dict[str, re.Pattern]` keyed by `form.lower()`, lazily populated on first use. This avoids recompiling on every `scan_iso_vocabulary()` call while keeping import-time cost zero.

```python
# module level
_FORM_PATTERNS: dict[str, re.Pattern] = {}

def _form_pattern(form: str) -> re.Pattern:
    key = form.lower()
    if key not in _FORM_PATTERNS:
        _FORM_PATTERNS[key] = re.compile(r'\b' + re.escape(key) + r'\b')
    return _FORM_PATTERNS[key]
```

Inner loop change:
```python
# Before
if form.lower() in text_lower:

# After
if _form_pattern(form).search(text_lower):
```

Applied uniformly to all surface forms — not just short ones. Word-boundary matching is strictly more correct for all forms.

### Fix 2: Remove HyDE — `Querytransformer.py`

**Root cause:** llama3.2:3b generates generic ISO boilerplate ("amélioration continue", "action corrective") for almost any input. With `min_vocab_terms=3` (a TEST flag), HyDE fires on 9/15 queries including queries that are already well-anchored ISO text.

**Removed entirely:**
- `should_use_hyde()`
- `_extract_hyde_context()`
- `generate_hyde_text()`
- `_HYDE_PROMPT_TEMPLATE`, `_HYDE_PROMPT_TEMPLATE_FR`
- `_HYDE_TIMEOUT`, `_HYDE_RETRIES`, `_HYDE_RETRY_SLEEP`
- `min_vocab_terms` parameter from `transform()`
- `asyncio` import (was only needed for HyDE)
- Deferred `from rag.retrival.clients.llm_client import chat_complete` import

**`transform()` signature change:**
```python
# Before
async def transform(query_text, norm_filter, language="EN", min_vocab_terms=3) -> TransformedQuery

# After
def transform(query_text, norm_filter, language="EN") -> TransformedQuery
```

`TransformedQuery.hyde_used` stays in the model hardcoded to `False`. Removing the field would silently break downstream consumers that read it.

**Updated module `__all__`** removes `should_use_hyde` and `generate_hyde_text` from the public API.

### Caller audit

Before Stage 1 ships, identify all callsites that `await transform(...)` and convert them to plain synchronous calls:

```bash
grep -r "await transform" rag/
```

Every hit must be updated. This is a breaking API change.

---

## Stage 2 — Embedding Prefix Migration (requires re-ingestion)

### Fix 3: `search_document:` prefix — `embedder.py`

`nomic-embed-text` uses asymmetric instruction prefixes to route vectors into the correct retrieval subspace. The ingestion side must prepend `"search_document: "` to every chunk's embedding text.

**Change in `_build_embedding_text()`:**
```python
# Before
return (
    f"{chunk.norm_full} clause {chunk.clause_number} "
    f"{chunk.clause_title}: {chunk.text}"
)

# After
return (
    f"search_document: {chunk.norm_full} clause {chunk.clause_number} "
    f"{chunk.clause_title}: {chunk.text}"
)
```

The structured clause identity prefix (norm_full + clause_number + clause_title) is preserved after the instruction prefix — nomic-embed-text handles this format correctly.

### Fix 4: `search_query:` prefix — `Querytransformer.py`

The query-side prefix is applied inside `transform()` before assembling `TransformedQuery`. The existing `embed_text()` docstring already anticipates this: *"the caller is responsible for formatting the string (e.g. TransformedQuery prepends the query-side prefix)"*.

```python
# At end of transform(), before constructing TransformedQuery:
embed_text = f"search_query: {embed_text}"
```

### Re-ingestion procedure

The two prefix changes must be deployed together and require a full collection rebuild:

1. Drop the `norms` collection in Qdrant (or set `QDRANT_COLLECTION` to a new name to preserve the old collection during transition).
2. Run `EMBEDDING_ENABLED=true python run.py` from `rag/ingestion_pipeline/`.
3. Verify collection point count matches expected chunk count.
4. Run smoke tests against the new collection.

**Important:** Applying only one prefix side (query without document, or document without query) creates a vector space mismatch and will degrade retrieval below the current baseline. Both sides must ship together.

---

## Testing & Validation

### Stage 1 (run against existing collection)

```bash
# Unit tests — 12/12 must pass
pytest rag/retrival/query_retrival/tests/test_sparse_encoder_query.py

# Smoke: dense vs hybrid (15 queries)
python rag/retrival/query_retrival/tests/smoketest/smoke_compare.py

# Hard semantic (20 queries)
python rag/retrival/query_retrival/tests/smoketest/smoke_hard_semantic.py
```

**Expected Stage 1 outcomes:**
- `smoke_compare`: hybrid recovers Test 11 (NC false-positive eliminated) → ≥ 14/15
- `smoke_hard_semantic`: hybrid holds 18/20 baseline (HyDE removal does not regress hard queries since Tests 7 and 20 failed on both paths anyway)
- Unit tests: 12/12 (no regression)

### Stage 2 (run against re-ingested collection)

Repeat identical commands. Expected: dense recall holds or improves due to correct embedding subspace. No new failures.

---

## Deferred Items

| Item | Reason |
|---|---|
| 3-call RRF ablation architecture (dense + sparse + fused) | Doubles Qdrant round-trips; defer to Phase 5 evaluation |
| HyDE re-introduction with better model | Requires stronger LLM (gpt-4o-mini or llama3:8b+); design separately |
| Re-ingest with `nomic-embed-text` sentence-transformers fallback | Fallback model does not support instruction prefixes — document as known limitation |

---

## Files Touched

**Stage 1:**
- `rag/shared/vocabulary/scanner.py`
- `rag/retrival/query_transformer/Querytransformer.py`
- Any file with `await transform(...)` (to be identified by grep audit)

**Stage 2:**
- `rag/ingestion_pipeline/embedder/embedder.py`
- `rag/retrival/query_transformer/Querytransformer.py` (add `search_query:` prefix)
