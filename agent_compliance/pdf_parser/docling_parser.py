from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ._cleanup import (
    _normalize_spacing,
    _remove_repeated_headers_footers,
    _remove_repeated_lines_global,
)

# Module-level compiled regex constants used in _extract_page1_metadata_fields
_RE_KV_INLINE   = re.compile(r"^([A-Za-zÀ-ÿ][^:]{1,40})\s*:\s*(.+)$")
_RE_KV_KEY_ONLY = re.compile(r"^([A-Za-zÀ-ÿ][^:]{1,40})\s*:\s*$")


@dataclass(slots=True)
class ParseResult:
    """Structured output returned by the parser for a single source document."""
    source_path: str
    text: str
    pages: int | None = None
    title: str | None = None
    metadata: dict[str, Any] | None = None
    page_texts: list[str] | None = None


def parse_document(
    file_path: str | Path,
    remove_headers_footers: bool = True,
) -> ParseResult:
    """Parse a PDF or DOCX file with Docling and return normalized content."""
    resolved = Path(file_path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {resolved}")
    suffix = resolved.suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise ValueError(f"Expected a .pdf or .docx file, got: {resolved.name}")

    try:
        import torch

        for t in ["uint16", "uint32", "uint64"]:
            if not hasattr(torch, t):
                setattr(torch, t, getattr(torch, "int" + t[4:]))
        if not hasattr(torch, "get_default_device"):
            torch.get_default_device = lambda: torch.device("cpu")
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise ImportError(
            "Docling is not installed. Install it with: pip install docling"
        ) from exc

    converter = DocumentConverter()
    conversion = converter.convert(str(resolved))
    document = conversion.document

    metadata = _extract_metadata(document) or {}
    cleanup: dict[str, Any] = {}

    should_remove_headers_footers = remove_headers_footers and suffix == ".pdf"

    if should_remove_headers_footers:
        document, native_removed = _filter_furniture_native(document)
        if native_removed > 0:
            cleanup["native_furniture_removed"] = native_removed

    raw_text = _extract_text(document)
    page_texts = _extract_page_texts(document, raw_text)
    text = raw_text

    if should_remove_headers_footers and len(page_texts) >= 3:
        cleaned_pages, removed_lines = _remove_repeated_headers_footers(page_texts)
        if removed_lines:
            text = "\n\n".join(page for page in cleaned_pages if page.strip())
            cleanup["headers_footers_removed"] = removed_lines
            cleanup["page_segments"] = len(page_texts)
    if should_remove_headers_footers:
        text, global_removed = _remove_repeated_lines_global(text)
        if global_removed:
            existing = cleanup.get("headers_footers_removed", [])
            merged = list(dict.fromkeys([*existing, *global_removed]))
            cleanup["headers_footers_removed"] = merged
            cleanup["global_line_cleanup"] = len(global_removed)
    text = _normalize_spacing(text)

    if cleanup:
        metadata["cleanup"] = cleanup
    heading_hints = _extract_heading_hints(document)
    if heading_hints:
        metadata["heading_hints"] = heading_hints
    if page_texts:
        page1_fields = _extract_page1_metadata_fields(page_texts[0])
        if page1_fields:
            metadata["page1_fields"] = page1_fields

    return ParseResult(
        source_path=str(resolved),
        text=text,
        pages=_extract_page_count(document),
        title=_extract_title(document),
        metadata=metadata,
        page_texts=page_texts,
    )


def parse_pdf(
    pdf_path: str | Path,
    remove_headers_footers: bool = True,
) -> ParseResult:
    """Parse a PDF file with Docling and return normalized content."""
    resolved = Path(pdf_path)
    if resolved.suffix.lower() != ".pdf":
        raise ValueError(f"parse_pdf expects a .pdf file, got: {resolved.name}")
    return parse_document(pdf_path, remove_headers_footers=remove_headers_footers)


# ---------------------------------------------------------------------------
# Low-level Docling extraction helpers
# ---------------------------------------------------------------------------

def _extract_text(document: Any) -> str:
    """Export the Docling document into a plain string, preferring markdown when available."""
    if hasattr(document, "export_to_markdown"):
        return document.export_to_markdown()
    if hasattr(document, "export_to_text"):
        return document.export_to_text()
    return str(document)


def _filter_furniture_native(document: Any) -> tuple[Any, int]:
    """Remove Docling PAGE_HEADER/PAGE_FOOTER items when furniture labels are available."""
    try:
        from docling_core.types.doc import ContentLayer
        from docling_core.types.doc.labels import DocItemLabel
    except Exception:
        return document, 0

    try:
        to_remove: list[Any] = []
        for item, _ in _iterate_items(
            document,
            included_content_layers={ContentLayer.FURNITURE},
        ):
            label = getattr(item, "label", None)
            if label in (DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER):
                to_remove.append(item)

        if not to_remove:
            return document, 0

        delete_items = getattr(document, "delete_items", None)
        if not callable(delete_items):
            return document, 0

        delete_items(node_items=to_remove)
        return document, len(to_remove)
    except Exception:
        return document, 0


def _extract_page_texts(document: Any, fallback_text: str) -> list[str]:
    """Build one text segment per page using Docling provenance, with text splitting as fallback."""
    try:
        from docling_core.types.doc import ContentLayer

        layers = {ContentLayer.BODY, ContentLayer.FURNITURE}
    except Exception:
        layers = None

    pages_map: dict[int, list[str]] = defaultdict(list)
    try:
        for item, _ in _iterate_items(document, included_content_layers=layers):
            text = _get_item_text(item, document=document)
            if not text:
                continue

            page_nos = _get_item_page_numbers(item)
            if not page_nos:
                continue

            for page_no in page_nos:
                pages_map[page_no].append(text)

        if len(pages_map) >= 2:
            ordered: list[str] = []
            for page_no in sorted(pages_map):
                joined = "\n".join(chunk for chunk in pages_map[page_no] if chunk.strip()).strip()
                if joined:
                    ordered.append(joined)
            if len(ordered) >= 2:
                return ordered
    except Exception:
        pass

    # Form-feed is a common page separator in extracted text.
    if "\f" in fallback_text:
        split_pages = [segment.strip() for segment in fallback_text.split("\f")]
        return [segment for segment in split_pages if segment]

    return [fallback_text] if fallback_text.strip() else []


def _iterate_items(
    document: Any,
    included_content_layers: set[Any] | None = None,
) -> Iterable[tuple[Any, Any]]:
    """Yield Docling items in a normalized `(item, parent)` shape across API variants."""
    iterator = getattr(document, "iterate_items", None)
    if not callable(iterator):
        return []

    try:
        raw_iter = (
            iterator(included_content_layers=included_content_layers)
            if included_content_layers is not None
            else iterator()
        )
    except TypeError:
        raw_iter = iterator()

    normalized: list[tuple[Any, Any]] = []
    for entry in raw_iter:
        if isinstance(entry, tuple) and len(entry) >= 2:
            normalized.append((entry[0], entry[1]))
        else:
            normalized.append((entry, None))
    return normalized


def _get_item_page_numbers(item: Any) -> list[int]:
    """Read page numbers from an item's provenance while preserving the original order."""
    prov_entries = getattr(item, "prov", None) or []
    page_nos: list[int] = []
    for prov_entry in prov_entries:
        page_no = getattr(prov_entry, "page_no", None)
        if isinstance(page_no, int):
            page_nos.append(page_no)

    # Preserve order, remove duplicates.
    seen: set[int] = set()
    unique: list[int] = []
    for page_no in page_nos:
        if page_no not in seen:
            seen.add(page_no)
            unique.append(page_no)
    return unique


def _get_item_text(item: Any, document: Any | None = None) -> str:
    """Extract displayable text from a Docling item using export helpers or the raw `text` field."""
    for attr in ("export_to_markdown", "export_to_text"):
        method = getattr(item, attr, None)
        if callable(method):
            try:
                if document is not None:
                    try:
                        text = method(doc=document)
                    except TypeError:
                        text = method()
                else:
                    text = method()
            except Exception:
                continue
            if isinstance(text, str) and text.strip():
                return text.strip()

    value = getattr(item, "text", None)
    if isinstance(value, str) and value.strip():
        return value.strip()

    return ""


# ---------------------------------------------------------------------------
# Document-level metadata extraction helpers
# ---------------------------------------------------------------------------

def _extract_page_count(document: Any) -> int | None:
    """Return the number of pages when the Docling document exposes a countable pages collection."""
    pages = getattr(document, "pages", None)
    if pages is None:
        return None
    try:
        return len(pages)
    except TypeError:
        return None


def _extract_title(document: Any) -> str | None:
    """Infer a document title from page-one heading items, then fall back to document metadata."""
    section_like = {"SECTION_HEADER", "TITLE", "HEADING"}

    for item, _ in _iterate_items(document):
        if not _is_page_one(item):
            continue

        label = getattr(item, "label", None)
        label_name = getattr(label, "name", None) or str(label)
        if any(token in str(label_name).upper() for token in section_like):
            text = _get_item_text(item)
            if text:
                return text.splitlines()[0].strip()

    name = getattr(document, "name", None)
    if isinstance(name, str) and name.strip():
        return Path(name.strip()).stem

    title = getattr(document, "title", None)
    if isinstance(title, str) and title.strip():
        return title.strip()

    return None


def _is_page_one(item: Any) -> bool:
    """Check whether a Docling item has provenance pointing to the first page."""
    for prov_entry in getattr(item, "prov", None) or []:
        if getattr(prov_entry, "page_no", None) == 1:
            return True
    return False


def _extract_metadata(document: Any) -> dict[str, Any] | None:
    """Return native document metadata when Docling exposes it as a dictionary."""
    metadata = getattr(document, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    return None


def _extract_heading_hints(document: Any) -> list[dict[str, Any]]:
    """Collect title-like items as lightweight section hints with their first known page number."""
    hints: list[dict[str, Any]] = []
    for item, _ in _iterate_items(document):
        label = getattr(item, "label", None)
        label_name = (getattr(label, "name", None) or str(label)).upper()
        if not any(token in label_name for token in ("SECTION_HEADER", "TITLE", "HEADING")):
            continue

        text = _get_item_text(item)
        if not text:
            continue
        title = text.splitlines()[0].strip()
        if not title:
            continue

        page_nos = _get_item_page_numbers(item)
        hints.append(
            {
                "title": title,
                "page": page_nos[0] if page_nos else 1,
            }
        )
    return hints


def _extract_page1_metadata_fields(page_text: str) -> dict[str, str]:
    """Parse selected key-value fields from the first page to enrich returned metadata."""
    fields: dict[str, str] = {}
    if not page_text.strip():
        return fields

    lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    allowed_keys = {
        "service",
        "poste",
        "suppléant",
        "suppleant",
        "poste_parent",
        "code",
        "titre",
        "title",
        "indice",
        "edition",
    }

    i = 0
    while i < len(lines):
        line = lines[i]
        # Support "Key: value" and "Key :" + next-line value patterns.
        inline = _RE_KV_INLINE.match(line)
        if inline:
            key = inline.group(1).strip().lower().replace(" ", "_")
            value = inline.group(2).strip()
            if key in allowed_keys and value:
                fields[key] = value
            i += 1
            continue

        key_only = _RE_KV_KEY_ONLY.match(line)
        if key_only and i + 1 < len(lines):
            key = key_only.group(1).strip().lower().replace(" ", "_")
            nxt = lines[i + 1]
            if key in allowed_keys and ":" not in nxt and len(nxt) <= 120:
                fields[key] = nxt
                i += 2
                continue
        i += 1

    return fields
