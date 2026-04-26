from __future__ import annotations

from typing import TypedDict

from agent_compliance.graph_v2.models import SectionMatch
from agent_compliance.pdf_parser import ParsedSection


class ComplianceState(TypedDict):
    doc_id: str
    company_id: str
    applicable_norms: list[str]
    language: str
    doc_code: str | None
    doc_type: str | None
    doc_level: int | None
    clause_menu: dict[str, list[tuple[str, str]]]
    sections: list[ParsedSection]
    section_matches: list[SectionMatch]
    report: dict | None
