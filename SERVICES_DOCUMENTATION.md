# Services Technical Documentation

## Table of Contents
1. [Document Analyze API (`agent_compliance/api`)](#1-document-analyze-api)
2. [QALITAS Mock Caller (`qalitas-mock-caller`)](#2-qalitas-mock-caller)
3. [Shared Contract](#3-shared-contract)
4. [Integration Flow](#4-integration-flow)
5. [Critical Notes](#5-critical-notes)

---

## 1. Document Analyze API

**Location:** `agent_compliance/api/`  
**Framework:** FastAPI 1.0.0  
**Role:** Receives a document analyze request, runs the compliance pipeline, returns a structured ISO-norm coverage report.

### 1.1 Files

| File | Purpose |
|---|---|
| `app.py` | App factory, endpoint handler, error handlers, pipeline orchestration |
| `contracts.py` | All Pydantic request/response models |
| `document_meta.py` | API compatibility shim that re-exports ingestion metadata symbols |
| `../ingestion/document_meta.py` | `DocumentMeta` dataclass + `from_request()` source-of-truth |
| `../ingestion/type_mappings.py` | `TYPE_LEVEL_MAP` (26 labels) + `derive_norms` |

### 1.2 Single Endpoint: `POST /analyze`

**No authentication.** Synchronous request/response.

#### Request Body (`AnalyzeRequest`)

```json
{
  "session": {
    "company_id": "<uuid>",
    "site_id":    "<uuid>",
    "user_id":    "<uuid>"
  },
  "document": {
    "id":               "<uuid>",
    "code":             "PRO-ENV-001",
    "designation":      "Procédure de maîtrise environnementale",
    "version":          "02",
    "type_designation": "Procédure",
    "Q": false,
    "E": true,
    "S": true,
    "H": false,
    "file_path": "qalitas-mock-caller/storage/docs/PRO-ENV-001.pdf"
  },
  "options": {
    "format": "json"
  }
}
```

**Validation rules enforced by Pydantic:**
- `session.*_id` → must be valid UUID
- `document.id` → must be valid UUID
- `document.code`, `designation`, `version`, `type_designation`, `file_path` → `minLength: 1`
- `document.file_path` → custom validator rejects any path containing `..` (path traversal guard)
- `options.format` → enum `json | pdf | docx`; **only `json` is accepted at runtime** (MVP restriction)

#### Success Response (HTTP 200)

```json
{
  "status": "completed",
  "doc_id": "<uuid>",
  "doc_code": "PRO-ENV-001",
  "sections_analyzed": 12,
  "sections_skipped": 2,
  "applicable_norms": ["ISO 14001", "ISO 45001"],
  "report": {
    "executive_summary": "Document PRO-ENV-001 (...) analyzed against ISO 14001, ISO 45001.",
    "coverage_matrix": [
      {
        "clause":     "ISO 14001 8.1",
        "status":     "PARTIAL",
        "evidence":   "<first section title with content>",
        "gaps":       ["Some sections were filtered as non-actionable"],
        "confidence": 0.78
      }
    ],
    "action_plan": [
      {
        "action":   "Review skipped sections and enrich missing compliance details",
        "clause":   "ISO 14001 8.1",
        "priority": "HIGH",
        "section":  "Document review"
      }
    ],
    "overall_status": "PARTIAL"
  },
  "report_url": null
}
```

> **`report_url` is always `null` in MVP.** Reserved for future async report storage.

#### Error Response (all non-200)

```json
{
  "status": "error",
  "code":   "ERROR_CODE",
  "detail": "human-readable description",
  "errors": []
}
```

`errors` array is only populated for `VALIDATION_ERROR`.

### 1.3 HTTP Status & Error Code Map

| HTTP | Code | Trigger |
|---|---|---|
| 400 | `FORMAT_NOT_AVAILABLE` | `options.format` is `pdf` or `docx` |
| 400 | `NO_NORMS` | All four flags Q/E/S/H are `false` |
| 404 | `FILE_NOT_FOUND` | Resolved file path does not exist on disk |
| 422 | `VALIDATION_ERROR` | Pydantic model validation failure |
| 422 | `UNSUPPORTED_FORMAT` | File extension is not `.pdf` or `.docx` |
| 422 | `LOW_QUALITY_DOCUMENT` | Parser quality gate failed (tier-C / low confidence) |
| 500 | `INTERNAL_ERROR` | Unhandled exception or pipeline error |

### 1.4 Runtime Execution Flow

```
POST /analyze
    │
    ├─ 1. Pydantic validates AnalyzeRequest
    │      └─ 422 VALIDATION_ERROR on failure
    │
    ├─ 2. Enforce options.format == "json"
    │      └─ 400 FORMAT_NOT_AVAILABLE
    │
    ├─ 3. Build DocumentMeta.from_request()
    │      └─ Derives applicable norms from Q/E/S/H flags
    │         Q→ISO 9001, E→ISO 14001, S→ISO 45001, H→ISO 45001
    │         S/H are deduplicated to one ISO 45001
    │
    ├─ 4. Guard: applicable_norms must not be empty
    │      └─ 400 NO_NORMS
    │
    ├─ 5. Resolve file path
    │      relative → FILE_BASE_PATH / file_path
    │      absolute → used as-is
    │      └─ 404 FILE_NOT_FOUND / 422 UNSUPPORTED_FORMAT
    │
    ├─ 6. _run_or_load_state(full_path)
    │      Checks _STATE_CACHE first (keyed by path + mtime + size)
    │      If miss → runs compliance pipeline runner
    │      └─ 500 INTERNAL_ERROR on pipeline failure
    │
    ├─ 7. assess_quality(sections)
    │      └─ 422 LOW_QUALITY_DOCUMENT if tier-C / unreliable
    │
    └─ 8. _build_report() → AnalyzeSuccessResponse → 200
```

### 1.5 Key Components

#### `DocumentMeta` (`ingestion/document_meta.py`)

Internal dataclass built from the request. Never touches the database.
`api/document_meta.py` is a compatibility re-export layer.

```python
@dataclass(slots=True)
class DocumentMeta:
    doc_id: str
    doc_code: str
    designation: str
    version: str
    file_path: str
    doc_type: str       # derived from TYPE_LEVEL_MAP
    doc_level: int      # 1..5 hierarchy levels, unknown fallback = 0
    applicable_norms: list[str]
    company_id: str
    site_id: str
```

**`TYPE_LEVEL_MAP`** — maps French `type_designation` to `(doc_type, doc_level)`:
Full mapping is defined in `agent_compliance/ingestion/type_mappings.py` (26 labels).
Representative entries:

| type_designation | doc_type | doc_level |
|---|---|---|
| Politique qualité | policy | 1 |
| Plan Qualité | manual | 2 |
| Procédure | procedure | 3 |
| Mode opératoire | work_instruction | 4 |
| Formulaire | form | 5 |
| AUCUN | unknown | 0 |

> **Unknown `type_designation` values fall back to `("unknown", 0)`** — no error is raised, so unrecognized types silently produce `doc_level=0`.

#### In-Memory Result Cache (`_STATE_CACHE`)

```python
_STATE_CACHE: dict[str, dict[str, Any]] = {}
```

- Cache key = `"{path}:{mtime_ns}:{size_bytes}"`
- The cache is **process-scoped and never evicted**. In long-running processes with many unique documents, this is a memory leak risk.
- File modifications are detected via `mtime_ns + size`, so re-uploads of the same file name are handled correctly.

#### Report Building (`_build_report`)

- **`overall_status`**: `COVERED` if all norms covered, `PARTIAL` if any norm partial, otherwise `MISSING`.
- **`coverage_matrix`**: One `CoverageItem` per applicable norm. Status is `PARTIAL` if any sections were skipped, otherwise `COVERED`.
- **`action_plan`**: A single HIGH-priority action is added when `sections_skipped > 0`.
- **`evidence`**: Title of the first non-empty section. Falls back to `"No section evidence extracted"`.
- **`confidence`**: Average `extraction_confidence` across all sections, rounded to 2 decimal places.

#### Section Stats (`_derive_section_stats`)

- If no sections have `llm_valid` set → returns `(total_sections, 0)` — treated as all analyzed.
- If LLM decisions present: `llm_valid=True` → analyzed, `llm_valid=False` → skipped. Undecided (neither) → counted as analyzed.

### 1.6 Environment

| Variable | Default | Purpose |
|---|---|---|
| `FILE_BASE_PATH` | `.` (cwd) | Root directory for resolving relative `file_path` values |

### 1.7 Running the API

```bash
export FILE_BASE_PATH=/absolute/path/to/docs/root
.venv/bin/uvicorn agent_compliance.api.app:app --reload
# Listens on http://127.0.0.1:8000 by default
```

---

## 2. QALITAS Mock Caller

**Location:** `qalitas-mock-caller/`  
**Framework:** FastAPI 1.0.0  
**Role:** Standalone integration test harness. Builds a realistic `POST /analyze` payload from a QALITAS-like SQLite database and forwards it to the Document Analyze API.

### 2.1 Files

| File | Purpose |
|---|---|
| `qalitas_mock_caller/app.py` | FastAPI app factory, 3 endpoints |
| `qalitas_mock_caller/config.py` | `Settings` dataclass + `load_settings()` from env |
| `qalitas_mock_caller/repository.py` | `QalitasRepository` — SQLite queries |
| `db/init_mock_sqlite.sql` | SQLite DDL + seed data |
| `scripts/seed_and_smoke.py` | Deterministic DB seeding + one-call smoke runner (`preview` + `trigger-analyze`) |
| `init.sql` | Full PostgreSQL schema (production reference) |
| `.env.example` | All env vars with example values |
| `tests/test_app.py` | Test suite (7 tests) |

### 2.2 Endpoints

#### `GET /health`
Returns `{"status": "ok"}`. Always 200. No dependencies.

#### `GET /preview-analyze-request`

Query param: `document_id=<uuid>` (optional)

Returns the JSON payload that *would* be sent to the agent — without actually calling it. Used for debugging and contract verification.

| Response | Condition |
|---|---|
| 200 + payload | Document found in DB |
| 404 `MOCK_DOCUMENT_NOT_FOUND` | `document_id` not in DB |
| 500 `MOCK_DB_ERROR` | SQLite error |

#### `POST /trigger-analyze`

Query param: `document_id=<uuid>` (optional, defaults to most-recently created document)

Builds payload from DB → forwards to `{AGENT_BASE_URL}{AGENT_ANALYZE_PATH}` → proxies response.

| Response | Condition |
|---|---|
| Upstream status + JSON body | Agent responded with JSON |
| 404 `MOCK_DOCUMENT_NOT_FOUND` | Document not in DB |
| 500 `MOCK_DB_ERROR` | SQLite error |
| 502 `AGENT_UNAVAILABLE` | `httpx.RequestError` (connection refused, timeout, etc.) |
| Upstream status + `UPSTREAM_NON_JSON` | Agent returned non-JSON body |

### 2.3 Configuration (`Settings`)

All settings are loaded from environment variables via `load_settings()`. The `Settings` object is a frozen dataclass.

| Env Var | Default | Description |
|---|---|---|
| `AGENT_BASE_URL` | `http://127.0.0.1:8000` | Base URL of the Document Analyze API |
| `AGENT_ANALYZE_PATH` | `/analyze` | Path appended to base URL |
| `AGENT_TIMEOUT_SECONDS` | `120` | HTTP timeout for agent call; minimum clamped to 1.0 |
| `AGENT_REPO_ROOT` | 2 levels up from `config.py` | Root of the monorepo |
| `QALITAS_DB_PATH` | `<repo>/qalitas-mock-caller/db/qalitas_mock.db` | SQLite DB file |
| `QALITAS_DB_INIT_SQL` | `<repo>/qalitas-mock-caller/db/init_mock_sqlite.sql` | SQL file for DB bootstrap |
| `QALITAS_DOCS_DIR` | `<repo>/qalitas-mock-caller/storage/docs` | Directory for seeded PDF files |

> **`analyze_url` property** on `Settings` concatenates `agent_base_url` + `agent_analyze_path`, normalizing slashes automatically.

> **Timeout validation**: if `AGENT_TIMEOUT_SECONDS` is non-numeric, it silently falls back to `30.0`. It is then clamped to `max(value, 1.0)`.

### 2.4 Repository (`QalitasRepository`)

#### DB Initialization (`init_if_needed`)

- Called once at app startup.
- **Only runs if the DB file does not yet exist.** If the file is present (even empty), initialization is skipped entirely.
- Creates the SQLite file, runs the full DDL + seed script as a single transaction.

#### Document Query (`build_analyze_request`)

Executes a 3-table JOIN:

```sql
SELECT
    d.Id, d.Code, d.Designation, d."Index" AS version,
    t.Designation AS type_designation,
    d.Q, d.E, d.S, d.H, d.FilePath,
    d.CompanyId, d.SiteId,
    e.Id AS user_id
FROM InternalDocs d
JOIN Ini_Types t ON t.Id = d.TypesId
LEFT JOIN Employees e
    ON e.SiteId = d.SiteId
   AND e.CompanyId = d.CompanyId
   AND e.IsEnabled = 1
WHERE (? IS NULL OR d.Id = ?)
ORDER BY d.CreatedDate DESC
LIMIT 1
```

**Key behaviors:**
- `document_id=None` → selects the **most recently created** document (via `ORDER BY CreatedDate DESC LIMIT 1`).
- `document_id=<uuid>` → filters to that specific document.
- Employee lookup is a `LEFT JOIN` — if no active employee exists for the site/company, `user_id` falls back to the hardcoded sentinel `"00000000-0000-0000-0000-000000000003"`.
- Only one employee is returned (`LIMIT 1`). If multiple active employees exist for the site/company, the result is non-deterministic.

#### Built Payload Structure

```json
{
  "session": {
    "company_id": "<from DB>",
    "site_id":    "<from DB>",
    "user_id":    "<from DB or fallback sentinel>"
  },
  "document": {
    "id":               "<from DB>",
    "code":             "PRO-ENV-001",
    "designation":      "Procédure de maîtrise environnementale",
    "version":          "02",
    "type_designation": "Procédure",
    "Q": false,
    "E": true,
    "S": true,
    "H": false,
    "file_path": "qalitas-mock-caller/storage/docs/PRO-ENV-001.pdf"
  },
  "options": {
    "format": "json"
  }
}
```

### 2.5 SQLite Mock Database Schema

```
Company (Id, Name, CompanyGroupId)
    │
    └─ Site (Id, Name, CompanyId → Company)
            │
            ├─ Employees (Id, IsEnabled, SerialNumber, ..., SiteId, CompanyId)
            ├─ Ini_Types  (Id, Code, Number, Designation, SiteId, CompanyId)
            └─ InternalDocs (Id, Code, Index, Designation, Q, S, E, H,
                             TypesId → Ini_Types, FilePath, CompanyId, SiteId,
                             CreatedDate)
```

**Seeded data (single test record):**

| Entity | Value |
|---|---|
| Company | `00000000-...0001` "QALITAS Mock Company" |
| Site | `00000000-...0002` "QALITAS Mock Site" |
| Employee | `00000000-...0003` "Mock Caller" (EMP-0001) |
| Type | `00000000-...0010` Code=PRO, Designation="Procédure" |
| Document | `00000000-...0004` PRO-ENV-001 v02, E=1, S=1, Q=0, H=0 |

### 2.6 Document Seeding (`_ensure_docs_seeded`)

On every startup, the app checks if `{QALITAS_DOCS_DIR}/PRO-ENV-001.pdf` exists. If not, it attempts to copy from:

```
{AGENT_REPO_ROOT}/agent_compliance/qhme_docs/qa-qc-documents-sample.pdf
```

If that source does not exist, the seed is silently skipped — **no error is raised**. The document will be missing from disk, and `/trigger-analyze` will return `404 FILE_NOT_FOUND` from the agent.

### 2.7 Running the Mock Caller

```bash
# From repo root
.venv/bin/uvicorn qalitas_mock_caller.app:app \
    --app-dir qalitas-mock-caller \
    --reload \
    --port 8100

# Preview payload (no agent call)
curl http://localhost:8100/preview-analyze-request

# Trigger full flow
curl -X POST http://localhost:8100/trigger-analyze

# Target a specific document
curl -X POST "http://localhost:8100/trigger-analyze?document_id=<uuid>"
```

### 2.8 Tests (`tests/test_app.py`)

| Test | What It Verifies |
|---|---|
| `test_health` | `/health` returns 200 `{status: ok}` |
| `test_preview_request_comes_from_db` | Payload fields match seeded DB record |
| `test_trigger_analyze_pass_through_success` | 200 agent response proxied unchanged |
| `test_trigger_analyze_pass_through_business_error` | 422 agent error proxied unchanged |
| `test_trigger_analyze_maps_request_error` | `httpx.ConnectError` → 502 `AGENT_UNAVAILABLE` |
| `test_trigger_analyze_maps_non_json` | Non-JSON agent body → `UPSTREAM_NON_JSON` |
| `test_document_not_found_from_db` | Missing `document_id` → 404 `MOCK_DOCUMENT_NOT_FOUND` |
| `test_db_seed_created` | SQLite DB file created and contains ≥1 InternalDocs row |

All tests use `tmp_path` (pytest fixture) for isolated DB and docs directories. Agent calls are monkeypatched — no real agent needed.

### 2.9 Seed + Smoke Utility (`scripts/seed_and_smoke.py`)

Purpose: seed deterministic mock records in `InternalDocs` and run one end-to-end smoke call through the mock caller transport path.

What it does:
- Applies `QALITAS_DB_INIT_SQL` via `executescript` (idempotent).
- Upserts two deterministic docs:
  - Doc A: `00000000-0000-0000-0000-000000000101` (`H=true`, `S=false`, `Q=false`, `E=false`) — default smoke target.
  - Doc B: `00000000-0000-0000-0000-000000000102` (`S=true`, `H=true`, `Q=false`, `E=false`) — future regression target.
- Calls `GET /preview-analyze-request?document_id=...` and validates Q/E/S/H flags.
- Calls `POST /trigger-analyze?document_id=...` unless `--seed-only` is set.

Usage:

```bash
# Seed only
.venv/bin/python qalitas-mock-caller/scripts/seed_and_smoke.py --seed-only

# Seed + one smoke call (mock caller must already run on :8100)
.venv/bin/python qalitas-mock-caller/scripts/seed_and_smoke.py
```

`--seed-only` performs DB initialization + dataset upsert only and does not require any running HTTP service.

Exit behavior:
- Returns non-zero on seeding failure, preview mismatch, transport failure, or upstream error status.

---

## 3. Shared Contract

**Location:** `agent_compliance/contracts/`

| File | Purpose |
|---|---|
| `analyze_v1.md` | Human-readable contract spec |
| `openapi.analyze.v1.json` | Machine-readable OpenAPI 3.1.0 snapshot |

The OpenAPI snapshot is generated from the live FastAPI app:

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

> **The snapshot must be regenerated and tests re-run whenever `contracts.py` changes.** Otherwise the snapshot drifts from the live schema.

---

## 4. Integration Flow

```
QALITAS Platform
      │
      │  (future production)
      ▼
┌─────────────────────────────┐
│  QALITAS Mock Caller :8100  │   ← integration test harness
│  (qalitas-mock-caller/)     │
│                             │
│  SQLite DB ──► payload ─────┼──► POST /analyze
│  (QALITAS-like schema)      │          │
└─────────────────────────────┘          │
                                         ▼
                              ┌─────────────────────────┐
                              │  Document Analyze API    │
                              │  agent_compliance/api/   │
                              │  :8000                   │
                              │                          │
                              │  1. Validate request     │
                              │  2. Derive norms         │
                              │  3. Resolve file path    │
                              │  4. Run pipeline         │
                              │  5. Quality gate         │
                              │  6. Build report         │
                              └─────────────────────────┘
```

**Key architectural principle:** The Document Analyze API has **zero dependency on the QALITAS database**. All document metadata needed for analysis is passed in the request body. The Mock Caller exists purely to simulate what QALITAS would send.

---

## 5. Critical Notes

### 5.1 MVP Restrictions (must not be overlooked)

- `options.format` only accepts `"json"`. `"pdf"` and `"docx"` are in the schema for forward compatibility but return `400 FORMAT_NOT_AVAILABLE` at runtime.
- `report_url` is always `null`. Async report delivery is not implemented.

### 5.2 `_STATE_CACHE` is a Memory Leak

The in-process result cache in `agent_compliance/api/app.py` is a plain dict with no eviction policy. In production, running many unique documents will accumulate parsed state indefinitely. This must be replaced with an LRU cache (`functools.lru_cache`, `cachetools`, or Redis) before production deployment.

### 5.3 DB Initialization is Not Re-entrant

`QalitasRepository.init_if_needed()` checks for the DB *file*, not schema version. If the DB file exists but is corrupted or has an outdated schema, initialization is silently skipped and subsequent queries will fail at runtime with a `RepositoryError`.

### 5.4 Non-Deterministic Employee Resolution

The repository query does `LEFT JOIN Employees ... LIMIT 1` with no `ORDER BY` on the employee. If a site/company has multiple active employees, the selected `user_id` is database-order-dependent and not stable.

### 5.5 Silent Doc Seeding Failure

If `{AGENT_REPO_ROOT}/agent_compliance/qhme_docs/qa-qc-documents-sample.pdf` is missing, `_ensure_docs_seeded()` silently no-ops. The result is a missing document file, which produces `404 FILE_NOT_FOUND` when `/trigger-analyze` is called — with no startup warning.

### 5.6 `type_designation` Fallback is Silent

Unknown French document type labels (not in `TYPE_LEVEL_MAP`) produce `doc_type="unknown"` and `doc_level=0` without raising an error or logging a warning. This can silently affect compliance report interpretation.

### 5.7 Coverage Status Logic is Simplified

`_build_report` sets `status="PARTIAL"` for every norm when *any* sections are skipped, regardless of which norm the skipped sections relate to. There is no per-norm section attribution.

### 5.8 Path Traversal Guard Scope

The `..` check in `AnalyzeDocument.validate_file_path` prevents Pydantic from accepting traversal paths. However, the runtime guard in `_resolve_relative_file_path` only enforces `relative_to(base)` for **relative paths**. Absolute paths bypass the sandbox check entirely and are used as-is.

### 5.9 PostgreSQL Schema vs SQLite Schema

`init.sql` (root of mock-caller) is the full **PostgreSQL** production schema (uses `UUID`, `BOOLEAN`, `TIMESTAMP`, `uuid_generate_v4()`). `db/init_mock_sqlite.sql` is the simplified **SQLite** adaptation (uses `TEXT` for IDs, `INTEGER` for booleans). These schemas must be kept in sync manually. The SQLite version omits several tables present in the PostgreSQL schema (`Classifyings`, `Ini_Domains`, `Ini_SubDomains`, `InternalDocTeams`).

### 5.10 Timeout Fallback

If `AGENT_TIMEOUT_SECONDS` is set to a non-numeric string, `config.py` silently falls back to `30.0` seconds (not the documented default of `120`). This discrepancy between the fallback value and the env default may cause unexpected short timeouts in misconfigured environments.
