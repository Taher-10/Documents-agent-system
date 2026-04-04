# Agent Compliance — Classification Module: Deep-Dive Analysis

> **Scope:** `agent_compliance/classification/` — `models.py`, `engine.py`, `__init__.py`, cross-referenced with `retrieval_pipeline_deep_dive.md` and `pdf_parser/parsed_document.py`.  
> **Purpose:** Understand every component's responsibility, full data flows, critical transformations, detected bad practices, and improvement recommendations.

---

## Table of Contents

1. [Module Architecture at a Glance](#1-module-architecture-at-a-glance)
2. [Data Contracts — `models.py`](#2-data-contracts--modelspy)
   - 2.1 [Type Aliases & Literals](#21-type-aliases--literals)
   - 2.2 [SectionClassification — the Output Contract](#22-sectionclassification--the-output-contract)
   - 2.3 [Field Validators](#23-field-validators)
3. [Classification Engine — `engine.py`](#3-classification-engine--enginepy)
   - 3.1 [Module-Level Pre-computation](#31-module-level-pre-computation)
   - 3.2 [ClauseInference — Internal Result](#32-clauseinference--internal-result)
   - 3.3 [`derive_domains()`](#33-derive_domains)
   - 3.4 [`derive_doc_type()` / `_derive_doc_type_with_confidence()`](#34-derive_doc_type--_derive_doc_type_with_confidence)
   - 3.5 [`classify_section()` — Public Orchestrator](#35-classify_section--public-orchestrator)
   - 3.6 [`infer_primary_clause()`](#36-infer_primary_clause)
   - 3.7 [`_regex_clause_match()`](#37-_regex_clause_match)
   - 3.8 [`_keyword_clause_match()`](#38-_keyword_clause_match)
   - 3.9 [Helper Utilities](#39-helper-utilities)
4. [Public API — `__init__.py`](#4-public-api--__init__py)
5. [Full End-to-End Data Flow](#5-full-end-to-end-data-flow)
6. [Retrieval Pipeline Integration (retrieval_pipeline_deep_dive.md)](#6-retrieval-pipeline-integration)
7. [Detected Bad Practices](#7-detected-bad-practices)
8. [Improvement Suggestions](#8-improvement-suggestions)

---

## 1. Module Architecture at a Glance

```
agent_compliance/
└── classification/
    ├── __init__.py       ← Public API surface (re-exports only)
    ├── models.py         ← Pydantic output contract (SectionClassification)
    └── engine.py         ← All heuristic logic
          │
          ├── Module-level: CLAUSE_TERM_MAP, TERM_TO_CLAUSE, VOCABULARY_BY_KEY
          │                 CLAUSE_SURFACE_FORMS, _SURFACE_FORM_PATTERNS  (built once at import)
          │
          ├── derive_domains()          ← registry_metadata → List[Domain]
          ├── derive_doc_type()         ← registry_metadata → DocType  (raises if unknown)
          ├── _derive_doc_type_with_confidence() ← same but returns (DocType, float)
          │
          ├── classify_section()        ← PUBLIC ENTRY POINT
          │     ├── derive_domains()
          │     ├── _derive_doc_type_with_confidence()
          │     └── infer_primary_clause()
          │
          └── infer_primary_clause()    ← clause detection pipeline
                ├── _regex_clause_match()   ← fast path: explicit references
                └── _keyword_clause_match() ← slow path: vocabulary + density
                      ├── scan_iso_vocabulary()        [external]
                      ├── _matched_surface_forms_in()
                      ├── _extraction_dampening()
                      └── _normalize_candidate_score()
```

**Execution model:** Entirely **synchronous** — zero I/O, zero async.  
**External dependencies:** `vocabulary.scan_iso_vocabulary`, `document_parser.parsed_document.ParsedSection`.

---

## 2. Data Contracts — `models.py`

### 2.1 Type Aliases & Literals

```python
Domain               = Literal["ISO9001", "ISO14001", "ISO45001"]
DocType              = Literal["policy", "procedure", "record"]
ClassificationMethod = Literal["heuristic", "llm"]
Confidence           = Annotated[float, Field(ge=0.0, le=1.0)]
ClauseId             = Annotated[str, Field(min_length=1)]
```

| Alias | Constraint | Purpose |
|---|---|---|
| `Domain` | 3 allowed values only | Locks ISO standard naming to the exact strings stored in Qdrant `norm_id` payload — prevents silent filter mismatches |
| `DocType` | 3 allowed values | Maps company document types to a normalized triad for downstream compliance rule selection |
| `ClassificationMethod` | `"heuristic"` or `"llm"` | Audit-trail marker — always `"heuristic"` currently (LLM path not yet implemented) |
| `Confidence` | `[0.0, 1.0]` | Enforced by Pydantic `ge`/`le` — prevents out-of-range scores from reaching Qdrant filters |
| `ClauseId` | `min_length=1` | Prevents empty-string clause IDs from silently passing as valid |

---

### 2.2 `SectionClassification` — the Output Contract

The **single output** of the classification pipeline. Maps directly to Qdrant filter fields used by the retrieval pipeline.

```
SectionClassification
│
├── domain              : list[Domain]         # → Qdrant FieldCondition("norm_id", ...)
├── primary_clause      : ClauseId | None      # → Qdrant FieldCondition("clause_id", ...)
├── doc_type            : DocType              # → downstream audit rule selection
├── doc_type_confidence : Confidence           # = 1.0 (exact match) | 0.3 (fallback)
├── confidence          : Confidence           # overall clause-level confidence
├── classification_method: ClassificationMethod# audit trail
├── ambiguity_notes     : str | None           # free-text explanation on low confidence
├── ranked_candidates   : list[tuple[ClauseId, Confidence]]   # non-empty only on ties
└── fallback_reason     : Literal["tie", "no_evidence"] | None
```

**Key design decisions:**
- `extra="forbid"` + `str_strip_whitespace=True` — all unknown fields cause `ValidationError`; leading/trailing whitespace is silently normalized
- `primary_clause=None` is **intentional and meaningful** — it triggers `fallback_reason` and `ranked_candidates`; callers must handle `None` explicitly

---

### 2.3 Field Validators

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Validator                          │ Input           │ Transformation         │
├────────────────────────────────────┼─────────────────┼────────────────────────┤
│ deduplicate_domains_preserving_order │ list[Domain]  │ dict.fromkeys() → list  │
│   e.g. ["ISO9001","ISO14001","ISO9001"] → ["ISO9001","ISO14001"]             │
├────────────────────────────────────┼─────────────────┼────────────────────────┤
│ validate_primary_clause            │ str | None      │ Split on "." → verify  │
│   checks: all parts are digits     │                 │ (HLS clause 4–10 only) │
│   and first part ∈ {4,5,6,7,8,9,10}│                │ raises ValueError if bad│
├────────────────────────────────────┼─────────────────┼────────────────────────┤
│ normalize_ambiguity_notes          │ str | None      │ "" → None              │
│   prevents empty strings from      │                 │ (cleaner downstream    │
│   reaching logging systems         │                 │ logging)               │
└─────────────────────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> `validate_primary_clause` only validates **format** (digits, HLS range). It does **not** verify the clause exists in `CLAUSE_TERM_MAP`. A regex-matched clause like `"6.5"` would pass validation but silently produce no keyword evidence because `"6.5"` has no entry in the map.

---

## 3. Classification Engine — `engine.py`

### 3.1 Module-Level Pre-computation

This is the most performance-critical block — executed **once at import time**, not per call:

```
SYSTEME_TO_DOMAIN: {"Q" → "ISO9001", "E" → "ISO14001", "S" → "ISO45001"}

DOC_TYPE_HINTS: {
    "policy"    : ("policy", "politique", "charte", "manual", "manuel")
    "procedure" : ("procedure", "procédure", "process", ..., "sop")
    "record"    : ("record", "enregistrement", "form", ..., "job description")
}

TITLE_CLAUSE_PATTERN  ← regex for explicit clause refs in titles (e.g. "8.7 Maîtrise...")
BODY_CLAUSE_PATTERN   ← same for body (limited to first 500 chars)

CLAUSE_TERM_MAP: {"4.1": ("context of the organization", ...), ...}
                  26 clauses covered, EN + FR terms

TERM_TO_CLAUSE: flattened inverse of CLAUSE_TERM_MAP (term string → clause id)

VOCABULARY_BY_KEY: merged EN + FR vocabulary from shared scanner (lowercased)

CLAUSE_SURFACE_FORMS: for each clause, a tuple of all surface forms
                       (canonical terms + vocabulary "forms" list, deduplicated & sorted)

_SURFACE_FORM_PATTERNS: for each clause → list of compiled re.Pattern objects
                         Pattern = r"\b" + re.escape(form) + r"\b"  (word-boundary guarded)
```

**Why module-level?**  
`_SURFACE_FORM_PATTERNS` can have hundreds of compiled regexes. Building them once at import (O(1) per classification call) vs. per-call (O(N) per classification call) is the right call for a high-throughput pipeline.

---

### 3.2 `ClauseInference` — Internal Result

A `frozen` dataclass — internal only, never exposed through the public API:

```python
@dataclass(frozen=True)
class ClauseInference:
    primary_clause    : str | None
    confidence        : float
    ambiguity_notes   : str | None = None
    ranked_candidates : list[tuple[str, float]] = field(default_factory=list)
    fallback_reason   : str | None = None
```

> [!NOTE]
> `ClauseInference` is **not validated** (no Pydantic) — `confidence` can technically be any float. The validation boundary is at `SectionClassification` where Pydantic enforces `[0.0, 1.0]`. This is acceptable since `ClauseInference` is private.

---

### 3.3 `derive_domains()`

**Responsibility:** Map the database `systeme` field to a list of ISO standard identifiers.

```
Input:
    registry_metadata : Mapping[str, Any]
         │
         ├─ systeme = str(registry_metadata.get("systeme", "")).upper()
         │   e.g. "QES" or "Q" or "qs"  (case-insensitive)
         │
         ├─ for char in systeme:
         │       if char in {"Q","E","S"}:
         │           append SYSTEME_TO_DOMAIN[char]  (no duplicates)
         │
         ├─ if domains == []: raise ValueError("Unable to derive...")
         │
         └─► Output: list[Domain]
                      e.g. "QES" → ["ISO9001", "ISO14001", "ISO45001"]
                           "Q"   → ["ISO9001"]
                           "QQ"  → ["ISO9001"]  (deduplication by in-place check)
```

**Important transformations:**
- `.upper()` — normalizes input case before mapping
- Iterates character-by-character — supports multi-standard documents naturally
- Built-in deduplication avoids duplicate domains before `SectionClassification` validator runs

---

### 3.4 `derive_doc_type()` / `_derive_doc_type_with_confidence()`

**Responsibility:** Map document registry metadata to the `policy / procedure / record` triad.

```
_derive_doc_type_with_confidence():
─────────────────────────────────
Input:
    registry_metadata : Mapping[str, Any]
         │
         ├─ metadata_blob = " ".join([
         │       str(metadata.get("types_documents", "") or ""),
         │       str(metadata.get("domaines_documents", "") or ""),
         │       str(metadata.get("sous_domaine_document", "") or ""),
         │   ]).lower()
         │   e.g. "procédure qualite "  (concatenated then lowercased)
         │
         ├─ for doc_type in {"policy", "procedure", "record"}:
         │       for hint in DOC_TYPE_HINTS[doc_type]:
         │           if hint in metadata_blob:
         │               return (doc_type, 1.0)  ← exact substring match
         │
         └─► if no match: return ("procedure", 0.3)  ← FALLBACK

derive_doc_type() [public]:
───────────────────────────
    calls _derive_doc_type_with_confidence()
    if confidence < 1.0: raise ValueError(...)  ← strict — rejects fallback
    else: return doc_type
```

**Confidence semantics:**

| confidence | Meaning | Source |
|---|---|---|
| `1.0` | Exact hint substring found in metadata blob | Registry metadata is reliable |
| `0.3` | No hint matched; fallback to `"procedure"` | Registry incomplete |

> [!WARNING]
> The `derive_doc_type()` public function **raises** on fallback, while `_derive_doc_type_with_confidence()` **returns** the fallback. Only `classify_section()` uses the confidence-returning version. External callers using `derive_doc_type()` directly will get a `ValueError` on unknown document types instead of a graceful fallback. This split behavior is inconsistent and easy to misuse.

---

### 3.5 `classify_section()` — Public Orchestrator

**The single public entry point** for classifying a parsed section.

```
Input:
    section           : ParsedSection | Mapping[str, Any]
    registry_metadata : Mapping[str, Any]
         │
         ├─ [1] derive_domains(registry_metadata)
         │       → domains: list[Domain]
         │
         ├─ [2] _derive_doc_type_with_confidence(registry_metadata)
         │       → (doc_type: DocType, doc_type_confidence: float)
         │
         ├─ [3] _languages_to_scan(section, registry_metadata)
         │       → languages: list[str]   (["EN"] | ["FR"] | ["EN","FR"])
         │
         ├─ [4] _section_float(section, "extraction_confidence", default=1.0)
         │       → extraction_confidence: float
         │
         ├─ [5] infer_primary_clause(section, domains, languages, extraction_confidence)
         │       → clause_inference: ClauseInference
         │
         └─► SectionClassification(
                 domain               = domains,
                 primary_clause       = clause_inference.primary_clause,
                 doc_type             = doc_type,
                 doc_type_confidence  = doc_type_confidence,
                 confidence           = clause_inference.confidence,
                 classification_method= "heuristic",
                 ambiguity_notes      = clause_inference.ambiguity_notes,
                 ranked_candidates    = clause_inference.ranked_candidates,
                 fallback_reason      = clause_inference.fallback_reason,
             )
```

---

### 3.6 `infer_primary_clause()`

**Responsibility:** Two-stage clause detection — fast regex path first, vocabulary keyword path as fallback.

```
Input:
    section              : ParsedSection | Mapping[str, Any]
    domains              : list[Domain]
    languages            : list[str]
    extraction_confidence: float
         │
         ├─ title    = _section_value(section, "title")
         ├─ raw_text = _section_value(section, "raw_text")
         │
         ├─ [Fast path] _regex_clause_match(title, raw_text)
         │       if result is not None → return immediately (0.90–0.95 confidence)
         │
         └─ [Slow path] _keyword_clause_match(title, raw_text, domains, languages,
                                              extraction_confidence)
                 → ClauseInference (0.0–0.8 confidence)
```

**Decision tree:**

```
                     infer_primary_clause()
                            │
               ┌────────────┴───────────┐
           title has                body[0:500] has
         clause ref?               clause ref?
            YES → 0.95 conf           YES → 0.90 conf
            NO  ─────────────────────────────────┐
                                                  │
                                    keyword_clause_match()
                                            │
                        ┌───────────────────┼────────────────────┐
                   empty text            hits found          no hits
                    → 0.0                    │                → 0.0
                   no_evidence        density scoring        no_evidence
                                            │
                               ┌────────────┴────────────┐
                            tie (=score)             clear winner
                            → None, 0.5               → clause_id
                            ranked_candidates          confidence: 0.5 or 0.8
                            fallback_reason="tie"      dampened by OCR quality
```

---

### 3.7 `_regex_clause_match()`

**Responsibility:** Detect explicit clause references in text — highest-priority, highest-confidence path.

```
Input:
    title    : str
    raw_text : str
         │
         ├─ [Path 1] TITLE_CLAUSE_PATTERN.search(title)
         │   Pattern: r"^\s*(?:clause|section|chapitre|chapter|article)\s+(4..10...)
         │             OR ^\s*(4..10...)" (bare number at start)
         │   Match:
         │     title = "8.7 Maîtrise des éléments..."
         │     group extraction: next(group for group in match.groups() if group)
         │     → "8.7"
         │   Output: ClauseInference(primary_clause="8.7", confidence=0.95,
         │                           ambiguity_notes="Explicit clause reference found in section title: 8.7.")
         │
         ├─ [Path 2] BODY_CLAUSE_PATTERN.search(raw_text[:500])
         │   Pattern: requires "clause|section|..." prefix (stricter than title)
         │   Match:
         │     body = "...rattachée à la clause 8.7."
         │     → "8.7"
         │   Output: ClauseInference(primary_clause="8.7", confidence=0.90, ...)
         │
         └─ Neither matched → return None  (triggers keyword path)
```

**Critical detail — body window `[:500]`:**
Only the first 500 characters of body text are scanned. This is a deliberate precision trade-off: later body text is more likely to mention clauses in cross-reference context ("see clause 9.1 for more details") rather than as the section's actual topic.

---

### 3.8 `_keyword_clause_match()`

**Responsibility:** Vocabulary-based clause inference when no explicit clause reference exists. The most complex function in the module.

```
Input:
    title               : str
    raw_text            : str
    domains             : list[Domain]
    languages           : list[str]
    extraction_confidence: float
         │
         ├─ [Step 0] text = f"{title}\n{raw_text}".strip()
         │   if empty: → ClauseInference(None, 0.0, fallback_reason="no_evidence")
         │
         ├─ [Step 1] ISO Vocabulary scan (per language)
         │   clause_hits: dict[str, set[str]] = defaultdict(set)
         │   for language in languages:
         │       for hit in scan_iso_vocabulary(text, language, norm_filter=domains):
         │           clause = TERM_TO_CLAUSE.get(hit.lower())
         │           if clause is not None:
         │               clause_hits[clause].add(hit)
         │   e.g. "audit interne" → TERM_TO_CLAUSE["audit interne"] → "9.2"
         │        "revue de direction" → "9.3"
         │
         │   if clause_hits empty → ClauseInference(None, 0.0, fallback_reason="no_evidence")
         │
         ├─ [Step 2] Surface form density scoring
         │   title_lower = title.lower()
         │   body_lower  = raw_text.lower()
         │   for each clause with hits:
         │       title_matches = _matched_surface_forms_in(title_lower, clause)
         │       body_matches  = _matched_surface_forms_in(body_lower, clause)
         │       density_scores[clause] = len(title_matches) * TITLE_WEIGHT + len(body_matches)
         │                                                      ↑ TITLE_WEIGHT = 3
         │       density_terms[clause]  = title_matches | body_matches
         │
         ├─ [Step 3] Rank & tie detection
         │   ranked = sorted([(clause, score, terms)], key=(-score, clause))
         │   top_clause, top_score, top_terms = ranked[0]
         │   tied_clauses = [c for c, s, _ in ranked if s == top_score]
         │
         ├─ [Step 4] Confidence computation
         │   evidence_count = len(density_terms[top_clause])
         │   base_confidence = 0.8 if evidence_count >= 3 else 0.5
         │   confidence = base_confidence * _extraction_dampening(extraction_confidence)
         │       _extraction_dampening():
         │           if extraction_confidence >= 0.70: → 1.0  (no penalty)
         │           else:  → 0.5 + 0.5 * (extraction_confidence / 0.70)  (linear ramp)
         │           e.g. extraction_confidence=0.35: 0.5 + 0.5*(0.35/0.70) = 0.75 dampen factor
         │
         ├─ [Step 5a: TIE path]
         │   if len(tied_clauses) > 1:
         │       ranked_candidates = [(clause, _normalize_candidate_score(score, ranked))
         │                            for clause, score, _ in ranked if clause in tied_clauses]
         │       return ClauseInference(
         │           primary_clause=None, confidence=confidence,
         │           ambiguity_notes="Keyword evidence is split across clauses ...",
         │           ranked_candidates=ranked_candidates,
         │           fallback_reason="tie",
         │       )
         │
         └─ [Step 5b: WINNER path]
             ambiguity_notes = None
             if confidence < 0.8:
                 ambiguity_notes = f"Low keyword density for clause {top_clause}..."
             return ClauseInference(
                 primary_clause=top_clause,
                 confidence=confidence,
                 ambiguity_notes=ambiguity_notes,
             )
```

#### Confidence Score Reference Table

| Condition | base_confidence | dampen factor | final confidence |
|---|---|---|---|
| ≥3 evidence terms, clean OCR (≥0.70) | 0.8 | 1.0 | **0.80** |
| <3 evidence terms, clean OCR | 0.5 | 1.0 | **0.50** |
| ≥3 evidence terms, degraded OCR (0.35) | 0.8 | 0.75 | **0.60** |
| <3 evidence terms, degraded OCR (0.35) | 0.5 | 0.75 | **0.375** |
| Regex match in title | — | — | **0.95** |
| Regex match in body | — | — | **0.90** |
| Tie / no evidence | — | — | **0.0 – 0.5** |

---

### 3.9 Helper Utilities

#### `_languages_to_scan()`

```
Input: section, registry_metadata
    → lang = registry_metadata.get("langue", "").upper()
             OR section.langue.upper()
    if lang in {"EN", "FR"}: return [lang]       ← single-language scan
    else:                      return ["EN","FR"] ← dual scan (slower, more recall)
```

> [!NOTE]
> Dual-language scanning doubles the ISO vocabulary scan work. When `langue` is unknown or missing, **both** EN and FR vocabularies are scanned. This is a recall-favoring design — acceptable for compliance where missed evidence is more dangerous than extra computation.

#### `_extraction_dampening()`

```
Input: extraction_confidence: float
    if >= 0.70: return 1.0                              ← no penalty
    else:       return 0.5 + 0.5 * (conf / 0.70)       ← linear ramp down to 0.5

e.g.:
    conf=0.70 → 1.0 (threshold)
    conf=0.35 → 0.75 (halfway between 0.5 and 1.0)
    conf=0.0  → 0.5  (floor: OCR-failed pages never get 0 keyword confidence)
```

The floor at `0.5` ensures even fully degraded OCR text can still produce a tiebreaker signal — it is never treated as entirely unreliable.

#### `_normalize_candidate_score()`

```
Input: score: float, ranked: list[tuple[str, float, list[str]]]
    max_score = ranked[0][1]
    if max_score <= 0: return 0.0
    return score / max_score    ← normalize to [0, 1] relative to best candidate
```

Used only for `ranked_candidates` on tie. Normalizes raw density counts to proportional scores for the output contract.

#### `_matched_surface_forms_in()`

```
Input: text_lower: str, clause: str
    return {
        form
        for form, pattern in zip(CLAUSE_SURFACE_FORMS[clause], _SURFACE_FORM_PATTERNS[clause])
        if pattern.search(text_lower)
    }
```

Scans **pre-compiled** patterns (module-level `_SURFACE_FORM_PATTERNS`) — O(1) per call. Returns the **set of matching form strings** (not counts) — so `density_scores` counts unique surface forms, not total occurrences.

---

## 4. Public API — `__init__.py`

```python
from classification.engine import classify_section, derive_doc_type, derive_domains
from classification.models import ClassificationMethod, DocType, Domain, SectionClassification
```

**Exported surface:**

| Symbol | Type | Role |
|---|---|---|
| `classify_section` | function | Primary entry point — classifies one section |
| `derive_domains` | function | Exposed for standalone domain derivation |
| `derive_doc_type` | function | Exposed for standalone doc-type derivation (raises on unknown) |
| `SectionClassification` | Pydantic model | Output contract type |
| `Domain`, `DocType`, `ClassificationMethod` | Literal type aliases | For callers to type-check against |

> [!NOTE]
> `infer_primary_clause`, `ClauseInference`, `_regex_clause_match`, `_keyword_clause_match` are **not** exported. They can only be tested by importing from `classification.engine` directly — which the test file does not do consistently.

---

## 5. Full End-to-End Data Flow

### Worked Example

**Document:** `"8.7 Maîtrise des éléments de sortie non conformes"` (section title)  
**Registry:** `systeme="Q"`, `types_documents="PROCÉDURE"`, `langue="FR"`

```
════════════════════════════════════════════════════════════════════════
 ENTRY: classify_section(section, registry_metadata)
════════════════════════════════════════════════════════════════════════

registry_metadata = {
    "systeme": "Q",
    "types_documents": "PROCÉDURE",
    "domaines_documents": "QUALITE",
    "langue": "FR",
}
section.title              = "8.7 Maîtrise des éléments de sortie non conformes"
section.raw_text           = "Cette section couvre aussi la compétence..."
section.extraction_confidence = 0.98

────────────────────────────────────────────────────────────────────────
 STEP 1 — derive_domains()
────────────────────────────────────────────────────────────────────────

 systeme = "Q" → chars = ["Q"]
 SYSTEME_TO_DOMAIN["Q"] = "ISO9001"
 → domains = ["ISO9001"]

────────────────────────────────────────────────────────────────────────
 STEP 2 — _derive_doc_type_with_confidence()
────────────────────────────────────────────────────────────────────────

 metadata_blob = "procédure qualite ".lower() = "procédure qualite "
 DOC_TYPE_HINTS["procedure"] contains "procédure"
 "procédure" in "procédure qualite " → True
 → (doc_type="procedure", doc_type_confidence=1.0)

────────────────────────────────────────────────────────────────────────
 STEP 3 — _languages_to_scan()
────────────────────────────────────────────────────────────────────────

 registry_metadata["langue"] = "FR" → .upper() = "FR"
 "FR" in {"EN","FR"} → True
 → languages = ["FR"]

────────────────────────────────────────────────────────────────────────
 STEP 4 — _section_float(section, "extraction_confidence", default=1.0)
────────────────────────────────────────────────────────────────────────

 float(0.98) = 0.98
 → extraction_confidence = 0.98

────────────────────────────────────────────────────────────────────────
 STEP 5 — infer_primary_clause()
────────────────────────────────────────────────────────────────────────

 title    = "8.7 Maîtrise des éléments de sortie non conformes"
 raw_text = "Cette section couvre aussi la compétence..."

  ▸ _regex_clause_match(title, raw_text)
        TITLE_CLAUSE_PATTERN.search("8.7 Maîtrise...")
        Pattern: r"^\s*((?:4|5|6|7|8|9|10)(?:\.\d+)*)\b"
        Match group: "8.7"
        → ClauseInference(
              primary_clause = "8.7",
              confidence     = 0.95,
              ambiguity_notes= "Explicit clause reference found in section title: 8.7.",
          )
        → RETURNS (skips keyword path entirely)

════════════════════════════════════════════════════════════════════════
 OUTPUT: SectionClassification
════════════════════════════════════════════════════════════════════════

 domain               = ["ISO9001"]
 primary_clause       = "8.7"
 doc_type             = "procedure"
 doc_type_confidence  = 1.0
 confidence           = 0.95
 classification_method= "heuristic"
 ambiguity_notes      = "Explicit clause reference found in section title: 8.7."
 ranked_candidates    = []
 fallback_reason      = None
```

---

### Keyword Path Example (No Explicit Clause Reference)

**Input:** `title="Audit interne"`, `raw_text="Le programme d'audit interne définit le calendrier d'audit..."`, lang=`"FR"`, extraction_confidence=`0.97`

```
STEP 5 — infer_primary_clause()
 ▸ _regex_clause_match → None (no "8.7..." pattern in title; no "clause X" in body)
 ▸ _keyword_clause_match()

    text = "Audit interne\nLe programme d'audit interne définit..."

    [Step 1] scan_iso_vocabulary(text, "FR", ["ISO9001"])
        "audit interne" surface form → word-boundary match ✓
        hit: "audit interne"
        TERM_TO_CLAUSE["audit interne"] = "9.2"
        clause_hits = {"9.2": {"audit interne"}}

    [Step 2] Surface form density
        CLAUSE_SURFACE_FORMS["9.2"] includes "audit interne", "audit de première partie", ...
        title_lower = "audit interne"
        _matched_surface_forms_in(title_lower, "9.2"):
            "audit interne" pattern → match ✓
            → title_matches = {"audit interne"}
        body_lower = "le programme d'audit interne définit..."
        _matched_surface_forms_in(body_lower, "9.2"):
            "audit interne" → match ✓
            → body_matches = {"audit interne"}
        density_scores["9.2"] = 1 * 3 + 1 = 4
        density_terms["9.2"]  = {"audit interne"}   ← 1 unique term

    [Step 3] Rank
        ranked = [("9.2", 4, ["audit interne"])]
        top_clause = "9.2", top_score = 4
        tied_clauses = ["9.2"]   ← no tie

    [Step 4] Confidence
        evidence_count = 1 < 3 → base_confidence = 0.5
        _extraction_dampening(0.97) = 1.0 (0.97 >= 0.70)
        confidence = 0.5 * 1.0 = 0.5
        
    [Step 5b] Winner path
        confidence < 0.8 → ambiguity_notes = "Low keyword density for clause 9.2; ..."
        → ClauseInference(primary_clause="9.2", confidence=0.5, ambiguity_notes="Low...")

OUTPUT: SectionClassification(
    primary_clause = "9.2",
    confidence     = 0.5,
    ambiguity_notes= "Low keyword density for clause 9.2; matched terms: audit interne.",
)
```

**Wait — tests say `confidence == 0.8` for the "Audit interne" test case.** This is because the test body contains *multiple* audit references:  
`"Le programme d'audit interne définit le calendrier d'audit, les audits internes et les critères de l'audit de première partie."` — `"audit de première partie"` is also a surface form for `9.2`, giving 2 body matches + 1 title match = 4 density, **2 unique terms** still < 3 → `0.5`. But tests assert `0.8`.

> [!IMPORTANT]
> The test `test_keyword_density_sets_high_confidence` asserts `confidence == 0.8` and `ambiguity_notes is None`. For that to happen, `evidence_count >= 3`. The body contains `"audit interne"`, `"les audits internes"`, and `"audit de première partie"` — **3 distinct surface form matches** → `base_confidence = 0.8`. This makes the test coherent, but the threshold `3` is a **magic number** with no documentation explaining _why_ 3 terms is the boundary between "low" and "high" density.

---

## 6. Retrieval Pipeline Integration

The classification module is a **pre-retrieval filter builder**. Its output feeds directly into `rag/retrival/` via `SectionClassification` fields:

```
SectionClassification.domain          → List[Domain]
                                           │
                                           └─► build_norm_filter(norm_filter=domains, ...)
                                                   ├─ len==1 → FieldCondition("norm_id", MatchValue("ISO9001"))
                                                   └─ len>1  → FieldCondition("norm_id", MatchAny([...]))
                                                   → Qdrant Prefetch.filter=

SectionClassification.primary_clause  → ClauseId | None
                                           │
                                           └─► If not None: additional FieldCondition("clause_id", ...)
                                               (narrows Qdrant search to matching clause chunks only)
```

> [!WARNING]
> **The `domain` values must match exactly** the `norm_id` values stored in Qdrant at ingestion time. `"ISO9001"` (no space, no colon) is the only valid format. The `retrieval_pipeline_deep_dive.md` § 5 explicitly calls this out:  
> _"norm_id | "ISO9001" (no spaces, no colon) | Ingestion pipeline | build_norm_filter()"_  
> The `Domain` Literal enforces this at the Pydantic level — any deviation raises `ValidationError` before reaching Qdrant.

### Score Lifecycle Integration

The classification result does **not** carry a score into the retrieval pipeline. Scores are produced inside retrieval:

```
Classification output   →   Qdrant filter   →   RRF score   →   Rerank score
(domain, clause)        ←── scopes corpus   ←── fused rank  ←── cross-encoder logit
```

The `confidence` field from `SectionClassification` is a **classification-side signal only** — it is not forwarded to the retrieval pipeline or used in RRF/rerank scoring.

---

## 7. Detected Bad Practices

### BP-1 — Hardcoded Confidence Thresholds with No Documentation

**Location:** `engine.py` lines 56–58, 347, 396

```python
_EXTRACTION_CONFIDENCE_THRESHOLD = 0.70  # line 56
_DOC_TYPE_FALLBACK_CONFIDENCE = 0.3      # line 58
base_confidence = 0.8 if evidence_count >= 3 else 0.5  # line 347
```

All three thresholds (`0.70`, `0.3`, `0.8`, `0.5`, `3`) are magic numbers. There is no comment explaining:
- Why `0.70` was chosen as the OCR quality boundary
- Why `3` terms is the boundary for high vs. low density
- Why `0.3` is the doc-type fallback confidence
- Why `0.8` vs `0.5` (not `0.75` vs `0.4`, for example)

**Risk:** Any calibration change requires reading the code to understand the intent, risking accidental drift in the confidence scale semantics.

---

### BP-2 — `ClassificationMethod` Literal Has a Dead Value

**Location:** `models.py` line 11

```python
ClassificationMethod = Literal["heuristic", "llm"]
```

`"llm"` is declared in the contract but `engine.py` **always** sets `classification_method="heuristic"` (line 238). There is no LLM classification code anywhere in the module. The `"llm"` value is unreachable dead code in the current implementation.

**Risk:** Callers reading the type definition may assume LLM classification is a meaningful code path and build logic around it.

---

### BP-3 — `derive_doc_type()` vs `_derive_doc_type_with_confidence()` Behavioral Split

**Location:** `engine.py` lines 191–215

```python
def derive_doc_type(registry_metadata):
    doc_type, confidence = _derive_doc_type_with_confidence(registry_metadata)
    if confidence < 1.0:
        raise ValueError(...)  # raises on fallback
    return doc_type

def _derive_doc_type_with_confidence(registry_metadata):
    ...
    return _DOC_TYPE_FALLBACK, _DOC_TYPE_FALLBACK_CONFIDENCE  # returns fallback silently
```

The **public function raises** while the **private function returns a fallback**. Both are exported: `derive_doc_type` is in `__all__` (via `__init__.py`). A caller using the public API gets an exception; `classify_section()` internally uses the private version and gets a graceful fallback.

**Risk:** External callers trying to handle unknown doc types must catch `ValueError` even though the engine itself handles the same case gracefully for classification.

---

### BP-4 — Import Path Inconsistency Between Engine and Tests

**Location:** `engine.py` line 11 vs `tests/test_classification_engine.py` lines 7–9

```python
# engine.py imports:
from classification.models import ...          # relative-style (no "agent_compliance." prefix)
from document_parser.parsed_document import ParsedSection   # wrong package name

# tests import:
from agent_compliance.pdf_parser.parsed_document import ParsedSection  # correct
from agent_compliance.classification import ...                         # correct
```

`engine.py` imports `document_parser.parsed_document` (non-existent package name) while the actual package is `agent_compliance.pdf_parser`. This was fixed at the test level but the source file retains the stale import path that requires a sys.path patch or editable install to work.

**Risk:** Running `engine.py` in isolation fails with `ModuleNotFoundError`. The module only works when `agent_compliance` is installed as a package (via `pyproject.toml` editable install). This is fragile for contributors.

---

### BP-5 — `ClauseInference.fallback_reason` Type is `str | None`, Not Narrowed

**Location:** `engine.py` lines 166–170

```python
@dataclass(frozen=True)
class ClauseInference:
    fallback_reason: str | None = None  # ← plain str
```

`SectionClassification.fallback_reason` in `models.py` is:
```python
fallback_reason: Literal["tie", "no_evidence"] | None  # ← validated Literal
```

`ClauseInference` (internal) allows any string while the external contract enforces a `Literal`. The mapping is implicit — if `_keyword_clause_match()` ever produces a new reason string (e.g. `"vocabulary_error"`), Pydantic will silently coerce or raise at the `SectionClassification(...)` constructor call.

**Risk:** Regression in internal reason strings will produce runtime `ValidationError` at the output boundary with no static type checker warning at the source.

---

### BP-6 — Body Window `[:500]` is a Silent Precision Trade-off

**Location:** `engine.py` line 279

```python
body_window = raw_text[:500]
body_match = BODY_CLAUSE_PATTERN.search(body_window)
```

The 500-character window is hardcoded with no configuration and no documentation of why 500 was chosen. For very dense documents where the first clause reference appears after a long preamble, this silently misses valid matches and falls through to the less-accurate keyword path.

---

### BP-7 — `CLAUSE_TERM_MAP` Gaps (Missing HLS Clauses)

**Location:** `engine.py` lines 72–130

The HLS (High Level Structure) has clauses 4 through 10. `CLAUSE_TERM_MAP` is missing:

| Missing Clause | HLS Topic |
|---|---|
| `5.4` | Worker participation and consultation (ISO45001 specific) |
| `6.1.2` | Hazard identification (ISO45001 specific) |
| `8.2` | Emergency preparedness and response |
| `8.3` | Management of change (ISO14001/ISO45001) |
| `8.6` | Release of products and services (ISO9001) |
| `9.1.2` | Customer satisfaction (ISO9001) |
| `9.1.3` | Analysis and evaluation |
| `10.1` | General improvement |

Any section covering these topics will fall to `fallback_reason="no_evidence"` even when the content explicitly discusses them. This is a **recall gap**.

---

### BP-8 — `density_scores` Counts Unique Forms, Not Occurrences

**Location:** `engine.py` lines 330–334

```python
density_scores[clause] = len(title_matches) * TITLE_WEIGHT + len(body_matches)
density_terms[clause]  = title_matches | body_matches
```

`_matched_surface_forms_in()` returns a **set** — "audit interne" appearing 5 times in the body counts as 1. Two different forms each appearing once ("audit interne" + "audit de première partie") also count as 2. This means repetition of a single phrase does not increase confidence, which is correct for deduplication but may undercount sections with a single highly-repeated term indicating very strong association.

---

## 8. Improvement Suggestions

### S-1 — Externalize All Thresholds to a `ClassifierConfig` Dataclass

```python
@dataclass(frozen=True)
class ClassifierConfig:
    """Tuneable parameters for the heuristic classifier."""
    extraction_confidence_threshold: float = 0.70
    """OCR quality cutoff below which keyword confidence is dampened."""
    high_density_term_count: int = 3
    """Minimum unique surface form matches for high-confidence (0.8) assignment."""
    title_weight: int = 3
    """Title match multiplier vs body match (1× each)."""
    doc_type_fallback_confidence: float = 0.3
    """Confidence assigned when no doc-type hint matches registry metadata."""
    body_clause_window: int = 500
    """Characters from section body scanned for explicit clause references."""
```

Pass `config: ClassifierConfig = ClassifierConfig()` into `classify_section()` and `infer_primary_clause()`. This makes calibration visible, testable, and configurable without code changes.

---

### S-2 — Narrow `ClauseInference.fallback_reason` to Match the Output Contract

```python
# Before
fallback_reason: str | None = None

# After
from typing import Literal
fallback_reason: Literal["tie", "no_evidence"] | None = None
```

This catches mismatches between the internal dataclass and the external Pydantic model at **type-check** time rather than at runtime.

---

### S-3 — Unify `derive_doc_type()` API

Replace the two-function split with a single function that accepts a `strict` parameter:

```python
def derive_doc_type(
    registry_metadata: Mapping[str, Any],
    *,
    strict: bool = False,
) -> DocType:
    """
    Args:
        strict: If True, raises ValueError when no hint matches.
                If False (default), returns the fallback 'procedure' with
                confidence stored on the returned object via a named tuple.
    """
    doc_type, confidence = _derive_doc_type_with_confidence(registry_metadata)
    if strict and confidence < 1.0:
        raise ValueError(...)
    return doc_type
```

Alternatively, return a `NamedTuple(doc_type, confidence)` from the public function and deprecate `derive_doc_type()`.

---

### S-4 — Remove or Implement `"llm"` ClassificationMethod

Either:
- Remove `"llm"` from `ClassificationMethod` until an LLM path is implemented (simplest, safe)
- Add a `TODO` comment: `Literal["heuristic", "llm"]  # "llm" reserved — not yet implemented`
- Implement a thin LLM classification path that `classify_section()` dispatches to when regex + keyword both return `confidence < 0.5`

The third option is the most valuable for genuinely ambiguous sections (empty titles, pure scanned images converted to garbled OCR text).

---

### S-5 — Extend `CLAUSE_TERM_MAP` for Missing HLS Clauses

Priority additions (highest recall impact for ISO45001 documents):

```python
CLAUSE_TERM_MAP["5.4"]   = ("worker participation", "consultation", "participation des travailleurs")
CLAUSE_TERM_MAP["8.2"]   = ("emergency preparedness", "plan d'urgence", "préparation aux situations d'urgence")
CLAUSE_TERM_MAP["8.3"]   = ("management of change", "gestion des changements", "maîtrise des modifications")  
CLAUSE_TERM_MAP["9.1.2"] = ("customer satisfaction", "satisfaction du client", "mesure de la satisfaction")
CLAUSE_TERM_MAP["10.1"]  = ("general improvement", "amélioration générale")
```

---

### S-6 — Document and Optionally Expand the `[:500]` Body Window

Short-term: add a constant and a docstring explaining the decision:

```python
_BODY_CLAUSE_SCAN_WINDOW = 500
"""
Characters from the start of section body text scanned for explicit clause references.
Rationale: Early body text (intro sentences) contains the section's own clause reference.
Later references are typically cross-references to other clauses (e.g., "see clause 9.1").
Scanning the full body would produce false positives.
"""
```

Long-term: Use `_BODY_CLAUSE_SCAN_WINDOW` from `ClassifierConfig` (see S-1).

---

### S-7 — Persist `doc_type_confidence` Path in `derive_domains()` Error Message

```python
# Current:
raise ValueError(
    "Unable to derive classification.domain from registry metadata field 'systeme'."
)

# Improved:
raise ValueError(
    f"Unable to derive classification.domain from registry metadata field 'systeme'. "
    f"Got: {systeme!r}. Expected one or more of: {list(SYSTEME_TO_DOMAIN.keys())}."
)
```

This makes debugging production failures significantly faster without changing behaviour.

---

### S-8 — Add Occurrence-Weighted Density Scoring as Optional Mode

The current density model counts **unique** surface forms. For compliance documents, a single term repeated throughout (e.g., "audit interne" 8× in an audit procedure) is a strong signal that should be reflected in confidence. Suggestion:

```python
# Current: unique form count
density_scores[clause] = len(title_matches) * TITLE_WEIGHT + len(body_matches)

# Proposed: occurrence count (configurable via ClassifierConfig.density_mode)
if config.density_mode == "occurrence":
    title_hits = sum(len(pattern.findall(title_lower)) 
                     for pattern in _SURFACE_FORM_PATTERNS[clause])
    body_hits  = sum(len(pattern.findall(body_lower))
                     for pattern in _SURFACE_FORM_PATTERNS[clause])
    density_scores[clause] = title_hits * TITLE_WEIGHT + body_hits
```

This would be opt-in (default stays `"unique"`) for backward compatibility.

---

## Summary: Bad Practices at a Glance

| # | Location | Severity | Category |
|---|---|---|---|
| BP-1 | Multiple thresholds | 🟡 Medium | Maintainability — magic numbers |
| BP-2 | `"llm"` in ClassificationMethod | 🟡 Medium | Dead code / misleading contract |
| BP-3 | `derive_doc_type()` vs private | 🟠 High | API inconsistency |
| BP-4 | Import path in `engine.py` | 🔴 Critical | Fragile module resolution |
| BP-5 | `ClauseInference.fallback_reason` type | 🟡 Medium | Type safety gap |
| BP-6 | `[:500]` body window | 🟢 Low | Silent precision trade-off |
| BP-7 | Missing HLS clauses in CLAUSE_TERM_MAP | 🟠 High | Recall gap for ISO45001 |
| BP-8 | Unique-form density scoring | 🟢 Low | Mild signal loss |
