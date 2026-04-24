# Agent IA 2 Analyze API — Implementation Notes

## What is implemented
- FastAPI endpoint: `POST /analyze`
- Request/response schemas with strict validation
- Contract error model + HTTP status mapping
- `DocumentMeta.from_request()` builder (request-only, no DB dependency)
- Ingestion-domain metadata source of truth (`agent_compliance/ingestion`)
- Strict write-through ingestion gate before parser flow (`ingest-or-skip` by `doc_id + company_id`)
- Path resolution using `FILE_BASE_PATH` for relative paths (absolute paths are also supported)
- Parse/orchestrator execution + quality gate + report shaping
- Guarded QHSE read helper surface (`agent_compliance/ingestion/qhse_reader.py`) with mandatory tenant filter
- OpenAPI snapshot and contract tests

## Module Map
- `agent_compliance/api/app.py`
  - FastAPI app creation
  - endpoint handler and error handlers
  - path resolution and cache
  - report payload assembly
- `agent_compliance/api/contracts.py`
  - Pydantic request/response contracts
- `agent_compliance/api/document_meta.py`
  - compatibility shim (re-export only)
- `agent_compliance/ingestion/document_meta.py`
  - `DocumentMeta` dataclass + `from_request()`
- `agent_compliance/ingestion/type_mappings.py`
  - `TYPE_LEVEL_MAP` (26 labels)
  - `derive_norms(Q/E/S/H)` with mapping: Q->9001, E->14001, S->45001, H->45001
  - S/H deduplication with deterministic ordering
- `agent_compliance/ingestion/qhse_reader.py`
  - `has_ingested_document(doc_id, company_id)` guarded cache-check helper
  - `read_document_sections(doc_id, company_id)` tenant-safe section retrieval helper
  - `RetrievedSections` + typed metadata contract (`SectionReadMetadata`)

## Runtime behavior summary
1. Validate body (`AnalyzeRequest`).
2. Enforce `options.format == "json"` in MVP.
3. Build `DocumentMeta` from request.
4. Reject if no derived norms.
5. Resolve and validate document path from `FILE_BASE_PATH`.
6. Run strict write-through ingestion: cache-check by `(doc_id, company_id)` then ingest on miss.
7. Execute parser/orchestrator.
8. Reject low-quality parse output.
9. Return structured compliance report.

## Local run
```bash
export FILE_BASE_PATH=/absolute/path/to/docs/root
.venv/bin/uvicorn agent_compliance.api.app:app --reload
```

## Tests
```bash
.venv/bin/pytest -q agent_compliance/tests
```

## Refresh OpenAPI snapshot
```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from agent_compliance.api import app
Path('agent_compliance/contracts/openapi.analyze.v1.json').write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2) + '\n',
    encoding='utf-8',
)
PY
```

Run tests after regenerating to ensure no unintended contract drift.
