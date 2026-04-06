# pdf_parser — Architecture & Data Flow

## Overview

`pdf_parser` converts a raw PDF or DOCX file into a structured list of
`ParsedSection` objects ready for downstream compliance analysis.
It is built around the [Docling](https://github.com/DS4SD/docling) library and
organized into five focused modules that each own one concern.

```
caller
  │
  ├─ parse_document(file_path)   ──►  ParseResult
  │                                        │
  └─ docling_to_sections(result) ──►  list[ParsedSection]
       assess_quality(sections)  ──►  (tier, confidence, flag)
```

---

## Module Map

```
pdf_parser/
  __init__.py          Public API surface
  docling_parser.py    Docling wrapping + low-level text extraction
  _cleanup.py          Multi-pass furniture removal (headers/footers)
  docling_adapter.py   ParseResult → list[ParsedSection] conversion
  _page_ranges.py      Page range assignment for sections
  parsed_document.py   Core data models (ParsedSection, SectionType, …)
```

---

## Data Models (`parsed_document.py`)

These are the contracts passed between every stage.

### `ParseResult`  *(defined in `docling_parser.py`)*
The raw output of the first pipeline stage.

| Field | Type | Description |
|---|---|---|
| `source_path` | `str` | Absolute path to the original file |
| `text` | `str` | Full cleaned document text (markdown preferred) |
| `pages` | `int \| None` | Page count from Docling metadata |
| `title` | `str \| None` | Inferred document title |
| `metadata` | `dict \| None` | Docling metadata + cleanup audit log |
| `page_texts` | `list[str] \| None` | One entry per page, in page order |

### `ParsedSection`
One logical section after structural conversion.

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Stable slug from heading, e.g. `section_objet_2` |
| `section_type` | `SectionType` | Semantic class (SCOPE, DEFINITIONS, …) |
| `title` | `str` | Heading text as found in the source |
| `raw_text` | `str` | Cleaned body text |
| `page_range` | `tuple[int, int]` | `(start_page, end_page)`, 1-indexed |
| `extraction_confidence` | `float` | 0.55–1.0 quality score |
| `heading_level` | `int` | 1 = top-level, 2 = sub-section |
| `scope` | `Any \| None` | Set later by the graph's classify node |

### `SectionType` enum
`METADATA · SCOPE · DEFINITIONS · REFERENCES · PROCESS_DIAGRAM · PROCEDURE_TEXT · RECORD_FORM · UNKNOWN`

---

## End-to-End Data Flow

### Stage 1 — `parse_document()` in `docling_parser.py`

```
file_path (str | Path)
    │
    ▼
[1] Resolve & validate path (.pdf or .docx only)
    │
    ▼
[2] Docling: DocumentConverter().convert(path)
    └─► DoclingDocument  (internal Docling object)
    │
    ▼
[3] _extract_metadata(document)
    └─► dict  →  metadata{}
    │
    ▼  (PDF only, when remove_headers_footers=True)
[4] _filter_furniture_native(document)             ← Docling-native removal
    └─► deletes PAGE_HEADER / PAGE_FOOTER items from DoclingDocument
    └─► cleanup["native_furniture_removed"] = N
    │
    ▼
[5] _extract_text(document)
    └─► document.export_to_markdown() or .export_to_text()
    └─► raw_text: str  (markdown with ## headings when available)
    │
    ▼
[6] _extract_page_texts(document, raw_text)
    ├─► iterate Docling items → group by page_no → ordered list[str]
    └─► fallback: split raw_text on \f (form-feed)
    └─► page_texts: list[str]  (one entry per physical page)
    │
    ▼  (PDF only, when ≥3 pages)
[7] _remove_repeated_headers_footers(page_texts)    ← from _cleanup.py
    └─► returns (cleaned_pages, removed_lines)
    └─► text rebuilt from cleaned_pages
    └─► cleanup["headers_footers_removed"] = [lines...]
    │
    ▼  (PDF only)
[8] _remove_repeated_lines_global(text)             ← from _cleanup.py
    └─► second-pass: removes signatures surviving step 7
    └─► cleanup["global_line_cleanup"] = N
    │
    ▼
[9] _normalize_spacing(text)                        ← from _cleanup.py
    └─► collapses blank lines / trailing whitespace
    │
    ▼
[10] Metadata enrichment
    ├─► _extract_heading_hints(document)  →  metadata["heading_hints"]
    └─► _extract_page1_metadata_fields(page_texts[0])  →  metadata["page1_fields"]
    │
    ▼
ParseResult(source_path, text, pages, title, metadata, page_texts)
```

---

### Stage 2 — Furniture Removal (`_cleanup.py`)

Runs as three sequential passes inside `parse_document()`:

#### Pass A — Native Docling removal (step 4 above)
Docling labels some items as `PAGE_HEADER` / `PAGE_FOOTER`.
`_filter_furniture_native()` calls `document.delete_items()` to remove them
**before** any text export. This is the cheapest and most precise pass.

#### Pass B — Page-by-page heuristic (step 7)
`_remove_repeated_headers_footers()` works on the `page_texts` list:

```
page_texts list
    │
    ▼
_canonicalize_line() on top/bottom N lines of each page
    │  → lowercase, strip digits→<num>, strip separators
    ▼
Counter → lines appearing on ≥60% of pages = candidates
    │
    ▼
_find_repeated_blocks()  →  multi-line header/footer blocks
    │
    ▼
Per page:
  _top_cut_size()    → how many leading lines to remove
  _bottom_cut_size() → how many trailing lines to remove
  inline sweep       → remove candidate lines anywhere in page
    │
    ▼
_order_removed_lines() → stable human-readable removal log
    │
    ▼
(cleaned_pages: list[str], removed_lines: list[str])
```

#### Pass C — Global signature sweep (step 8)
`_remove_repeated_lines_global()` operates on the fully-joined text string.
It targets lines that repeat ≥2 times **and** match furniture heuristics
(contains `|`, keywords like `"edition"`, `"page:"`, etc.).
This catches signatures that survived the page-based pass.

---

### Stage 3 — `docling_to_sections()` in `docling_adapter.py`

```
ParseResult (or raw DoclingDocument)
    │
    ▼
[1] _split_markdown_into_sections(text)
    ├─► regex: ^(#{1,6})\s+(.+)$  →  heading boundaries
    ├─► preamble before first heading → SectionType.METADATA
    └─► list[ParsedSection]  (page_range all = (1,1) at this point)
    │
    if ≤1 section found (no markdown headings):
    ▼
[2] _split_plaintext_into_sections(text, hint_titles)
    ├─► line-by-line scan with _is_plain_heading_line()
    │   (checks length ≤64, ending punctuation, known French heading vocab)
    └─► list[ParsedSection]
    │
    ▼
[3] _promote_metadata_preamble(sections, metadata)
    └─► if first section is METADATA: append page1_fields key/values to raw_text
    │
    ▼
[4] _assign_page_ranges_from_page_texts(sections, page_texts, total_pages)
    │                                              ← from _page_ranges.py
    └─► see page-range flow below
    │
    ▼
list[ParsedSection]  with correct page_range on every entry
```

For a raw `DoclingDocument` input (no `ParseResult`), step 4 uses
`_assign_page_ranges()` + `_extract_heading_page_candidates()` instead,
which scans Docling item provenance directly.

---

### Stage 4 — Page Range Assignment (`_page_ranges.py`)

Both assignment strategies share `_apply_ranges_from_starts()`.

#### Strategy A — From `page_texts` *(used when caller has a `ParseResult`)*
```
sections: list[ParsedSection]   page_texts: list[str]
    │                                │
    ▼                                ▼
_normalize_heading_key() on each section title AND each page blob
    │  → NFKD unicode, lowercase, strip punctuation, collapse spaces
    ▼
For each section (in order):
  scan forward through normalized page blobs
  if section title key found inside page blob → start_page = page index + 1
    │
    ▼
starts: list[int]  (one per section)
    │
    ▼
_apply_ranges_from_starts():
  section[i].page_range = (starts[i], starts[i+1] - 1)
  last section → end_page = total_pages
```

#### Strategy B — From Docling item provenance *(used for raw DoclingDocument)*
```
_extract_heading_page_candidates(doc)
    └─► iterate doc items → _is_heading_like() → (normalized_title, page_no)

_assign_page_ranges(sections, heading_candidates, total_pages)
    └─► same cursor-forward matching as Strategy A
        but matches against Docling item titles instead of page blobs
```

---

### Stage 5 — `assess_quality()` in `docling_adapter.py`

```
list[ParsedSection]
    │
    ▼
For each section:
  empty  → empty_sections++, short_sections++
  len < 40 chars → short_sections++
    │
    ▼
empty_ratio  = empty_sections / total
short_ratio  = short_sections / total
    │
    ▼
tier assignment:
  empty_ratio ≥ 0.50  →  "C"  (cap confidence at 0.5)
  short_ratio ≥ 0.25  →  "B"  (cap confidence at 0.8)
  otherwise           →  "A"  (floor confidence at 1.0)
    │
    ▼
low_quality_flag = tier == "C" or min_confidence < 0.65
    │
    ▼
(tier: str, min_confidence: float, low_quality_flag: bool)
```

---

## Public API (`__init__.py`)

```python
from agent_compliance.pdf_parser import (
    parse_document,      # file → ParseResult
    parse_pdf,           # PDF-only wrapper around parse_document
    docling_to_sections, # ParseResult → list[ParsedSection]
    assess_quality,      # list[ParsedSection] → (tier, confidence, flag)
    ParseResult,         # dataclass
    ParsedSection,       # dataclass
    SectionType,         # enum
)
```

---

## Typical Call Sequence

```python
# 1. Parse the raw document
result = parse_document("procedure.pdf", remove_headers_footers=True)
# result.text        → cleaned markdown
# result.page_texts  → ["page 1 text", "page 2 text", ...]
# result.metadata    → {"heading_hints": [...], "cleanup": {...}}

# 2. Convert to structured sections
sections = docling_to_sections(result)
# sections[0]  → ParsedSection(id="section_preamble_1", type=METADATA, ...)
# sections[1]  → ParsedSection(id="section_objet_2",    type=SCOPE, ...)

# 3. Assess extraction quality
tier, min_conf, low_flag = assess_quality(sections)
# ("A", 1.0, False) for a clean selectable-text PDF
# ("C", 0.5, True)  for a scanned or mostly-empty document
```

---

## Dependency Graph

```
__init__.py
  ├── docling_parser.py
  │     └── _cleanup.py          (no further internal deps)
  ├── docling_adapter.py
  │     ├── docling_parser.py    (imports ParseResult)
  │     ├── parsed_document.py   (imports ParsedSection, SectionType)
  │     └── _page_ranges.py
  │           └── parsed_document.py  (imports ParsedSection)
  └── parsed_document.py         (no internal deps)
```

External consumers (`graph/nodes.py`, `parse.py`) import only from
`__init__.py` and never from submodules directly.

---

## Structural Refactoring

Two large files were split into focused private submodules to reduce per-file responsibility:

| Original file | Lines before | Extracted to | Lines after |
|---|---|---|---|
| `docling_parser.py` | ~701 | `_cleanup.py` | ~290 |
| `docling_adapter.py` | ~504 | `_page_ranges.py` | ~290 |

`__init__.py` was updated to export `ParsedSection` and `SectionType`, which were
previously missing from `__all__` despite being returned by public API functions.

---

## Performance Optimizations

Seven targeted changes were applied across four files. No logic, inputs, or outputs
were changed — only how computation is structured.

### 1. Regex hoisting (`_cleanup.py`)

Eight patterns moved from inside function bodies to module-level constants compiled
once at import time:

```python
_RE_PIPE      = re.compile(r"\|")
_RE_WS        = re.compile(r"\s+")
_RE_SEPARATOR = re.compile(r"[-:]+")
_RE_DIGITS    = re.compile(r"\d+")
_RE_BARS      = re.compile(r"[|\\s]")
_RE_NL_TRAIL  = re.compile(r"[ \t]+\n")
_RE_NL_BLANK  = re.compile(r"\n[ \t]+\n")
_RE_NL_MULTI  = re.compile(r"\n{3,}")
```

Previously these were compiled on every call to `_canonicalize_line()`,
`_remove_repeated_lines_global()`, and `_normalize_spacing()`.

### 2. Per-page canonicalization caching (`_cleanup.py`)

In `_remove_repeated_headers_footers()`, `_canonicalize_line()` was called 3–4×
per line (once for the top-cut scan, once for the bottom-cut scan, once in the
inline sweep, once for removal tracking). Now each page's lines are canonicalized
exactly once into a `page_canonicals` list and all subsequent passes reuse that list:

```python
page_canonicals = [_canonicalize_line(line) for line in lines]
kept_canon = page_canonicals[top_cut:kept_end]
kept = [ln for ln, c in zip(kept_raw, kept_canon) if c not in global_candidates]
kept_set = set(kept)
for line, canon in zip(lines, page_canonicals):
    if canon in global_candidates and line not in kept_set:
        ...
```

### 3. O(n²) → O(n) deduplication (`_cleanup.py`)

`_order_removed_lines()` previously used `not in ordered` (list membership = O(n))
inside a loop over all candidates, giving O(n²) total. Replaced with a parallel
`seen: set[str]` for O(1) membership checks:

```python
seen: set[str] = set()
if original not in seen:
    ordered.append(original)
    seen.add(original)
```

### 4. Regex hoisting (`_page_ranges.py`)

Four patterns moved to module level:

```python
_RE_NUMBERED_HEADING = re.compile(r"^\s*(\d+([.-]\d+)*)\s*[-.)]?\s+\S+")
_RE_MD_PUNCT         = re.compile(r"[`*_~#>\[\](){}]")
_RE_NON_ALNUM        = re.compile(r"[^a-z0-9]+")
_RE_WS               = re.compile(r"\s+")
```

`_is_heading_like()` now calls `_RE_NUMBERED_HEADING.match(text)` instead of
compiling an inline pattern. `_normalize_heading_key()` uses the three hoisted
constants directly.

### 5. Redundant pass removal (`_page_ranges.py`)

`_normalize_heading_key()` previously ran four substitution passes. The intermediate
whitespace-collapse step was immediately overwritten by the `[^a-z0-9]+` substitution
that followed it, making it a no-op. Removed, leaving three passes:

```python
normalized = _RE_MD_PUNCT.sub(" ", normalized)   # strip markdown punctuation
normalized = _RE_NON_ALNUM.sub(" ", normalized)   # collapse non-alphanumeric
normalized = _RE_WS.sub(" ", normalized).strip()  # final whitespace collapse
```

### 6. Regex hoisting (`docling_parser.py`)

Two patterns used inside the `while` loop of `_extract_page1_metadata_fields()`
were hoisted to module level:

```python
_RE_KV_INLINE   = re.compile(r"^([A-Za-zÀ-ÿ][^:]{1,40})\s*:\s*(.+)$")
_RE_KV_KEY_ONLY = re.compile(r"^([A-Za-zÀ-ÿ][^:]{1,40})\s*:\s*$")
```

### 7. Regex hoisting (`docling_adapter.py`)

The heading-split pattern used in `_split_markdown_into_sections()` was moved from
a local variable inside the function to a module-level constant:

```python
_RE_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
```

Previously `re.compile(...)` was called on every invocation of
`_split_markdown_into_sections()`.
