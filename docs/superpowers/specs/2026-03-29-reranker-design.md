# Reranker Design Spec
**Date:** 2026-03-29
**Component:** Step 5 — Reranker (retrieval layer)
**Status:** Approved

---

## Overview

The Reranker is the third component of the retrieval pipeline. It receives the top-15 candidates from `HybridRetriever` ordered by RRF fusion score, applies a cross-encoder model to score each `(query, chunk)` pair jointly, and returns the full list re-ordered by `rerank_score` descending.

The cross-encoder reads the query and chunk concatenated — attention flows both ways — producing a precise relevance judgment that embedding-based retrieval cannot. The cost is N forward passes per query (one per candidate), which is why it runs on 15 candidates, not the full corpus.

---

## Pipeline Position

```
TransformedQuery
    → HybridRetriever (top_k=15)
    → Reranker
    → ContextAssembler (next component)
```

---

## Model

**`cross-encoder/mmarco-mMiniLMv2-L12-H384`**

- 12-layer MiniLM fine-tuned on mMARCO (MS MARCO machine-translated into 26 languages including FR and EN)
- Handles French queries against English ISO norm chunks (cross-lingual relevance judgment)
- ~450MB, cold load 5–10s on CPU, inference on 15 pairs ~300ms on CPU
- Output: raw logits (not normalized). Higher = more relevant. Relative ordering is what matters.

This model is chosen over `ms-marco-MiniLM-L-6-v2` (English-only) because queries can be French (company documents in French against English ISO norms).

---

## Architecture & Component Boundary

**File:** `rag/retrival/re_ranker/reranker.py`

```
rag/retrival/re_ranker/
├── __init__.py
├── reranker.py
└── tests/
    ├── __init__.py
    └── test_reranker.py
```

The `rerank()` method signature takes `query_text: str` — not a `TransformedQuery`. This enforces at the structural level that only `original_query` can be passed in. The caller extracts `transformed_query.original_query` before calling; the reranker never sees `embed_text`.

`Reranker` has **no async methods** — `CrossEncoder.predict()` is synchronous CPU inference.

**Side-effect change:** `HybridRetriever.retrieve()` default `top_k` changes from `10` → `15`.

---

## Class Interface

```python
from sentence_transformers import CrossEncoder
from rag.retrival.models import RetrievedChunk
from typing import List

class Reranker:
    def __init__(self, model_name: str) -> None:
        self._model = CrossEncoder(model_name)  # loads eagerly at init

    def rerank(self, query_text: str, candidates: List[RetrievedChunk]) -> List[RetrievedChunk]:
        ...
```

---

## Core Logic

`rerank()` executes three steps:

1. **Guard** — if `candidates` is empty, return `[]` immediately. No model call.

2. **Score** — build `[[query_text, chunk.text] for chunk in candidates]` and call `self._model.predict(pairs)` once. Single batch call — more efficient than individual calls.

3. **Assign & sort** — iterate `zip(candidates, scores)`, set `chunk.rerank_score = float(score)` on each chunk, sort descending by `rerank_score`, return the full sorted list.

**No truncation here.** `top_k_rerank` truncation belongs to `ContextAssembler`.

---

## Score Field

`RetrievedChunk.rerank_score` already exists as a `0.0` placeholder (defined in `rag/retrival/models.py`). The reranker mutates only this field — all other fields on each chunk are unchanged.

Score semantics: raw cross-encoder logit. Not normalized to 0–1. Relative ordering is what matters.

---

## Error Handling

| Situation | Behaviour |
|-----------|-----------|
| Model not found / corrupted | `CrossEncoder.__init__` raises `OSError`/`ValueError` — propagates naturally, fails fast at startup |
| Empty candidates list | Early return `[]`, no exception, no model call |
| Single candidate | Scored and returned normally (list of length 1) |

No wrapping of `sentence-transformers` errors — the library's messages are descriptive enough.

---

## Dependency

Adds `sentence-transformers` to project dependencies. `numpy` is already available transitively.

---

## Tests

**Location:** `rag/retrival/re_ranker/tests/test_reranker.py`
**Type:** Integration tests using the real `mmarco-mMiniLMv2-L12-H384` model.

The model is loaded once via a module-scoped pytest fixture to avoid repeated 5–10s cold loads.

### Test Cases

| # | Name | What it verifies |
|---|------|-----------------|
| 1 | `test_relevant_chunk_ranked_higher` | Relevant candidate scores higher than irrelevant one. Uses real ISO-like EN/FR text pairs to validate multilingual scoring. |
| 2 | `test_scores_assigned` | After `rerank()`, every chunk has `rerank_score != 0.0`. Confirms scores were written. |
| 3 | `test_sort_order` | Returned list is sorted descending by `rerank_score` for a 3+ candidate list. |
| 4 | `test_empty_input_guard` | `rerank("any query", [])` returns `[]` without error. |
| 5 | `test_input_passthrough` | All fields on each `RetrievedChunk` other than `rerank_score` are unchanged after reranking. |

---

## Development Sequence

1. Install `sentence-transformers`, pull model, time cold load on actual hardware
2. Implement `Reranker` class with eager loading and `rerank()` core logic
3. Write integration tests (all 5 cases above)
4. Run tests, confirm multilingual scoring works (FR query → EN chunk)
5. Update `HybridRetriever.retrieve()` default `top_k`: `10` → `15`
6. Wire into retrieval service when `ContextAssembler` is ready
