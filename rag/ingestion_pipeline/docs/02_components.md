# Component Documentation

This document describes each component of the ingestion pipeline in detail: its purpose, inputs, outputs, key classes and methods, configuration, error handling, and notable design decisions.

---

## 1. Parser (`parser/`)

### Purpose
Converts a raw ISO standard PDF file into a structured `ParsedDocument`. This is the only component that interacts with the raw PDF bytes; all downstream components consume the `ParsedDocument` interface.

### Input
- A file path string pointing to a PDF document (e.g., `"data/n9001.pdf"`).

### Output
A `ParsedDocument` dataclass (`parser/document.py`) with four fields:

| Field | Type | Description |
|-------|------|-------------|
| `standard_id` | `str` | Stem of the source PDF filename, e.g. `"n9001"` |
| `markdown` | `str` | Full document text as a markdown string with embedded `<!-- page:N -->` markers |
| `page_map` | `dict` | Maps `{char_offset: page_num}` for all page marker positions in `markdown` |
| `heading_positions` | `list` | Ordered list of `{offset, level, text}` dicts for all detected headings |

### Key Classes and Functions

#### `parse_iso_pdf(pdf_path: str) -> ParsedDocument`
Defined in `parser/pipeline.py`. The single public entry point for the parser. Executes all four internal phases and returns a `ParsedDocument`.

Internal phases executed by `parse_iso_pdf()`:

**Phase 1 — Header/Footer Detection**
`detect_headers_footers(doc, sample_pages=200)` (in `parser/pdf_parser.py`) scans the top 15% and bottom 15% of each page. A text block is flagged as a header or footer if it appears on more than 30% of sampled pages and is fewer than 500 characters. Both full-block and per-line matching are performed to catch blocks where the page number changes but the copyright line repeats.

**Phase 2 — Font Hierarchy**
`build_font_hierarchy(doc)` performs a single pass over all pages counting characters per font size. The most frequent size becomes the body text size. Sizes more than 0.5 pt larger than body and meeting a minimum character threshold are assigned heading levels H1–H4 (largest to smallest). `compute_doc_stats(doc, body_size)` derives the mean body indentation and mean line spacing, which feed into the heading scorer.

**Phase 3 — Per-Page Classification**
For each page, `score_heading_probability()` evaluates 8 weighted signals:

| Signal | Weight |
|--------|--------|
| Font size present in heading map | +3 |
| Text matches ISO section number regex | +3 |
| Block contains bold text (larger than body) | +2 |
| Vertical gap above block exceeds 1.5× average line spacing | +2 |
| Text length < 80 characters | +1 |
| Block starts left of typical body indentation | +1 |
| Uppercase character ratio > 0.7 | +1 |
| Text ends with a period (prose, not a heading) | -1 |

A score ≥ 4 classifies the block as a heading. An additional structural-signal guard requires a score ≥ 6 for blocks lacking any font-size or ISO-pattern signal, preventing copyright notices from being misidentified as headings. Heading depth is assigned by `determine_heading_level()`.

Table pages are detected using `pdfplumber.find_tables()`. On table pages, body-size blocks skip heading classification (their content is already captured by pdfplumber), but genuine heading-font blocks are still classified normally.

A document state machine (`FRONT_MATTER` → `CLAUSES` → `BACK_MATTER`) discards text before the first clause-1 heading and stops at annex headings, keeping only the normative body.

**Phase 4 — Post-Processing**
`_fix_clause_headings()` repairs two PyMuPDF layout defects: inline clause numbers merged with body text, and blank clause-number headings followed by orphaned title lines. TOC pages (identified by more than 10 dot-leader sequences) are skipped. Standalone page numbers and excess whitespace are removed. Page markers `<!-- page:N -->` are prepended to each page.

### Configuration Parameters
Defined in `parser/config.py`:

| Constant | Default | Effect |
|----------|---------|--------|
| `HEADER_FOOTER_ZONE` | 0.15 | Fraction of page height defining the header/footer zone |
| `HEADER_FOOTER_THRESHOLD` | 0.3 | Minimum fraction of pages a block must appear on |
| `HEADER_FOOTER_MAX_CHARS` | 500 | Maximum characters for a block to be considered boilerplate |
| `FONT_GAP_TOLERANCE` | 0.5 | Minimum pt gap between body size and a heading candidate |
| `HEADING_SCORE_THRESHOLD` | 4 | Minimum score to classify a block as a heading |
| `HEADING_STRUCTURAL_SCORE_THRESHOLD` | 6 | Score threshold for blocks without font/pattern signals |
| `_DEBUG_SCORES` | `False` | Set `True` to print score distribution at run end |

### Error Handling
The parser does not raise on malformed or partially corrupt PDFs. Font hierarchy construction falls back to `body_size=11.0` if no text is found. TOC pages are silently skipped. All post-processing filters degrade gracefully.

---

## 2. Segmenter — PageTracker (`segmenter/page_tracker.py`)

### Purpose
Provides O(log n) resolution of character offsets in the assembled markdown string to their corresponding PDF page numbers. It is the bridge between the parser's character-based representation and the chunker's need for page-number provenance.

### Input
- `page_map: dict` — the `{char_offset: page_num}` dict from `ParsedDocument`.

### Output
A stateful `PageTracker` instance with two public methods.

### Key Class

#### `PageTracker`

```python
PageTracker(page_map: dict)
```

**Constructor**: sorts the `page_map` keys once at construction time into two parallel lists (`_offsets`, `_pages`). All subsequent lookups use `bisect.bisect_right` — O(log n) per call.

**`page_at(offset: int) -> int`**: returns the page number that contains `offset`. Falls back to page 1 if the map is empty.

**`page_range(start: int, end: int) -> tuple`**: returns `(first_page, last_page)` for a span. Used by the chunker to record the starting page of each chunk.

### Error Handling
If constructed with an empty `page_map`, emits `UserWarning` and falls back to returning page 1 for all offsets. This allows the pipeline to continue without page-number data.

---

## 3. Segmenter — Clause Boundary Detection and Tree Construction (`segmenter/iso_segmenter.py`)

### Purpose
Transforms the `ParsedDocument`'s `heading_positions` list into (a) a flat ordered `List[ClauseSpan]` representing clause text boundaries, and (b) a recursive `ClauseNode` tree representing the full clause hierarchy.

### Input
- `ParsedDocument` (for `detect_clause_boundaries`)
- `List[ClauseSpan]`, full markdown string, `standard_id` (for `construct_clause_tree`)

### Output
- `List[ClauseSpan]` — flat boundary list
- `ClauseNode` — root of the recursive clause tree

### Key Functions

#### `detect_clause_boundaries(doc: ParsedDocument) -> List[ClauseSpan]`

Algorithm:
1. Uses `heading_positions` from the parser as authoritative boundaries — no re-scanning of raw markdown.
2. Extracts a preamble span (text before the first heading) when present.
3. For each heading, suppresses false headings matched by `_FALSE_HEADING_RE` (copyright notices, ICS codes) and French subtitle fragments (`_SUBTITLE_FRAGMENT_RE`). Suppressed ranges are absorbed into the preceding span.
4. Assigns `clause_id` from ISO section number regex (e.g., `"4.4.1"`) or annex pattern (e.g., `"A"`). Falls back to `"H{n}"` sequential placeholders.
5. Overrides the parser-reported heading level with the dot-depth of the `clause_id` (e.g., `"4.4.1"` → level 3), correcting parser-level noise.
6. Scans each clause block for lines with ≥ 80% uppercase density (possible missed boundary), emitting `UserWarning` for investigation.

#### `construct_clause_tree(spans, text, standard_id) -> ClauseNode`

Algorithm (monotonic stack):
1. Initialises a root `ClauseNode(clause_id='root', level=0)` and a stack `[root]`.
2. For each span: pops the stack until the top has a strictly lower level than the current span, then attaches the new node to the stack top.
3. The preamble span (`clause_id='0'`) is always attached directly to root, bypassing the stack logic.
4. Lettered sub-items (e.g., `"a) description"`) are skipped with a warning — they are list entries erroneously marked as headings.
5. Duplicate `clause_id` values are flagged with a warning but not dropped.
6. After construction, counts leaf nodes and validates against `EXPECTED_LEAF_COUNTS[standard_id]` (65–75 for ISO 9001, 55–70 for ISO 14001). A count outside this range emits a warning.

### Key Data Types (from `segmenter/models.py`)

**`ClauseSpan`** — intermediate boundary marker:

| Field | Type | Description |
|-------|------|-------------|
| `clause_id` | `str` | Canonical clause identifier, e.g. `"4.1.2"` |
| `start_idx` | `int` | Inclusive char offset in markdown |
| `end_idx` | `int` | Exclusive char offset in markdown |
| `level` | `int` | Hierarchy depth (1 = top-level) |
| `title` | `str` | Verbatim heading text |
| `duplicate` | `bool` | True if `clause_id` seen previously |

**`ClauseNode`** — recursive tree node:

| Field | Type | Description |
|-------|------|-------------|
| `clause_id` | `str` | Same as corresponding `ClauseSpan` |
| `title` | `str` | Verbatim heading text |
| `level` | `int` | Hierarchy depth (0 = root) |
| `text` | `str` | Full clause text slice (stripped) |
| `children` | `List[ClauseNode]` | Direct sub-clauses |

**`ContentType`** — normative classification enum:
- `REQUIREMENT` — contains SHALL / doit / doivent
- `RECOMMENDATION` — contains SHOULD / il convient / devrait
- `INFORMATIVE` — plain prose
- `STRUCTURAL` — empty or heading-only

---

## 4. Chunker (`chunker/assembler.py`, `chunker/models.py`)

### Purpose
Converts the flat `List[ClauseSpan]` into `List[NormChunk]` — the primary retrieval units of the pipeline. Handles overflow splitting for long clauses, bilingual modality detection, and cross-reference extraction.

### Input
- `spans: List[ClauseSpan]`
- `markdown: str` — full assembled markdown
- `standard_id: str` — PDF stem
- `tracker: PageTracker` — for page number resolution

### Output
`List[NormChunk]` — with `keywords` and `bm25_tokens` left empty (populated by Phase 5).

### Key Function

#### `assemble_norm_chunks(spans, markdown, standard_id, tracker) -> List[NormChunk]`

For each `ClauseSpan`:
1. Extracts raw text from `markdown[span.start_idx:span.end_idx]`.
2. Computes `parent_clause` by dropping the last dot-separated component of `clause_id` (e.g., `"8.5.1"` → `"8.5"`).
3. Calls `_split_text_at_paragraphs(raw_text, MAX_CHUNK_WORDS)` — splits at blank-line boundaries only (never mid-sentence) when the word count exceeds the threshold.
4. For each part: resolves page number via `tracker.page_at()`, builds chunk ID via `build_chunk_id()`, strips NOTE/EXAMPLE blocks, runs bilingual modality detection, optionally runs LLM refinement, extracts cross-references, counts tokens.
5. Runs `_regression_7_5_2(chunks)` as a permanent post-assembly sanity check.

#### `build_chunk_id(standard_id, clause_id, part_suffix, first_page) -> str`
Constructs the canonical chunk identifier: `{standard_id}_{clause_id}_{part_suffix}_p{first_page}`.
Example: `"n9001_8.5.1_part1_p23"`.
All chunk ID construction must go through this function.

### Modality Detection

`_detect_modality(clean_text)` applies bilingual regex patterns:

| Pattern | Signal | ContentType |
|---------|--------|-------------|
| `shall / must / is required to / doit / doivent` | SHALL | `REQUIREMENT` |
| `should / il convient / it is recommended / devrait` | SHOULD | `RECOMMENDATION` |
| `may / peut / peuvent` | Permission | (flag only) |
| `can` | Capability | (flag only) |

Classification priority: SHALL overrides SHOULD. If both are present, a `UserWarning` is emitted.

NOTE and EXAMPLE blocks are stripped before modality detection via `_strip_note_example_blocks()` to avoid counting modal verbs in non-normative notes.

### Cross-Reference Extraction

`_detect_cross_refs(text)` extracts four categories of references:
- English clause references: `"see clause 4.1"`, `"section 8.5"`
- French clause references: `"voir 4.4"`, `"conformément aux exigences de 6.1"`
- ISO document references: `"ISO 9001"`, `"ISO 14001-1:2015"`
- Annex references: `"Annex A"`, `"Annexe B"`

Non-breaking spaces (`\xa0`) are normalised. Results are deduplicated while preserving insertion order.

### Configuration Parameters

| Variable | Default | Source |
|----------|---------|--------|
| `MAX_CHUNK_WORDS` | 600 | `os.getenv("MAX_CHUNK_WORDS", "600")` |
| `LLM_NORMALISATION` | `False` | `os.getenv("LLM_NORMALISATION", "false")` |
| `LLM_MODEL` | `"mistral"` | `os.getenv("LLM_MODEL", "mistral")` |
| `OLLAMA_URL` | `"http://localhost:11434/api/generate"` | `os.getenv("OLLAMA_URL", ...)` |

### Regression Guard

`_regression_7_5_2(chunks)` is a permanent test that must never be removed. It validates that ISO 9001:2015 §7.5.2 yields 3–4 discrete obligations. This clause contains a `doit` followed by lettered items a), b), c) — each being a distinct requirement. A mismatch emits a `UserWarning`, signalling regression in boundary detection or modality extraction.

### Key Data Type: `NormChunk`

Defined in `chunker/models.py`. The primary retrieval unit of the entire pipeline.

| Field Group | Fields |
|-------------|--------|
| Identity | `chunk_id` |
| Provenance | `norm_id`, `norm_full`, `norm_version`, `clause_number`, `clause_title`, `parent_clause`, `page_number`, `chunk_index`, `total_chunks` |
| Content | `text`, `token_count` |
| Classification | `content_type` (ContentType enum) |
| Modal counts | `shall_count`, `should_count`, `has_requirements`, `has_permissions`, `has_recommendations`, `has_capabilities` |
| Retrieval enrichment | `keywords` (List[str]), `related_clauses` (List[str]) |
| Embedding provenance | `embedding_model` (str, default `""`) |
| Language | `language` (str, default `""`) |
| BM25-only | `bm25_tokens` (List[str], excluded from Qdrant payload) |

---

## 5. Enricher (`enricher/enricher.py`)

### Purpose
Adds two retrieval-focused fields to every `NormChunk`: `keywords` (top-5 TF-IDF terms) and `bm25_tokens` (combined word/clause-digit/keyword tokens for local BM25 retrieval).

### Input
- `List[NormChunk]` — the full chunk corpus (used for IDF computation at construction time)

### Output
- The same `List[NormChunk]`, mutated in-place with `keywords` and `bm25_tokens` populated.

### Key Class

#### `Enricher`

```python
Enricher(chunks: List[NormChunk])
```

**Constructor**: pre-computes corpus-level IDF for all terms across all chunks. IDF formula:

```
IDF(t) = log((N + 1) / (df + 1)) + 1
```

where N is total chunk count and df is the number of chunks containing term t. The smoothing constants (+1) prevent zero IDF for universal terms and avoid log(0) for rare terms.

**`enrich(chunks: List[NormChunk]) -> List[NormChunk]`**: iterates all chunks, calling:
1. `_tfidf_keywords(chunk)` — populates `chunk.keywords` with top-5 terms.
2. `_bm25_tokens(chunk)` — populates `chunk.bm25_tokens` (reads `chunk.keywords`, so order is mandatory).

**`_tfidf_keywords(chunk)`**: computes TF × IDF for all unigrams and bigrams in the chunk. Ranks by descending score, preferring bigrams over same-score unigrams (bigrams carry more semantic context), with alphabetical tie-breaking. Returns the top 5.

**`_bm25_tokens(chunk)`**: builds the BM25 token list from three sources, with order-preserving deduplication:
1. Stop-word-filtered alphabetic word tokens from `chunk.text`.
2. Digit tokens from `clause_number` (e.g., `"7.5.2"` → `["7", "5", "2"]`).
3. Word-level tokens from `chunk.keywords`.

### Term Extraction

`_extract_terms(text)` processes text through four steps:
1. Strips markdown noise (`#+`, HTML comments, bold/italic markers, inline code, link syntax).
2. Extracts 3+ character alphabetic words including accented French characters.
3. Filters a combined English + French stop-word list.
4. Generates all adjacent bigrams from the filtered word list.

### Design Constraint
The only pipeline import in this module is `NormChunk` from `chunker.models`. All other code uses the standard library exclusively, making the enricher self-contained and easily replaceable.

---

## 6. Registry (`registry/registry.py`)

### Purpose
Provides two output-side operations: Pydantic v2 structural validation of all chunks (Phase 6a) and serialisation of the full pipeline result to a timestamped JSON registry file (Phase 6b).

### Input
- `List[NormChunk]` for validation
- `SegmenterResult` (duck-typed: any object with `.standard_id`, `.tree`, `.chunks`) for the registry write

### Output
- `int` violation count from `validate_chunks()`
- `str` absolute file path from `write_registry()`
- Two files on disk: a timestamped JSON registry and a stable latest-pointer `.txt` file

### Key Functions

#### `validate_chunks(chunks: List[NormChunk]) -> int`
Runs Pydantic v2 validation on every chunk. Violations are emitted as `UserWarning` — none raise. The pipeline continues regardless of violation count. Returns the number of violations found (0 on a clean run).

Three validators are applied via the internal `_ChunkValidator` model:
- `chunk_id_must_match_pattern`: chunk_id must match `^[a-z0-9]+_.+_part\d+_p\d+$`.
- `requirement_flag_consistency`: `has_requirements=True` requires `shall_count > 0`.
- `text_length_anomaly`: non-structural/non-informative chunks with `token_count < 3` are flagged as suspicious.

#### `write_registry(result, output_dir="output") -> str`
Writes the pipeline result to:
- `{output_dir}/{norm_slug}_registry_{YYYYMMDDTHHMMSS}.json` — the immutable, timestamped registry.
- `{output_dir}/{norm_slug}_registry_latest.txt` — a one-line pointer file that is the only mutable artifact.

**Excluded from registry JSON**:
- `text` — the registry is a structural index, not a content store; full text is stored in Qdrant.
- `bm25_tokens` — local-only field.

An `assert` gate verifies that `chunk_count == len(chunks)` before writing to prevent silent data loss.

### Pydantic Confinement
Pydantic v2 is imported only in this module. No other pipeline package imports Pydantic. This confinement limits the scope of any future library version changes to a single file.

---

## 7. Embedder (`embedder/embedder.py`)

### Purpose
Converts `List[NormChunk]` into `EmbeddingResult` by generating dense float vectors for each eligible chunk. Supports two backends: Ollama (primary, async) and sentence-transformers (fallback).

### Input
- `List[NormChunk]` — full chunk list
- `collection: str` — collection name (passed through for log context only)

### Output
`EmbeddingResult` dataclass:

| Field | Type | Description |
|-------|------|-------------|
| `embedded` | `List[EmbeddedChunk]` | Successfully embedded chunks |
| `failed_chunks` | `List[NormChunk]` | Chunks that failed after all retries |
| `failure_rate` | `float` | `len(failed_chunks) / total_eligible` (0.0–1.0) |

### Key Class

#### `EmbedderService`

**Constructor** (`__init__`): probes Ollama with a synchronous 3-second GET request. If reachable, sets `_use_ollama=True` and creates a persistent `httpx.AsyncClient`. If unreachable, loads the sentence-transformers fallback model (`paraphrase-multilingual-mpnet-base-v2`) and emits `UserWarning`. The semaphore is created lazily (not in `__init__`) because `asyncio.Semaphore` must be instantiated inside a running event loop.

**`async embed_chunks(chunks, collection) -> EmbeddingResult`**: the Phase 7a entry point. Filters chunks to those whose `content_type.value` is in `EMBED_CONTENT_TYPES` (all four types by default). Processes chunks in batches of `EMBED_BATCH_SIZE`. For each successful batch, calls `BM25SparseEncoder.encode()` per chunk to compute sparse indices and values. Returns `EmbeddingResult` without raising.

**`_build_embedding_text(chunk) -> str`**: builds the string sent to the embedding model. Format: `"{norm_full} clause {clause_number} {clause_title}: {text}"`. The structured prefix anchors the clause identity so that clauses sharing normative vocabulary produce distinct vectors.

**`async _embed_single_ollama(text, model) -> List[float]`**: embeds one text via Ollama with semaphore-controlled concurrency and exponential backoff retry.

**`async close()`**: releases the `httpx.AsyncClient` connection pool. Must be called after all embedding is complete.

### Retry Strategy

| Condition | Behaviour |
|-----------|-----------|
| HTTP 400, 401, 403, 404 (non-retryable 4xx) | Raises immediately, no sleep |
| HTTP 429, 5xx, timeout, connection error | Retries up to `EMBED_MAX_RETRIES` times |
| Delay formula | `min(BASE * 2^attempt, MAX_DELAY) + uniform(0, JITTER)` |

### Configuration Parameters (from `embedder/config.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server base URL |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Primary embedding model name |
| `EMBED_BATCH_SIZE` | 50 | Chunks per embedding batch |
| `MAX_CONCURRENT_REQUESTS` | 10 | Semaphore cap for concurrent Ollama requests |
| `EMBED_MAX_RETRIES` | 5 | Per-request retry attempts |
| `EMBED_RETRY_BASE_DELAY` | 0.5 s | Exponential backoff base |
| `EMBED_RETRY_MAX_DELAY` | 30.0 s | Backoff ceiling |
| `EMBED_RETRY_JITTER` | 0.5 s | Random jitter added to each delay |
| `EMBED_WARNING_THRESHOLD` | 0.10 | Warn if failure rate exceeds 10% |
| `EMBED_CRITICAL_THRESHOLD` | 0.30 | Abort upsert if failure rate exceeds 30% |
| `SPARSE_DIM` | 131072 (2^17) | BM25 hash vocabulary size |
| `EMBED_CONTENT_TYPES` | All four | ContentType values eligible for embedding |

### Error Handling
`embed_chunks()` never raises. Batch-level failures emit `UserWarning` and record all chunks in the batch as failed. Per-chunk failures (returned as exceptions via `return_exceptions=True` in `asyncio.gather`) are recorded individually. The caller (`pipeline.embed_and_store`) enforces `EMBED_WARNING_THRESHOLD` and `EMBED_CRITICAL_THRESHOLD`.

---

## 8. BM25SparseEncoder (`embedder/bm25_encoder.py`)

### Purpose
Produces sparse BM25 vectors (integer indices + float scores) from each chunk's `bm25_tokens` field. These vectors are stored as the `"sparse"` named vector in Qdrant, enabling hybrid dense/sparse retrieval.

### Input
- `List[NormChunk]` — full eligible corpus (for Pass 1 corpus statistics)
- Individual `NormChunk` objects (for Pass 2 per-chunk encoding)

### Output
- Per-chunk: `Tuple[List[int], List[float]]` — sorted ascending indices and corresponding BM25 scores.

### Key Class

#### `BM25SparseEncoder`

**Constructor** (Pass 1): iterates all chunks to compute per-token document frequency (DF), total document count (N), and average document length (avgdl). Uses `set()` per document so each token counts once toward DF regardless of frequency within that document.

**`encode(chunk: NormChunk) -> Tuple[List[int], List[float]]`** (Pass 2): for each token in `chunk.bm25_tokens`, computes the Robertson-Walker BM25 score:

```
IDF(t) = log((N - df(t) + 0.5) / (df(t) + 0.5) + 1)

score(t, D) = IDF(t) * TF(t,D) * (k1 + 1)
              ─────────────────────────────────────────
              TF(t,D) + k1 * (1 - b + b * |D| / avgdl)
```

with `k1=1.2`, `b=0.75` (Okapi BM25 industry defaults).

**`_token_to_index(token: str) -> int`** (static): maps a token to a deterministic integer index via:
```
index = int(md5(token.encode("utf-8")).hexdigest(), 16) % SPARSE_DIM
```
MD5 is used for determinism across runs regardless of `PYTHONHASHSEED`. Hash collisions are handled by summing the BM25 scores of colliding tokens — the standard strategy for hashing-based sparse retrieval.

### Design Constraint
Standard library only plus `NormChunk` (chunker.models) and `SPARSE_DIM` (embedder.config). No Qdrant, no segmenter, no enricher, no registry imports.

---

## 9. VectorStoreManager (`vector_store/qdrant_store.py`)

### Purpose
Upserts `EmbeddedChunk` objects into a Qdrant vector database collection, managing collection creation, hybrid vector schema, model consistency guards, and idempotent point IDs.

### Input
- `List[EmbeddedChunk]` — successfully embedded chunks from `EmbedderService`
- `collection_name: str` — target Qdrant collection (default: `"norms"`)

### Output
- `int` — count of chunks successfully upserted (0 on failure)

### Key Class

#### `VectorStoreManager`

**Constructor**: initialises a `QdrantClient` from environment variables (`QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_API_KEY`).

**`validate_model_consistency(collection_name, model_name)`**: reads the sentinel point from the collection and compares the stored `embedding_model` and `sparse_dim` to the current values. Raises `RuntimeError` on mismatch. Emits `UserWarning` for legacy collections without a sentinel.

**`upsert_chunks(embedded_chunks, collection_name) -> int`**: main upsert entry point.
1. Returns 0 immediately for empty input.
2. Auto-detects vector size from the first embedding.
3. Calls `_ensure_collection()` to create the collection if absent.
4. Builds `PointStruct` objects with named vectors `{"dense": List[float], "sparse": SparseVector}` and a rich payload.
5. Calls `client.upsert()`. On exception: emits `UserWarning`, returns 0.

**`_chunk_id_to_point_id(chunk_id) -> str`**: derives a deterministic UUID via `uuid.uuid5(NAMESPACE_DNS, chunk_id)`. Same chunk_id always produces the same UUID → idempotent upserts (re-running the pipeline replaces existing points rather than duplicating them).

**`_ensure_collection(collection_name, vector_size, model_name)`**: creates the collection with named-vector schema if it does not exist. Writes the sentinel point immediately after creation. Uses a `_created_collections` set to skip the round-trip on subsequent batches within the same run.

**`_write_sentinel(collection_name, model_name, vector_size)`**: writes a fixed-UUID point (`00000000-0000-0000-0000-000000000001`) with a zero vector and payload `{sentinel: True, embedding_model: ..., sparse_dim: ...}`. Failures are silently swallowed — the sentinel is best-effort.

**`_build_payload(embedded) -> dict`**: serialises all `NormChunk` fields except `bm25_tokens`. Serialisation rules:
- `List[str]` → comma-joined string (empty list → `""`)
- `ContentType` enum → `.value` string
- `text` IS included (required for RAG retrieval)
- `bm25_tokens` is intentionally excluded

### Qdrant Collection Schema
Collections use a named-vector schema:
```python
vectors_config = {
    "dense": VectorParams(size=vector_size, distance=Distance.COSINE),
}
sparse_vectors_config = {
    "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False)),
}
```
Existing single-vector collections are structurally incompatible with this schema and must be deleted before the first run after upgrading.

### Configuration Parameters (from environment)

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_HOST` | `localhost` | Qdrant server hostname |
| `QDRANT_PORT` | `6333` | Qdrant server port |
| `QDRANT_API_KEY` | (none) | API key for Qdrant Cloud |
