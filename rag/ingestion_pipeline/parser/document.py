from dataclasses import dataclass


@dataclass
class ParsedDocument:
    """
    Structured result of parse_iso_pdf().

    Attributes
    ----------
    standard_id : str
        Stem of the source PDF filename (e.g. "n9001" for "data/n9001.pdf").

    markdown : str
        Full markdown output with embedded <!-- page:N --> markers, identical
        to what parse_iso_pdf() previously returned as a bare string.

    page_map : dict
        Maps char_offset (int) -> page_num (int).
        Each key is the character position in `markdown` where a page marker
        (<!-- page:N -->) begins. Consumers can binary-search the sorted keys
        to resolve any content offset to its page number:

            import bisect
            keys = sorted(page_map)
            page = page_map[keys[bisect.bisect_right(keys, offset) - 1]]

    heading_positions : list
        Ordered list of headings found in `markdown`. Each entry is a dict:
            {"offset": int, "level": int, "text": str}
        "offset" — character position of the leading "#" in `markdown`.
        "level"  — 1–4, matching the ATX heading depth.
        "text"   — heading text without "#" prefix or trailing whitespace.
    """
    standard_id: str
    markdown: str
    page_map: dict
    heading_positions: list
