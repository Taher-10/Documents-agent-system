"""
shared/bm25/tokenizer.py
────────────────────────
Canonical BM25 tokenizer used by BOTH the ingestion enricher (Phase 5)
and the query transformer (retrieval side).

Any change here affects index-time and query-time tokenisation identically,
preserving vocabulary symmetry.

Public API
----------
    tokenize_for_bm25(text, clause_ref, bonus_terms) -> List[str]
"""

import re
from typing import List, Optional


# ==============================================================================
# Regex helpers
# ==============================================================================

# Alphabetic words of 3+ characters (includes accented French characters)
_WORD_RE = re.compile(r'\b[a-zA-ZÀ-ÿ]{3,}\b')

# Strips markdown formatting noise before term extraction
_MARKDOWN_NOISE_RE = re.compile(r'#+\s|<!--.*?-->|\*\*|\*|`|\[.*?\]', re.DOTALL)


# ==============================================================================
# Stop-word list (English + French) — mirrors enricher.py exactly
# ==============================================================================

STOP_WORDS: frozenset = frozenset({
    # ── English ───────────────────────────────────────────────────────────────
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "must", "can",
    "this", "that", "these", "those", "it", "its", "not", "no", "nor",
    "so", "yet", "both", "either", "neither", "each", "all", "any",
    "their", "there", "they", "them", "then", "than", "when", "where",
    "which", "who", "what", "how", "if", "while", "also", "more", "such",
    "into", "out", "up", "about", "after", "before", "between", "through",
    # ── French ────────────────────────────────────────────────────────────────
    "la", "le", "les", "de", "du", "des", "un", "une", "en", "et", "ou",
    "si", "il", "ils", "elle", "elles", "ce", "se", "sa", "son", "ses",
    "au", "aux", "par", "sur", "sous", "dans", "dont", "que", "qui",
    "est", "sont", "doit", "doivent", "leur", "leurs", "tout", "tous",
    "toute", "toutes", "cette", "cet", "ces", "mais", "car", "donc",
    "voir", "also", "its", "has",
})


# ==============================================================================
# Public API
# ==============================================================================

def tokenize_for_bm25(
    text: str,
    clause_ref: Optional[str] = None,
    bonus_terms: Optional[List[str]] = None,
) -> List[str]:
    """
    Canonical BM25 tokenizer — single source of truth for both index-time
    (enricher) and query-time (query transformer) tokenisation.

    Steps
    -----
    1. Strip markdown noise (headings, HTML comments, bold/italic, code, links).
    2. Extract 3+ character alphabetic words (including accented letters).
    3. Filter stop words (English + French combined list).
    4. Append clause-digit tokens: "7.5.2" → ["7", "5", "2"].
       At ingestion:  clause_ref = chunk.clause_number
       At query time: clause_ref = first clause pattern found in text (if any)
    5. Append bonus term tokens — always split into unigrams.
       At ingestion:  bonus_terms = chunk.keywords  (TF-IDF keyphrases)
       At query time: bonus_terms = ISO vocabulary hits (canonical phrases)
       Splitting fixes the bigram asymmetry: "corrective action" ->
       ["corrective", "action"] on both sides.
    6. Return order-preserving deduplicated token list.

    Parameters
    ----------
    text : str
        Raw chunk text or query text (markdown OK).
    clause_ref : str, optional
        Clause number string, e.g. "7.5.2".  Non-digit chars are stripped and
        the remainder is split on whitespace to yield digit tokens.
    bonus_terms : List[str], optional
        Additional terms to inject (keywords or ISO vocab hits).
        Each term is lowercased and split on whitespace before deduplication,
        ensuring bigrams never enter the index as compound tokens.

    Returns
    -------
    List[str] -- deduplicated tokens in source order, all lowercase.
    """
    clean = _MARKDOWN_NOISE_RE.sub(' ', text)
    word_tokens: List[str] = [
        w.lower() for w in _WORD_RE.findall(clean)
        if w.lower() not in STOP_WORDS
    ]

    # Clause digits: "7.5.2" -> ["7", "5", "2"]
    clause_tokens: List[str] = []
    if clause_ref:
        clause_tokens = re.sub(r'[^0-9]', ' ', clause_ref).split()

    # Bonus terms — always split bigrams into unigrams before indexing
    bonus_tokens: List[str] = []
    if bonus_terms:
        for term in bonus_terms:
            bonus_tokens.extend(term.lower().split())

    seen: set = set()
    result: List[str] = []
    for t in word_tokens + clause_tokens + bonus_tokens:
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result
