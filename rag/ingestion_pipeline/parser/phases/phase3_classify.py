from ..patterns import ISO_SECTION_RE, ANNEX_RE
from ..config import (
    FONT_GAP_TOLERANCE,
    HEADING_SCORE_THRESHOLD,
    HEADING_STRUCTURAL_SCORE_THRESHOLD,
    SHORT_TEXT_THRESHOLD,
    UPPERCASE_RATIO_THRESHOLD,
    VERTICAL_GAP_MULTIPLIER,
    _DEBUG_SCORES,
    _score_log,
)
from .phase2_font import get_block_text, get_block_dominant_size


def determine_heading_level(text, dominant_size, font_levels, body_size, is_bold):
    """
    Determine heading depth (1-3) or 0 from structural and font signals.

    Signals applied in priority order
    ----------------------------------
    1.  font_levels map         – direct lookup by rounded dominant font size
    2.  Bold + larger than body – estimated level from ISO dot-depth
    3.  ISO section number      – section depth from dot count ("4.1.1" → 2 → H3)
    4.  Annex heading pattern   – always H2

    Parameters
    ----------
    text          : str   cleaned block text
    dominant_size : float rounded font size
    font_levels   : dict  {size: level} from build_font_hierarchy
    body_size     : float dominant body font size
    is_bold       : bool  True if any non-empty span has bit-16 bold flag

    Returns
    -------
    int  0 = body text, 1-3 = heading depth
    """
    # Signal 1: font size map
    level = font_levels.get(dominant_size, 0)

    # Signal 2: bold + size fallback (handles rare sizes not in the map)
    if level == 0 and dominant_size > body_size + FONT_GAP_TOLERANCE and is_bold:
        depth = text.count(".") if ISO_SECTION_RE.match(text) else 0
        level = min(4, depth + 2)

    # Signal 3: ISO section number pattern
    if level == 0 and ISO_SECTION_RE.match(text) and dominant_size > body_size:
        depth = text.count(".")  # "4"->0, "4.1"->1, "4.1.1"->2, "4.1.1.1"->3
        level = min(4, depth + 1)

    # Signal 4: Annex headings always H2
    if level == 0 and ANNEX_RE.match(text):
        level = 2

    return level


def score_heading_probability(block, font_levels, body_size,
                              avg_body_indent=0.0, prev_block_y1=0.0,
                              avg_line_spacing=12.0, page_height=0.0):
    """
    Compute a weighted score across 8 signals to estimate heading probability.

    Score table
    -----------
    +3  Font size present in font_levels map (implies size > body by construction)
    +3  Text matches ISO section number pattern (ISO_SECTION_RE)
    +2  Block contains bold text (any span with bit-16 flag)
    +2  Vertical gap above block > avg_line_spacing * 1.5
         (only active when prev_block_y1 > 0, i.e. not first block on page)
    +1  Total text length < 80 characters (typical of heading vs. paragraph)
    +1  Block x0 < avg_body_indent (left of typical body margin)
         (only active when avg_body_indent > 0)
    +1  Uppercase character ratio > 0.7 (e.g. "MANAGEMENT REVIEW")
    -1  Text ends with a period (prose sentence, not a heading)

    Parameters
    ----------
    block            : dict   PyMuPDF dict-format block
    font_levels      : dict   {size: level} from build_font_hierarchy
    body_size        : float  dominant body font size
    avg_body_indent  : float  mean x0 of body blocks; 0.0 disables indent signal
    prev_block_y1    : float  y1 of previous rendered block; 0.0 disables gap signal
    avg_line_spacing : float  mean body line height in points

    Returns
    -------
    (score, is_bold, dominant_size, text)
    """
    text = get_block_text(block)
    dominant_size = get_block_dominant_size(block)
    bbox = block.get("bbox", [0.0, 0.0, 0.0, 0.0])
    x0, y0 = bbox[0], bbox[1]

    is_bold = any(
        span.get("flags", 0) & 16
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span["text"].strip()
    )

    score = 0

    # +3: font size is in the heading map (larger than body by construction)
    if font_levels.get(dominant_size, 0) > 0:
        score += 3

    # +3: ISO section number match
    if ISO_SECTION_RE.match(text):
        score += 3

    # +2: bold text that is also larger than body size.
    # Body-size bold text (legal notices, labels) does not get this bonus;
    # it must be reserved for blocks that are visually prominent headings.
    if is_bold and dominant_size > body_size:
        score += 2

    # +2: vertical gap above block exceeds 1.5× average line spacing.
    # Guard: prev_block_y1 == 0.0 means first block on page (page margin, not gap).
    if prev_block_y1 > 0.0 and avg_line_spacing > 0.0:
        if (y0 - prev_block_y1) > avg_line_spacing * VERTICAL_GAP_MULTIPLIER:
            score += 2

    # +1: short text (headings are rarely long paragraphs)
    if len(text) < SHORT_TEXT_THRESHOLD:
        score += 1

    # +1: block starts left of the typical body indentation margin
    if avg_body_indent > 0.0 and x0 < avg_body_indent:
        score += 1

    # +1: high uppercase ratio — only meaningful for multi-word blocks with enough
    # alpha chars to form a real title (e.g. "MANAGEMENT REVIEW").
    # Guards prevent single tokens, symbols, and short identifiers from firing.
    alpha_chars = [c for c in text if c.isalpha()]
    if (len(text.split()) >= 2
            and len(alpha_chars) >= 4
            and sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) > UPPERCASE_RATIO_THRESHOLD):
        score += 1

    # -1: ends with a period (prose, not a heading)
    if text.rstrip().endswith("."):
        score -= 1

    if _DEBUG_SCORES:
        _score_log.append(score)

    return score, is_bold, dominant_size, text


def classify_block(block, font_levels, body_size,
                   avg_body_indent=0.0, prev_block_y1=0.0,
                   avg_line_spacing=12.0, page_height=0.0):
    """
    Classify a text block as a heading (level 1-4) or body text (level 0).

    Uses a probability-based scoring system (score_heading_probability) with 8
    weighted signals. A block is classified as a heading when score >= 4.
    The precise heading depth is then assigned by determine_heading_level.

    Backward compatibility
    ----------------------
    The three new optional parameters default to values that disable the
    new signals (vertical gap and indent), preserving the effective behaviour
    of the original 3-signal classifier for any existing callers that pass
    only (block, font_levels, body_size).

    Returns
    -------
    (heading_level, text)
        heading_level : int  0 = body, 1-3 = heading depth
        text          : str  cleaned text of the block
    """
    score, is_bold, dominant_size, text = score_heading_probability(
        block, font_levels, body_size,
        avg_body_indent=avg_body_indent,
        prev_block_y1=prev_block_y1,
        avg_line_spacing=avg_line_spacing,
        page_height=page_height,
    )

    if not text or score < HEADING_SCORE_THRESHOLD:
        return 0, text

    # Structural-signal guard: blocks that score ≥ 4 purely from soft signals
    # (bold, short, indent, uppercase, vertical spacing) without any font-
    # hierarchy or section-pattern confirmation are likely metadata labels
    # (copyright notices, document IDs) rather than genuine content headings.
    # Require a higher score threshold (≥ 6) for those marginal cases.
    # ISO standards virtually always express real headings via font size or
    # section numbering, so this guard has minimal false-negative risk.
    has_structural_signal = (
        font_levels.get(dominant_size, 0) > 0
        or bool(ISO_SECTION_RE.match(text))
        or bool(ANNEX_RE.match(text))
    )
    if not has_structural_signal and score < HEADING_STRUCTURAL_SCORE_THRESHOLD:
        return 0, text

    level = determine_heading_level(text, dominant_size, font_levels, body_size, is_bold)

    # Fallback: score qualifies as heading but no structural signal assigned a level.
    # Default to H4 (deepest standard level) as a conservative assignment.
    if level == 0:
        level = 4

    return level, text
