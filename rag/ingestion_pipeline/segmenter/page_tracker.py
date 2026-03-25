"""
segmenter/page_tracker.py
─────────────────────────
Stateful O(log n) page resolver built from ParsedDocument.page_map.

page_map layout (from parser)
─────────────────────────────
  {char_offset: page_num, ...}

Each key is the character position in the assembled markdown where a
  <!-- page:N -->
marker begins.  Content between two consecutive markers belongs to the
earlier marker's page.

Construction sorts the keys once.  All lookups use bisect — callers
never touch the raw dict.
"""

import bisect
import warnings


class PageTracker:
    """
    Resolves character offsets in assembled markdown to page numbers.

    Parameters
    ----------
    page_map : dict
        Mapping of {char_offset: page_num} as produced by parse_iso_pdf().
        May be empty (falls back to page 1 with a warning).

    Usage
    -----
        tracker = PageTracker(parsed_doc.page_map)
        tracker.page_at(1500)          # → int
        tracker.page_range(800, 2400)  # → (int, int)
    """

    def __init__(self, page_map: dict):
        if not page_map:
            warnings.warn(
                "PageTracker received an empty page_map — "
                "all offsets will resolve to page 1.",
                UserWarning,
                stacklevel=2,
            )
            self._offsets = []
            self._pages = []
        else:
            pairs = sorted(page_map.items())          # sort once at construction
            self._offsets = [offset for offset, _ in pairs]
            self._pages = [page for _, page in pairs]

    # ── Public API ────────────────────────────────────────────────────────────

    def page_at(self, offset: int) -> int:
        """
        Return the page number that contains *offset*.

        Uses bisect_right so that an offset exactly on a marker boundary
        belongs to that marker's page (not the previous one).

        O(log n) where n = number of pages.
        Falls back to page 1 for an empty map.
        """
        if not self._offsets:
            return 1

        idx = bisect.bisect_right(self._offsets, offset) - 1
        if idx < 0:
            # offset is before the first page marker — treat as page 1
            return self._pages[0]
        return self._pages[idx]

    def page_range(self, start: int, end: int) -> tuple:
        """
        Return (first_page, last_page) for the span [start, end].

        Both endpoints are inclusive.  *end* must be >= *start*.
        O(log n).
        """
        return (self.page_at(start), self.page_at(end))
