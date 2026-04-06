from __future__ import annotations

from pathlib import Path

from langgraph.config import get_stream_writer

from agent_compliance.pdf_parser import docling_to_sections, parse_document

from .state import AgentState


def _emit(node: str, event: str, msg: str) -> None:
    """Push a structured log event through the LangGraph stream writer."""
    get_stream_writer()({"node": node, "event": event, "msg": msg})


def validate_input(state: AgentState) -> dict:
    path = Path(state["document_path"])
    _emit("validate_input", "start", f"Checking file: {path.name}")
    if not path.exists():
        msg = f"File not found: {path}"
        _emit("validate_input", "error", msg)
        return {"error": msg, "status": "error"}
    if path.suffix.lower() not in {".pdf", ".docx"}:
        msg = f"Unsupported format '{path.suffix}' — expected .pdf or .docx"
        _emit("validate_input", "error", msg)
        return {"error": msg, "status": "error"}
    _emit("validate_input", "done", f"File OK ({path.suffix.lstrip('.')})")
    return {"error": None, "status": "validated"}


def parse_document_node(state: AgentState) -> dict:
    _emit("parse_document", "start", "Converting document with Docling (may take a moment)...")
    try:
        result = parse_document(state["document_path"], remove_headers_footers=True)
        pages = result.pages or len(result.page_texts or []) or "?"
        _emit("parse_document", "done", f"{pages} pages extracted, headers/footers removed")
        return {"parse_result": result, "status": "parsed"}
    except Exception as exc:
        _emit("parse_document", "error", str(exc))
        return {"error": str(exc), "status": "error"}


def extract_sections_node(state: AgentState) -> dict:
    _emit("extract_sections", "start", "Splitting document into logical sections...")
    try:
        sections = docling_to_sections(state["parse_result"])
        _emit("extract_sections", "done", f"{len(sections)} sections identified")
        return {"sections": sections, "status": "sectioned"}
    except Exception as exc:
        _emit("extract_sections", "error", str(exc))
        return {"error": str(exc), "status": "error"}


def handle_error_node(state: AgentState) -> dict:
    _emit("handle_error", "error", state.get("error") or "Unknown error")
    return {"status": "error"}
