"""_page_ranges.py — Page range assignment for ParsedSection lists.

Extracted from docling_adapter.py to isolate the page-mapping concern from
section conversion and quality assessment. All public signatures are unchanged;
this module is private to the pdf_parser package.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from .parsed_document import ParsedSection

if TYPE_CHECKING:
    from docling_core.types.doc.document import DoclingDocument

# ---------------------------------------------------------------------------
# Module-level compiled regex constants (never recompiled on each call)
# ---------------------------------------------------------------------------
_RE_NUMBERED_HEADING = re.compile(r"^\s*(\d+([.-]\d+)*)\s*[-.)]?\s+\S+")
_RE_MD_PUNCT         = re.compile(r"[`*_~#>\[\](){}]")
_RE_NON_ALNUM        = re.compile(r"[^a-z0-9]+")
_RE_WS               = re.compile(r"\s+")


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
    return bool(_RE_NUMBERED_HEADING.match(text))


def _get_item_heading_text(item: object) -> str:
    for attr in ("text", "title", "name"):
        value = getattr(item, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_heading_key(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    normalized = _RE_MD_PUNCT.sub(" ", normalized)
    normalized = _RE_NON_ALNUM.sub(" ", normalized)
    normalized = _RE_WS.sub(" ", normalized).strip()
    return normalized


def _heading_keys_match(section_key: str, candidate_key: str) -> bool:
    if section_key == candidate_key:
        return True
    if section_key and candidate_key:
        return section_key in candidate_key or candidate_key in section_key
    return False
