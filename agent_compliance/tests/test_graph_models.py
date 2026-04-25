from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from agent_compliance.graph.models import (
    MappingOutput,
    MatchedClause,
    MatchedClauseOutput,
    SectionMatch,
    SectionMatchOutput,
    to_section_match,
)
from agent_compliance.retrieval.clause_store import ClauseRecord


@dataclass
class _DummySection:
    id: str
    title: str
    section_type: object


def _fetched_clause(
    clause_number: str = "8.4.1",
    clause_title: str = "General",
    norm_id: str = "ISO9001",
) -> ClauseRecord:
    return ClauseRecord(
        norm_id=norm_id,
        clause_number=clause_number,
        clause_title=clause_title,
        parent_clause="8.4",
        text="Clause text",
        language="EN",
    )


def test_import_smoke() -> None:
    assert MappingOutput(clause_ids=["8.4.1"], reasoning="ok").clause_ids == ["8.4.1"]
    assert MatchedClauseOutput(
        clause_number="8.4.1",
        evidence_text="Evidence",
        status="COVERED",
        advice="Keep records",
    ).clause_number == "8.4.1"


def test_not_applicable_status_valid_for_dataclass_and_output_model() -> None:
    section_match = SectionMatch(
        section_id="s1",
        section_type="procedure_text",
        title="Proc",
        matched_clauses=[],
        status="NOT_APPLICABLE",
        gaps=[],
        confidence=0.5,
        has_commitments=False,
    )
    output = SectionMatchOutput(
        matched_clauses=[],
        status="NOT_APPLICABLE",
        gaps=[],
        confidence=0.2,
    )

    assert section_match.status == "NOT_APPLICABLE"
    assert output.status == "NOT_APPLICABLE"


def test_to_section_match_drops_unmatched_clause_numbers() -> None:
    section = _DummySection(
        id="section_1",
        title="Supplier control",
        section_type=SimpleNamespace(value="procedure_text"),
    )
    output = SectionMatchOutput(
        matched_clauses=[
            MatchedClauseOutput(
                clause_number="8.4.1",
                evidence_text="Approved suppliers list is maintained.",
                status="COVERED",
                advice="Continue periodic supplier reviews.",
            ),
            MatchedClauseOutput(
                clause_number="9.9.9",
                evidence_text="Hallucinated evidence",
                status="PARTIAL",
                advice="Hallucinated advice",
            ),
        ],
        status="PARTIAL",
        gaps=["Need external provider KPI trend"],
        confidence=0.79,
    )

    result = to_section_match(output, [_fetched_clause()], section, has_commitments=True)

    assert result.section_id == "section_1"
    assert result.section_type == "procedure_text"
    assert len(result.matched_clauses) == 1
    assert result.matched_clauses[0].clause_number == "8.4.1"


def test_to_section_match_maps_fields_exactly() -> None:
    section = _DummySection(
        id="section_2",
        title="Internal audit",
        section_type=SimpleNamespace(value="procedure_text"),
    )
    fetched = [_fetched_clause(clause_number="9.2.1", clause_title="Internal audit", norm_id="ISO9001")]
    output = SectionMatchOutput(
        matched_clauses=[
            MatchedClauseOutput(
                clause_number="9.2.1",
                evidence_text="Audits are performed quarterly.",
                status="COVERED",
                advice="Maintain audit program evidence.",
            )
        ],
        status="COVERED",
        gaps=[],
        confidence=0.93,
    )

    result = to_section_match(output, fetched, section, has_commitments=False)
    matched: MatchedClause = result.matched_clauses[0]

    assert result.section_id == "section_2"
    assert result.title == "Internal audit"
    assert result.has_commitments is False
    assert result.confidence == 0.93
    assert matched.norm_id == "ISO9001"
    assert matched.clause_number == "9.2.1"
    assert matched.clause_title == "Internal audit"
    assert matched.evidence_text == "Audits are performed quarterly."
    assert matched.advice == "Maintain audit program evidence."
    assert matched.status == "COVERED"


def test_to_section_match_handles_empty_and_all_filtered() -> None:
    section = _DummySection(
        id="section_3",
        title="No commitments",
        section_type=SimpleNamespace(value="scope"),
    )

    empty_output = SectionMatchOutput(
        matched_clauses=[],
        status="MISSING",
        gaps=["No verifiable commitment"],
        confidence=0.4,
    )
    empty_result = to_section_match(empty_output, [_fetched_clause()], section, has_commitments=False)
    assert empty_result.matched_clauses == []

    filtered_output = SectionMatchOutput(
        matched_clauses=[
            MatchedClauseOutput(
                clause_number="0.0.0",
                evidence_text="Unknown clause",
                status="NON_CONFORMING",
                advice="N/A",
            )
        ],
        status="MISSING",
        gaps=["No mapped clause"],
        confidence=0.11,
    )
    filtered_result = to_section_match(filtered_output, [_fetched_clause("8.4.1")], section, has_commitments=False)
    assert filtered_result.matched_clauses == []
