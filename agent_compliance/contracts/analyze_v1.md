# Agent IA 2 API Contract v1 (MVP)

## Integration Model
- Agent IA 2 is a standalone HTTP microservice.
- QALITAS owns DB/session and sends all required metadata in the request.
- Agent IA 2 does not query QALITAS DB.

## Endpoint
`POST /analyze`

- Synchronous request/response contract.
- MVP supports JSON output only.

## Request Schema
```json
{
  "session": {
    "company_id": "uuid",
    "site_id": "uuid",
    "user_id": "uuid"
  },
  "document": {
    "id": "uuid",
    "code": "PRO-ENV-001",
    "designation": "Procédure de maîtrise environnementale",
    "version": "02",
    "type_designation": "Procédure",
    "Q": false,
    "E": true,
    "S": true,
    "H": false,
    "file_path": "test/PRO-ENV-001.pdf"
  },
  "options": {
    "format": "json"
  }
}
```

## Validation and Rules
- `session.company_id`, `session.site_id`, `session.user_id` must be UUIDs.
- `document.id` must be UUID.
- `document.file_path` must be relative to `FILE_BASE_PATH`.
- Absolute paths and path traversal (`..`) are rejected.
- Norms are derived by agent from `Q/E/S/H`.
- `options.format` allows `json|pdf|docx` in schema, but MVP accepts only `json`.

## Runtime Flow
1. Validate request body.
2. Reject unsupported format (`FORMAT_NOT_AVAILABLE`) if not `json`.
3. Build `DocumentMeta` from request (`from_request()`), derive norms from flags.
4. Resolve full path: `FILE_BASE_PATH / document.file_path`.
5. Validate file existence and extension (`.pdf`/`.docx`).
6. Run compliance parser orchestrator (normal Python orchestrator, no LangGraph runtime).
7. Assess parse quality; reject low quality (`LOW_QUALITY_DOCUMENT`) for tier-C/unreliable output.
8. Build and return JSON report payload.

## Success Response (200)
```json
{
  "status": "completed",
  "doc_id": "uuid",
  "doc_code": "PRO-ENV-001",
  "sections_analyzed": 12,
  "sections_skipped": 2,
  "applicable_norms": ["ISO 14001", "ISO 22000"],
  "report": {
    "executive_summary": "...",
    "coverage_matrix": [
      {
        "clause": "ISO 14001 8.1",
        "status": "PARTIAL",
        "evidence": "Section title",
        "gaps": ["..."],
        "confidence": 0.78
      }
    ],
    "action_plan": [
      {
        "action": "...",
        "clause": "ISO 14001 7.5.3",
        "priority": "HIGH",
        "section": "Document review"
      }
    ],
    "overall_status": "PARTIAL"
  },
  "report_url": null
}
```

## Error Model
```json
{
  "status": "error",
  "code": "ERROR_CODE",
  "detail": "human-readable detail",
  "errors": []
}
```

`errors` is present for validation failures (`VALIDATION_ERROR`) and omitted otherwise.

## HTTP Status Mapping
- `200`: success
- `400`: `NO_NORMS`, `FORMAT_NOT_AVAILABLE`
- `404`: `FILE_NOT_FOUND`
- `422`: `VALIDATION_ERROR`, `LOW_QUALITY_DOCUMENT`, `UNSUPPORTED_FORMAT`
- `500`: `INTERNAL_ERROR`

## Environment
- Required path setting:

```bash
export FILE_BASE_PATH=/path/to/document/root
```

Example resolved file:
- Request: `"file_path": "test/PRO-ENV-001.pdf"`
- Resolved: `${FILE_BASE_PATH}/test/PRO-ENV-001.pdf`

## Contract Artifacts
- Human-readable contract: `agent_compliance/contracts/analyze_v1.md`
- OpenAPI snapshot: `agent_compliance/contracts/openapi.analyze.v1.json`
- Request fixture: `agent_compliance/tests/fixtures/mock_request.py`
- Golden success response: `agent_compliance/tests/fixtures/golden_success_response.json`

## Forward Compatibility
- `options.format` is already in v1 schema to avoid request-shape changes later.
- `pdf` and `docx` values are reserved for future phases and currently return `FORMAT_NOT_AVAILABLE`.
