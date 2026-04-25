from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from agent_compliance.graph_v2.nodes import loader as loader_mod
from agent_compliance.graph_v2.nodes.loader import loader_node
from agent_compliance.graph_v2.workflow import build_graph
from agent_compliance.pdf_parser.parsed_document import ParsedSection, SectionType


def _section(section_id: str = "sec-1") -> ParsedSection:
    return ParsedSection(
        id=section_id,
        section_type=SectionType.PROCEDURE_TEXT,
        title="Procedure",
        raw_text="Sample section text",
        page_range=(1, 1),
        extraction_confidence=0.9,
    )


def _state(language: str = "EN") -> dict:
    return {
        "doc_id": "doc-123",
        "company_id": "company-123",
        "applicable_norms": ["ISO 9001"],
        "language": language,
        "clause_menu": {},
        "sections": [],
        "section_matches": [],
        "report": None,
    }


def test_build_graph_smoke() -> None:
    graph = build_graph(MagicMock(), "agent_compliance/data/iso_clauses.db")
    assert hasattr(graph, "invoke")


def test_loader_node_uses_guarded_reader_and_clause_store(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_read_document_sections(qdrant_client, *, doc_id: str, company_id: str):
        calls["read"] = {"qdrant_client": qdrant_client, "doc_id": doc_id, "company_id": company_id}
        return SimpleNamespace(sections=[_section("sec-1")])

    def fake_load_clause_menu(applicable_norms, *, language: str, db_path: str):
        calls["menu"] = {
            "applicable_norms": list(applicable_norms),
            "language": language,
            "db_path": db_path,
        }
        return {"ISO9001": [("4.1", "Context")]}

    monkeypatch.setattr(loader_mod, "read_document_sections", fake_read_document_sections)
    monkeypatch.setattr(loader_mod, "load_clause_menu", fake_load_clause_menu)

    qdrant = MagicMock()
    result = loader_node(_state(), qdrant=qdrant, db_path="agent_compliance/data/iso_clauses.db")

    assert "sections" in result
    assert "clause_menu" in result
    assert len(result["sections"]) == 1
    assert result["clause_menu"] == {"ISO9001": [("4.1", "Context")]}
    assert calls["read"] == {"qdrant_client": qdrant, "doc_id": "doc-123", "company_id": "company-123"}
    assert calls["menu"] == {
        "applicable_norms": ["ISO 9001"],
        "language": "EN",
        "db_path": "agent_compliance/data/iso_clauses.db",
    }


def test_loader_language_pass_through(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_read_document_sections(qdrant_client, *, doc_id: str, company_id: str):
        _ = qdrant_client, doc_id, company_id
        return SimpleNamespace(sections=[])

    def fake_load_clause_menu(applicable_norms, *, language: str, db_path: str):
        seen["language"] = language
        _ = applicable_norms, db_path
        return {}

    monkeypatch.setattr(loader_mod, "read_document_sections", fake_read_document_sections)
    monkeypatch.setattr(loader_mod, "load_clause_menu", fake_load_clause_menu)

    loader_node(_state(language="FR"), qdrant=MagicMock(), db_path="agent_compliance/data/iso_clauses.db")
    assert seen["language"] == "FR"


def test_loader_empty_sections_and_menu(monkeypatch) -> None:
    def fake_read_document_sections(qdrant_client, *, doc_id: str, company_id: str):
        _ = qdrant_client, doc_id, company_id
        return SimpleNamespace(sections=[])

    def fake_load_clause_menu(applicable_norms, *, language: str, db_path: str):
        _ = applicable_norms, language, db_path
        return {}

    monkeypatch.setattr(loader_mod, "read_document_sections", fake_read_document_sections)
    monkeypatch.setattr(loader_mod, "load_clause_menu", fake_load_clause_menu)

    result = loader_node(_state(), qdrant=MagicMock(), db_path="agent_compliance/data/iso_clauses.db")
    assert result == {"sections": [], "clause_menu": {}}


def test_compiled_graph_invoke_smoke_with_mocked_data_paths(monkeypatch) -> None:
    def fake_read_document_sections(qdrant_client, *, doc_id: str, company_id: str):
        _ = qdrant_client, doc_id, company_id
        return SimpleNamespace(sections=[_section("sec-1"), _section("sec-2")])

    def fake_load_clause_menu(applicable_norms, *, language: str, db_path: str):
        _ = applicable_norms, language, db_path
        return {"ISO9001": [(f"8.4.{idx}", f"Clause {idx}") for idx in range(1, 13)]}

    monkeypatch.setattr(loader_mod, "read_document_sections", fake_read_document_sections)
    monkeypatch.setattr(loader_mod, "load_clause_menu", fake_load_clause_menu)

    graph = build_graph(MagicMock(), "agent_compliance/data/iso_clauses.db")
    result = graph.invoke(_state())

    assert len(result["sections"]) > 0
    assert "ISO9001" in result["clause_menu"]
    assert len(result["clause_menu"]["ISO9001"]) > 10
