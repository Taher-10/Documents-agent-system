# Executive Summary

## Project Overview

This project develops a complete, production-quality ingestion pipeline for ISO standard PDF documents, designed to serve as the data preparation layer of a Retrieval-Augmented Generation (RAG) system. The pipeline transforms unstructured normative PDF content into semantically-enriched, vectorised retrieval units stored in a hybrid vector database.

The work addresses a technically demanding problem: ISO standards are densely structured, bilingual (EN/FR), layout-sensitive documents whose normative hierarchy must be precisely preserved for accurate retrieval. Off-the-shelf chunking approaches that split on fixed token counts or generic document boundaries are inappropriate for this domain, as they destroy the clause-level semantic units that define the normative obligations of a standard.

---

## What Was Built

The pipeline is composed of seven sequential phases, implemented across eight Python packages with strictly enforced acyclic dependencies:

**Phase 1 — PDF Parsing** (`parser/`): a multi-signal heading classifier using font hierarchy, ISO section number patterns, bold text, vertical spacing, indentation, and text length to reliably identify clause headings in ISO PDFs. Two PDF libraries (PyMuPDF and pdfplumber) are used complementarily: PyMuPDF provides font-aware text extraction, pdfplumber handles table extraction. A document state machine restricts extraction to the normative body only.

**Phases 2–3 — Segmentation** (`segmenter/`): clause boundary detection converts the heading position index into a flat list of `ClauseSpan` objects encoding each clause's character-offset range. A monotonic stack algorithm assembles the flat list into a recursive `ClauseNode` tree representing the full ISO clause hierarchy.

**Phase 4 — Chunking** (`chunker/`): clause spans are converted into `NormChunk` objects with overflow splitting at paragraph boundaries (at most 600 words per chunk), bilingual modal verb analysis (SHALL/SHOULD/MAY/CAN in English and French), and cross-reference extraction (clause refs, ISO document refs, annex refs).

**Phase 5 — Enrichment** (`enricher/`): a stateful TF-IDF enricher computes corpus-level IDF across all chunks and assigns top-5 TF-IDF keywords per chunk (with bigram preference). BM25 tokens are assembled from word tokens, clause-digit tokens, and keyword tokens.

**Phase 6 — Registry** (`registry/`): Pydantic v2 validation (isolated exclusively to this module) validates structural invariants. The pipeline result is serialised to a timestamped JSON registry file providing a durable, human-readable audit trail.

**Phase 7 — Embedding and Vector Storage** (`embedder/`, `vector_store/`): an async embedding service with Ollama as primary backend and sentence-transformers as fallback computes 768-dimensional dense vectors. A two-pass corpus BM25 encoder (Robertson-Walker formula, MD5 hash index mapping) computes sparse vectors from the BM25 token lists. Both vectors are upserted into a Qdrant named-vector collection, enabling hybrid dense/sparse retrieval.

---

## Key Technical Contributions

**Clause-aligned chunking**: by detecting ISO clause boundaries from font metadata and section number patterns rather than fixed token counts, the pipeline preserves normative units (a clause, a sub-clause) as retrieval units. This is a prerequisite for accurate RAG retrieval in the normative domain.

**Hybrid dense + sparse retrieval support**: each Qdrant point carries both a dense cosine-similarity vector (for semantic query matching) and a sparse BM25 vector (for lexical precision matching). This hybrid approach is known to outperform pure dense retrieval for technical documents with specific vocabulary.

**Model consistency enforcement**: the sentinel mechanism guards against the silent corruption of a vector collection by embedding model changes. This is a production-quality concern often absent in research prototypes.

**Bilingual design throughout**: heading classification, modality detection, cross-reference extraction, stop-word filtering, and enrichment all handle both English and French without configuration changes, reflecting the bilingual nature of ISO standards.

**Strict architecture**: the no-cycles dependency rule, Pydantic isolation, deferred Phase 7 imports, and single-integration-point design (`pipeline.py`) produce a codebase that is modular, testable, and maintainable.

---

## Architecture Summary

The pipeline follows the **Pipeline design pattern** with strict **Separation of Concerns**: each module has exactly one responsibility, documented in its module docstring alongside its explicit dependency rule. The **Strategy pattern** is used for the embedding backend. The tree construction uses a **monotonic stack** algorithm. The Qdrant integration applies the **Sentinel pattern** for out-of-band metadata.

Dependencies are directed and acyclic: `segmenter/models` → `segmenter/*` → `chunker/*` → `enricher/*` → `registry/*` → `embedder/*` → `vector_store/*` → `pipeline.py`. No reverse imports exist. `pipeline.py` is the only module that imports from all packages.

Error handling is tiered: the mandatory phases (1–6) never raise and always produce a usable result; optional Phase 7 raises `RuntimeError` only under two defined conditions (model mismatch, critical embedding failure rate). This ensures that a document ingestion run always produces a registry output even when the vector database is unavailable.

---

## Results and Validation

The pipeline processes ISO 9001:2015 (`n9001.pdf`) and produces approximately 95 `NormChunk` objects covering the full normative body of the standard. A permanent regression test (`_regression_7_5_2`) validates that §7.5.2 yields 3–4 discrete obligations on every run, guarding against regressions in boundary detection.

A pytest test suite provides coverage across all major components:
- Integration test (`test_parser_to_segmenter.py`): end-to-end parsing and segmentation of `n9001.pdf`.
- Unit tests for `EmbedderService` (`test_embedder.py`): all execution paths including retry logic, fallback activation, per-chunk failure tracking, semaphore lazy creation, and sparse vector generation — all with mocked HTTP and model clients.
- Unit tests for `BM25SparseEncoder` (`test_bm25_encoder.py`): BM25 scoring properties (TF/IDF sensitivity), hash collision handling, index sorting, and edge cases.
- Unit tests for `VectorStoreManager` (`test_vector_store.py`): payload serialisation rules, idempotent point IDs, model consistency guard, sentinel write/read, and named-vector schema enforcement — all with a mocked Qdrant client.

---

## Outlook

The pipeline is designed for extension. Adding a new ISO standard requires adding three entries to dictionaries in `segmenter/models.py`. The embedding backend can be replaced by changing two lines in `embedder/config.py`. A FastAPI query API layer is noted as future work (the dependency is already present); it would consume `VectorStoreManager` for vector search and `EmbedderService.embed_text()` for query embedding, both of which are already implemented.

The modular architecture developed in this project demonstrates that a production-quality document ingestion pipeline can be built with clear separation of concerns, without sacrificing correctness or flexibility — qualities that are essential for any RAG system deployed in a regulatory or normative context.
