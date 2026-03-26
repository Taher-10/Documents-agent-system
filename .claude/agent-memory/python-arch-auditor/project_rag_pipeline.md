---
name: RAG Pipeline Project Context
description: Key architectural facts about the RAG ingestion/retrieval pipeline for ISO standards
type: project
---

This is a Python 3.12 RAG pipeline for ISO 9001:2015 and ISO 14001:2015. The project lives at the working directory root.

**Import roots:** There is NO single unified root. Two separate roots exist:
- `rag/ingestion_pipeline/` — invoked via `cd rag/ingestion_pipeline && python run.py`
- `rag/retrival/` — invoked via sys.path hacks

**Why:** No `pyproject.toml` or `setup.py` exists at the project level. Neither sub-tree is installed as a package.

**Confirmed dependency direction (ingestion):**
`parser → segmenter → chunker → enricher → registry → embedder/vector_store`
Only `rag/ingestion_pipeline/pipeline.py` is supposed to import across all packages.

**Known architectural violations recorded in audit:**
- `segmenter/iso_segmenter.py` imports from `parser` (cross-layer, should use Protocol)
- `segmenter/pipeline.py` is an orphaned duplicate orchestrator — never imported, incomplete
- `retriever.py` uses `sys.path.insert` at module import time (production code)
- `retriever.py` uses `importlib` path surgery to load `BM25SparseEncoder` from ingestion tree
- `parser/` package name shadows Python stdlib `parser` module

**How to apply:** Reference these when suggesting fixes or reviewing new code in this project.
