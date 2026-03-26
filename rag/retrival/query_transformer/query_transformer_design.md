# What is the Query Transformer's job, precisely?

Before planning anything, let's be crystal clear about what this component does and doesn't do, because the boundary matters.

The Query Transformer is a pure transformation function. It takes a raw input (a section of text from an agent, or a topic description) and produces a transformed query object ready for the retriever to use. It does not touch Qdrant. It does not return results. It does not make decisions about compliance. It is a data preparation step.

Think of it like a translator at the UN. A French delegate speaks French. The ISO norm library only speaks formal ISO English. The translator doesn't answer the question — they just make sure the question arrives in the right language, with the right vocabulary, so the library can find the right books.

The component has one public method signature conceptually:

And `TransformedQuery` carries three things outward:

- The text to embed (either the original, or HyDE‑enhanced)
- The BM25 token set (original tokens + any ISO vocab injections)
- The Qdrant payload filter (the norm filter, ready to pass to Qdrant)
- A flag: `hyde_used: bool`

## The three sub-systems inside Query Transformer

The component has three internal responsibilities. They are loosely sequential — HyDE runs first (it modifies the embed text), then ISO vocab extraction runs on that text (it enriches the BM25 tokens), then the norm filter is built (it's independent of the text entirely). Let's plan each one fully.

### Sub-system 1: HyDE — The hardest and most important piece

#### What it is conceptually
HyDE stands for Hypothetical Document Embeddings. The research insight behind it is this: when you embed a question, and you embed an answer, they often land in very different places in the vector space — even if the answer perfectly addresses the question. This is because the writing style, vocabulary, and sentence structure of questions and answers are fundamentally different.

ISO norms and company documents are a perfect example of this problem. A company procedure says "we check our suppliers every year." An ISO clause says "the organization shall evaluate the performance and re-evaluate suppliers at defined intervals." These mean exactly the same thing but look completely different to an embedding model.

HyDE solves this by generating a hypothetical ISO clause that would govern the topic — not a real one, just a plausible-sounding one — and using that as the search query instead of the original text. The hypothetical clause is already written in norm language, so it lands much closer to real norm chunks.

Here's the key intuition: you're not searching for what the text says, you're searching for what the norm that governs it would say.

**Example:**
> Input text: "The company conducts quarterly internal audits. Results are communicated to management."
>
> HyDE output: "The organization shall conduct internal audits at planned intervals to determine whether the quality management system conforms to the requirements of this document. The results of the audits shall be reported to relevant management."

The HyDE output sounds like ISO 9001 §9.2. Because it does — and now your embedding search will find §9.2 instead of landing somewhere vague.

#### When to trigger HyDE — the conditional logic
HyDE costs one LLM call per section. For a 10‑section document that's 10 LLM calls before any retrieval starts. The design makes it conditional based on two signals:

1. **Token count of input text.** If the input is under 150 tokens, it's short. Short sections have sparse vocabulary — the embedding doesn't have much to work with. HyDE helps most here because it expands a thin signal into a rich one.
2. **ISO vocabulary hit count.** If the text already contains 3 or more terms from the ISO vocabulary list (things like "documented information," "management review," "interested parties," "nonconformity"), the text is already written in norm language. Embedding it directly will work fine. HyDE adds nothing and costs an LLM call.

The decision logic in plain English:

- Short text (< 150 tokens) → use HyDE (sparse vocabulary needs expansion)
- Long text with 3+ ISO terms → skip HyDE (already in norm language)
- Long text with < 3 ISO terms → use HyDE (operational language, vocabulary gap exists)

This means you need to build the ISO vocabulary check before the HyDE decision, even though HyDE conceptually comes first. In practice the order is: count ISO hits → decide → optionally call HyDE.

#### The HyDE prompt
The LLM prompt for HyDE needs to be very specific about the output format. You want it to produce something that sounds like an ISO clause, not a general paragraph. Key constraints for the prompt:

- Tell the LLM exactly which standard to target (ISO 9001, ISO 14001, etc.)
- Tell it to use prescriptive language (shall, must, is required to)
- Tell it to keep it to 2‑4 sentences
- Tell it not to explain or caveat — just produce the clause

You also need a hard timeout on this call. The design says 5 seconds. If HyDE times out, the fallback is the original text — retrieval continues, `hyde_used` is set to `False`, no failure.

#### Failure behavior
HyDE failure is silent and non‑fatal. Two retries, 0.5s sleep between. If both fail: fall back to raw text, proceed. The agent never knows HyDE was attempted. This is not like an embedding failure or a Qdrant failure — it's a quality optimization, not a required step.

#### What model for HyDE?
The design uses the same LLM client as the rest of the system (GPT‑4o primary, Mistral 7B local via Ollama fallback). But for HyDE, speed matters more than reasoning quality — you just need plausible ISO‑sounding text, not deep analysis. So use the fastest available model. In local dev that's Mistral 7B. In prod that's likely GPT‑4o‑mini or GPT‑4o with a short `max_tokens` limit (~150 tokens output is plenty for a 2‑4 sentence clause).

---

### Sub-system 2: ISO Vocabulary Extraction — The precision booster

#### What it does
The BM25 side of hybrid search catches exact keyword matches. But BM25 only works with the tokens you give it. If the query text is "the company checks its suppliers regularly," the BM25 tokens are words like `company`, `checks`, `suppliers`, `regularly`. None of those match the ISO clause tokens `evaluate`, `performance`, `re-evaluate`, `defined intervals`.

ISO Vocabulary Extraction solves this by scanning the input text (after HyDE, if HyDE ran) against a maintained glossary of ~80 ISO terms and phrases. When a match is found, those terms are injected into the BM25 token set. This augments the sparse search without changing the embedding text.

Think of it as: the dense search gets the meaning, the BM25 search gets boosted with the exact terminology the norm uses.

#### What goes in the vocabulary list
The list needs to cover three categories:

1. **ISO management system terms** — "documented information," "management review," "interested parties," "context of the organization," "risk and opportunities," "nonconformity," "corrective action," "continual improvement," "objectives," "competence," "awareness," "communication," "monitoring and measurement," "internal audit," "management system," "top management."
2. **Clause number patterns** — if the input text contains patterns like "8.5" or "clause 7.4" or "section 9.1," those are injected as explicit BM25 tokens. This matters because your `bm25_tokens` during ingestion included the digit components of clause numbers (e.g., "8.5.1" → ["8", "5", "1"]). If the query mentions "clause 8.5," injecting "8" and "5" as BM25 tokens boosts retrieval for that exact clause.
3. **Modal vocabulary** — "shall," "must," "is required to," "should," "it is recommended," "may," "can." If the input text already uses these, they're strong signals about the normative weight of the content.

#### How matching works
Simple substring matching is fine for MVP. This is not semantic matching — you're not trying to understand if "supplier" means the same as "external provider" (that's what the dense search does). You're just scanning: does the text contain any of these exact terms or patterns?

- For multi‑word terms like "documented information," scan for the full phrase (case‑insensitive).
- For clause number patterns, use a regex: `r'\b\d+\.\d+(\.\d+)*\b'`. Match, extract, inject.

The output is a set of additional tokens to merge into the BM25 query token set. The original text tokens are kept — you're adding to them, not replacing them.

#### One important nuance: don't double‑inject
Your BM25 query tokens start as the tokenized words from the (possibly HyDE‑enhanced) query text. If the query text already contains "management review," then tokenizing it will already produce `management` and `review` as tokens. Injecting them again from the vocabulary list is harmless but wasteful. Use a set — deduplication is free.

---

### Sub-system 3: Norm Filter — The simplest piece

#### What it does
The norm filter restricts the Qdrant search to only chunks from the requested standards. Agent 2 sends `norm_filter=["ISO9001"]`. Agent 3 might send `norm_filter=["ISO9001", "ISO14001"]`. The Query Transformer builds this into a Qdrant `Filter` object before handing to the retriever.

This is applied *before* the search — it reduces the search space. This is not a post‑filter (retrieve everything, then discard). Qdrant applies the filter at query time, meaning only matching points are even considered.

#### Why it matters more than it looks
Imagine you've indexed ISO 9001, ISO 14001, and ISO 45001 — roughly 750 chunks total. Agent 2 is checking a quality management document against ISO 9001 only. Without the norm filter, the retriever searches all 750 chunks and some ISO 14001 environment clauses might rank highly just because they share vocabulary. The norm filter ensures the retriever only sees the ~250–300 ISO 9001 chunks.

This improves both precision (you don't get irrelevant standard clauses) and speed (smaller search space).

#### What the filter looks like
For a single standard:Filter: norm_id == "ISO9001"
For multiple standards (Agent 3, dual compliance):Filter: norm_id in ["ISO9001", "ISO14001"]

#### What happens if the filter matches nothing?
This is the empty corpus guard — critical. If the norm filter matches zero chunks (corpus not loaded, wrong `norm_id`, etc.), the retriever would return zero results silently. The design requires an explicit failure: `success=False` with error message `"EMPTY_CORPUS: no chunks matched norm_filter=..."`. But this guard lives in the retriever, not the Query Transformer. The Query Transformer just builds the filter object correctly. The retriever checks if results came back.

**What the Query Transformer should do:** validate that the `norm_filter` list is not empty before building the filter. An empty `norm_filter=[]` is a caller error — raise early, don't pass an empty filter to Qdrant (which would return everything, not nothing, depending on how Qdrant handles empty `must` conditions).

---

## The output: TransformedQuery

The Query Transformer's output object carries everything the retriever needs. Let me describe each field:

- **`embed_text: str`** — The text to embed and use as the dense query vector. This is either the original query text (if HyDE was skipped) or the HyDE‑generated hypothetical clause.
- **`bm25_tokens: List[str]`** — The token set for sparse search. Starts as tokenized words from the `embed_text`, augmented with ISO vocabulary matches and clause number patterns. These are the tokens the BM25 query will use.
- **`qdrant_filter: Filter`** — The Qdrant `Filter` object with the `norm_id` condition. Ready to pass directly to `query_points()`.
- **`hyde_used: bool`** — Records whether HyDE was triggered. Propagated all the way to `RetrievalResult.hyde_used` so agents can see it.
- **`iso_vocab_hits: List[str]`** — The ISO terms that were matched. Useful for debugging and for the evaluation framework — if you're running retrieval quality tests you want to know which vocabulary terms were injected.
- **`original_query: str`** — The original input text before any transformation. The Reranker uses this (not the HyDE text) to score candidates. Always preserve it.

---

## Data dependencies — what you need before writing a line of code

Before implementing, you need these assets ready:

1. **The ISO vocabulary list as a maintained Python structure.** This is not a temporary hack — it's a first‑class artifact of the system. It needs to live in a config or constants file, not hardcoded inside a method. You will update it as you discover gaps during retrieval testing. Structure it as a dict where keys are the terms and values are notes or category tags:

   ```python
   ISO_VOCABULARY = {
       "documented information": "management_system",
       "management review": "leadership",
       "interested parties": "context",
       "nonconformity": "improvement",
       "corrective action": "improvement",
       # ... ~80 terms
   }

   Building this list before coding is important — you'll use it in both the HyDE decision (counting hits) and the token injection (augmenting BM25 tokens). It's also the artifact you'll refine most over time.

The HyDE LLM prompt template. Write this before coding the method. It needs to be version‑controlled (consistent with your Jinja2 prompt versioning approach from the design). Settle the wording before implementation — changing it later changes HyDE's output behavior, which affects retrieval quality.
The token count estimator. You need estimate_tokens(text: str) -> int for the HyDE decision (is the text under 150 tokens?). The simplest approach for local dev: len(text.split()) * 1.3 (average English word is ~1.3 tokens). Good enough for a threshold check. Don't install tiktoken just for this unless you already have it.
Ollama running with a chat model. HyDE needs an LLM. Local dev means Ollama with Mistral 7B (or similar). Before coding HyDE, confirm you can make a chat completion call to Ollama and get a response back.
Development sequence — the right order to build this

Here's the exact order I'd follow:

Step 1: Build the ISO vocabulary list (half a day). Research and write out ~80 terms covering the categories above. Cross‑reference against actual ISO 9001 and ISO 14001 clause headings to make sure the terms are representative. This is analysis work, not coding. Save it in query_transformer/vocabulary.py.

Step 2: Build the TransformedQuery dataclass (1 hour). Define the output object with all its fields. Simple data definition, no logic. This gives you a clear target to implement toward.

Step 3: Build ISO Vocabulary Extraction and test it (1 day). This has no external dependencies — it's pure string processing. Build the scanner that takes text and returns matched terms. Build the token augmentation that merges them into a base token set. Write unit tests with known inputs and expected outputs. Test on real sections from your mock company documents.

Step 4: Build the HyDE decision logic and test it (half a day). The decision logic is just the two signals (token count, ISO vocab hits) combined into a boolean. Test it with three cases: short text (should trigger), long text with many ISO terms (should skip), long text with few ISO terms (should trigger).

Step 5: Build the HyDE LLM call (2 days). This is where you wire in the async LLM client. Build the prompt, make the call, handle timeout and retry, return either the generated text or None. Test it end‑to‑end: send a real company procedure section, verify the output sounds like an ISO clause. This is the component most likely to need iteration on the prompt.

Step 6: Build the norm filter builder (2 hours). Trivial once you know the Qdrant filter API. Takes List[str] of norm IDs, returns a Filter object. Validate the list is non‑empty. Unit test with one and two standards.

Step 7: Wire into the transform() public method (half a day). Assemble the three sub‑systems in the right order. Return the TransformedQuery. Write an integration test that sends a full VerifyContext through transform() and gets back a valid TransformedQuery. Check: embed_text is non‑empty, bm25_tokens is non‑empty and contains some ISO vocabulary terms, qdrant_filter is a valid Filter object, hyde_used correctly reflects whether HyDE ran.

Testing strategy — how to know it's working

The Query Transformer is well‑isolated, which makes testing relatively straightforward. You don't need Qdrant or a full corpus to test it. Here's what to test:

Unit tests (no LLM, no Qdrant)

For ISO Vocabulary Extraction:

Text containing "documented information" → "documented information" in iso_vocab_hits, its tokens in bm25_tokens
Text containing "8.5" → "8" and "5" injected as BM25 tokens
Text with no ISO terms → iso_vocab_hits is empty, bm25_tokens contains only the text's own words
For HyDE decision:

50‑word text → should_use_hyde() == True
300‑word text with "documented information, management review, nonconformity, corrective action" → should_use_hyde() == False
300‑word text with no ISO terms → should_use_hyde() == True
For norm filter builder:

["ISO9001"] → filter condition on norm_id == "ISO9001"
["ISO9001", "ISO14001"] → filter condition norm_id in [...]
[] → raises ValueError
Integration tests (with LLM, no Qdrant)

Send a real company procedure text through the full transform() method:

Verify HyDE output looks like an ISO clause (contains "shall" or "the organization")
Verify hyde_used matches what the decision logic predicted
Verify that the HyDE‑generated text still gets ISO vocab extraction run on it
Verify the output is a valid TransformedQuery with all fields populated
Regression test — the HyDE fallback

Mock the LLM call to always raise a timeout. Verify transform() still returns a TransformedQuery with hyde_used=False and embed_text equal to the original query text. The system must not fail when HyDE fails.

Risks and things to watch out for

Risk 1: HyDE output quality varies. Mistral 7B might produce vague, non‑ISO‑sounding output for ambiguous inputs. You won't know how bad this is until you test on real company documents. Build a simple evaluation: embed the HyDE output, compute cosine similarity to the top‑5 retrieved chunks, compare to doing the same with the original text. If HyDE consistently produces worse similarity scores for a model, you know the prompt needs work.
Risk 2: The ISO vocabulary list is never "done." You'll discover missing terms as you run retrieval tests. Plan for this — make the list easy to update, and track which terms are actually being matched against your test queries (the iso_vocab_hits field in TransformedQuery is your window into this).
Risk 3: Token count estimation is approximate. The 150‑token threshold for HyDE activation is based on an estimate, not exact tiktoken counting. A 140‑token section might be 155 actual tokens or 130 — the threshold is fuzzy by design. Don't over‑engineer this. The cost of occasionally triggering HyDE on a slightly‑too‑long section is one unnecessary LLM call, not a correctness failure.
Risk 4: HyDE generates content for the wrong standard. If the norm filter includes both ISO 9001 and ISO 14001 but the section is clearly about quality (not environment), HyDE might generate a mix. The prompt should specify which standard to target. When multiple standards are in the filter, generate HyDE text for each separately, then use the one with higher cosine similarity to the original text — or, simpler for MVP, just generate once and mention both standards in the prompt context.
How this connects to everything else

When you hand off TransformedQuery to the Hybrid Retriever, here's exactly what it uses:

embed_text → gets embedded via EmbedderService → becomes the dense query vector for Qdrant
bm25_tokens → gets converted to a sparse query vector using BM25 weights → used for the sparse Qdrant search
qdrant_filter → passed directly to query_points() as the query_filter argument
original_query → stored, passed to the Reranker later (not used in retrieval itself)
hyde_used → stored, propagated to RetrievalResult
The Query Transformer has no return path — it doesn't know what the retriever found. It's a one‑way preparation step. Keep it that way.