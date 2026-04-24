from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent_compliance.ingestion.document_meta import DocumentMeta
from agent_compliance.ingestion.payload_builder import build_payload
from agent_compliance.ingestion.qhse_ingester import (
    IngestionError,
    ensure_qhse_collection,
    has_ingested_document,
    ingest_document,
)
from agent_compliance.ingestion.utils import stable_uuid
from agent_compliance.pdf_parser.docling_parser import ParseResult
from agent_compliance.pdf_parser.parsed_document import ParsedSection, SectionType


def _meta() -> DocumentMeta:
    return DocumentMeta(
        doc_id="doc-123",
        doc_code="PRO-QHSE-001",
        designation="QHSE Procedure",
        version="02",
        file_path="/tmp/qhse.pdf",
        doc_type="procedure",
        doc_level=3,
        applicable_norms=["ISO 14001", "ISO 45001"],
        company_id="company-123",
        site_id="site-456",
    )


def _parse_result() -> ParseResult:
    return ParseResult(
        source_path="/tmp/qhse.pdf",
        text="parsed text",
        pages=3,
        title="QHSE Procedure",
        metadata={"page1_fields": {"owner": "quality"}},
    )


def _section(
    section_id: str,
    *,
    text: str,
    confidence: float = 1.0,
    section_type: SectionType = SectionType.PROCEDURE_TEXT,
) -> ParsedSection:
    return ParsedSection(
        id=section_id,
        section_type=section_type,
        title=f"Title {section_id}",
        raw_text=text,
        page_range=(1, 2),
        extraction_confidence=confidence,
        heading_level=2,
    )


def test_stable_uuid_is_deterministic() -> None:
    assert stable_uuid("doc-1", "sec-1") == stable_uuid("doc-1", "sec-1")
    assert stable_uuid("doc-1", "sec-1") != stable_uuid("doc-1", "sec-2")
    assert stable_uuid("doc-1", "sec-1") != stable_uuid("doc-2", "sec-1")


def test_build_payload_includes_required_fields() -> None:
    payload = build_payload(_section("sec-1", text="body"), _meta(), _parse_result())

    assert payload["section_id"] == "sec-1"
    assert payload["section_type"] == "procedure_text"
    assert payload["doc_id"] == "doc-123"
    assert payload["doc_code"] == "PRO-QHSE-001"
    assert payload["doc_type"] == "procedure"
    assert payload["doc_level"] == 3
    assert payload["applicable_norms"] == ["ISO 14001", "ISO 45001"]
    assert payload["company_id"] == "company-123"
    assert payload["site_id"] == "site-456"
    assert payload["doc_path"] == "/tmp/qhse.pdf"
    assert payload["page1_fields"] == {"owner": "quality"}


def test_ensure_qhse_collection_creates_collection_and_indexes() -> None:
    qdrant = MagicMock()
    qdrant.get_collections.return_value = SimpleNamespace(collections=[])

    ensure_qhse_collection(qdrant)

    assert qdrant.create_collection.call_count == 1
    assert qdrant.create_payload_index.call_count == 5
    vector_size = qdrant.create_collection.call_args.kwargs["vectors_config"].size
    assert vector_size == 1024


def test_ensure_qhse_collection_rejects_existing_size_mismatch() -> None:
    qdrant = MagicMock()
    qdrant.get_collections.return_value = SimpleNamespace(
        collections=[SimpleNamespace(name="qhse_sections")]
    )
    qdrant.get_collection.return_value = SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(vectors=SimpleNamespace(size=768))
        )
    )

    with pytest.raises(IngestionError, match="vector size 768"):
        ensure_qhse_collection(qdrant)


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


def test_ingest_document_skips_entire_tier_c_document(monkeypatch: pytest.MonkeyPatch) -> None:
    qdrant = MagicMock()
    sections = [_section("sec-1", text="A"), _section("sec-2", text="B")]

    from agent_compliance.ingestion import qhse_ingester

    monkeypatch.setattr(qhse_ingester, "ensure_qhse_collection", lambda *args, **kwargs: None)
    monkeypatch.setattr(qhse_ingester, "_parse_sections", lambda _path: (_parse_result(), sections))
    monkeypatch.setattr(qhse_ingester, "assess_quality", lambda _sections: ("C", 0.45, True))

    result = ingest_document(_meta(), qdrant, embed_fn=lambda _text: [0.1] * 1024)

    assert result.ingested == 0
    assert result.skipped_quality_gate == 2
    assert result.reason == "low_quality_document"
    qdrant.upsert.assert_not_called()


def test_ingest_document_filters_low_confidence_and_empty_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qdrant = MagicMock()
    sections = [
        _section("sec-empty", text="   ", confidence=1.0),
        _section("sec-low", text="Too low", confidence=0.59),
        _section("sec-ok", text="Good section", confidence=0.99),
    ]

    from agent_compliance.ingestion import qhse_ingester

    monkeypatch.setattr(qhse_ingester, "ensure_qhse_collection", lambda *args, **kwargs: None)
    monkeypatch.setattr(qhse_ingester, "_parse_sections", lambda _path: (_parse_result(), sections))
    monkeypatch.setattr(qhse_ingester, "assess_quality", lambda _sections: ("A", 0.99, False))

    result = ingest_document(_meta(), qdrant, embed_fn=lambda _text: [0.1] * 1024)

    assert result.ingested == 1
    assert result.skipped_empty_text == 1
    assert result.skipped_low_confidence == 1
    assert result.skipped_embed_error == 0
    assert result.reason is None

    points = qdrant.upsert.call_args.kwargs["points"]
    assert len(points) == 1
    assert points[0].id == stable_uuid("doc-123", "sec-ok")
    assert points[0].payload["doc_id"] == "doc-123"


def test_ingest_document_skips_embed_errors_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qdrant = MagicMock()
    sections = [
        _section("sec-fail", text="Will fail", confidence=0.99),
        _section("sec-ok", text="Will pass", confidence=0.99),
    ]

    from agent_compliance.ingestion import qhse_ingester

    monkeypatch.setattr(qhse_ingester, "ensure_qhse_collection", lambda *args, **kwargs: None)
    monkeypatch.setattr(qhse_ingester, "_parse_sections", lambda _path: (_parse_result(), sections))
    monkeypatch.setattr(qhse_ingester, "assess_quality", lambda _sections: ("A", 0.99, False))

    def _embed(text: str) -> list[float]:
        if "fail" in text.lower():
            raise RuntimeError("embed error")
        return [0.2] * 1024

    result = ingest_document(_meta(), qdrant, embed_fn=_embed)

    assert result.ingested == 1
    assert result.skipped_embed_error == 1
    points = qdrant.upsert.call_args.kwargs["points"]
    assert len(points) == 1
    assert points[0].id == stable_uuid("doc-123", "sec-ok")


def test_ingest_document_rejects_wrong_vector_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qdrant = MagicMock()
    sections = [_section("sec-1", text="Some text", confidence=0.99)]

    from agent_compliance.ingestion import qhse_ingester

    monkeypatch.setattr(qhse_ingester, "ensure_qhse_collection", lambda *args, **kwargs: None)
    monkeypatch.setattr(qhse_ingester, "_parse_sections", lambda _path: (_parse_result(), sections))
    monkeypatch.setattr(qhse_ingester, "assess_quality", lambda _sections: ("A", 0.99, False))

    with pytest.raises(IngestionError, match="Embedding vector size 768"):
        ingest_document(_meta(), qdrant, embed_fn=lambda _text: [0.1] * 768)

    qdrant.upsert.assert_not_called()
