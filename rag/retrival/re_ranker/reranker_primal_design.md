#this is primal design for reranker with lot of inconsistencies and suggestions this is treated as start point/reference not the truth 
#in case of inconsistensy between design assumption of this step and accual program implemented decision the implemented design is the truth

# What the Reranker does, precisely

The Hybrid Retriever gave you ~15 candidates ordered by RRF fusion score. That ordering is good but imperfect — RRF is a rank-combination heuristic, not a deep semantic judgment. The Reranker makes the precise judgment.

It does this by reading each (query, chunk) pair jointly in a single forward pass. This is the fundamental difference from embedding-based retrieval. The embedding model encodes the query and each chunk independently into vectors, then measures geometric distance. The cross-encoder reads the query and chunk concatenated together — it can see how specific words in the query relate to specific words in the chunk, attention flows both ways, and the output is a single relevance score for that pair.

The cost is that you cannot pre-compute anything. Every query requires N forward passes (one per candidate). This is why you run it on 15 candidates, not 750. The Hybrid Retriever does the coarse filtering; the Reranker does the precision pass on the survivors.

## The model: what it is and why this one

`cross-encoder/ms-marco-MiniLM-L-6-v2` is a 6-layer MiniLM model fine-tuned on the MS MARCO passage ranking dataset. MS MARCO is a large-scale reading comprehension and passage retrieval benchmark built from real Bing search queries and web passages. Fine-tuning on it produces a model that understands "which passage best answers this question" — which is exactly the judgment you need.

Key properties for your use case:

- **Size:** ~85MB. Loads in 2–5 seconds on CPU. Inference on 15 pairs takes ~100ms. Both are acceptable for your latency budget.
- **Language:** English only. This is correct — your ISO norm chunks are official English editions. The original query text passed to the reranker comes from `TransformedQuery.original_query`, which is either the raw section text (English company documents) or a topic description. If the company documents are French, this is a limitation — the reranker will score French query text against English chunks less accurately than an English query would. For MVP this is accepted. The fallback model `cross-encoder/mmarco-mMiniLMv2-L12-H384` handles multilingual if needed later.

this design is got to be changed for cross-encoder/mmarco-mMiniLMv2-L12-H384
What it is: A 12-layer MiniLM model fine-tuned on mMARCO, which is MS MARCO machine-translated into 26 languages including French and English. The training signal teaches the model to judge relevance across language pairs, not just within a single language.
The tradeoffs you are accepting
Propertyms-marco-MiniLM-L-6-v2mmarco-mMiniLMv2-L12-H384Size~85MB~450MBLayers612LanguagesEnglish only26 languages (FR + EN strong)Cold load (CPU)2–5s5–10sInference 15 pairs (CPU)~100ms~300msFR→EN cross-lingualpoorgood
The size and latency cost is real. 300ms per section is still within your latency budget — the per-section target is 200–600ms total for all of C1 excluding HyDE, and the reranker is one part of that. Measure it on your actual hardware in Step 7 and confirm.
- **Input format:** The model expects a `[query, passage]` pair. The `sentence-transformers` library's `CrossEncoder` class handles the tokenization and formatting — you pass Python strings, it handles the rest.
- **Output:** A single float score per pair. Higher is more relevant. The scale is not fixed (it is not 0–1) — it is a raw logit. What matters is relative ordering, not absolute value.

## The original query rule — why it matters and how to enforce it

HyDE generates a hypothetical ISO clause to improve retrieval. For example:

- **Original query:**  
  "The company conducts quarterly internal audits. Results are communicated to management."

- **HyDE embed_text:**  
  "The organization shall conduct internal audits at planned intervals. Results shall be reported to relevant management."

The HyDE text is better for finding the right chunks through embedding similarity. But it is worse for reranking, for two reasons.

1. **The HyDE text is a fabrication.** It sounds like ISO 9001 §9.2 because it was designed to. If you rerank using the HyDE text, you are asking "which chunk is most similar to my fabricated ISO clause" — but the agent actually wants to know "which chunk is most relevant to the company's actual section text." Those are different questions.
2. **HyDE can introduce specificity that was not in the original input.** If HyDE generates "The organization shall conduct internal audits at planned intervals to determine whether the quality management system conforms to ISO 9001 requirements," and the actual section says nothing about ISO 9001 specifically, you have added a constraint that was not there. The reranker would then downrank chunks that don't explicitly mention ISO 9001 conformance.

**The rule:** the reranker always receives `TransformedQuery.original_query`, never `embed_text`.

This is enforced architecturally, not by convention. The `Reranker.rerank()` method takes `(query_text: str, candidates: List[RetrievedChunk])` — not a `TransformedQuery`. The caller (`RAGEngine.retrieve()`) is responsible for passing `transformed_query.original_query` explicitly. The reranker has no access to `embed_text` and cannot accidentally use it.

this section is usless as the hyde has already been removed

## What the Reranker receives and returns

**Input:**
- `query_text: str` — always `TransformedQuery.original_query`
- `candidates: List[RetrievedChunk]` — the top-k from HybridRetriever, ordered by `rrf_score`

**Output:**
- Same `List[RetrievedChunk]`, but with `rerank_score` populated on each chunk and the list sorted by `rerank_score` descending

The reranker does not add or remove chunks. It re-scores and re-orders what the retriever gave it. The length stays the same going in and out — `top_k_rerank` truncation happens in the Context Assembler, not here. Pass all candidates through, score all of them, return all of them reordered.

## Startup loading — load once, reuse forever

The model is loaded once when `RAGEngine` initializes, held in memory for the process lifetime, and reused on every `retrieve()` call. The cold load cost (2–5 seconds) is paid once at startup, not per request.

The `CrossEncoder` class from `sentence-transformers` loads the model synchronously. This is acceptable at startup — `RAGEngine` is not serving requests yet. After loading, every `predict()` call is CPU inference, typically ~100ms for 15 pairs.

One important operational detail: the model runs on CPU. Your environment is local CPU only (no GPU). `sentence-transformers` defaults to CPU if no GPU is available, so no special configuration is needed. The 100ms inference estimate is for CPU — on a slow machine it may be 200–300ms, still within your per-section latency budget.

## Scoring mechanics

The `CrossEncoder.predict()` method takes a list of `[query, passage]` pairs and returns a numpy array of scores. One call, all 15 pairs scored in a single batch. The batch is more efficient than 15 individual calls because the model can process them together.

The pairs are constructed as: `[[query_text, chunk.text] for chunk in candidates]`. The `chunk.text` field is the full clause text stored in the Qdrant payload — the same text that will be injected into the LLM prompt. You are scoring against the actual content, not a summary or title.

After `predict()` returns, iterate over candidates and scores together, set `chunk.rerank_score = float(score)` on each chunk, then sort the list by `rerank_score` descending. Return the sorted list.

## What "ordering improves on golden queries" means concretely

You need at least 5–10 golden queries with known correct clauses before running this test. A golden query is a triple: (query_text, norm_filter, expected_clause_number). For example:

| Query | Filter | Expected |
|-------|--------|----------|
| "The company trains all new employees on quality procedures" | `["ISO9001"]` | "7.2" (Competence clause) |
| "Audit results are shared with top management each quarter" | `["ISO9001"]` | "9.3" (Management review) or "9.2" (Internal audit) |
| "We identify environmental aspects of our manufacturing process" | `["ISO14001"]` | "6.1.2" (Environmental aspects) |

For each golden query, run the full pipeline up to and including the reranker. Check two things:

- **Check 1 — Recall:** Is the expected clause present in the reranked list at all? If it was in the top-15 from the retriever but dropped out after reranking, something is wrong. The reranker should not remove relevant clauses — it only reorders.
- **Check 2 — Rank improvement:** What was the expected clause's rank before reranking (by `rrf_score`) versus after (by `rerank_score`)? Improvement means the correct clause moved up. You are not expecting perfection — you are looking for a consistent pattern that the reranker moves relevant clauses toward the top.

Do not set a fixed threshold for this test at MVP. The ablation table in Phase 5 is where you measure Recall@3, Recall@5, and MRR rigorously. Here you just want evidence that the reranker is contributing positively — the correct clause should be rank #1 or #2 after reranking for most golden queries.

## The original-query test — how to write it

This test verifies that the reranker receives `original_query` and not `embed_text` when HyDE was used. It is a behavioral test, not a mock-args test — you verify the outcome, not the internal call.

The setup: construct a scenario where `original_query` and `embed_text` are meaningfully different (i.e., HyDE ran). Score the candidates against both texts. Verify the scores differ. Then verify that the scores produced by the full pipeline match the `original_query` scores, not the `embed_text` scores.

Concretely:
original_query: "We check our suppliers every year"
embed_text: "The organization shall evaluate and re-evaluate external
providers at defined intervals per clause 8.4"

Score candidates against original_query → score_set_A
Score candidates against embed_text → score_set_B

A ≠ B (verify the texts produce different scores — confirms the test is meaningful)

Run full pipeline with HyDE active
→ pipeline_scores

Assert pipeline_scores == score_set_A (original query was used)
Assert pipeline_scores ≠ score_set_B (HyDE text was NOT used)

This test fails if someone later "optimizes" the pipeline by passing `embed_text` to the reranker instead of `original_query` — which would be a correctness regression disguised as a performance improvement.

## Development sequence

### Step 1 — Operational Setup
Install the package, pull the model, time the cold load, and confirm the model runs on your hardware. Do not skip the timing step. If your machine takes 8 seconds to load, you need to know that before wiring it into startup — you may want to move the load to a background thread with a readiness flag.

### Step 2 — Define the Architectural Boundary
The `rerank()` method signature takes `query_text: str` as a plain string — not a `TransformedQuery`. This is what enforces the original-query rule structurally. The caller must extract `original_query` before calling; the reranker cannot accidentally reach into `TransformedQuery` and use `embed_text`.

### Step 3 — Implement the Core Logic
The key detail is that `predict()` takes a list of pairs, not individual pairs — use the batch call. Also: return all candidates with scores set, do not apply `top_k_rerank` truncation here. The Context Assembler owns that decision.

### Step 4 — Write the Original-Query Test
This is the most important test in this component. Write it before Step 5 — if the original-query rule is broken, the golden query results are unreliable anyway.

### Step 5 — Build and Test with Golden Queries
Requires you to build your golden query set first. Do this as a separate task before Step 5 — sit with your actual ISO PDF, pick 5–10 sections from real company documents (or write plausible ones), and manually identify which ISO clause should be the top result. This set is also what you will use in Phase 5 evaluation, so building it now is not throwaway work.

### Step 6 — Wire into RAGEngine
In `RAGEngine.retrieve()`, the call sequence becomes: `HybridRetriever.retrieve(transformed_query)` → `Reranker.rerank(transformed_query.original_query, candidates)` → pass to Context Assembler. The explicit `original_query` extraction happens at this call site, visible to any future reader.

### Step 7 — Measure and Tune
The 100ms estimate is for a modern laptop CPU. On older hardware or under load it may be higher. Measure it, log it, and if it consistently exceeds 300ms consider reducing the candidate count passed to the reranker from 15 to 10. That is a tuning decision — make it with data, not guesswork.