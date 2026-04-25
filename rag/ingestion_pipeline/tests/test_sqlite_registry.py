from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from rag.ingestion_pipeline.chunker.models import NormChunk
from rag.ingestion_pipeline.registry.registry import (
    delete_norm_from_sqlite_registry,
    write_sqlite_clause_registry,
)
from rag.ingestion_pipeline.segmenter.models import ContentType


def _chunk(
    *,
    chunk_id: str,
    clause_number: str,
    chunk_index: int,
    text: str,
    has_requirements: bool,
    clause_title: str = "Clause Title",
    parent_clause: str = "8",
    language: str = "EN",
) -> NormChunk:
    return NormChunk(
        chunk_id=chunk_id,
        norm_id="ISO9001",
        norm_full="ISO 9001:2015",
        norm_version="2015",
        clause_number=clause_number,
        clause_family=clause_number.split(".")[0],
        clause_title=clause_title,
        parent_clause=parent_clause,
        page_number=1,
        chunk_index=chunk_index,
        total_chunks=1,
        text=text,
        token_count=10,
        content_type=ContentType.REQUIREMENT if has_requirements else ContentType.INFORMATIVE,
        shall_count=1 if has_requirements else 0,
        should_count=0,
        has_requirements=has_requirements,
        has_permissions=False,
        has_recommendations=False,
        has_capabilities=False,
        keywords=[],
        related_clauses=[],
        embedding_model="",
        language=language,
        bm25_tokens=[],
    )


def _result(chunks: list[NormChunk]):
    return SimpleNamespace(chunks=chunks)


def test_sqlite_writer_creates_norm_tables_and_inserts_once(tmp_path) -> None:
    db_path = tmp_path / "iso_clauses.db"
    result = _result(
        [
            _chunk(
                chunk_id="n9001_8.1_part1_p1",
                clause_number="8.1",
                chunk_index=1,
                text="First part",
                has_requirements=False,
                clause_title="Planning and control",
                parent_clause="8",
                language="EN",
            ),
            _chunk(
                chunk_id="n9001_8.1_part2_p2",
                clause_number="8.1",
                chunk_index=2,
                text="Second part",
                has_requirements=True,
                clause_title="Planning and control",
                parent_clause="8",
                language="EN",
            ),
            _chunk(
                chunk_id="n9001_9.1_part1_p5",
                clause_number="9.1",
                chunk_index=1,
                text="Single chunk clause",
                has_requirements=False,
                clause_title="Monitoring",
                parent_clause="9",
                language="EN",
            ),
        ]
    )

    inserted = write_sqlite_clause_registry(result, db_path=str(db_path))
    assert inserted == 2

    with sqlite3.connect(db_path) as conn:
        norm_cols = [r[1] for r in conn.execute("PRAGMA table_info(iso_norms)").fetchall()]
        clause_cols = [r[1] for r in conn.execute("PRAGMA table_info(iso_clauses)").fetchall()]
        norm_rows = conn.execute("SELECT COUNT(*) FROM iso_norms").fetchone()[0]
        clause_rows = conn.execute("SELECT COUNT(*) FROM iso_clauses").fetchone()[0]
        row = conn.execute(
            """
            SELECT clause_title, top_level_family, language, text, has_requirements
            FROM iso_clauses
            WHERE clause_number = '8.1'
            """
        ).fetchone()

    assert norm_cols == [
        "norm_key",
        "norm_id",
        "norm_version",
        "language",
        "norm_full",
        "created_at",
    ]
    assert clause_cols == [
        "norm_key",
        "norm_id",
        "norm_version",
        "language",
        "clause_number",
        "clause_title",
        "parent_clause",
        "top_level_family",
        "text",
        "has_requirements",
    ]
    assert norm_rows == 1
    assert clause_rows == 2
    assert row == ("Planning and control", "8", "EN", "First part\n\nSecond part", 1)


def test_sqlite_writer_skip_mode_does_not_overwrite_existing_norm(tmp_path) -> None:
    db_path = tmp_path / "iso_clauses.db"
    first = _result(
        [
            _chunk(
                chunk_id="n9001_4.1_part1_p1",
                clause_number="4.1",
                chunk_index=1,
                text="Old EN text",
                has_requirements=False,
                clause_title="Old title",
                parent_clause="4",
                language="EN",
            )
        ]
    )
    second = _result(
        [
            _chunk(
                chunk_id="n9001_4.1_part1_p1",
                clause_number="4.1",
                chunk_index=1,
                text="New EN text",
                has_requirements=True,
                clause_title="New title",
                parent_clause="4",
                language="EN",
            )
        ]
    )

    assert write_sqlite_clause_registry(first, db_path=str(db_path), if_exists="skip") == 1
    assert write_sqlite_clause_registry(second, db_path=str(db_path), if_exists="skip") == 0

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT clause_title, text, has_requirements
            FROM iso_clauses
            WHERE clause_number = '4.1'
            """
        ).fetchone()

    assert row == ("Old title", "Old EN text", 0)


def test_sqlite_writer_stores_fr_and_en_as_distinct_norms(tmp_path) -> None:
    db_path = tmp_path / "iso_clauses.db"
    en = _result(
        [
            _chunk(
                chunk_id="n9001_5.1_part1_p1",
                clause_number="5.1",
                chunk_index=1,
                text="EN text",
                has_requirements=True,
                clause_title="Leadership",
                parent_clause="5",
                language="EN",
            )
        ]
    )
    fr = _result(
        [
            _chunk(
                chunk_id="n9001_5.1_part1_p1",
                clause_number="5.1",
                chunk_index=1,
                text="Texte FR",
                has_requirements=True,
                clause_title="Leadership FR",
                parent_clause="5",
                language="FR",
            )
        ]
    )

    assert write_sqlite_clause_registry(en, db_path=str(db_path), if_exists="skip") == 1
    assert write_sqlite_clause_registry(fr, db_path=str(db_path), if_exists="skip") == 1

    with sqlite3.connect(db_path) as conn:
        norm_count = conn.execute("SELECT COUNT(*) FROM iso_norms").fetchone()[0]
        clause_count = conn.execute("SELECT COUNT(*) FROM iso_clauses").fetchone()[0]
        languages = conn.execute(
            "SELECT language, COUNT(*) FROM iso_clauses GROUP BY language ORDER BY language"
        ).fetchall()

    assert norm_count == 2
    assert clause_count == 2
    assert languages == [("EN", 1), ("FR", 1)]


def test_sqlite_delete_norm_removes_associated_clauses(tmp_path) -> None:
    db_path = tmp_path / "iso_clauses.db"
    en = _result(
        [
            _chunk(
                chunk_id="n9001_6.1_part1_p1",
                clause_number="6.1",
                chunk_index=1,
                text="EN text",
                has_requirements=True,
                clause_title="Planification",
                parent_clause="6",
                language="EN",
            )
        ]
    )
    fr = _result(
        [
            _chunk(
                chunk_id="n9001_6.1_part1_p1",
                clause_number="6.1",
                chunk_index=1,
                text="FR texte",
                has_requirements=True,
                clause_title="Planification FR",
                parent_clause="6",
                language="FR",
            )
        ]
    )
    write_sqlite_clause_registry(en, db_path=str(db_path), if_exists="skip")
    write_sqlite_clause_registry(fr, db_path=str(db_path), if_exists="skip")

    deleted = delete_norm_from_sqlite_registry(
        db_path=str(db_path),
        norm_id="ISO9001",
        norm_version="2015",
        language="FR",
    )
    assert deleted == 1

    with sqlite3.connect(db_path) as conn:
        norms = conn.execute(
            "SELECT language FROM iso_norms ORDER BY language"
        ).fetchall()
        clauses = conn.execute(
            "SELECT language FROM iso_clauses ORDER BY language"
        ).fetchall()

    assert norms == [("EN",)]
    assert clauses == [("EN",)]


def test_sqlite_migrates_legacy_single_table_schema(tmp_path) -> None:
    db_path = tmp_path / "iso_clauses.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS iso_clauses (
                norm_id          TEXT NOT NULL,
                clause_number    TEXT NOT NULL,
                clause_title     TEXT NOT NULL,
                parent_clause    TEXT NOT NULL,
                text             TEXT NOT NULL,
                has_requirements INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (norm_id, clause_number)
            );
            INSERT INTO iso_clauses (
                norm_id, clause_number, clause_title, parent_clause, text, has_requirements
            ) VALUES (
                'ISO9001', '4.1', 'Legacy title', '4', 'Legacy text', 1
            );
            """
        )
        conn.commit()

    inserted = write_sqlite_clause_registry(
        _result(
            [
                _chunk(
                    chunk_id="n9001_5.1_part1_p1",
                    clause_number="5.1",
                    chunk_index=1,
                    text="Fresh text",
                    has_requirements=True,
                    clause_title="Fresh title",
                    parent_clause="5",
                    language="FR",
                )
            ]
        ),
        db_path=str(db_path),
        if_exists="skip",
    )
    assert inserted == 1

    with sqlite3.connect(db_path) as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        norm_rows = conn.execute("SELECT COUNT(*) FROM iso_norms").fetchone()[0]
        clause_rows = conn.execute("SELECT COUNT(*) FROM iso_clauses").fetchone()[0]
        legacy_row = conn.execute(
            """
            SELECT COUNT(*)
            FROM iso_clauses
            WHERE clause_number = '4.1' AND text = 'Legacy text'
            """
        ).fetchone()[0]

    assert "iso_clauses_legacy" not in tables
    assert norm_rows >= 2
    assert clause_rows >= 2
    assert legacy_row == 1


def test_sqlite_writer_normalizes_alias_db_path_and_keeps_one_file(tmp_path) -> None:
    canonical = tmp_path / "iso_clauses.db"
    alias = tmp_path / "iso_norms.db"

    result = _result(
        [
            _chunk(
                chunk_id="n9001_7.1_part1_p1",
                clause_number="7.1",
                chunk_index=1,
                text="Infrastructure requirements",
                has_requirements=True,
                clause_title="7.1",
                parent_clause="7",
                language="EN",
            )
        ]
    )

    inserted = write_sqlite_clause_registry(result, db_path=str(alias), if_exists="skip")
    assert inserted == 1
    assert canonical.exists()
    assert not alias.exists()

    with sqlite3.connect(canonical) as conn:
        count = conn.execute("SELECT COUNT(*) FROM iso_clauses").fetchone()[0]
    assert count == 1
