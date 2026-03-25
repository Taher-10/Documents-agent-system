from ..patterns import _CONTROL_CHARS_RE
from ..config import (
    HEADER_FOOTER_ZONE,
    HEADER_FOOTER_THRESHOLD,
    HEADER_FOOTER_MAX_CHARS,
    SAMPLE_PAGES,
)


def _clean(text):
    """Remove ASCII control characters (except \\t and \\n) from text."""
    return _CONTROL_CHARS_RE.sub('', text)


# ---------------------------------------------------------------------------
# Phase 1 – Header / Footer detection
# ---------------------------------------------------------------------------

def detect_headers_footers(doc, sample_pages=SAMPLE_PAGES):
    """
    Identify repeating text blocks in the top 15% / bottom 15% of pages.
    These are running headers and footers (e.g. license banners, page refs).

    Threshold: a block must appear on > 30% of sampled pages AND be < 500 chars.
    The 500-char ceiling was raised from the original 100 so that multi-line
    license blocks (~170 chars) are correctly captured.
    """
    repeating_blocks = {}
    number_of_pages = min(sample_pages, doc.page_count)

    for i in range(number_of_pages):
        page = doc[i]
        blocks = page.get_text("blocks")
        page_height = page.rect.height

        for b in blocks:
            x0, y0, x1, y1, text = b[:5]
            # _clean() removes \x08 and other control chars that PyMuPDF
            # injects between page numbers and footer text in the same block.
            text = _clean(text).strip()

            if not text:
                continue

            # Classify position as header or footer zone
            if y0 < page_height * HEADER_FOOTER_ZONE:
                position = "header"
            elif y1 > page_height * (1 - HEADER_FOOTER_ZONE):
                position = "footer"
            else:
                continue  # body content – ignore

            # Track the full block as a unit (catches exact repeating blocks).
            key = (text, position)
            repeating_blocks[key] = repeating_blocks.get(key, 0) + 1

            # Also track each individual line within the block.
            # This catches blocks like "vi\n© ISO 2015 – Tous droits réservés"
            # where the page number changes every page but the copyright line
            # is constant — the full block never repeats, but the line does.
            for line in text.splitlines():
                line = line.strip()
                if line:
                    repeating_blocks[(line, position)] = (
                        repeating_blocks.get((line, position), 0) + 1
                    )

    # A block/line seen on more than 30% of sampled pages is a header/footer.
    threshold = number_of_pages * HEADER_FOOTER_THRESHOLD

    # Return as a set for O(1) membership checks in the hot path.
    headers_footers = {
        text for (text, pos), count in repeating_blocks.items()
        if count > threshold and len(text) < HEADER_FOOTER_MAX_CHARS
    }
    return headers_footers
