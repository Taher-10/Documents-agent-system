# QALITAS Mock Caller

Standalone mock service that builds `/analyze` payload from a QALITAS-like DB and forwards it to Agent IA 2.

## Endpoints
- `GET /health` -> `{"status": "ok"}`
- `GET /preview-analyze-request` -> generated payload from DB (debug/verification)
- `POST /trigger-analyze` -> sends DB-generated payload to Agent `/analyze`
  - optional query param: `document_id=<uuid>`

## Environment variables
- `AGENT_BASE_URL` (default: `http://127.0.0.1:8000`)
- `AGENT_ANALYZE_PATH` (default: `/analyze`)
- `AGENT_TIMEOUT_SECONDS` (default: `120`)
- `AGENT_REPO_ROOT` (default: repo root)
- `QALITAS_DB_PATH` (default: `qalitas-mock-caller/db/qalitas_mock.db`)
- `QALITAS_DB_INIT_SQL` (default: `qalitas-mock-caller/db/init_mock_sqlite.sql`)
- `QALITAS_DOCS_DIR` (default: `qalitas-mock-caller/storage/docs`)

## Behavior
- Initializes SQLite DB from `QALITAS_DB_INIT_SQL` if DB file is missing
- Seeds local docs repo at `qalitas-mock-caller/storage/docs`
- Builds payload by joining DB tables (`InternalDocs`, `Ini_Types`, `Employees`)
- Sends payload unchanged to `{AGENT_BASE_URL}{AGENT_ANALYZE_PATH}`
- Passes upstream JSON body and status code as-is
- Returns:
  - `502 AGENT_UNAVAILABLE` if agent is unreachable
  - `UPSTREAM_NON_JSON` when agent returns non-JSON body
  - `MOCK_DOCUMENT_NOT_FOUND` when requested `document_id` is absent

## Run
From repo root:

```bash
.venv/bin/uvicorn qalitas_mock_caller.app:app --app-dir qalitas-mock-caller --reload --port 8100
```

Preview generated request:

```bash
curl http://localhost:8100/preview-analyze-request
```

Trigger call:

```bash
curl -X POST http://localhost:8100/trigger-analyze
```

## Seed + Smoke Script

Reusable utility script to seed deterministic mock DB data and run one integration smoke call through the mock caller.

Script path:

```bash
qalitas-mock-caller/scripts/seed_and_smoke.py
```

Default scenarios seeded into `InternalDocs`:
- Doc A (default smoke target): `00000000-0000-0000-0000-000000000101` with `H=true, S=false, Q=false, E=false`
- Doc B (future regression): `00000000-0000-0000-0000-000000000102` with `S=true, H=true, Q=false, E=false`

Seed only (no trigger call):

```bash
.venv/bin/python qalitas-mock-caller/scripts/seed_and_smoke.py --seed-only
```

Seed + one smoke call via mock endpoint (`POST /trigger-analyze?document_id=...`):

```bash
.venv/bin/python qalitas-mock-caller/scripts/seed_and_smoke.py
```

Target Doc B explicitly:

```bash
.venv/bin/python qalitas-mock-caller/scripts/seed_and_smoke.py \
  --document-id 00000000-0000-0000-0000-000000000102
```

Notes:
- `--seed-only` does not require the mock caller service to be running.
- Smoke mode assumes mock caller is running at `http://127.0.0.1:8100`.
- The script validates preview payload flags before trigger call.
- Exit code is non-zero on seeding errors, preview validation failures, or smoke transport/upstream failures.

## Test
```bash
.venv/bin/pytest -q qalitas-mock-caller/tests/test_app.py
```
