# SQLite Registry DB and Adapter

This document describes the persistent SQLite database used by the ingestion pipeline and the registry adapter that writes to it.

---

## 1. Purpose

The SQLite registry is the durable clause store for ingested ISO norms.

It supports:
- Multi-norm storage (e.g., ISO9001, ISO14001)
- Multi-language storage for the same norm/version (e.g., EN and FR)
- Add-only ingestion mode (no overwrite)
- Controlled overwrite mode
- Norm-level deletion with cascade to clauses

---

## 2. Canonical DB Location

Default canonical path:

`/Users/mohamed_taher/Desktop/Documents agent system/agent_compliance/data/iso_clauses.db`

In code, this is resolved by:
- `pipeline._default_sqlite_registry_path()`
- `segment(..., sqlite_registry_enabled=True, ...)`

Even if another filename is provided (for example `iso_norms.db`), the adapter canonicalizes to `iso_clauses.db` in the same directory.

---

## 3. Registry Adapter Entry Points

Main writer:
- `registry.write_sqlite_clause_registry(result, db_path, if_exists)`

Norm delete API:
- `registry.delete_norm_from_sqlite_registry(db_path, norm_id, norm_version, language)`

Pipeline integration:
- `pipeline.segment(..., sqlite_registry_enabled, sqlite_db_path, sqlite_if_exists)`

---

## 4. Schema

### `iso_norms`

One row per norm identity `(norm_id, norm_version, language)`.

```sql
CREATE TABLE IF NOT EXISTS iso_norms (
    norm_key      TEXT PRIMARY KEY,
    norm_id       TEXT NOT NULL,
    norm_version  TEXT NOT NULL DEFAULT '',
    language      TEXT NOT NULL DEFAULT 'EN',
    norm_full     TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(norm_id, norm_version, language)
);
```

### `iso_clauses`

One row per clause per norm identity.

```sql
CREATE TABLE IF NOT EXISTS iso_clauses (
    norm_key          TEXT NOT NULL,
    norm_id           TEXT NOT NULL,
    norm_version      TEXT NOT NULL DEFAULT '',
    language          TEXT NOT NULL DEFAULT 'EN',
    clause_number     TEXT NOT NULL,
    clause_title      TEXT NOT NULL,
    parent_clause     TEXT NOT NULL,
    top_level_family  TEXT NOT NULL DEFAULT '',
    text              TEXT NOT NULL,
    has_requirements  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (norm_key, clause_number),
    FOREIGN KEY (norm_key) REFERENCES iso_norms(norm_key) ON DELETE CASCADE
);
```

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_iso_norm_identity
    ON iso_norms(norm_id, norm_version, language);
CREATE INDEX IF NOT EXISTS idx_clause_norm_key
    ON iso_clauses(norm_key);
CREATE INDEX IF NOT EXISTS idx_clause_norm_id
    ON iso_clauses(norm_id);
CREATE INDEX IF NOT EXISTS idx_clause_family
    ON iso_clauses(norm_id, top_level_family);
```

---

## 5. How Clause Rows Are Built

The adapter aggregates chunk-level output into one clause row:

- Group key: `clause_number` (within one norm identity)
- `text`: concatenation of all chunk parts ordered by `(chunk_index, page_number, chunk_id)`
- `has_requirements`: `1` if any chunk part has requirements, else `0`
- `top_level_family`: from `chunk.clause_family` (fallback: prefix of `clause_number`)
- `clause_title`: if title is blank or only clause number, fallback to first 80 chars of clause text

This improves downstream LLM context for clauses like `4.4.1`, `6.1.1`, `8.7.1`.

---

## 6. `if_exists` Modes

`write_sqlite_clause_registry(..., if_exists=...)` supports:

- `skip` (default): if norm identity exists, insert `0` rows and keep existing data
- `upsert`: replace clause rows for that norm identity
- `error`: raise runtime error if norm identity already exists

Norm identity is: `(norm_id, norm_version, language)`.

---

## 7. Migration and Path Normalization

The adapter handles:

1. Legacy single-table schema migration (`iso_clauses` old shape) into new `iso_norms + iso_clauses`.
2. Alias DB merge:
   - If `iso_norms.db` exists in the same directory, its data is merged into canonical `iso_clauses.db`.
   - Alias file is removed after successful merge.
3. Canonical filename enforcement:
   - Any requested DB path is normalized to `<directory>/iso_clauses.db`.

---

## 8. Environment Variables

- `SQLITE_REGISTRY_ENABLED=true|false`
- `SQLITE_REGISTRY_PATH=/path/to/dir/iso_clauses.db` (directory is respected, filename canonicalized)
- `SQLITE_REGISTRY_IF_EXISTS=skip|upsert|error`

---

## 9. Operational Queries

List norms:

```sql
SELECT norm_id, norm_version, language, norm_key
FROM iso_norms
ORDER BY norm_id, norm_version, language;
```

Clause counts by norm identity:

```sql
SELECT norm_id, norm_version, language, COUNT(*) AS clauses
FROM iso_clauses
GROUP BY norm_id, norm_version, language
ORDER BY norm_id, norm_version, language;
```

Read clauses for one norm identity:

```sql
SELECT clause_number, top_level_family, clause_title, has_requirements
FROM iso_clauses
WHERE norm_id='ISO9001' AND norm_version='2015' AND language='FR'
ORDER BY clause_number;
```

Delete one norm identity (from application API, preferred):

```python
from rag.ingestion_pipeline.registry import delete_norm_from_sqlite_registry

delete_norm_from_sqlite_registry(
    db_path="/Users/mohamed_taher/Desktop/Documents agent system/agent_compliance/data/iso_clauses.db",
    norm_id="ISO9001",
    norm_version="2015",
    language="FR",
)
```

Equivalent SQL:

```sql
DELETE FROM iso_norms
WHERE norm_id='ISO9001' AND norm_version='2015' AND language='FR';
```

`iso_clauses` rows are removed automatically by cascade.

