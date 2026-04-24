# Agent IA 2 Analyze API — Implementation Notes

## What is implemented
- FastAPI endpoint: `POST /analyze`
- Request/response schemas with strict validation
- Contract error model + HTTP status mapping
- `DocumentMeta.from_request()` builder (request-only, no DB dependency)
- Path resolution using `FILE_BASE_PATH` for relative paths (absolute paths are also supported)
- Parse/orchestrator execution + quality gate + report shaping
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
  - `DocumentMeta` dataclass
  - `TYPE_LEVEL_MAP`
  - `derive_norms(Q/E/S/H)` with mapping: Q->9001, E->14001, S->45001, H->22000

## Runtime behavior summary
1. Validate body (`AnalyzeRequest`).
2. Enforce `options.format == "json"` in MVP.
3. Build `DocumentMeta` from request.
4. Reject if no derived norms.
5. Resolve and validate document path from `FILE_BASE_PATH`.
6. Execute parser/orchestrator.
7. Reject low-quality parse output.
8. Return structured compliance report.

## Local run
```bash
export FILE_BASE_PATH=/absolute/path/to/docs/root
.venv/bin/uvicorn agent_compliance.api.app:app --reload
```

## Tests
```bash
.venv/bin/pytest -q agent_compliance/tests/test_analyze_api.py
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
