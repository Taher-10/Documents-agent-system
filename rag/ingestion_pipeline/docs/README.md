# ISO Standard Ingestion Pipeline — Documentation Index

This documentation covers the full ingestion pipeline developed as part of a Final Year Project (PFE). The pipeline processes ISO standard PDF documents and produces structured, semantically-enriched retrieval units suitable for a Retrieval-Augmented Generation (RAG) system.

---

## Documents

| # | File | Contents |
|---|------|----------|
| 1 | [01_global_overview.md](01_global_overview.md) | High-level architecture, purpose, technology stack, pipeline phases, and design principles |
| 2 | [02_components.md](02_components.md) | Detailed per-component documentation: Parser, Segmenter, Chunker, Enricher, Registry, Embedder, BM25SparseEncoder, VectorStoreManager |
| 3 | [03_data_flow.md](03_data_flow.md) | End-to-end data flow from raw PDF to Qdrant, with data type transformations at each stage |
| 4 | [04_architecture_insights.md](04_architecture_insights.md) | Architecture patterns, dependency rules, concurrency model, error handling strategy, and design principles |
| 5 | [05_adrs.md](05_adrs.md) | Architecture Decision Records (ADRs) documenting key technical decisions, their context, alternatives, and trade-offs |
| 6 | [06_summary.md](06_summary.md) | Executive summary suitable for inclusion in a PFE report conclusion |

---

## Quick Reference: Pipeline Phases

| Phase | Module | Input | Output |
|-------|--------|-------|--------|
| 0 | `segmenter/models.py` | — | Shared type contracts |
| 1 | `parser/` | PDF file | `ParsedDocument` |
| 2 | `segmenter/page_tracker.py` | `page_map` | `PageTracker` |
| 3 | `segmenter/iso_segmenter.py` | `ParsedDocument` | `List[ClauseSpan]` |
| 4 | `segmenter/iso_segmenter.py` | `List[ClauseSpan]` | `ClauseNode` (tree) |
| 5 | `chunker/assembler.py` | `List[ClauseSpan]` + markdown | `List[NormChunk]` |
| 6 | `enricher/enricher.py` | `List[NormChunk]` | `List[NormChunk]` (enriched) |
| 7a | `registry/registry.py` | `SegmenterResult` | JSON registry file |
| 7b | `registry/registry.py` | `SegmenterResult` | SQLite clause registry (`iso_clauses`) |
| 7c | `embedder/embedder.py` + `embedder/bm25_encoder.py` | `List[NormChunk]` | `EmbeddingResult` |
| 7d | `vector_store/qdrant_store.py` | `List[EmbeddedChunk]` | Qdrant collection |

---

## Key Entry Points

```python
# Parse a PDF
from parser import parse_iso_pdf
doc = parse_iso_pdf("data/n9001.pdf")   # returns ParsedDocument

# Run the full pipeline (Phases 1-6), write registry JSON
from pipeline import segment
result = segment(doc, output_dir="output")   # returns SegmenterResult

# Run embedding + Qdrant upsert (Phase 7, optional)
from pipeline import embed_and_store
count = embed_and_store(result, collection="norms")

# Optional SQLite clause registry
#   SQLITE_REGISTRY_ENABLED=true
#   SQLITE_REGISTRY_PATH=agent_compliance/data/iso_clauses.db
#   SQLITE_REGISTRY_IF_EXISTS=skip   # skip | upsert | error
#   Note: writer always canonicalizes to a single file name: iso_clauses.db
```

---

## Source Layout

```
pipeline.py                  # Top-level orchestrator
parser/                      # Layer 1 — PDF to ParsedDocument
  pipeline.py                #   Main parse_iso_pdf() function
  document.py                #   ParsedDocument dataclass
  pdf_parser.py              #   PDF extraction helpers
  phases/                    #   Per-phase sub-modules
  config.py                  #   Parser thresholds and flags
segmenter/                   # Clause boundary and tree construction
  models.py                  #   Shared type contracts (ClauseSpan, ClauseNode, ContentType)
  page_tracker.py            #   O(log n) char-offset to page resolver
  iso_segmenter.py           #   Phase 2 (boundary detection) and Phase 3 (tree construction)
chunker/                     # NormChunk assembly
  assembler.py               #   Phase 4 — overflow splitting, modality detection
  models.py                  #   NormChunk dataclass
enricher/                    # TF-IDF and BM25 enrichment
  enricher.py                #   Phase 5 — Enricher class
registry/                    # Validation and JSON output
  registry.py                #   Phase 6 — Pydantic validation + write_registry()
embedder/                    # Dense and sparse vector generation
  embedder.py                #   Phase 7a — EmbedderService (Ollama + fallback)
  bm25_encoder.py            #   Phase 7a — BM25SparseEncoder
  models.py                  #   EmbeddedChunk, EmbeddingResult dataclasses
  config.py                  #   Embedding env-var constants
vector_store/                # Qdrant integration
  qdrant_store.py            #   Phase 7b — VectorStoreManager
tests/                       # pytest test suite
```
