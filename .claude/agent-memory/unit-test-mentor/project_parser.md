---
name: Parser Component Context
description: RAG pipeline PDF parser — 4-phase architecture, key testable functions, and mocking strategy
type: project
---

Parser lives at `rag/ingestion_pipeline/parser/`. Public entry point is `parse_iso_pdf(pdf_path)` in `pipeline.py`. Returns a `ParsedDocument` dataclass with fields: `standard_id`, `markdown`, `page_map`, `heading_positions`.

Four phases, each in its own file under `phases/`:
- Phase 1: `phase1_boilerplate.py` — `detect_headers_footers(doc, sample_pages)`. Pure dict/set logic once `doc` is mocked.
- Phase 2: `phase2_font.py` — `build_font_hierarchy(doc)`, `compute_doc_stats(doc, body_size)`, `get_block_text(block)`, `get_block_dominant_size(block)`. Block helpers take plain dicts (no mocking needed).
- Phase 3: `phase3_classify.py` — `score_heading_probability(block, ...)`, `classify_block(block, ...)`, `determine_heading_level(...)`. All take plain dicts — no PDF dependency at all.
- Phase 4: `phase4_format.py` — `format_block_as_markdown(block, ...)`. Delegates to phase 3; takes plain dicts.

Post-processing pure functions in `postprocess.py`: `is_toc_page(text)`, `normalize_whitespace(text)`, `remove_page_numbers(text)` — all take strings, zero mocking needed.

Key mocking target: `fitz.Document` (PyMuPDF). Mock `doc.page_count`, `doc[i]`, `page.get_text("blocks")`, `page.get_text("dict")`, `page.rect.height`. Phase 3/4/postprocess have no PDF dependency so need no mocking.

Config constants are in `parser/config.py`. Tests can import them directly to avoid hardcoding magic numbers.

**Why:** Student asked for unit testing strategy for a PFE (2026-03-25). This is the first session.
**How to apply:** Always distinguish which functions need doc mocks vs. which take plain dicts (no mocking needed). This distinction is the single most useful insight for this student.
