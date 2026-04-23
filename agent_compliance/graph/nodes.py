from __future__ import annotations

from pathlib import Path
from typing import Callable

from agent_compliance.pdf_parser import docling_to_sections, parse_document

from .state import AgentState


EmitFn = Callable[[str, str, str], None]


def _noop_emit(_node: str, _event: str, _msg: str) -> None:
    pass


def _emit(node: str, event: str, msg: str) -> None:
    """Default local emitter used when no runtime stream emitter is injected."""
    _noop_emit(node, event, msg)


def validate_input(state: AgentState, emit_fn: EmitFn | None = None) -> dict:
    emitter = emit_fn or _emit
    path = Path(state["document_path"])
    emitter("validate_input", "start", f"Checking file: {path.name}")
    if not path.exists():
        msg = f"File not found: {path}"
        emitter("validate_input", "error", msg)
        return {"error": msg, "status": "error"}
    if path.suffix.lower() not in {".pdf", ".docx"}:
        msg = f"Unsupported format '{path.suffix}' — expected .pdf or .docx"
        emitter("validate_input", "error", msg)
        return {"error": msg, "status": "error"}
    emitter("validate_input", "done", f"File OK ({path.suffix.lstrip('.')})")
    return {"error": None, "status": "validated"}


def parse_document_node(state: AgentState, emit_fn: EmitFn | None = None) -> dict:
    emitter = emit_fn or _emit
    emitter("parse_document", "start", "Converting document with Docling (may take a moment)...")
    try:
        result = parse_document(state["document_path"], remove_headers_footers=True)
        pages = result.pages or len(result.page_texts or []) or "?"
        emitter("parse_document", "done", f"{pages} pages extracted, headers/footers removed")
        return {"parse_result": result, "status": "parsed"}
    except Exception as exc:
        emitter("parse_document", "error", str(exc))
        return {"error": str(exc), "status": "error"}


def extract_sections_node(state: AgentState, emit_fn: EmitFn | None = None) -> dict:
    emitter = emit_fn or _emit
    emitter("extract_sections", "start", "Splitting document into logical sections...")
    try:
        sections = docling_to_sections(state["parse_result"])
        emitter("extract_sections", "done", f"{len(sections)} sections identified")
        return {"sections": sections, "status": "sectioned"}
    except Exception as exc:
        emitter("extract_sections", "error", str(exc))
        return {"error": str(exc), "status": "error"}


def handle_error_node(state: AgentState, emit_fn: EmitFn | None = None) -> dict:
    emitter = emit_fn or _emit
    emitter("handle_error", "error", state.get("error") or "Unknown error")
    return {"status": "error"}
