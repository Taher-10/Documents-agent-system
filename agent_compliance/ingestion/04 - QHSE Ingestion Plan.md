---
tags: [plan, ingestion, phase-1, qdrant, qhse]
created: 2026-04-23
status: 🟡 in-progress
parent: "[[00 - Home]]"
---

# QHSE Document Ingestion — Implementation Plan

> [!info] Related
> Architecture: [[01 - Architecture]] · Progress: [[02 - Progress Tracker]] · Parser: [[parser-summary-for-compliance]] · Codebase: [[03 - Codebase Structure]]

---

## Context & Decisions

### What we learned from prerequisites

| Question        | Answer                                                              |
| --------------- | ------------------------------------------------------------------- |
| Metadata source | PostgreSQL database — `InternalDocs` table                          |
| Norm flags      | Boolean columns `Q`, `S`, `E`, `H` on each document                 |
| Doc types       | `IniTypesDesignation` enum (26 types, French labels)                |
| Domains         | `IniDomainsDesignation` enum (functional domains, not norm domains) |
| Qdrant          | Local Docker · ISO collection = `norms`                             |
| Embedding model | **Qwen3-Embedding** (same model as `norms` collection — mandatory)  |
| Documents       | On-demand (user triggers per document) · PDF + DOCX                 |
| Platform        | Multi-tenant web app — `CompanyId` + `SiteId` per document          |
| Repo structure  | `agent_2/` (agent logic) · `rag/` (ISO ingestion + retrieval)       |

---

## Decisions — Confirmed ✅

> [!check] All 3 questions answered
>
> **Q1 — `H` flag → Health** maps to **ISO 45001** (covers Occupational Health & Safety).
> `S` (Safety) and `H` (Health) both map to ISO 45001 — deduplicated at derivation time.
>
> **Q2 — Multi-tenancy → Option A confirmed** (single collection + mandatory `company_id` filter).
> Security is enforced at the **application layer**: every Qdrant query MUST include `company_id` filter.
> This is a hard rule — see security note below.
>
> **Q3 — Module location → `agent_2/`** because QHSE parsing is live (on-demand), not offline.
> `rag/` stays ISO-only (offline). QHSE ingestion is part of the agent trigger flow.

---

## Architecture of the Ingestion Pipeline

```
QALITAS sends POST /analyze
  { session: { company_id, site_id, user_id },
    document: { id, code, type_designation, Q/E/S/H, file_path, ... } }
        │
        ▼
DocumentMeta.from_request(doc, session)
        │  maps type_designation → doc_type + doc_level
        │  maps Q/E/S/H → applicable_norms
        ▼
DocumentMeta (dataclass)
        │
        ├──────────────────────────────┐
        ▼                              ▼
parse_document(FilePath)        validation checks
docling_to_sections()           (tier, confidence)
        │
        ▼
list[ParsedSection]
  filter: confidence ≥ 0.6
  filter: tier != "C"
        │
        ▼
build_qdrant_payload(section, meta)
        │
        ▼
Qdrant upsert → collection: qhse_sections
  vector: embed(section.raw_text)   ← Qwen3-Embedding
  payload: section fields + meta fields
```

---

## Type → Level Mapping

Derived from `IniTypesDesignation` — no manual entry needed.

```python
TYPE_LEVEL_MAP = {
    # Level 1 — Strategic
    "Politique qualité":           ("policy",           1),
    # Level 2 — System
    "Manuel Qualité":              ("manual",           2),
    "Plan Qualité":                ("manual",           2),
    "Fiche Descriptive d'un Processus": ("process_sheet", 2),
    # Level 3 — Operational
    "Procédure":                   ("procedure",        3),
    "Document":                    ("document",         3),
    "Document Production":         ("document",         3),
    "Fiche Technique":             ("technical_sheet",  3),
    "Liste":                       ("list",             3),
    "Norme":                       ("norm_ref",         3),
    "Loi":                         ("regulation",       3),
    "Gamme":                       ("routing",          3),
    "Gamme accessoires":           ("routing",          3),
    "Gamme barre stabilisatrice":  ("routing",          3),
    # Level 4 — Instructions
    "Instruction":                 ("work_instruction", 4),
    "Mode opératoire":             ("work_instruction", 4),
    "Fiche Fonction":              ("job_sheet",        4),
    "Plan accessoires":            ("plan",             4),
    "Plan outillage":              ("plan",             4),
    "Plan de définition accessoires": ("plan",          4),
    "Plan de définition outillage":   ("plan",          4),
    "Projets":                     ("project",          4),
    # Level 5 — Records
    "Formulaire":                  ("form",             5),
    "Fiche":                       ("form",             5),
    "Document d'enregistrement":   ("record",           5),
    # Unknown
    "AUCUN":                       ("unknown",          0),
}
```

---

## Norm Flag → ISO Norm Mapping

```python
NORM_FLAG_MAP = {
    "Q": "ISO 9001",
    "E": "ISO 14001",
    "S": "ISO 45001",
    "H": "ISO 45001",   # Health → same standard as Safety, deduplicated below
}

def derive_norms(row: dict) -> list[str]:
    norms = {
        NORM_FLAG_MAP[flag]
        for flag in ("Q", "E", "S", "H")
        if row.get(flag) is True
    }
    return sorted(norms)   # set deduplicates S+H collision
    # e.g. Q=True, H=True, S=True → ["ISO 45001"] (not duplicated)
    # e.g. Q=True, E=True         → ["ISO 14001", "ISO 9001"]
```

---

## Module Structure (in `agent_2/`)

QHSE ingestion is **live and on-demand** → lives in `agent_2/`, not `rag/`.
`rag/` remains ISO-only (offline pipeline).

```
agent_2/
├── ingestion/
│   ├── __init__.py
│   ├── document_meta.py         ← DocumentMeta dataclass + from_request() (no DB access)
│   ├── type_mappings.py         ← TYPE_LEVEL_MAP (26 types) + NORM_FLAG_MAP + derive_norms()
│   ├── payload_builder.py       ← builds Qdrant payload from section + meta
│   ├── qhse_ingester.py         ← ingest_document() — parse + embed + upsert
│   └── utils.py                 ← stable_uuid(doc_id, section_id) → uuid5
└── (agent graph, nodes, state...)

rag/
└── (ISO ingestion only — offline, unchanged)
```

> [!note] Why separate?
> `rag/` ingests ISO norms once, offline, from PDFs.
> `agent_2/ingestion/` ingests client documents live, triggered per user action.
> Different lifecycles, different triggers — keep them separate.

> [!info] Ownership of `DocumentMeta`
> `DocumentMeta` is an **ingestion domain object** — it lives in `agent_2/ingestion/`, not in the API layer.
> The API layer builds it via `from_request()` then passes it to the ingestion pipeline.
> The API layer has no other dependency on ingestion internals.
> `api/document_meta.py` is a temporary placeholder — deleted once this module is built.

---

## Data Contracts

### `DocumentMeta` dataclass — `document_meta.py`

```python
@dataclass
class DocumentMeta:
    doc_id:           str        # InternalDocs.Id (UUID)
    doc_code:         str        # InternalDocs.Code  e.g. "PRO-ENV-001"
    designation:      str        # InternalDocs.Designation (title)
    version:          str        # InternalDocs."Index"
    file_path:        str        # InternalDocs.FilePath
    doc_type:         str        # derived from TypesId → TYPE_LEVEL_MAP
    doc_level:        int        # derived from TypesId → TYPE_LEVEL_MAP
    applicable_norms: list[str]  # derived from Q/S/E/H flags
    company_id:       str        # InternalDocs.CompanyId  ← tenant isolation
    site_id:          str        # InternalDocs.SiteId

    @classmethod
    def from_request(cls, doc: dict, session: dict) -> "DocumentMeta":
        # QALITAS sends the metadata — agent never queries DB directly
        type_label = doc["type_designation"]   # resolved string, not UUID
        doc_type, doc_level = TYPE_LEVEL_MAP.get(type_label, ("unknown", 0))
        return cls(
            doc_id           = doc["id"],
            doc_code         = doc["code"],
            designation      = doc["designation"],
            version          = doc["version"],
            file_path        = doc["file_path"],
            doc_type         = doc_type,
            doc_level        = doc_level,
            applicable_norms = derive_norms(doc),
            company_id       = session["company_id"],
            site_id          = session["site_id"],
        )
```

---

### Qdrant Payload — `payload_builder.py`

```python
def build_payload(section: ParsedSection, meta: DocumentMeta, result: ParseResult) -> dict:
    return {
        # --- Section fields ---
        "section_id":            section.id,
        "section_type":          section.section_type.value,
        "title":                 section.title,
        "raw_text":              section.raw_text,
        "heading_level":         section.heading_level,
        "page_start":            section.page_range[0],
        "page_end":              section.page_range[1],
        "extraction_confidence": section.extraction_confidence,

        # --- Document fields (from ParseResult) ---
        "doc_title":    result.title,
        "doc_pages":    result.pages,
        "page1_fields": result.metadata.get("page1_fields", {}),

        # --- DocumentMeta fields ---
        "doc_id":           meta.doc_id,
        "doc_code":         meta.doc_code,
        "designation":      meta.designation,
        "version":          meta.version,
        "doc_type":         meta.doc_type,
        "doc_level":        meta.doc_level,
        "applicable_norms": meta.applicable_norms,

        # --- Tenant isolation ---
        "company_id":  meta.company_id,
        "site_id":     meta.site_id,
    }
```

---

### Main Function — `qhse_ingester.py`

```python
def ingest_document(
    meta: DocumentMeta,
    qdrant_client: QdrantClient,
    embed_fn: Callable[[str], list[float]],
    collection: str = "qhse_sections",
) -> IngestResult:
    """
    Parse + embed + upsert one QHSE document into Qdrant.
    Returns count of sections ingested and any skipped sections.
    """
    # 1. Parse
    result   = parse_document(meta.file_path)
    sections = docling_to_sections(result)
    tier, min_conf, low_flag = assess_quality(sections)

    if tier == "C":
        return IngestResult(ingested=0, skipped=len(sections), reason="low_quality_document")

    # 2. Filter + embed + upsert
    points = []
    skipped = 0
    for section in sections:
        if section.extraction_confidence < 0.6:
            skipped += 1
            continue

        vector  = embed_fn(section.raw_text)
        payload = build_payload(section, meta, result)

        points.append(PointStruct(
            id      = stable_uuid(meta.doc_id, section.id),
            vector  = vector,
            payload = payload,
        ))

    qdrant_client.upsert(collection_name=collection, points=points)

    return IngestResult(ingested=len(points), skipped=skipped)
```

---

## Qdrant Collection Setup

```python
# Run once — creates the collection
qdrant_client.create_collection(
    collection_name = "qhse_sections",
    vectors_config  = VectorsConfig(
        size     = 1024,      # Qwen3-Embedding ✅ confirmed
        distance = Distance.COSINE,
    )
)

# Payload indexes for filtering
qdrant_client.create_payload_index("qhse_sections", "company_id",   PayloadSchemaType.KEYWORD)
qdrant_client.create_payload_index("qhse_sections", "site_id",      PayloadSchemaType.KEYWORD)
qdrant_client.create_payload_index("qhse_sections", "section_type", PayloadSchemaType.KEYWORD)
qdrant_client.create_payload_index("qhse_sections", "doc_type",     PayloadSchemaType.KEYWORD)
qdrant_client.create_payload_index("qhse_sections", "doc_level",    PayloadSchemaType.INTEGER)
```

---

## Multi-Tenancy: Data Security

> [!danger] Security Rule — Never Bypass
> **Every single Qdrant query must include `company_id` as a mandatory filter.**
> This is the only mechanism preventing cross-client data access.
> There is no infrastructure-level wall — the application layer IS the wall.

### How isolation works in practice

```python
# CORRECT — always pass company_id
qdrant_client.search(
    collection_name = "qhse_sections",
    query_vector    = embed_fn(query_text),
    query_filter    = Filter(must=[
        FieldCondition(key="company_id", match=MatchValue(value=current_company_id)),
        FieldCondition(key="section_type", match=MatchValue(value="PROCEDURE_TEXT")),
    ]),
    limit = 5
)

# WRONG — never do this (exposes all clients' data)
qdrant_client.search(
    collection_name = "qhse_sections",
    query_vector    = embed_fn(query_text),
    limit = 5
)
```

### Where `company_id` comes from at runtime

```
Web request → authenticated user session
                    ↓
             user.company_id  ← from auth token / session
                    ↓
             passed into ComplianceState
                    ↓
             every Qdrant call reads it from state
```

`company_id` must be on `ComplianceState` and passed to every retrieval function.
It is **never** taken from the document payload itself — always from the authenticated session.

---

## On-Demand Trigger Flow (Live — in agent_2)

Ingestion is part of the agent startup — not a separate offline job.

```
QALITAS: POST /analyze  { session, document }   ← QALITAS already has the DB row
        ↓
DocumentMeta.from_request(doc, session)         ← no DB query, data is in request
        ↓
Check Qdrant: is doc_id already ingested?
        │
        ├── YES → skip ingestion, use cached sections
        │
        └── NO  → ingest_document(meta, qdrant_client, embed_fn)
                        parse file_path → filter → embed → upsert
        ↓
Build ComplianceState (doc_id + company_id + applicable_norms)
        ↓
LangGraph: loader node reads sections from Qdrant by doc_id + company_id
        ↓
ReAct Mapper runs
        ↓
JSON report returned to QALITAS
```

> [!note] Cache check
> Before parsing, check if `doc_id` already has sections in Qdrant.
> If yes — skip re-parsing. This avoids re-ingesting unchanged documents
> and makes repeat analyses fast.

---

## Build Order

```
Step 1  type_mappings.py        → TYPE_LEVEL_MAP + NORM_FLAG_MAP (after Q1 confirmed)
Step 2  document_meta.py        → DocumentMeta dataclass + from_db_row()
Step 3  payload_builder.py      → build_payload()
Step 4  Qdrant collection setup → create collection + indexes (after Q2 confirmed)
Step 5  qhse_ingester.py        → ingest_document() + IngestResult
Step 6  integration test        → ingest one real document, verify in Qdrant
```

---

## Checklist

- [x] Q1: `H` = Health → ISO 45001 (deduplicated with S)
- [x] Q2: single collection + mandatory `company_id` filter
- [x] Q3: module in `agent_2/ingestion/`
- [x] Qwen3-Embedding output vector size = **1024**
- [ ] `type_mappings.py` written
- [ ] `document_meta.py` written
- [ ] `payload_builder.py` written
- [ ] Qdrant `qhse_sections` collection created + indexes
- [ ] `qhse_ingester.py` written (with cache check)
- [ ] Security review: every Qdrant call has `company_id` filter
- [ ] Integration test: 1 document ingested, verified in Qdrant

---

*Back to [[00 - Home]] · [[02 - Progress Tracker]]*
