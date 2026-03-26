"""
Querytransformer.py
===================
Scans text for ISO management system vocabulary and augments BM25 token sets.
Also provides the HyDE trigger decision gate, HyDE generation, and norm filter builder.

Public API
----------
    transform(query_text, norm_filter, language)  -> TransformedQuery full pipeline entry point
    scan_iso_vocabulary(text, language)           -> List[str]       canonical hits + clause numbers
    augment_bm25_tokens(base, iso_hits)           -> List[str]       merged token set, no duplicates
    should_use_hyde(text, language)               -> bool            True when HyDE should run
    generate_hyde_text(text, norm_filter, lang)   -> Optional[str]   hypothetical ISO clause or None
    build_norm_filter(norm_filter, language)       -> Filter          Qdrant filter restricting to norms + language
"""

import asyncio
import os
import re
from typing import List, Optional, Set

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from models import TransformedQuery

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


def scan_iso_vocabulary(text: str, language: str = "EN") -> List[str]:
    """
    Scan *text* for ISO vocabulary hits.

    Only the vocabulary for *language* is consulted (
    ``"EN"`` → ``ISO_VOCABULARY_EN``, 
    ``"FR"`` → ``ISO_VOCABULARY_FR``), avoiding
    cross-language false positives.

    When any surface form matches, the **canonical key** is recorded (one entry
    per canonical term, regardless of how many surface forms matched).
    Also records any clause-number patterns and modal terms found.

    Returns a sorted list — suitable for direct assignment to
    ``TransformedQuery.iso_vocab_hits`` and for the HyDE trigger check
    (len < 3 → trigger HyDE).
    """
    text_lower = text.lower()
    hits: Set[str] = set()

    # --- ISO vocabulary (language-specific) ---
    vocab = ISO_VOCABULARY_EN if language == "EN" else ISO_VOCABULARY_FR
    for canonical_key, surface_forms in vocab.items():
        for form in surface_forms:
            if form.lower() in text_lower:
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


def augment_bm25_tokens(base_tokens: List[str], iso_hits: List[str]) -> List[str]:
    """
    Merge *iso_hits* into *base_tokens* without introducing duplicates.

    Clause numbers (e.g. "8.5") are expanded into their digit parts ("8", "5")
    to match the ingestion tokenisation format where "8.5.1" was stored as
    individual tokens ["8", "5", "1"].

    All other hits (canonical phrases, modal terms) are injected as-is.
    The original *base_tokens* are always preserved.
    """
    token_set: Set[str] = set(base_tokens)

    for term in iso_hits:
        if CLAUSE_PATTERN.fullmatch(term):
            # Expand "8.5.1" → "8", "5", "1"
            for digit_part in term.split("."):
                token_set.add(digit_part)
        else:
            token_set.add(term)

    return list(token_set)


# ---------------------------------------------------------------------------
# HyDE decision gate
# ---------------------------------------------------------------------------

_HYDE_TOKEN_THRESHOLD = 150   # estimated tokens below which HyDE always fires
_HYDE_VOCAB_THRESHOLD = 3     # ISO vocab hits below which HyDE fires for long texts


def should_use_hyde(text: str, language: str = "EN") -> bool:
    """
    Return True when HyDE should be applied to *text*.

    Two signals are combined:

    1. **Token count** — estimated as ``len(text.split()) * 1.3``.
       Short texts (< 150 estimated tokens) always trigger HyDE: sparse
       vocabulary needs expansion regardless of ISO term density.

    2. **ISO vocabulary hits** — checked only for longer texts.
       If the text already contains 3 or more ISO canonical terms it is
       already written in norm language; embedding directly is sufficient.
       Fewer than 3 hits means a vocabulary gap exists → trigger HyDE.

    The short-circuit on token count avoids running ``scan_iso_vocabulary``
    for texts that will trigger anyway.
    """
    estimated_tokens = len(text.split()) * 1.3
    if estimated_tokens < _HYDE_TOKEN_THRESHOLD:
        return True
    return len(scan_iso_vocabulary(text, language)) < _HYDE_VOCAB_THRESHOLD

# ---------------------------------------------------------------------------
# HyDE generation
# ---------------------------------------------------------------------------

# Prompt templates — version-controlled here, not inside the function.
# Edit these strings to iterate on HyDE output quality.
_HYDE_PROMPT_TEMPLATE = """\
You are writing body text from an ISO management system standard.
Based on the following operational text, write a 2-4 sentence hypothetical ISO clause \
that would govern this activity. Target standard(s): {standards}.

Rules:
- Use prescriptive normative language: "shall", "must", "is required to".
- Do NOT include a clause number, section heading, or title — start directly with "The organization" or equivalent.
- Do NOT explain, summarize, or add caveats. Output ONLY the clause body text.

Operational text:
{text}

ISO clause body:"""

_HYDE_PROMPT_TEMPLATE_FR = """\
Vous rédigez le corps d'un texte extrait d'un référentiel de système de management ISO.
À partir du texte opérationnel suivant, rédigez une clause ISO hypothétique de 2 à 4 phrases \
qui régirait cette activité. Référentiel(s) cible(s) : {standards}.

Règles :
- Utilisez un langage normatif prescriptif : "doit", "est tenu de", "est requis de".
- N'incluez PAS de numéro de clause, d'en-tête ou de titre — commencez directement par "L'organisme" ou équivalent.
- N'expliquez pas, ne résumez pas et n'ajoutez pas de réserves. Produisez UNIQUEMENT le corps de la clause.

Texte opérationnel :
{text}

Corps de la clause ISO :"""

_HYDE_TIMEOUT: float = float(os.getenv("HYDE_TIMEOUT", "15.0"))  # 15s covers llama3.2:3b locally (~10 tok/s × 100 tok); cloud APIs are faster
_HYDE_RETRIES: int = 2        # total attempts before giving up
_HYDE_RETRY_SLEEP: float = 0.5  # seconds to wait between attempts


async def generate_hyde_text(
    text: str, norm_filter: List[str], language: str = "EN"
) -> Optional[str]:
    """
    Generate a hypothetical ISO clause for the given operational text.

    Calls the LLM client (provider selected by ``LLM_PROVIDER`` env var) with a
    hard per-attempt timeout of 5 s and up to 2 total attempts.

    Returns the generated clause text on success, or ``None`` if every attempt
    fails (timeout, network error, empty response).  Failure is **silent and
    non-fatal** — callers must fall back to the original text and set
    ``hyde_used = False``.

    Parameters
    ----------
    text:
        The operational procedure text to transform into an ISO clause.
    norm_filter:
        List of norm IDs (e.g. ``["ISO9001"]``).  Used to target the prompt.
        If empty, defaults to ``"ISO 9001"``.
    language:
        ``"EN"`` (default) or ``"FR"``.  Selects the prompt template so the
        generated clause is in the same language as the query.
    """
    from clients.llm_client import chat_complete  # deferred — avoids hard dep at module level

    standards = ", ".join(norm_filter) if norm_filter else "ISO 9001"
    template = _HYDE_PROMPT_TEMPLATE if language == "EN" else _HYDE_PROMPT_TEMPLATE_FR
    prompt = template.format(standards=standards, text=text)

    for attempt in range(_HYDE_RETRIES):
        try:
            result = await asyncio.wait_for(
                chat_complete(prompt, max_tokens=100),
                timeout=_HYDE_TIMEOUT,
            )
            if result:
                return result
        except Exception:  # TimeoutError, ConnectionError, HTTP errors, etc.
            pass
        if attempt < _HYDE_RETRIES - 1:
            await asyncio.sleep(_HYDE_RETRY_SLEEP)

    return None


# ---------------------------------------------------------------------------
# Norm filter builder
# ---------------------------------------------------------------------------

def build_norm_filter(norm_filter: List[str], language: str = "EN") -> Filter:
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

    Returns
    -------
    Filter
        A ``must`` filter combining ``norm_id`` and ``language`` conditions.
        Single standard → ``MatchValue``; multiple → ``MatchAny``.

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

    return Filter(must=[
        FieldCondition(key="norm_id", match=match),
        FieldCondition(key="language", match=MatchValue(value=language)),
    ])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def transform(
    query_text: str, norm_filter: List[str], language: str = "EN"
) -> TransformedQuery:
    """
    Full pipeline entry point — orchestrates all sub-systems.

    Ordered steps (HyDE runs *before* vocabulary scan so the generated
    ISO-style text gets scanned, not the raw operational text):

    1. Build the Qdrant norm filter (raises ``ValueError`` if empty).
    2. Decide whether HyDE should run.
    3. If HyDE triggered, generate hypothetical clause; fall back on failure.
    4. Scan the (possibly HyDE-rewritten) text for ISO vocabulary.
    5. Tokenise and augment BM25 tokens.
    6. Return a ``TransformedQuery``.

    Parameters
    ----------
    query_text:
        Raw operational / user text to transform.
    norm_filter:
        Non-empty list of norm IDs (e.g. ``["ISO9001"]``).
    language:
        ``"EN"`` (default) or ``"FR"``.  Determines the ISO vocabulary used
        for scanning, the HyDE prompt language, and the Qdrant language filter.

    Returns
    -------
    TransformedQuery
    """
    # 1. Norm filter (fast, raises on empty list)
    qdrant_filter = build_norm_filter(norm_filter, language)

    # 2 + 3. HyDE
    hyde_triggered = should_use_hyde(query_text, language)
    if hyde_triggered:
        hyde_text = await generate_hyde_text(query_text, norm_filter, language)
        if hyde_text:
            embed_text = hyde_text
            hyde_used = True
        else:
            embed_text = query_text
            hyde_used = False
    else:
        embed_text = query_text
        hyde_used = False

    # 4. ISO vocabulary scan (on post-HyDE text)
    iso_vocab_hits = scan_iso_vocabulary(embed_text, language)

    # 5. BM25 tokens
    base_tokens = embed_text.lower().split()
    bm25_tokens = augment_bm25_tokens(base_tokens, iso_vocab_hits)

    # 6. Assemble result
    return TransformedQuery(
        embed_text=embed_text,
        bm25_tokens=bm25_tokens,
        qdrant_filter=qdrant_filter,
        hyde_used=hyde_used,
        iso_vocab_hits=iso_vocab_hits,
        original_query=query_text,
        language=language,
    )
