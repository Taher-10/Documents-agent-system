from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from agent_compliance.retrieval.clause_store import (
    fetch_clauses_by_ids,
    fetch_clauses_by_section_type,
    load_clause_menu,
)

LIVE_DB_PATH = Path("agent_compliance/data/iso_clauses.db")


@pytest.fixture(scope="module")
def live_db_path() -> str:
    if not LIVE_DB_PATH.exists():
        pytest.skip(f"Live DB not found: {LIVE_DB_PATH}")
    return str(LIVE_DB_PATH)


def _sort_key(clause_number: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in clause_number.split("."):
        digits = ""
        for char in part:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def test_live_language_isolation_en_vs_fr(live_db_path: str) -> None:
    en = fetch_clauses_by_ids(["4.1"], ["ISO 9001"], language="EN", db_path=live_db_path)
    fr = fetch_clauses_by_ids(["4.1"], ["ISO 9001"], language="FR", db_path=live_db_path)

    assert len(en) == 1
    assert len(fr) == 1
    assert en[0].language == "EN"
    assert fr[0].language == "FR"
    assert en[0].text != fr[0].text


def test_live_multi_norm_menu_fr(live_db_path: str) -> None:
    menu = load_clause_menu(["ISO 9001", "ISO 14001"], language="FR", db_path=live_db_path)
    assert set(menu.keys()) == {"ISO9001", "ISO14001"}
    assert len(menu["ISO9001"]) > 0
    assert len(menu["ISO14001"]) > 0


def test_live_input_guards(live_db_path: str) -> None:
    assert load_clause_menu([], db_path=live_db_path) == {}
    assert fetch_clauses_by_ids([], ["ISO 9001"], db_path=live_db_path) == []
    assert fetch_clauses_by_ids(["   ", ""], ["ISO 9001"], db_path=live_db_path) == []
    assert fetch_clauses_by_section_type("no_match", ["ISO 9001"], db_path=live_db_path) == []


def test_live_title_cleaning_and_truncation(live_db_path: str) -> None:
    records = fetch_clauses_by_ids(
        ["4.4.1", "4.4.2", "9.2.1"],
        ["ISO 9001"],
        language="EN",
        db_path=live_db_path,
    )
    by_id = {item.clause_number: item for item in records}

    assert "4.4.1" in by_id
    assert "4.4.2" in by_id
    assert "9.2.1" in by_id

    assert "#" not in by_id["4.4.1"].clause_title
    assert "#" not in by_id["4.4.2"].clause_title
    assert "\t" not in by_id["4.4.1"].clause_title
    assert len(by_id["9.2.1"].clause_title) <= 80


def test_live_numeric_sort_edge_cases(live_db_path: str) -> None:
    menu = load_clause_menu(["ISO 9001"], language="EN", db_path=live_db_path)
    rows = menu["ISO9001"]
    clause_numbers = [clause for clause, _ in rows]

    assert clause_numbers == sorted(clause_numbers, key=_sort_key)
    assert clause_numbers.index("10.1") > clause_numbers.index("9.2.1")
    assert sorted(["4.4.2", "4.4.10", "4.4.1"], key=_sort_key) == ["4.4.1", "4.4.2", "4.4.10"]


def test_live_sql_injection_string_does_not_expand_results(live_db_path: str) -> None:
    baseline = fetch_clauses_by_ids(["8.4.1"], ["ISO 9001"], language="EN", db_path=live_db_path)
    injected = fetch_clauses_by_ids(
        ["8.4.1' OR 1=1 --"],
        ["ISO 9001"],
        language="EN",
        db_path=live_db_path,
    )

    assert len(baseline) == 1
    assert injected == []


def test_live_concurrency_stress_reads(live_db_path: str) -> None:
    def task(i: int) -> tuple[str, int]:
        if i % 3 == 0:
            return ("menu", len(load_clause_menu(["ISO 9001"], language="EN", db_path=live_db_path)["ISO9001"]))
        if i % 3 == 1:
            return (
                "ids",
                len(fetch_clauses_by_ids(["8.4.1", "9.2.1"], ["ISO 9001"], language="EN", db_path=live_db_path)),
            )
        return (
            "section",
            len(fetch_clauses_by_section_type("PROCEDURE_TEXT", ["ISO 9001"], language="EN", db_path=live_db_path)),
        )

    errors: list[str] = []
    counts: dict[str, list[int]] = {"menu": [], "ids": [], "section": []}

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(task, i) for i in range(900)]
        for future in as_completed(futures):
            try:
                kind, count = future.result()
                counts[kind].append(count)
            except Exception as exc:  # pragma: no cover - assertion below captures details
                errors.append(repr(exc))

    assert not errors, f"Unexpected concurrent read errors: {errors[:3]}"
    assert len(set(counts["menu"])) == 1
    assert len(set(counts["ids"])) == 1
    assert len(set(counts["section"])) == 1


def test_live_query_plan_uses_indexes(live_db_path: str) -> None:
    with sqlite3.connect(live_db_path) as conn:
        menu_plan = conn.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT n.norm_id, n.language, c.clause_number, c.clause_title, c.parent_clause, c.text
            FROM iso_clauses c
            JOIN iso_norms n ON c.norm_key = n.norm_key
            WHERE n.norm_id IN ('ISO9001') AND n.language = 'EN' AND c.has_requirements = 1
            """
        ).fetchall()

        ids_plan = conn.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT n.norm_id, n.language, c.clause_number, c.clause_title, c.parent_clause, c.text
            FROM iso_clauses c
            JOIN iso_norms n ON c.norm_key = n.norm_key
            WHERE n.norm_id IN ('ISO9001')
              AND n.language = 'EN'
              AND c.clause_number IN ('8.4.1', '9.2.1')
            """
        ).fetchall()

        section_plan = conn.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT n.norm_id, n.language, c.clause_number, c.clause_title, c.parent_clause, c.text
            FROM iso_clauses c
            JOIN iso_norms n ON c.norm_key = n.norm_key
            WHERE n.norm_id IN ('ISO9001')
              AND n.language = 'EN'
              AND c.top_level_family IN ('6', '8')
              AND c.has_requirements = 1
            """
        ).fetchall()

    menu_text = " ".join(str(row) for row in menu_plan)
    ids_text = " ".join(str(row) for row in ids_plan)
    section_text = " ".join(str(row) for row in section_plan)

    assert "idx_iso_norm_identity" in menu_text
    assert "idx_clause_norm_key" in menu_text
    assert "idx_iso_norm_identity" in ids_text
    assert "sqlite_autoindex_iso_clauses_1" in ids_text
    assert "idx_iso_norm_identity" in section_text
    assert "idx_clause_norm_key" in section_text


def test_db_failure_modes_raise_operational_error(tmp_path: Path) -> None:
    missing_dir_db = tmp_path / "missing_dir" / "iso_clauses.db"
    with pytest.raises(sqlite3.OperationalError):
        load_clause_menu(["ISO 9001"], db_path=str(missing_dir_db))

    empty_db = tmp_path / "empty.db"
    sqlite3.connect(empty_db).close()
    with pytest.raises(sqlite3.OperationalError):
        fetch_clauses_by_ids(["8.4.1"], ["ISO 9001"], db_path=str(empty_db))
