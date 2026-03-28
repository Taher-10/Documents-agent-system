# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RAG (Retrieval-Augmented Generation) pipeline for ISO standard documents (ISO 9001:2015, ISO 14001:2015). The pipeline ingests PDFs, segments and enriches clauses, generates hybrid embeddings, and stores them in Qdrant for question-answering retrieval.

**Stack**: Python 3.12 | FastAPI | Qdrant | Ollama | PyMuPDF + pdfplumber | pytest

## Commands

```bash
# Run ingestion pipeline — ISO 9001 (Phases 1–6: parse → segment → chunk → enrich → validate → registry)
cd rag/ingestion_pipeline && python run.py

# Enable Phase 7 (embedding + Qdrant storage) — ISO 9001
EMBEDDING_ENABLED=true python run.py

# Ingest ISO 14001 (run from repo root)
EMBEDDING_ENABLED=true python -c "
from pathlib import Path
from rag.ingestion_pipeline.pdf_parser import parse_iso_pdf
from rag.ingestion_pipeline.pipeline import segment, embed_and_store
base = Path('rag/ingestion_pipeline')
doc = parse_iso_pdf(str(base / 'data' / 'n14001.pdf'))
result = segment(doc, output_dir=str(base / 'output'), language='FR')
embed_and_store(result, collection='norms')
"

# Run unit tests (all four suites)
pytest rag/shared/vocabulary/tests/test_scanner.py rag/retrival/query_transformer/tests/test_transform.py rag/retrival/query_retrival/tests/test_sparse_encoder_query.py rag/retrival/query_retrival/tests/test_hybrid_retriever.py -v

# Smoke tests (require live Qdrant + Ollama)
python rag/retrival/query_retrival/tests/smoketest/smoke_compare.py          # 15 FR queries
python rag/retrival/query_retrival/tests/smoketest/smoke_hard_semantic.py    # 17 hard FR queries
python rag/retrival/query_retrival/tests/smoketest/smoke_hard_semantic2.py   # 50 FR queries (4 tiers)

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
| 5 | `enricher/` | TF-IDF keywords + BM25 tokens + ISO vocab hits added to chunks (language-aware) |
| 6 | `registry/` | Pydantic v2 validation + JSON registry output |
| 7 | `embedder/` + `vector_store/` | Dense (Ollama `nomic-embed-text` with `search_document:` prefix) + sparse (BM25) → Qdrant |

**Orchestrator**: `pipeline.py` is the only file that imports across all packages. All other modules follow strict one-directional dependency flow.

**Phase 7 resilience**: Raises only if >30% of embeddings fail or embedding model is mismatched (sentinel UUID pattern). Partial failures emit `UserWarning`.

### Retrieval Pipeline (`rag/retrival/`)

```
raw_query → QueryTransformer → TransformedQuery → DenseRetriever | HybridRetriever → List[RetrievedChunk]
```

- **QueryTransformer** (`Querytransformer.py`): Synchronous `transform()` — no HyDE. Applies `search_query:` prefix (nomic asymmetric), ISO vocabulary injection, clause-number detection, BM25 token augmentation, and Qdrant filter construction. `hyde_used` is always `False`.
- **DenseRetriever** (`retriever_dense.py`): Dense-only cosine similarity search via `qdrant.query_points(using="dense")`. Score convention: `rrf_score = cosine`, `dense_score = sparse_score = -1.0` sentinels. Step 3 in the development sequence.
- **HybridRetriever** (`retriever.py`): Dense + sparse (BM25) + Qdrant RRF fusion using Prefetch + `FusionQuery(Fusion.RRF)`. Sparse Prefetch is omitted when `bm25_tokens` is empty. `DenseRetriever` is kept as a backward-compat alias. Step 4 in the development sequence.
- **Shared BM25 encoder** (`rag/shared/bm25/bm25_encoder.py`): `BM25SparseEncoder.encode_query()` is used by both the ingestion enricher and the retrieval pipeline for consistent tokenisation.
- **Vocabulary scanner** (`rag/shared/vocabulary/scanner.py`): Single source of truth for ISO vocabulary hits and modal terms. `MODAL_TERMS_EN` and `MODAL_TERMS_FR` are language-specific lists; `MODAL_TERMS` is a backward-compat alias for EN. All surface-form matching uses word-boundary regex (`\b...\b`) via a lazy-init `_FORM_PATTERNS` cache — prevents false positives like "NC" inside "influencer".

### Key Data Models

- `ParsedDocument` — parser output: markdown, page_map `{char_offset: page_num}`, heading_positions
- `ClauseSpan` — `(clause_id, start_idx, end_idx, level, title)`
- `NormChunk` — retrieval unit with provenance, text, content_type, modal counts, keywords, bm25_tokens
- `EmbeddedChunk` — NormChunk + dense vector + sparse vector
- `TransformedQuery` — embed_text (with `search_query:` prefix), bm25_tokens, qdrant_filter, hyde_used (always False), iso_vocab_hits, original_query, language, norm_filter (raw IDs, preserved for diagnostics / EmptyCorpusError message)

### Adding a New Standard

Update `STANDARD_ID_MAP`, `NORM_ID_MAP`, `NORM_VERSION_MAP` in `rag/ingestion_pipeline/segmenter/models.py` and add the PDF to `rag/ingestion_pipeline/data/`.

## Documentation

In-depth architecture docs live in `rag/ingestion_pipeline/docs/`:
- `01_global_overview.md` — Design principles, tech stack
- `02_components.md` — Per-component deep dive
- `03_data_flow.md` — End-to-end transformations
- `04_architecture_insights.md` — Concurrency, error handling patterns
- `05_adrs.md` — Architecture Decision Records
