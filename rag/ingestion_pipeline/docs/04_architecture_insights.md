# Architecture Insights

This document analyses the architectural patterns, design principles, dependency management, concurrency model, and error handling strategy found in the codebase. It also identifies potential weaknesses and areas for future consideration.

---

## 1. Design Patterns Identified

### Pipeline Pattern
The most prominent pattern in the system. Each phase receives the output of the previous phase, applies a single well-defined transformation, and passes the result forward. The pipeline entry points (`segment_document`, `segment`, `embed_and_store`) orchestrate these phases in a fixed sequence. No phase has knowledge of what comes before or after it.

This pattern provides:
- Composability: phases can be run independently (e.g., `segment_document` for in-memory testing without file I/O).
- Testability: each phase can be unit-tested in isolation with controlled inputs.
- Replaceability: any phase can be replaced without modifying adjacent phases.

### Strategy Pattern (Embedding Backend)
`EmbedderService` implements an implicit Strategy pattern for the embedding backend. At construction time, it probes Ollama and selects either the Ollama async strategy or the sentence-transformers synchronous fallback. The `embed_chunks()` method delegates to whichever strategy was selected, and the calling code (`pipeline.py`) is entirely unaware of which backend is active.

### Monotonic Stack (Tree Construction)
`construct_clause_tree()` uses a classic monotonic stack algorithm to build a tree from a flat sorted list of annotated spans. The stack maintains the current path from root to the deepest open node. For each new span, the stack is popped until a node of strictly lower level is found (the parent), then the new node is attached. This is O(n) in the number of spans.

### Sentinel Pattern (Model Consistency Guard)
`VectorStoreManager` uses a dedicated sentinel Qdrant point (fixed UUID `00000000-0000-0000-0000-000000000001`) to record the embedding model name and `SPARSE_DIM` at collection creation time. On subsequent runs, the sentinel is read and validated before embedding begins. This is an instance of the Sentinel pattern: a reserved marker that carries out-of-band metadata without conflicting with regular data points.

### Registry/Index Pattern
The JSON registry file produced by `write_registry()` is explicitly designed as a lookup index rather than a content store. `text` and `bm25_tokens` are excluded from the JSON. The registry records structural metadata (provenance, classification, keywords, cross-references) that enables offline analysis and auditing without loading the full vector database.

---

## 2. Dependency Rules and Enforcement

The dependency graph is acyclic by design:

```
segmenter/models
    ↓
segmenter/* (page_tracker, iso_segmenter)
    ↓
chunker/*   (assembler, models)
    ↓
enricher/*
    ↓
registry/*
    ↓
embedder/*  (embedder, bm25_encoder, models, config)
    ↓
vector_store/*
    ↓
pipeline.py  ← only module that imports from all packages
```

Rules enforced by code structure:
- `segmenter/models.py` imports only from the standard library. It is the root of the dependency graph and the "contract lock" for all downstream types.
- `chunker/models.py` imports `ContentType` from `segmenter.models` — the only cross-package type dependency, and it goes in the allowed direction.
- `enricher/enricher.py` imports only `NormChunk` from `chunker.models` and the standard library.
- `registry/registry.py` imports from `segmenter.models` (for `ClauseNode`) and `chunker.models` (for `NormChunk`), but not from the enricher or any output-side module.
- `embedder/*` modules import from `chunker.models` and `embedder.config`, but not from `segmenter`, `enricher`, or `registry`.
- `vector_store/qdrant_store.py` imports only from `embedder.models` and `qdrant_client`.
- `pipeline.py` is the single integration point — it imports from all packages but no other module imports from `pipeline.py`.

The `embedder` and `vector_store` packages are additionally protected by **deferred imports** inside `embed_and_store()`. Phases 1–6 can run without those packages installed, and importing `pipeline.py` never raises `ImportError` even if Qdrant or sentence-transformers are absent.

---

## 3. Concurrency Model

### Async Embedding (Phase 7a)
Ollama's `/api/embeddings` endpoint accepts one prompt per request (unlike batch-capable APIs). The design compensates for this with controlled asynchronous concurrency:

1. All texts within a batch are submitted as concurrent tasks via `asyncio.gather(*tasks, return_exceptions=True)`.
2. A lazily-created `asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)` caps the number of simultaneously active requests at 10 (configurable). This prevents saturating Ollama while still exploiting I/O parallelism.
3. A persistent `httpx.AsyncClient` across the batch avoids connection setup overhead for each request.

The semaphore is created lazily (inside `_get_semaphore()`, not in `__init__`) because `asyncio.Semaphore` must be instantiated inside a running event loop. Instantiating it at construction time, before `asyncio.run()` is called in `embed_and_store()`, would raise a `DeprecationWarning` or `RuntimeError` in Python 3.10+.

### Synchronous Wrapper
`pipeline.embed_and_store()` is synchronous: it calls `asyncio.run(embedder.embed_chunks(...))` to drive the async embedding step. The Qdrant upsert (`VectorStoreManager.upsert_chunks()`) is fully synchronous, using the qdrant-client synchronous API. This design avoids propagating async requirements to callers of `pipeline.py`.

### BM25 Encoding (Single-Threaded)
`BM25SparseEncoder` is synchronous and single-threaded. It is instantiated once per `embed_chunks()` call, and `encode()` is called per chunk within the batch loop. Because BM25 scoring is CPU-bound and fast (hash lookups and arithmetic), parallelism is not required.

---

## 4. Error Handling Strategy

The pipeline adopts a tiered error handling strategy: phases 1–6 are designed to never halt execution; phase 7 can raise under defined conditions.

### Tier 1: Silent Degradation (Phases 1–3)
The parser handles malformed PDFs, missing fonts, and empty pages gracefully. The segmenter emits `UserWarning` for structural anomalies (false headings, duplicate IDs, high-uppercase lines, out-of-range leaf counts) but always produces a usable output.

### Tier 2: Warning-Only Validation (Phases 6a)
Pydantic validation in `validate_chunks()` always emits `UserWarning` and never raises, even when violations are found. The pipeline continues unconditionally. This is a deliberate choice: validation failures in ISO documents (which may have unusual formatting) should not block production runs.

### Tier 3: Conditional Raises (Phase 7)
Phase 7 is the only phase that can raise `RuntimeError`, and only under two specific conditions:
1. **Model mismatch**: `validate_model_consistency()` raises `RuntimeError` if the embedding model stored in the sentinel differs from the current model. This prevents silent data corruption from mixing embeddings from different model spaces.
2. **Critical failure rate**: `embed_and_store()` raises `RuntimeError` if `failure_rate > EMBED_CRITICAL_THRESHOLD` (default 30%). This prevents a partially-failed run from silently writing an incomplete collection.

### Tier 4: Best-Effort Operations
Some operations are explicitly best-effort with failure silently swallowed:
- `_write_sentinel()`: sentinel write failures do not break the pipeline (`except Exception: pass`).
- `_ensure_collection()`: Qdrant API failures emit `UserWarning` and do not prevent the return of 0.
- `EmbedderService.close()`: connection pool cleanup failures inside the `finally` block in `embed_and_store()` are silently ignored.

### Return Values as Error Signals
`validate_chunks()` returns a violation count (0 = clean), `upsert_chunks()` returns a count of 0 on failure, and `embed_and_store()` returns 0 on import failure or batch-level embedding failure. Callers can inspect return values without catching exceptions for non-critical failure detection.

---

## 5. Architecture Strengths

**Strong modularity**: each package has a single, clearly documented responsibility. Module docstrings explicitly state the dependency rule applicable to that module. New contributors can understand the boundaries without reading the full codebase.

**No-cycles dependency**: the strict acyclic dependency graph eliminates entire classes of bugs (circular import errors, implicit coupling, unexpected initialization order) and makes the codebase easier to reason about.

**Deferred Phase 7 imports**: `embedder` and `vector_store` are imported only inside `embed_and_store()`. The entire phases 1–6 pipeline is usable in environments where Qdrant or sentence-transformers are not installed. This is essential for lightweight deployments or CI environments.

**Pydantic isolation**: confining Pydantic v2 to a single module (`registry/registry.py`) means that upgrading or replacing the validation library requires changing only one file. The data contracts themselves (dataclasses) are independent of any validation framework.

**Hybrid retrieval readiness**: storing both a dense cosine-similarity vector and a sparse BM25 vector per chunk enables hybrid retrieval strategies that combine semantic similarity with lexical precision — a well-established improvement over pure dense retrieval, particularly for technical documents with specific vocabulary.

**Idempotent upserts**: deterministic UUID generation from chunk IDs ensures that re-running the pipeline on the same document replaces existing Qdrant points rather than creating duplicates. The collection converges to a consistent state regardless of how many times the pipeline runs.

**Bilingual support**: modality detection, cross-reference extraction, stop-word filtering, and enrichment all cover both English and French. The pipeline handles both languages without configuration changes.

**Regression guard**: the `_regression_7_5_2()` test is permanently embedded in the chunker's assembly function and runs on every pipeline execution. This guards against regressions in clause boundary detection being silently introduced.

---

## 6. Potential Weaknesses and Trade-offs

**Hard-coded standard support**: `STANDARD_ID_MAP`, `NORM_ID_MAP`, `NORM_VERSION_MAP`, and `EXPECTED_LEAF_COUNTS` in `segmenter/models.py` require a code change to support a new ISO standard. A configuration-file-driven approach would be more extensible but would add indirection.

**Parser state machine coupling**: the `_parse_state` state machine in `parser/pipeline.py` (FRONT_MATTER → CLAUSES → BACK_MATTER) is tightly coupled to ISO standards' specific document structure (clause 1 as the first normative heading, annexes as terminators). Documents with a different structure (e.g., ISO/IEC standards with different front-matter patterns) may require parser adjustments.

**Single-shot asyncio.run()**: `embed_and_store()` calls `asyncio.run()` to drive the async embedding step. If the caller is already inside an event loop (e.g., in a FastAPI endpoint), `asyncio.run()` raises `RuntimeError`. The `# FastAPI / Uvicorn — Not yet wired` note in CLAUDE.md acknowledges this: when the API layer is added, the embedding call will need to be restructured to `await embedder.embed_chunks(...)` directly.

**MD5 for sparse index mapping**: while MD5 is deterministic and fast, it is a cryptographic hash function repurposed for a non-cryptographic task. A purpose-built non-cryptographic hash (e.g., MurmurHash3 or FNV) would be faster. The current choice is acceptable for the workload but worth revisiting if performance profiling identifies hash computation as a bottleneck.

**BM25 corpus scope**: `BM25SparseEncoder` is instantiated per `embed_chunks()` call, so IDF statistics reflect only the chunks in the current run. If the standard is split across multiple calls or if new chunks are added incrementally, the IDF statistics will not reflect the full historical corpus. For a single-standard, single-run use case this is fine; multi-standard incremental ingestion would require a persistent DF store.

**No async Qdrant**: the `VectorStoreManager` uses the synchronous `QdrantClient`. For very large batches, the upsert call blocks the thread. An async Qdrant client would allow pipelining embedding and upsert, but the current synchronous approach is simpler and sufficient for the current batch sizes.

**`_score_log` global mutable state**: `parser/config.py` uses a module-level list `_score_log` that `phase3_classify` appends to and the parser reads and clears. This cross-module mutation via a shared mutable global is intentional (documented in CLAUDE.md) but is a coupling point that makes the parser difficult to use concurrently.

---

## 7. Comment on the No-Cycles Dependency Rule

The no-cycles rule is the single most important architectural constraint in the codebase. It is documented in `pipeline.py`'s module docstring, in each sub-module's dependency rule comment, and in CLAUDE.md.

In practice, enforcing this rule means:
- `SegmenterResult` is defined in `pipeline.py` rather than in any sub-package, because it wraps outputs from both `segmenter` (for the tree) and `chunker`/`enricher` (for the chunks). Placing it in either sub-package would require that package to import from the other, reversing or creating a cycle in the dependency graph.
- The registry module accepts `SegmenterResult` as a duck-typed argument rather than importing from `pipeline.py`, because `pipeline.py` imports from `registry` — importing back would create a cycle.
- `embedder/config.py` imports only from the standard library, even though it conceptually belongs to the embedding subsystem, because any pipeline import would risk introducing a cycle.

The practical benefit of this rule is that the pipeline is highly testable: any phase can be instantiated and tested with mock inputs without loading any of its downstream dependencies.
