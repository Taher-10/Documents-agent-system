# Retrieval Progress Tracker

Last updated: 2026-04-25

## Phase Status

### M2.2 — Clause Access Layer (Completed)

Implemented a new SQLite-backed clause access layer in:
- `agent_compliance/retrieval/norm_normalizer.py`
- `agent_compliance/retrieval/clause_filter.py`
- `agent_compliance/retrieval/clause_store.py`
- `agent_compliance/retrieval/__init__.py`

Added tests:
- `agent_compliance/tests/test_sqlite_clause_access_layer.py`

Validation completed:
- `pytest -q agent_compliance/tests/test_sqlite_clause_access_layer.py` -> 6 passed
- `pytest -q agent_compliance/tests` -> 53 passed

### M2.3 — Graph Data Models (Completed)

Implemented data model foundations in:
- `agent_compliance/graph/models.py`

Added models:
- `MatchedClause` dataclass
- `SectionMatch` dataclass
- `MappingOutput` (Pydantic)
- `MatchedClauseOutput` (Pydantic)
- `SectionMatchOutput` (Pydantic, includes `NOT_APPLICABLE`)
- `to_section_match(...)` converter with hallucination-drop guard for unknown clause IDs

Added tests:
- `agent_compliance/tests/test_graph_models.py`

Validation completed:
- `pytest -q agent_compliance/tests/test_graph_models.py` -> 5 passed
- `pytest -q agent_compliance/tests` -> 67 passed

### M2.4 — ComplianceState + LangGraph Skeleton (Completed)

Implemented parallel LangGraph skeleton (legacy `agent_compliance/graph` untouched):
- `agent_compliance/graph_v2/state.py`
- `agent_compliance/graph_v2/nodes/loader.py`
- `agent_compliance/graph_v2/workflow.py`
- `agent_compliance/graph_v2/__init__.py`

Added live smoke utility:
- `agent_compliance/graph_v2/smoke_live_graph_v2.py`

Added tests:
- `agent_compliance/tests/test_graph_v2_skeleton.py`

Validation completed:
- `pytest -q agent_compliance/tests/test_graph_v2_skeleton.py` -> 5 passed
- `pytest -q agent_compliance/tests` -> 72 passed

Live integration smoke evidence (Qdrant + SQLite, FR menu):
- Inputs: `doc_id=00000000-0000-0000-0000-000000000102`, `company_id=00000000-0000-0000-0000-000000000001`, `applicable_norms=["ISO 9001"]`, `language="FR"`
- Output: `sections_count=13`, `ISO9001_menu_count=66`
- Assertions: `sections>0=True`, `ISO9001 in menu=True`, `ISO9001 menu > 10=True`

## Delivered in M2.2

1. Norm normalization
- `normalize_norm_id("ISO 9001") -> "ISO9001"`
- `normalize_norm_id("ISO 14001:2015") -> "ISO14001"`

2. Section-type fallback mapping
- Added `SECTION_TYPE_CLAUSE_MAP`
- Added robust `get_top_level_families(section_type)` normalization for:
  - uppercase/lowercase variants
  - enum-like values (example: `SectionType.PROCEDURE_TEXT`)

3. SQLite clause read access
- Added `ClauseRecord` dataclass
- Added `load_clause_menu(...)`
- Added `fetch_clauses_by_ids(...)`
- Added `fetch_clauses_by_section_type(...)`

4. Query and data behavior
- Default DB path: `agent_compliance/data/iso_clauses.db`
- Optional override: `NORMS_DB_PATH`
- Uses `sqlite3` with `sqlite3.Row`
- Base query joins `iso_clauses` with `iso_norms` on `norm_key`
- Requirement-only filter applied where expected (`has_requirements=1`)
- Numeric clause ordering enforced (`10.x` after `9.x`)
- Safe edge handling for empty inputs and unknown IDs/types

## Current Scope Boundary

M2.2, M2.3, and M2.4 are complete (SQLite access + data models + graph skeleton loader).

Not included yet:
- LLM clause mapping/matching nodes
- API/report integration (`agent_compliance/api/app.py`)
- Replacement/cutover of legacy `agent_compliance/graph/*`
- Multi-version norm selection logic (`norm_version` parameterization)

## Next Phase Plan (Recommended)

### M2.5 — Clause Mapping + Matching Nodes

Goal:
- Add post-loader intelligence (mapping + matching) on top of `graph_v2` skeleton.

Tasks:
1. Define retrieval input contract from section context:
- preferred clause IDs when available
- fallback by `section_type` when IDs absent

2. Add retrieval orchestration/matching nodes in `graph_v2`:
- call `load_clause_menu` for menu context
- call `fetch_clauses_by_ids` for targeted retrieval
- fallback to `fetch_clauses_by_section_type`

3. Add deterministic ordering and per-section trace metadata:
- include selected clause numbers and norms used

4. Add tests for graph-node behavior:
- successful targeted retrieval
- fallback retrieval path
- empty-result resilience

### M2.6 — API/Report Integration

Goal:
- Consume retrieved clause text in report generation and audit evidence outputs.

Tasks:
1. Extend internal state to carry retrieved clauses per section.
2. Update report builder to reference real clause evidence instead of static mapping.
3. Keep response contract backward compatible unless versioned change is approved.
4. Add API tests for:
- clause-backed evidence strings
- behavior when no clause found

### M2.7 — Operational Hardening

Goal:
- Production-safe behavior and observability.

Tasks:
1. Config hardening:
- explicit DB path checks and clear startup errors

2. Reliability:
- standardize sqlite exceptions into controlled internal errors
- optional read-time metrics/logging hooks

3. Performance:
- benchmark common query paths on realistic DB size
- verify index usage for `norm_id`, `top_level_family`, `clause_number`

4. Compatibility:
- decide whether to keep both `retrival` docs path and `retrieval` code path long-term

## Open Decisions for Later Phases

1. Norm version handling:
- current behavior assumes one version per norm/language in active DB
- later option: add explicit `norm_version` filter to clause-store public methods

2. Language default strategy:
- current default remains `EN`
- later option: request-driven fallback policy (`EN` -> `FR` or vice versa)

3. Legacy path cleanup:
- docs currently exist under `agent_compliance/retrival`
- runtime code is now under `agent_compliance/retrieval`
- cleanup/migration plan should be done in one dedicated refactor phase
