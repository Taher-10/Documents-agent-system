from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class DocumentNotFoundError(RuntimeError):
    pass


class RepositoryError(RuntimeError):
    pass


class QalitasRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def init_if_needed(self, init_sql_path: Path) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.db_path.exists():
            return
        sql = init_sql_path.read_text(encoding="utf-8")
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(sql)
            conn.commit()

    def build_analyze_request(
        self,
        document_id: str | None = None,
        *,
        options_format: str = "json",
    ) -> dict[str, Any]:
        query = """
        SELECT
            d.Id            AS document_id,
            d.Code          AS code,
            d.Designation   AS designation,
            d."Index"       AS version,
            t.Designation   AS type_designation,
            d.Q             AS q,
            d.E             AS e,
            d.S             AS s,
            d.H             AS h,
            d.FilePath      AS file_path,
            d.CompanyId     AS company_id,
            d.SiteId        AS site_id,
            e.Id            AS user_id
        FROM InternalDocs d
        JOIN Ini_Types t
          ON t.Id = d.TypesId
        LEFT JOIN Employees e
          ON e.SiteId = d.SiteId
         AND e.CompanyId = d.CompanyId
         AND e.IsEnabled = 1
        WHERE (? IS NULL OR d.Id = ?)
        ORDER BY d.CreatedDate DESC
        LIMIT 1
        """

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(query, (document_id, document_id)).fetchone()
        except sqlite3.Error as exc:  # pragma: no cover
            raise RepositoryError(f"DB query failed: {exc}") from exc

        if row is None:
            raise DocumentNotFoundError(
                f"No InternalDocs record found for document_id={document_id!r}"
            )

        user_id = row["user_id"] or "00000000-0000-0000-0000-000000000003"

        payload = {
            "session": {
                "company_id": row["company_id"],
                "site_id": row["site_id"],
                "user_id": user_id,
            },
            "document": {
                "id": row["document_id"],
                "code": row["code"],
                "designation": row["designation"],
                "version": row["version"],
                "type_designation": row["type_designation"],
                "Q": bool(row["q"]),
                "E": bool(row["e"]),
                "S": bool(row["s"]),
                "H": bool(row["h"]),
                "file_path": row["file_path"],
            },
            "options": {
                "format": options_format,
            },
        }
        return payload
