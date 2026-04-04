"""
Querytransformer.py
===================
Scans text for ISO management system vocabulary and augments BM25 token sets.
Also provides the norm filter builder.

Public API
----------
    transform(query_text, norm_filter, language)  -> TransformedQuery full pipeline entry point
    scan_iso_vocabulary(text, language)           -> List[str]       canonical hits + clause numbers
    augment_bm25_tokens(base, iso_hits)           -> List[str]       merged token set, no duplicates
    build_norm_filter(norm_filter, language)       -> Filter          Qdrant filter restricting to norms + language
"""

from typing import List, Set

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from rag.retrival.models import TransformedQuery
from rag.shared.bm25.tokenizer import tokenize_for_bm25
from rag.shared.vocabulary.scanner import (
    CLAUSE_PATTERN,
    scan_iso_vocabulary,
)


def augment_bm25_tokens(base_tokens: List[str], iso_hits: List[str]) -> List[str]:
    """
    Merge *iso_hits* into *base_tokens* without introducing duplicates.

    Clause numbers (e.g. "8.5") are expanded into their digit parts ("8", "5")
    to match the ingestion tokenisation format where "8.5.1" was stored as
    individual tokens ["8", "5", "1"].

    All other hits (canonical phrases, modal terms) are split into unigrams
    before injection so that multi-word phrases like "corrective action" produce
    ["corrective", "action"] — matching how ingestion splits keyword bigrams via
    the shared tokenizer.
    The original *base_tokens* are always preserved.
    """
    token_set: Set[str] = set(base_tokens)

    for term in iso_hits:
        if CLAUSE_PATTERN.fullmatch(term):
            # Expand "8.5.1" -> "8", "5", "1"
            for digit_part in term.split("."):
                token_set.add(digit_part)
        else:
            # Split bigrams/phrases into unigrams to match index-time tokenisation
            for word in term.lower().split():
                token_set.add(word)

    return list(token_set)


# ---------------------------------------------------------------------------
# Norm filter builder
# ---------------------------------------------------------------------------

def build_norm_filter(
    norm_filter: List[str],
    language: str = "EN",
    clause_families: List[str] = [],
) -> Filter:
    """
    Build a Qdrant ``Filter`` that restricts search to the requested norm(s)
    and the specified language.

    Parameters
    ----------
    norm_filter:
        Non-empty list of norm IDs (e.g. ``["ISO9001"]`` or
        ``["ISO9001", "ISO14001"]``).  An empty list is a caller error
        and raises ``ValueError`` immediately — do not pass it to Qdrant.
    language:
        ``"EN"`` (default) or ``"FR"``.  Appended as a ``must`` condition on
        the ``language`` payload field so Qdrant only scores chunks in the
        correct language.
    clause_families:
        Optional top-level clause family IDs (e.g. ``["8"]``).  When
        non-empty, a ``must`` condition on ``clause_family`` is appended so
        Qdrant restricts results to chunks whose ``clause_number`` belongs to
        any of the specified families (e.g. "8", "8.1", "8.5.1" all share
        family "8").  Empty list → no clause filter applied.

    Returns
    -------
    Filter
        A ``must`` filter combining ``norm_id``, ``language``, and optionally
        ``clause_family`` conditions.
        Single value → ``MatchValue``; multiple → ``MatchAny``.

    Raises
    ------
    ValueError
        If *norm_filter* is empty.
    """
    if not norm_filter:
        raise ValueError("norm_filter must not be empty")

    if len(norm_filter) == 1:
        match = MatchValue(value=norm_filter[0])
    else:
        match = MatchAny(any=norm_filter)

    conditions = [
        FieldCondition(key="norm_id", match=match),
        FieldCondition(key="language", match=MatchValue(value=language)),
    ]

    if clause_families:
        family_match = (
            MatchValue(value=clause_families[0])
            if len(clause_families) == 1
            else MatchAny(any=clause_families)
        )
        conditions.append(FieldCondition(key="clause_family", match=family_match))

    return Filter(must=conditions)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def transform(
    query_text: str,
    norm_filter: List[str],
    language: str = "EN",
    clause_families: List[str] = [],
    specific_clauses: List[str] = [],
) -> TransformedQuery:
    """
    Full pipeline entry point — orchestrates vocabulary scan and BM25 augmentation.

    Steps:
    1. Build the Qdrant norm filter (raises ``ValueError`` if empty).
    2. Scan the query text for ISO vocabulary.
    3. Tokenise and augment BM25 tokens (injecting specific_clauses as soft boost).
    4. Return a ``TransformedQuery``.

    Parameters
    ----------
    query_text:
        Raw user text to transform.
    norm_filter:
        Non-empty list of norm IDs (e.g. ``["ISO9001"]``).
    language:
        ``"EN"`` (default) or ``"FR"``.  Determines the ISO vocabulary used
        for scanning and the Qdrant language filter.
    clause_families:
        Optional top-level clause family IDs (e.g. ``["8"]``).  When
        non-empty, a hard Qdrant filter on ``clause_family`` is added — only
        chunks belonging to these families are returned.  All children are
        included automatically (e.g. "8" matches "8.1", "8.5.1", etc.).
        Empty list → no clause filter (default behaviour).
    specific_clauses:
        Optional sub-clause IDs for soft BM25 boosting (e.g. ``["8.5"]``).
        These are injected into the BM25 token set using the same digit-split
        convention as the rest of the pipeline ("8.5" → ["8", "5"]), boosting
        sparse recall without imposing a hard filter.
        Empty list → no boost (default behaviour).

    Returns
    -------
    TransformedQuery
    """
    # 1. Norm filter (fast, raises on empty list); clause_families added when present
    qdrant_filter = build_norm_filter(norm_filter, language, clause_families)

    # 2. ISO vocabulary scan
    iso_vocab_hits = scan_iso_vocabulary(query_text, language, norm_filter)

    # 3. BM25 tokens — merge iso hits + specific_clauses for soft boosting
    clause_hit = CLAUSE_PATTERN.search(query_text)
    base_tokens = tokenize_for_bm25(
        text=query_text,
        clause_ref=clause_hit.group(0) if clause_hit else None,
    )
    # specific_clauses are treated as clause-number hits so augment_bm25_tokens
    # expands "8.5" → ["8", "5"] via the CLAUSE_PATTERN fullmatch branch.
    combined_hits = iso_vocab_hits + list(specific_clauses)
    bm25_tokens = augment_bm25_tokens(base_tokens, combined_hits)

    # 4. Assemble result
    # "search_query:" instruction prefix required by nomic-embed-text to route
    # query vectors into the correct retrieval subspace.
    # Must be paired with "search_document:" at ingestion time (embedder.py).
    embed_text = f"search_query: {query_text}"
    return TransformedQuery(
        embed_text=embed_text,
        bm25_tokens=bm25_tokens,
        qdrant_filter=qdrant_filter,
        hyde_used=False,
        iso_vocab_hits=iso_vocab_hits,
        original_query=query_text,
        language=language,
        norm_filter=norm_filter,
        clause_families=list(clause_families),
    )
