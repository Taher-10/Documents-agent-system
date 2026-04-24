---
tags: [plan, ingestion, qhse, mvp, phases]
created: 2026-04-24
updated: 2026-04-24
status: in-progress
parent: "[[00 - Home]]"
---

# QHSE Ingestion Plan (MVP Phases)

## Objective
Deliver a phased MVP implementation for QHSE ingestion in `agent_compliance` with tenant-safe Qdrant storage, stable contracts, and clear handoff gates between phases.

## Historical Reference
- `04 - QHSE Ingestion Plan.md` remains unchanged and is treated as historical/reference context.

## Locked Decisions
- `H -> ISO 45001` (not ISO 22000).
- `S` and `H` both map to `ISO 45001` and must be deduplicated in `derive_norms`.
- Implementation target is `agent_compliance` in this MVP (no `agent_2` migration in this plan).
- Phase framing is MVP-first: additive ingestion, low regression risk, contract stability.
- Tenant isolation guardrail is mandatory: every Qdrant read query must include `company_id` filter.

## Phase Ordering and Handoffs
- Order is fixed: Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5.
- Handoff rule: a phase exits only when its exit criteria are met and artifacts are documented in `06 - QHSE Progress.md`.
- If a blocker prevents exit, status becomes `blocked` and unresolved items move to the next session handoff.

## Phase 1 - Domain Alignment and Source of Truth

### Goal
Align ingestion domain metadata and norm/type mapping with agreed MVP behavior.

### Scope
- Create ingestion-domain mapping and metadata modules under `agent_compliance/ingestion`.
- Keep API request/response schema unchanged.

### Implementation Tasks
- Add `type_mappings.py` with full `TYPE_LEVEL_MAP`, `NORM_FLAG_MAP`, and `derive_norms`.
- Add `document_meta.py` in ingestion domain with `DocumentMeta.from_request`.
- Update API imports to consume ingestion-domain `DocumentMeta`.
- Ensure `H -> ISO 45001` mapping and `S/H` deduplication behavior.

### Acceptance Criteria
- `derive_norms` returns deduplicated norms and maps `H` to `ISO 45001`.
- Unknown type designations fall back to `("unknown", 0)` without schema break.
- `/analyze` contract shape remains unchanged.

### Risks
- Contract drift if tests/snapshots are not updated after mapping correction.
- Partial mapping migration if API still reads old mapping logic.

### Exit Criteria
- All mapping and metadata reads come from ingestion-domain modules.
- Tests for norm derivation and type mapping are green.

## Phase 2 - Qdrant Ingestion Writer

### Goal
Implement parse-filter-embed-upsert writer for QHSE sections into Qdrant.

### Scope
- Build ingestion writer and payload construction components.
- Set up `qhse_sections` collection and payload indexes.

### Implementation Tasks
- Add `payload_builder.py` for section + parse-result + meta payload assembly.
- Add `utils.py` with deterministic `stable_uuid(doc_id, section_id)`.
- Add `qhse_ingester.py` with `ingest_document()` and ingest result reporting.
- Use injected `embed_fn(text) -> list[float]` for embedding integration (backend wiring deferred to later phase integration).
- Enforce quality/confidence ingestion filters (`tier != C`, confidence threshold).
- Enforce strict vector-size guard (`1024`) at both collection validation and section embedding output.
- Add `has_ingested_document(doc_id, company_id)` helper with mandatory tenant filter.
- Ensure collection/index creation for `company_id`, `site_id`, `section_type`, `doc_type`, `doc_level`.

### Acceptance Criteria
- Ingestion upserts deterministic point IDs.
- Payload contains tenant fields and required section/document metadata.
- Collection schema and indexes exist for tenant and retrieval filtering.
- Embed failures are skipped and reported in ingestion counters without aborting whole-document ingestion.

### Risks
- Vector-size mismatch if embedder configuration diverges from expected model output.
- Reingestion duplication if deterministic ID/caching checks are incorrect.

### Exit Criteria
- One real document can be ingested and verified in `qhse_sections`.
- Ingestion result includes accurate ingested/skipped counts.

## Phase 3 - API Integration (Write-Through)

### Goal
Integrate ingestion path into `/analyze` with minimal behavior regression.

### Scope
- Add ingest-or-skip logic into API runtime flow.
- Keep current report generation path intact for MVP safety.

### Implementation Tasks
- Add cache check by `(doc_id, company_id)` before ingesting.
- In `/analyze`: if not ingested, run ingester; if already ingested, skip upsert path.
- Add lazy process-level runtime clients for Qdrant and embedder service in API layer.
- Add async ingestion bridge (`ingest_document_async`) to avoid sync-over-async embedding calls in FastAPI.
- Map strict ingestion failures to structured API errors (`500 INGESTION_ERROR`).
- Map ingestion `low_quality_document` result to existing `422 LOW_QUALITY_DOCUMENT`.
- Keep parser/orchestrator report shaping behavior unchanged.
- Bound or replace unbounded process cache behavior where needed.

### Acceptance Criteria
- `/analyze` remains synchronous and returns existing response shape.
- Repeated analysis of unchanged docs avoids redundant ingestion work.
- Ingestion path failures map to structured API error handling.
- No request/response schema changes are required for Phase 3 integration.

### Risks
- Latency regression if ingestion always runs and cache checks are weak.
- Mixed source-of-truth behavior if partial integration bypasses new ingestion modules.

### Exit Criteria
- API flow demonstrates ingest-once behavior for same `(doc_id, company_id)`.
- Existing contract tests continue passing after integration.

## Phase 4 - Tenant-Safe Read Path and Security Hardening

### Goal
Enforce tenant isolation and prevent unsafe raw Qdrant read usage.

### Scope
- Add guarded Qdrant read helpers/repository access patterns.
- Apply tenant-filter enforcement in all ingestion retrieval call sites.

### Implementation Tasks
- Implement read helper APIs that require `company_id`.
- Add validation/guard logic preventing unfiltered cross-tenant reads.
- Audit ingestion-related Qdrant queries for mandatory tenant filter.
- Document guardrail policy in ingestion docs.

### Acceptance Criteria
- No ingestion retrieval call can execute without `company_id`.
- Security checks confirm tenant filtering on every read path.

### Risks
- Accidental direct `qdrant_client.search/query_points` usage outside guard helper.
- Incomplete audit leaving one path unfiltered.

### Exit Criteria
- Security review checklist completed with zero missing `company_id` filters.
- Cross-tenant retrieval test attempts return no data leakage.

## Phase 5 - Contract, Docs, and Validation Sync

### Goal
Finalize documentation and verification for stable cross-session operation.

### Scope
- Sync contracts, docs, and tests with implemented behavior.
- Prepare operational handoff artifacts.

### Implementation Tasks
- Update API docs and snapshots reflecting `H -> ISO 45001`.
- Update and run tests covering mappings, ingestion behavior, and tenant guards.
- Record final state, unresolved risks, and next milestones in progress tracker.
- Ensure progress tracker is current for future sessions.

### Acceptance Criteria
- Docs and tests consistently reflect deduplicated `S/H -> ISO 45001`.
- Validation checklist and known risks are explicitly documented.

### Risks
- Documentation drift if code changes are merged without tracker updates.
- Snapshot mismatch if OpenAPI/contracts are not regenerated when needed.

### Exit Criteria
- Phase statuses and artifacts are fully updated in `06 - QHSE Progress.md`.
- MVP ingestion documentation is decision-complete for implementation and handoff.
