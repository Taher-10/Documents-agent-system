## M2.4 — ComplianceState + Graph Skeleton

**Scope:** `graph/state.py`, `graph/nodes/loader.py`, `graph/workflow.py`

**Prerequisite:** M2.1 (DB populated) + M2.2 (clause_store) + M2.3 (models) done.

**Goal:** A runnable graph that loads QHSE sections from Qdrant and clause menu from SQLite. No LLM yet. Smoke-tests both data paths end-to-end.

### `graph/state.py`

```python
from typing import TypedDict
from agent_compliance.pdf_parser import ParsedSection
from agent_compliance.graph.models import SectionMatch

class ComplianceState(TypedDict):
    doc_id:           str
    company_id:       str
    applicable_norms: list[str]
    language:         str             # "EN" | "FR" — passed to all clause_store queries
    clause_menu:      dict[str, list[tuple[str, str]]]
    sections:         list[ParsedSection]
    section_matches:  list[SectionMatch]
    report:           dict | None
```

`language` defaults to `"EN"` when initializing state from an API request — no FR norms exist yet, nothing breaks. When FR norms are ingested, the caller sets this from document metadata or company locale.

---

### `graph/nodes/loader.py`

Two data sources — QHSE sections from Qdrant, clause menu from SQLite. Neither uses the other.

```python
from agent_compliance.ingestion.qhse_reader import read_document_sections
from agent_compliance.retrieval.clause_store import load_clause_menu
from agent_compliance.graph.state import ComplianceState

def loader_node(state: ComplianceState, qdrant, db_path: str) -> dict:
    sections_result = read_document_sections(
        doc_id=state["doc_id"],
        company_id=state["company_id"],
        qdrant_client=qdrant,
    )
    menu = load_clause_menu(
        state["applicable_norms"],
        language=state["language"],
        db_path=db_path,
    )
    return {
        "sections":    sections_result.sections,
        "clause_menu": menu,
    }
```

> [!warning] Security rule — unchanged
> `read_document_sections()` from `ingestion/qhse_reader.py` is the only allowed read path for `qhse_sections`. AST policy test will fail CI if you call `qdrant_client` directly for QHSE reads.

---

### `graph/workflow.py`

Graph takes both dependencies — `qdrant` for QHSE sections, `db_path` for ISO norms.

```python
from functools import partial
from langgraph.graph import StateGraph, END
from qdrant_client import QdrantClient
from agent_compliance.graph.state import ComplianceState
from agent_compliance.graph.nodes.loader import loader_node

def build_graph(qdrant: QdrantClient, db_path: str) -> StateGraph:
    graph = StateGraph(ComplianceState)
    graph.add_node("loader", partial(loader_node, qdrant=qdrant, db_path=db_path))
    graph.set_entry_point("loader")
    graph.add_edge("loader", END)
    return graph.compile()
```

**Done condition:**

```python
graph = build_graph(qdrant_client, "data/norms.db")
state = graph.invoke({
    "doc_id": "<real_doc_id>",
    "company_id": "<real_company_id>",
    "applicable_norms": ["ISO 9001"],
    "clause_menu": {}, "sections": [], "section_matches": [], "report": None,
})
assert len(state["sections"]) > 0
assert "ISO9001" in state["clause_menu"]
assert len(state["clause_menu"]["ISO9001"]) > 10   # requirement clauses loaded
```
