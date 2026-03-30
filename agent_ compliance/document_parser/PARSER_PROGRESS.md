# PARSER_PROGRESS.md
## QHSE Document Parser — Build Progress & Decisions

> Companion to: `PARSER_HLD.md`
> Build order (strict): M6 → M1 → M2-TierA → M2-DOCX → M3 → M4-regex → M4-LLM → M5 → M2-TierB → wire `__init__` → integration tests

---

## Module Status

| Module | File | Status | Tests |
|---|---|---|---|
| M6 — Data models | `src/document_parser/parsed_document.py` | ✅ Done | 25/25 passing |
| M1 — Diagnostician | `src/document_parser/document_diagnostician.py` | ✅ Done | 33/33 passing |
| M2-TierA — PDF extractor | `src/document_parser/extractors/tier_a.py` | ⬜ Not started | — |
| M2-DOCX — DOCX extractor | `src/document_parser/extractors/docx.py` | ⬜ Not started | — |
| M3 — Text cleaner | `src/document_parser/text_cleaner.py` | ⬜ Not started | — |
| M4-regex — Section segmenter (regex path) | `src/document_parser/section_segmenter.py` | ⬜ Not started | — |
| M4-LLM — Section segmenter (LLM fallback) | `src/document_parser/section_segmenter.py` | ⬜ Not started | — |
| M5 — Metadata extractor | `src/document_parser/metadata_extractor.py` | ⬜ Not started | — |
| M2-TierB — Hybrid extractor | `src/document_parser/extractors/tier_b.py` | ⬜ Not started | — |
| M2-TierC — Scan stub | `src/document_parser/extractors/tier_c.py` | ⬜ Not started | — |
| Wire — Pipeline entry point | `src/document_parser/__init__.py` | 🔧 Stub only | — |
| Integration tests | `tests/test_integration_parser.py` | ⬜ Not started | — |

---

## M6 — Data Models `parsed_document.py` ✅

**Completed:** 2026-03-30

### What was built
- `SectionType` — `str` Enum with 8 values: `METADATA`, `SCOPE`, `DEFINITIONS`, `REFERENCES`, `PROCESS_DIAGRAM`, `PROCEDURE_TEXT`, `RECORD_FORM`, `UNKNOWN`
- `ParsedSection` — dataclass with `to_dict()` / `from_dict()`, `page_range` serialized as list for JSON compat
- `ParsedDocument` — dataclass with:
  - `validate()` enforcing all 6 HLD invariants (see below)
  - `to_dict()` / `from_dict()` full round-trip
  - `parsed_at` auto-populated to UTC ISO 8601 via `datetime.now(tz=timezone.utc)`
- Custom exceptions: `UnsupportedFormatError`, `ExtractionFailedError`, `EmptyDocumentError`

### Validation invariants enforced
1. `sections` must not be empty
2. Every `ParsedSection.id` must be unique within the document
3. `min_confidence` must equal `min(s.extraction_confidence for s in sections)`
4. `low_quality_flag` must be `True` if `quality_tier == "C"` or `min_confidence < 0.65`
5. `file_format` must match actual file extension of `source_path`
6. At least one section must have `section_type != SectionType.UNKNOWN`

### Decisions
- `page_range` stored as `tuple[int, int]` in the dataclass but serialized to `list` in `to_dict()` for JSON compatibility — `from_dict()` converts back to `tuple`.
- `parsed_at` defaults to `datetime.now(tz=timezone.utc).isoformat()` at construction time; callers can override.
- Exceptions defined in `parsed_document.py` (not a separate `exceptions.py`) to keep the single-file contract clean for M6. Re-exported from `__init__.py`.
- `from __future__ import annotations` used for forward-ref compatibility with Python 3.12.

### Test file
`tests/test_parsed_document.py` — 25 tests, all passing

---

## M1 — Document Diagnostician `document_diagnostician.py` ✅

**Completed:** 2026-03-30

### What was built
- `PageInfo` — dataclass: page_number, page_type, has_selectable_text, image_count, font_issue, text_sample
- `PageMap` — dataclass: total_pages, file_format, quality_tier, pages, producer
- `classify_page_type(page_text, image_count, font_issue)` — pure function: image (<30 chars), text (>100 + no font issue), hybrid (else)
- `assign_quality_tier(pages)` — pure function: C if >50% image, A if all text + no font issues, B otherwise
- `inspect_document(path)` — dispatches to `_inspect_pdf` (fitz, context manager) or `_inspect_docx` (python-docx); raises `UnsupportedFormatError` for other formats
- Re-exported from `__init__.py`

### Decisions
- Used `fitz` (PyMuPDF) exclusively for PDF inspection — no subprocess `pdfinfo`/`pdffonts` calls
- Font-issue detection: `any(f[1] == "" for f in page.get_fonts())` — ext `""` means no embedded stream; base-14 fonts return `"n/a"` so are correctly excluded
- `fitz.open()` used as context manager (`with` statement) for safe handle release
- DOCX treated as one logical page — python-docx has no native page-boundary concept
- Both `fitz` and `python-docx` imported locally inside their respective functions

### Test file
`tests/test_diagnostician.py` — 33 tests, all passing

---

## Upcoming: M2-TierA — PDF Extractor

**Goal:** Extract text and tables from clean (Tier A) PDFs using pdfplumber primary + fitz fallback.

---

## Open Questions / Deferred Decisions

| # | Question | Status |
|---|---|---|
| 1 | LLM client abstraction for M4 fallback — use existing project `LLMClient` or define new interface? | ⬜ Decide before M4-LLM |
| 2 | Where does `DocumentContext` / `DocumentJob` live — inside this package or a shared `contracts/` module? | ⬜ Decide before wire step |
| 3 | Tier C OCR implementation (pytesseract / cloud) — deferred post-MVP | 🔒 Out of scope for MVP |