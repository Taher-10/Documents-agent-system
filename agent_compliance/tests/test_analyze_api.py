from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from agent_compliance.pdf_parser.docling_parser import ParseResult
from agent_compliance.pdf_parser.parsed_document import ParsedSection, SectionType
from agent_compliance.tests.fixtures.mock_request import MOCK_REQUEST

api_app_mod = importlib.import_module("agent_compliance.api.app")


@pytest.fixture(autouse=True)
def clear_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    api_app_mod._STATE_CACHE.clear()
    api_app_mod._PIPELINE_RUNNER = None
    api_app_mod._QDRANT_CLIENT = None
    api_app_mod._EMBEDDER_SERVICE = None

    monkeypatch.setattr(api_app_mod, "_get_qdrant_client", lambda: MagicMock())
    monkeypatch.setattr(api_app_mod, "_get_embedder_service", lambda: MagicMock())
    monkeypatch.setattr(api_app_mod, "has_ingested_document", lambda *args, **kwargs: True)

    async def _noop_ingest(*args, **kwargs):
        return SimpleNamespace(
            ingested=1,
            reason=None,
            quality_tier="A",
            min_confidence=1.0,
        )

    monkeypatch.setattr(api_app_mod, "ingest_document_async", _noop_ingest)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("FILE_BASE_PATH", str(tmp_path))

    file_dir = tmp_path / "test"
    file_dir.mkdir(parents=True, exist_ok=True)
    (file_dir / "PRO-ENV-001.pdf").write_text("dummy")

    return TestClient(api_app_mod.app)


def _success_sections() -> list[ParsedSection]:
    return [
        ParsedSection(
            id="section_scope_1",
            section_type=SectionType.SCOPE,
            title="Scope",
            raw_text="Applies to all activities.",
            page_range=(1, 1),
            extraction_confidence=1.0,
        ),
        ParsedSection(
            id="section_proc_2",
            section_type=SectionType.PROCEDURE_TEXT,
            title="Procedure",
            raw_text="The organization shall document controls.",
            page_range=(1, 2),
            extraction_confidence=1.0,
        ),
    ]


@pytest.mark.parametrize("fixture_name", ["golden_success_response.json"])
def test_analyze_success(client: TestClient, monkeypatch: pytest.MonkeyPatch, fixture_name: str) -> None:
    async def fake_run(_: str, thread_id: str | None = None) -> dict:
        _ = thread_id
        return {
            "document_path": "ignored",
            "parse_result": ParseResult(source_path="x", text="ok", pages=2),
            "sections": _success_sections(),
            "error": None,
            "status": "sections_filtered",
        }

    monkeypatch.setattr(api_app_mod, "_PIPELINE_RUNNER", fake_run)

    response = client.post("/analyze", json=MOCK_REQUEST)

    assert response.status_code == 200
    payload = response.json()

    expected = json.loads(
        (Path(__file__).parent / "fixtures" / fixture_name).read_text(encoding="utf-8")
    )
    assert payload == expected


def test_analyze_cache_miss_runs_ingestion_once_and_keeps_contract(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qdrant = MagicMock()
    has_calls: list[tuple[str, str]] = []

    def fake_has_ingested(_client, *, doc_id: str, company_id: str, collection: str = "qhse_sections"):
        assert _client is qdrant
        _ = collection
        has_calls.append((doc_id, company_id))
        return False

    ingest_mock = AsyncMock(
        return_value=SimpleNamespace(
            ingested=2,
            reason=None,
            quality_tier="A",
            min_confidence=1.0,
        )
    )

    embedder = MagicMock()
    embedder.embed_text = AsyncMock(return_value=[0.1] * 1024)

    async def fake_run(_: str, thread_id: str | None = None) -> dict:
        _ = thread_id
        return {
            "document_path": "ignored",
            "parse_result": ParseResult(source_path="x", text="ok", pages=2),
            "sections": _success_sections(),
            "error": None,
            "status": "sections_filtered",
        }

    monkeypatch.setattr(api_app_mod, "_PIPELINE_RUNNER", fake_run)
    monkeypatch.setattr(api_app_mod, "_get_qdrant_client", lambda: qdrant)
    monkeypatch.setattr(api_app_mod, "_get_embedder_service", lambda: embedder)
    monkeypatch.setattr(api_app_mod, "has_ingested_document", fake_has_ingested)
    monkeypatch.setattr(api_app_mod, "ingest_document_async", ingest_mock)

    response = client.post("/analyze", json=MOCK_REQUEST)

    assert response.status_code == 200
    assert has_calls == [("00000000-0000-0000-0000-000000000004", "00000000-0000-0000-0000-000000000001")]
    ingest_mock.assert_awaited_once()

    payload = response.json()
    expected = json.loads(
        (Path(__file__).parent / "fixtures" / "golden_success_response.json").read_text(encoding="utf-8")
    )
    assert payload == expected


def test_analyze_cache_hit_skips_ingestion(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ingest_mock = AsyncMock()

    async def fake_run(_: str, thread_id: str | None = None) -> dict:
        _ = thread_id
        return {
            "document_path": "ignored",
            "parse_result": ParseResult(source_path="x", text="ok", pages=2),
            "sections": _success_sections(),
            "error": None,
            "status": "sections_filtered",
        }

    monkeypatch.setattr(api_app_mod, "_PIPELINE_RUNNER", fake_run)
    monkeypatch.setattr(api_app_mod, "has_ingested_document", lambda *args, **kwargs: True)
    monkeypatch.setattr(api_app_mod, "ingest_document_async", ingest_mock)

    response = client.post("/analyze", json=MOCK_REQUEST)

    assert response.status_code == 200
    ingest_mock.assert_not_awaited()


def test_analyze_ingestion_exception_returns_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run(_: str, thread_id: str | None = None) -> dict:
        _ = thread_id
        return {
            "document_path": "ignored",
            "parse_result": ParseResult(source_path="x", text="ok", pages=2),
            "sections": _success_sections(),
            "error": None,
            "status": "sections_filtered",
        }

    async def failing_ingest(*args, **kwargs):
        _ = args, kwargs
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(api_app_mod, "_PIPELINE_RUNNER", fake_run)
    monkeypatch.setattr(api_app_mod, "has_ingested_document", lambda *args, **kwargs: False)
    monkeypatch.setattr(api_app_mod, "ingest_document_async", failing_ingest)

    response = client.post("/analyze", json=MOCK_REQUEST)

    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "INGESTION_ERROR"


def test_analyze_ingestion_low_quality_maps_to_422(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def low_quality_ingest(*args, **kwargs):
        _ = args, kwargs
        return SimpleNamespace(
            ingested=0,
            reason="low_quality_document",
            quality_tier="C",
            min_confidence=0.5,
        )

    monkeypatch.setattr(api_app_mod, "has_ingested_document", lambda *args, **kwargs: False)
    monkeypatch.setattr(api_app_mod, "ingest_document_async", low_quality_ingest)

    response = client.post("/analyze", json=MOCK_REQUEST)

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "LOW_QUALITY_DOCUMENT"


def test_analyze_ingestion_zero_non_low_quality_returns_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def zero_ingest(*args, **kwargs):
        _ = args, kwargs
        return SimpleNamespace(
            ingested=0,
            reason="no_sections_ingested",
            quality_tier="A",
            min_confidence=1.0,
        )

    monkeypatch.setattr(api_app_mod, "has_ingested_document", lambda *args, **kwargs: False)
    monkeypatch.setattr(api_app_mod, "ingest_document_async", zero_ingest)

    response = client.post("/analyze", json=MOCK_REQUEST)

    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "INGESTION_ERROR"


def test_invalid_uuid_returns_structured_error(client: TestClient) -> None:
    body = dict(MOCK_REQUEST)
    body["session"] = dict(MOCK_REQUEST["session"])
    body["session"]["company_id"] = "not-a-uuid"

    response = client.post("/analyze", json=body)

    assert response.status_code == 422
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["code"] == "VALIDATION_ERROR"
    assert isinstance(payload.get("errors"), list)


@pytest.mark.parametrize("bad_path", ["../escape/file.pdf"])
def test_invalid_file_path_rejected(client: TestClient, bad_path: str) -> None:
    body = dict(MOCK_REQUEST)
    body["document"] = dict(MOCK_REQUEST["document"])
    body["document"]["file_path"] = bad_path

    response = client.post("/analyze", json=body)

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"


def test_absolute_file_path_is_accepted(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "absolute.pdf"
    source.write_text("dummy")

    async def fake_run(_: str, thread_id: str | None = None) -> dict:
        _ = thread_id
        return {
            "document_path": str(source),
            "parse_result": ParseResult(source_path=str(source), text="ok", pages=2),
            "sections": _success_sections(),
            "error": None,
            "status": "sections_filtered",
        }

    monkeypatch.setattr(api_app_mod, "_PIPELINE_RUNNER", fake_run)

    body = dict(MOCK_REQUEST)
    body["document"] = dict(MOCK_REQUEST["document"])
    body["document"]["file_path"] = str(source)

    response = client.post("/analyze", json=body)
    assert response.status_code == 200


def test_no_norms_returns_400(client: TestClient) -> None:
    body = dict(MOCK_REQUEST)
    body["document"] = dict(MOCK_REQUEST["document"])
    body["document"].update({"Q": False, "E": False, "S": False, "H": False})

    response = client.post("/analyze", json=body)

    assert response.status_code == 400
    assert response.json()["code"] == "NO_NORMS"


def test_h_only_maps_to_iso_45001(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(_: str, thread_id: str | None = None) -> dict:
        _ = thread_id
        return {
            "document_path": "ignored",
            "parse_result": ParseResult(source_path="x", text="ok", pages=2),
            "sections": _success_sections(),
            "error": None,
            "status": "sections_filtered",
        }

    monkeypatch.setattr(api_app_mod, "_PIPELINE_RUNNER", fake_run)

    body = dict(MOCK_REQUEST)
    body["document"] = dict(MOCK_REQUEST["document"])
    body["document"].update({"Q": False, "E": False, "S": False, "H": True})

    response = client.post("/analyze", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["applicable_norms"] == ["ISO 45001"]
    assert [item["clause"] for item in payload["report"]["coverage_matrix"]] == ["ISO 45001 8.1"]
    assert all("ISO 22000" not in item["clause"] for item in payload["report"]["coverage_matrix"])


def test_s_and_h_are_deduplicated_to_single_norm(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run(_: str, thread_id: str | None = None) -> dict:
        _ = thread_id
        return {
            "document_path": "ignored",
            "parse_result": ParseResult(source_path="x", text="ok", pages=2),
            "sections": _success_sections(),
            "error": None,
            "status": "sections_filtered",
        }

    monkeypatch.setattr(api_app_mod, "_PIPELINE_RUNNER", fake_run)

    body = dict(MOCK_REQUEST)
    body["document"] = dict(MOCK_REQUEST["document"])
    body["document"].update({"Q": False, "E": False, "S": True, "H": True})

    response = client.post("/analyze", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["applicable_norms"] == ["ISO 45001"]
    assert len(payload["report"]["coverage_matrix"]) == 1


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
def test_non_json_format_not_available(client: TestClient, fmt: str) -> None:
    body = dict(MOCK_REQUEST)
    body["options"] = {"format": fmt}

    response = client.post("/analyze", json=body)

    assert response.status_code == 400
    assert response.json()["code"] == "FORMAT_NOT_AVAILABLE"


def test_missing_file_returns_404(client: TestClient) -> None:
    body = dict(MOCK_REQUEST)
    body["document"] = dict(MOCK_REQUEST["document"])
    body["document"]["file_path"] = "test/missing.pdf"

    response = client.post("/analyze", json=body)

    assert response.status_code == 404
    assert response.json()["code"] == "FILE_NOT_FOUND"


def test_low_quality_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(_: str, thread_id: str | None = None) -> dict:
        _ = thread_id
        return {
            "document_path": "ignored",
            "parse_result": ParseResult(source_path="x", text="", pages=1),
            "sections": [],
            "error": None,
            "status": "sections_filtered",
        }

    monkeypatch.setattr(api_app_mod, "_PIPELINE_RUNNER", fake_run)

    response = client.post("/analyze", json=MOCK_REQUEST)

    assert response.status_code == 422
    assert response.json()["code"] == "LOW_QUALITY_DOCUMENT"


def test_mock_fixture_contract_accepted(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(_: str, thread_id: str | None = None) -> dict:
        _ = thread_id
        return {
            "document_path": "ignored",
            "parse_result": ParseResult(source_path="x", text="ok", pages=2),
            "sections": _success_sections(),
            "error": None,
            "status": "sections_filtered",
        }

    monkeypatch.setattr(api_app_mod, "_PIPELINE_RUNNER", fake_run)

    response = client.post("/analyze", json=MOCK_REQUEST)
    assert response.status_code == 200


def test_openapi_snapshot_matches() -> None:
    actual = api_app_mod.app.openapi()
    expected_path = Path(__file__).parent.parent / "contracts" / "openapi.analyze.v1.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert actual == expected
