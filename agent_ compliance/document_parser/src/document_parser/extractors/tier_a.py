"""
tier_a.py — Tier A extractor: clean selectable-text PDFs.

Primary:  pdfplumber (text + tables).
Fallback: PyMuPDF (fitz) when pdfplumber yields < 50 chars on a page.
"""

import warnings
from pathlib import Path

import fitz
import pdfplumber

from document_parser.document_diagnostician import PageMap
from document_parser.parsed_document import RawPageText

_FITZ_FALLBACK_THRESHOLD = 50  # chars


def extract_tier_a(path: Path, page_map: PageMap) -> list[RawPageText]:
    """Extract text and tables from a Tier A (clean) PDF.

    Args:
        path: Absolute path to the PDF file.
        page_map: Diagnostician output describing each page.

    Returns:
        One RawPageText per page in page_map.pages, preserving order.
    """
    results: list[RawPageText] = []

    with pdfplumber.open(str(path)) as pdf, fitz.open(str(path)) as fitz_doc:
        for page_info in page_map.pages:
            idx = page_info.page_number - 1  # 0-indexed

            plumber_page = pdf.pages[idx]
            text = plumber_page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            raw_tables = plumber_page.extract_tables() or []

            # Normalise: None cells → empty string
            tables: list[list[list[str]]] = [
                [[(cell or "") for cell in row] for row in table]
                for table in raw_tables
            ]

            if len(text.strip()) < _FITZ_FALLBACK_THRESHOLD:
                warnings.warn(
                    f"Page {page_info.page_number}: pdfplumber yielded "
                    f"{len(text.strip())} chars — falling back to fitz.",
                    UserWarning,
                    stacklevel=2,  # points warning at caller of extract_tier_a
                )
                text = fitz_doc[idx].get_text()
                method = "fitz"
            else:
                method = "pdfplumber"

            results.append(
                RawPageText(
                    page_number=page_info.page_number,
                    text=text,
                    tables=tables,
                    extraction_method=method,
                    confidence=1.0,
                )
            )

    return results
