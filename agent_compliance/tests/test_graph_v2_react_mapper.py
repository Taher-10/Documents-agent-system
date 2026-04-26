from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import groq
import httpx
import pytest
from langchain_core.exceptions import OutputParserException

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
        "doc_code": "PRO-QHSE-001",
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
        schema_name = self.schema.__name__
        self.owner.prompts.append((schema_name, messages))
        self.owner.calls[schema_name] += 1
        if self.owner.raise_on_invoke:
            raise OutputParserException("forced parse error")
        if self.schema is MappingOutput:
            return self.owner._next_mapping_outcome()
        if self.schema is SectionMatchOutput:
            return self.owner._next_assessment_outcome()
        raise AssertionError(f"Unexpected schema {self.schema}")


class _FakeLLM:
    def __init__(
        self,
        *,
        mapping_outputs: list[MappingOutput | Exception],
        assessment_outputs: list[SectionMatchOutput | Exception],
        raise_on_invoke: bool = False,
    ):
        self.mapping_outputs = list(mapping_outputs)
        self.assessment_outputs = list(assessment_outputs)
        self.raise_on_invoke = raise_on_invoke
        self.prompts: list[tuple[str, list]] = []
        self.calls = {"MappingOutput": 0, "SectionMatchOutput": 0}

    def with_structured_output(self, schema):
        return _FakeStructuredInvoker(self, schema)

    def _next_mapping_outcome(self) -> MappingOutput:
        if not self.mapping_outputs:
            raise AssertionError("No MappingOutput outcome configured")
        outcome = self.mapping_outputs.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _next_assessment_outcome(self) -> SectionMatchOutput:
        if not self.assessment_outputs:
            raise AssertionError("No SectionMatchOutput outcome configured")
        outcome = self.assessment_outputs.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _long_text(seed: str) -> str:
    return (seed + " ") * 80


def _disable_retry_sleep(monkeypatch) -> None:
    monkeypatch.setattr(react_mod._invoke_structured.retry, "sleep", lambda _: None)


def _status_error(status_code: int) -> groq.APIStatusError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code=status_code, request=request)
    return groq.APIStatusError(f"status {status_code}", response=response, body={"error": "x"})


def _rate_limit_error(*, retry_after: str | None = None) -> groq.RateLimitError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    headers = {"Retry-After": retry_after} if retry_after is not None else None
    response = httpx.Response(status_code=429, request=request, headers=headers)
    return groq.RateLimitError("rate limited", response=response, body={"error": "rate"})


class _RetryOutcome:
    failed = True

    def __init__(self, exc: Exception):
        self._exc = exc

    def exception(self):
        return self._exc


class _RetryState:
    def __init__(self, *, attempt_number: int, exc: Exception | None = None):
        self.attempt_number = attempt_number
        self.outcome = _RetryOutcome(exc) if exc is not None else None


@pytest.fixture(autouse=True)
def _disable_section_pacing(monkeypatch) -> None:
    monkeypatch.setattr(react_mod.time, "sleep", lambda _: None)


def test_is_mappable_patterns_and_short_text() -> None:
    historical = _Section("s1", SectionType.PROCEDURE_TEXT, "Historique des modifications", _long_text("audit"))
    short_text = _Section("s2", SectionType.PROCEDURE_TEXT, "Audit", "too short")
    valid = _Section("s3", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("doit procédure"))

    assert react_mod._is_mappable(historical) == (False, "non_mappable_title")
    assert react_mod._is_mappable(short_text) == (False, "non_mappable_short")
    assert react_mod._is_mappable(valid) == (True, None)


def test_is_mappable_type_gates() -> None:
    metadata = _Section("s1", SectionType.METADATA, "Page de garde", _long_text("meta"))
    references = _Section("s2", SectionType.REFERENCES, "Références", _long_text("ref"))
    definitions = _Section("s3", SectionType.DEFINITIONS, "Définitions", _long_text("glossaire"))

    assert react_mod._is_mappable(metadata) == (False, "non_mappable_type")
    assert react_mod._is_mappable(references) == (False, "non_mappable_type")
    assert react_mod._is_mappable(definitions) == (False, "non_mappable_definitions")


def test_validate_evidence_drops_low_overlap_evidence_and_forces_non_conforming() -> None:
    output = SectionMatchOutput(
        matched_clauses=[
            MatchedClauseOutput(
                clause_number="9.2.1",
                evidence_text="this quote is not in section",
                status="COVERED",
                advice="x",
            )
        ],
        status="COVERED",
        gaps=[],
        confidence=0.8,
    )

    validated = react_mod._validate_evidence(output, _long_text("audit interne"))

    assert validated.status == "NON_CONFORMING"
    assert validated.gaps == ["invalid_evidence"]
    assert validated.matched_clauses == []


def test_validate_evidence_keeps_high_overlap_paraphrase() -> None:
    raw_text = (
        "Le responsable qualité enregistre le gabarit sur QALITAS "
        "et renseigne les champs obligatoires."
    )
    output = SectionMatchOutput(
        matched_clauses=[
            MatchedClauseOutput(
                clause_number="7.5.3.1",
                evidence_text="responsable qualité enregistre gabarit QALITAS champs obligatoires",
                status="PARTIAL",
                advice="x",
            )
        ],
        status="PARTIAL",
        gaps=[],
        confidence=0.8,
    )

    validated = react_mod._validate_evidence(output, raw_text)

    assert validated.status == "PARTIAL"
    assert validated.gaps == []
    assert len(validated.matched_clauses) == 1
    assert validated.matched_clauses[0].status == "PARTIAL"


def test_validate_evidence_downgrades_empty_evidence() -> None:
    output = SectionMatchOutput(
        matched_clauses=[
            MatchedClauseOutput(
                clause_number="9.2.1",
                evidence_text="   ",
                status="PARTIAL",
                advice="x",
            )
        ],
        status="PARTIAL",
        gaps=[],
        confidence=0.7,
    )

    validated = react_mod._validate_evidence(output, _long_text("audit interne"))

    assert validated.status == "NON_CONFORMING"
    assert validated.gaps == ["invalid_evidence"]
    assert len(validated.matched_clauses) == 1
    assert validated.matched_clauses[0].status == "NON_CONFORMING"


def test_retry_after_wait_uses_max_of_exponential_and_header() -> None:
    waiter = react_mod._wait_exponential_with_retry_after(multiplier=1, min_wait=2, max_wait=8)
    retry_state = _RetryState(attempt_number=1, exc=_rate_limit_error(retry_after="7"))
    assert waiter(retry_state) == 7


def test_retry_after_wait_falls_back_to_exponential_when_header_missing() -> None:
    waiter = react_mod._wait_exponential_with_retry_after(multiplier=1, min_wait=2, max_wait=8)
    retry_state = _RetryState(attempt_number=1, exc=_rate_limit_error())
    assert waiter(retry_state) == 2


def test_prompt_renderers_are_stable() -> None:
    section = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("texte"))
    menu_text = react_mod._render_clause_menu({"ISO9001": [("9.2.1", "Internal audit")]})
    mapping_prompt = react_mod._mapping_prompt(
        section,
        menu_text,
        "PRO-QHSE-001",
        "procedure",
        3,
    )
    assessment_prompt = react_mod._assessment_prompt(
        section,
        [_clause("9.2.1")],
        "PRO-QHSE-001",
        "procedure",
        3,
    )

    assert "ISO9001" in menu_text
    assert "9.2.1" in menu_text
    assert len(mapping_prompt) == 2
    assert len(assessment_prompt) == 2
    assert "Document: PRO-QHSE-001 | Type: procedure | Level: 3" in mapping_prompt[1].content
    assert "Document: PRO-QHSE-001 | Type: procedure | Level: 3" in assessment_prompt[1].content
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
    assert match.gaps == ["non_mappable_type"]


def test_section_pacing_applies_only_to_llm_processed_sections(monkeypatch) -> None:
    mappable = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("audit"))
    non_mappable = _Section("s2", SectionType.METADATA, "Table des matières", _long_text("meta"))
    llm = _FakeLLM(
        mapping_outputs=[MappingOutput(clause_ids=["9.2.1"], reasoning="mapped")],
        assessment_outputs=[
            SectionMatchOutput(
                matched_clauses=[
                    MatchedClauseOutput(
                        clause_number="9.2.1",
                        evidence_text="audit",
                        status="PARTIAL",
                        advice="x",
                    )
                ],
                status="PARTIAL",
                gaps=[],
                confidence=0.7,
            )
        ],
    )
    sleep_calls: list[float] = []

    monkeypatch.setattr(react_mod.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(react_mod, "get_llm", lambda: llm)
    monkeypatch.setattr(react_mod, "fetch_clauses_by_ids", lambda *a, **k: [_clause("9.2.1")])
    monkeypatch.setattr(react_mod, "fetch_clauses_by_section_type", lambda *a, **k: [])

    state = _state(section=mappable)
    state["sections"] = [mappable, non_mappable]
    result = react_mod.react_mapper_node(state, db_path="agent_compliance/data/iso_clauses.db")

    assert [m.status for m in result["section_matches"]] == ["PARTIAL", "NOT_APPLICABLE"]
    assert sleep_calls == [0.5]


def test_non_mappable_title_and_short_text_are_audited(monkeypatch) -> None:
    title_section = _Section("s1", SectionType.PROCEDURE_TEXT, "Historique des modifications", _long_text("texte"))
    short_section = _Section("s2", SectionType.PROCEDURE_TEXT, "Audit", "too short")
    calls = {"get_llm": 0}

    def fake_get_llm():
        calls["get_llm"] += 1
        return _FakeLLM(mapping_outputs=[], assessment_outputs=[])

    monkeypatch.setattr(react_mod, "get_llm", fake_get_llm)

    title_result = react_mod.react_mapper_node(_state(section=title_section), db_path="agent_compliance/data/iso_clauses.db")
    short_result = react_mod.react_mapper_node(_state(section=short_section), db_path="agent_compliance/data/iso_clauses.db")

    assert calls["get_llm"] == 0
    assert title_result["section_matches"][0].status == "NOT_APPLICABLE"
    assert title_result["section_matches"][0].gaps == ["non_mappable_title"]
    assert short_result["section_matches"][0].status == "NOT_APPLICABLE"
    assert short_result["section_matches"][0].gaps == ["non_mappable_short"]


def test_definitions_section_uses_deterministic_clause_3_without_llm(monkeypatch) -> None:
    section = _Section("s1", SectionType.DEFINITIONS, "Définitions", _long_text("termes"))
    calls = {"get_llm": 0, "by_ids": 0}

    def fake_get_llm():
        calls["get_llm"] += 1
        return _FakeLLM(mapping_outputs=[], assessment_outputs=[])

    def fake_fetch_by_ids(clause_ids, *args, **kwargs):
        _ = args, kwargs
        calls["by_ids"] += 1
        assert clause_ids == ["3"]
        return [_clause("3")]

    monkeypatch.setattr(react_mod, "get_llm", fake_get_llm)
    monkeypatch.setattr(react_mod, "fetch_clauses_by_ids", fake_fetch_by_ids)

    result = react_mod.react_mapper_node(_state(section=section), db_path="agent_compliance/data/iso_clauses.db")
    match = result["section_matches"][0]

    assert calls["get_llm"] == 0
    assert calls["by_ids"] == 1
    assert match.status == "PARTIAL"
    assert match.gaps == ["non_mappable_definitions"]
    assert len(match.matched_clauses) == 1
    assert match.matched_clauses[0].clause_number == "3"
    assert "Clause 3 vocabulary" in match.matched_clauses[0].advice


def test_definitions_missing_clause_3_returns_missing(monkeypatch) -> None:
    section = _Section("s1", SectionType.DEFINITIONS, "Définitions", _long_text("termes"))
    calls = {"get_llm": 0}

    def fake_get_llm():
        calls["get_llm"] += 1
        return _FakeLLM(mapping_outputs=[], assessment_outputs=[])

    monkeypatch.setattr(react_mod, "get_llm", fake_get_llm)
    monkeypatch.setattr(react_mod, "fetch_clauses_by_ids", lambda *a, **k: [])

    result = react_mod.react_mapper_node(_state(section=section), db_path="agent_compliance/data/iso_clauses.db")
    match = result["section_matches"][0]

    assert calls["get_llm"] == 0
    assert match.status == "MISSING"
    assert match.gaps == ["definitions_clause_missing"]


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

    def fake_assessment_prompt(section_arg, clauses, doc_code, doc_type, doc_level):
        _ = section_arg
        _ = doc_code, doc_type, doc_level
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
    assert llm.calls["MappingOutput"] == 1
    assert llm.calls["SectionMatchOutput"] == 0


def test_transient_mapping_errors_retry_then_succeed(monkeypatch) -> None:
    _disable_retry_sleep(monkeypatch)
    section = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("audit"))
    llm = _FakeLLM(
        mapping_outputs=[
            _rate_limit_error(),
            _rate_limit_error(),
            MappingOutput(clause_ids=["9.2.1"], reasoning="ok after retries"),
        ],
        assessment_outputs=[
            SectionMatchOutput(
                matched_clauses=[
                    MatchedClauseOutput(
                        clause_number="9.2.1",
                        evidence_text="audit",
                        status="COVERED",
                        advice="Conserver les preuves d'audit.",
                    )
                ],
                status="COVERED",
                gaps=[],
                confidence=0.9,
            )
        ],
    )

    monkeypatch.setattr(react_mod, "get_llm", lambda: llm)
    monkeypatch.setattr(react_mod, "fetch_clauses_by_ids", lambda *a, **k: [_clause("9.2.1")])
    monkeypatch.setattr(react_mod, "fetch_clauses_by_section_type", lambda *a, **k: [])

    result = react_mod.react_mapper_node(_state(section=section), db_path="agent_compliance/data/iso_clauses.db")
    match = result["section_matches"][0]

    assert match.status == "COVERED"
    assert match.gaps == []
    assert llm.calls["MappingOutput"] == 3
    assert llm.calls["SectionMatchOutput"] == 1


def test_transient_assessment_errors_retry_then_succeed(monkeypatch) -> None:
    _disable_retry_sleep(monkeypatch)
    section = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("audit"))
    llm = _FakeLLM(
        mapping_outputs=[MappingOutput(clause_ids=["9.2.1"], reasoning="mapped")],
        assessment_outputs=[
            _rate_limit_error(),
            _rate_limit_error(),
            SectionMatchOutput(
                matched_clauses=[
                    MatchedClauseOutput(
                        clause_number="9.2.1",
                        evidence_text="audit",
                        status="PARTIAL",
                        advice="Ajouter une périodicité formelle.",
                    )
                ],
                status="PARTIAL",
                gaps=["audit cadence"],
                confidence=0.7,
            ),
        ],
    )

    monkeypatch.setattr(react_mod, "get_llm", lambda: llm)
    monkeypatch.setattr(react_mod, "fetch_clauses_by_ids", lambda *a, **k: [_clause("9.2.1")])
    monkeypatch.setattr(react_mod, "fetch_clauses_by_section_type", lambda *a, **k: [])

    result = react_mod.react_mapper_node(_state(section=section), db_path="agent_compliance/data/iso_clauses.db")
    match = result["section_matches"][0]

    assert match.status == "PARTIAL"
    assert llm.calls["MappingOutput"] == 1
    assert llm.calls["SectionMatchOutput"] == 3


def test_transient_errors_exhaust_retries_yield_llm_exhausted(monkeypatch) -> None:
    _disable_retry_sleep(monkeypatch)
    section = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("audit"))
    llm = _FakeLLM(
        mapping_outputs=[_rate_limit_error(), _rate_limit_error(), _rate_limit_error()],
        assessment_outputs=[],
    )

    monkeypatch.setattr(react_mod, "get_llm", lambda: llm)

    result = react_mod.react_mapper_node(_state(section=section), db_path="agent_compliance/data/iso_clauses.db")
    match = result["section_matches"][0]

    assert match.status == "MISSING"
    assert match.gaps == ["llm_exhausted"]
    assert llm.calls["MappingOutput"] == 3
    assert llm.calls["SectionMatchOutput"] == 0


def test_non_retryable_error_yields_llm_exhausted_without_retry(monkeypatch) -> None:
    _disable_retry_sleep(monkeypatch)
    section = _Section("s1", SectionType.PROCEDURE_TEXT, "Audit interne", _long_text("audit"))
    llm = _FakeLLM(
        mapping_outputs=[_status_error(401)],
        assessment_outputs=[],
    )

    monkeypatch.setattr(react_mod, "get_llm", lambda: llm)

    result = react_mod.react_mapper_node(_state(section=section), db_path="agent_compliance/data/iso_clauses.db")
    match = result["section_matches"][0]

    assert match.status == "MISSING"
    assert match.gaps == ["llm_exhausted"]
    assert llm.calls["MappingOutput"] == 1
    assert llm.calls["SectionMatchOutput"] == 0


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
