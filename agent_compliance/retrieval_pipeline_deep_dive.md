# RAG Retrieval Pipeline — Deep-Dive Reference

> **Scope:** Every component inside `rag/retrival/` and the shared utilities it depends on.  
> **Purpose:** Understand what each component does, what it receives, what it transforms, and what it emits.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Shared Data Models](#2-shared-data-models)
3. [Component Summaries](#3-component-summaries)
   - 3.1 [Shared — ISO Vocabulary Scanner](#31-shared--iso-vocabulary-scanner)
   - 3.2 [Shared — BM25 Tokenizer](#32-shared--bm25-tokenizer)
   - 3.3 [Shared — BM25 Sparse Encoder](#33-shared--bm25-sparse-encoder)
   - 3.4 [Query Transformer](#34-query-transformer)
   - 3.5 [Hybrid Retriever](#35-hybrid-retriever)
   - 3.6 [Reranker](#36-reranker)
   - 3.7 [RetrievalService (Orchestrator)](#37-retrievalservice-orchestrator)
4. [Full End-to-End Data Flow](#4-full-end-to-end-data-flow)
5. [Shared ID Cross-Reference](#5-shared-id-cross-reference)
6. [Error Contract](#6-error-contract)
7. [Score Lifecycle](#7-score-lifecycle)

---

## 1. Architecture Overview

The pipeline is a **four-stage, two-modality** system:

```
Raw Query
   │
   ▼
┌─────────────────────────────┐   sync, no I/O
│      Query Transformer      │──────────────────────────► TransformedQuery
│   Querytransformer.py       │   4 internal transforms
└─────────────────────────────┘
   │
   ▼
┌─────────────────────────────┐   1 async I/O (Ollama embed)
│      Hybrid Retriever       │   1 sync I/O  (Qdrant RRF) ► List[RetrievedChunk] (≤ top_k)
│   query_retrival/retriever  │   dense + sparse + RRF fusion
└─────────────────────────────┘
   │
   ▼
┌─────────────────────────────┐   sync, CPU-bound
│         Reranker            │──────────────────────────► List[RetrievedChunk] (sorted)
│   re_ranker/reranker.py     │   cross-encoder batch score
└─────────────────────────────┘
   │
   ▼
┌─────────────────────────────┐   list slice
│   Truncate top_k_rerank     │──────────────────────────► Final output (≤ top_k_rerank)
│      service.py             │
└─────────────────────────────┘
```

**Execution contract per stage:**

| Stage | Execution mode | I/O |
|---|---|---|
| 1 — Query Transformer | Synchronous | None |
| 2 — Hybrid Retriever | Async | 1× Ollama embed (async) + 1× Qdrant query (sync) |
| 3 — Reranker | Synchronous | CPU only (cross-encoder batch inference) |
| 4 — Truncate | Synchronous | None |

---

## 2. Shared Data Models

### `TransformedQuery` — `rag/retrival/models.py`

The data contract **from** the Query Transformer **to** the Hybrid Retriever.

| Field | Type | Set by | Consumed by |
|---|---|---|---|
| `embed_text` | `str` | `transform()` — `"search_query: {raw_query}"` | `embedder.embed_text()` → dense vector |
| `bm25_tokens` | `List[str]` | `augment_bm25_tokens()` | `BM25SparseEncoder.encode_query()` → sparse vector |
| `qdrant_filter` | `Filter` | `build_norm_filter()` | Qdrant `Prefetch.filter=` |
| `hyde_used` | `bool` | Always `False` (HyDE removed) | Diagnostics only |
| `iso_vocab_hits` | `List[str]` | `scan_iso_vocabulary()` | `augment_bm25_tokens()` + diagnostics |
| `original_query` | `str` | Raw `query_text` passthrough | `Reranker.rerank()` + `EmptyCorpusError` message |
| `language` | `str` | Caller-supplied `"EN"` / `"FR"` | Vocab scan dispatch + Qdrant filter |
| `norm_filter` | `List[str]` | Caller-supplied norm IDs | `EmptyCorpusError` message |

> [!IMPORTANT]
> `embed_text` ≠ `original_query`. `embed_text` carries the `"search_query: "` instruction prefix required by `nomic-embed-text`. The Reranker must **never** receive `embed_text` — it uses `original_query` only.

---

### `RetrievedChunk` — `rag/retrival/models.py`

The data contract **from** the Hybrid Retriever **to** the Reranker and **the final pipeline output**.

**Provenance group** (mapped 1-to-1 from Qdrant payload):

| Field | Type | Description |
|---|---|---|
| `chunk_id` | `str` | UUID string — Qdrant point ID |
| `norm_id` | `str` | e.g. `"ISO9001"` |
| `norm_full` | `str` | e.g. `"ISO 9001:2015"` |
| `norm_version` | `str` | e.g. `"2015"` |
| `clause_number` | `str` | e.g. `"8.5.1"` |
| `clause_title` | `str` | Human-readable clause name |
| `parent_clause` | `str` | Empty string for top-level clauses |
| `page_number` | `int` | Original PDF page |
| `chunk_index` | `int` | 1-based within clause |
| `total_chunks` | `int` | `1` when no split occurred |

**Content group:**

| Field | Type | Description |
|---|---|---|
| `text` | `str` | Clause text — fed to cross-encoder at rerank time |
| `token_count` | `int` | Token count at ingestion |
| `content_type` | `str` | `"normative"` stored as plain string (not enum) |

**Modal vocabulary group** (pre-computed at ingestion, stored in payload):

| Field | Type | Description |
|---|---|---|
| `shall_count` | `int` | Occurrences of "shall" / "doit" |
| `should_count` | `int` | Occurrences of "should" / "il convient" |
| `has_requirements` | `bool` | `shall_count > 0` |
| `has_permissions` | `bool` | Presence of "may" / "peut" |
| `has_recommendations` | `bool` | Presence of "should" / "il convient" |
| `has_capabilities` | `bool` | Presence of "can" / "il est possible de" |

**Score group — evolves through pipeline stages:**

| Field | Default | Populated by | Value |
|---|---|---|---|
| `dense_score` | `-1.0` | Never (permanent sentinel) | RRF fusion hides individual vector scores |
| `sparse_score` | `-1.0` | Never (permanent sentinel) | Same reason |
| `rrf_score` | `0.0` | `_scored_point_to_chunk()` | `ScoredPoint.score` from Qdrant RRF |
| `rerank_score` | `0.0` | `Reranker.rerank()` | `CrossEncoder.predict()` raw logit |

---

## 3. Component Summaries

### 3.1 Shared — ISO Vocabulary Scanner

**File:** `rag/shared/vocabulary/scanner.py`  
**Used by:** Query Transformer (query-time) **and** Ingestion Enricher (index-time) — single source of truth

#### Responsibility
Scan any text for ISO management system vocabulary. Returns a sorted, deduplicated list of **canonical term keys**, **modal/normative-weight terms**, and **clause number patterns** found in that text.

#### Key internals

| Element | Detail |
|---|---|
| `ISO_VOCABULARY_EN` / `ISO_VOCABULARY_FR` | Large dicts in `vocabulary.py`. Per entry: `{ "forms": List[str], "standards": List[str] }` |
| `_FORM_PATTERNS` | Module-level lazy cache `Dict[str, re.Pattern]` — compiled once per surface form |
| `_form_pattern(form)` | Returns `re.compile(r'\b' + re.escape(form.lower()) + r'\b')` — **word-boundary guarded** to prevent substring false positives (e.g. `"NC"` inside `"influencer"`) |
| `CLAUSE_PATTERN` | `re.compile(r'\b\d+\.\d+(?:\.\d+)*\b')` — matches `"7.5.1"`, `"8.5"` etc. |
| `MODAL_TERMS_EN/FR` | Normative-weight word lists as per ISO Directives Part 2 |

#### Data flow

```
Input:
    text        : str
    language    : "EN" | "FR"
    norm_filter : List[str] | None
         │
         ├─► text_lower = text.lower()
         │
         ├─► [ISO Vocabulary scan]
         │       vocab = ISO_VOCABULARY_EN if language=="EN" else ISO_VOCABULARY_FR
         │       for canonical_key, entry in vocab.items():
         │           if norm_filter given AND entry["standards"] ∩ norm_filter == ∅:
         │               skip  ← standard-scope filter
         │           for form in entry["forms"]:
         │               _form_pattern(form).search(text_lower) ?
         │                   YES → hits.add(canonical_key); break  ← first match wins
         │
         ├─► [Modal terms scan]
         │       modal_list = MODAL_TERMS_FR if language=="FR" else MODAL_TERMS_EN
         │       for term in modal_list:
         │           _form_pattern(term).search(text_lower) ?
         │               YES → hits.add(term)
         │
         ├─► [Clause number scan]
         │       for clause_num in CLAUSE_PATTERN.findall(text):
         │           hits.add(clause_num)
         │
         └─► Output: sorted(hits) → List[str]
```

**Example output for `"un NC a été détecté lors de l'audit interne clause 9.2"` (FR, ISO9001):**
```
["9.2", "audit interne", "doit", "non-conformité"]
```

> [!NOTE]
> Being a shared single source of truth is the **central symmetry guarantee**: every vocabulary hit at index-time (ingestion enricher) maps to an identical hit at query-time (query transformer), ensuring BM25 sparse signals always align.

---

### 3.2 Shared — BM25 Tokenizer

**File:** `rag/shared/bm25/tokenizer.py`  
**Used by:** Query Transformer (query-time) **and** Ingestion Enricher (index-time) — identical function, identical stop-word list

#### Responsibility
Produce a **deduplicated, stop-word-filtered, order-preserving** token list from any text. The symmetry between index-time and query-time tokenisation is the core design invariant.

#### Key internals

| Element | Detail |
|---|---|
| `_WORD_RE` | `r'\b[a-zA-ZÀ-ÿ]{3,}\b'` — 3+ char alphabetic words, accented French chars included |
| `_MARKDOWN_NOISE_RE` | Strips `## headings`, `<!-- comments -->`, `**bold**`, `` `code` ``, `[links]` before tokenisation |
| `STOP_WORDS` | `frozenset` of ~90 English+French stop words (mirrors `enricher.py` exactly) |

#### Data flow

```
Input:
    text        : str           — raw text, markdown OK
    clause_ref  : str | None    — e.g. "7.5.2"
    bonus_terms : List[str] | None
         │
    [Step 1] Strip markdown noise
         │       _MARKDOWN_NOISE_RE.sub(' ', text) → clean
         │
    [Step 2] Extract & filter word tokens
         │       _WORD_RE.findall(clean)  →  lowercase each
         │       drop if word ∈ STOP_WORDS
         │       → word_tokens: List[str]
         │
    [Step 3] Clause digit tokens
         │       if clause_ref:
         │           re.sub(r'[^0-9]', ' ', clause_ref).split()
         │           "7.5.2" → ["7", "5", "2"]
         │       → clause_tokens: List[str]
         │
    [Step 4] Bonus term tokens
         │       if bonus_terms:
         │           for term in bonus_terms: term.lower().split()
         │           "corrective action" → ["corrective", "action"]
         │       → bonus_tokens: List[str]
         │
    [Step 5] Order-preserving deduplication
         │       for t in word_tokens + clause_tokens + bonus_tokens:
         │           if t not in seen: result.append(t)
         │
         └─► Output: List[str]  — deduplicated, all lowercase
```

> [!NOTE]
> **Step 4 bigram splitting** is a critical precision fix: ISO vocabulary hits like `"corrective action"` are stored in Qdrant as individual tokens `["corrective", "action"]`. Query tokens must be at the same granularity or sparse matching silently fails.

---

### 3.3 Shared — BM25 Sparse Encoder

**File:** `rag/shared/bm25/bm25_encoder.py`  
**Class:** `BM25SparseEncoder`

#### Dual API — two modes, one class

| Method | Invoked at | Corpus stats needed? | Weight formula |
|---|---|---|---|
| `BM25SparseEncoder(chunks).encode(chunk)` | Ingestion (index-time) | Yes — Pass 1 computes DF + avgdl | Full Robertson-Walker BM25 |
| `BM25SparseEncoder.encode_query(tokens)` | Retrieval (query-time) | No — static method | Uniform `1.0` per token |

**Why uniform weight at query-time?** IDF scaling is already embedded in the document-side sparse vectors stored in Qdrant. The query vector only signals *which* tokens are present; the IDF weighting emerges from the sparse dot-product.

#### Token → index mapping (identical on both sides)

```
index = int( MD5(token.encode("utf-8")).hexdigest(), 16 ) % SPARSE_DIM
```
- `SPARSE_DIM = 131_072`
- MD5 is stable across runs regardless of `PYTHONHASHSEED`
- Collisions (~2% probability at 80 tokens) → weights **summed** at the colliding index

#### `encode_query()` data flow (retrieval path)

```
Input: tokens: List[str]   (= TransformedQuery.bm25_tokens)
         │
         ├─ if empty → return ([], [])
         │
         ├─ for each token:
         │       idx  = MD5(token) % 131_072
         │       scores[idx] += 1.0    ← uniform; collision → sum
         │
         ├─ sort pairs by ascending index
         │
         └─► Output: (indices: List[int], values: List[float])
                     → SparseVector(indices=..., values=...)
```

#### `encode()` data flow (ingestion, for context)

```
Input: chunk: NormChunk   (corpus stats already computed in __init__)
         │
         ├─ tf = Counter(chunk.bm25_tokens)
         ├─ for each (token, tf_val):
         │       df    = self._df.get(token, 1)
         │       IDF   = log( (N - df + 0.5) / (df + 0.5) + 1 )
         │       score = IDF × tf_val*(k1+1) / [tf_val + k1*(1 - b + b×|D|/avgdl)]
         │       if score ≤ 0: skip
         │       idx = MD5(token) % 131_072;  scores[idx] += score
         │
         ├─ sort by ascending index
         └─► Output: (indices: List[int], values: List[float])
```

---

### 3.4 Query Transformer

**File:** `rag/retrival/query_transformer/Querytransformer.py`  
**Entry point:** `transform(query_text, norm_filter, language) → TransformedQuery`

#### Responsibility
Convert a raw user query into a `TransformedQuery`. **Entirely synchronous — zero I/O.** Enriches the query with ISO vocabulary signals and prepares two parallel representations: a prefixed dense embedding text and an augmented BM25 token list.

#### Public sub-functions

| Function | Input | Output | Notes |
|---|---|---|---|
| `build_norm_filter(norm_filter, language)` | `List[str]`, `str` | Qdrant `Filter` | Single → `MatchValue`; multiple → `MatchAny`; empty → `ValueError` |
| `scan_iso_vocabulary(text, language, norm_filter)` | `str`, `str`, `List[str]` | `List[str]` | Delegated to `shared/vocabulary/scanner.py` |
| `augment_bm25_tokens(base_tokens, iso_hits)` | `List[str]`, `List[str]` | `List[str]` | Clause refs digit-expanded; phrases unigram-split; merged via set |
| `transform(...)` | `str`, `List[str]`, `str` | `TransformedQuery` | Orchestrates all 3 above + tokenizer |

#### `transform()` data flow

```
Input:
    query_text  : str        — e.g. "un NC a été détecté lors de l'audit"
    norm_filter : List[str]  — e.g. ["ISO9001"]
    language    : str        — e.g. "FR"
         │
    [Step 1] build_norm_filter(norm_filter, language)
         │       len==1 → match = MatchValue("ISO9001")
         │       len>1  → match = MatchAny(any=[...])
         │       Filter(must=[
         │           FieldCondition("norm_id",  match),
         │           FieldCondition("language", MatchValue("FR"))
         │       ])
         │       → qdrant_filter: Filter
         │
    [Step 2] scan_iso_vocabulary(query_text, "FR", ["ISO9001"])
         │       word-boundary regex scan of ISO_VOCABULARY_FR
         │       "NC" → match word-boundary → hits.add("non-conformité")
         │       "audit" → part of "audit interne" surface form → hit
         │       CLAUSE_PATTERN: no clause reference in this query
         │       → iso_vocab_hits: ["audit interne", "non-conformité"]   (sorted)
         │
    [Step 3a] CLAUSE_PATTERN.search(query_text)
         │       → clause_hit or None  (None in this example)
         │
    [Step 3b] tokenize_for_bm25(text=query_text, clause_ref=None)
         │       strip noise → extract words → filter stop words
         │       → base_tokens: ["détecté", "audit", "lors"]
         │
    [Step 3c] augment_bm25_tokens(base_tokens, iso_vocab_hits)
         │       token_set = {"détecté", "audit", "lors"}
         │       "non-conformité" → not clause → split → "non-conformité"
         │       "audit interne"  → not clause → split → "audit", "interne"
         │       result set: {"détecté", "audit", "lors", "non-conformité", "interne"}
         │       → bm25_tokens: List[str]
         │
    [Step 4] Assemble TransformedQuery
         │       embed_text     = "search_query: un NC a été détecté lors de l'audit"
         │       bm25_tokens    = (Step 3c)
         │       qdrant_filter  = (Step 1)
         │       hyde_used      = False    ← always
         │       iso_vocab_hits = (Step 2)
         │       original_query = "un NC a été détecté lors de l'audit"  ← no prefix
         │       language       = "FR"
         │       norm_filter    = ["ISO9001"]
         │
         └─► Output: TransformedQuery
```

#### `augment_bm25_tokens()` transformation detail

```
base_tokens   : ["détecté", "audit", "lors"]
iso_vocab_hits: ["8.5.1", "non-conformité", "audit interne"]

Iteration:
  "8.5.1"          → CLAUSE_PATTERN.fullmatch ✓ → expand digits → add "8","5","1"
  "non-conformité" → phrase → split()           → add "non-conformité"
  "audit interne"  → phrase → split()           → add "audit" (dup), "interne"

token_set after merge:
  {"détecté", "audit", "lors", "8", "5", "1", "non-conformité", "interne"}

bm25_tokens = list(token_set)
```

---

### 3.5 Hybrid Retriever

**File:** `rag/retrival/query_retrival/retriever.py`  
**Class:** `HybridRetriever`  
**Entry point:** `await retriever.retrieve(query, top_k, collection) → List[RetrievedChunk]`

#### Responsibility
Execute a **two-modality search** (dense cosine + sparse BM25) in a **single Qdrant round-trip** using the Prefetch + `FusionQuery(RRF)` pattern. Converts raw `ScoredPoint` objects to typed `RetrievedChunk` instances.

#### Qdrant query pattern

```python
qdrant.query_points(
    collection_name = collection,
    prefetch = [
        Prefetch(
            query  = dense_vector,                     # 768-dim float list
            using  = "dense",                          # named vector slot
            filter = query.qdrant_filter,
            limit  = prefetch_limit,                   # max(20, top_k*2)
        ),
        Prefetch(
            query  = SparseVector(indices, values),    # BM25 query vector
            using  = "sparse",                         # named vector slot
            filter = query.qdrant_filter,
            limit  = prefetch_limit,
        ),
    ],
    query  = FusionQuery(fusion=Fusion.RRF),           # outer fusion
    limit  = top_k,
    with_payload = True,
)
```

- Filter is applied **on each Prefetch**, not the outer call (Qdrant API requirement)
- If `bm25_tokens` is empty → sparse Prefetch is **omitted** (graceful dense-only fallback)

#### Data flow

```
Input:
    query      : TransformedQuery
    top_k      : int = 15
    collection : str = "norms"
         │
    [Step 1] await embedder.embed_text(query.embed_text)    ← only async I/O
         │       "search_query: {raw query}" → Ollama nomic-embed-text
         │       → dense_vector: List[float]   (768 dims)
         │
    [Step 2] BM25SparseEncoder.encode_query(query.bm25_tokens)   ← sync, no I/O
         │       token → MD5 index, weight 1.0
         │       → (sparse_indices: List[int], sparse_values: List[float])
         │
    [Step 3] Build Prefetch list
         │       prefetch_limit = max(20, top_k * 2)   ← ensures RRF overlap
         │       Always: Prefetch(dense_vector, "dense", filter, limit)
         │       If sparse non-empty: Prefetch(SparseVector, "sparse", filter, limit)
         │
    [Step 4] qdrant.query_points(Prefetch list + FusionQuery(RRF))   ← single sync call
         │       Qdrant internally:
         │           Run dense Prefetch  → top-N by cosine similarity
         │           Run sparse Prefetch → top-N by sparse dot product
         │           RRF merge:  score(d) = Σ_i  1 / (60 + rank_i(d))
         │           Return top_k results with full payload
         │       → response.points: List[ScoredPoint]
         │
    [Step 5] Empty guard
         │       if not results: raise EmptyCorpusError(...)   ← never silenced
         │
    [Step 6] Map: _scored_point_to_chunk(point) for each ScoredPoint
         │       chunk_id     = str(point.id)
         │       payload fields mapped by key (KeyError if missing = ingestion bug)
         │       dense_score  = -1.0       ← permanent sentinel
         │       sparse_score = -1.0       ← permanent sentinel
         │       rrf_score    = point.score ← RRF fused score from Qdrant
         │       rerank_score = 0.0        ← placeholder
         │
         └─► Output: List[RetrievedChunk]  (len ≤ top_k, ordered by rrf_score desc)
```

> [!NOTE]
> `DenseRetriever` in `retriever_dense.py` is the development-stage predecessor (single-modality, no RRF).
> It is kept as a backward-compat alias but is **not used by `RetrievalService`**.

---

### 3.6 Reranker

**File:** `rag/retrival/re_ranker/reranker.py`  
**Class:** `Reranker`  
**Entry point:** `reranker.rerank(query_text, candidates) → List[RetrievedChunk]`

#### Responsibility
Re-score every `(query, chunk)` pair with a **cross-encoder** that reads both texts jointly, then sort by that score. Corrects ranking errors from the initial bi-encoder RRF pass.

#### Model: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`

| Property | Value |
|---|---|
| Architecture | 12-layer MiniLM |
| Training data | mMARCO (26 languages) |
| Languages | Strong FR + EN; handles cross-lingual pairs |
| Output | Raw logits (not probabilities) — higher = more relevant |
| Loading | Eager at `__init__` — fails fast if model is missing |

#### Data flow

```
Input:
    query_text : str                — TransformedQuery.original_query  (NO prefix!)
    candidates : List[RetrievedChunk] — from HybridRetriever (ordered by rrf_score)
         │
    [Step 1] Guard
         │       if not candidates: return []
         │
    [Step 2] Build pairs
         │       pairs = [[query_text, chunk.text] for chunk in candidates]
         │       → List[List[str]]   (N × 2)
         │
    [Step 3] Batch score  (single model inference call)
         │       scores = CrossEncoder.predict(pairs)
         │       → numpy array of N raw logits
         │
    [Step 4] Assign scores
         │       for chunk, score in zip(candidates, scores):
         │           chunk.rerank_score = float(score)
         │
    [Step 5] Sort in-place
         │       candidates.sort(key=lambda c: c.rerank_score, reverse=True)
         │
         └─► Output: List[RetrievedChunk]  (all N items, rerank_score populated, sorted desc)
                     Truncation is NOT done here — belongs to service.py
```

> [!IMPORTANT]
> The cross-encoder **must** receive `original_query` — no instruction prefix.  
> The attention mechanism reads natural language; `"search_query: "` is meaningless noise to it and degrades scoring quality.

---

### 3.7 RetrievalService (Orchestrator)

**File:** `rag/retrival/service.py`  
**Class:** `RetrievalService`  
**Entry point:** `await service.retrieve(query, norm_filter, language, ...) → List[RetrievedChunk]`

#### Responsibility
Wire all four stages into a single public awaitable. Manages `top_k` / `top_k_rerank` cascade and resource lifecycle.

#### Constructor

| Parameter | Default | Role |
|---|---|---|
| `embedder` | required | Async client with `embed_text(str) → List[float]` |
| `qdrant` | required | `QdrantClient` instance |
| `reranker` | required | `Reranker` instance |
| `collection` | `"norms"` | Qdrant collection name |
| `top_k` | `15` | Candidate pool size fed to HybridRetriever |
| `top_k_rerank` | `5` | Final output size after reranking |

#### Data flow

```
Input:
    query         : str
    norm_filter   : List[str]
    language      : str
    top_k         : int | None
    top_k_rerank  : int | None
         │
         effective_top_k       = top_k        or self._top_k        (15)
         effective_top_k_rerank= top_k_rerank or self._top_k_rerank (5)
         │
    [Step 1] transform(query, norm_filter, language)            ← sync
         │       → tq: TransformedQuery
         │
    [Step 2] await self._retriever.retrieve(tq, effective_top_k, self._collection)
         │       → chunks: List[RetrievedChunk]  (len ≤ 15)
         │
    [Step 3] self._reranker.rerank(tq.original_query, chunks)  ← sync
         │       → ranked: List[RetrievedChunk]  (all 15, sorted by rerank_score)
         │
    [Step 4] ranked[:effective_top_k_rerank]                   ← slice
         │
         └─► Output: List[RetrievedChunk]  (len ≤ 5, sorted by rerank_score desc)
```

---

## 4. Full End-to-End Data Flow

### Worked example

**Query:** `"les exigences de l'audit interne ISO 9001 clause 9.2"`  
**norm_filter:** `["ISO9001"]` | **language:** `"FR"` | **top_k:** `15` | **top_k_rerank:** `5`

```
═══════════════════════════════════════════════════════════════════════
 ENTRY POINT: RetrievalService.retrieve()
═══════════════════════════════════════════════════════════════════════

  query         = "les exigences de l'audit interne ISO 9001 clause 9.2"
  norm_filter   = ["ISO9001"]
  language      = "FR"
  effective_top_k        = 15
  effective_top_k_rerank = 5

───────────────────────────────────────────────────────────────────────
 STAGE 1 — QUERY TRANSFORMER  (sync)
───────────────────────────────────────────────────────────────────────

  ▸ build_norm_filter(["ISO9001"], "FR")
        1 norm → MatchValue("ISO9001")
        → Filter(must=[
              FieldCondition("norm_id",  MatchValue("ISO9001")),
              FieldCondition("language", MatchValue("FR"))
          ])

  ▸ scan_iso_vocabulary(query_text, "FR", ["ISO9001"])
        text_lower = "les exigences de l'audit interne iso 9001 clause 9.2"
        ISO_VOCABULARY_FR:
            "audit interne" surface form → word-boundary match ✓
            "exigences"     surface form → word-boundary match ✓
        CLAUSE_PATTERN.findall: "9.2" found
        MODAL_TERMS_FR: none present in this query
        → iso_vocab_hits: ["9.2", "audit interne", "exigences"]

  ▸ CLAUSE_PATTERN.search → match "9.2"

  ▸ tokenize_for_bm25(query_text, clause_ref="9.2")
        Step 1: no markdown noise
        Step 2: words → lowercase → stop-word filter
                ["les","exigences","audit","interne","clause"] → ["exigences","audit","interne","clause"]
        Step 3: "9.2" → ["9","2"]
        → base_tokens: ["exigences","audit","interne","clause","9","2"]

  ▸ augment_bm25_tokens(base_tokens, ["9.2","audit interne","exigences"])
        "9.2"          → clause expand → "9","2"    (already in set)
        "audit interne"→ unigrams     → "audit","interne"  (already in set)
        "exigences"    → unigrams     → "exigences"  (already in set)
        → bm25_tokens: ["exigences","audit","interne","clause","9","2"]  (unchanged here)

  ▸ Assemble TransformedQuery
        embed_text     = "search_query: les exigences de l'audit interne ISO 9001 clause 9.2"
        bm25_tokens    = ["exigences","audit","interne","clause","9","2"]
        qdrant_filter  = Filter(norm_id=ISO9001, language=FR)
        hyde_used      = False
        iso_vocab_hits = ["9.2","audit interne","exigences"]
        original_query = "les exigences de l'audit interne ISO 9001 clause 9.2"
        language       = "FR"
        norm_filter    = ["ISO9001"]

───────────────────────────────────────────────────────────────────────
 STAGE 2 — HYBRID RETRIEVER  (async)
───────────────────────────────────────────────────────────────────────

  ▸ await embedder.embed_text("search_query: les exigences de l'audit...")
        → HTTP call to Ollama nomic-embed-text
        → dense_vector: [0.023, -0.14, 0.87, ...]   (768 floats)

  ▸ BM25SparseEncoder.encode_query(["exigences","audit","interne","clause","9","2"])
        MD5("exigences") % 131072 = 44012  → weight 1.0
        MD5("audit")     % 131072 = 3891   → weight 1.0
        MD5("interne")   % 131072 = 71837  → weight 1.0
        MD5("clause")    % 131072 = 18234  → weight 1.0
        MD5("9")         % 131072 = 1042   → weight 1.0
        MD5("2")         % 131072 = 99210  → weight 1.0
        sort ascending: [1042, 3891, 18234, 44012, 71837, 99210]
        → SparseVector(indices=[1042,3891,...], values=[1.0,1.0,...])

  ▸ Build Prefetches   (prefetch_limit = max(20, 30) = 30)
        Prefetch #1: dense_vector, using="dense",  filter=qdrant_filter, limit=30
        Prefetch #2: SparseVector, using="sparse", filter=qdrant_filter, limit=30

  ▸ qdrant.query_points(prefetch=[P1,P2], query=FusionQuery(RRF), limit=15)
        Qdrant internally:
            P1 → top-30 by cosine(dense_vector, chunk.dense_vector)
            P2 → top-30 by sparse_dot(query_sparse, chunk.sparse_vector)
            RRF merge: score(d) = 1/(60+rank_dense) + 1/(60+rank_sparse)
        → 15 ScoredPoint results, ordered by RRF score

  ▸ Empty guard: 15 results → OK

  ▸ _scored_point_to_chunk × 15
        For each ScoredPoint:
            chunk_id     = "3f7a1b2c-..."
            norm_id      = "ISO9001"
            clause_number= "9.2"
            clause_title = "Internal audit"
            text         = "L'organisme doit procéder à des audits internes..."
            language     = "FR"
            rrf_score    = point.score  (e.g. 0.0321)  ✅
            dense_score  = -1.0         (sentinel)
            sparse_score = -1.0         (sentinel)
            rerank_score = 0.0          (placeholder)

  → chunks: 15 × RetrievedChunk   (rrf_score populated)

───────────────────────────────────────────────────────────────────────
 STAGE 3 — RERANKER  (sync)
───────────────────────────────────────────────────────────────────────

  query_text = "les exigences de l'audit interne ISO 9001 clause 9.2"  ← original_query

  pairs = [
      ["les exigences...", "L'organisme doit procéder à des audits internes..."],
      ["les exigences...", "documented information as evidence of the audit..."],
      ...  (15 pairs)
  ]

  scores = CrossEncoder.predict(pairs)   ← single batch call
      → [4.21, 1.83, 3.97, 2.14, 0.92, ...]   (raw logits)

  Assign rerank_score + sort:
      chunk "9.2 FR" (clause 9.2 FR text) → rerank_score = 4.21  → rank 1 ✅
      chunk "9.1 FR" (clause 9.1 FR text) → rerank_score = 3.97  → rank 2
      chunk "9.2 EN" (clause 9.2 EN text) → rerank_score = 2.14  → rank 3
      ...

  → ranked: 15 × RetrievedChunk   (rerank_score populated, sorted)

───────────────────────────────────────────────────────────────────────
 STAGE 4 — TRUNCATE  (sync)
───────────────────────────────────────────────────────────────────────

  ranked[:5]   → top 5 by rerank_score

═══════════════════════════════════════════════════════════════════════
 FINAL OUTPUT — per chunk shape
═══════════════════════════════════════════════════════════════════════

  chunk_id      : "3f7a1b2c-4a91-..."
  norm_id       : "ISO9001"
  clause_number : "9.2"
  clause_title  : "Internal audit"
  text          : "L'organisme doit procéder à des audits internes à intervalles planifiés..."
  language      : "FR"
  rrf_score     : 0.0321   ← from HybridRetriever (preserved for diagnostics)
  rerank_score  : 4.21     ← from Reranker  ← THE FINAL RANKING KEY
  dense_score   : -1.0     ← permanent sentinel (RRF hides per-vector scores)
  sparse_score  : -1.0     ← permanent sentinel
```

---

## 5. Shared ID Cross-Reference

Identifiers and constants that must remain **consistent across all pipeline components**:

| ID / Key | Format | Produced by | Consumed by |
|---|---|---|---|
| `norm_id` | `"ISO9001"` (no spaces, no colon) | Ingestion pipeline | `build_norm_filter()` → `FieldCondition("norm_id", ...)` |
| `language` | `"EN"` or `"FR"` (uppercase 2-char) | Caller / Ingestion | `scan_iso_vocabulary()` dispatch + Qdrant `FieldCondition("language", ...)` |
| `clause_number` | `"8.5.1"` (dot-separated digits) | Ingestion chunker | `CLAUSE_PATTERN.search()` + `tokenize_for_bm25(clause_ref=...)` |
| `chunk_id` | UUID string | Qdrant auto-generated | `RetrievedChunk.chunk_id` → downstream citation |
| Sparse token index | `MD5(token) % 131_072` | `BM25SparseEncoder` (both ingestion + retrieval) | Must use **identical hash function** on both sides |
| Dense named vector | `"dense"` (Qdrant slot name) | Qdrant collection config | `Prefetch(using="dense")` |
| Sparse named vector | `"sparse"` (Qdrant slot name) | Qdrant collection config | `Prefetch(using="sparse")` |
| Embed prefix — document | `"search_document: "` | `embedder._build_embedding_text()` at ingestion | Nomic-embed-text document subspace routing |
| Embed prefix — query | `"search_query: "` | `transform()` → `embed_text` field | Nomic-embed-text query subspace routing |

> [!WARNING]
> **Prefix symmetry is a hard requirement.** Both `"search_document: "` (ingestion) and `"search_query: "` (retrieval) must be active simultaneously. Applying only one side misaligns the vector space and silently collapses dense recall — the degradation is not immediately obvious from error messages.

---

## 6. Error Contract

| Exception | Raised in | Trigger | Meaning |
|---|---|---|---|
| `ValueError("norm_filter must not be empty")` | `build_norm_filter()` | `norm_filter == []` | Caller error — empty filter would match all documents in Qdrant |
| `KeyError` | `_scored_point_to_chunk()` | A payload key is missing | Ingestion bug — a required `NormChunk` field was not stored in Qdrant |
| `EmptyCorpusError` | `HybridRetriever.retrieve()` | Qdrant returns 0 results | (A) corpus never ingested; (B) `norm_id` value mismatch (e.g. `"ISO 9001"` vs `"ISO9001"`) |

> [!CAUTION]
> `EmptyCorpusError` is **never swallowed as an empty list**. An empty list would silently produce a compliance report with zero citations — the most dangerous silent failure mode in the RAG system.

---

## 7. Score Lifecycle

Each `RetrievedChunk` carries four score fields. Their state at each pipeline boundary:

```
┌──────────────────────────┬──────────────┬──────────────┬─────────────┬──────────────┐
│   Pipeline boundary      │ dense_score  │ sparse_score │  rrf_score  │ rerank_score │
├──────────────────────────┼──────────────┼──────────────┼─────────────┼──────────────┤
│ _scored_point_to_chunk() │   -1.0       │   -1.0       │  0.0321 ✅  │    0.0       │
│ (end of Step 6, Stage 2) │  [sentinel]  │  [sentinel]  │ from Qdrant │ [placeholder]│
├──────────────────────────┼──────────────┼──────────────┼─────────────┼──────────────┤
│ After Reranker.rerank()  │   -1.0       │   -1.0       │  0.0321     │   4.21 ✅    │
│ (end of Stage 3)         │  [unchanged] │  [unchanged] │ [preserved] │ cross-encoder│
├──────────────────────────┼──────────────┼──────────────┼─────────────┼──────────────┤
│ After truncation         │   -1.0       │   -1.0       │  0.0321     │   4.21       │
│ (final output)           │  [permanent] │  [permanent] │ [diagnostic]│ [ranking key]│
└──────────────────────────┴──────────────┴──────────────┴─────────────┴──────────────┘
```

**Key insight:** `rrf_score` is intentionally preserved after reranking. Comparing the `rrf_score` rank vs the `rerank_score` rank reveals where the cross-encoder **disagreed** with the hybrid retriever — the primary diagnostic tool for quality regressions.

| Use case | Score to use |
|---|---|
| Final answer ranking | `rerank_score` |
| Diagnostic: retriever quality | `rrf_score` |
| Dense-only contribution | Not available (`-1.0` sentinel) |
| Sparse-only contribution | Not available (`-1.0` sentinel) |
