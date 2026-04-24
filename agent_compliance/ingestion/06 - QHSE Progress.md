---
tags: [progress, ingestion, qhse, mvp]
created: 2026-04-24
updated: 2026-04-24
status: in-progress
parent: "[[00 - Home]]"
---

# QHSE Ingestion Progress

## Progress Conventions
- Date format: `YYYY-MM-DD`.
- Allowed phase statuses: `not-started | in-progress | blocked | completed`.
- Source plan: `05 - QHSE Ingestion Plan (MVP Phases).md`.

## Current Snapshot
- Overall status: `in-progress`
- Current phase: `Phase 4 - Tenant-Safe Read Path and Security Hardening`
- Last update: `2026-04-24`
- Next milestone: `Phase 4 implementation kickoff (guarded read helpers + tenant filter audit)`

## Phase Progress

### Phase 1 - Domain Alignment and Source of Truth
- Status: `completed`
- Completion: `100%`
- Completed items:
- Added `agent_compliance/ingestion/type_mappings.py` as source of truth (`TYPE_LEVEL_MAP`, `NORM_FLAG_MAP`, `derive_norms`).
- Added `agent_compliance/ingestion/document_meta.py` with `DocumentMeta.from_request()`.
- Added `agent_compliance/ingestion/__init__.py` exports.
- Converted `agent_compliance/api/document_meta.py` to compatibility re-export shim.
- Added tests `agent_compliance/tests/test_ingestion_document_meta.py`.
- Added API regression tests for `H=true` and `S/H` dedup behavior.
- Validation passed: `29` tests green (`test_ingestion_document_meta.py` + `test_analyze_api.py`).
- In-progress items:
- None.
- Next actions:
- None.
- Blockers:
- None currently.
- Owner/date:
- Owner: `session-agent`
- Date: `2026-04-24`

### Phase 2 - Qdrant Ingestion Writer
- Status: `completed`
- Completion: `100%`
- Completed items:
- Added `agent_compliance/ingestion/payload_builder.py` for section + parse-result + metadata payload assembly.
- Added `agent_compliance/ingestion/utils.py` with deterministic `stable_uuid(doc_id, section_id)`.
- Added `agent_compliance/ingestion/qhse_ingester.py` with:
- `ingest_document()` parse/filter/embed/upsert flow.
- `ensure_qhse_collection()` collection + payload-index ensure flow.
- `has_ingested_document(doc_id, company_id)` helper enforcing tenant filter.
- Added strict vector-size guard (`1024`) for collection compatibility and embedding output shape.
- Added ingestion counters and reasons in `IngestResult` (ingested/skipped breakdown).
- Exported ingestion writer interfaces from `agent_compliance/ingestion/__init__.py`.
- Added tests `agent_compliance/tests/test_qhse_ingester.py` (`9` tests).
- Validation passed: `38` tests green (`agent_compliance/tests`).
- Smoke test passed against local Qdrant (`qhse_sections`):
- First ingest: `total_sections=14`, `ingested=13`, `skipped_empty_text=1`, `has_ingested_document=True`, tenant/doc count=`13`.
- Re-ingest: tenant/doc count remained `13` (idempotent upsert, no duplication).
- In-progress items:
- None.
- Next actions:
- Start Phase 3 API write-through integration (`/analyze` ingest-or-skip path).
- Add embedder adapter from `rag` async `embed_text` to ingestion writer callable contract.
- Blockers:
- None currently.
- Owner/date:
- Owner: `session-agent`
- Date: `2026-04-24`

### Phase 3 - API Integration (Write-Through)
- Status: `completed`
- Completion: `100%`
- Completed items:
- Added write-through ingestion integration in `agent_compliance/api/app.py`:
- Ingest-or-skip behavior before parser/orchestrator execution.
- Cache check by `(doc_id, company_id)` using `has_ingested_document`.
- Strict ingestion failure mapping to `500 INGESTION_ERROR`.
- `low_quality_document` ingestion result mapped to `422 LOW_QUALITY_DOCUMENT`.
- Added lazy process-level clients for Qdrant and embedder runtime.
- Added shutdown cleanup for embedder lifecycle.
- Added async ingestion bridge `ingest_document_async(...)` in `agent_compliance/ingestion/qhse_ingester.py`.
- Exported async ingestion API via `agent_compliance/ingestion/__init__.py`.
- Extended API tests in `agent_compliance/tests/test_analyze_api.py` with:
- Cache miss ingests and keeps response contract unchanged.
- Cache hit skips ingestion path.
- Ingestion exception -> `500 INGESTION_ERROR`.
- Ingestion low-quality -> `422 LOW_QUALITY_DOCUMENT`.
- Zero-ingested non-low-quality -> `500 INGESTION_ERROR`.
- Validation passed: `43` tests green (`agent_compliance/tests`).
- End-to-end smoke passed via `qalitas-mock-caller` -> `/analyze` -> `qhse_sections`:
- First call status `200`, second call status `200` for same document.
- Count behavior: `0 -> 13 -> 13` (ingest once, no duplication).
- Deterministic ID check passed (`stable_uuid(doc_id, section_id)` match).
- Required payload fields + collection filter schema keys verified.
- In-progress items:
- None.
- Next actions:
- Start Phase 4 security hardening tasks.
- Blockers:
- None currently.
- Owner/date:
- Owner: `session-agent`
- Date: `2026-04-24`

### Phase 4 - Tenant-Safe Read Path and Security Hardening
- Status: `not-started`
- Completion: `0%`
- Completed items:
- None.
- In-progress items:
- None.
- Next actions:
- Implement guarded read helpers requiring `company_id`.
- Run security audit over all ingestion retrieval queries.
- Blockers:
- None currently (Phase 3 completed).
- Owner/date:
- Owner: `session-agent`
- Date: `2026-04-24`

### Phase 5 - Contract, Docs, and Validation Sync
- Status: `not-started`
- Completion: `0%`
- Completed items:
- None.
- In-progress items:
- None.
- Next actions:
- Sync docs/snapshots/tests with final implemented behavior.
- Finalize handoff details and unresolved risk register.
- Blockers:
- Depends on Phase 4 completion.
- Owner/date:
- Owner: `session-agent`
- Date: `2026-04-24`

## Decisions Log

| Decision | Date | Rationale | Impact | Change Policy |
| --- | --- | --- | --- | --- |
| Implement in `agent_compliance` for MVP (no `agent_2` migration now). | 2026-04-24 | Matches current codebase reality and reduces migration risk. | Limits scope to additive ingestion integration in existing structure. | Revisit only after MVP completion and explicit migration request. |
| `H` maps to `ISO 45001`; `S` and `H` deduplicate to one norm. | 2026-04-24 | Aligns locked ingestion decision and safety/health standard model. | Contract-sensitive behavior for `applicable_norms` and report matrix logic. | Any change requires contract/doc/test updates in same change set. |
| Tenant filter guardrail is mandatory on every Qdrant read. | 2026-04-24 | Prevents cross-tenant data leakage in single-collection model. | Affects all retrieval helpers and security verification requirements. | Non-negotiable; no bypass allowed. |
| Keep `04 - QHSE Ingestion Plan.md` as historical reference. | 2026-04-24 | Preserves original context and decisions trail. | New work tracks on files `05` and `06`. | Archive/merge only via explicit request. |
| Phase 2 ingestion writer uses injected `embed_fn(text) -> list[float]` contract. | 2026-04-24 | Keeps writer backend-agnostic and testable; API layer owns runtime embedder lifecycle. | Requires Phase 3 async adapter when wiring `rag` `EmbedderService.embed_text`. | Change requires coordinated updates in writer + API integration tests. |
| Phase 2 vector-size policy is strict fail at `1024` mismatch. | 2026-04-24 | Prevents silent mixing of incompatible vectors in `qhse_sections`. | Ingestion raises explicit error on incompatible collection/model output dimensions. | Any relaxation requires explicit migration/data integrity review. |
| Phase 2 embedding failure policy is `skip and report`. | 2026-04-24 | Maintains document-level progress while exposing failures through counters. | `IngestResult` includes skipped embed-error counts; ingestion does not fail whole document for single-section failures. | Changing to fail-fast requires contract + test updates. |
| Phase 3 API policy is strict write-through ingestion before parser flow. | 2026-04-24 | Ensures indexed QHSE sections exist at analysis time and prevents silent ingestion bypass. | `/analyze` now executes ingest-or-skip by `(doc_id, company_id)` prior to orchestrator run. | Any relaxation requires explicit API behavior decision and test updates. |
| Phase 3 ingestion failure mapping uses `500 INGESTION_ERROR` (except low-quality -> `422`). | 2026-04-24 | Distinguishes server-side ingestion failures from existing low-quality parse semantics. | Error code path added without changing success response schema. | Any remap requires API tests and downstream caller handling updates. |

## Session Handoff

### Current Context
- Planning docs are now split into:
- Historical reference: `04 - QHSE Ingestion Plan.md`
- Execution plan: `05 - QHSE Ingestion Plan (MVP Phases).md`
- Live tracker: `06 - QHSE Progress.md`

### Pending Tasks
- Start implementation at Phase 4 tasks.
- Update tracker at each phase gate or blocker.
- Keep decisions log synchronized with any scope or behavior changes.

### Commands and Paths
- Ingestion docs path: `agent_compliance/ingestion/`
- Suggested verification commands:
- `ls -la agent_compliance/ingestion`
- `rg -n "Phase 1|Phase 2|Phase 3|Phase 4|Phase 5" agent_compliance/ingestion/06 - QHSE Progress.md`
- `rg -n "H -> ISO 45001|S/H|company_id" agent_compliance/ingestion/05 - QHSE Ingestion Plan (MVP Phases).md agent_compliance/ingestion/06 - QHSE Progress.md`

### Validation Checklist
- `05` and `06` both exist and numbering is unique.
- Each of 5 phases has its own dedicated progress subsection in `06`.
- Locked decisions appear in `05` and are recorded in `06` decisions log.
- Session handoff contains actionable next steps, blockers, commands, and key paths.

### Known Risks
- Documentation/code drift if tracker is not updated when behavior changes.
- Tenant guardrail risk if any direct Qdrant call bypasses filtered helper APIs.
- Contract drift risk if behavior changes later without synchronized docs/tests/snapshots.
- Runtime dependency risk (Qdrant/embedder availability) can affect strict write-through API latency and failure rate.

## Important Details
- Qdrant target collection for QHSE ingestion: `qhse_sections`.
- Embedding model target: `Qwen3-Embedding`.
- Expected embedding vector size: `1024`.
- Phase 2 embedding integration strategy: injected `embed_fn(text) -> list[float]` callable.
- Phase 3 API integration strategy: strict write-through ingest-or-skip before parser/orchestrator report flow.
- Tenant guardrail: all Qdrant read queries must include `company_id` filter.
- Contract-sensitive rule: `H -> ISO 45001`; `S` and `H` deduplicate to one `ISO 45001` in derived norms.
- This documentation task introduces no API schema change by itself.
