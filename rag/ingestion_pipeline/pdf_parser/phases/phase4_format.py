from ..patterns import _PAGE_NUMBER_RE
from .phase2_font import get_block_text, get_block_dominant_size
from .phase3_classify import classify_block


def format_block_as_markdown(block, font_levels, body_size, headers_footers,
                             avg_body_indent=0.0, prev_block_y1=0.0,
                             avg_line_spacing=12.0, page_height=0.0,
                             is_table_page=False):
    """
    Convert a single dict-format block to its Markdown representation.

    Returns None if the block should be skipped (image, header/footer, empty).
    Otherwise returns a string: "# Heading", "## Heading", or plain text.

    page_height    : float  used by classify_block for page-zone penalty.
    is_table_page  : bool   when True, heading classification is suppressed so
                            that table cell content (already captured by
                            pdfplumber) is never misidentified as a heading.
    """
    # Skip image blocks (type 1 in PyMuPDF dict format)
    if block.get("type") != 0:
        return None

    text = get_block_text(block)
    if not text:
        return None

    # ── Full-block match (exact repeating blocks) ──────────────────────────
    if text in headers_footers:
        return None

    # ── Line-level match (blocks with a varying page number + constant footer)
    # Example: "vi\n© ISO 2015 – Tous droits réservés"
    #   - "© ISO 2015 – Tous droits réservés" is detected as a footer line
    #   - "vi" is a Roman-numeral page number
    # Strategy: remove known footer lines and standalone page numbers;
    # if nothing substantive remains, skip the whole block.
    block_lines = [l.strip() for l in text.splitlines() if l.strip()]
    if any(line in headers_footers for line in block_lines):
        surviving = [
            line for line in block_lines
            if line not in headers_footers and not _PAGE_NUMBER_RE.match(line)
        ]
        if not surviving:
            return None
        # Reconstruct text from the lines that survived filtering
        text = "\n".join(surviving)

    # On table pages, suppress heading classification only for blocks at body
    # font size. ISO clause numbers in table cells have body-size text and no
    # font-hierarchy signal — those are already captured by pdfplumber.
    # Blocks at a genuine heading font size (present in font_levels) are still
    # classified normally so section headings above/below tables are preserved.
    if is_table_page and font_levels.get(get_block_dominant_size(block), 0) == 0:
        return text

    heading_level, text = classify_block(
        block, font_levels, body_size,
        avg_body_indent=avg_body_indent,
        prev_block_y1=prev_block_y1,
        avg_line_spacing=avg_line_spacing,
        page_height=page_height,
    )

    if heading_level > 0:
        # Emit a Markdown ATX heading: "#", "##", "###", or "####"
        return "#" * heading_level + " " + text

    return text
