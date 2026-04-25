"""SQLite-backed clause access functions for Agent Compliance."""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass

from agent_compliance.retrieval.clause_filter import get_top_level_families
from agent_compliance.retrieval.norm_normalizer import normalize_norm_id

NORMS_DB_PATH = os.getenv("NORMS_DB_PATH", "agent_compliance/data/iso_clauses.db")


@dataclass(slots=True)
class ClauseRecord:
    norm_id: str
    clause_number: str
    clause_title: str
    parent_clause: str
    text: str
    language: str


def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _clean_title(clause_number: str, raw_title: str) -> str:
    title = re.sub(r"^#+\s*", "", raw_title or "")
    title = title.replace("\t", " ").strip()
    if title.startswith(clause_number):
        title = title[len(clause_number):].strip(" .:-")
    if len(title) > 80:
        title = title[:77] + "..."
    return title or clause_number


def _sort_key(clause_number: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in clause_number.split("."):
        match = re.match(r"\d+", part)
        parts.append(int(match.group()) if match else 0)
    return tuple(parts) if parts else (0,)


def _to_record(row: sqlite3.Row) -> ClauseRecord:
    return ClauseRecord(
        norm_id=row["norm_id"],
        clause_number=row["clause_number"],
        clause_title=_clean_title(row["clause_number"], row["clause_title"]),
        parent_clause=row["parent_clause"],
        text=row["text"],
        language=row["language"],
    )


def _normalize_norms(applicable_norms: list[str]) -> list[str]:
    seen: set[str] = set()
    norm_ids: list[str] = []
    for norm in applicable_norms:
        normalized = normalize_norm_id(norm)
        if normalized and normalized not in seen:
            seen.add(normalized)
            norm_ids.append(normalized)
    return norm_ids


def _rows(db_path: str, query: str, params: list[str]) -> list[sqlite3.Row]:
    with closing(_conn(db_path)) as conn:
        return conn.execute(query, params).fetchall()


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
    """Return requirement-only menu rows grouped by norm."""
    norm_ids = _normalize_norms(applicable_norms)
    if not norm_ids:
        return {}

    placeholders = ",".join("?" * len(norm_ids))
    query = (
        _SELECT
        + f"WHERE n.norm_id IN ({placeholders}) "
        "AND n.language = ? AND c.has_requirements = 1"
    )
    rows = _rows(db_path, query, norm_ids + [language.upper()])

    menu: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        menu.setdefault(row["norm_id"], []).append(
            (row["clause_number"], _clean_title(row["clause_number"], row["clause_title"]))
        )

    for norm_id in menu:
        menu[norm_id].sort(key=lambda pair: _sort_key(pair[0]))
    return menu


def fetch_clauses_by_ids(
    clause_ids: list[str],
    applicable_norms: list[str],
    language: str = "EN",
    db_path: str = NORMS_DB_PATH,
) -> list[ClauseRecord]:
    """Fetch full clause records by clause number."""
    normalized_clause_ids = [item.strip() for item in clause_ids if item and item.strip()]
    if not normalized_clause_ids:
        return []

    norm_ids = _normalize_norms(applicable_norms)
    if not norm_ids:
        return []

    norm_ph = ",".join("?" * len(norm_ids))
    clause_ph = ",".join("?" * len(normalized_clause_ids))
    query = (
        _SELECT
        + f"WHERE n.norm_id IN ({norm_ph}) "
        "AND n.language = ? "
        f"AND c.clause_number IN ({clause_ph})"
    )
    rows = _rows(db_path, query, norm_ids + [language.upper()] + normalized_clause_ids)

    records = [_to_record(row) for row in rows]
    records.sort(key=lambda item: (item.norm_id, _sort_key(item.clause_number)))
    return records


def fetch_clauses_by_section_type(
    section_type: str,
    applicable_norms: list[str],
    language: str = "EN",
    db_path: str = NORMS_DB_PATH,
) -> list[ClauseRecord]:
    """Fallback fetch for requirement clauses under mapped top-level families."""
    families = get_top_level_families(section_type)
    if not families:
        return []

    norm_ids = _normalize_norms(applicable_norms)
    if not norm_ids:
        return []

    norm_ph = ",".join("?" * len(norm_ids))
    family_ph = ",".join("?" * len(families))
    query = (
        _SELECT
        + f"WHERE n.norm_id IN ({norm_ph}) "
        "AND n.language = ? "
        f"AND c.top_level_family IN ({family_ph}) "
        "AND c.has_requirements = 1"
    )
    rows = _rows(db_path, query, norm_ids + [language.upper()] + families)

    records = [_to_record(row) for row in rows]
    records.sort(key=lambda item: (item.norm_id, _sort_key(item.clause_number)))
    return records
