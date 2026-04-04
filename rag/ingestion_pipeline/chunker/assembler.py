"""
chunker/assembler.py
─────────────────────
Phase 4 — NormChunk Assembly

Converts a flat list of ClauseSpan objects (from the segmenter) into a list
of NormChunk objects ready for retrieval enrichment.

Core responsibilities:
  1. Text extraction  — slice each clause's text from the assembled markdown.
  2. Overflow splitting — clauses exceeding MAX_CHUNK_WORDS are split at
     paragraph boundaries into part1, part2, … preserving context.
  3. Modality detection — bilingual (EN + FR) regex pass to classify each
     chunk and count modal verbs.
  4. Cross-reference extraction — collects clause refs, ISO refs, and annex
     refs mentioned in the text body.
  5. Optional LLM refinement — Mistral 7B via Ollama (off by default;
     enable with LLM_NORMALISATION=true).
  6. Regression test — _regression_7_5_2() validates that §7.5.2 yields
     3–4 discrete obligations; NEVER remove this test.

Environment variables
---------------------
  MAX_CHUNK_WORDS    : int  — split threshold (default 600)
  LLM_NORMALISATION  : bool — enable Ollama LLM pass (default false)
  LLM_MODEL          : str  — Ollama model name (default "mistral")
  OLLAMA_URL         : str  — Ollama HTTP endpoint

Dependency rule: imports only from chunker.models, segmenter.*, and the
standard library. No enricher or registry imports.
"""

import json as _json
import os
import re
import urllib.request
import warnings
from typing import List, Tuple

from rag.ingestion_pipeline.segmenter.models import (
    NORM_ID_MAP,
    NORM_VERSION_MAP,
    STANDARD_ID_MAP,
    ClauseSpan,
    ContentType,
)
from rag.ingestion_pipeline.segmenter.page_tracker import PageTracker

from .models import NormChunk


# ==============================================================================
# Environment-controlled configuration
# ==============================================================================

# Maximum word count per chunk before paragraph-boundary splitting is applied.
MAX_CHUNK_WORDS: int = int(os.getenv("MAX_CHUNK_WORDS", "600"))

# LLM pass is intentionally OFF — set LLM_NORMALISATION=true to enable.
LLM_NORMALISATION: bool = os.getenv("LLM_NORMALISATION", "false").lower() == "true"

# Ollama model and endpoint for the optional LLM refinement pass.
_LLM_MODEL: str  = os.getenv("LLM_MODEL",   "mistral")
_OLLAMA_URL: str = os.getenv("OLLAMA_URL",   "http://localhost:11434/api/generate")


# ==============================================================================
# Bilingual modality regexes (document may be in French or English)
# ==============================================================================

# SHALL — hard requirement markers
_SHALL_RE = re.compile(
    r'\b(shall|must|is required to|are required to|doit|doivent)\b',
    re.IGNORECASE,
)

# SHOULD — recommendation markers
_SHOULD_RE = re.compile(
    r'\b(should|il convient|it is recommended|devrait|devraient)\b',
    re.IGNORECASE,
)

# MAY — permission markers
_MAY_RE = re.compile(r'\b(may|peut|peuvent)\b', re.IGNORECASE)

# CAN — capability markers (modal sense)
_CAN_RE = re.compile(r'\bcan\b', re.IGNORECASE)


# ==============================================================================
# Cross-reference extraction regexes
# ==============================================================================

# English: "see clause 4.1", "section 8.5.2"
_CLAUSE_REF_RE = re.compile(
    r'(?:see\s+)?(?:clause|section)\s+(\d+(?:\.\d+)*)',
    re.IGNORECASE,
)

# French: "voir 4.4", "référence en 4.1", "mentionnés en 4.2",
#         "conformément aux exigences de 6.1" — also handles \xa0 non-breaking space
_CLAUSE_REF_FR_RE = re.compile(
    r'(?:'
    r'voir'
    r'|r[eé]f[eé]rence\s+en'
    r'|mentionn[eé]e?s?\s+en'
    r'|conform[eé]ment\s+(?:aux\s+exigences\s+)?(?:de|[àa])'
    r')'
    r'[\s\xa0]+'
    r'(\d+(?:\.\d+)+)',   # clause number must contain at least one dot
    re.IGNORECASE,
)

# ISO document references: "ISO 9001", "ISO 14001-1:2015", etc.
_ISO_REF_RE = re.compile(
    r'\bISO[\s\xa0]+\d{4,5}(?:[-/]\d+)?(?::\d{4})?\b',
    re.IGNORECASE,
)

# Annex references: "Annex A", "Annexe B"
_ANNEX_REF_RE = re.compile(r'\bAnnex(?:e)?\s+([A-Z])\b', re.IGNORECASE)


# ==============================================================================
# Note / Example block markers
# ==============================================================================

# NOTE blocks: "NOTE", "NOTE 1:", "NOTE —"
_NOTE_BLOCK_RE = re.compile(r'^NOTE\s*\d*\s*[:\-—]?', re.IGNORECASE | re.MULTILINE)

# EXAMPLE blocks: "EXAMPLE", "EXAMPLE 2 —"
_EXAMPLE_BLOCK_RE = re.compile(r'^EXAMPLE\s*\d*\s*[:\-—]?', re.IGNORECASE | re.MULTILINE)

# Lettered sub-items — used by the permanent regression test
_LETTERED_ITEM_RE = re.compile(r'^\s*[a-z]\)\s', re.MULTILINE)


# ==============================================================================
# Public helper — chunk ID construction
# ==============================================================================

def build_chunk_id(
    standard_id: str,
    clause_id: str,
    part_suffix: str,
    first_page: int,
) -> str:
    """
    Build the canonical chunk identifier string.

    Format: {standard_id}_{clause_id}_{part_suffix}_p{first_page}
    Example: "n9001_8.5.1_part1_p23"

    IMPORTANT: never construct this string manually anywhere else in the
    pipeline.  All chunk ID generation must go through this function so the
    format stays consistent and is easy to update in one place.

    Parameters
    ----------
    standard_id  : PDF stem, e.g. "n9001".
    clause_id    : Clause identifier, e.g. "8.5.1" or "Annex A".
    part_suffix  : "part1", "part2", … — 1-based index within the clause.
    first_page   : PDF page number where this chunk begins.
    """
    return f"{standard_id}_{clause_id}_{part_suffix}_p{first_page}"


# ==============================================================================
# Private helpers
# ==============================================================================

def _strip_note_example_blocks(text: str) -> str:
    """
    Remove NOTE and EXAMPLE blocks from text before modality detection.

    A block begins at the NOTE/EXAMPLE marker line and continues until the
    first blank line.  Removing these prevents inflated shall/should counts
    caused by modal verbs that appear inside normative notes.

    The blank-line separator is preserved to maintain paragraph structure.

    Parameters
    ----------
    text : Raw clause text slice.

    Returns
    -------
    str — text with NOTE/EXAMPLE blocks stripped.
    """
    lines = text.split('\n')
    result: List[str] = []
    in_block = False

    for line in lines:
        stripped = line.strip()
        if _NOTE_BLOCK_RE.match(stripped) or _EXAMPLE_BLOCK_RE.match(stripped):
            in_block = True
            continue
        if in_block:
            if stripped == '':
                in_block = False
                result.append(line)   # keep the blank separator
            # continuation lines within the block are silently dropped
            continue
        result.append(line)

    return '\n'.join(result)


def _detect_modality(
    clean_text: str,
) -> Tuple[int, int, bool, bool, bool, bool, ContentType]:
    """
    Classify a text chunk by the modal verbs it contains.

    Detection is bilingual (English + French).  NOTE/EXAMPLE blocks must be
    stripped before calling this function (see _strip_note_example_blocks).

    Classification priority:
      1. Any SHALL → REQUIREMENT  (warns if SHOULD also present)
      2. Any SHOULD → RECOMMENDATION
      3. Non-empty text → INFORMATIVE
      4. Empty text   → STRUCTURAL

    Parameters
    ----------
    clean_text : Text with NOTE/EXAMPLE blocks removed.

    Returns
    -------
    (shall_count, should_count, has_requirements, has_permissions,
     has_recommendations, has_capabilities, content_type)
    """
    shall_count  = len(_SHALL_RE.findall(clean_text))
    should_count = len(_SHOULD_RE.findall(clean_text))
    has_req  = shall_count > 0
    has_perm = bool(_MAY_RE.search(clean_text))
    has_rec  = should_count > 0
    has_cap  = bool(_CAN_RE.search(clean_text))

    if has_req and has_rec:
        warnings.warn(
            "Chunk contains both SHALL and SHOULD — classifying as REQUIREMENT. "
            "Review clause boundaries if unexpected.",
            UserWarning,
            stacklevel=3,
        )

    if has_req:
        content_type = ContentType.REQUIREMENT
    elif has_rec:
        content_type = ContentType.RECOMMENDATION
    elif clean_text.strip():
        content_type = ContentType.INFORMATIVE
    else:
        content_type = ContentType.STRUCTURAL

    return shall_count, should_count, has_req, has_perm, has_rec, has_cap, content_type


def _detect_cross_refs(text: str) -> List[str]:
    """
    Extract all clause cross-references from text.

    Covers:
      • English: "see clause 4.1", "section 8.5"
      • French: "voir 4.4", "référence en 4.1", "conformément de 6.1"
      • ISO document refs: "ISO 9001", "ISO 14001-1:2015"
      • Annex refs: "Annex A", "Annexe B"

    Non-breaking spaces (\\xa0) are normalised to regular spaces in all
    returned strings.  Insertion order is preserved; duplicates are removed.

    Parameters
    ----------
    text : Raw clause text slice (not stripped of notes).

    Returns
    -------
    List[str] — deduplicated reference strings, ordered by first appearance.
    """
    def _norm(s: str) -> str:
        """Normalise whitespace including non-breaking spaces."""
        return re.sub(r'[\xa0\s]+', ' ', s).strip()

    refs: List[str] = []
    refs.extend(_CLAUSE_REF_RE.findall(text))
    refs.extend(_CLAUSE_REF_FR_RE.findall(text))
    refs.extend(_norm(m) for m in _ISO_REF_RE.findall(text))
    refs.extend(f"Annex {m}" for m in _ANNEX_REF_RE.findall(text))

    # Preserve insertion order, deduplicate
    seen: set = set()
    result: List[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            result.append(r)
    return result


def _split_text_at_paragraphs(
    text: str,
    max_words: int,
) -> List[Tuple[str, int]]:
    """
    Split *text* into (chunk_text, start_offset_in_text) pairs so that each
    chunk contains at most *max_words* words.

    Splits occur only at blank-line paragraph boundaries — mid-sentence splits
    are never introduced.

    When no split is needed the list contains a single element: [(text, 0)].

    Algorithm
    ---------
    1. Collect paragraph-boundary positions via \\n\\s*\\n.
    2. Walk segments greedily, flushing a part whenever adding the next segment
       would exceed max_words.

    Parameters
    ----------
    text      : Raw clause text (may be large).
    max_words : Word-count ceiling per part.

    Returns
    -------
    List of (part_text, start_offset) — start_offset is relative to the
    beginning of *text*, enabling conversion to absolute markdown offsets.
    """
    if len(text.split()) <= max_words:
        return [(text, 0)]

    boundaries: List[int] = [0]
    for m in re.finditer(r'\n\s*\n', text):
        boundaries.append(m.end())
    boundaries.append(len(text))

    parts: List[Tuple[str, int]] = []
    part_start      = 0
    part_word_count = 0

    for i in range(len(boundaries) - 1):
        seg_start  = boundaries[i]
        seg_end    = boundaries[i + 1]
        seg        = text[seg_start:seg_end]
        seg_words  = len(seg.split())

        if part_word_count + seg_words > max_words and part_word_count > 0:
            parts.append((text[part_start:seg_start], part_start))
            part_start      = seg_start
            part_word_count = seg_words
        else:
            part_word_count += seg_words

    parts.append((text[part_start:], part_start))
    return parts


def _llm_refine_obligations(text: str) -> List[str]:
    """
    Optional Pass 2: use Mistral 7B via Ollama to extract obligation sentences.

    Called only when LLM_NORMALISATION=true.  Always falls back to an empty
    list on any failure — the regex pass from _detect_modality is used instead.

    The LLM prompt asks for verbatim obligation sentences (one per line).

    Parameters
    ----------
    text : NOTE/EXAMPLE-stripped clause text (at most 2000 chars are sent).

    Returns
    -------
    List[str] — extracted obligation sentences, or [] on failure.
    """
    prompt = (
        "Extract all obligation sentences (containing shall, must, doit, doivent, or "
        "'is required to') from the following ISO standard clause. "
        "Return one obligation per line, verbatim.\n\n"
        f"{text[:2000]}"
    )
    payload = _json.dumps(
        {"model": _LLM_MODEL, "prompt": prompt, "stream": False}
    ).encode()

    try:
        req = urllib.request.Request(
            _OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = _json.loads(resp.read().decode())
        lines = [line.strip() for line in result.get("response", "").split('\n')
                 if line.strip()]
        return lines
    except Exception as exc:
        warnings.warn(
            f"LLM refinement failed ({exc}); falling back to regex.",
            UserWarning,
            stacklevel=3,
        )
        return []


# ==============================================================================
# Permanent regression test — DO NOT REMOVE
# ==============================================================================

def _regression_7_5_2(chunks: List[NormChunk]) -> None:
    """
    Permanent named regression: ISO 9001:2015 §7.5.2 must produce 3–4 discrete
    obligations.

    NEVER remove this test.

    §7.5.2 contains one 'doit' followed by lettered items a), b), c) — each item
    is a distinct obligation.  The counting rule:
      - If SHALL markers are present alongside lettered sub-items, count the
        lettered items (each is a discrete requirement).
      - Otherwise fall back to the raw SHALL-marker count.

    A mismatch issues a warning and helps detect regression in clause boundary
    detection or modality extraction.

    Parameters
    ----------
    chunks : Full list of NormChunks produced by assemble_norm_chunks().
             Silently does nothing if §7.5.2 is absent (e.g. a different standard).
    """
    target = [c for c in chunks if c.clause_number == "7.5.2"]
    if not target:
        return   # clause absent — skip silently (e.g. ISO 14001 has no §7.5.2)

    total_obligations = 0
    for chunk in target:
        clean          = _strip_note_example_blocks(chunk.text)
        shall_hits     = len(_SHALL_RE.findall(clean))
        lettered_items = len(_LETTERED_ITEM_RE.findall(clean))
        if shall_hits > 0 and lettered_items > 0:
            total_obligations += lettered_items
        else:
            total_obligations += shall_hits

    if not (3 <= total_obligations <= 4):
        warnings.warn(
            f"REGRESSION 7.5.2: expected 3–4 obligations, found {total_obligations}. "
            "Review clause boundary detection and modality extraction.",
            UserWarning,
            stacklevel=2,
        )


# ==============================================================================
# Phase 4 — Main assembly function
# ==============================================================================

def assemble_norm_chunks(
    spans: List[ClauseSpan],
    markdown: str,
    standard_id: str,
    tracker: PageTracker,
) -> List[NormChunk]:
    """
    Phase 4: convert each ClauseSpan into one or more NormChunk objects.

    Processing per span
    -------------------
    1. Extract raw text from the markdown using span offsets.
    2. Compute parent_clause ("8.5.1" → "8.5", top-level → "").
    3. Split at paragraph boundaries if text exceeds MAX_CHUNK_WORDS.
    4. For each split part:
         a. Resolve PDF page number via PageTracker.
         b. Build canonical chunk_id via build_chunk_id().
         c. Strip NOTE/EXAMPLE blocks.
         d. Run bilingual modality detection (_detect_modality).
         e. Optionally run LLM refinement pass (_llm_refine_obligations).
         f. Extract cross-references (_detect_cross_refs).
         g. Count tokens (whitespace split).
         h. Append NormChunk — keywords/bm25_tokens left empty for Phase 5.
    5. Run permanent regression test _regression_7_5_2().

    Parameters
    ----------
    spans       : Ordered ClauseSpan list from detect_clause_boundaries().
    markdown    : Full assembled markdown string from ParsedDocument.
    standard_id : PDF stem (e.g. "n9001").
    tracker     : PageTracker instance built from ParsedDocument.page_map.

    Returns
    -------
    List[NormChunk] — keywords and bm25_tokens fields are empty; Phase 5 fills them.
    """
    norm_id      = NORM_ID_MAP.get(standard_id, standard_id.upper())
    norm_full    = STANDARD_ID_MAP.get(standard_id, standard_id)
    norm_version = NORM_VERSION_MAP.get(standard_id, "")

    chunks: List[NormChunk] = []

    for span in spans:
        raw_text = markdown[span.start_idx:span.end_idx].strip()
        if not raw_text:
            continue

        # Parent clause: "8.5.1" → "8.5",  "8" → "",  preamble "0" → ""
        id_parts      = span.clause_id.split('.')
        parent_clause = '.'.join(id_parts[:-1]) if len(id_parts) > 1 else ""

        # Locate where stripped text starts within the markdown
        strip_offset = span.start_idx
        while strip_offset < span.end_idx and markdown[strip_offset] in ' \t\n\r':
            strip_offset += 1

        text_parts  = _split_text_at_paragraphs(raw_text, MAX_CHUNK_WORDS)
        total_parts = len(text_parts)

        for idx, (part_text, offset_in_raw) in enumerate(text_parts, start=1):
            abs_offset  = strip_offset + offset_in_raw
            first_page  = tracker.page_at(abs_offset)
            part_suffix = f"part{idx}"
            chunk_id    = build_chunk_id(standard_id, span.clause_id, part_suffix, first_page)

            # Pass 1 — regex-based modality detection on cleaned text
            clean = _strip_note_example_blocks(part_text)
            (shall_count, should_count, has_req, has_perm, has_rec,
             has_cap, content_type) = _detect_modality(clean)

            # Pass 2 — optional LLM refinement (off by default)
            if LLM_NORMALISATION and has_req:
                obligations = _llm_refine_obligations(clean)
                if obligations:
                    refined = ' '.join(obligations)
                    (shall_count, should_count, has_req, has_perm, has_rec,
                     has_cap, content_type) = _detect_modality(refined)

            related_clauses = _detect_cross_refs(part_text)
            token_count     = len(part_text.split())

            clause_family = span.clause_id.split(".")[0] if span.clause_id.strip() else ""

            chunks.append(NormChunk(
                chunk_id=chunk_id,
                norm_id=norm_id,
                norm_full=norm_full,
                norm_version=norm_version,
                clause_number=span.clause_id,
                clause_family=clause_family,
                clause_title=span.title,
                parent_clause=parent_clause,
                page_number=first_page,
                chunk_index=idx,
                total_chunks=total_parts,
                text=part_text,
                token_count=token_count,
                content_type=content_type,
                shall_count=shall_count,
                should_count=should_count,
                has_requirements=has_req,
                has_permissions=has_perm,
                has_recommendations=has_rec,
                has_capabilities=has_cap,
                keywords=[],           # Phase 5 (Enricher) fills this
                related_clauses=related_clauses,
                embedding_model="",    # set during the embedding step
            ))

    _regression_7_5_2(chunks)
    return chunks
