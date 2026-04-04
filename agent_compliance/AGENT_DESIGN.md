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

## V1 — Parser Agent (current)

### Objective

Parse a company document and produce a typed, quality-assessed section list
ready for a downstream compliance checker.

### What V1 does NOT do

- No LLM calls
- No retrieval against Qdrant
- No compliance checking
- No API endpoint (planned for V2)

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
def run(document_path: str) -> dict:
    return graph.invoke(...)

# Streaming use (CLI and future SSE endpoint)
def stream_run(document_path: str) -> Iterator[dict]:
    for mode, chunk in graph.stream(..., stream_mode=["custom", "values"]):
        if mode == "custom":
            yield chunk          # {"node": ..., "event": ..., "msg": ...}
        elif mode == "values":
            final_state = chunk  # captured for the __final__ yield
    yield {"node": "__final__", "event": "final", "state": final_state}
```

`stream_mode=["custom", "values"]` runs the graph **once** and gives both
the log events and the final state — no double invocation.

**CLI output:**
```
  ... [validate_input] Checking file: PQ-PROD-01 02 Procédure de gestion des gabarits.pdf
  ✓ [validate_input] File OK (pdf)
  ... [parse_document] Converting document with Docling (may take a moment)...
  ✓ [parse_document] 7 pages extracted, headers/footers removed
  ... [extract_sections] Splitting document into logical sections...
  ✓ [extract_sections] 10 sections identified
  ... [assess_quality] Evaluating extraction quality...
  ✓ [assess_quality] Tier A, confidence 1.00
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

### File Layout

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

## V2 — Planned

| Addition | Details |
|---|---|
| FastAPI endpoint | `POST /parse` → SSE stream via `stream_run()` |
| LLM classification node | Add after `assess_quality` — maps sections to `RetrievalScope` using `classification/models.py` |
| Retrieval node | Query existing Qdrant pipeline with scoped filters from `RetrievalScope` |
| Human-in-the-loop | `interrupt()` when `low_quality_flag = True` — ask user to confirm before proceeding |
| Persistence | LangGraph checkpointer for session resume |
