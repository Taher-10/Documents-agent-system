# extractors sub-package — populated by M2 modules
from document_parser.extractors.docx import extract_docx
from document_parser.extractors.tier_a import extract_tier_a

__all__ = ["extract_docx", "extract_tier_a"]
