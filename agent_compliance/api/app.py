from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agent_compliance.pdf_parser import assess_quality
from agent_compliance.pdf_parser.parsed_document import ParsedSection

from .contracts import (
    ActionItem,
    AnalyzeRequest,
    AnalyzeSuccessResponse,
    CoverageItem,
    ErrorResponse,
    ReportPayload,
)
from .document_meta import DocumentMeta
from agent_compliance.ingestion.qhse_ingester import (
    IngestResult,
    has_ingested_document,
    ingest_document_async,
)


@dataclass(slots=True)
class ApiError(Exception):
    status_code: int
    code: str
    detail: str


_STATE_CACHE: dict[str, dict[str, Any]] = {}
_PIPELINE_RUNNER = None
_QDRANT_CLIENT = None
_EMBEDDER_SERVICE = None


def _get_pipeline_runner():
    global _PIPELINE_RUNNER
    if _PIPELINE_RUNNER is None:
        from agent_compliance.graph.run import run as run_pipeline

        _PIPELINE_RUNNER = run_pipeline
    return _PIPELINE_RUNNER


def _get_qdrant_client():
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is None:
        from qdrant_client import QdrantClient

        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        api_key = os.getenv("QDRANT_API_KEY") or None
        _QDRANT_CLIENT = QdrantClient(host=host, port=port, api_key=api_key)
    return _QDRANT_CLIENT


def _get_embedder_service():
    global _EMBEDDER_SERVICE
    if _EMBEDDER_SERVICE is None:
        from rag.ingestion_pipeline.embedder import EmbedderService

        _EMBEDDER_SERVICE = EmbedderService()
    return _EMBEDDER_SERVICE


async def _ingest_if_needed(meta: DocumentMeta) -> IngestResult | None:
    try:
        qdrant_client = _get_qdrant_client()
        if has_ingested_document(
            qdrant_client,
            doc_id=meta.doc_id,
            company_id=meta.company_id,
        ):
            return None

        embedder = _get_embedder_service()

        async def _embed_text(text: str) -> list[float]:
            return await embedder.embed_text(text)

        result = await ingest_document_async(
            meta,
            qdrant_client,
            embed_fn=_embed_text,
        )
    except Exception as exc:
        raise ApiError(500, "INGESTION_ERROR", f"Ingestion failed: {exc}") from exc

    if result.reason == "low_quality_document":
        raise ApiError(
            422,
            "LOW_QUALITY_DOCUMENT",
            (
                "Document could not be parsed reliably "
                f"(quality_tier={result.quality_tier}, min_confidence={result.min_confidence:.2f})"
            ),
        )

    if result.ingested <= 0:
        reason = result.reason or "unknown"
        raise ApiError(500, "INGESTION_ERROR", f"Ingestion produced no sections (reason={reason})")

    return result


def _file_base_path() -> Path:
    raw = os.getenv("FILE_BASE_PATH", ".")
    return Path(raw).expanduser().resolve()


def _resolve_relative_file_path(file_path: str) -> Path:
    base = _file_base_path()
    requested = Path(file_path).expanduser()
    full_path = requested.resolve() if requested.is_absolute() else (base / requested).resolve()
    try:
        if not requested.is_absolute():
            full_path.relative_to(base)
    except ValueError as exc:  # pragma: no cover - defense in depth after model validation
        raise ApiError(422, "VALIDATION_ERROR", "file_path escapes FILE_BASE_PATH") from exc
    return full_path


def _cache_key(path: Path) -> str:
    stat = path.stat()
    return f"{path}:{stat.st_mtime_ns}:{stat.st_size}"


def _derive_section_stats(sections: list[ParsedSection]) -> tuple[int, int]:
    if not sections:
        return (0, 0)

    has_llm_decisions = any(section.llm_valid is not None for section in sections)
    if not has_llm_decisions:
        return (len(sections), 0)

    analyzed = sum(section.llm_valid is True for section in sections)
    skipped = sum(section.llm_valid is False for section in sections)

    # If the model returned malformed output for some sections, count them as analyzed.
    undecided = len(sections) - analyzed - skipped
    analyzed += undecided
    return (analyzed, skipped)


def _avg_confidence(sections: list[ParsedSection]) -> float:
    if not sections:
        return 0.0
    return round(sum(float(s.extraction_confidence) for s in sections) / len(sections), 2)


def _norm_clause(norm: str) -> str:
    mapping = {
        "ISO 9001": "ISO 9001 7.5.3",
        "ISO 14001": "ISO 14001 8.1",
        "ISO 22000": "ISO 22000 8.5",
        "ISO 45001": "ISO 45001 8.1",
    }
    return mapping.get(norm, f"{norm} 8.1")


def _best_evidence(sections: list[ParsedSection]) -> str:
    for section in sections:
        if section.raw_text.strip():
            return f"{section.title}"
    return "No section evidence extracted"


def _build_report(meta: DocumentMeta, sections: list[ParsedSection], skipped: int) -> ReportPayload:
    avg_conf = _avg_confidence(sections)
    evidence = _best_evidence(sections)

    matrix: list[CoverageItem] = []
    for norm in meta.applicable_norms:
        status = "PARTIAL" if skipped > 0 else "COVERED"
        gaps = ["Some sections were filtered as non-actionable"] if skipped > 0 else []
        matrix.append(
            CoverageItem(
                clause=_norm_clause(norm),
                status=status,
                evidence=evidence,
                gaps=gaps,
                confidence=avg_conf,
            )
        )

    actions: list[ActionItem] = []
    if skipped > 0:
        actions.append(
            ActionItem(
                action="Review skipped sections and enrich missing compliance details",
                clause=_norm_clause(meta.applicable_norms[0]),
                priority="HIGH",
                section="Document review",
            )
        )

    if all(item.status == "COVERED" for item in matrix):
        overall_status = "COVERED"
    elif any(item.status == "PARTIAL" for item in matrix):
        overall_status = "PARTIAL"
    else:
        overall_status = "MISSING"

    return ReportPayload(
        executive_summary=(
            f"Document {meta.doc_code} ({meta.designation}) analyzed against "
            f"{', '.join(meta.applicable_norms)}."
        ),
        coverage_matrix=matrix,
        action_plan=actions,
        overall_status=overall_status,
    )


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for err in errors:
        item = dict(err)
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {
                key: (str(value) if isinstance(value, Exception) else value)
                for key, value in ctx.items()
            }
        sanitized.append(item)
    return sanitized


async def _run_or_load_state(full_path: Path) -> dict[str, Any]:
    key = _cache_key(full_path)
    cached = _STATE_CACHE.get(key)
    if cached is not None:
        return cached

    runner = _get_pipeline_runner()
    state = await runner(str(full_path))
    _STATE_CACHE[key] = state
    return state


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent IA 2 Analyze API",
        version="1.0.0",
        description="QALITAS -> Agent IA 2 synchronous document analyze contract.",
    )

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        global _QDRANT_CLIENT, _EMBEDDER_SERVICE

        if _EMBEDDER_SERVICE is not None:
            try:
                await _EMBEDDER_SERVICE.close()
            finally:
                _EMBEDDER_SERVICE = None

        close = getattr(_QDRANT_CLIENT, "close", None)
        if callable(close):
            close()
        _QDRANT_CLIENT = None

    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        payload = ErrorResponse(code=exc.code, detail=exc.detail)
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        payload = ErrorResponse(
            code="VALIDATION_ERROR",
            detail="Request validation failed",
            errors=_sanitize_validation_errors(exc.errors()),
        )
        return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        payload = ErrorResponse(code="INTERNAL_ERROR", detail=str(exc) or "Unexpected error")
        return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))

    @app.post(
        "/analyze",
        response_model=AnalyzeSuccessResponse,
        responses={
            400: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    async def analyze(payload: AnalyzeRequest) -> AnalyzeSuccessResponse:
        if payload.options.format != "json":
            raise ApiError(
                400,
                "FORMAT_NOT_AVAILABLE",
                "Only options.format='json' is available in MVP",
            )

        doc_meta = DocumentMeta.from_request(
            doc=payload.document.model_dump(mode="json"),
            session=payload.session.model_dump(mode="json"),
        )

        if not doc_meta.applicable_norms:
            raise ApiError(400, "NO_NORMS", "All norm flags (Q/E/S/H) are false")

        full_path = _resolve_relative_file_path(doc_meta.file_path)
        if not full_path.exists():
            raise ApiError(404, "FILE_NOT_FOUND", "file_path does not exist")
        if full_path.suffix.lower() not in {".pdf", ".docx"}:
            raise ApiError(422, "UNSUPPORTED_FORMAT", "Expected .pdf or .docx document")

        # Ingestion parser expects a concrete path; normalize to resolved absolute path.
        doc_meta.file_path = str(full_path)
        await _ingest_if_needed(doc_meta)

        state = await _run_or_load_state(full_path)
        if state.get("error"):
            message = str(state["error"])
            if "File not found" in message:
                raise ApiError(404, "FILE_NOT_FOUND", "file_path does not exist")
            raise ApiError(500, "INTERNAL_ERROR", message)

        sections: list[ParsedSection] = list(state.get("sections") or [])
        quality_tier, min_confidence, low_quality_flag = assess_quality(sections)
        if low_quality_flag:
            raise ApiError(
                422,
                "LOW_QUALITY_DOCUMENT",
                (
                    "Document could not be parsed reliably "
                    f"(quality_tier={quality_tier}, min_confidence={min_confidence:.2f})"
                ),
            )

        analyzed, skipped = _derive_section_stats(sections)
        report = _build_report(doc_meta, sections, skipped=skipped)

        return AnalyzeSuccessResponse(
            status="completed",
            doc_id=doc_meta.doc_id,
            doc_code=doc_meta.doc_code,
            sections_analyzed=analyzed,
            sections_skipped=skipped,
            applicable_norms=doc_meta.applicable_norms,
            report=report,
            report_url=None,
        )

    return app


app = create_app()
