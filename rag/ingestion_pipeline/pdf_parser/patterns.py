import re

# ---------------------------------------------------------------------------
# ISO section-number patterns used as a fallback signal for heading detection.
# Matches: "4", "4.1", "4.1.1", "A.1", "B.2.3" at the start of a block.
# Also matches annex titles like "Annexe A (informative)".
# ---------------------------------------------------------------------------
ISO_SECTION_RE = re.compile(r'^[A-Z]?\d+(\.\d+)*[\s\.]')
ANNEX_RE = re.compile(r'^(Annexe|Annex|Appendix)\b', re.IGNORECASE)

# Detects the first normative clause heading (e.g. "1 Scope", "1 General").
# Used by the pipeline state machine to skip front matter before clause 1.
CLAUSE_START_RE = re.compile(r'^1\s+[A-Z]')

# Matches standalone page numbers — both Arabic (1, 2, 3) and Roman numerals
# (i, ii, iii, iv, v, vi ...).  Used to identify leftover page-number lines
# after footer content has been stripped from a mixed block.
_PAGE_NUMBER_RE = re.compile(r'^[ivxlcdmIVXLCDM\d]+$')

# PyMuPDF occasionally inserts ASCII control characters (notably \x08 backspace)
# as rendering artifacts between elements in a block — e.g. between a page number
# and a copyright line.  These are never meaningful text and must be stripped
# before any comparison or matching is done.
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]')
