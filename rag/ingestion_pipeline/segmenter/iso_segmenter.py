"""
segmenter/iso_segmenter.py
───────────────────────────
Phases 2 & 3 — Clause Boundary Detection and Clause Tree Construction

This module transforms a ParsedDocument (from the parser package) into two
structural representations of the ISO standard's clause hierarchy:

  Phase 2 — detect_clause_boundaries()
      Reads heading_positions from the ParsedDocument and emits a flat ordered
      list of ClauseSpan objects, each marking the character-offset range of
      one ISO clause in the assembled markdown.

  Phase 3 — construct_clause_tree()
      Assembles the flat ClauseSpan list into a recursive ClauseNode tree,
      maintaining parent-child relationships via a monotonic stack.

Dependency rule: imports only from segmenter.models and the standard library
(+ parser.document for the ParsedDocument type annotation).
No chunker, enricher, or registry modules are imported here.
"""

import re
import warnings
from typing import List

from rag.ingestion_pipeline.pdf_parser.document import ParsedDocument

from .models import (
    EXPECTED_LEAF_COUNTS,
    ClauseNode,
    ClauseSpan,
)


# ==============================================================================
# Regex constants — clause identification and false-heading filtering
# ==============================================================================

# Matches ISO section numbers at the start of a heading:
#   "4", "4.1", "4.1.1", "A1" (lettered annex sub-section)
ISO_SECTION_RE = re.compile(r'^([A-Z]?\d+(\.\d+)*)(?=[\s\.]|$)')

# Matches annex markers at the start of a heading:
#   "Annexe A", "Annex B", "Appendix C"
ANNEX_RE = re.compile(r'^(Annexe|Annex|Appendix)\b', re.IGNORECASE)

# Filters copyright / metadata lines that the PDF parser may emit as headings.
# These are never real clause headings.
_FALSE_HEADING_RE = re.compile(
    r'^('
    r'DOCUMENT\s+PROTÉGÉ\s+PAR\s+COPYRIGHT'
    r'|NORME\s+INTERNATIONALE'
    r'|ICS\s*[\u2002\s]\d+\.\d+'
    r')',
    re.IGNORECASE,
)

# French subtitle fragments erroneously split from the previous heading
# (e.g. "et de son contexte" appearing as a separate heading line).
_SUBTITLE_FRAGMENT_RE = re.compile(r'^et\b', re.IGNORECASE)


# ==============================================================================
# Private helpers
# ==============================================================================

def _scan_for_suspect_boundaries(text: str) -> None:
    """
    Warn when a non-heading line has unusually high uppercase density.

    Lines that are ≥ 80 % uppercase and contain > 10 alphabetic characters
    sometimes indicate a heading that was missed by the parser.  This function
    issues a UserWarning for each such line so the issue can be investigated
    without halting the pipeline.

    Parameters
    ----------
    text : Markdown slice to scan (typically a single clause block).
    """
    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith('<!--'):
            continue
        alpha_count = sum(1 for c in stripped if c.isalpha())
        if alpha_count > 10:
            upper_count = sum(1 for c in stripped if c.isupper())
            if (upper_count / alpha_count) >= 0.8:
                warnings.warn(
                    f"Suspect boundary (high uppercase): {stripped[:60]}...",
                    UserWarning,
                    stacklevel=3,
                )






# ==============================================================================
# Phase 2 — Clause Boundary Detection
# ==============================================================================

def detect_clause_boundaries(doc: ParsedDocument) -> List[ClauseSpan]:
    """
    Convert a ParsedDocument's heading_positions into an ordered list of
    ClauseSpan objects.

    Algorithm
    ---------
    1. Use heading_positions (pre-built by the parser) as authoritative
       boundaries — no re-scanning of the raw markdown for headings.
    2. Extract the preamble (text before the first heading) if present.
    3. For each heading:
         a. Filter false headings (copyright, ICS codes, French fragments).
            When a false heading is suppressed, its text range is merged into
            the previous span.
         b. Assign a canonical clause_id from the ISO section regex or annex
            pattern; fall back to a sequential placeholder "H{n}".
         c. Override the heading level using the dot-depth of the clause ID
            (e.g. "4.4.1" → level 3) to correct parser-level noise.
    4. Flag suspect high-uppercase lines within each clause block.

    Parameters
    ----------
    doc : ParsedDocument produced by parse_iso_pdf().

    Returns
    -------
    List[ClauseSpan] — ordered by position in the markdown, no overlaps.
    """
    spans: List[ClauseSpan] = []
    text = doc.markdown
    headings = doc.heading_positions

    # Edge case: no headings detected at all — treat entire document as preamble
    if not headings:
        _scan_for_suspect_boundaries(text)
        return [ClauseSpan(clause_id='0', start_idx=0, end_idx=len(text),
                           level=0, title="Preamble")]

    # Preamble: text that precedes the first heading
    first_offset = headings[0]["offset"]
    if first_offset > 0 and text[0:first_offset].strip():
        spans.append(ClauseSpan(
            clause_id='0',
            start_idx=0,
            end_idx=first_offset,
            level=0,
            title="Preamble",
        ))

    for i, h in enumerate(headings):
        start_idx  = h["offset"]
        end_idx    = headings[i + 1]["offset"] if i + 1 < len(headings) else len(text)
        raw_level  = h["level"]
        title_text = h["text"].strip()

        # ── False-heading suppression ──────────────────────────────────────────
        if _FALSE_HEADING_RE.match(title_text) or _SUBTITLE_FRAGMENT_RE.match(title_text):
            warnings.warn(
                f"Suppressing false heading: {title_text[:60]!r}",
                UserWarning,
                stacklevel=2,
            )
            # Extend the previous span to absorb the suppressed range
            if spans:
                prev = spans[-1]
                spans[-1] = ClauseSpan(
                    clause_id=prev.clause_id,
                    start_idx=prev.start_idx,
                    end_idx=end_idx,
                    level=prev.level,
                    title=prev.title,
                    duplicate=prev.duplicate,
                )
            continue

        # ── Clause ID and level resolution ────────────────────────────────────
        clause_id = f"H{i + 1}"   # default placeholder if no pattern matches
        level     = raw_level

        sec_match   = ISO_SECTION_RE.match(title_text)
        annex_match = ANNEX_RE.match(title_text)

        if sec_match:
            matched_str = sec_match.group(1).strip()
            clause_id   = matched_str
            # Dot-depth is authoritative — overrides parser-reported level
            override_level = len(matched_str.split('.'))
            if override_level != raw_level:
                level = override_level

        elif annex_match:
            parts     = title_text.split()
            clause_id = parts[1] if len(parts) > 1 else "Annex"
            level     = 1

        spans.append(ClauseSpan(
            clause_id=clause_id,
            start_idx=start_idx,
            end_idx=end_idx,
            level=level,
            title=title_text,
        ))

        # Check clause block for missed boundaries
        _scan_for_suspect_boundaries(text[start_idx:end_idx])

    return spans



# ==============================================================================
# Phase 3 — Clause Tree Construction
# ==============================================================================

def construct_clause_tree(
    spans: List[ClauseSpan],
    text: str,
    standard_id: str,
) -> ClauseNode:
    """
    Assemble a flat ClauseSpan list into a recursive ClauseNode tree.

    Algorithm
    ---------
    Uses a monotonic stack to maintain the current path from root to the
    deepest open node.  For each span:
      1. Pop the stack until the top's level is strictly less than this span's
         level — that top becomes the parent.
      2. Attach a new ClauseNode to the parent.
      3. Push the new node onto the stack.

    Special cases:
      • Preamble (clause_id='0') is always a direct child of root regardless
        of level, to avoid it being swallowed by a preceding node.
      • Lettered sub-items (e.g. "a) item") are skipped — they are list entries
        mistakenly emitted as headings.
      • Duplicate clause IDs are flagged with a warning but not dropped, so
        the tree remains complete.

    Leaf-count validation:
      After building the tree, count leaf nodes and compare against
      EXPECTED_LEAF_COUNTS[standard_id].  A mismatch issues a warning without
      halting the pipeline.

    Parameters
    ----------
    spans       : Ordered ClauseSpan list from detect_clause_boundaries().
    text        : The full assembled markdown string.
    standard_id : PDF stem (e.g. "n9001") — used for leaf-count validation.

    Returns
    -------
    ClauseNode — the root node (clause_id='root', level=0).
    """
    root  = ClauseNode(clause_id='root', title="Root", level=0, text="")
    stack: List[ClauseNode] = [root]
    seen_ids: set = set()

    for span in spans:
        # ── Duplicate detection ────────────────────────────────────────────────
        if span.clause_id in seen_ids and span.clause_id != "0":
            span.duplicate = True
            warnings.warn(
                f"Duplicate clause_id detected: {span.clause_id}",
                UserWarning,
                stacklevel=2,
            )
        else:
            seen_ids.add(span.clause_id)

        # ── Skip lettered sub-items (e.g. "a) description") ───────────────────
        if re.match(r'^[a-z][\)\.][ \t]', span.title):
            warnings.warn(
                f"Skipping lettered sub-item erroneously marked as node: {span.title}",
                UserWarning,
                stacklevel=2,
            )
            continue

        node = ClauseNode(
            clause_id=span.clause_id,
            title=span.title,
            level=span.level,
            text=text[span.start_idx:span.end_idx].strip(),
        )

        # Preamble always attaches directly to root
        if span.clause_id == '0':
            root.children.append(node)
            continue

        # Pop stack until we find a node at a strictly lower level (the parent)
        while len(stack) > 1 and stack[-1].level >= node.level:
            stack.pop()

        stack[-1].children.append(node)
        stack.append(node)

    # ── Leaf-count validation ──────────────────────────────────────────────────
    def _count_leaves(n: ClauseNode) -> int:
        if not n.children:
            return 1 if n.clause_id != 'root' else 0
        return sum(_count_leaves(c) for c in n.children)

    total_leaves = _count_leaves(root)
    if standard_id in EXPECTED_LEAF_COUNTS:
        min_l, max_l = EXPECTED_LEAF_COUNTS[standard_id]
        if not (min_l <= total_leaves <= max_l):
            warnings.warn(
                f"Leaf count {total_leaves} for {standard_id} falls outside "
                f"EXPECTED_LEAF_COUNTS range [{min_l}, {max_l}].",
                UserWarning,
                stacklevel=2,
            )

    return root

