"""
document_diagnostician.py — M1: Per-page triage and quality-tier routing.

Build order: M6 (done) → M1 (this file) → M2-TierA → ...

Public API (planned end-state):
    inspect_document(path: Path) -> PageMap

Current public functions (built so far):
    classify_page_type(page_text, image_count, font_issue) -> Literal["text","image","hybrid"]
    assign_quality_tier(pages) -> Literal["A","B","C"]
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from document_parser.parsed_document import UnsupportedFormatError


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PageInfo:
    """Diagnostic snapshot of a single page.

    Attributes:
        page_number: 1-indexed page number.
        page_type: "text" — selectable text dominant;
                   "image" — image-only, near-zero text;
                   "hybrid" — mixed or degraded.
        has_selectable_text: True if any selectable text was extracted.
        image_count: Number of embedded image objects on this page.
        font_issue: True if non-embedded non-base14 fonts detected (broken encoding risk).
        text_sample: First 200 chars of extracted text (for debugging).
    """

    page_number: int
    page_type: Literal["text", "image", "hybrid"]
    has_selectable_text: bool
    image_count: int
    font_issue: bool
    text_sample: str


@dataclass
class PageMap:
    """Full diagnostic result for one document.

    Attributes:
        total_pages: Total number of pages inspected.
        file_format: "pdf" or "docx".
        quality_tier: "A" = clean, "B" = hybrid/degraded, "C" = full scan.
        pages: Per-page diagnostics, ordered 1…N.
        producer: PDF producer string from metadata (e.g. "Microsoft Word 2016");
                  None for DOCX or when unavailable.
    """

    total_pages: int
    file_format: Literal["pdf", "docx"]
    quality_tier: Literal["A", "B", "C"]
    pages: list[PageInfo]
    producer: str | None


# ---------------------------------------------------------------------------
# Pure classification functions
# ---------------------------------------------------------------------------

def classify_page_type(
    page_text: str,
    image_count: int,
    font_issue: bool,
) -> Literal["text", "image", "hybrid"]:
    """Classify a single page as text, image, or hybrid.

    Rules (in priority order):
    - image:  stripped text length < 30 characters
    - text:   stripped text length > 100 AND no font issue
    - hybrid: everything else (30–100 chars, or >100 with font issue)

    Args:
        page_text: Raw text extracted from the page.
        image_count: Number of embedded image objects on the page. Accepted for
            interface consistency with the diagnostician pipeline; not used by the
            current text-yield rules (image-dominant heuristics are handled via
            the text-length threshold, not image count).
        font_issue: True if non-embedded non-base14 fonts were detected.

    Returns:
        One of "text", "image", "hybrid".
    """
    stripped_len = len(page_text.strip())
    if stripped_len < 30:
        return "image"
    if stripped_len > 100 and not font_issue:
        return "text"
    return "hybrid"


def assign_quality_tier(pages: list[PageInfo]) -> Literal["A", "B", "C"]:
    """Assign an overall quality tier from per-page diagnostics.

    Rules:
    - C: more than 50% of pages are type "image"
    - A: ALL pages are type "text" AND no page has a font issue
    - B: everything else

    Args:
        pages: List of PageInfo objects for every page in the document.

    Returns:
        "A", "B", or "C".
    """
    if not pages:
        return "C"
    total = len(pages)
    image_pages = sum(1 for p in pages if p.page_type == "image")
    if image_pages / total > 0.5:
        return "C"
    if all(p.page_type == "text" and not p.font_issue for p in pages):
        return "A"
    return "B"


# ---------------------------------------------------------------------------
# inspect_document — public entry point
# ---------------------------------------------------------------------------

def inspect_document(path: Path) -> PageMap:
    """Inspect a PDF or DOCX file and return per-page diagnostics + quality tier.

    Does NOT extract full text — only samples enough to classify pages.
    Called before any extractor (M2) runs.

    Args:
        path: Absolute path to a .pdf or .docx file.

    Returns:
        PageMap with total_pages, file_format, quality_tier, per-page PageInfo.

    Raises:
        UnsupportedFormatError: If the file extension is not .pdf or .docx.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _inspect_pdf(path)
    elif suffix == ".docx":
        return _inspect_docx(path)
    else:
        raise UnsupportedFormatError(
            f"Unsupported file format: '{suffix}'. Expected .pdf or .docx."
        )


def _inspect_docx(path: Path) -> PageMap:
    """DOCX documents are always Tier A — treat entire doc as one text page."""
    from docx import Document as DocxDocument  # local import — optional dep

    doc = DocxDocument(str(path))
    full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    page = PageInfo(
        page_number=1,
        page_type="text",
        has_selectable_text=True,
        image_count=0,  # python-docx has no per-page image count at this stage
        font_issue=False,
        text_sample=full_text[:200],
    )
    return PageMap(
        total_pages=1,
        file_format="docx",
        quality_tier="A",
        pages=[page],
        producer=None,
    )


def _inspect_pdf(path: Path) -> PageMap:
    """Inspect a PDF file using PyMuPDF (fitz).

    Font-issue detection: a font is flagged as problematic only if it is NOT a
    base-14 font (xref != 0 means it is a real PDF font object, not a virtual
    base-14 reference) AND it has no embedded font stream (ext == "").
    Base-14 fonts (Helvetica, Times, Courier, …) have xref == 0 and are always
    reliable, so they are excluded from font_issue.

    Args:
        path: Absolute path to a .pdf file.

    Returns:
        PageMap with per-page diagnostics and an overall quality tier.
    """
    import fitz  # local import keeps module importable without fitz installed

    pages_info: list[PageInfo] = []
    with fitz.open(str(path)) as doc:
        producer: str | None = (doc.metadata or {}).get("producer") or None

        for i, page in enumerate(doc, start=1):
            page_text = page.get_text()
            images = page.get_images()
            image_count = len(images)

            # font_issue: font has a PDF object (any xref) but no embedded stream.
            # base-14 built-ins (Helvetica, Times, Courier…) have ext == 'n/a', NOT ''.
            # Truly non-embedded non-standard fonts have ext == '' — these risk garbled text.
            fonts = page.get_fonts(full=False)
            font_issue = any(f[1] == "" for f in fonts)

            page_type = classify_page_type(page_text, image_count, font_issue)
            has_selectable = len(page_text.strip()) > 0

            pages_info.append(PageInfo(
                page_number=i,
                page_type=page_type,
                has_selectable_text=has_selectable,
                image_count=image_count,
                font_issue=font_issue,
                text_sample=page_text[:200],
            ))

    quality_tier = assign_quality_tier(pages_info)

    return PageMap(
        total_pages=len(pages_info),
        file_format="pdf",
        quality_tier=quality_tier,
        pages=pages_info,
        producer=producer,
    )
