from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from .docling_parser import ParseResult
from .parsed_document import ParsedSection, SectionType

if TYPE_CHECKING:
    from docling_core.types.doc.document import DoclingDocument


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

    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    matches = list(heading_pattern.finditer(markdown))

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

    return sections


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

    return sections


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
    blob = f"{title}\n{body}".lower()

    if any(k in blob for k in ("objet", "domaine d'application", "scope")):
        return SectionType.SCOPE
    if any(k in blob for k in ("definition", "définition", "glossaire")):
        return SectionType.DEFINITIONS
    if any(k in blob for k in ("référence", "reference", "documents associés")):
        return SectionType.REFERENCES
    if any(k in blob for k in ("logigramme", "flowchart", "diagram")):
        return SectionType.PROCESS_DIAGRAM
    if any(k in blob for k in ("fiche", "formulaire", "record form")):
        return SectionType.RECORD_FORM
    if any(k in blob for k in ("sommaire", "historique", "approbation", "validation")):
        return SectionType.METADATA
    return SectionType.PROCEDURE_TEXT


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


def _extract_heading_page_candidates(doc: "DoclingDocument") -> list[tuple[str, int]]:
    candidates: list[tuple[str, int]] = []
    iterate_items = getattr(doc, "iterate_items", None)
    if not callable(iterate_items):
        return candidates

    try:
        raw_iter = iterate_items()
    except Exception:
        return candidates

    for entry in raw_iter:
        item = entry[0] if isinstance(entry, tuple) else entry
        page_no = _get_first_page_no(item)
        if page_no is None or not _is_heading_like(item):
            continue

        key = _normalize_heading_key(_get_item_heading_text(item))
        if key:
            candidates.append((key, page_no))
    return candidates


def _assign_page_ranges(
    sections: list[ParsedSection],
    heading_candidates: list[tuple[str, int]],
    total_pages: int,
) -> None:
    starts: list[int] = []
    cursor = 0
    last_start = 1

    for section in sections:
        title_key = _normalize_heading_key(section.title)
        start_page = 1 if section.title.lower() == "preamble" else last_start

        if title_key and section.title.lower() != "preamble":
            for idx in range(cursor, len(heading_candidates)):
                cand_key, cand_page = heading_candidates[idx]
                if _heading_keys_match(title_key, cand_key):
                    start_page = cand_page
                    cursor = idx + 1
                    break

        start_page = max(last_start, start_page)
        starts.append(start_page)
        last_start = start_page

    _apply_ranges_from_starts(sections, starts, total_pages)


def _assign_page_ranges_from_page_texts(
    sections: list[ParsedSection],
    page_texts: list[str],
    total_pages: int,
) -> None:
    if not sections:
        return

    normalized_pages = [_normalize_heading_key(text) for text in page_texts]
    starts: list[int] = []
    cursor = 0
    last_start = 1

    for section in sections:
        title_key = _normalize_heading_key(section.title)
        start_page = 1 if section.title.lower() == "preamble" else last_start

        if title_key and section.title.lower() != "preamble":
            for idx in range(cursor, len(normalized_pages)):
                page_blob = normalized_pages[idx]
                if title_key and title_key in page_blob:
                    start_page = idx + 1
                    cursor = idx
                    break

        start_page = max(last_start, start_page)
        starts.append(start_page)
        last_start = start_page

    _apply_ranges_from_starts(sections, starts, total_pages)


def _apply_ranges_from_starts(
    sections: list[ParsedSection],
    starts: list[int],
    total_pages: int,
) -> None:
    for idx, section in enumerate(sections):
        start_page = starts[idx] if idx < len(starts) else 1
        if idx + 1 < len(starts):
            end_page = max(start_page, starts[idx + 1] - 1)
        else:
            end_page = max(start_page, total_pages)
        section.page_range = (start_page, end_page)


def _get_first_page_no(item: object) -> int | None:
    prov_entries = getattr(item, "prov", None) or []
    for prov in prov_entries:
        page_no = getattr(prov, "page_no", None)
        if isinstance(page_no, int) and page_no >= 1:
            return page_no
    return None


def _is_heading_like(item: object) -> bool:
    label = getattr(item, "label", None)
    label_name = (getattr(label, "name", None) or str(label)).upper()
    if any(token in label_name for token in ("SECTION_HEADER", "TITLE", "HEADING")):
        return True

    text = _get_item_heading_text(item)
    if not text:
        return False
    return bool(re.match(r"^\s*(\d+([.-]\d+)*)\s*[-.)]?\s+\S+", text))


def _get_item_heading_text(item: object) -> str:
    for attr in ("text", "title", "name"):
        value = getattr(item, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_heading_key(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    normalized = normalized.lower()
    normalized = re.sub(r"[`*_~#>\[\](){}]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _heading_keys_match(section_key: str, candidate_key: str) -> bool:
    if section_key == candidate_key:
        return True
    if section_key and candidate_key:
        return section_key in candidate_key or candidate_key in section_key
    return False


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
