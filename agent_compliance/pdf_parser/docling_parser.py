from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(slots=True)
class ParseResult:
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


def _extract_text(document: Any) -> str:
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


def _remove_repeated_headers_footers(
    page_texts: list[str],
    probe_lines: int = 5,
    min_ratio: float = 0.6,
) -> tuple[list[str], list[str]]:
    threshold = max(2, math.ceil(len(page_texts) * min_ratio))

    stripped_pages = [
        [line.strip() for line in page_text.splitlines() if line.strip()]
        for page_text in page_texts
    ]

    header_counts: Counter[str] = Counter()
    footer_counts: Counter[str] = Counter()
    canonical_to_original: dict[str, str] = {}

    for lines in stripped_pages:
        if not lines:
            continue

        for line in lines[:probe_lines]:
            canonical = _canonicalize_line(line)
            if canonical:
                header_counts[canonical] += 1
                canonical_to_original.setdefault(canonical, line)

        for line in lines[-probe_lines:]:
            canonical = _canonicalize_line(line)
            if canonical:
                footer_counts[canonical] += 1
                canonical_to_original.setdefault(canonical, line)

    header_candidates = {k for k, v in header_counts.items() if v >= threshold}
    footer_candidates = {k for k, v in footer_counts.items() if v >= threshold}

    header_blocks = _find_repeated_blocks(
        stripped_pages,
        probe_lines=probe_lines,
        threshold=threshold,
        from_top=True,
    )
    footer_blocks = _find_repeated_blocks(
        stripped_pages,
        probe_lines=probe_lines,
        threshold=threshold,
        from_top=False,
    )

    if (
        not header_candidates
        and not footer_candidates
        and not header_blocks
        and not footer_blocks
    ):
        return page_texts, []

    global_candidates = set(header_candidates) | set(footer_candidates)
    for block in header_blocks + footer_blocks:
        global_candidates.update(block)

    cleaned_pages: list[str] = []
    removed_lines: set[str] = set()

    for lines in stripped_pages:
        if not lines:
            cleaned_pages.append("")
            continue

        top_cut = _top_cut_size(lines, probe_lines, header_candidates, header_blocks)
        bottom_cut = _bottom_cut_size(
            lines,
            probe_lines,
            footer_candidates,
            footer_blocks,
            already_cut_top=top_cut,
        )

        kept = lines[top_cut : len(lines) - bottom_cut if bottom_cut else len(lines)]
        # In some docs, extraction order may interleave header/footer lines inside page text.
        # Remove detected repeated candidates anywhere in the page segment as a final cleanup.
        kept = [
            line
            for line in kept
            if _canonicalize_line(line) not in global_candidates
        ]
        removed_lines.update(lines[:top_cut])
        if bottom_cut:
            removed_lines.update(lines[-bottom_cut:])
        for line in lines:
            if _canonicalize_line(line) in global_candidates and line not in kept:
                removed_lines.add(line)

        cleaned_pages.append("\n".join(kept).strip())

    ordered_removed = _order_removed_lines(
        removed_lines,
        canonical_to_original,
        header_candidates,
        footer_candidates,
        header_blocks,
        footer_blocks,
    )

    return cleaned_pages, ordered_removed


def _find_repeated_blocks(
    stripped_pages: list[list[str]],
    probe_lines: int,
    threshold: int,
    from_top: bool,
) -> list[tuple[str, ...]]:
    counts: Counter[tuple[str, ...]] = Counter()
    for lines in stripped_pages:
        if len(lines) < 2:
            continue

        candidate_lines = lines[:probe_lines] if from_top else lines[-probe_lines:]
        canon = [_canonicalize_line(line) for line in candidate_lines]

        for size in range(2, min(len(canon), probe_lines) + 1):
            block = tuple(canon[:size] if from_top else canon[-size:])
            if all(block):
                counts[block] += 1

    candidates = [block for block, count in counts.items() if count >= threshold]
    candidates.sort(key=len, reverse=True)
    return candidates


def _top_cut_size(
    lines: list[str],
    probe_lines: int,
    header_candidates: set[str],
    header_blocks: list[tuple[str, ...]],
) -> int:
    max_scan = min(len(lines), probe_lines)
    canonical = [_canonicalize_line(line) for line in lines[:max_scan]]

    for block in header_blocks:
        block_size = len(block)
        if block_size <= len(canonical) and tuple(canonical[:block_size]) == block:
            return block_size

    cut = 0
    while cut < max_scan:
        if canonical[cut] and canonical[cut] in header_candidates:
            cut += 1
            continue
        break
    return cut


def _bottom_cut_size(
    lines: list[str],
    probe_lines: int,
    footer_candidates: set[str],
    footer_blocks: list[tuple[str, ...]],
    already_cut_top: int,
) -> int:
    remaining = lines[already_cut_top:]
    max_scan = min(len(remaining), probe_lines)
    if max_scan <= 0:
        return 0

    canonical_tail = [_canonicalize_line(line) for line in remaining[-max_scan:]]

    for block in footer_blocks:
        block_size = len(block)
        if block_size <= len(canonical_tail) and tuple(canonical_tail[-block_size:]) == block:
            return block_size

    cut = 0
    idx = len(canonical_tail) - 1
    while idx >= 0:
        value = canonical_tail[idx]
        if value and value in footer_candidates:
            cut += 1
            idx -= 1
            continue
        break
    return cut


def _order_removed_lines(
    removed_lines: set[str],
    canonical_to_original: dict[str, str],
    header_candidates: set[str],
    footer_candidates: set[str],
    header_blocks: list[tuple[str, ...]],
    footer_blocks: list[tuple[str, ...]],
) -> list[str]:
    ordered: list[str] = []

    canonical_order = sorted(header_candidates | footer_candidates)
    for canonical in canonical_order:
        original = canonical_to_original.get(canonical)
        if original and original in removed_lines and original not in ordered:
            ordered.append(original)

    for block in header_blocks + footer_blocks:
        for canonical in block:
            original = canonical_to_original.get(canonical)
            if original and original in removed_lines and original not in ordered:
                ordered.append(original)

    for line in sorted(removed_lines):
        if line not in ordered:
            ordered.append(line)

    return ordered


def _canonicalize_line(line: str) -> str:
    canonical = line.lower().strip()
    canonical = re.sub(r"\|", " ", canonical)
    canonical = re.sub(r"\s+", " ", canonical).strip()

    separator_probe = canonical.replace(" ", "")
    if separator_probe and re.fullmatch(r"[-:]+", separator_probe):
        return ""

    canonical = re.sub(r"\d+", "<num>", canonical)
    canonical = re.sub(r"\s+", " ", canonical).strip(" -:")

    # Ignore very short tokens to reduce false positives.
    if len(canonical) < 6:
        return ""
    return canonical


def _remove_repeated_lines_global(
    text: str,
    min_repeats: int = 2,
) -> tuple[str, list[str]]:
    lines = text.splitlines()
    if len(lines) < 20:
        return text, []

    canonical_to_line: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for line in lines:
        canonical = _canonicalize_line(line)
        if not canonical:
            continue
        counts[canonical] += 1
        canonical_to_line.setdefault(canonical, line.strip())

    def is_header_footer_signature(line: str) -> bool:
        lowered = line.lower()
        if "|" in line:
            return True
        markers = ("edition", "indice", "code", "page:", "page ", "footer", "header")
        if any(marker in lowered for marker in markers):
            return True
        if "procédure de gestion des gabarits" in lowered:
            return True
        return False

    candidates: set[str] = set()
    for canonical, count in counts.items():
        if count < min_repeats:
            continue
        sample = canonical_to_line.get(canonical, "")
        if sample and is_header_footer_signature(sample):
            candidates.add(canonical)

    if not candidates:
        return text, []

    remove_idx: set[int] = set()
    for idx, line in enumerate(lines):
        canonical = _canonicalize_line(line)
        if canonical in candidates:
            remove_idx.add(idx)

    for idx, line in enumerate(lines):
        if idx in remove_idx:
            continue
        compact = re.sub(r"[|\\s]", "", line)
        if compact and re.fullmatch(r"[-:]+", compact):
            if (idx - 1 in remove_idx) or (idx + 1 in remove_idx):
                remove_idx.add(idx)

    cleaned_lines: list[str] = []
    removed_lines: set[str] = set()
    for idx, line in enumerate(lines):
        if idx in remove_idx:
            if line.strip():
                removed_lines.add(line.strip())
            continue
        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines).strip()
    return cleaned_text, sorted(removed_lines)


def _normalize_spacing(text: str) -> str:
    # Normalize whitespace artifacts introduced by line removal passes.
    normalized = re.sub(r"[ \t]+\n", "\n", text)
    normalized = re.sub(r"\n[ \t]+\n", "\n\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _extract_page_count(document: Any) -> int | None:
    pages = getattr(document, "pages", None)
    if pages is None:
        return None
    try:
        return len(pages)
    except TypeError:
        return None


def _extract_title(document: Any) -> str | None:
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
    for prov_entry in getattr(item, "prov", None) or []:
        if getattr(prov_entry, "page_no", None) == 1:
            return True
    return False


def _extract_metadata(document: Any) -> dict[str, Any] | None:
    metadata = getattr(document, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    return None


def _extract_heading_hints(document: Any) -> list[dict[str, Any]]:
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
        inline = re.match(r"^([A-Za-zÀ-ÿ][^:]{1,40})\s*:\s*(.+)$", line)
        if inline:
            key = inline.group(1).strip().lower().replace(" ", "_")
            value = inline.group(2).strip()
            if key in allowed_keys and value:
                fields[key] = value
            i += 1
            continue

        key_only = re.match(r"^([A-Za-zÀ-ÿ][^:]{1,40})\s*:\s*$", line)
        if key_only and i + 1 < len(lines):
            key = key_only.group(1).strip().lower().replace(" ", "_")
            nxt = lines[i + 1]
            if key in allowed_keys and ":" not in nxt and len(nxt) <= 120:
                fields[key] = nxt
                i += 2
                continue
        i += 1

    return fields
