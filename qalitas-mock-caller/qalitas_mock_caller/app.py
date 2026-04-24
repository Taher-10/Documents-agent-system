from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import Settings, load_settings
from .repository import DocumentNotFoundError, QalitasRepository, RepositoryError


def _ensure_docs_seeded(cfg: Settings) -> None:
    cfg.qalitas_docs_dir.mkdir(parents=True, exist_ok=True)
    target = cfg.qalitas_docs_dir / "PRO-ENV-001.pdf"
    if target.exists():
        return
    source = cfg.agent_repo_root / "agent_compliance" / "qhme_docs" / "qa-qc-documents-sample.pdf"
    if source.exists():
        target.write_bytes(source.read_bytes())


def _build_payload_from_db(
    repository: QalitasRepository,
    *,
    document_id: str | None = None,
    fmt: str = "json",
) -> dict[str, Any]:
    return repository.build_analyze_request(document_id=document_id, options_format=fmt)


async def _call_agent(url: str, payload: dict[str, Any], timeout_seconds: float) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        return await client.post(url, json=payload)


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or load_settings()
    repository = QalitasRepository(cfg.qalitas_db_path)
    repository.init_if_needed(cfg.qalitas_db_init_sql)
    _ensure_docs_seeded(cfg)

    app = FastAPI(
        title="QALITAS Mock Caller",
        version="1.0.0",
        description="Mock service that builds request payload from QALITAS-like DB and forwards to Agent IA 2 /analyze.",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/preview-analyze-request")
    async def preview_analyze_request(document_id: str | None = None) -> JSONResponse:
        try:
            payload = _build_payload_from_db(repository, document_id=document_id)
        except DocumentNotFoundError as exc:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "code": "MOCK_DOCUMENT_NOT_FOUND", "detail": str(exc)},
            )
        except RepositoryError as exc:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "code": "MOCK_DB_ERROR", "detail": str(exc)},
            )
        return JSONResponse(status_code=200, content=payload)

    @app.post("/trigger-analyze")
    async def trigger_analyze(document_id: str | None = None) -> JSONResponse:
        try:
            payload = _build_payload_from_db(repository, document_id=document_id)
        except DocumentNotFoundError as exc:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "code": "MOCK_DOCUMENT_NOT_FOUND", "detail": str(exc)},
            )
        except RepositoryError as exc:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "code": "MOCK_DB_ERROR", "detail": str(exc)},
            )

        try:
            upstream = await _call_agent(cfg.analyze_url, payload, cfg.agent_timeout_seconds)
        except httpx.RequestError as exc:
            detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            return JSONResponse(
                status_code=502,
                content={
                    "status": "error",
                    "code": "AGENT_UNAVAILABLE",
                    "detail": detail,
                },
            )

        try:
            body = upstream.json()
        except (json.JSONDecodeError, ValueError):
            return JSONResponse(
                status_code=upstream.status_code,
                content={
                    "status": "error",
                    "code": "UPSTREAM_NON_JSON",
                    "detail": (upstream.text or "Upstream returned non-JSON response")[:500],
                },
            )

        return JSONResponse(status_code=upstream.status_code, content=body)

    return app


app = create_app()
