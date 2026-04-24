## QALITAS Mock Caller Service (External Folder) — Implementation Plan

### Summary
Build a tiny standalone FastAPI service in a separate folder that forwards the exact `MOCK_REQUEST` payload to `http://localhost:8000/analyze` with no schema transformation.  
Chosen defaults:
- Shape: **FastAPI mock service**
- Payload source: **import `agent_compliance/tests/fixtures/mock_request.py` directly**

### Key Implementation Changes
- Create external project (example: `qalitas-mock-caller/`) with:
1. `app.py` exposing:
   - `GET /health` → `{status: "ok"}`
   - `POST /trigger-analyze` → forwards fixture payload to agent `/analyze`
2. Config via env vars:
   - `AGENT_BASE_URL` (default `http://localhost:8000`)
   - `AGENT_ANALYZE_PATH` (default `/analyze`)
   - `AGENT_TIMEOUT_SECONDS` (default `30`)
   - `AGENT_REPO_ROOT` (absolute path to this repo for fixture import)
- Payload loading behavior:
1. Add `AGENT_REPO_ROOT` to `sys.path`
2. Import `MOCK_REQUEST` from `agent_compliance.tests.fixtures.mock_request`
3. Use `deepcopy(MOCK_REQUEST)` before sending (prevents accidental mutation)
4. Send as `json=payload` unchanged
- Response behavior:
1. Return upstream status code and upstream JSON body as-is when possible
2. If upstream body is non-JSON, return `{status:"error", code:"UPSTREAM_NON_JSON", detail:"..."}` with upstream status
3. If agent is unreachable/timeout, return `502` with `{status:"error", code:"AGENT_UNAVAILABLE", detail:"..."}`

### Public Interfaces
- Mock service endpoint:
1. `POST /trigger-analyze`
   - No request body required
   - Response mirrors agent response
2. `GET /health`
- Runtime contract to agent:
1. HTTP `POST {AGENT_BASE_URL}{AGENT_ANALYZE_PATH}`
2. Body is exactly `MOCK_REQUEST` fixture content

### Test Plan
- Unit tests (mock service):
1. Fixture import succeeds from `AGENT_REPO_ROOT`
2. Forward call uses exact payload equality against imported fixture
3. Upstream `200` JSON response is passed through unchanged
4. Upstream `400/422` JSON errors are passed through unchanged
5. Connection failure maps to `502 AGENT_UNAVAILABLE`
- Smoke flow:
1. Start agent service
2. Start mock caller service
3. `POST /trigger-analyze`
4. Confirm response shape/status matches direct call to agent

### Assumptions
- Agent API is running at `http://localhost:8000/analyze`.
- `FILE_BASE_PATH` for agent is configured so fixture `document.file_path` resolves to an existing test file.
- External mock service is for integration testing only (no auth/session generation logic).
- Payload must remain contract-identical to `agent_compliance/tests/fixtures/mock_request.py`.
