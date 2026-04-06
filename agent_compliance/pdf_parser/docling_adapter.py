from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from .docling_parser import ParseResult
from .parsed_document import ParsedSection, SectionType
from ._page_ranges import (
    _assign_page_ranges,
    _assign_page_ranges_from_page_texts,
    _extract_heading_page_candidates,
    _normalize_heading_key,
)

if TYPE_CHECKING:
    from docling_core.types.doc.document import DoclingDocument

# Module-level compiled regex constant used in _split_markdown_into_sections
_RE_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def docling_to_sections(source: "DoclingDocument | ParseResult") -> list[ParsedSection]:
    """Convert Docling output into a flat list of ParsedSection objects.

    Preferred input is ParseResult (output of parse_pdf), but raw DoclingDocument
    is also supported for compatibility.
    """
    if isinstance(source, ParseResult):
        markdown = source.text or ""
        sections = _split_markdown_into_sections(markdown)
        metadata = source.metadata or {}
        hint_titles = _extract_hint_titles(metadata)
        if len(sections) <= 1:
            sections = _split_plaintext_into_sections(markdown, hint_titles=hint_titles)
        total_pages = max(1, int(source.pages or len(source.page_texts or []) or 1))
        if sections:
            _promote_metadata_preamble(sections, metadata)
            _assign_page_ranges_from_page_texts(sections, source.page_texts or [], total_pages)
            return sections

        fallback = markdown.strip()
        return [
            ParsedSection(
                id="section_document_1",
                section_type=SectionType.UNKNOWN,
                title="Document",
                raw_text=fallback,
                page_range=(1, total_pages),
                extraction_confidence=_estimate_confidence(fallback),
                heading_level=1,
            )
        ]

    doc = source
    markdown = ""
    export_to_markdown = getattr(doc, "export_to_markdown", None)
    if callable(export_to_markdown):
        markdown = export_to_markdown() or ""

    sections = _split_markdown_into_sections(markdown)
    if sections:
        total_pages = _extract_total_pages(doc)
        heading_candidates = _extract_heading_page_candidates(doc)
        _assign_page_ranges(sections, heading_candidates, total_pages)
        return sections

    export_to_text = getattr(doc, "export_to_text", None)
    fallback = export_to_text() if callable(export_to_text) else ""
    fallback = fallback.strip() or markdown.strip()

    total_pages = _extract_total_pages(doc)
    return [
        ParsedSection(
            id="section_document_1",
            section_type=SectionType.UNKNOWN,
            title="Document",
            raw_text=fallback,
            page_range=(1, total_pages),
            extraction_confidence=_estimate_confidence(fallback),
            heading_level=1,
        )
    ]


def _split_markdown_into_sections(markdown: str) -> list[ParsedSection]:
    """Split markdown text on heading boundaries into ParsedSection objects."""
    if not markdown or not markdown.strip():
        return []

    matches = list(_RE_MD_HEADING.finditer(markdown))

    if not matches:
        body = markdown.strip()
        if not body:
            return []
        return [
            ParsedSection(
                id="section_document_1",
                section_type=SectionType.UNKNOWN,
                title="Document",
                raw_text=body,
                page_range=(1, 1),
                extraction_confidence=_estimate_confidence(body),
                heading_level=1,
            )
        ]

    sections: list[ParsedSection] = []
    preamble = markdown[: matches[0].start()].strip()
    index = 1
    if preamble:
        sections.append(
            ParsedSection(
                id="section_preamble_1",
                section_type=SectionType.METADATA,
                title="Preamble",
                raw_text=preamble,
                page_range=(1, 1),
                extraction_confidence=_estimate_confidence(preamble),
                heading_level=1,
            )
        )
        index += 1

    for i, match in enumerate(matches):
        hashes = match.group(1)
        title = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()

        sections.append(
            ParsedSection(
                id=_make_section_id(title, index),
                section_type=_classify_section_type(title, body),
                title=title or f"Section {index}",
                raw_text=body,
                page_range=(1, 1),
                extraction_confidence=_estimate_confidence(body),
                heading_level=len(hashes),
            )
        )
        index += 1

    return _drop_noise_sections(sections)


def _split_plaintext_into_sections(
    text: str,
    hint_titles: list[str] | None = None,
) -> list[ParsedSection]:
    """Fallback splitter for form-like docs without markdown headings."""
    if not text or not text.strip():
        return []

    lines = [line.strip() for line in text.splitlines()]
    heading_indices: list[int] = []
    for idx, line in enumerate(lines):
        if _is_plain_heading_line(line, hint_titles=hint_titles):
            heading_indices.append(idx)

    if not heading_indices:
        body = text.strip()
        return [
            ParsedSection(
                id="section_document_1",
                section_type=SectionType.UNKNOWN,
                title="Document",
                raw_text=body,
                page_range=(1, 1),
                extraction_confidence=_estimate_confidence(body),
                heading_level=1,
            )
        ]

    sections: list[ParsedSection] = []
    index = 1

    preamble = "\n".join(lines[: heading_indices[0]]).strip()
    if preamble:
        sections.append(
            ParsedSection(
                id="section_preamble_1",
                section_type=SectionType.METADATA,
                title="Preamble",
                raw_text=preamble,
                page_range=(1, 1),
                extraction_confidence=_estimate_confidence(preamble),
                heading_level=1,
            )
        )
        index += 1

    for i, start_idx in enumerate(heading_indices):
        end_idx = heading_indices[i + 1] if i + 1 < len(heading_indices) else len(lines)
        title = lines[start_idx]
        body = "\n".join(lines[start_idx + 1 : end_idx]).strip()
        sections.append(
            ParsedSection(
                id=_make_section_id(title, index),
                section_type=_classify_section_type(title, body),
                title=title,
                raw_text=body,
                page_range=(1, 1),
                extraction_confidence=_estimate_confidence(body),
                heading_level=2,
            )
        )
        index += 1

    # Drop trailing empty sections that are usually heading artifacts.
    while sections and not sections[-1].raw_text.strip():
        sections.pop()

    return _drop_noise_sections(sections)


def _is_plain_heading_line(
    line: str,
    hint_titles: list[str] | None = None,
) -> bool:
    if not line:
        return False
    if len(line) > 64:
        return False
    if line.endswith((".", ";", ":", "!", "?")):
        return False

    normalized = _normalize_heading_key(line)
    if not normalized:
        return False

    known = {
        "objectifs de poste",
        "missions",
        "taches",
        "consignes aux postes",
        "profil",
        "competences",
        "experience",
        "aptitude physique",
    }
    hint_set = {_normalize_heading_key(title) for title in (hint_titles or [])}
    hint_set = {k for k in hint_set if k}
    if normalized in hint_set:
        return True
    return normalized in known


def _make_section_id(title: str, index: int) -> str:
    """Create a stable, unique section ID from the heading title."""
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if not normalized:
        normalized = f"section_{index}"
    return f"section_{normalized}_{index}"


def assess_quality(
    sections: list[ParsedSection],
) -> tuple[str, float, bool]:
    """Determine quality tier from section confidence scores."""
    if not sections:
        return ("C", 0.0, True)

    confidences = [float(s.extraction_confidence) for s in sections]
    min_confidence = min(confidences) if confidences else 0.0

    short_sections = 0
    empty_sections = 0
    for section in sections:
        text = section.raw_text.strip()
        if not text:
            empty_sections += 1
            short_sections += 1
            continue
        if len(text) < 40:
            short_sections += 1

    empty_ratio = empty_sections / len(sections)
    short_ratio = short_sections / len(sections)

    if empty_ratio >= 0.5:
        tier = "C"
        min_confidence = min(min_confidence, 0.5)
    elif short_ratio >= 0.25:
        tier = "B"
        min_confidence = min(min_confidence, 0.8)
    else:
        tier = "A"
        min_confidence = max(min_confidence, 1.0)

    low_quality_flag = tier == "C" or min_confidence < 0.65
    return (tier, float(min_confidence), low_quality_flag)


def _classify_section_type(title: str, body: str) -> SectionType:
    title_lower = title.lower()
    blob = f"{title}\n{body}".lower()

    # Title-only checks prevent body text from triggering wrong types.
    # e.g. "Scope: All projects" in body must not classify the section as SCOPE.
    if any(k in title_lower for k in ("objet", "domaine d'application", "scope")):
        return SectionType.SCOPE
    if any(k in title_lower for k in ("definition", "définition", "glossaire")):
        return SectionType.DEFINITIONS
    if any(k in title_lower for k in ("référence", "reference", "documents associés")):
        return SectionType.REFERENCES
    if any(k in blob for k in ("logigramme", "flowchart", "diagram")):
        return SectionType.PROCESS_DIAGRAM
    if any(k in blob for k in ("fiche", "formulaire", "record form")):
        return SectionType.RECORD_FORM
    if any(k in blob for k in ("sommaire", "historique", "approbation", "validation")):
        return SectionType.METADATA
    return SectionType.PROCEDURE_TEXT


def _drop_noise_sections(sections: list[ParsedSection]) -> list[ParsedSection]:
    """Remove repeated empty-body sections (e.g. page footers turned into headings).

    A section is considered noise when its body is empty AND the same title
    appears more than once across the list — a clear sign of a repeated
    header/footer that the PDF extractor mistook for a heading.
    """
    from collections import Counter
    title_counts = Counter(s.title for s in sections if not s.raw_text.strip())
    return [
        s for s in sections
        if s.raw_text.strip() or title_counts[s.title] < 2
    ]


def _estimate_confidence(text: str) -> float:
    clean = text.strip()
    if not clean:
        return 0.55
    if len(clean) < 40:
        return 0.75
    if len(clean) < 120:
        return 0.9
    return 1.0


def _extract_total_pages(doc: "DoclingDocument") -> int:
    pages = getattr(doc, "pages", None)
    if pages is None:
        return 1
    try:
        count = len(pages)
    except TypeError:
        return 1
    return max(1, int(count))


def _extract_hint_titles(metadata: dict) -> list[str]:
    hints = metadata.get("heading_hints", [])
    titles: list[str] = []
    if isinstance(hints, list):
        for hint in hints:
            if isinstance(hint, dict):
                title = hint.get("title")
                if isinstance(title, str) and title.strip():
                    titles.append(title.strip())
    return titles


def _promote_metadata_preamble(sections: list[ParsedSection], metadata: dict) -> None:
    if not sections:
        return
    page1_fields = metadata.get("page1_fields", {})
    if not isinstance(page1_fields, dict) or not page1_fields:
        return
    first = sections[0]
    if first.section_type != SectionType.METADATA:
        return
    # Keep raw text readable but append normalized key/value summary for agents.
    kv_lines = [f"{k}: {v}" for k, v in page1_fields.items() if isinstance(v, str)]
    if kv_lines:
        summary = "\n".join(kv_lines)
        if summary not in first.raw_text:
            first.raw_text = f"{first.raw_text}\n\n{summary}".strip()
