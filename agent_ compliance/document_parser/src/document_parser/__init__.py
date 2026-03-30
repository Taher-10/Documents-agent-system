"""
document_parser — QHSE document parser package.

Public API:
    parse_document(path, job_id) -> ParsedDocument   (wired in __init__ after all modules built)

Data models re-exported here for convenience:
"""

from document_parser.parsed_document import (
    EmptyDocumentError,
    ExtractionFailedError,
    ParsedDocument,
    ParsedSection,
    RawPageText,
    SectionType,
    UnsupportedFormatError,
)
from document_parser.document_diagnostician import (
    PageInfo,
    PageMap,
    inspect_document,
)

__all__ = [
    # M6 — Data models
    "ParsedDocument",
    "ParsedSection",
    "RawPageText",
    "SectionType",
    "UnsupportedFormatError",
    "ExtractionFailedError",
    "EmptyDocumentError",
    # M1 — Diagnostician
    "PageInfo",
    "PageMap",
    "inspect_document",
]
