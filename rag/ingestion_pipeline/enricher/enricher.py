"""
enricher/enricher.py
─────────────────────
Phase 5 — Retrieval Metadata Enrichment

Adds two retrieval-focused fields to every NormChunk:

  keywords    — top-5 TF-IDF terms per chunk (bigrams preferred on tie).
  bm25_tokens — combined word / clause-digit / keyword tokens for local BM25.

Design constraint (preserved from the original monolith):
  This module imports ONLY the NormChunk dataclass from chunker.models and
  the standard library.  No segmenter, registry, or other pipeline packages
  are imported here.  This keeps the enricher self-contained and replaceable.

The Enricher is stateful (it pre-computes corpus-level IDF at construction
time) but has no side effects beyond mutating the chunks it is given.

Usage
-----
  enricher = Enricher(chunks)   # computes IDF across the corpus
  enricher.enrich(chunks)       # mutates chunks in-place, returns same list
"""

import math
import re
from typing import Dict, List

from rag.ingestion_pipeline.chunker.models import NormChunk


# ==============================================================================
# Stop-word list (English + French)
# ==============================================================================

_STOP_WORDS: frozenset = frozenset({
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
# Module-level regex helpers
# ==============================================================================

# Matches alphabetic words (3+ chars, supports accented French characters)
_WORD_RE = re.compile(r'\b[a-zA-ZÀ-ÿ]{3,}\b')

# Strips markdown formatting noise before term extraction
_MARKDOWN_NOISE_RE = re.compile(r'#+\s|<!--.*?-->|\*\*|\*|`|\[.*?\]', re.DOTALL)


# ==============================================================================
# Module-level term extraction helper
# ==============================================================================

def _extract_terms(text: str) -> List[str]:
    """
    Extract stop-word-filtered unigrams and bigrams from text.

    Steps
    -----
    1. Strip markdown noise (headings, HTML comments, bold/italic markers,
       inline code, link syntax).
    2. Extract 3+ character alphabetic words (including accented letters).
    3. Filter stop words (English + French combined list).
    4. Generate all adjacent bigrams from the filtered word list.
    5. Return unigrams followed by bigrams (preserves term-order for TF-IDF).

    Parameters
    ----------
    text : Raw chunk text.

    Returns
    -------
    List[str] — unigrams + bigrams, stop-word filtered.
    """
    clean = _MARKDOWN_NOISE_RE.sub(' ', text)
    words = [w for w in _WORD_RE.findall(clean.lower()) if w not in _STOP_WORDS]
    terms = list(words)
    for i in range(len(words) - 1):
        terms.append(f"{words[i]} {words[i + 1]}")
    return terms


# ==============================================================================
# Enricher class
# ==============================================================================

class Enricher:
    """
    Phase 5 — stateless post-processing pass that adds TF-IDF keywords and
    BM25 tokens to each NormChunk.

    The class is instantiated once per pipeline run with the full chunk list
    so that corpus-level IDF can be pre-computed.  Individual chunk enrichment
    is then O(n) over the term list per chunk.

    Enrichment pipeline (applied in enrich())
    -----------------------------------------
    1. _tfidf_keywords(chunk) — top-5 terms by TF * IDF score.
       Bigrams are preferred over same-score unigrams.
       Result stored in chunk.keywords.

    2. _bm25_tokens(chunk) — word tokens + clause-digit tokens + keyword tokens.
       Combined from three sources; order-preserving deduplication applied.
       Result stored in chunk.bm25_tokens.
       NOTE: bm25_tokens is never sent to ChromaDB (metadata={"chroma": False}).

    Design constraint
    -----------------
    The only pipeline import in this module is NormChunk from chunker.models.
    All other code uses the standard library exclusively.

    Parameters
    ----------
    chunks : Full list of NormChunks to enrich (used to compute corpus IDF).
    """

    def __init__(self, chunks: List[NormChunk]):
        # Pre-compute corpus-level IDF at construction time
        self._idf: Dict[str, float] = self._compute_idf(chunks)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _compute_idf(chunks: List[NormChunk]) -> Dict[str, float]:
        """
        Compute smoothed IDF for all terms in the corpus.

        Formula: log((N + 1) / (df + 1)) + 1
          where N  = total number of chunks
                df = number of chunks that contain the term

        Smoothing (+1 in numerator and denominator) prevents zero IDF for
        terms that appear in every chunk and avoids log(0) for rare terms.

        Parameters
        ----------
        chunks : Full chunk corpus.

        Returns
        -------
        Dict[str, float] — term → IDF score.
        """
        n = len(chunks)
        if n == 0:
            return {}
        df: Dict[str, int] = {}
        for chunk in chunks:
            for term in set(_extract_terms(chunk.text)):
                df[term] = df.get(term, 0) + 1
        return {t: math.log((n + 1) / (count + 1)) + 1 for t, count in df.items()}

    def _tfidf_keywords(self, chunk: NormChunk) -> List[str]:
        """
        Compute and return the top-5 TF-IDF keywords for a single chunk.

        TF = raw term count within the chunk.
        TF-IDF score = TF * IDF (IDF pre-computed across the full corpus).

        Ranking: descending TF-IDF score → prefer bigrams over same-score
        unigrams → alphabetical tie-break.  This ensures bigrams surface
        when they carry equal information to unigrams.

        Parameters
        ----------
        chunk : NormChunk to extract keywords from.

        Returns
        -------
        List[str] — up to 5 keywords, ordered by rank.
        """
        terms = _extract_terms(chunk.text)
        if not terms:
            return []

        tf: Dict[str, int] = {}
        for t in terms:
            tf[t] = tf.get(t, 0) + 1

        scores = {t: cnt * self._idf.get(t, 1.0) for t, cnt in tf.items()}

        # Sort: descending score → prefer bigrams (more words = richer) → alphabetical
        ranked = sorted(
            scores.items(),
            key=lambda x: (-x[1], -len(x[0].split()), x[0]),
        )
        return [t for t, _ in ranked[:5]]

    @staticmethod
    def _bm25_tokens(chunk: NormChunk) -> List[str]:
        """
        Build the BM25 token list for a chunk from three sources.

        Sources (applied in order, with order-preserving deduplication):
          1. Word tokens from chunk.text — stop-word filtered alphabetic words.
          2. Clause-digit tokens — digits extracted from the clause number,
             e.g. "7.5.2" → ["7", "5", "2"].  Enables exact-digit lookups.
          3. Keyword tokens — word-level tokens from chunk.keywords (which must
             already be populated before calling this method).

        These tokens are stored in chunk.bm25_tokens and are NEVER sent to
        ChromaDB (enforced via NormChunk field metadata={"chroma": False}).

        Parameters
        ----------
        chunk : NormChunk with keywords already populated.

        Returns
        -------
        List[str] — deduplicated tokens in source order.
        """
        clean       = _MARKDOWN_NOISE_RE.sub(' ', chunk.text)
        word_tokens = [
            w.lower() for w in _WORD_RE.findall(clean)
            if w.lower() not in _STOP_WORDS
        ]
        # Digit tokens from clause number (non-digit chars stripped, then split)
        clause_tokens = re.sub(r'[^0-9]', ' ', chunk.clause_number).split()

        # Word-level tokens from TF-IDF keywords (keywords set in _tfidf_keywords)
        kw_tokens: List[str] = []
        for kw in chunk.keywords:
            kw_tokens.extend(kw.lower().split())

        seen:   set       = set()
        result: List[str] = []
        for t in word_tokens + clause_tokens + kw_tokens:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return result

    # ── Public API ────────────────────────────────────────────────────────────

    def enrich(self, chunks: List[NormChunk]) -> List[NormChunk]:
        """
        Enrich all chunks in-place with keywords and BM25 tokens.

        Order matters: keywords must be set before bm25_tokens because
        _bm25_tokens() reads chunk.keywords to include keyword word-tokens.

        Parameters
        ----------
        chunks : List of NormChunks to enrich.  Must be the same list (or a
                 subset) used to initialise the Enricher.

        Returns
        -------
        List[NormChunk] — the same list, mutated in-place.
        """
        for chunk in chunks:
            chunk.keywords    = self._tfidf_keywords(chunk)       # pass 1
            chunk.bm25_tokens = self._bm25_tokens(chunk)          # pass 2 (reads keywords)
        return chunks
