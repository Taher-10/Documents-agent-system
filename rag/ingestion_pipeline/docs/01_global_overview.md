# Global System Overview

## 1. Purpose

This pipeline ingests ISO standard PDF documents and produces semantically-enriched, vectorised retrieval units suitable for a Retrieval-Augmented Generation (RAG) system. The primary use case is enabling a question-answering system to retrieve precise, clause-level content from normative documents such as ISO 9001:2015 (Quality Management) and ISO 14001:2015 (Environmental Management).

The end product of a successful run is:
- A structured JSON registry of all clause chunks with their metadata and TF-IDF keywords.
- A Qdrant vector collection where each chunk is stored as a hybrid point containing a dense semantic embedding and a sparse BM25 vector, enabling both semantic and keyword-based retrieval.

---

## 2. Design Principles

### Separation of Concerns
Each phase of the pipeline has exactly one responsibility. No module performs two distinct pipeline roles. The parser only parses; the segmenter only segments; the enricher only enriches.

### Strict Dependency Directionality
Dependencies flow in one direction only, with no cycles:

```
segmenter/models → segmenter/* → chunker/* → enricher/* → registry/* → embedder/* → vector_store/* → pipeline.py
```

`pipeline.py` is the only module permitted to import from all packages. This rule is documented in the source code and enforced by design.

### Modular Replaceability
Every component can be replaced or upgraded without modifying its neighbours, because each component communicates only through well-defined data type contracts (`ParsedDocument`, `ClauseSpan`, `NormChunk`, `EmbeddedChunk`).

### Resilience by Default
All optional phases (Phase 7) degrade gracefully. Embedding failures produce `UserWarning` and partial results rather than pipeline crashes. Only critical threshold violations raise `RuntimeError`.

### Pydantic Confinement
Pydantic v2 validation is confined exclusively to `registry/registry.py`. No other module imports Pydantic. This limits the blast radius of any future Pydantic version changes.

---

## 3. Technology Stack

| Category | Library | Role |
|----------|---------|------|
| PDF extraction | PyMuPDF (`fitz`) | Font-aware text extraction with span-level metadata |
| PDF table extraction | pdfplumber | Ruled-line table detection and grid parsing |
| Data contracts | Python `dataclasses` | All inter-phase data types (no Pydantic in the hot path) |
| Validation | Pydantic v2 | Structural validation in registry layer only |
| Async HTTP | httpx | Async Ollama embedding API client |
| Embedding (primary) | Ollama (`nomic-embed-text`) | Dense vector generation via local REST API |
| Embedding (fallback) | sentence-transformers (`paraphrase-multilingual-mpnet-base-v2`, 768-dim) | Fallback when Ollama is unreachable |
| Vector database | qdrant-client + Qdrant | Named-vector collection with dense (COSINE) + sparse (BM25) vectors |
| Testing | pytest | Unit and integration tests; all external services mocked |

---

## 4. Pipeline Phases at a Glance

The pipeline is divided into two major layers and seven numbered phases.

### Layer 1 — Parser (`parser/`)

The parser converts a raw PDF into a `ParsedDocument` — a self-contained structured representation of the document text. It runs four internal phases:

| Internal Phase | Operation |
|----------------|-----------|
| Header/Footer Detection | Identifies recurring page-level boilerplate to strip |
| Font Hierarchy | Maps font sizes to heading levels (H1–H4) via character frequency |
| Per-Page Classification | Scores each text block across 8 signals to classify as heading or body |
| Post-Processing | Inserts `<!-- page:N -->` markers, removes standalone page numbers, normalises whitespace |

### Layer 2 — Segmenter Pipeline (root-level packages)

The segmenter pipeline takes the `ParsedDocument` produced by Layer 1 and executes the following phases in strict order:

| Phase | Module | Operation |
|-------|--------|-----------|
| Phase 1 | `segmenter/page_tracker.py` | Builds an O(log n) bisect-based char-offset to page resolver |
| Phase 2 | `segmenter/iso_segmenter.py` | Converts `heading_positions` into a flat ordered `List[ClauseSpan]` |
| Phase 3 | `segmenter/iso_segmenter.py` | Assembles the flat span list into a recursive `ClauseNode` tree |
| Phase 4 | `chunker/assembler.py` | Converts each `ClauseSpan` into one or more `NormChunk` objects |
| Phase 5 | `enricher/enricher.py` | Adds TF-IDF keywords and BM25 tokens to each `NormChunk` |
| Phase 6a | `registry/registry.py` | Pydantic validation of all chunks (warnings only, never raises) |
| Phase 6b | `registry/registry.py` | Writes a timestamped JSON registry file and a stable latest-pointer |
| Phase 7 (optional) | `embedder/` + `vector_store/` | Embedding + Qdrant upsert, activated by calling `embed_and_store()` |

---

## 5. Data Flow Summary

```
data/n9001.pdf
    |
    v  parse_iso_pdf()
ParsedDocument
  .standard_id    "n9001"
  .markdown       Full markdown string with <!-- page:N --> markers
  .page_map       {char_offset: page_num, ...}
  .heading_positions  [{offset, level, text}, ...]
    |
    v  Phase 1: PageTracker(page_map)
PageTracker — O(log n) bisect resolver
    |
    v  Phase 2: detect_clause_boundaries(doc)
List[ClauseSpan]
  .clause_id, .start_idx, .end_idx, .level, .title
    |
    +----> Phase 3: construct_clause_tree()
    |      ClauseNode (recursive tree, for hierarchy navigation)
    |
    v  Phase 4: assemble_norm_chunks()
List[NormChunk]  (keywords=[], bm25_tokens=[] — not yet populated)
  .chunk_id       "n9001_8.5.1_part1_p23"
  .text           Raw clause text
  .content_type   REQUIREMENT | RECOMMENDATION | INFORMATIVE | STRUCTURAL
  .shall_count, .should_count, .has_requirements, ...
  .related_clauses [cross-refs extracted by regex]
    |
    v  Phase 5: Enricher.enrich()
List[NormChunk]  (keywords and bm25_tokens now populated)
  .keywords       Top-5 TF-IDF terms
  .bm25_tokens    Word + clause-digit + keyword tokens
    |
    v  Phase 6a: validate_chunks()       [warnings only]
    v  Phase 6b: write_registry()        [JSON file written]
SegmenterResult
  .standard_id    "ISO 9001:2015"
  .tree           ClauseNode root
  .chunks         List[NormChunk]
    |
    v  Phase 7 (optional): embed_and_store()
    |
    +-- EmbedderService.embed_chunks()
    |   EmbeddingResult
    |     .embedded      List[EmbeddedChunk]
    |     .failed_chunks List[NormChunk]
    |     .failure_rate  float
    |
    +-- VectorStoreManager.upsert_chunks()
        Qdrant collection "norms"
          PointStruct.vector = {
            "dense":  List[float]  (nomic-embed-text or sentence-transformers)
            "sparse": SparseVector (BM25 indices + values)
          }
          PointStruct.payload = all NormChunk fields except bm25_tokens
```

---

## 6. Supported Standards

The pipeline currently recognises two ISO standards, identified by their PDF filename stem:

| PDF stem | Human-readable label | Short ID | Year |
|----------|----------------------|----------|------|
| `n9001`  | ISO 9001:2015 | ISO9001 | 2015 |
| `n14001` | ISO 14001:2015 | ISO14001 | 2015 |

These mappings are defined in `segmenter/models.py` (`STANDARD_ID_MAP`, `NORM_ID_MAP`, `NORM_VERSION_MAP`) and can be extended by adding new entries to those dictionaries.
