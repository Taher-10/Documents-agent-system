# Architecture Decision Records (ADRs)

This document records the significant architectural decisions made during the development of the ISO ingestion pipeline. Each ADR documents the context that prompted the decision, the decision taken, the alternatives that were evaluated, and the consequences.

---

## ADR-01: Chunking Strategy — Paragraph-Boundary Overflow Splitting

### Context
ISO standard clauses vary significantly in length. Short clauses (e.g., §4.1 "Understanding the organization") may be a few hundred words, while large clauses (e.g., §8 "Operation") can span many pages of dense normative text. A retrieval system benefits from chunks with relatively uniform length: very long chunks dilute semantic focus, while very short chunks lose context.

The pipeline needed a splitting strategy that respects the natural structure of the document without introducing mid-sentence splits, which would corrupt the meaning of normative obligations.

### Decision
Clause text exceeding `MAX_CHUNK_WORDS` (default 600 words) is split exclusively at blank-line paragraph boundaries via `_split_text_at_paragraphs()` in `chunker/assembler.py`. Splits never occur mid-sentence or mid-paragraph. The split threshold is configurable via the `MAX_CHUNK_WORDS` environment variable. Each resulting part is a distinct `NormChunk` with a `chunk_index` and `total_chunks` field recording its position within the original clause.

The chunk ID encodes the split: `"{standard_id}_{clause_id}_part1_p{page}"`, `"...part2_p{page}"`, etc.

### Alternatives Considered
- **Fixed sentence-count splitting**: would split mid-normative-obligation if a sentence boundary happened to fall at the wrong point in a complex multi-sentence requirement.
- **LLM-assisted splitting**: could produce semantically coherent splits but would require a running LLM for every document, adding latency and a hard external dependency to a mandatory phase.
- **No splitting (one chunk per clause)**: some clauses would exceed the context window of most embedding models, producing truncated or low-quality embeddings.

### Consequences
- Chunks are semantically coherent (no mid-paragraph cuts).
- The word-count ceiling of 600 words fits comfortably within the context limits of standard embedding models.
- Splitting at paragraphs means the actual chunk size can still be close to `MAX_CHUNK_WORDS` but never guaranteed to be exactly that value.
- The `chunk_index` / `total_chunks` provenance fields allow retrieval systems to reassemble split clauses when needed.

---

## ADR-02: Embedding Model Abstraction — Ollama Primary with Sentence-Transformers Fallback

### Context
The pipeline needed a dense embedding capability that could work in development environments without a GPU, in production environments with Ollama, and in CI environments with neither. Requiring Ollama as a hard dependency would block testing in most CI setups and lightweight deployments.

### Decision
`EmbedderService` (in `embedder/embedder.py`) implements a two-backend design:
- **Primary**: Ollama REST API (`nomic-embed-text` by default). Probed synchronously at construction time with a 3-second GET request to the base URL.
- **Fallback**: `sentence-transformers paraphrase-multilingual-mpnet-base-v2` (768-dimensional, bilingual EN+FR). Loaded only when Ollama is unreachable.

The selection is transparent to all callers. `pipeline.embed_and_store()` does not know or care which backend is active.

The fallback model is imported lazily inside `_load_fallback()`, not at module import time. This means `import embedder.embedder` succeeds even when sentence-transformers is not installed — the `ImportError` surfaces only if the fallback is actually needed.

### Alternatives Considered
- **Ollama only**: simpler code but requires a running Ollama instance in all environments, including CI and lightweight deployments.
- **OpenAI API**: would add a paid external dependency and network latency; unsuitable for air-gapped or cost-sensitive deployments.
- **Sentence-transformers only**: no external service required, but gives up the performance and flexibility of Ollama (which can serve arbitrary models).
- **Single model, no abstraction**: fragile; a single backend failure breaks Phase 7 entirely.

### Consequences
- The pipeline degrades gracefully from Ollama to sentence-transformers without any configuration change required.
- The `_model_name` field is set from whichever backend is active and stamped onto each `EmbeddedChunk` and into the Qdrant sentinel. This preserves full provenance even when the backend switches between runs.
- A backend switch between runs triggers the model consistency guard (ADR-03), preventing silent mixing of embedding spaces.
- The sentence-transformers model is 768-dimensional, while `nomic-embed-text` outputs a different dimensionality. Switching backends invalidates the existing collection (ADR-03 handles this).

---

## ADR-03: Vector DB Integration — Qdrant with Named Vectors and Sentinel Model Guard

### Context
The pipeline needs to store both dense semantic vectors and sparse BM25 vectors per chunk to enable hybrid retrieval. Qdrant supports named vectors (multiple vector types per point) via its `vectors_config` / `sparse_vectors_config` API.

A secondary concern is model-space integrity: if the pipeline is re-run with a different embedding model, the new vectors are in a different geometric space and cannot be compared against existing vectors. Silent mixing would produce nonsensical retrieval results.

Additionally, if `SPARSE_DIM` (the BM25 hash vocabulary size) is changed, all stored sparse indices become invalid because the hash function produces different index assignments.

### Decision
Three related decisions were made together:

1. **Named-vector schema**: collections are created with `vectors_config={"dense": VectorParams(COSINE)}` and `sparse_vectors_config={"sparse": SparseVectorParams(on_disk=False)}`. Each `PointStruct.vector` is a dict `{"dense": List[float], "sparse": SparseVector(indices, values)}`.

2. **Sentinel point**: when a collection is first created, a reserved point with a fixed UUID (`00000000-0000-0000-0000-000000000001`) and a zero vector is written. Its payload records `{embedding_model, sparse_dim}`. On every subsequent run, `validate_model_consistency()` reads this sentinel and raises `RuntimeError` if either value has changed.

3. **Idempotent point IDs**: chunk IDs are mapped to Qdrant point UUIDs via `uuid.uuid5(NAMESPACE_DNS, chunk_id)`. This is deterministic: the same chunk always gets the same UUID, so re-running the pipeline on the same document updates existing points rather than creating duplicates.

### Alternatives Considered
- **Single-vector collections** (pre-ADR-03 approach): Qdrant's older API stores one flat vector per point. Hybrid retrieval would require a separate index or post-retrieval BM25 re-ranking, adding pipeline complexity and losing the performance benefits of native sparse vector indexing.
- **Storing BM25 tokens as payload and re-encoding at query time**: would require the query-time service to have a copy of the full BM25 corpus statistics (DF, avgdl), creating a stateful dependency between ingestion and retrieval.
- **External metadata store (separate DB for model tracking)**: more complex than embedding the guard inside Qdrant itself; introduces a second service that must be kept in sync.
- **No model guard**: silent mixing of embedding spaces produces semantically nonsensical cosine similarity scores that are extremely difficult to diagnose in production.

### Consequences
- Hybrid retrieval (dense cosine + sparse BM25) is supported natively in Qdrant without additional infrastructure.
- Changing `SPARSE_DIM` or switching embedding models requires deleting and re-ingesting the entire collection (an explicit migration step documented in CLAUDE.md).
- Existing single-vector collections created before this ADR are structurally incompatible with the named-vector schema and cannot be migrated in place.
- Legacy collections without a sentinel emit a `UserWarning` (no `RuntimeError`) to maintain backward compatibility.
- Sentinels written before `sparse_dim` was added to the guard (pre-ADR-03 sentinels) also emit `UserWarning` only.

---

## ADR-04: Pydantic Isolation to the Registry Layer

### Context
Pydantic v2 is a powerful validation library but introduces a significant dependency with a history of breaking changes between major versions. If Pydantic validation were distributed across multiple modules (as it often is in FastAPI-heavy projects), a Pydantic version upgrade would require coordinated changes across the entire codebase.

The pipeline also needs to remain importable and runnable in environments where Pydantic is not installed or where a different version is present.

### Decision
Pydantic v2 is imported exclusively in `registry/registry.py`. No other module in the pipeline imports Pydantic. All inter-phase data types (`ParsedDocument`, `ClauseSpan`, `ClauseNode`, `NormChunk`, `EmbeddedChunk`, `EmbeddingResult`) are standard Python `dataclasses` with no Pydantic dependency.

The `_ChunkValidator` Pydantic model is private to `registry/registry.py` (prefixed with `_`), making it clear that it is an implementation detail of the registry layer rather than a public contract.

### Alternatives Considered
- **Pydantic BaseModel for all data types**: provides automatic validation on assignment but deeply couples every pipeline phase to Pydantic. An upgrade from Pydantic v1 to v2 would require changes to every module.
- **No validation at all**: simpler but risks silent data quality issues (malformed chunk IDs, inconsistent flag values) passing into the registry and Qdrant without detection.
- **Custom validation without Pydantic**: possible but duplicates functionality that Pydantic provides well, and raises maintenance burden.

### Consequences
- A Pydantic version upgrade requires changes only to `registry/registry.py`.
- All data types can be instantiated and used in tests without any Pydantic import.
- Validation is necessarily downstream of the data-generation phases — it cannot enforce constraints at construction time. The validation is therefore advisory (warnings only) rather than preventive.
- The `extra='allow'` configuration on `_ChunkValidator` ensures that new fields added to `NormChunk` do not break validation until the validator is updated to cover them.

---

## ADR-05: Async Concurrency Model for Embeddings

### Context
Ollama's embedding endpoint processes one text at a time. For a typical ISO standard with ~95 clauses, sequential embedding would take approximately 95 × (network round-trip + inference time) seconds — likely 2–10 minutes depending on hardware. Concurrent requests can reduce this to near the time of a single batch.

However, unlimited concurrency would saturate the Ollama server, causing timeouts and failures.

### Decision
Three concurrency mechanisms are used together:

1. **`asyncio.gather(return_exceptions=True)`**: all texts within a batch are submitted as concurrent tasks. Individual failures surface as `Exception` objects in the result list rather than aborting the batch.

2. **`asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)`**: caps the number of simultaneously active requests. Default is 10. The semaphore wraps each `_embed_single_ollama()` call via `async with self._get_semaphore()`.

3. **Lazy semaphore creation**: `asyncio.Semaphore` is created on first access inside `_get_semaphore()`, not in `__init__`. This is required because `asyncio.Semaphore` must be bound to a running event loop. Creating it in `__init__` (before `asyncio.run()` is called by the synchronous wrapper) raises a deprecation warning or error in Python 3.10+.

### Alternatives Considered
- **Sequential embedding**: trivially simple but unacceptably slow for production use.
- **Thread pool with `requests`**: would work but bypasses Python's async infrastructure, requires explicit thread management, and does not compose as cleanly with the rest of the codebase.
- **Unlimited concurrency**: risks overwhelming Ollama, causing cascading timeouts. The semaphore provides a simple backpressure mechanism.
- **Semaphore in `__init__`**: fails in Python 3.10+ because `asyncio.Semaphore` requires an active event loop at construction time.

### Consequences
- Embedding throughput scales with concurrency up to `MAX_CONCURRENT_REQUESTS` (default 10), after which it is bounded by Ollama's server capacity.
- The `return_exceptions=True` design ensures that a single failing request does not abort the batch — partial results are always returned and individual failures are tracked in `EmbeddingResult.failed_chunks`.
- The synchronous `asyncio.run()` wrapper in `pipeline.embed_and_store()` means Phase 7 cannot be awaited directly from an async caller without restructuring.

---

## ADR-06: BM25 Token Exclusion from Qdrant Payload

### Context
`NormChunk.bm25_tokens` is a large list of string tokens (typically 30–100 tokens per chunk). These tokens are needed during Phase 7a to compute the BM25 sparse vector, but they have no utility inside Qdrant after the sparse vector has been computed and stored.

Including `bm25_tokens` in the Qdrant payload would:
- Significantly increase payload storage size per point.
- Expose internal tokenisation details in the retrieval API response.
- Create confusion about which representation (the sparse vector or the token list) should be used for retrieval.

### Decision
`bm25_tokens` is intentionally excluded from the Qdrant payload in `VectorStoreManager._build_payload()`. The exclusion is documented in the method's docstring and enforced by explicit omission (the key is not in the returned dict). The `NormChunk` dataclass also marks the field with `metadata={"chroma": False}` to signal that it should not be included in any ChromaDB-compatible serialisation layer.

`bm25_tokens` is also excluded from the JSON registry written by `write_registry()`, for the same reason: the registry is a structural index, not a content store.

### Alternatives Considered
- **Include `bm25_tokens` in payload**: Qdrant filters can then use token content for hybrid metadata filtering, but this adds payload bloat and couples the retrieval layer to the tokenisation internals.
- **Store BM25 tokens in a separate Qdrant collection**: decoupled but adds retrieval complexity and a secondary collection to manage.

### Consequences
- Qdrant payload size is minimised.
- The BM25 sparse vector (already computed from the tokens) is the canonical form stored in Qdrant; the token list is transient.
- If future retrieval logic needs the raw token list (e.g., for query-time BM25 expansion), it would need to be re-derived from `chunk.text` using the same tokenisation logic.

---

## ADR-07: SegmenterResult Defined in pipeline.py

### Context
`SegmenterResult` is a container that wraps two outputs from different sub-packages: `tree: ClauseNode` (from `segmenter`) and `chunks: List[NormChunk]` (from `chunker` + `enricher`). It cannot be defined in either sub-package without that package importing from the other — which would create a cycle in the dependency graph.

### Decision
`SegmenterResult` is defined as a `@dataclass` directly in `pipeline.py`. Since `pipeline.py` is already the only module permitted to import from all packages, this is the natural home for a type that wraps outputs from multiple packages.

The registry layer (`registry/registry.py`) receives `SegmenterResult` as a duck-typed argument (documented as "any object with `.standard_id`, `.tree`, `.chunks` attributes") to avoid importing from `pipeline.py` (which imports from `registry` — a reverse import that would create a cycle).

### Alternatives Considered
- **Define in `segmenter` package**: would require `segmenter` to import `NormChunk` from `chunker`, reversing the dependency direction.
- **Define in a shared `models` package at the root level**: would work but adds another top-level package for a single dataclass, increasing structural complexity.
- **Use a Pydantic model**: unnecessary overhead for a simple container; also contradicts ADR-04.

### Consequences
- `SegmenterResult` is not importable from any sub-package; callers must import from `pipeline`.
- The duck-typing approach in `registry` means the registry functions will work with any object that has the right attributes, which is slightly less type-safe but avoids the circular import.

---

## ADR-08: Parser State Machine for Document Section Filtering

### Context
ISO standard PDFs contain three structural sections: front matter (foreword, introduction, scope — non-normative), the normative body (clauses 1 through N), and back matter (annexes, bibliography — informative). The ingestion pipeline should index only the normative body.

The parser needed a mechanism to skip front matter and stop at back matter without requiring a full two-pass approach (first identify boundaries, then extract content).

### Decision
A simple three-state machine is implemented in `parser/pipeline.py`:

- `FRONT_MATTER`: initial state. All blocks are discarded until a block matching `CLAUSE_START_RE` (a heading with a clause-1 number) is found at a heading font size.
- `CLAUSES`: normal extraction. All blocks are processed. Transitions to `BACK_MATTER` when a block matching `ANNEX_RE` (e.g., "Annexe A") is found at a heading font size.
- `BACK_MATTER`: terminal state. The outer page loop breaks immediately.

### Alternatives Considered
- **Post-extraction filtering by heading regex**: requires extracting everything and then discarding; wastes processing time on front matter and back matter.
- **PDF bookmark/outline navigation**: PyMuPDF provides access to the PDF TOC (table of contents) structure, which could theoretically identify normative sections. However, ISO PDF bookmarks are not consistently structured across different standards and editions.
- **Fixed page ranges from a config file**: brittle; page ranges change between editions and publishers.

### Consequences
- Front matter and back matter are never extracted, keeping the pipeline focused on normative content.
- The state machine is deterministic and requires no pre-computation.
- If a standard uses a non-standard structure (e.g., normative annexes), the current stop condition would exclude them. The `ANNEX_RE` pattern would need adjustment for such documents.
