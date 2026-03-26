from ..config import FONT_GAP_TOLERANCE, MIN_HEADING_CHARS_FLOOR, MIN_HEADING_CHARS_PCT
from .phase1_boilerplate import _clean


# ---------------------------------------------------------------------------
# Phase 2 helpers – block-level text extraction and heading classification
# ---------------------------------------------------------------------------

def get_block_text(block):
    """
    Extract plain text from a dict-format block by concatenating all spans.

    Lines within a block are joined with "\\n" (not "") for two reasons:
      1. Header/footer matching — detect_headers_footers() stores text via
         get_text("blocks") which uses "\\n" between lines.  Joining with ""
         produces a different string, breaking the exact-match check.
      2. Word integrity — without a separator, the last word of one line and
         the first word of the next are concatenated (e.g. "d'organismesnationaux").
         A "\\n" keeps them distinct; Markdown renders a single newline as a space.
    """
    lines = []
    for line in block.get("lines", []):
        line_text = "".join(span["text"] for span in line.get("spans", []))
        # _clean() strips \x08 and other control chars; rstrip removes trailing
        # newlines PyMuPDF occasionally appends, preventing double-newlines.
        lines.append(_clean(line_text).rstrip())
    return "\n".join(lines).strip()


def get_block_dominant_size(block):
    """
    Return the largest font size found in any non-empty span of the block.
    This is the primary signal for heading classification.
    """
    max_size = 0.0
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            if span["text"].strip():
                max_size = max(max_size, span["size"])
    return round(max_size, 1)


# ---------------------------------------------------------------------------
# Phase 2 – Font hierarchy detection
# ---------------------------------------------------------------------------

def build_font_hierarchy(doc):
    """
    Single pass over the entire document to derive a font-size -> heading-level map.

    Strategy
    --------
    1.  Count total characters per font size across all pages.
    2.  The most frequent size is body text.
    3.  Sizes > body + 0.5 pt are heading candidates.
        (Using 0.5 rather than 1.0 so that 12pt headings are not missed
         when the body is 11pt — "12 > 12" would be False with a strict +1 gap.)
    4.  Filter out very-rare sizes (cover page, one-off labels) using a minimum
        character threshold of max(100, 0.1% of total document chars).
    5.  Map the top 3 remaining sizes (largest -> H1, ..., third -> H3).

    Returns
    -------
    font_levels : dict {rounded_size: heading_level (1 | 2 | 3)}
    body_size   : float – dominant body text font size
    """
    size_chars = {}  # {rounded_size: total_char_count}

    for page_num in range(doc.page_count):
        page = doc[page_num]
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:  # skip image blocks
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if not text:
                        continue
                    # Round to 1 decimal to collapse floating-point noise
                    # (e.g. 10.999 and 11.001 both become 11.0)
                    size = round(span["size"], 1)
                    size_chars[size] = size_chars.get(size, 0) + len(text)

    if not size_chars:
        # Safe fallback for empty or corrupt documents
        print("[Font Hierarchy] No text found. Using fallback body=11pt, no headings.")
        return {}, 11.0

    # Body text = the size with the most accumulated characters
    body_size = max(size_chars, key=size_chars.get)

    total_chars = sum(size_chars.values())
    # Minimum chars to qualify as a real heading level (not a cover-page blip).
    # 0.1% of total chars, floored at 100 so tiny docs still work.
    min_heading_chars = max(MIN_HEADING_CHARS_FLOOR, total_chars * MIN_HEADING_CHARS_PCT)

    # Heading candidates: clearly larger than body AND frequent enough
    heading_candidates = sorted(
        [
            s for s, count in size_chars.items()
            if s > body_size + FONT_GAP_TOLERANCE and count >= min_heading_chars
        ],
        reverse=True  # largest first -> H1
    )

    # Assign H1 / H2 / H3 / H4 to the top 4 distinct sizes
    font_levels = {}
    for level, size in enumerate(heading_candidates[:4], start=1):
        font_levels[size] = level

    # ── Diagnostic output ──────────────────────────────────────────────────
    print(f"[Font Hierarchy] Body: {body_size}pt | Total chars: {total_chars:,}")
    for size, level in sorted(font_levels.items(), key=lambda x: x[1]):
        h = "#" * level
        print(f"  {h} (H{level}) -> {size}pt  [{size_chars.get(size, 0):,} chars in doc]")
    # ───────────────────────────────────────────────────────────────────────

    return font_levels, body_size


def compute_doc_stats(doc, body_size):
    """
    Single pass over the document to derive layout statistics from body text blocks.

    A block qualifies as body text when its dominant font size is within 0.5pt
    of body_size (same tolerance used in build_font_hierarchy for heading candidates).

    Returns
    -------
    avg_body_indent : float
        Mean x0 coordinate of body text block bounding boxes.
        Used in score_heading_probability to reward blocks that start left of the
        typical body margin (a common trait of headings).
        Returns 0.0 if no qualifying blocks are found (disables the signal).

    avg_line_spacing : float
        Mean line height across body text blocks (block height / number of lines).
        Used to compute the vertical-gap threshold (avg_line_spacing * 1.5).
        Returns 12.0 as a safe fallback if no qualifying blocks are found.
    """
    indent_sum, indent_count = 0.0, 0
    spacing_sum, spacing_count = 0.0, 0

    for page_num in range(doc.page_count):
        page = doc[page_num]
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            if abs(get_block_dominant_size(block) - body_size) > FONT_GAP_TOLERANCE:
                continue
            bbox = block.get("bbox")
            lines = block.get("lines", [])
            if not bbox or not lines:
                continue
            indent_sum += bbox[0]
            indent_count += 1
            block_height = bbox[3] - bbox[1]
            if block_height > 0:
                spacing_sum += block_height / len(lines)
                spacing_count += 1

    avg_body_indent = indent_sum / indent_count if indent_count else 0.0
    avg_line_spacing = spacing_sum / spacing_count if spacing_count else 12.0
    return avg_body_indent, avg_line_spacing
