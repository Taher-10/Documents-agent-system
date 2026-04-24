from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

MOCK_ROOT = Path(__file__).resolve().parents[1]
if str(MOCK_ROOT) not in sys.path:
    sys.path.insert(0, str(MOCK_ROOT))

from qalitas_mock_caller.app import create_app
from qalitas_mock_caller.config import Settings


def _build_settings(tmp_path: Path) -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    db_dir = tmp_path / "db"
    docs_dir = tmp_path / "storage" / "docs"
    db_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Create target docs file expected by DB seed.
    (docs_dir / "PRO-ENV-001.pdf").write_bytes(b"%PDF-1.4 mock pdf")

    return Settings(
        agent_base_url="http://127.0.0.1:8000",
        agent_analyze_path="/analyze",
        agent_timeout_seconds=5.0,
        agent_repo_root=repo_root,
        qalitas_db_path=db_dir / "qalitas_mock.db",
        qalitas_db_init_sql=repo_root / "qalitas-mock-caller" / "db" / "init_mock_sqlite.sql",
        qalitas_docs_dir=docs_dir,
    )


def test_health(tmp_path: Path) -> None:
    app = create_app(_build_settings(tmp_path))
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_preview_request_comes_from_db(tmp_path: Path) -> None:
    app = create_app(_build_settings(tmp_path))
    client = TestClient(app)

    response = client.get("/preview-analyze-request")
    assert response.status_code == 200

    payload = response.json()
    assert payload["session"]["company_id"] == "00000000-0000-0000-0000-000000000001"
    assert payload["document"]["id"] == "00000000-0000-0000-0000-000000000004"
    assert payload["document"]["type_designation"] == "Procédure"
    assert payload["document"]["file_path"] == "qalitas-mock-caller/storage/docs/PRO-ENV-001.pdf"


def test_trigger_analyze_pass_through_success(tmp_path: Path, monkeypatch) -> None:
    app = create_app(_build_settings(tmp_path))
    client = TestClient(app)

    async def fake_call_agent(url: str, payload: dict, timeout_seconds: float) -> httpx.Response:
        assert url == "http://127.0.0.1:8000/analyze"
        assert payload["document"]["id"] == "00000000-0000-0000-0000-000000000004"
        assert timeout_seconds == 5.0
        req = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=req,
            json={"status": "completed", "doc_id": payload["document"]["id"]},
        )

    monkeypatch.setattr("qalitas_mock_caller.app._call_agent", fake_call_agent)

    response = client.post("/trigger-analyze")
    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "doc_id": "00000000-0000-0000-0000-000000000004",
    }


def test_trigger_analyze_pass_through_business_error(tmp_path: Path, monkeypatch) -> None:
    app = create_app(_build_settings(tmp_path))
    client = TestClient(app)

    async def fake_call_agent(url: str, payload: dict, timeout_seconds: float) -> httpx.Response:
        req = httpx.Request("POST", url)
        return httpx.Response(
            422,
            request=req,
            json={"status": "error", "code": "LOW_QUALITY_DOCUMENT", "detail": "bad parse"},
        )

    monkeypatch.setattr("qalitas_mock_caller.app._call_agent", fake_call_agent)

    response = client.post("/trigger-analyze")
    assert response.status_code == 422
    assert response.json() == {
        "status": "error",
        "code": "LOW_QUALITY_DOCUMENT",
        "detail": "bad parse",
    }


def test_trigger_analyze_maps_request_error(tmp_path: Path, monkeypatch) -> None:
    app = create_app(_build_settings(tmp_path))
    client = TestClient(app)

    async def fake_call_agent(url: str, payload: dict, timeout_seconds: float) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("qalitas_mock_caller.app._call_agent", fake_call_agent)

    response = client.post("/trigger-analyze")
    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == "AGENT_UNAVAILABLE"


def test_trigger_analyze_maps_non_json(tmp_path: Path, monkeypatch) -> None:
    app = create_app(_build_settings(tmp_path))
    client = TestClient(app)

    async def fake_call_agent(url: str, payload: dict, timeout_seconds: float) -> httpx.Response:
        req = httpx.Request("POST", url)
        return httpx.Response(500, request=req, text="internal html error")

    monkeypatch.setattr("qalitas_mock_caller.app._call_agent", fake_call_agent)

    response = client.post("/trigger-analyze")
    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "code": "UPSTREAM_NON_JSON",
        "detail": "internal html error",
    }


def test_document_not_found_from_db(tmp_path: Path) -> None:
    app = create_app(_build_settings(tmp_path))
    client = TestClient(app)

    response = client.post("/trigger-analyze", params={"document_id": "11111111-1111-1111-1111-111111111111"})
    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == "MOCK_DOCUMENT_NOT_FOUND"


def test_db_seed_created(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    create_app(settings)
    assert settings.qalitas_db_path.exists()

    with sqlite3.connect(settings.qalitas_db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM InternalDocs").fetchone()
        assert row is not None
        assert row[0] >= 1
