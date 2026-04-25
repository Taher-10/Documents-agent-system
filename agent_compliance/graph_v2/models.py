from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from agent_compliance.retrieval.clause_store import ClauseRecord


@dataclass
class MatchedClause:
    norm_id: str
    clause_number: str
    clause_title: str
    evidence_text: str
    status: Literal["COVERED", "PARTIAL", "NON_CONFORMING"]
    advice: str


@dataclass
class SectionMatch:
    section_id: str
    section_type: str
    title: str
    matched_clauses: list[MatchedClause]
    status: Literal["COVERED", "PARTIAL", "MISSING", "NON_CONFORMING", "NOT_APPLICABLE"]
    gaps: list[str]
    confidence: float
    has_commitments: bool


class MappingOutput(BaseModel):
    clause_ids: list[str]
    reasoning: str


class MatchedClauseOutput(BaseModel):
    clause_number: str
    evidence_text: str
    status: Literal["COVERED", "PARTIAL", "NON_CONFORMING"]
    advice: str


class SectionMatchOutput(BaseModel):
    matched_clauses: list[MatchedClauseOutput]
    status: Literal["COVERED", "PARTIAL", "MISSING", "NON_CONFORMING", "NOT_APPLICABLE"]
    gaps: list[str]
    confidence: float


def _section_type_value(section: Any) -> str:
    section_type = getattr(section, "section_type")
    return section_type.value if hasattr(section_type, "value") else str(section_type)


def to_section_match(
    output: SectionMatchOutput,
    fetched: list[ClauseRecord],
    section: Any,
    has_commitments: bool,
) -> SectionMatch:
    clause_map = {clause.clause_number: clause for clause in fetched}
    matched = [
        MatchedClause(
            norm_id=clause_map[item.clause_number].norm_id,
            clause_number=item.clause_number,
            clause_title=clause_map[item.clause_number].clause_title,
            evidence_text=item.evidence_text,
            status=item.status,
            advice=item.advice,
        )
        for item in output.matched_clauses
        if item.clause_number in clause_map
    ]

    return SectionMatch(
        section_id=section.id,
        section_type=_section_type_value(section),
        title=section.title,
        matched_clauses=matched,
        status=output.status,
        gaps=output.gaps,
        confidence=output.confidence,
        has_commitments=has_commitments,
    )
