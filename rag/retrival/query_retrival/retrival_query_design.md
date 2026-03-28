
The agent receiving this result checks `result.success` before using the context. If you return an empty list instead, the agent will pass empty context to its LLM and generate a compliance report with no citations — a silent P1 violation that is very hard to debug.

There are two distinct situations that produce zero results:

- **Situation A:** The corpus is not loaded. No chunks exist in the collection at all. The norm filter is correct but there is nothing to find. This is a configuration problem — the ingestion pipeline was never run or failed.

- **Situation B:** The `norm_filter` contains a wrong value. You pass `norm_filter=["ISO9001"]` but the actual `norm_id` stored in the payload is `"ISO 9001"` (with a space) or `"iso9001"` (lowercase). This is a data alignment problem between ingestion and retrieval. Your ingestion pipeline uses `NORM_ID_MAP` to set `norm_id = "ISO9001"` (no space, correct case). Verify this matches exactly what is stored in at least one Qdrant payload before assuming the guard will only ever trigger for Situation A.

---

## Score preservation

The `RetrievedChunk` model has four score fields: `dense_score`, `sparse_score`, `rrf_score`, and `rerank_score`. At this stage (before reranking), you only have access to the RRF fused score from Qdrant — you do not get the individual dense and sparse scores back from the fusion query.

This is a Qdrant limitation of the native hybrid search API: Prefetch + FusionQuery returns the fused score only, not the component scores. You have two options:

**Option A (recommended for MVP):** Set `rrf_score` from the Qdrant result, and set `dense_score` and `sparse_score` to `-1.0` or `0.0` as explicit "not available" sentinels. Document this clearly in the field. The reranker and context assembler only use `rerank_score` for final ordering — the component scores are for evaluation and debugging only.

**Option B (more complex):** Run the dense and sparse searches separately first to get individual scores, then run the fused query for the actual ranking. This gives you all four scores but costs two extra Qdrant round-trips per retrieval call. Not worth it for MVP — defer to Phase 5 evaluation work if you need the ablation data.

**Use Option A.** Set `dense_score = -1.0`, `sparse_score = -1.0`, `rrf_score = result.score` at construction time. The `rerank_score` field starts at `0.0` and is populated by the Reranker in the next component.

---

## Multi-collection retrieval (Agent 3 path)

Agent 3 queries both norms and company_docs. Since company_docs is empty for now, you need to handle this gracefully rather than failing or blocking.

**The plan:** create the empty company_docs collection at startup (same collection creation logic, same schema), then query it alongside norms. Qdrant will return zero results from company_docs and the merge will just be all norms results. No special case needed — the retriever treats zero results from a collection as an empty contribution to the merge.

For multi-collection retrieval the pattern is: run retrieval against each collection independently, then merge the result lists by RRF score, then take top-k from the merged list. You are **not** running a Qdrant cross-collection query (Qdrant does not support that natively) — you are running N separate queries and merging in Python.

This matters for the `RetrievedChunk` model: each chunk knows which collection it came from via `norm_id` (for norms) or `doc_code` (for company docs). The merge just interleaves them by score. The context assembler handles formatting them differently.

**For now:** implement single-collection retrieval fully, create the empty company_docs collection, and add a stub for multi-collection that logs a warning and falls back to norms-only until company_docs is populated.

---

## The top_k parameters explained

The retrieval request carries two k values: `top_k_retrieval` and `top_k_rerank`. These serve different purposes.

- **`top_k_retrieval`** (default 10) is the number of chunks returned by the Hybrid Retriever to the Reranker. This is the final output size of this component.

- The Qdrant prefetch uses a larger internal limit — typically 2× to 3× `top_k_retrieval`. So if `top_k_retrieval = 10`, each Prefetch fetches 20 candidates. This gives RRF enough candidates from both lists to produce a good merged ranking. If you only fetched 10 from each list, you might miss a chunk that ranks #12 in dense but #2 in sparse — it would be excluded from the fusion entirely.

**The formula:** `prefetch_limit = max(20, top_k_retrieval * 2)`. Use this consistently, not a hardcoded 20.

- **`top_k_rerank`** (default 5) is the Reranker's output size — how many chunks survive after the cross-encoder precision pass. The Hybrid Retriever does not use this value at all. Pass it through to `RetrievalResult` but don't apply it here.

---

## What the Hybrid Retriever receives and returns

**Input:** `TransformedQuery` (from the Query Transformer you already built) + `top_k_retrieval: int` from `RetrievalRequest`.

**Output:** `List[RetrievedChunk]` — ranked by RRF score, length = `top_k_retrieval`, each with:
- All provenance fields populated from the Qdrant payload
- `rrf_score` set
- `dense_score` and `sparse_score` set to `-1.0`
- `rerank_score` set to `0.0`

**On empty result:** does not return a list — raises a retrieval-specific exception or returns a sentinel result object that the `RAGEngine.retrieve()` method converts to `RetrievalResult(success=False, ...)`.

---

## Development sequence — COMPLETED (2026-03-28)

All 7 steps are implemented and tested. This section is preserved for architectural context.

### ✅ Step 1 — query-side sparse encoder
`BM25SparseEncoder.encode_query()` uses uniform weight 1.0 per token. Hash function is byte-for-byte identical to ingestion: MD5, modulus 131072. Verified by `test_sparse_encoder_query.py` (12 tests).

### ✅ Step 2 — RetrievedChunk model
Four score fields: `dense_score = -1.0`, `sparse_score = -1.0`, `rrf_score` from Qdrant, `rerank_score = 0.0`. Sentinel `-1.0` distinguishes "not available" from a real `0.0` score.

### ✅ Step 3 — DenseRetriever (`retriever_dense.py`)
Dense-only cosine search via `qdrant.query_points(using="dense")`. Used as baseline in all smoke tests.

### ✅ Step 4 — HybridRetriever (`retriever.py`)
Prefetch + `FusionQuery(Fusion.RRF)`. Sparse Prefetch omitted when `bm25_tokens` is empty. Ranking differs from dense-only in 47–50/50 smoke test cases — sparse signal confirmed active.

### ✅ Step 5 — norm filter + empty corpus guard
Filter applied on Prefetch objects. `EmptyCorpusError` raised on zero results.

### ✅ Step 6 — company_docs stub
Deferred. Single-collection `norms` is fully operational. Multi-collection path (Agent 3) to be implemented when `company_docs` is needed.

### ✅ Step 7 — QueryTransformer wired end-to-end
Synchronous `transform()` — HyDE removed (2026-03-28). Applies `search_query:` nomic prefix, ISO vocabulary injection, French/English modal terms (language-aware), clause-number detection, BM25 token augmentation.

---

## Current state — retrieval quality (2026-03-28)

Corpus: ISO 9001:2015 (95 chunks) + ISO 14001:2015 (86 chunks) = **181 points** in `norms` collection.
Ingested as `language="FR"` with `search_document:` prefix and French modal BM25 tokens.

| Smoke test | Dense | Hybrid | Cases |
|---|---|---|---|
| `smoke_compare.py` | 93% (14/15) | 93% (14/15) | 15 mixed FR |
| `smoke_hard_semantic.py` | 82% (14/17) | **94% (16/17)** | 17 hard FR |
| `smoke_hard_semantic2.py` | 92% (46/50) | 92% (46/50) | 50 FR, 4 tiers |

Sparse signal active in 47–50/50 cases (ranking changes between dense and hybrid).

Known failure categories (not retrieval-layer fixable):
- Expert-tier synthesis queries (audit checklist generation, executive summary matrix)
- Edge-case: "8.7 situations d'urgence absent de l'ISO 9001" — clause does not exist in the standard

---

## The one conceptual risk to keep in mind

The MD5 hash approach means there is no shared vocabulary file between ingestion and retrieval. The correctness guarantee is purely that both sides execute the same hash function. This is elegant and solves the vocabulary-file-sync problem — but it means a typo in the hash function on either side produces wrong indices with no error.

**The gate test in Step 1 (confirm indices match between ingestion and query encoding) is the only safety net for this. Do not skip it.**