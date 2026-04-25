## M2.3 — Data Models

**Scope:** `graph/models.py`

**Prerequisite:** M2.2 done (`ClauseRecord` shape stable).

**Goal:** All dataclasses and Pydantic schemas in one place before building any nodes. Everything downstream imports from here.

### `graph/models.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel
from agent_compliance.retrieval.clause_store import ClauseRecord

# ── Domain objects ────────────────────────────────────────────────────────────

@dataclass
class MatchedClause:
    norm_id:        str
    clause_number:  str
    clause_title:   str
    evidence_text:  str   # verbatim quote from section.raw_text
    status:         Literal["COVERED", "PARTIAL", "NON_CONFORMING"]
    advice:         str   # specific and actionable — not generic

@dataclass
class SectionMatch:
    section_id:      str
    section_type:    str
    title:           str
    matched_clauses: list[MatchedClause]
    status:          Literal["COVERED", "PARTIAL", "MISSING", "NON_CONFORMING", "NOT_APPLICABLE"]
    gaps:            list[str]
    confidence:      float
    has_commitments: bool

# ── Pydantic schemas for LLM structured output ───────────────────────────────

class MappingOutput(BaseModel):
    clause_ids: list[str]   # e.g. ["8.4.1", "9.2", "7.2"]
    reasoning:  str         # brief justification — kept for debugging, not surfaced to API

class MatchedClauseOutput(BaseModel):
    clause_number: str
    evidence_text: str
    status:        Literal["COVERED", "PARTIAL", "NON_CONFORMING"]
    advice:        str

class SectionMatchOutput(BaseModel):
    matched_clauses: list[MatchedClauseOutput]
    status:          Literal["COVERED", "PARTIAL", "MISSING", "NON_CONFORMING"]
    gaps:            list[str]
    confidence:      float

# ── Converter ────────────────────────────────────────────────────────────────

def to_section_match(
    output: SectionMatchOutput,
    fetched: list[ClauseRecord],
    section,           # ParsedSection
    has_commitments: bool,
) -> SectionMatch:
    clause_map = {c.clause_number: c for c in fetched}
    matched = [
        MatchedClause(
            norm_id       = clause_map[mc.clause_number].norm_id,
            clause_number = mc.clause_number,
            clause_title  = clause_map[mc.clause_number].clause_title,
            evidence_text = mc.evidence_text,
            status        = mc.status,
            advice        = mc.advice,
        )
        for mc in output.matched_clauses
        if mc.clause_number in clause_map   # drop any hallucination that slipped through
    ]
    return SectionMatch(
        section_id      = section.id,
        section_type    = section.section_type.value,
        title           = section.title,
        matched_clauses = matched,
        status          = output.status,
        gaps            = output.gaps,
        confidence      = output.confidence,
        has_commitments = has_commitments,
    )
```

**Done condition:**
- All models import cleanly
- `SectionMatch(status="NOT_APPLICABLE", ...)` is valid — Literal accepts it
- `to_section_match()` with a mismatched `clause_number` silently drops that entry (the `if mc.clause_number in clause_map` guard)