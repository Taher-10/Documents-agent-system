# End-to-End Data Flow

This document traces the complete journey of data through the pipeline, from a raw PDF file to a populated Qdrant vector collection. Each stage describes the input consumed, the transformation applied, and the output produced.

---

## Overview

```
Raw PDF
  └─> [Parser]            → ParsedDocument
        └─> [PageTracker] → PageTracker (stateful resolver)
        └─> [Segmenter]   → List[ClauseSpan] + ClauseNode tree
              └─> [Chunker]    → List[NormChunk]
                    └─> [Enricher]  → List[NormChunk] (enriched)
                          └─> [Registry] → JSON file on disk
                                └─> [Embedder + BM25SparseEncoder] → EmbeddingResult
                                      └─> [VectorStoreManager]     → Qdrant collection
```

---

## Stage 1: PDF to ParsedDocument

**Module**: `parser/pipeline.py` → `parse_iso_pdf(pdf_path)`

**Input**: a file path string, e.g. `"data/n9001.pdf"`.

**What happens**:
1. PyMuPDF (`fitz`) opens the PDF. A scan over up to 200 pages identifies recurring header and footer blocks.
2. A full document scan counts characters per font size, establishing the body font and mapping 1–4 larger sizes to heading levels H1–H4.
3. Body indentation and line spacing statistics are derived for use in the heading scorer.
4. For each page (within the normative body — from the first clause-1 heading to the first annex):
   - `pdfplumber.find_tables()` detects grid tables; `extract_tables_with_pdfplumber()` converts them to Markdown.
   - `page.get_text("dict", sort=True)` extracts blocks with per-span font metadata.
   - Each block is scored across 8 signals and classified as heading or body text.
   - Sub-clause heading layout defects are repaired.
   - TOC pages (> 10 dot-leader sequences) are skipped.
   - `<!-- page:N -->` markers are prepended to each page's output.
5. All pages are joined with plain blank lines; page marker positions are indexed into `page_map`; heading positions are extracted into `heading_positions`.

**Output**: `ParsedDocument`
```python
ParsedDocument(
    standard_id="n9001",          # PDF filename stem
    markdown="<!-- page:4 -->\n## 4 Context ...\n...",  # full document text
    page_map={0: 4, 2150: 5, ...},  # char_offset → page_num
    heading_positions=[
        {"offset": 14, "level": 2, "text": "4 Context of the organization"},
        {"offset": 243, "level": 3, "text": "4.1 Understanding the organization ..."},
        ...
    ]
)
```

**What is discarded at this stage**:
- Front matter (pages before the first clause-1 heading).
- Back matter (pages from the first annex heading onward).
- Running headers, footers, and standalone page numbers.
- TOC pages.

---

## Stage 2: Page Map to PageTracker

**Module**: `segmenter/page_tracker.py` → `PageTracker(doc.page_map)`

**Input**: `ParsedDocument.page_map` — a `{char_offset: page_num}` dict.

**What happens**: the constructor sorts the dict keys once into two parallel lists (`_offsets`, `_pages`). This single sort cost (O(n log n)) makes all subsequent lookups O(log n) via `bisect.bisect_right`.

**Output**: a `PageTracker` instance held in memory. Used exclusively by the chunker (Stage 5) to resolve the starting character offset of each chunk part to its PDF page number.

---

## Stage 3: ParsedDocument to List[ClauseSpan]

**Module**: `segmenter/iso_segmenter.py` → `detect_clause_boundaries(doc)`

**Input**: `ParsedDocument` (specifically `doc.markdown` and `doc.heading_positions`).

**What happens**:
1. If text exists before the first heading, a preamble `ClauseSpan(clause_id='0')` is created.
2. For each heading entry in `heading_positions`:
   - False headings (copyright notices, ICS metadata, French subtitle fragments) are suppressed; their text range is absorbed into the previous span.
   - The clause ID is extracted from the heading text via `ISO_SECTION_RE` (e.g., `"4.4.1"`) or `ANNEX_RE` (e.g., `"Annexe A"`). Falls back to a sequential placeholder `"H{n}"`.
   - The heading level is corrected to the dot-depth of the clause ID, overriding the parser's reported level.
3. Each clause block is scanned for high-uppercase non-heading lines (possible missed boundary); `UserWarning` emitted if found.

**Output**: `List[ClauseSpan]`
```python
[
    ClauseSpan(clause_id='4', start_idx=14, end_idx=243, level=1, title="4 Context..."),
    ClauseSpan(clause_id='4.1', start_idx=243, end_idx=580, level=2, title="4.1 Understanding..."),
    ClauseSpan(clause_id='4.2', start_idx=580, end_idx=910, level=2, title="4.2 Understanding..."),
    ...
]
```

---

## Stage 4: List[ClauseSpan] to ClauseNode Tree

**Module**: `segmenter/iso_segmenter.py` → `construct_clause_tree(spans, text, standard_id)`

**Input**: `List[ClauseSpan]` from Stage 3, the full markdown string, and the standard ID.

**What happens**: a monotonic stack algorithm builds the tree. For each span, the stack is popped until the top node has a strictly lower level, then the new node is attached as a child. The preamble always attaches to root directly. Lettered sub-items are skipped. After construction, leaf count is validated against `EXPECTED_LEAF_COUNTS`.

**Output**: `ClauseNode` root (the clause hierarchy tree)
```
root (level=0)
  ├─ 4 "Context of the organization" (level=1)
  │   ├─ 4.1 "Understanding the organization..." (level=2)
  │   └─ 4.2 "Understanding the needs..." (level=2)
  ├─ 5 "Leadership" (level=1)
  │   ├─ 5.1 "Leadership and commitment" (level=2)
  │   │   ├─ 5.1.1 "General" (level=3)
  │   │   └─ 5.1.2 "Customer focus" (level=3)
  ...
```

This tree is stored in the `SegmenterResult` and serialised (without `text` fields) into the JSON registry.

---

## Stage 5: List[ClauseSpan] to List[NormChunk]

**Module**: `chunker/assembler.py` → `assemble_norm_chunks(spans, markdown, standard_id, tracker)`

**Input**: `List[ClauseSpan]`, full markdown, standard ID, `PageTracker`.

**What happens** per span:
1. Raw text is sliced from `markdown[span.start_idx:span.end_idx]`.
2. `_split_text_at_paragraphs(raw_text, MAX_CHUNK_WORDS)` determines whether the clause needs splitting. Splits occur only at blank-line paragraph boundaries.
3. For each resulting part:
   - `tracker.page_at(abs_offset)` resolves the page number.
   - `build_chunk_id()` constructs the canonical ID: `"{standard_id}_{clause_id}_{partN}_p{page}"`.
   - `_strip_note_example_blocks()` removes NOTE and EXAMPLE blocks before modality detection.
   - `_detect_modality()` counts SHALL/SHOULD/MAY/CAN markers and assigns `ContentType`.
   - `_detect_cross_refs()` extracts all clause, ISO, and annex cross-references.
   - Token count is computed via whitespace split.
   - A `NormChunk` is constructed with `keywords=[]` and `bm25_tokens=[]` (placeholders for Phase 5).

**Output**: `List[NormChunk]` — `keywords` and `bm25_tokens` are empty at this point.
```python
NormChunk(
    chunk_id="n9001_4.1_part1_p5",
    norm_id="ISO9001",
    norm_full="ISO 9001:2015",
    norm_version="2015",
    clause_number="4.1",
    clause_title="Understanding the organization and its context",
    parent_clause="4",
    page_number=5,
    chunk_index=1,
    total_chunks=1,
    text="The organization shall determine external and internal issues ...",
    token_count=87,
    content_type=ContentType.REQUIREMENT,
    shall_count=2,
    should_count=0,
    has_requirements=True,
    has_permissions=False,
    has_recommendations=False,
    has_capabilities=False,
    keywords=[],           # filled by Phase 5
    related_clauses=["9.3"],
    embedding_model="",
    language="",
    bm25_tokens=[],        # filled by Phase 5
)
```

---

## Stage 6: NormChunk Enrichment

**Module**: `enricher/enricher.py` → `Enricher(chunks).enrich(chunks)`

**Input**: `List[NormChunk]` with empty `keywords` and `bm25_tokens`.

**What happens**:
1. **IDF computation**: at construction, the `Enricher` iterates all chunks and builds a term-to-IDF map using smoothed IDF: `log((N+1)/(df+1)) + 1`.
2. **TF-IDF keywords** (pass 1): for each chunk, markdown noise is stripped, stop-word-filtered unigrams and bigrams are extracted, TF × IDF scores are computed, and the top 5 terms are selected. Bigrams are preferred over same-score unigrams.
3. **BM25 tokens** (pass 2): combines stop-filtered word tokens from `chunk.text`, digit tokens from `clause_number`, and word tokens from `chunk.keywords` (just populated in pass 1). Deduplication preserves insertion order.

**Output**: the same `List[NormChunk]`, mutated in-place. `keywords` and `bm25_tokens` are now populated.
```python
# After enrichment:
chunk.keywords = ["documented information", "organization shall", "requirements", ...]
chunk.bm25_tokens = ["organization", "determine", "external", "internal", ..., "4", "1", ...]
```

---

## Stage 7a: Validation and Registry Write

**Module**: `registry/registry.py`

### Phase 6a: validate_chunks()

**Input**: `List[NormChunk]`

**What happens**: each chunk is converted to a dict and validated against Pydantic's `_ChunkValidator`. Three structural invariants are checked: chunk_id format, `has_requirements`/`shall_count` consistency, and minimum token count for non-structural chunks. All violations become `UserWarning` — the pipeline continues unconditionally.

**Output**: `int` violation count.

### Phase 6b: write_registry()

**Input**: `SegmenterResult` (`.standard_id`, `.tree`, `.chunks`)

**What happens**:
1. The standard ID slug is derived (e.g., `"iso90012015"`).
2. A timestamped filename is constructed: `iso90012015_registry_20260324T143000.json`.
3. The registry dict is built: `standard_id`, `generated_at`, `chunk_count`, the recursive `clause_tree` (without `text` fields), and the `chunks` list (without `text` and `bm25_tokens`).
4. An assertion verifies `chunk_count == len(chunks)`.
5. The JSON is written with `ensure_ascii=False` (preserves French characters).
6. A stable pointer file `iso90012015_registry_latest.txt` is updated with the new filename.

**Output**: `str` absolute path to the written JSON file.

Registry JSON structure (excerpt):
```json
{
  "standard_id": "ISO 9001:2015",
  "generated_at": "2026-03-24T14:30:00.123456",
  "chunk_count": 95,
  "clause_tree": {
    "clause_id": "root",
    "title": "Root",
    "level": 0,
    "children": [
      {
        "clause_id": "4",
        "title": "4 Context of the organization",
        "level": 1,
        "children": [...]
      }
    ]
  },
  "chunks": [
    {
      "chunk_id": "n9001_4.1_part1_p5",
      "clause_number": "4.1",
      "content_type": "requirement",
      "keywords": ["documented information", "organization shall"],
      "shall_count": 2,
      ...
    }
  ]
}
```

---

## Stage 7b: Embedding (Optional Phase 7)

**Module**: `embedder/embedder.py` + `embedder/bm25_encoder.py`

**Input**: `List[NormChunk]` from `SegmenterResult.chunks`

**Pre-check** (in `pipeline.embed_and_store`): `VectorStoreManager.validate_model_consistency()` is called before embedding to detect model-space mismatches early. Raises `RuntimeError` on mismatch.

**What happens**:
1. `EmbedderService.__init__()` probes Ollama. Selects either the Ollama backend or the sentence-transformers fallback.
2. Chunks are filtered to those with `content_type.value` in `EMBED_CONTENT_TYPES` (all four by default).
3. `BM25SparseEncoder(eligible)` is instantiated once with the full eligible corpus, computing DF and avgdl for Pass 1.
4. Chunks are processed in batches of `EMBED_BATCH_SIZE` (default 50):
   - `_build_embedding_text(chunk)` builds the prefixed input string: `"{norm_full} clause {number} {title}: {text}"`.
   - Ollama: all texts in the batch are fired as concurrent `httpx` requests via `asyncio.gather(return_exceptions=True)`. Concurrency is capped by `asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)`. Failed individual requests are tracked per-chunk.
   - Fallback: `sentence_transformers.SentenceTransformer.encode()` processes the batch synchronously.
   - For each successful embedding: `bm25_encoder.encode(chunk)` computes `(sparse_indices, sparse_values)`.
   - `EmbeddedChunk(chunk=chunk, vector=..., sparse_indices=..., sparse_values=...)` is created.
5. `EmbeddingResult` is returned with `embedded`, `failed_chunks`, and `failure_rate`.

**Output**: `EmbeddingResult`
```python
EmbeddingResult(
    embedded=[
        EmbeddedChunk(
            chunk=<NormChunk "n9001_4.1_part1_p5">,
            vector=[0.021, -0.043, ..., 0.018],   # 768 floats
            sparse_indices=[312, 1045, 7823, ...], # ascending
            sparse_values=[0.84, 0.61, 0.32, ...], # BM25 scores
        ),
        ...
    ],
    failed_chunks=[],
    failure_rate=0.0
)
```

**Failure thresholds** (enforced by `pipeline.embed_and_store`, not `EmbedderService`):
- `failure_rate > 0.10` → `UserWarning`
- `failure_rate > 0.30` → `RuntimeError` (aborts upsert)

---

## Stage 7c: Qdrant Upsert (Optional Phase 7)

**Module**: `vector_store/qdrant_store.py` → `VectorStoreManager.upsert_chunks()`

**Input**: `List[EmbeddedChunk]` from `EmbeddingResult.embedded`

**What happens**:
1. Vector size is derived from `embedded_chunks[0].vector`.
2. `_ensure_collection()` checks whether the collection exists (using a local cache after the first check). Creates the named-vector collection if absent and writes the sentinel point.
3. For each `EmbeddedChunk`:
   - Point ID: `uuid.uuid5(NAMESPACE_DNS, chunk_id)` — deterministic, same chunk always gets the same UUID.
   - Vector: `{"dense": e.vector, "sparse": SparseVector(e.sparse_indices, e.sparse_values)}`.
   - Payload: all `NormChunk` fields except `bm25_tokens`, with `List[str]` fields comma-joined.
4. `client.upsert()` is called. On exception: `UserWarning` emitted, 0 returned.

**Output**: `int` count of upserted chunks.

Qdrant point structure:
```
PointStruct(
    id="a4f3d2c1-...",         # uuid5 of chunk_id
    vector={
        "dense":  [0.021, ..., 0.018],          # semantic embedding
        "sparse": SparseVector(
            indices=[312, 1045, 7823],
            values=[0.84, 0.61, 0.32]
        )
    },
    payload={
        "chunk_id":      "n9001_4.1_part1_p5",
        "text":          "The organization shall determine...",
        "clause_number": "4.1",
        "content_type":  "requirement",
        "keywords":      "documented information,organization shall",
        "shall_count":   2,
        ...
        # bm25_tokens is absent
    }
)
```

---

## Dependency Graph Between Phases

The following diagram shows which phases are mandatory (all runs) versus optional (Phase 7):

```
                    [PDF file]
                        |
              [Parser: parse_iso_pdf()]          <- MANDATORY
                        |
              [ParsedDocument]
                   /        \
     [PageTracker]           [detect_clause_boundaries()]  <- MANDATORY
                                       |
                             [List[ClauseSpan]]
                           /                    \
     [construct_clause_tree()]        [assemble_norm_chunks()]  <- MANDATORY
               |                                    |
         [ClauseNode]                      [List[NormChunk] (bare)]
                                                    |
                                          [Enricher.enrich()]   <- MANDATORY
                                                    |
                                         [List[NormChunk] (enriched)]
                                          /                   \
                              [validate_chunks()]       [write_registry()]  <- MANDATORY
                                                                |
                                                         [SegmenterResult]
                                                                |
                                             ╔══════════════════╩══════╗
                                             ║  Phase 7 (OPTIONAL)     ║
                                             ╠══════════════════════════╣
                                      [validate_model_consistency()]
                                                    |
                                       [EmbedderService.embed_chunks()]
                                       [BM25SparseEncoder per chunk]
                                                    |
                                           [EmbeddingResult]
                                                    |
                                      [VectorStoreManager.upsert_chunks()]
                                                    |
                                            [Qdrant collection]
                                             ╚══════════════════╝
```
