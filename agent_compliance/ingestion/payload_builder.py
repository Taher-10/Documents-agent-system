from __future__ import annotations

from typing import Any

from agent_compliance.pdf_parser.docling_parser import ParseResult
from agent_compliance.pdf_parser.parsed_document import ParsedSection

from .document_meta import DocumentMeta


def build_payload(section: ParsedSection, meta: DocumentMeta, result: ParseResult) -> dict[str, Any]:
    page_start, page_end = section.page_range
    metadata = result.metadata or {}

    return {
        "section_id": section.id,
        "section_type": section.section_type.value,
        "title": section.title,
        "raw_text": section.raw_text,
        "heading_level": section.heading_level,
        "page_start": page_start,
        "page_end": page_end,
        "extraction_confidence": section.extraction_confidence,
        "doc_title": result.title,
        "doc_path": result.source_path,
        "doc_pages": result.pages,
        "page1_fields": metadata.get("page1_fields", {}),
        "doc_id": meta.doc_id,
        "doc_code": meta.doc_code,
        "designation": meta.designation,
        "version": meta.version,
        "doc_type": meta.doc_type,
        "doc_level": meta.doc_level,
        "applicable_norms": meta.applicable_norms,
        "company_id": meta.company_id,
        "site_id": meta.site_id,
    }
