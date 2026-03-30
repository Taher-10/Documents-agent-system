"""
test_parsed_document.py — M6 unit tests.

Covers:
  - SectionType enum values
  - ParsedSection construction and serialization
  - ParsedDocument.validate() — all invariant violations
  - ParsedDocument.to_dict / from_dict round-trip
  - ParsedDocument.validate() — happy path passes
"""

import json
import pytest
from document_parser.parsed_document import (
    EmptyDocumentError,
    ExtractionFailedError,
    ParsedDocument,
    ParsedSection,
    RawPageText,
    SectionType,
    UnsupportedFormatError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_section(
    id: str = "section_1",
    section_type: SectionType = SectionType.SCOPE,
    title: str = "Objet",
    raw_text: str = "Ce document décrit...",
    page_range: tuple[int, int] = (1, 1),
    extraction_confidence: float = 1.0,
    heading_level: int = 1,
    visual_ref: str | None = None,
) -> ParsedSection:
    return ParsedSection(
        id=id,
        section_type=section_type,
        title=title,
        raw_text=raw_text,
        page_range=page_range,
        extraction_confidence=extraction_confidence,
        visual_ref=visual_ref,
        heading_level=heading_level,
    )


def _make_doc(
    sections: list[ParsedSection] | None = None,
    quality_tier: str = "A",
    min_confidence: float = 1.0,
    low_quality_flag: bool = False,
    source_path: str = "/docs/PQ-PROD-01.pdf",
    file_format: str = "pdf",
) -> ParsedDocument:
    if sections is None:
        sections = [_make_section()]
    return ParsedDocument(
        job_id="test-001",
        source_path=source_path,
        file_format=file_format,  # type: ignore[arg-type]
        quality_tier=quality_tier,  # type: ignore[arg-type]
        min_confidence=min_confidence,
        low_quality_flag=low_quality_flag,
        sections=sections,
        raw_metadata={"doc_code": "PQ-PROD-01"},
        parser_version="1.0.0",
        parsed_at="2026-03-30T12:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# SectionType
# ---------------------------------------------------------------------------

class TestSectionType:
    def test_all_values_are_strings(self):
        for member in SectionType:
            assert isinstance(member.value, str)

    def test_known_values(self):
        assert SectionType.SCOPE.value == "scope"
        assert SectionType.DEFINITIONS.value == "definitions"
        assert SectionType.PROCESS_DIAGRAM.value == "process_diagram"
        assert SectionType.UNKNOWN.value == "unknown"

    def test_from_string(self):
        assert SectionType("procedure_text") is SectionType.PROCEDURE_TEXT


# ---------------------------------------------------------------------------
# ParsedSection
# ---------------------------------------------------------------------------

class TestParsedSection:
    def test_construction(self):
        s = _make_section()
        assert s.id == "section_1"
        assert s.section_type == SectionType.SCOPE
        assert s.heading_level == 1
        assert s.visual_ref is None

    def test_to_dict_keys(self):
        s = _make_section(page_range=(2, 4))
        d = s.to_dict()
        assert d["section_type"] == "scope"
        assert d["page_range"] == [2, 4]  # list, not tuple, for JSON compat

    def test_from_dict_roundtrip(self):
        original = _make_section(
            id="section_6_1",
            section_type=SectionType.PROCEDURE_TEXT,
            page_range=(5, 8),
            extraction_confidence=0.92,
            heading_level=2,
        )
        restored = ParsedSection.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.section_type == original.section_type
        assert restored.page_range == original.page_range
        assert restored.extraction_confidence == original.extraction_confidence
        assert restored.heading_level == original.heading_level

    def test_json_serializable(self):
        s = _make_section()
        json_str = json.dumps(s.to_dict())
        assert "scope" in json_str

    def test_visual_ref_preserved(self):
        s = _make_section(
            section_type=SectionType.PROCESS_DIAGRAM,
            visual_ref="/tmp/page3.png",
        )
        assert s.to_dict()["visual_ref"] == "/tmp/page3.png"
        restored = ParsedSection.from_dict(s.to_dict())
        assert restored.visual_ref == "/tmp/page3.png"


# ---------------------------------------------------------------------------
# ParsedDocument — happy path
# ---------------------------------------------------------------------------

class TestParsedDocumentHappyPath:
    def test_validate_passes_clean_doc(self):
        doc = _make_doc()
        doc.validate()  # must not raise

    def test_to_dict_from_dict_roundtrip(self):
        sections = [
            _make_section("section_1", SectionType.SCOPE),
            _make_section("section_2", SectionType.PROCEDURE_TEXT, extraction_confidence=0.95),
        ]
        original = _make_doc(sections=sections)
        restored = ParsedDocument.from_dict(original.to_dict())
        assert restored.job_id == original.job_id
        assert restored.quality_tier == original.quality_tier
        assert len(restored.sections) == 2
        assert restored.sections[1].section_type == SectionType.PROCEDURE_TEXT

    def test_json_serializable(self):
        doc = _make_doc()
        json_str = json.dumps(doc.to_dict())
        assert "test-001" in json_str

    def test_raw_metadata_preserved(self):
        doc = _make_doc()
        assert doc.raw_metadata["doc_code"] == "PQ-PROD-01"

    def test_low_quality_flag_true_for_tier_c(self):
        s = _make_section(extraction_confidence=0.1)
        doc = _make_doc(
            sections=[s],
            quality_tier="C",
            min_confidence=0.1,
            low_quality_flag=True,
        )
        doc.validate()  # must not raise

    def test_low_quality_flag_true_for_low_confidence(self):
        s = _make_section(extraction_confidence=0.6)
        doc = _make_doc(
            sections=[s],
            quality_tier="B",
            min_confidence=0.6,
            low_quality_flag=True,
        )
        doc.validate()

    def test_docx_format(self):
        s = _make_section()
        doc = _make_doc(
            sections=[s],
            source_path="/docs/FP-QAL-11.docx",
            file_format="docx",
        )
        doc.validate()


# ---------------------------------------------------------------------------
# ParsedDocument — validate() invariant violations
# ---------------------------------------------------------------------------

class TestParsedDocumentValidation:
    def test_empty_sections_raises(self):
        doc = _make_doc(sections=[])
        with pytest.raises(ValueError, match="sections must not be empty"):
            doc.validate()

    def test_duplicate_section_ids_raises(self):
        sections = [
            _make_section("section_1"),
            _make_section("section_1"),  # duplicate
        ]
        doc = _make_doc(sections=sections)
        with pytest.raises(ValueError, match="Duplicate ParsedSection.id"):
            doc.validate()

    def test_min_confidence_mismatch_raises(self):
        sections = [_make_section(extraction_confidence=0.8)]
        doc = _make_doc(sections=sections, min_confidence=1.0)  # wrong
        with pytest.raises(ValueError, match="min_confidence mismatch"):
            doc.validate()

    def test_low_quality_flag_wrong_for_clean_doc_raises(self):
        sections = [_make_section(extraction_confidence=1.0)]
        doc = _make_doc(
            sections=sections,
            quality_tier="A",
            min_confidence=1.0,
            low_quality_flag=True,  # should be False
        )
        with pytest.raises(ValueError, match="low_quality_flag"):
            doc.validate()

    def test_low_quality_flag_missing_for_tier_c_raises(self):
        sections = [_make_section(extraction_confidence=0.1)]
        doc = _make_doc(
            sections=sections,
            quality_tier="C",
            min_confidence=0.1,
            low_quality_flag=False,  # should be True
        )
        with pytest.raises(ValueError, match="low_quality_flag"):
            doc.validate()

    def test_file_format_extension_mismatch_raises(self):
        s = _make_section()
        doc = _make_doc(
            sections=[s],
            source_path="/docs/file.docx",
            file_format="pdf",  # mismatch
        )
        with pytest.raises(ValueError, match="file_format"):
            doc.validate()

    def test_all_unknown_sections_raises(self):
        sections = [
            _make_section("s1", SectionType.UNKNOWN),
            _make_section("s2", SectionType.UNKNOWN),
        ]
        doc = _make_doc(sections=sections)
        with pytest.raises(ValueError, match="section_type != UNKNOWN"):
            doc.validate()


# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------

class TestExceptions:
    def test_unsupported_format_error(self):
        with pytest.raises(UnsupportedFormatError):
            raise UnsupportedFormatError("only pdf/docx supported")

    def test_extraction_failed_error(self):
        with pytest.raises(ExtractionFailedError):
            raise ExtractionFailedError("all extractors failed")

    def test_empty_document_error(self):
        with pytest.raises(EmptyDocumentError):
            raise EmptyDocumentError("document yielded no text")


# ---------------------------------------------------------------------------
# Helper used by other test files (kept here as a fixture)
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_parsed_document() -> ParsedDocument:
    """Minimal valid ParsedDocument for use in other test modules."""
    sections = [
        _make_section("section_1", SectionType.SCOPE, page_range=(1, 1)),
        _make_section("section_2", SectionType.PROCEDURE_TEXT, page_range=(2, 5)),
    ]
    return _make_doc(sections=sections)


# ---------------------------------------------------------------------------
# RawPageText
# ---------------------------------------------------------------------------

class TestRawPageText:
    def test_construction_and_fields(self):
        rpt = RawPageText(
            page_number=1,
            text="Some text",
            tables=[[["A", "B"], ["C", "D"]]],
            extraction_method="pdfplumber",
            confidence=1.0,
        )
        assert rpt.page_number == 1
        assert rpt.text == "Some text"
        assert rpt.tables[0][1][0] == "C"
        assert rpt.extraction_method == "pdfplumber"
        assert rpt.confidence == 1.0

    def test_public_import(self):
        from document_parser import RawPageText as RawPageTextPublic
        assert RawPageTextPublic is RawPageText

    def test_empty_tables_allowed(self):
        rpt = RawPageText(
            page_number=2, text="", tables=[], extraction_method="fitz", confidence=0.3
        )
        assert rpt.tables == []
