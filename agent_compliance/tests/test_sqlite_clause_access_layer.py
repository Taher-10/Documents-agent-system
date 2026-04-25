from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent_compliance.retrieval.clause_filter import get_top_level_families
from agent_compliance.retrieval.clause_store import (
    ClauseRecord,
    fetch_clauses_by_ids,
    fetch_clauses_by_section_type,
    load_clause_menu,
)
from agent_compliance.retrieval.norm_normalizer import normalize_norm_id


def _seed_registry_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE iso_norms (
                norm_key      TEXT PRIMARY KEY,
                norm_id       TEXT NOT NULL,
                norm_version  TEXT NOT NULL DEFAULT '',
                language      TEXT NOT NULL DEFAULT 'EN',
                norm_full     TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(norm_id, norm_version, language)
            );

            CREATE TABLE iso_clauses (
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
            """
        )

        conn.executemany(
            """
            INSERT INTO iso_norms (norm_key, norm_id, norm_version, language, norm_full)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("k_9001_en_2015", "ISO9001", "2015", "EN", "ISO 9001:2015"),
                ("k_9001_fr_2015", "ISO9001", "2015", "FR", "ISO 9001:2015"),
            ],
        )

        conn.executemany(
            """
            INSERT INTO iso_clauses (
                norm_key, norm_id, norm_version, language, clause_number, clause_title,
                parent_clause, top_level_family, text, has_requirements
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "k_9001_en_2015",
                    "ISO9001",
                    "2015",
                    "EN",
                    "4.1",
                    "### 4.1 Understanding\torganization context",
                    "4",
                    "4",
                    "Context text.",
                    1,
                ),
                (
                    "k_9001_en_2015",
                    "ISO9001",
                    "2015",
                    "EN",
                    "6.1.1",
                    "6.1.1 Risk and opportunities",
                    "6.1",
                    "6",
                    "Risk planning text.",
                    1,
                ),
                (
                    "k_9001_en_2015",
                    "ISO9001",
                    "2015",
                    "EN",
                    "7.2",
                    "7.2 Competence",
                    "7",
                    "7",
                    "Competence text.",
                    0,
                ),
                (
                    "k_9001_en_2015",
                    "ISO9001",
                    "2015",
                    "EN",
                    "8.4.1",
                    "8.4.1 External control",
                    "8.4",
                    "8",
                    "Supplier control text.",
                    1,
                ),
                (
                    "k_9001_en_2015",
                    "ISO9001",
                    "2015",
                    "EN",
                    "8.5.1",
                    "8.5.1",
                    "8.5",
                    "8",
                    "Production control text.",
                    1,
                ),
                (
                    "k_9001_en_2015",
                    "ISO9001",
                    "2015",
                    "EN",
                    "9.2.1",
                    "9.2.1 Internal audit",
                    "9.2",
                    "9",
                    "Audit text.",
                    1,
                ),
                (
                    "k_9001_en_2015",
                    "ISO9001",
                    "2015",
                    "EN",
                    "10.1",
                    "10.1 General",
                    "10",
                    "10",
                    "Improvement text.",
                    1,
                ),
                (
                    "k_9001_fr_2015",
                    "ISO9001",
                    "2015",
                    "FR",
                    "4.1",
                    "4.1 Contexte",
                    "4",
                    "4",
                    "Texte FR.",
                    1,
                ),
            ],
        )


@pytest.fixture()
def sqlite_registry_path(tmp_path: Path) -> str:
    db_path = tmp_path / "iso_clauses.db"
    _seed_registry_db(db_path)
    return str(db_path)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("ISO 9001", "ISO9001"), ("ISO 14001:2015", "ISO14001")],
)
def test_normalize_norm_id(raw: str, expected: str) -> None:
    assert normalize_norm_id(raw) == expected


def test_get_top_level_families_normalized_input() -> None:
    expected = ["6", "8"]
    assert get_top_level_families("PROCEDURE_TEXT") == expected
    assert get_top_level_families("procedure_text") == expected
    assert get_top_level_families("SectionType.PROCEDURE_TEXT") == expected
    assert get_top_level_families("unknown_section") == []


def test_load_clause_menu_requirement_only_sorted_and_clean_titles(sqlite_registry_path: str) -> None:
    menu = load_clause_menu(["ISO 9001"], language="EN", db_path=sqlite_registry_path)

    assert list(menu.keys()) == ["ISO9001"]
    clause_numbers = [number for number, _ in menu["ISO9001"]]

    assert "7.2" not in clause_numbers
    assert clause_numbers == ["4.1", "6.1.1", "8.4.1", "8.5.1", "9.2.1", "10.1"]

    title_by_clause = dict(menu["ISO9001"])
    assert title_by_clause["4.1"] == "Understanding organization context"
    assert "#" not in title_by_clause["4.1"]
    assert "\t" not in title_by_clause["4.1"]
    assert title_by_clause["8.5.1"] == "8.5.1"


def test_fetch_clauses_by_ids_returns_records_and_handles_missing(sqlite_registry_path: str) -> None:
    records = fetch_clauses_by_ids(
        ["8.4.1", "9.2.1"],
        ["ISO 9001"],
        language="EN",
        db_path=sqlite_registry_path,
    )

    assert len(records) == 2
    assert all(isinstance(item, ClauseRecord) for item in records)
    assert {item.clause_number for item in records} == {"8.4.1", "9.2.1"}
    assert all(item.text for item in records)

    assert fetch_clauses_by_ids(
        ["8.4.99"],
        ["ISO 9001"],
        language="EN",
        db_path=sqlite_registry_path,
    ) == []
    assert fetch_clauses_by_ids([], ["ISO 9001"], db_path=sqlite_registry_path) == []


def test_fetch_clauses_by_section_type_uses_top_level_family(sqlite_registry_path: str) -> None:
    records = fetch_clauses_by_section_type(
        "PROCEDURE_TEXT",
        ["ISO 9001"],
        language="EN",
        db_path=sqlite_registry_path,
    )
    clause_numbers = {item.clause_number for item in records}

    assert {"6.1.1", "8.4.1", "8.5.1"}.issubset(clause_numbers)
    assert "9.2.1" not in clause_numbers

    lower_case_records = fetch_clauses_by_section_type(
        "procedure_text",
        ["ISO 9001"],
        language="EN",
        db_path=sqlite_registry_path,
    )
    assert {item.clause_number for item in lower_case_records} == clause_numbers
    assert fetch_clauses_by_section_type(
        "not_mapped",
        ["ISO 9001"],
        db_path=sqlite_registry_path,
    ) == []
