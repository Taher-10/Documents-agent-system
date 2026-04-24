# Parser Summary — Compliance Agent Integration

> What the parser gives us, what's missing, and exactly what to do next.

---

## What the Parser Produces

### Entry point
```python
result   = parse_document("procedure.pdf")       # → ParseResult
sections = docling_to_sections(result)            # → list[ParsedSection]
tier, conf, flag = assess_quality(sections)       # → ("A", 1.0, False)
```

### `ParsedSection` — one object per logical section
| Field | Type | Value / Notes |
|---|---|---|
| `id` | `str` | Stable slug e.g. `section_objet_2` |
| `section_type` | `SectionType` | Semantic class — see enum below |
| `title` | `str` | Heading text from source |
| `raw_text` | `str` | Cleaned body text |
| `page_range` | `tuple[int,int]` | `(start, end)` 1-indexed |
| `extraction_confidence` | `float` | 0.55 – 1.0 |
| `heading_level` | `int` | `1` = top-level, `2` = sub-section |
| `scope` | `Any \| None` | **Empty — reserved for graph classify node** |

### `SectionType` enum (8 values)
```
METADATA · SCOPE · DEFINITIONS · REFERENCES ·
PROCESS_DIAGRAM · PROCEDURE_TEXT · RECORD_FORM · UNKNOWN
```

### `ParseResult` — document-level fields
| Field | Useful for compliance? |
|---|---|
| `title` | Yes — document name |
| `pages` | Yes — context |
| `metadata["page1_fields"]` | Yes — key/value pairs from page 1 (version, owner, date…) |
| `metadata["heading_hints"]` | Yes — list of headings found |
| `metadata["cleanup"]` | Audit log only |

---

## What the Parser Already Covers ✅

| Compliance need         | Parser field                                | Status                         |
| ----------------------- | ------------------------------------------- | ------------------------------ |
| Section text            | `raw_text`                                  | ✅ Ready                        |
| Section semantic type   | `section_type` (SectionType enum)           | ✅ Ready                        |
| Position in document    | `page_range`, `heading_level`               | ✅ Ready                        |
| Extraction quality      | `extraction_confidence`, `assess_quality()` | ✅ Ready                        |
| Document-level metadata | `ParseResult.metadata["page1_fields"]`      | ✅ Partially (what's on page 1) |

---

## What Is Missing ❌

These fields are **not produced by the parser** but are required for precise ISO clause retrieval in Phase 2:

| Missing field              | Why it matters                                                        | Where to add it                       |
| -------------------------- | --------------------------------------------------------------------- | ------------------------------------- |
| `doc_type`                 | Determines ISO clause scope (policy → clause 5, procedure → clause 8) | Document-level, before ingestion      |
| `doc_level`                | QHSE pyramid level (1=Policy … 5=Record)                              | Document-level, before ingestion      |
| `applicable_norms`         | Which standards apply (ISO 9001 / 14001 / 45001)                      | Document-level, before ingestion      |
| Hierarchy between sections | Parent/child section relationships                                    | Not needed if `heading_level` is used |

---

## SectionType → ISO Clause Scope Mapping

This is what enables targeted ISO retrieval per section in Phase 2:

| `SectionType` | ISO clauses to target |
|---|---|
| `METADATA` | Document identification (7.5.2) |
| `SCOPE` | 4.1, 4.2, 4.3, 5.2 (context, interested parties, policy) |
| `DEFINITIONS` | Clause 3 (terms), 4.1 |
| `REFERENCES` | Clause 2 (normative references) |
| `PROCEDURE_TEXT` | 8.1, 8.4, 8.5, 6.1, 6.2 (operations, planning) |
| `RECORD_FORM` | 7.5, 9.1, 9.1.1 (documented information, monitoring) |
| `PROCESS_DIAGRAM` | 4.4, 8.1 (process approach, operational control) |
| `UNKNOWN` | Broad search, no filter |

---

## Qdrant Payload Schema for QHSE Sections

Each `ParsedSection` becomes one vector in Qdrant with this payload:

```python
{
    # --- From ParsedSection ---
    "section_id":            section.id,
    "section_type":          section.section_type.value,   # e.g. "PROCEDURE_TEXT"
    "title":                 section.title,
    "raw_text":              section.raw_text,              # used as vector content
    "heading_level":         section.heading_level,         # 1 or 2
    "page_start":            section.page_range[0],
    "page_end":              section.page_range[1],
    "extraction_confidence": section.extraction_confidence,

    # --- From ParseResult (document-level) ---
    "doc_title":    result.title,
    "doc_path":     result.source_path,
    "doc_pages":    result.pages,
    "page1_fields": result.metadata.get("page1_fields", {}),  # version, owner, date…

    # --- Added externally before ingestion (not from parser) ---
    "doc_type":         "procedure",          # policy|manual|procedure|work_instruction|form|record
    "doc_level":        3,                    # 1–5 (QHSE pyramid)
    "applicable_norms": ["ISO 14001", "ISO 45001"],
}
```

---

## The `scope` Field — Reserved Hook for Phase 2

`ParsedSection.scope` is currently `None`. It is explicitly reserved by the parser for
"the graph's classify node." This is the natural place to attach Phase 2 classification
results (e.g., which ISO clauses were matched, compliance status) without modifying
the parser.

```python
section.scope = {
    "matched_clauses": ["ISO 14001 8.1", "ISO 45001 8.1.2"],
    "status": "PARTIAL",
    "confidence": 0.82,
}
```

---

## What to Build Next (Phase 1 completion → Phase 2 entry)

1. **Add `doc_type` / `doc_level` / `applicable_norms`** — a lightweight metadata envelope
   passed alongside the parser call. Can be a simple config dict per document batch.

2. **Ingest QHSE sections into Qdrant** — one vector per `ParsedSection`, payload = schema above.
   Skip sections with `extraction_confidence < 0.6` or `tier == "C"`.

3. **Build the ISO retrieval function** — given a `ParsedSection`, filter ISO Qdrant collection
   by norm + clause range hinted by `section_type` (use the mapping table above),
   then semantic search on `raw_text`.

4. **Wire into the ReAct Mapper** — pass `(section, top_k_iso_clauses)` to the agent
   and use `section.scope` to store the result.

