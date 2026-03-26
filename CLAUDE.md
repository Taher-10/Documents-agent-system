# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RAG (Retrieval-Augmented Generation) pipeline for ISO standard documents (ISO 9001:2015, ISO 14001:2015). The pipeline ingests PDFs, segments and enriches clauses, generates hybrid embeddings, and stores them in Qdrant for question-answering retrieval.

**Stack**: Python 3.12 | FastAPI | Qdrant | Ollama | PyMuPDF + pdfplumber | pytest

## Commands

```bash
# Run ingestion pipeline (Phases 1–6: parse → segment → chunk → enrich → validate → registry)
cd rag/ingestion_pipeline && python run.py

# Enable Phase 7 (embedding + Qdrant storage)
EMBEDDING_ENABLED=true python run.py

# Run tests
pytest rag/retrival/query_retrival/tests/test_sparse_encoder_query.py
pytest rag/retrival/query_retrival/tests/smoketest/smoke_hybrid.py

# Qdrant connection test
python rag/retrival/clients/vectorDbtest.py
```

## Environment Variables

Defined in `rag/ingestion_pipeline/embedder/config.py`:

| Variable | Default |
|---|---|
| `EMBEDDING_ENABLED` | `false` |
| `QDRANT_URL` | `http://localhost:6333` |
| `QDRANT_COLLECTION` | `norms` |
| `OLLAMA_EMBED_ENDPOINT` | — |
| `OLLAMA_EMBED_MODEL` | — |

## Architecture

### Ingestion Pipeline (`rag/ingestion_pipeline/`)

Seven sequential phases. Each phase has one responsibility and communicates via typed dataclass contracts:

```
PDF → ParsedDocument → List[ClauseSpan] → ClauseNode → List[NormChunk]
    → enriched NormChunk → JSON registry → Qdrant collection
```

| Phase | Module | Responsibility |
|---|---|---|
| 1 | `parser/` | PDF → `ParsedDocument` (markdown + page_map + heading_positions) |
| 2 | `segmenter/` | Clause boundary detection → `List[ClauseSpan]` |
| 3 | `segmenter/` | Clause tree construction → `ClauseNode` hierarchy |
| 4 | `chunker/` | Clause → `NormChunk` assembly, overflow splitting |
| 5 | `enricher/` | TF-IDF keywords + BM25 tokens added to chunks |
| 6 | `registry/` | Pydantic v2 validation + JSON registry output |
| 7 | `embedder/` + `vector_store/` | Dense (Ollama `nomic-embed-text`) + sparse (BM25) → Qdrant |

**Orchestrator**: `pipeline.py` is the only file that imports across all packages. All other modules follow strict one-directional dependency flow.

**Phase 7 resilience**: Raises only if >30% of embeddings fail or embedding model is mismatched (sentinel UUID pattern). Partial failures emit `UserWarning`.

### Retrieval Pipeline (`rag/retrival/`)

```
raw_query → QueryTransformer → TransformedQuery → HybridRetriever → List[RetrievedChunk]
```

- **QueryTransformer**: HyDE (generates ISO-clause-like hypothetical text) + ISO vocabulary injection + Qdrant filter construction. HyDE has a 5-second timeout with raw-text fallback.
- **HybridRetriever**: Qdrant RRF-ranked fusion of dense + sparse vectors.

### Key Data Models

- `ParsedDocument` — parser output: markdown, page_map `{char_offset: page_num}`, heading_positions
- `ClauseSpan` — `(clause_id, start_idx, end_idx, level, title)`
- `NormChunk` — retrieval unit with provenance, text, content_type, modal counts, keywords, bm25_tokens
- `EmbeddedChunk` — NormChunk + dense vector + sparse vector
- `TransformedQuery` — embed_text, bm25_tokens, qdrant_filter, hyde_used

### Adding a New Standard

Update `STANDARD_ID_MAP`, `NORM_ID_MAP`, `NORM_VERSION_MAP` in `rag/ingestion_pipeline/segmenter/models.py` and add the PDF to `rag/ingestion_pipeline/data/`.

## Documentation

In-depth architecture docs live in `rag/ingestion_pipeline/docs/`:
- `01_global_overview.md` — Design principles, tech stack
- `02_components.md` — Per-component deep dive
- `03_data_flow.md` — End-to-end transformations
- `04_architecture_insights.md` — Concurrency, error handling patterns
- `05_adrs.md` — Architecture Decision Records
