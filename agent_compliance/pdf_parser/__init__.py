"""PDF parsing package built around Docling."""

from .docling_adapter import assess_quality, docling_to_sections
from .docling_parser import ParseResult, parse_document, parse_pdf
from .parsed_document import ParsedSection, SectionType

__all__ = [
    "ParseResult",
    "parse_document",
    "parse_pdf",
    "docling_to_sections",
    "assess_quality",
    "ParsedSection",
    "SectionType",
]
