---
name: Retrieval pipeline architecture decisions
description: Key architectural decisions, module boundaries, and known failure modes discovered in the hybrid retrieval pipeline
type: project
---

## Pipeline state as of 2026-03-27

**Branch**: Retrival-mastering

**Retriever evolution sequence** (per docstrings):
- Step 3: `retriever_dense.py` — standalone DenseRetriever (new, untracked)
- Step 4: `retriever.py` — HybridRetriever (dense + sparse + RRF) with `DenseRetriever = HybridRetriever` backward-compat alias

**Why**: retriever_dense.py exists as the Step 3 milestone file. retriever.py is Step 4 and already exports a `DenseRetriever` alias, making retriever_dense.py effectively superseded. The alias in retriever.py means smoke_dense.py and smoke_dense_multi.py already run through the hybrid code path when using `DenseRetriever`.

## Key design decisions found in code

**BM25 encoding**: Hash-based (MD5 % 131072), no persistent vocabulary file. Query side uses uniform weight 1.0; document side uses full Robertson-Walker BM25 scores. This is the correct asymmetric weighting for sparse retrieval.

**HyDE gating** (should_use_hyde):
- Signal 1: clause number present → skip HyDE (correct)
- Signal 2: ≥ min_vocab_terms ISO vocab hits → skip HyDE (min_vocab_terms defaults to 1 in transform(), 2 in should_use_hyde signature — mismatch, but transform() passes its own min_vocab_terms=1)
- Signal 3: estimated_tokens < 150 AND zero vocab hits → trigger HyDE

**HyDE timeout**: 15 seconds per attempt, 3 retries, 0.5s sleep between attempts. Total worst-case: 45+ seconds. CLAUDE.md says "5-second timeout" but code uses `HYDE_TIMEOUT=15.0`. This is a documentation/reality mismatch.

**Prefetch limit**: `max(20, top_k * 2)` — with default top_k=10 this gives 20 candidates per arm, which is the minimum. May be too small for hard queries where relevant chunks rank poorly in one arm.

**Token symmetry**: Both ingestion (enricher.py) and query (Querytransformer.py) use `tokenize_for_bm25` from `rag.shared.bm25.tokenizer` — confirmed single source of truth.

**Stop-word list duplication**: `_STOP_WORDS` is defined identically in both `enricher.py` and `tokenizer.py`. The enricher uses its own local copy rather than importing from shared. This is a maintenance risk but currently not a correctness bug.

## Known failure modes

**"shall" removed by stop-word filter**: `tokenizer.py` STOP_WORDS includes "shall" and "must". These are high-signal normative terms in ISO documents. Removing them from BM25 tokens means queries like "shall determine" get no BM25 boost for the normative weight. This is a domain-specific stop-word list design flaw.

**DenseRetriever name collision**: retriever.py line 265 reassigns `DenseRetriever = HybridRetriever`. smoke_compare.py imports `DenseRetriever` from retriever_dense.py (the actual dense-only class) AND `HybridRetriever` from retriever.py. The comparison test is structurally sound, but the alias in retriever.py could confuse maintainers into thinking "DenseRetriever" runs dense-only when it actually runs the full hybrid.

**HyDE double-scan**: transform() pre-scans the raw query for HyDE context anchors, then scans the post-HyDE text for ISO vocab. If HyDE fires and succeeds, the ISO vocab scan on the generated text may find different vocabulary than the original query intended — vocab hits from the LLM's phrasing influence BM25 tokens.

**LLM_PROVIDER read at import time**: `LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")` is evaluated when llm_client.py is imported, not when chat_complete() is called. Changing the env var at runtime has no effect.

**Ollama requests.post timeout (30s) vs asyncio.wait_for (15s)**: The inner `requests.post` in `_ollama_request` has a 30-second socket timeout, but `asyncio.wait_for` wraps the whole `asyncio.to_thread` call with 15s. The asyncio timeout fires first and cancels the thread task, but the underlying blocking `requests.post` in the worker thread continues running (Python threads cannot be forcibly cancelled). Under high load, this can accumulate stale Ollama connections.
