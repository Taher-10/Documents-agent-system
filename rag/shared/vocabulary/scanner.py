"""
shared/vocabulary/scanner.py
─────────────────────────────
Shared ISO vocabulary scanner — single source of truth used by BOTH the
ingestion enricher (Phase 5) and the query transformer (retrieval side).

Any change here affects index-time and query-time vocabulary injection
identically, preserving BM25 sparse-match symmetry.

Public API
----------
    CLAUSE_PATTERN      — compiled regex for clause numbers (e.g. "8.5.1")
    MODAL_TERMS         — normative-weight term list (shall, should, may, ...)
    scan_iso_vocabulary(text, language, norm_filter) -> List[str]
"""

import re
from typing import List, Optional, Set

from .vocabulary import ISO_VOCABULARY_EN, ISO_VOCABULARY_FR

# Matches clause numbers like "8.5", "7.4.1", "4.3.2.1"
CLAUSE_PATTERN = re.compile(r'\b\d+\.\d+(?:\.\d+)*\b')

# Modal / normative-weight terms (category 3)
MODAL_TERMS: List[str] = [
    "shall",
    "must",
    "is required to",
    "should",
    "it is recommended",
    "may",
    "is permitted",
    "can",
]

# ── Surface-form pattern cache ────────────────────────────────────────────────
# Compiled once per unique surface form (lazy init) to avoid recompiling
# on every scan_iso_vocabulary() call.
_FORM_PATTERNS: dict[str, re.Pattern] = {}


def _form_pattern(form: str) -> re.Pattern:
    """Return a compiled word-boundary regex for *form*, cached after first use."""
    key = form.lower()
    if key not in _FORM_PATTERNS:
        _FORM_PATTERNS[key] = re.compile(r'\b' + re.escape(key) + r'\b')
    return _FORM_PATTERNS[key]


def scan_iso_vocabulary(
    text: str,
    language: str = "EN",
    norm_filter: Optional[List[str]] = None,
) -> List[str]:
    """
    Scan *text* for ISO vocabulary hits.

    Only the vocabulary for *language* is consulted (
    ``"EN"`` → ``ISO_VOCABULARY_EN``,
    ``"FR"`` → ``ISO_VOCABULARY_FR``), avoiding cross-language false positives.

    When *norm_filter* is provided, only terms tagged for one of those standards
    are considered — e.g. passing ``["ISO9001"]`` suppresses
    ``"système de management environnemental"`` (ISO14001-only) entirely,
    eliminating false-positive BM25 token injection.

    When any surface form matches, the **canonical key** is recorded (one entry
    per canonical term, regardless of how many surface forms matched).
    Also records any clause-number patterns and modal terms found.

    Returns a sorted list — suitable for direct assignment to
    ``TransformedQuery.iso_vocab_hits`` and for the HyDE trigger check
    (len < 3 → trigger HyDE).

    Parameters
    ----------
    text : str
        Raw chunk text or user query text.
    language : str
        ``"EN"`` (default) or ``"FR"``.
    norm_filter : List[str], optional
        Standard IDs to scope the lookup, e.g. ``["ISO9001"]``.
        When None, all vocabulary entries are considered.

    Returns
    -------
    List[str] — sorted canonical vocabulary hits + clause numbers + modal terms.
    """
    text_lower = text.lower()
    hits: Set[str] = set()

    # --- ISO vocabulary (language-specific, standard-scoped) ---
    vocab = ISO_VOCABULARY_EN if language == "EN" else ISO_VOCABULARY_FR
    for canonical_key, entry in vocab.items():
        # Skip terms that don't belong to any requested standard
        if norm_filter and not any(s in entry["standards"] for s in norm_filter):
            continue
        for form in entry["forms"]:
            if _form_pattern(form).search(text_lower):
                hits.add(canonical_key)
                break  # first match wins; skip remaining surface forms

    # --- Modal / normative-weight terms ---
    for term in MODAL_TERMS:
        if term in text_lower:
            hits.add(term)

    # --- Clause number patterns ---
    for clause_num in CLAUSE_PATTERN.findall(text):
        hits.add(clause_num)

    return sorted(hits)
