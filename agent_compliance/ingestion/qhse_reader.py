from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from agent_compliance.pdf_parser.parsed_document import ParsedSection, SectionType


QHSE_COLLECTION_NAME = "qhse_sections"


class SectionReadMetadata(TypedDict):
    doc_code: str | None
    designation: str | None
    version: str | None
    doc_type: str | None
    doc_level: int | None
    applicable_norms: list[str]
    site_id: str | None
    doc_title: str | None
    doc_pages: int | None


@dataclass(slots=True)
class RetrievedSections:
    doc_id: str
    company_id: str
    sections: list[ParsedSection]
    metadata: SectionReadMetadata


def _tenant_doc_filter(doc_id: str, company_id: str) -> Filter:
    return Filter(
        must=[
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            FieldCondition(key="company_id", match=MatchValue(value=company_id)),
        ]
    )


def has_ingested_document(
    qdrant_client: QdrantClient,
    *,
    doc_id: str,
    company_id: str,
    collection: str = QHSE_COLLECTION_NAME,
) -> bool:
    result = qdrant_client.count(
        collection_name=collection,
        count_filter=_tenant_doc_filter(doc_id=doc_id, company_id=company_id),
        exact=True,
    )
    count = int(getattr(result, "count", 0) or 0)
    return count > 0


def _metadata_defaults() -> SectionReadMetadata:
    return {
        "doc_code": None,
        "designation": None,
        "version": None,
        "doc_type": None,
        "doc_level": None,
        "applicable_norms": [],
        "site_id": None,
        "doc_title": None,
        "doc_pages": None,
    }


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_section_type(value: Any) -> SectionType:
    if isinstance(value, SectionType):
        return value
    if isinstance(value, str):
        try:
            return SectionType(value)
        except ValueError:
            return SectionType.UNKNOWN
    return SectionType.UNKNOWN


def _payload_to_section(payload: dict[str, Any]) -> ParsedSection:
    page_start = _safe_int(payload.get("page_start"), 0)
    page_end = _safe_int(payload.get("page_end"), page_start)
    return ParsedSection(
        id=str(payload.get("section_id") or ""),
        section_type=_to_section_type(payload.get("section_type")),
        title=str(payload.get("title") or ""),
        raw_text=str(payload.get("raw_text") or ""),
        page_range=(page_start, page_end),
        extraction_confidence=float(payload.get("extraction_confidence") or 0.0),
        heading_level=_safe_int(payload.get("heading_level"), 1),
    )


def _payload_to_metadata(payload: dict[str, Any]) -> SectionReadMetadata:
    norms = payload.get("applicable_norms")
    applicable_norms = [str(item) for item in norms] if isinstance(norms, list) else []
    return {
        "doc_code": str(payload["doc_code"]) if payload.get("doc_code") is not None else None,
        "designation": str(payload["designation"]) if payload.get("designation") is not None else None,
        "version": str(payload["version"]) if payload.get("version") is not None else None,
        "doc_type": str(payload["doc_type"]) if payload.get("doc_type") is not None else None,
        "doc_level": _safe_int(payload.get("doc_level"), 0) if payload.get("doc_level") is not None else None,
        "applicable_norms": applicable_norms,
        "site_id": str(payload["site_id"]) if payload.get("site_id") is not None else None,
        "doc_title": str(payload["doc_title"]) if payload.get("doc_title") is not None else None,
        "doc_pages": _safe_int(payload.get("doc_pages"), 0) if payload.get("doc_pages") is not None else None,
    }


def read_document_sections(
    qdrant_client: QdrantClient,
    *,
    doc_id: str,
    company_id: str,
    collection: str = QHSE_COLLECTION_NAME,
    limit: int = 2048,
) -> RetrievedSections:
    if limit <= 0:
        return RetrievedSections(
            doc_id=doc_id,
            company_id=company_id,
            sections=[],
            metadata=_metadata_defaults(),
        )

    scroll_filter = _tenant_doc_filter(doc_id=doc_id, company_id=company_id)
    points: list[Any] = []
    offset: Any = None

    while len(points) < limit:
        page_limit = min(256, limit - len(points))
        batch, next_offset = qdrant_client.scroll(
            collection_name=collection,
            scroll_filter=scroll_filter,
            limit=page_limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points.extend(batch or [])
        if next_offset is None:
            break
        offset = next_offset

    metadata = _metadata_defaults()
    sections: list[ParsedSection] = []
    for point in points:
        payload = getattr(point, "payload", None)
        if not isinstance(payload, dict):
            continue
        if not sections:
            metadata = _payload_to_metadata(payload)
        sections.append(_payload_to_section(payload))

    sections.sort(key=lambda section: (section.page_range[0], section.id))
    return RetrievedSections(
        doc_id=doc_id,
        company_id=company_id,
        sections=sections,
        metadata=metadata,
    )
