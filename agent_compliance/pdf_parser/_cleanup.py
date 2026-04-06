"""_cleanup.py — Multi-pass furniture removal for PDF text.

Extracted from docling_parser.py to isolate the cleanup concern from
Docling wrapping and low-level extraction. All public signatures are
unchanged; this module is private to the pdf_parser package.
"""

from __future__ import annotations

import math
import re
from collections import Counter

# ---------------------------------------------------------------------------
# Module-level compiled regex constants (never recompiled on each call)
# ---------------------------------------------------------------------------
_RE_PIPE      = re.compile(r"\|")
_RE_WS        = re.compile(r"\s+")
_RE_SEPARATOR = re.compile(r"[-:]+")
_RE_DIGITS    = re.compile(r"\d+")
_RE_BARS      = re.compile(r"[|\\s]")
_RE_NL_TRAIL  = re.compile(r"[ \t]+\n")
_RE_NL_BLANK  = re.compile(r"\n[ \t]+\n")
_RE_NL_MULTI  = re.compile(r"\n{3,}")


def _remove_repeated_headers_footers(
    page_texts: list[str],
    probe_lines: int = 5,
    min_ratio: float = 0.6,
) -> tuple[list[str], list[str]]:
    """Detect repeated page-edge content and remove likely headers and footers from each page."""
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

        # Compute canonicals once per page and reuse across both filtering passes.
        page_canonicals = [_canonicalize_line(line) for line in lines]

        kept_end = len(lines) - bottom_cut if bottom_cut else len(lines)
        kept_raw   = lines[top_cut:kept_end]
        kept_canon = page_canonicals[top_cut:kept_end]

        # In some docs, extraction order may interleave header/footer lines inside page text.
        # Remove detected repeated candidates anywhere in the page segment as a final cleanup.
        kept = [ln for ln, c in zip(kept_raw, kept_canon) if c not in global_candidates]
        kept_set = set(kept)  # O(1) membership for the removal-tracking pass below

        removed_lines.update(lines[:top_cut])
        if bottom_cut:
            removed_lines.update(lines[-bottom_cut:])
        for line, canon in zip(lines, page_canonicals):
            if canon in global_candidates and line not in kept_set:
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
    """Find repeated multi-line header or footer blocks shared across enough pages."""
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
    """Return how many leading lines should be trimmed from a page as header content."""
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
    """Return how many trailing lines should be trimmed from a page as footer content."""
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
    """Produce a stable, human-readable ordering for the lines removed during cleanup."""
    ordered: list[str] = []
    seen: set[str] = set()

    canonical_order = sorted(header_candidates | footer_candidates)
    for canonical in canonical_order:
        original = canonical_to_original.get(canonical)
        if original and original in removed_lines and original not in seen:
            ordered.append(original)
            seen.add(original)

    for block in header_blocks + footer_blocks:
        for canonical in block:
            original = canonical_to_original.get(canonical)
            if original and original in removed_lines and original not in seen:
                ordered.append(original)
                seen.add(original)

    for line in sorted(removed_lines):
        if line not in seen:
            ordered.append(line)
            seen.add(line)

    return ordered


def _canonicalize_line(line: str) -> str:
    """Normalize a line so repeated furniture can match despite spacing or page-number differences."""
    canonical = line.lower().strip()
    canonical = _RE_PIPE.sub(" ", canonical)
    canonical = _RE_WS.sub(" ", canonical).strip()

    separator_probe = canonical.replace(" ", "")
    if separator_probe and _RE_SEPARATOR.fullmatch(separator_probe):
        return ""

    canonical = _RE_DIGITS.sub("<num>", canonical)
    canonical = _RE_WS.sub(" ", canonical).strip(" -:")

    # Ignore very short tokens to reduce false positives.
    if len(canonical) < 6:
        return ""
    return canonical


def _remove_repeated_lines_global(
    text: str,
    min_repeats: int = 2,
) -> tuple[str, list[str]]:
    """Remove repeated header or footer signatures that survive page-based cleanup."""
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
        compact = _RE_BARS.sub("", line)
        if compact and _RE_SEPARATOR.fullmatch(compact):
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
    """Collapse whitespace artifacts left behind after line-removal cleanup passes."""
    normalized = _RE_NL_TRAIL.sub("\n", text)
    normalized = _RE_NL_BLANK.sub("\n\n", normalized)
    normalized = _RE_NL_MULTI.sub("\n\n", normalized)
    return normalized.strip()
