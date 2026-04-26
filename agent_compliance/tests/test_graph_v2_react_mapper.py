from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from agent_compliance.graph_v2.models import MappingOutput, MatchedClauseOutput, SectionMatchOutput
from agent_compliance.graph_v2.nodes import react_mapper as react_mod
from agent_compliance.pdf_parser.parsed_document import SectionType
from agent_compliance.retrieval.clause_store import ClauseRecord


@dataclass
class _Section:
    id: str
    section_type: SectionType
    title: str
    raw_text: str


def _state(*, section: _Section, language: str = "FR") -> dict:
    return {
        "doc_id": "doc-1",
        "company_id": "company-1",
        "applicable_norms": ["ISO 9001"],
        "language": language,
        "doc_type": "procedure",
        "doc_level": 3,
        "clause_menu": {"ISO9001": [("8.4.1", "General"), ("9.2.1", "Internal audit")]},
        "sections": [section],
        "section_matches": [],
        "report": None,
    }


def _clause(num: str) -> ClauseRecord:
    return ClauseRecord(
        norm_id="ISO9001",
        clause_number=num,
        clause_title=f"Title {num}",
        parent_clause=num.rsplit(".", 1)[0] if "." in num else "",
        text=f"Clause text {num}",
        language="FR",
    )


class _FakeStructuredInvoker:
    def __init__(self, owner: "_FakeLLM", schema):
        self.owner = owner
        self.schema = schema

    def invoke(self, messages):
        self.owner.prompts.append((self.schema.__name__, messages))
        if self.owner.raise_on_invoke:
            raise ValueError("forced parse error")
        if self.schema is MappingOutput:
            return self.owner.mapping_outputs.pop(0)
        if self.schema is SectionMatchOutput:
            return self.owner.assessment_outputs.pop(0)
        raise AssertionError(f"Unexpected schema {self.schema}")


class _FakeLLM:
    def __init__(
        self,
        *,
        mapping_outputs: list[MappingOutput],
        assessment_outputs: list[SectionMatchOutput],
        raise_on_invoke: bool = False,
    ):
        self.mapping_outputs = mapping_outputs
        self.assessment_outputs = assessment_outputs
        self.raise_on_invoke = raise_on_invoke
        self.prompts: list[tuple[str, list]] = []

    def with_structured_output(self, schema):
        return _FakeStructuredInvoker(self, schema)


def _long_text(seed: str) -> str:
    return (seed + " ") * 80


def test_is_mappable_patterns_and_short_text() -> None:
    historical = _Section("s1", SectionType.PROCEDURE_TEXT, "Historique des modifications", _long_text("audit"))
    short_text = _Section("s2", SectionType.PROCEDURE_TEXT, "Audit", "too short")
    valid = _Section("s3", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("doit procédure"))

    assert react_mod._is_mappable(historical) is False
    assert react_mod._is_mappable(short_text) is False
    assert react_mod._is_mappable(valid) is True


def test_prompt_renderers_are_stable() -> None:
    section = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("texte"))
    menu_text = react_mod._render_clause_menu({"ISO9001": [("9.2.1", "Internal audit")]})
    mapping_prompt = react_mod._mapping_prompt(section, menu_text, "procedure", 3)
    assessment_prompt = react_mod._assessment_prompt(section, [_clause("9.2.1")])

    assert "ISO9001" in menu_text
    assert "9.2.1" in menu_text
    assert len(mapping_prompt) == 2
    assert len(assessment_prompt) == 2
    assert "Document type: procedure" in mapping_prompt[1].content
    assert "ISO clauses to assess" in assessment_prompt[1].content


def test_non_mappable_section_skips_llm_calls(monkeypatch) -> None:
    section = _Section("s1", SectionType.METADATA, "Table des matières", _long_text("texte"))
    calls = {"get_llm": 0}

    def fake_get_llm():
        calls["get_llm"] += 1
        return _FakeLLM(mapping_outputs=[], assessment_outputs=[])

    monkeypatch.setattr(react_mod, "get_llm", fake_get_llm)

    result = react_mod.react_mapper_node(_state(section=section), db_path="agent_compliance/data/iso_clauses.db")
    match = result["section_matches"][0]

    assert calls["get_llm"] == 0
    assert match.status == "NOT_APPLICABLE"


def test_mapper_drops_hallucinated_ids_and_uses_fallback(monkeypatch) -> None:
    section = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("doit audit interne"))
    llm = _FakeLLM(
        mapping_outputs=[MappingOutput(clause_ids=["8.4.99"], reasoning="hallucinated")],
        assessment_outputs=[
            SectionMatchOutput(
                matched_clauses=[
                    MatchedClauseOutput(
                        clause_number="9.2.1",
                        evidence_text="doit audit interne",
                        status="PARTIAL",
                        advice="Ajouter la fréquence documentée des audits.",
                    ),
                    MatchedClauseOutput(
                        clause_number="8.4.99",
                        evidence_text="fake",
                        status="NON_CONFORMING",
                        advice="fake",
                    ),
                ],
                status="PARTIAL",
                gaps=["audit frequency"],
                confidence=0.7,
            )
        ],
    )
    calls = {"by_ids": 0, "fallback": 0}

    monkeypatch.setattr(react_mod, "get_llm", lambda: llm)

    def fake_fetch_by_ids(*args, **kwargs):
        _ = args, kwargs
        calls["by_ids"] += 1
        return []

    def fake_fetch_by_section(*args, **kwargs):
        _ = args, kwargs
        calls["fallback"] += 1
        return [_clause("9.2.1")]

    monkeypatch.setattr(react_mod, "fetch_clauses_by_ids", fake_fetch_by_ids)
    monkeypatch.setattr(react_mod, "fetch_clauses_by_section_type", fake_fetch_by_section)

    result = react_mod.react_mapper_node(_state(section=section), db_path="agent_compliance/data/iso_clauses.db")
    match = result["section_matches"][0]

    assert calls["by_ids"] == 1
    assert calls["fallback"] == 1
    assert len(match.matched_clauses) == 1
    assert match.matched_clauses[0].clause_number == "9.2.1"


def test_fallback_empty_yields_missing_and_skips_assessment(monkeypatch) -> None:
    section = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("doit audit interne"))
    llm = _FakeLLM(
        mapping_outputs=[MappingOutput(clause_ids=["8.4.99"], reasoning="none valid")],
        assessment_outputs=[],
    )

    monkeypatch.setattr(react_mod, "get_llm", lambda: llm)
    monkeypatch.setattr(react_mod, "fetch_clauses_by_ids", lambda *a, **k: [])
    monkeypatch.setattr(react_mod, "fetch_clauses_by_section_type", lambda *a, **k: [])

    result = react_mod.react_mapper_node(_state(section=section), db_path="agent_compliance/data/iso_clauses.db")
    match = result["section_matches"][0]

    assert match.status == "MISSING"
    assert match.gaps == ["no_mapped_clauses"]
    assert [schema for schema, _ in llm.prompts] == ["MappingOutput"]


def test_clause_cap_applies_before_assessment(monkeypatch) -> None:
    section = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("audit"))
    llm = _FakeLLM(
        mapping_outputs=[
            MappingOutput(
                clause_ids=[f"9.2.{idx}" for idx in range(1, 11)],
                reasoning="many clauses",
            )
        ],
        assessment_outputs=[
            SectionMatchOutput(
                matched_clauses=[
                    MatchedClauseOutput(
                        clause_number="9.2.1",
                        evidence_text="audit",
                        status="COVERED",
                        advice="Continuer la traçabilité.",
                    )
                ],
                status="COVERED",
                gaps=[],
                confidence=0.9,
            )
        ],
    )
    captured = {"assessment_clause_count": -1}

    monkeypatch.setattr(react_mod, "get_llm", lambda: llm)
    monkeypatch.setattr(react_mod, "fetch_clauses_by_ids", lambda *a, **k: [_clause(f"9.2.{idx}") for idx in range(1, 11)])
    monkeypatch.setattr(react_mod, "fetch_clauses_by_section_type", lambda *a, **k: [])

    def fake_assessment_prompt(section_arg, clauses):
        _ = section_arg
        captured["assessment_clause_count"] = len(clauses)
        return [SimpleNamespace(content="sys"), SimpleNamespace(content="user")]

    monkeypatch.setattr(react_mod, "_assessment_prompt", fake_assessment_prompt)

    result = react_mod.react_mapper_node(_state(section=section), db_path="agent_compliance/data/iso_clauses.db")

    assert captured["assessment_clause_count"] == 8
    assert result["section_matches"][0].status == "COVERED"


def test_llm_error_yields_missing_with_parse_gap(monkeypatch) -> None:
    section = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("audit"))
    llm = _FakeLLM(
        mapping_outputs=[MappingOutput(clause_ids=["9.2.1"], reasoning="audit")],
        assessment_outputs=[],
        raise_on_invoke=True,
    )

    monkeypatch.setattr(react_mod, "get_llm", lambda: llm)
    monkeypatch.setattr(react_mod, "fetch_clauses_by_ids", lambda *a, **k: [_clause("9.2.1")])
    monkeypatch.setattr(react_mod, "fetch_clauses_by_section_type", lambda *a, **k: [])

    result = react_mod.react_mapper_node(_state(section=section), db_path="agent_compliance/data/iso_clauses.db")
    match = result["section_matches"][0]

    assert match.status == "MISSING"
    assert match.gaps == ["llm_parse_error"]
    assert match.confidence == 0.0


def test_commitment_detection_is_language_aware(monkeypatch) -> None:
    section = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("doit audit interne"))

    def fake_llm_factory():
        return _FakeLLM(
            mapping_outputs=[MappingOutput(clause_ids=["9.2.1"], reasoning="audit")],
            assessment_outputs=[
                SectionMatchOutput(
                    matched_clauses=[
                        MatchedClauseOutput(
                            clause_number="9.2.1",
                            evidence_text="doit audit interne",
                            status="PARTIAL",
                            advice="Ajouter les critères d'audit.",
                        )
                    ],
                    status="PARTIAL",
                    gaps=[],
                    confidence=0.6,
                )
            ],
        )

    monkeypatch.setattr(react_mod, "fetch_clauses_by_ids", lambda *a, **k: [_clause("9.2.1")])
    monkeypatch.setattr(react_mod, "fetch_clauses_by_section_type", lambda *a, **k: [])

    monkeypatch.setattr(react_mod, "get_llm", fake_llm_factory)
    fr_result = react_mod.react_mapper_node(_state(section=section, language="FR"), db_path="agent_compliance/data/iso_clauses.db")
    assert fr_result["section_matches"][0].has_commitments is True

    monkeypatch.setattr(react_mod, "get_llm", fake_llm_factory)
    en_result = react_mod.react_mapper_node(_state(section=section, language="EN"), db_path="agent_compliance/data/iso_clauses.db")
    assert en_result["section_matches"][0].has_commitments is False
