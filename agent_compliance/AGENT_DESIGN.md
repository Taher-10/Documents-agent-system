# Compliance Agent — Design Log

Tracks every architectural decision from scratch to the current state.
Each section records *what* was built, *why*, and *what comes next*.

---

## Context

The goal is an AI agent that ingests QHSE company documents (PDF / DOCX)
and checks them for compliance against ISO standards (ISO 9001, ISO 14001, ISO 45001).

The agent is being built incrementally. Each version adds one layer of capability
without breaking what exists.

**Documents under test** (in `agent_compliance/qhme_docs/`):
- `PQ-PROD-01 02 Procédure de gestion des gabarits.pdf`
- `ReportJobDescriptionFiche01.pdf / .docx`
- `3.-Environmental-_-Quality-Management-System-Manual.pdf`

---

## Framework Selection

| Question | Answer |
|---|---|
| Does it need planning, file management, persistent memory? | Not yet |
| Does it need complex control flow — loops, branching, error paths? | Yes |
| Is it a single-purpose agent with a fixed tool? | No — multiple stages |

**Decision: LangGraph.**

LangChain alone would not give us typed state shared across steps or explicit
error routing. Deep Agents would over-engineer a pipeline that needs custom
graph control. LangGraph sits exactly at the right level.

The layers below (LangChain primitives, Docling parser) are used freely inside
LangGraph nodes — the frameworks are additive, not competing.

---

## V1 — Parser Agent

### Objective

Parse a company document and produce a typed, quality-assessed section list
ready for a downstream compliance checker.

### What V1 does NOT do

- No LLM calls
- No retrieval against Qdrant
- No compliance checking
- No API endpoint

---

### Graph

```
START
  │
  ▼
validate_input ──(error)──► handle_error ──► END
  │
  ▼
parse_document ──(error)──► handle_error ──► END
  │
  ▼
extract_sections ──(error)──► handle_error ──► END
  │
  ▼
assess_quality
  │
  ▼
END
```

Every error path converges on `handle_error` then `END`.
No node is ever skipped silently.

---

### State (`graph/state.py`)

```python
class AgentState(TypedDict):
    # Input
    document_path: str

    # Intermediate
    parse_result: Any | None          # ParseResult from Docling

    # Output
    sections: list[Any]               # list[ParsedSection]
    quality_tier: str | None          # "A" | "B" | "C"
    min_confidence: float | None
    low_quality_flag: bool

    # Control
    error: str | None
    status: str                        # pending → validated → parsed → sectioned → done | error
```

**Design notes:**
- `parse_result` uses `Any` to avoid importing the Docling type at schema level.
- `sections` is a plain list with no reducer — each node fully overwrites it.
  Reducers were intentionally skipped: sections are produced once by
  `extract_sections_node` and never appended to by parallel workers.
- `status` is a human-readable progress string, not a routing signal.
  Routing is done by whether `error` is set, not by `status` value.

---

### Nodes (`graph/nodes.py`)

| Node | Responsibility | Uses |
|---|---|---|
| `validate_input` | File exists + extension check | `pathlib.Path` |
| `parse_document_node` | Docling conversion, header/footer removal | `pdf_parser.parse_document` |
| `extract_sections_node` | Markdown → `ParsedSection` list | `pdf_parser.docling_to_sections` |
| `assess_quality_node` | Confidence scoring → quality tier | `pdf_parser.assess_quality` |
| `handle_error_node` | Ensure `status = "error"`, pass through | — |

Every node returns a **partial dict** — never the full state object.

---

### Conditional Routing (`graph/graph.py`)

```python
def _route_after_validate(state):  return "handle_error" if state.get("error") else "parse_document"
def _route_after_parse(state):     return "handle_error" if state.get("error") else "extract_sections"
def _route_after_sections(state):  return "handle_error" if state.get("error") else "assess_quality"
```

The pattern is consistent: every node that can fail gets its own router
that checks `state["error"]`. This keeps the error contract simple —
any node signals failure by writing `{"error": "...", "status": "error"}`.

---

### Logging Strategy (`graph/nodes.py` + `graph/run.py`)

**Problem:** Docling can take several seconds. Without feedback the CLI
or future frontend would show a blank screen.

**Solution:** LangGraph custom stream writer.

Each node calls `_emit(node, event, msg)` before and after its work:

```python
def _emit(node: str, event: str, msg: str) -> None:
    get_stream_writer()({"node": node, "event": event, "msg": msg})
```

Event types: `"start"` | `"done"` | `"error"`

**In `run.py`:**

```python
# Programmatic use (API layer will call this)
def run(document_path: str, thread_id: str | None = None) -> dict:
    return graph.invoke(...)

# Streaming use (CLI and future SSE endpoint)
def stream_run(document_path: str, thread_id: str | None = None) -> Iterator[dict]:
    for mode, chunk in graph.stream(..., stream_mode=["custom", "values", "updates"]):
        if mode == "custom":
            yield chunk                    # {"node": ..., "event": ..., "msg": ...}
        elif mode == "values":
            final_state = chunk
        elif mode == "updates" and "__interrupt__" in chunk:
            interrupt_payload = chunk["__interrupt__"]
    # yields __interrupt__ event or __final__ event
```

**Frontend-ready:** `stream_run()` already produces the right shape for SSE.
The future API endpoint will just wrap it:

```python
@app.post("/parse")
async def parse(file: UploadFile):
    async def event_stream():
        for event in stream_run(saved_path):
            yield f"data: {json.dumps(event)}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

No graph changes needed when the API is added.

---

### File Layout (V1)

```
agent_compliance/
  graph/
    __init__.py       exports: graph, build_graph, run, AgentState
    state.py          AgentState TypedDict
    nodes.py          5 node functions + _emit helper
    graph.py          StateGraph wiring + compiled graph singleton
    run.py            run() for API, stream_run() + main() for CLI
```

---

### Running V1

```bash
# Basic run
python -m agent_compliance.graph.run "agent_compliance/qhme_docs/PQ-PROD-01 02 Procédure de gestion des gabarits.pdf"

# With full section JSON
python -m agent_compliance.graph.run "..." --json

# From code (future API pattern)
from agent_compliance.graph import run
result = run("path/to/doc.pdf")
# result["sections"], result["quality_tier"], result["error"]
```

---

## V2 — Classification Enrichment (current)

### Objective

Enrich every parsed section with a `RetrievalScope` — the set of ISO domains,
clause families, and specific clauses that section is evidence for. This scope
lives on the section itself (`section.scope`) so downstream retrieval and
compliance nodes never need to zip parallel lists.

Registry metadata (document system, doc type) is fetched from `documents_system.db`
to make domain derivation data-driven. A human-in-the-loop gate is added for
Tier C documents before classification proceeds.

### What V2 adds

- `tools/db_tool.py` — SQLite registry lookup (`fetch_document_metadata`)
- `classification/` module — deterministic keyword-based scope derivation (no LLM)
- Three new graph nodes: `human_review`, `fetch_metadata`, `classify_sections`
- `InMemorySaver` checkpointer — required for HITL `interrupt()`
- `thread_id` on all entry points — required for checkpointer state tracking
- `resume_run(thread_id, decision)` — resumes a paused graph after human review

---

### Graph

```
START
  │
  ▼
validate_input ──(error)──────────────────────────────────► handle_error ──► END
  │
  ▼
parse_document ──(error)──────────────────────────────────► handle_error ──► END
  │
  ▼
extract_sections ──(error)────────────────────────────────► handle_error ──► END
  │
  ▼
assess_quality
  │
  ├──(low_quality_flag=True)──► human_review  ──(abort)──► handle_error ──► END
  │                                  │
  │                              (proceed)
  │                                  │
  └──(no low quality)────────────────┤
                                     ▼
                               fetch_metadata
                                     │
                                     ▼
                               classify_sections
                                     │
                                     ▼
                                    END
```

---

### State (`graph/state.py`)

```python
class AgentState(TypedDict):
    # Input
    document_path: str

    # Intermediate
    parse_result: Any | None

    # Output
    sections: list[Any]               # list[ParsedSection] — each carries .scope after classify_sections
    quality_tier: str | None
    min_confidence: float | None
    low_quality_flag: bool
    registry_metadata: dict[str, Any] # from documents_system.db; {} if not found
    document_scope: Any | None        # merged RetrievalScope for the whole document

    # Control
    error: str | None
    status: str   # pending → validated → parsed → sectioned → classified | done | error
```

**Key design decision — enrichment over parallel lists:**
Classification results live on each `ParsedSection` as `section.scope`, not as a
separate `classification_results` list in state. This keeps section structure and
its retrieval intent co-located. Downstream nodes read `section.scope.domains`,
`section.scope.specific_clauses`, etc. directly.

---

### New Nodes (`graph/nodes.py`)

| Node | Responsibility | Uses |
|---|---|---|
| `human_review_node` | `interrupt()` when Tier C — user confirms or aborts | `langgraph.types.interrupt` |
| `fetch_metadata_node` | Code extracted from filename → SQLite lookup → `registry_metadata` | `tools.db_tool.fetch_document_metadata` |
| `classify_sections_node` | Enrich each `section.scope` in-place; compute merged `document_scope` | `classification.classify_for_retrieval` |

**HITL pattern (`human_review_node`):**
- `interrupt()` pauses the graph and surfaces a payload to the caller
- The node re-runs from the top on resume (LangGraph guarantee) — safe because `_emit()` is idempotent and the abort branch runs after the interrupt
- Resume values: `"proceed"` → continues to `fetch_metadata`; `"abort"` → sets `error` → `handle_error`

**Enrichment pattern (`classify_sections_node`):**
```python
for section in sections:
    section.scope = classify_for_retrieval(section, meta)
doc_scope = _merge_scopes([s.scope for s in sections])
return {"sections": sections, "document_scope": doc_scope, "status": "classified"}
```

---

### Classification Module (`classification/`)

Deterministic keyword-based engine — no LLM, fully auditable.

| File | Responsibility |
|---|---|
| `models.py` | `RetrievalScope` Pydantic model — domains, clause_families, specific_clauses, evidence, confidence |
| `scope_deriver.py` | Domain + doc-type derivation from `registry_metadata` (`systeme` field: Q/E/S → ISO9001/14001/45001) |
| `section_topic_mapper.py` | Two-level HLS keyword mapping (clause families 4–10, specific clauses e.g. "9.2", "7.2") |
| `engine.py` | `classify_for_retrieval(section, registry_metadata) → RetrievalScope` — orchestrates deriver + mapper |

**Confidence formula:** `overall = 0.6 × domain_confidence + 0.4 × content_confidence`

**Evidence tracking:** every `RetrievalScope` carries the exact keyword hits that fired,
enabling auditability and debugging.

---

### ParsedSection enrichment (`pdf_parser/parsed_document.py`)

`scope: Any | None = field(default=None)` added to `ParsedSection`.

- Type is `Any` at runtime (no circular import); `TYPE_CHECKING` guard gives `RetrievalScope` type hint for tooling.
- `to_dict()` rewritten to manually build the dict (avoids `dataclasses.asdict()` breaking on Pydantic models); serializes `scope` via `scope.model_dump()`.
- `from_dict()` discards `scope` from JSON — scope is a live enrichment, not a persisted field.

---

### Tools (`tools/`)

`tools/db_tool.py` — `fetch_document_metadata(document_path: str) → dict`

- Extracts doc code from filename with regex `[A-Z]+-[A-Z]+-\d+` (e.g. `PQ-PROD-01`)
- Queries `Document` table in `documents_system.db`
- Returns `{code, systeme, types_documents, domaines_documents, indice, titre}` or `{}` if not found
- `langue` is absent from the schema — classification engine defaults to scanning EN + FR

---

### Checkpointer & Thread ID

```python
graph = build_graph()   # InMemorySaver() wired at compile time

# All entry points accept thread_id
run(path, thread_id="abc")
stream_run(path, thread_id="abc")

# Resume a paused graph
resume_run(thread_id="abc", decision="proceed")  # or "abort"
```

A UUID is auto-generated if no `thread_id` is provided.

---

### CLI Usage (V2)

```bash
# Normal run
python -m agent_compliance.graph.run "agent_compliance/qhme_docs/PQ-PROD-01 02 Procédure de gestion des gabarits.pdf"

# Output includes clause hints per section:
#   [procedure_text   ] Gestion des gabarits  (p3-5) → ['7.5', '8.5']

# Resume after HITL pause
python -m agent_compliance.graph.run "..." --thread-id <tid> --resume proceed
python -m agent_compliance.graph.run "..." --thread-id <tid> --resume abort

# From code
from agent_compliance.graph import run
result = run("path/to/doc.pdf")
for s in result["sections"]:
    print(s.title, s.scope.domains, s.scope.specific_clauses)
print(result["document_scope"].clause_families)
```

---

### File Layout (V2)

```
agent_compliance/
  graph/
    __init__.py       exports: graph, build_graph, run, stream_run, resume_run, AgentState
    state.py          AgentState TypedDict (+ registry_metadata, document_scope)
    nodes.py          8 node functions + _emit + _merge_scopes
    graph.py          StateGraph wiring + InMemorySaver checkpointer
    run.py            run(), stream_run(), resume_run(), main() CLI
  classification/
    __init__.py
    models.py         RetrievalScope Pydantic model
    engine.py         classify_for_retrieval() orchestrator
    scope_deriver.py  Domain + doc-type from registry metadata
    section_topic_mapper.py  Two-level HLS keyword mapping
  pdf_parser/
    parsed_document.py  ParsedSection.scope field added
  tools/
    __init__.py
    db_tool.py        fetch_document_metadata() — SQLite registry lookup
```

---

## V3 — Planned

| Addition | Details |
|---|---|
| FastAPI endpoint | `POST /parse` → SSE stream via `stream_run()` |
| Retrieval node | Query Qdrant with `section.scope` filters — one retrieval call per section |
| Compliance checker node | LLM call: section text + retrieved norm chunks → gap analysis |
| Human-in-the-loop (retrieval) | `interrupt()` when retrieval returns no results — ask user to confirm scope or broaden |
| Persistence | Swap `InMemorySaver` for `PostgresSaver` for session resume across restarts |
