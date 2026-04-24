from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from agent_compliance.ingestion.qhse_reader import has_ingested_document, read_document_sections
from agent_compliance.pdf_parser.parsed_document import SectionType


def _point(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(payload=payload)


def test_has_ingested_document_enforces_doc_and_company_filter() -> None:
    qdrant = MagicMock()
    qdrant.count.return_value = SimpleNamespace(count=1)

    found = has_ingested_document(
        qdrant,
        doc_id="doc-123",
        company_id="company-123",
    )

    assert found is True
    count_filter = qdrant.count.call_args.kwargs["count_filter"]
    dumped = count_filter.model_dump()
    keys = {cond["key"] for cond in dumped["must"]}
    assert keys == {"doc_id", "company_id"}


def test_read_document_sections_filters_by_tenant_and_orders_sections() -> None:
    qdrant = MagicMock()
    qdrant.scroll.return_value = (
        [
            _point(
                {
                    "section_id": "sec-b",
                    "section_type": "procedure_text",
                    "title": "B",
                    "raw_text": "text b",
                    "page_start": 2,
                    "page_end": 2,
                    "extraction_confidence": 0.8,
                    "heading_level": 2,
                    "doc_code": "PRO-QHSE-001",
                    "designation": "QHSE Procedure",
                    "version": "02",
                    "doc_type": "procedure",
                    "doc_level": 3,
                    "applicable_norms": ["ISO 14001", "ISO 45001"],
                    "site_id": "site-456",
                    "doc_title": "QHSE Procedure",
                    "doc_pages": 5,
                }
            ),
            _point(
                {
                    "section_id": "sec-a",
                    "section_type": "scope",
                    "title": "A",
                    "raw_text": "text a",
                    "page_start": 1,
                    "page_end": 1,
                    "extraction_confidence": 0.9,
                    "heading_level": 1,
                }
            ),
        ],
        None,
    )

    result = read_document_sections(
        qdrant,
        doc_id="doc-123",
        company_id="company-123",
    )

    scroll_filter = qdrant.scroll.call_args.kwargs["scroll_filter"]
    dumped = scroll_filter.model_dump()
    keys = {cond["key"] for cond in dumped["must"]}
    assert keys == {"doc_id", "company_id"}

    assert [section.id for section in result.sections] == ["sec-a", "sec-b"]
    assert [section.section_type for section in result.sections] == [
        SectionType.SCOPE,
        SectionType.PROCEDURE_TEXT,
    ]
    assert result.metadata == {
        "doc_code": "PRO-QHSE-001",
        "designation": "QHSE Procedure",
        "version": "02",
        "doc_type": "procedure",
        "doc_level": 3,
        "applicable_norms": ["ISO 14001", "ISO 45001"],
        "site_id": "site-456",
        "doc_title": "QHSE Procedure",
        "doc_pages": 5,
    }


def test_read_document_sections_falls_back_to_unknown_section_type() -> None:
    qdrant = MagicMock()
    qdrant.scroll.return_value = (
        [
            _point(
                {
                    "section_id": "sec-1",
                    "section_type": "not-a-valid-type",
                    "title": "Bad type",
                    "raw_text": "txt",
                    "page_start": 1,
                    "page_end": 1,
                    "extraction_confidence": 0.5,
                }
            ),
            _point(
                {
                    "section_id": "sec-2",
                    "title": "Missing type",
                    "raw_text": "txt",
                    "page_start": 1,
                    "page_end": 1,
                    "extraction_confidence": 0.5,
                }
            ),
        ],
        None,
    )

    result = read_document_sections(
        qdrant,
        doc_id="doc-123",
        company_id="company-123",
    )

    assert [section.section_type for section in result.sections] == [
        SectionType.UNKNOWN,
        SectionType.UNKNOWN,
    ]
