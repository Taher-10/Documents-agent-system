from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import httpx


MOCK_ROOT = Path(__file__).resolve().parents[1]
if str(MOCK_ROOT) not in sys.path:
    sys.path.insert(0, str(MOCK_ROOT))

from qalitas_mock_caller.config import load_settings


COMPANY_ID = "00000000-0000-0000-0000-000000000001"
SITE_ID = "00000000-0000-0000-0000-000000000002"
TYPE_ID = "00000000-0000-0000-0000-000000000010"
FILE_PATH = "qalitas-mock-caller/storage/docs/PRO-ENV-001.pdf"

DOC_A_ID = "00000000-0000-0000-0000-000000000101"
DOC_B_ID = "00000000-0000-0000-0000-000000000102"

SCENARIOS: dict[str, dict[str, Any]] = {
    DOC_A_ID: {
        "code": "PRO-HSE-101",
        "designation": "Procédure santé H-only",
        "version": "01",
        "Q": False,
        "E": False,
        "S": False,
        "H": True,
        "created_date": "2026-04-24T09:00:00Z",
    },
    DOC_B_ID: {
        "code": "PRO-HSE-102",
        "designation": "Procédure sécurité santé S+H",
        "version": "01",
        "Q": False,
        "E": False,
        "S": True,
        "H": True,
        "created_date": "2026-04-24T09:05:00Z",
    },
}


def _parse_args() -> argparse.Namespace:
    defaults = load_settings()

    parser = argparse.ArgumentParser(
        description="Seed deterministic mock InternalDocs rows and run one trigger-analyze smoke call.",
    )
    parser.add_argument(
        "--mock-base-url",
        default="http://127.0.0.1:8100",
        help="Base URL for QALITAS mock caller service.",
    )
    parser.add_argument(
        "--db-path",
        default=str(defaults.qalitas_db_path),
        help="SQLite database path to seed.",
    )
    parser.add_argument(
        "--init-sql",
        default=str(defaults.qalitas_db_init_sql),
        help="Path to init SQL script (DDL + base seed).",
    )
    parser.add_argument(
        "--document-id",
        default=DOC_A_ID,
        choices=sorted(SCENARIOS.keys()),
        help="Document scenario to preview + smoke.",
    )
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Seed data only; skip preview and trigger-analyze HTTP calls.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=120.0,
        help="HTTP timeout for preview and smoke calls.",
    )
    return parser.parse_args()


def _run_init_sql(conn: sqlite3.Connection, init_sql_path: Path) -> None:
    sql = init_sql_path.read_text(encoding="utf-8")
    conn.executescript(sql)


def _assert_base_rows(conn: sqlite3.Connection) -> None:
    checks = {
        "Company": ("SELECT COUNT(*) FROM Company WHERE Id = ?", (COMPANY_ID,)),
        "Site": ("SELECT COUNT(*) FROM Site WHERE Id = ?", (SITE_ID,)),
        "Ini_Types": ("SELECT COUNT(*) FROM Ini_Types WHERE Id = ?", (TYPE_ID,)),
    }

    for label, (query, params) in checks.items():
        row = conn.execute(query, params).fetchone()
        if row is None or int(row[0]) < 1:
            raise RuntimeError(
                f"Required base row missing in {label}; init SQL did not seed expected IDs."
            )


def _upsert_internal_docs(conn: sqlite3.Connection) -> None:
    stmt = """
    INSERT OR REPLACE INTO InternalDocs (
        Id, Code, "Index", Designation, SiteId, CompanyId, Q, S, E, H, TypesId, FilePath, CreatedDate
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    for doc_id, data in SCENARIOS.items():
        conn.execute(
            stmt,
            (
                doc_id,
                data["code"],
                data["version"],
                data["designation"],
                SITE_ID,
                COMPANY_ID,
                int(bool(data["Q"])),
                int(bool(data["S"])),
                int(bool(data["E"])),
                int(bool(data["H"])),
                TYPE_ID,
                FILE_PATH,
                data["created_date"],
            ),
        )


def _seed_dataset(db_path: Path, init_sql_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _run_init_sql(conn, init_sql_path)
        _assert_base_rows(conn)
        _upsert_internal_docs(conn)
        conn.commit()


def _endpoint(base_url: str, route: str) -> str:
    return f"{base_url.rstrip('/')}{route}"


def _safe_json(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {"raw": data}
    except (json.JSONDecodeError, ValueError):
        return None


def _validate_preview_payload(payload: dict[str, Any], document_id: str) -> None:
    expected = SCENARIOS[document_id]
    doc = payload.get("document")
    if not isinstance(doc, dict):
        raise RuntimeError("Preview payload missing 'document' object.")

    if str(doc.get("id")) != document_id:
        raise RuntimeError(
            f"Preview document id mismatch: expected {document_id}, got {doc.get('id')!r}"
        )

    for flag in ("Q", "E", "S", "H"):
        actual = bool(doc.get(flag))
        exp = bool(expected[flag])
        if actual != exp:
            raise RuntimeError(
                f"Preview flag mismatch for {flag}: expected {exp}, got {actual}"
            )


def _print_error(prefix: str, message: str) -> None:
    print(f"{prefix}: {message}", file=sys.stderr)


def main() -> int:
    args = _parse_args()
    db_path = Path(args.db_path).expanduser().resolve()
    init_sql_path = Path(args.init_sql).expanduser().resolve()

    if not init_sql_path.exists():
        _print_error("[error]", f"init SQL not found: {init_sql_path}")
        return 1

    try:
        _seed_dataset(db_path=db_path, init_sql_path=init_sql_path)
    except Exception as exc:
        _print_error("[error]", f"seeding failed: {type(exc).__name__}: {exc}")
        return 1

    print(f"[seed] DB ready at {db_path}")
    print(f"[seed] upserted docs: {DOC_A_ID} (H-only), {DOC_B_ID} (S+H)")

    if args.seed_only:
        print("[preview] skipped (--seed-only)")
        print("[smoke] skipped (--seed-only)")
        return 0

    preview_url = _endpoint(args.mock_base_url, "/preview-analyze-request")
    trigger_url = _endpoint(args.mock_base_url, "/trigger-analyze")
    params = {"document_id": args.document_id}

    try:
        with httpx.Client(timeout=max(args.timeout_seconds, 1.0)) as client:
            preview = client.get(preview_url, params=params)
    except httpx.RequestError as exc:
        _print_error("[error]", f"preview call failed: {type(exc).__name__}: {exc}")
        return 1

    if preview.status_code != 200:
        body = _safe_json(preview)
        _print_error(
            "[error]",
            f"preview status={preview.status_code} body={body if body is not None else preview.text[:300]!r}",
        )
        return 1

    preview_payload = _safe_json(preview)
    if preview_payload is None:
        _print_error("[error]", "preview returned non-JSON response")
        return 1

    try:
        _validate_preview_payload(preview_payload, args.document_id)
    except RuntimeError as exc:
        _print_error("[error]", str(exc))
        return 1

    doc = preview_payload["document"]
    print(
        "[preview] "
        f"id={doc.get('id')} flags="
        f"Q={doc.get('Q')} E={doc.get('E')} S={doc.get('S')} H={doc.get('H')}"
    )

    try:
        with httpx.Client(timeout=max(args.timeout_seconds, 1.0)) as client:
            smoke = client.post(trigger_url, params=params)
    except httpx.RequestError as exc:
        _print_error("[error]", f"trigger call failed: {type(exc).__name__}: {exc}")
        return 1

    body = _safe_json(smoke)
    if smoke.status_code >= 400:
        _print_error(
            "[error]",
            f"smoke failed status={smoke.status_code} body={body if body is not None else smoke.text[:300]!r}",
        )
        return 1

    status = body.get("status") if isinstance(body, dict) else None
    doc_id = body.get("doc_id") if isinstance(body, dict) else None
    code = body.get("code") if isinstance(body, dict) else None
    print(
        f"[smoke] status_code={smoke.status_code} "
        f"status={status!r} doc_id={doc_id!r} code={code!r}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
