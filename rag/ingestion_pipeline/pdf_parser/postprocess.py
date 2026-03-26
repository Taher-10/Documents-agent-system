import re


# ---------------------------------------------------------------------------
# TOC detection
# ---------------------------------------------------------------------------

def is_toc_page(text):
    """
    Detect table-of-contents pages by counting dot-leader sequences ("...").
    ISO standards use these extensively in TOC entries.
    """
    return text.count("...") > 10


# ---------------------------------------------------------------------------
# Whitespace / page-number cleanup
# ---------------------------------------------------------------------------

def normalize_whitespace(text):
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def remove_page_numbers(text):
    # Remove lines that contain only a number (standalone page numbers)
    text = re.sub(r'(?m)^\s*\d+\s*$', '', text)
    return text
