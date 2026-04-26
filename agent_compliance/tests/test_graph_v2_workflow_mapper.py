from __future__ import annotations

from unittest.mock import MagicMock

from agent_compliance.graph_v2 import workflow as workflow_mod
from agent_compliance.graph_v2.workflow import build_graph
from agent_compliance.pdf_parser.parsed_document import ParsedSection, SectionType


def _state() -> dict:
    return {
        "doc_id": "doc-123",
        "company_id": "company-123",
        "applicable_norms": ["ISO 9001"],
        "language": "FR",
        "doc_type": None,
        "doc_level": None,
        "clause_menu": {},
        "sections": [],
        "section_matches": [],
        "report": None,
    }


def _section(section_id: str) -> ParsedSection:
    return ParsedSection(
        id=section_id,
        section_type=SectionType.PROCEDURE_TEXT,
        title="Procedure",
        raw_text="Document section text " * 20,
        page_range=(1, 1),
        extraction_confidence=0.9,
    )


def test_workflow_calls_loader_then_mapper_and_preserves_count(monkeypatch) -> None:
    call_order: list[str] = []

    def fake_loader_node(state: dict, *, qdrant, db_path: str):
        _ = qdrant, db_path
        call_order.append("loader")
        return {
            "sections": [_section("sec-1"), _section("sec-2")],
            "clause_menu": {"ISO9001": [("9.2.1", "Internal audit")]},
            "doc_type": "procedure",
            "doc_level": 3,
        }

    def fake_react_mapper_node(state: dict, *, db_path: str):
        _ = db_path
        call_order.append("react_mapper")
        sections = state.get("sections") or []
        return {
            "section_matches": [
                f"match-{idx}" for idx, _ in enumerate(sections, start=1)
            ]
        }

    monkeypatch.setattr(workflow_mod, "loader_node", fake_loader_node)
    monkeypatch.setattr(workflow_mod, "react_mapper_node", fake_react_mapper_node)

    graph = build_graph(MagicMock(), "agent_compliance/data/iso_clauses.db")
    result = graph.invoke(_state())

    assert call_order == ["loader", "react_mapper"]
    assert len(result["sections"]) == 2
    assert len(result["section_matches"]) == len(result["sections"])


def test_workflow_build_smoke() -> None:
    graph = build_graph(MagicMock(), "agent_compliance/data/iso_clauses.db")
    assert hasattr(graph, "invoke")
