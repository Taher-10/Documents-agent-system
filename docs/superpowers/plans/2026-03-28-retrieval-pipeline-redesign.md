# Retrieval Pipeline Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix NC false-positive vocabulary injection, remove HyDE LLM dependency, and add nomic-embed-text asymmetric instruction prefixes to improve hybrid retrieval accuracy.

**Architecture:** Two independent stages. Stage 1 (Tasks 1–6) is code-only with no data changes — run against the existing Qdrant collection. Stage 2 (Tasks 7–9) adds embedding instruction prefixes and requires a full re-ingestion before validation.

**Tech Stack:** Python 3.12, pytest/unittest, Qdrant, Ollama nomic-embed-text, rag.shared.vocabulary, rag.retrival.query_transformer

---

## File Map

| File | Stage | Action |
|---|---|---|
| `rag/shared/vocabulary/tests/__init__.py` | 1 | Create (empty, makes directory a package) |
| `rag/shared/vocabulary/tests/test_scanner.py` | 1 | Create — unit tests for NC word-boundary fix |
| `rag/shared/vocabulary/scanner.py` | 1 | Modify — add `_FORM_PATTERNS` cache and `_form_pattern()`, change inner loop |
| `rag/retrival/query_transformer/tests/__init__.py` | 1 | Create (empty) |
| `rag/retrival/query_transformer/tests/test_transform.py` | 1 | Create — unit tests for sync transform() |
| `rag/retrival/query_transformer/Querytransformer.py` | 1+2 | Modify — remove HyDE, make sync; add `search_query:` prefix in Stage 2 |
| `rag/retrival/query_retrival/tests/smoketest/smoke_compare.py` | 1 | Modify — remove `await` from `transform(...)` call |
| `rag/retrival/query_retrival/tests/smoketest/smoke_hard_semantic.py` | 1 | Modify — remove `await` from `transform(...)` call |
| `rag/ingestion_pipeline/embedder/embedder.py` | 2 | Modify — `_build_embedding_text()` prepends `"search_document: "` |

---

## STAGE 1 — Correctness Fixes

---

### Task 1: Write failing tests for NC word-boundary fix

**Files:**
- Create: `rag/shared/vocabulary/tests/__init__.py`
- Create: `rag/shared/vocabulary/tests/test_scanner.py`

- [ ] **Step 1: Create the package init file**

```bash
touch "rag/shared/vocabulary/tests/__init__.py"
```

- [ ] **Step 2: Write the failing tests**

Create `rag/shared/vocabulary/tests/test_scanner.py`:

```python
"""
tests/test_scanner.py
─────────────────────
Unit tests for scan_iso_vocabulary() word-boundary matching.

Critical invariant: short surface forms like "NC" must only match as
standalone words, never as substrings inside longer words ("influencer",
"performances", "fonctions").

Run:
    pytest rag/shared/vocabulary/tests/test_scanner.py -v
"""
import unittest

from rag.shared.vocabulary.scanner import scan_iso_vocabulary


class TestNCFalsePositiveFR(unittest.TestCase):
    """'NC' inside common French words must NOT trigger non-conformité."""

    def test_nc_inside_influencer_no_hit(self):
        text = "L'organisme doit influencer ses processus externes."
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertNotIn("non-conformité", hits)

    def test_nc_inside_performances_no_hit(self):
        text = "surveiller les performances de l'organisme"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertNotIn("non-conformité", hits)

    def test_nc_inside_fonctions_no_hit(self):
        text = "les fonctions et responsabilités définies"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertNotIn("non-conformité", hits)

    def test_nc_inside_lancement_no_hit(self):
        text = "le lancement du nouveau produit est planifié"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertNotIn("non-conformité", hits)

    def test_nc_inside_tendances_no_hit(self):
        text = "analyser les tendances des résultats"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertNotIn("non-conformité", hits)


class TestNCTruePositiveFR(unittest.TestCase):
    """Standalone 'NC' MUST trigger non-conformité."""

    def test_standalone_nc_hits(self):
        text = "un NC a été détecté lors de l'audit"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertIn("non-conformité", hits)

    def test_nc_at_start_of_text_hits(self):
        text = "NC détectée sur la ligne de production"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertIn("non-conformité", hits)

    def test_nc_at_end_of_text_hits(self):
        text = "le produit a été rejeté pour NC"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertIn("non-conformité", hits)

    def test_nc_with_punctuation_hits(self):
        text = "traitement de la NC, clôture de l'action"
        hits = scan_iso_vocabulary(text, language="FR", norm_filter=["ISO9001"])
        self.assertIn("non-conformité", hits)


class TestNCFalsePositiveEN(unittest.TestCase):
    """'NC' inside common English words must NOT trigger nonconformity."""

    def test_nc_inside_incremental_no_hit(self):
        text = "an incremental approach to improvement"
        hits = scan_iso_vocabulary(text, language="EN", norm_filter=["ISO9001"])
        self.assertNotIn("nonconformity", hits)

    def test_nc_inside_anced_no_hit(self):
        text = "balanced scorecard for performance management"
        hits = scan_iso_vocabulary(text, language="EN", norm_filter=["ISO9001"])
        self.assertNotIn("nonconformity", hits)


class TestNCTruePositiveEN(unittest.TestCase):
    """Standalone 'NC' MUST trigger nonconformity in EN."""

    def test_standalone_nc_hits(self):
        text = "the NC was identified during the audit"
        hits = scan_iso_vocabulary(text, language="EN", norm_filter=["ISO9001"])
        self.assertIn("nonconformity", hits)

    def test_nc_uppercase_hits(self):
        text = "Track each NC through to closure"
        hits = scan_iso_vocabulary(text, language="EN", norm_filter=["ISO9001"])
        self.assertIn("nonconformity", hits)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/shared/vocabulary/tests/test_scanner.py -v
```

Expected: multiple FAIL — `assertNotIn` failures for `test_nc_inside_influencer_no_hit` etc. because substring matching currently passes "NC" inside those words.

---

### Task 2: Implement NC word-boundary fix in scanner.py

**Files:**
- Modify: `rag/shared/vocabulary/scanner.py`

- [ ] **Step 1: Add the pattern cache and helper just after the `MODAL_TERMS` list**

Open `rag/shared/vocabulary/scanner.py`. After line 35 (the closing `]` of `MODAL_TERMS`), add:

```python

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
```

- [ ] **Step 2: Replace the substring check in scan_iso_vocabulary()**

In `scan_iso_vocabulary()`, change the inner loop from:

```python
        for form in entry["forms"]:
            if form.lower() in text_lower:
                hits.add(canonical_key)
                break  # first match wins; skip remaining surface forms
```

to:

```python
        for form in entry["forms"]:
            if _form_pattern(form).search(text_lower):
                hits.add(canonical_key)
                break  # first match wins; skip remaining surface forms
```

- [ ] **Step 3: Run the new tests to confirm they pass**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/shared/vocabulary/tests/test_scanner.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 4: Run the BM25 unit tests to confirm no regression**

```bash
pytest rag/retrival/query_retrival/tests/test_sparse_encoder_query.py -v
```

Expected: 12/12 PASS.

- [ ] **Step 5: Commit**

```bash
git add rag/shared/vocabulary/tests/__init__.py \
        rag/shared/vocabulary/tests/test_scanner.py \
        rag/shared/vocabulary/scanner.py
git commit -m "fix: replace NC substring match with word-boundary regex in vocabulary scanner"
```

---

### Task 3: Write failing tests for sync transform()

**Files:**
- Create: `rag/retrival/query_transformer/tests/__init__.py`
- Create: `rag/retrival/query_transformer/tests/test_transform.py`

- [ ] **Step 1: Create the package init file**

```bash
touch "rag/retrival/query_transformer/tests/__init__.py"
```

- [ ] **Step 2: Write the failing tests**

Create `rag/retrival/query_transformer/tests/test_transform.py`:

```python
"""
tests/test_transform.py
────────────────────────
Unit tests for QueryTransformer.transform().

Verifies:
1. transform() is synchronous (not a coroutine)
2. hyde_used is always False
3. embed_text equals the input query (Stage 1) — updated in Stage 2 to check prefix
4. bm25_tokens are non-empty for ISO-vocabulary queries
5. qdrant_filter is constructed (non-None)
6. iso_vocab_hits contains expected canonical terms

Run:
    pytest rag/retrival/query_transformer/tests/test_transform.py -v
"""
import inspect
import unittest

from rag.retrival.query_transformer.Querytransformer import transform


class TestTransformIsSync(unittest.TestCase):
    """transform() must be a plain synchronous function, not a coroutine."""

    def test_transform_is_not_coroutine(self):
        self.assertFalse(
            inspect.iscoroutinefunction(transform),
            "transform() must be sync — remove async def",
        )

    def test_transform_returns_transformed_query_not_coroutine(self):
        result = transform("audit interne", norm_filter=["ISO9001"], language="FR")
        # If still async, result would be a coroutine object, not TransformedQuery
        self.assertFalse(
            inspect.iscoroutine(result),
            "transform() returned a coroutine — it must be sync",
        )
        if inspect.iscoroutine(result):
            result.close()  # prevent ResourceWarning


class TestTransformHydeAlwaysFalse(unittest.TestCase):
    """hyde_used must always be False regardless of query content."""

    def test_short_query_hyde_false(self):
        tq = transform("NC", norm_filter=["ISO9001"], language="FR")
        self.assertFalse(tq.hyde_used)

    def test_long_operational_query_hyde_false(self):
        query = (
            "L'organisation analyse régulièrement les facteurs internes "
            "et externes susceptibles d'influencer ses performances"
        )
        tq = transform(query, norm_filter=["ISO9001"], language="FR")
        self.assertFalse(tq.hyde_used)

    def test_english_query_hyde_false(self):
        tq = transform("document control and records management", norm_filter=["ISO9001"], language="EN")
        self.assertFalse(tq.hyde_used)


class TestTransformEmbedText(unittest.TestCase):
    """embed_text must equal the input query (Stage 1 — no prefix yet)."""

    def test_embed_text_equals_input(self):
        query = "audit interne planifié"
        tq = transform(query, norm_filter=["ISO9001"], language="FR")
        self.assertEqual(tq.embed_text, query)

    def test_original_query_preserved(self):
        query = "revue de direction"
        tq = transform(query, norm_filter=["ISO9001"], language="FR")
        self.assertEqual(tq.original_query, query)


class TestTransformBm25Tokens(unittest.TestCase):
    """bm25_tokens must be non-empty for vocabulary-bearing queries."""

    def test_iso_vocab_query_produces_tokens(self):
        tq = transform("audit interne planifié", norm_filter=["ISO9001"], language="FR")
        self.assertGreater(len(tq.bm25_tokens), 0)

    def test_english_iso_vocab_produces_tokens(self):
        tq = transform("internal audit planning and programme", norm_filter=["ISO9001"], language="EN")
        self.assertGreater(len(tq.bm25_tokens), 0)


class TestTransformVocabHits(unittest.TestCase):
    """iso_vocab_hits must contain expected canonical terms."""

    def test_nc_standalone_fr_hits_nonconformite(self):
        tq = transform("un NC a été détecté lors de l'audit", norm_filter=["ISO9001"], language="FR")
        self.assertIn("non-conformité", tq.iso_vocab_hits)

    def test_nc_in_influencer_fr_no_nonconformite(self):
        """NC inside 'influencer' must NOT appear in vocab hits."""
        tq = transform(
            "les facteurs susceptibles d'influencer les performances",
            norm_filter=["ISO9001"],
            language="FR",
        )
        self.assertNotIn("non-conformité", tq.iso_vocab_hits)

    def test_norm_filter_is_applied(self):
        tq = transform("système de management", norm_filter=["ISO9001"], language="FR")
        self.assertIsNotNone(tq.qdrant_filter)


class TestTransformNormFilter(unittest.TestCase):
    """Empty norm_filter must raise ValueError."""

    def test_empty_norm_filter_raises(self):
        with self.assertRaises(ValueError):
            transform("any query", norm_filter=[], language="EN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 3: Run tests to confirm the sync tests fail**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/retrival/query_transformer/tests/test_transform.py -v
```

Expected: `test_transform_is_not_coroutine` and `test_transform_returns_transformed_query_not_coroutine` FAIL (transform is currently async). Other tests may also fail with `RuntimeWarning: coroutine was never awaited`.

---

### Task 4: Remove HyDE from Querytransformer.py

**Files:**
- Modify: `rag/retrival/query_transformer/Querytransformer.py`

- [ ] **Step 1: Replace the entire file content**

Rewrite `rag/retrival/query_transformer/Querytransformer.py` to the following. Every removed function is gone entirely — no stubs, no comments referencing them:

```python
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

from typing import List, Optional, Set

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from rag.retrival.models import TransformedQuery
from rag.shared.bm25.tokenizer import tokenize_for_bm25
from rag.shared.vocabulary.scanner import (
    CLAUSE_PATTERN,
    MODAL_TERMS,
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

def transform(
    query_text: str,
    norm_filter: List[str],
    language: str = "EN",
) -> TransformedQuery:
    """
    Full pipeline entry point — orchestrates vocabulary scan and BM25 augmentation.

    Steps:
    1. Build the Qdrant norm filter (raises ``ValueError`` if empty).
    2. Scan the query text for ISO vocabulary.
    3. Tokenise and augment BM25 tokens.
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

    Returns
    -------
    TransformedQuery
    """
    # 1. Norm filter (fast, raises on empty list)
    qdrant_filter = build_norm_filter(norm_filter, language)

    # 2. ISO vocabulary scan
    iso_vocab_hits = scan_iso_vocabulary(query_text, language, norm_filter)

    # 3. BM25 tokens
    clause_hit = CLAUSE_PATTERN.search(query_text)
    base_tokens = tokenize_for_bm25(
        text=query_text,
        clause_ref=clause_hit.group(0) if clause_hit else None,
    )
    bm25_tokens = augment_bm25_tokens(base_tokens, iso_vocab_hits)

    # 4. Assemble result
    return TransformedQuery(
        embed_text=query_text,
        bm25_tokens=bm25_tokens,
        qdrant_filter=qdrant_filter,
        hyde_used=False,
        iso_vocab_hits=iso_vocab_hits,
        original_query=query_text,
        language=language,
    )
```

- [ ] **Step 2: Run the transform tests to confirm they pass**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/retrival/query_transformer/tests/test_transform.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Run the BM25 unit tests to confirm no regression**

```bash
pytest rag/retrival/query_retrival/tests/test_sparse_encoder_query.py -v
```

Expected: 12/12 PASS.

- [ ] **Step 4: Commit**

```bash
git add rag/retrival/query_transformer/tests/__init__.py \
        rag/retrival/query_transformer/tests/test_transform.py \
        rag/retrival/query_transformer/Querytransformer.py
git commit -m "feat: remove HyDE from QueryTransformer, make transform() synchronous"
```

---

### Task 5: Update await → sync calls in smoke tests

**Files:**
- Modify: `rag/retrival/query_retrival/tests/smoketest/smoke_compare.py:316`
- Modify: `rag/retrival/query_retrival/tests/smoketest/smoke_hard_semantic.py:396`

- [ ] **Step 1: Run the caller audit grep**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
grep -rn "await transform" rag/
```

Expected output (two hits, both to fix):
```
rag/retrival/query_retrival/tests/smoketest/smoke_compare.py:316:            tq = await transform(tc.query, norm_filter=NORM_FILTER, language=LANGUAGE)
rag/retrival/query_retrival/tests/smoketest/smoke_hard_semantic.py:396:            tq = await transform(tc.query, norm_filter=NORM_FILTER, language=LANGUAGE)
```

- [ ] **Step 2: Fix smoke_compare.py**

In `rag/retrival/query_retrival/tests/smoketest/smoke_compare.py`, change line 316 from:

```python
            tq = await transform(tc.query, norm_filter=NORM_FILTER, language=LANGUAGE)
```

to:

```python
            tq = transform(tc.query, norm_filter=NORM_FILTER, language=LANGUAGE)
```

- [ ] **Step 3: Fix smoke_hard_semantic.py**

In `rag/retrival/query_retrival/tests/smoketest/smoke_hard_semantic.py`, change line 396 from:

```python
            tq = await transform(tc.query, norm_filter=NORM_FILTER, language=LANGUAGE)
```

to:

```python
            tq = transform(tc.query, norm_filter=NORM_FILTER, language=LANGUAGE)
```

- [ ] **Step 4: Run the caller audit grep again to confirm zero hits**

```bash
grep -rn "await transform" rag/
```

Expected: **no output**. If any line still appears, it must be fixed before continuing.

- [ ] **Step 5: Commit**

```bash
git add rag/retrival/query_retrival/tests/smoketest/smoke_compare.py \
        rag/retrival/query_retrival/tests/smoketest/smoke_hard_semantic.py
git commit -m "fix: remove await from transform() calls in smoke tests (now sync)"
```

---

### Task 6: Stage 1 validation

**Files:** none (validation only)

- [ ] **Step 1: Run all unit tests**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/shared/vocabulary/tests/test_scanner.py \
       rag/retrival/query_transformer/tests/test_transform.py \
       rag/retrival/query_retrival/tests/test_sparse_encoder_query.py -v
```

Expected: all tests PASS (13 + 10 + 12 = 35 tests).

- [ ] **Step 2: Run smoke_compare against existing collection**

```bash
python rag/retrival/query_retrival/tests/smoketest/smoke_compare.py
```

Expected: hybrid ≥ 14/15. If hybrid score is LOWER than before, check whether `await transform` was missed anywhere (run grep again).

- [ ] **Step 3: Run smoke_hard_semantic against existing collection**

```bash
python rag/retrival/query_retrival/tests/smoketest/smoke_hard_semantic.py
```

Expected: hybrid ≥ 18/20. If unexpected errors occur (TypeError, AttributeError), run `grep -rn "await transform" rag/` again — a missed callsite is the most likely cause.

---

## STAGE 2 — Embedding Prefix Migration

> **Prerequisite:** Stage 1 complete and all tests passing.
> **Warning:** Tasks 7 and 8 must be committed together before re-ingesting. Applying only one prefix side (document without query, or query without document) creates a vector space mismatch that will degrade retrieval below the pre-Stage-1 baseline.

---

### Task 7: Add search_document: prefix to ingestion embedder

**Files:**
- Modify: `rag/ingestion_pipeline/embedder/embedder.py:164-178`

- [ ] **Step 1: Update _build_embedding_text()**

In `rag/ingestion_pipeline/embedder/embedder.py`, change the `_build_embedding_text` method from:

```python
    @staticmethod
    def _build_embedding_text(chunk: NormChunk) -> str:
        """
        Build the string that will be sent to the embedding model.

        A structured prefix anchors the clause identity so that clauses
        sharing normative vocabulary (shall, documented information, …)
        produce distinct vectors in the embedding space.

        Format: "{norm_full} clause {clause_number} {clause_title}: {text}"
        """
        return (
            f"{chunk.norm_full} clause {chunk.clause_number} "
            f"{chunk.clause_title}: {chunk.text}"
        )
```

to:

```python
    @staticmethod
    def _build_embedding_text(chunk: NormChunk) -> str:
        """
        Build the string that will be sent to the embedding model.

        The "search_document:" instruction prefix is required by nomic-embed-text
        to route document vectors into the correct retrieval subspace.
        Must be paired with "search_query:" at query time (Querytransformer.py).

        Format: "search_document: {norm_full} clause {clause_number} {clause_title}: {text}"
        """
        return (
            f"search_document: {chunk.norm_full} clause {chunk.clause_number} "
            f"{chunk.clause_title}: {chunk.text}"
        )
```

- [ ] **Step 2: Verify the change with a quick unit check (no ingestion run yet)**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
python -c "
from rag.ingestion_pipeline.embedder.embedder import EmbedderService
from unittest.mock import MagicMock
chunk = MagicMock()
chunk.norm_full = 'ISO 9001:2015'
chunk.clause_number = '8.5.1'
chunk.clause_title = 'Planning of changes'
chunk.text = 'The organization shall plan changes.'
result = EmbedderService._build_embedding_text(chunk)
assert result.startswith('search_document: '), f'Missing prefix: {result!r}'
print('OK:', result[:80])
"
```

Expected output:
```
OK: search_document: ISO 9001:2015 clause 8.5.1 Planning of changes: The organizati
```

- [ ] **Step 3: Commit (do NOT re-ingest yet — query prefix must be added first)**

```bash
git add rag/ingestion_pipeline/embedder/embedder.py
git commit -m "feat: add search_document: instruction prefix to nomic-embed-text ingestion"
```

---

### Task 8: Add search_query: prefix to QueryTransformer

**Files:**
- Modify: `rag/retrival/query_transformer/Querytransformer.py`
- Modify: `rag/retrival/query_transformer/tests/test_transform.py`

- [ ] **Step 1: Update transform() to prepend the query prefix**

In `rag/retrival/query_transformer/Querytransformer.py`, change the `transform()` function's step 4 assembly block from:

```python
    # 4. Assemble result
    return TransformedQuery(
        embed_text=query_text,
        bm25_tokens=bm25_tokens,
        qdrant_filter=qdrant_filter,
        hyde_used=False,
        iso_vocab_hits=iso_vocab_hits,
        original_query=query_text,
        language=language,
    )
```

to:

```python
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
    )
```

- [ ] **Step 2: Update the embed_text test in test_transform.py**

In `rag/retrival/query_transformer/tests/test_transform.py`, the `TestTransformEmbedText` class currently asserts `embed_text == query`. Update it to assert the prefix is present:

```python
class TestTransformEmbedText(unittest.TestCase):
    """embed_text must be prefixed with 'search_query: '."""

    def test_embed_text_has_search_query_prefix(self):
        query = "audit interne planifié"
        tq = transform(query, norm_filter=["ISO9001"], language="FR")
        self.assertTrue(
            tq.embed_text.startswith("search_query: "),
            f"Expected 'search_query: ' prefix, got: {tq.embed_text!r}",
        )

    def test_embed_text_contains_original_query(self):
        query = "audit interne planifié"
        tq = transform(query, norm_filter=["ISO9001"], language="FR")
        self.assertIn(query, tq.embed_text)

    def test_original_query_preserved_without_prefix(self):
        query = "revue de direction"
        tq = transform(query, norm_filter=["ISO9001"], language="FR")
        self.assertEqual(tq.original_query, query)
        self.assertNotIn("search_query", tq.original_query)
```

- [ ] **Step 3: Run all unit tests to confirm passing**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/shared/vocabulary/tests/test_scanner.py \
       rag/retrival/query_transformer/tests/test_transform.py \
       rag/retrival/query_retrival/tests/test_sparse_encoder_query.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add rag/retrival/query_transformer/Querytransformer.py \
        rag/retrival/query_transformer/tests/test_transform.py
git commit -m "feat: add search_query: instruction prefix for nomic-embed-text query encoding"
```

---

### Task 9: Re-ingest and validate Stage 2

**Files:** none (operational steps)

> **Note:** Both prefix commits (Tasks 7 and 8) are now in place. Re-ingestion is safe.

- [ ] **Step 1: Drop the existing Qdrant collection**

Connect to Qdrant and drop the `norms` collection, or use a new collection name by setting `QDRANT_COLLECTION` to `norms_v2` to preserve the old collection during transition:

```bash
# Option A — drop and rebuild in place (destructive, can't roll back easily)
python -c "
from qdrant_client import QdrantClient
client = QdrantClient(url='http://localhost:6333')
client.delete_collection('norms')
print('Collection dropped.')
"

# Option B — use a new collection name (safe, old collection preserved)
export QDRANT_COLLECTION=norms_v2
```

- [ ] **Step 2: Run the ingestion pipeline**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system/rag/ingestion_pipeline"
EMBEDDING_ENABLED=true python run.py
```

Monitor for warnings. Expected output ends with a summary of embedded vs failed chunks. A failure_rate > 30% will raise RuntimeError — investigate the Ollama connection if this occurs.

- [ ] **Step 3: Verify collection point count**

```bash
python -c "
from qdrant_client import QdrantClient
import os
client = QdrantClient(url='http://localhost:6333')
collection = os.getenv('QDRANT_COLLECTION', 'norms')
info = client.get_collection(collection)
print(f'Points in {collection!r}: {info.points_count}')
"
```

Expected: non-zero point count matching the chunk count reported by the ingestion run.

- [ ] **Step 4: Run all unit tests**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
pytest rag/shared/vocabulary/tests/test_scanner.py \
       rag/retrival/query_transformer/tests/test_transform.py \
       rag/retrival/query_retrival/tests/test_sparse_encoder_query.py -v
```

Expected: all tests PASS (no regression from prefix changes).

- [ ] **Step 5: Run smoke_compare against new collection**

If using Option B (new collection name), export the env var first:
```bash
export QDRANT_COLLECTION=norms_v2
python rag/retrival/query_retrival/tests/smoketest/smoke_compare.py
```

Expected: hybrid ≥ 14/15. Dense result should hold or improve vs. Stage 1 baseline.

- [ ] **Step 6: Run smoke_hard_semantic against new collection**

```bash
python rag/retrival/query_retrival/tests/smoketest/smoke_hard_semantic.py
```

Expected: hybrid ≥ 18/20.

- [ ] **Step 7: Commit final validation note**

```bash
cd "/Users/mohamed_taher/Desktop/Documents agent system"
git commit --allow-empty -m "chore: Stage 2 re-ingestion complete — nomic prefix migration validated"
```

---

## Troubleshooting Reference

| Symptom | Likely cause | Check |
|---|---|---|
| `TypeError: object can't be used in 'await'` at runtime | Missed `await transform(...)` callsite | `grep -rn "await transform" rag/` |
| Smoke tests produce errors, not wrong results | Same as above | Same grep |
| Dense recall drops after Stage 2 | Prefix applied on one side only | Verify both `_build_embedding_text` and `transform()` were updated and re-ingestion ran |
| Ingestion `RuntimeError: failure_rate > 0.30` | Ollama connection or model missing | `curl http://localhost:11434/api/tags` to check `nomic-embed-text` is available |
| `smoke_hard_semantic` hybrid < 18/20 after Stage 1 | NC false positives may still exist for other surface forms | Check `iso_vocab_hits` in test output for unexpected vocabulary injections |
