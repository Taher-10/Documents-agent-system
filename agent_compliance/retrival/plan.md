M2.2 — Clause Access Layer

**Scope:** `retrieval/norm_normalizer.py`, `retrieval/clause_filter.py`, `retrieval/clause_store.py`

**Prerequisite:** M2.1 done — `data/norms.db` populated.

**Goal:** Three functions that Phase 2 nodes call. All queries are simple indexed SQL — no Qdrant, no aggregation logic (that's already done in the DB).

---

### `retrieval/norm_normalizer.py`

Still needed — converts incoming `applicable_norms` from the API request (`"ISO 9001"`) to the DB key format (`"ISO9001"`).

```python
def normalize_norm_id(norm: str) -> str:
    """'ISO 9001' → 'ISO9001',  'ISO 14001:2015' → 'ISO14001'"""
    norm = norm.upper().replace(" ", "").replace("-", "")
    if ":" in norm:
        norm = norm.split(":")[0]
    return norm
```

---

### `retrieval/clause_filter.py`

Fallback map only. `get_top_level_families()` returns the values that will be matched against the `top_level_family` column in SQLite — catching all requirement clauses at every depth under a given chapter.

```python
SECTION_TYPE_CLAUSE_MAP: dict[str, list[str]] = {
    "METADATA":        ["7.5.2"],
    "SCOPE":           ["4.1", "4.2", "4.3", "5.2"],
    "DEFINITIONS":     ["3", "4.1"],
    "REFERENCES":      ["2"],
    "PROCEDURE_TEXT":  ["6.1", "6.2", "8.1", "8.4", "8.5"],
    "RECORD_FORM":     ["7.5", "9.1", "9.1.1"],
    "PROCESS_DIAGRAM": ["4.4", "8.1"],
    "UNKNOWN":         [],
}

def get_top_level_families(section_type: str) -> list[str]:
    """
    Returns unique top_level_family values for the fallback SQL filter.
    "PROCEDURE_TEXT" → ["6.1","6.2","8.1","8.4","8.5"] → ["6", "8"]
    Matched against iso_clauses.top_level_family — catches all depths (6.1, 6.1.1, 8.4.1, etc.)
    """
    prefixes = SECTION_TYPE_CLAUSE_MAP.get(section_type, [])
    return list(dict.fromkeys(p.split(".")[0] for p in prefixes))
```

---

### `retrieval/clause_store.py`

Three public functions + one private title cleaner. All use `sqlite3` stdlib — no extra dependencies.

```python
import os
import re
import sqlite3
from dataclasses import dataclass
from agent_compliance.retrieval.norm_normalizer import normalize_norm_id
from agent_compliance.retrieval.clause_filter import get_top_level_families

NORMS_DB_PATH = os.getenv("NORMS_DB_PATH", "rag/ingestion_pipeline/output/iso_clauses.db")

@dataclass
class ClauseRecord:
    norm_id:       str    # "ISO9001" — from iso_norms JOIN
    clause_number: str    # "8.4.1"
    clause_title:  str    # cleaned — safe to render directly in LLM prompt
    parent_clause: str    # "8.4"
    text:          str    # full clause text
    language:      str    # "EN" | "FR" — from iso_norms JOIN


def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _clean_title(clause_number: str, raw_title: str) -> str:
    """
    Strips parser noise from clause titles before they reach the LLM menu.
    Order matters: strip markdown first, then tabs, then clause number prefix, then truncate.
    """
    title = re.sub(r"^#+\s*", "", raw_title)   # '### 8.4.1 ...' → '8.4.1 ...'
    title = title.replace("\t", " ").strip()    # '10\tImprovement' → '10 Improvement'
    if title.startswith(clause_number):         # '8.4.1 General' → 'General'
        title = title[len(clause_number):].strip()
    if len(title) > 80:                         # normative bleed — truncate
        title = title[:77] + "..."
    return title or clause_number               # never return empty — fall back to number


def _sort_key(clause_number: str) -> tuple[int, ...]:
    """Numeric sort: '10.2' > '9.3', not '10.2' < '9.3'."""
    try:
        return tuple(int(p) for p in clause_number.split("."))
    except ValueError:
        return (0,)


def _to_record(row: sqlite3.Row) -> ClauseRecord:
    return ClauseRecord(
        norm_id       = row["norm_id"],
        clause_number = row["clause_number"],
        clause_title  = _clean_title(row["clause_number"], row["clause_title"]),
        parent_clause = row["parent_clause"],
        text          = row["text"],
        language      = row["language"],
    )


# Base SELECT used by all three functions — JOIN through iso_norms
_SELECT = (
    "SELECT n.norm_id, n.language, "
    "c.clause_number, c.clause_title, c.parent_clause, c.text "
    "FROM iso_clauses c "
    "JOIN iso_norms n ON c.norm_key = n.norm_key "
)


def load_clause_menu(
    applicable_norms: list[str],
    language: str = "EN",
    db_path: str = NORMS_DB_PATH,
) -> dict[str, list[tuple[str, str]]]:
    """
    Returns {norm_id: [(clause_number, cleaned_title), ...]}
    Requirement clauses only, sorted in ISO numeric order.
    """
    norm_ids = [normalize_norm_id(n) for n in applicable_norms]
    ph = ",".join("?" * len(norm_ids))
    rows = _conn(db_path).execute(
        _SELECT + f"WHERE n.norm_id IN ({ph}) AND n.language = ? AND c.has_requirements = 1",
        norm_ids + [language],
    ).fetchall()
    menu: dict[str, list] = {}
    for row in rows:
        title = _clean_title(row["clause_number"], row["clause_title"])
        menu.setdefault(row["norm_id"], []).append((row["clause_number"], title))
    for norm_id in menu:
        menu[norm_id].sort(key=lambda pair: _sort_key(pair[0]))
    return menu


def fetch_clauses_by_ids(
    clause_ids: list[str],
    applicable_norms: list[str],
    language: str = "EN",
    db_path: str = NORMS_DB_PATH,
) -> list[ClauseRecord]:
    """Fetches full clause records by clause_number. Returns [] for unknown IDs — no crash."""
    if not clause_ids:
        return []
    norm_ids   = [normalize_norm_id(n) for n in applicable_norms]
    ph_norms   = ",".join("?" * len(norm_ids))
    ph_clauses = ",".join("?" * len(clause_ids))
    rows = _conn(db_path).execute(
        _SELECT + f"WHERE n.norm_id IN ({ph_norms}) AND n.language = ? "
                  f"AND c.clause_number IN ({ph_clauses})",
        norm_ids + [language] + clause_ids,
    ).fetchall()
    return [_to_record(r) for r in rows]


def fetch_clauses_by_section_type(
    section_type: str,
    applicable_norms: list[str],
    language: str = "EN",
    db_path: str = NORMS_DB_PATH,
) -> list[ClauseRecord]:
    """
    Fallback: all requirement clauses under top-level families for a SectionType.
    Uses top_level_family — catches all depths (6.1, 6.1.1, 8.4.1, etc.).
    """
    families = get_top_level_families(section_type)
    if not families:
        return []
    norm_ids    = [normalize_norm_id(n) for n in applicable_norms]
    ph_norms    = ",".join("?" * len(norm_ids))
    ph_families = ",".join("?" * len(families))
    rows = _conn(db_path).execute(
        _SELECT + f"WHERE n.norm_id IN ({ph_norms}) AND n.language = ? "
                  f"AND c.top_level_family IN ({ph_families}) AND c.has_requirements = 1",
        norm_ids + [language] + families,
    ).fetchall()
    return [_to_record(r) for r in rows]
```

> [!note] Thread safety
> `check_same_thread=False` allows the connection to be used from the thread pool spun up by `run_in_executor` in FastAPI. Each call opens its own connection — SQLite handles concurrent reads safely.

**Done condition:**
- `load_clause_menu(["ISO 9001"])` → `{"ISO9001": [("4.1", "Understanding the organization..."), ...]}` — titles clean, no `#` or `\t`, sorted numerically (`4.1` before `10.1`)
- `fetch_clauses_by_ids(["8.4.1", "9.2.1"], ["ISO 9001"])` → 2 `ClauseRecord` objects, `text` non-empty
- `fetch_clauses_by_ids(["8.4.99"], ["ISO 9001"])` → `[]`, no exception
- `fetch_clauses_by_section_type("PROCEDURE_TEXT", ["ISO 9001"])` → records include `8.4.1`, `8.5.1`, `6.1.1` (all depths, not just level-1)