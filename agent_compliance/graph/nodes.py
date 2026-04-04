from __future__ import annotations

from pathlib import Path

from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from agent_compliance.classification import RetrievalScope, classify_for_retrieval
from agent_compliance.pdf_parser import assess_quality, docling_to_sections, parse_document
from agent_compliance.tools.db_tool import fetch_document_metadata

from .state import AgentState


def _emit(node: str, event: str, msg: str) -> None:
    """Push a structured log event through the LangGraph stream writer."""
    get_stream_writer()({"node": node, "event": event, "msg": msg})


# ---------------------------------------------------------------------------
# V1 nodes
# ---------------------------------------------------------------------------


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


def assess_quality_node(state: AgentState) -> dict:
    _emit("assess_quality", "start", "Evaluating extraction quality...")
    tier, min_conf, low_flag = assess_quality(state["sections"])
    flag_note = " — low quality flag raised" if low_flag else ""
    _emit("assess_quality", "done", f"Tier {tier}, confidence {min_conf:.2f}{flag_note}")
    return {
        "quality_tier": tier,
        "min_confidence": min_conf,
        "low_quality_flag": low_flag,
        "status": "done",
    }


def handle_error_node(state: AgentState) -> dict:
    _emit("handle_error", "error", state.get("error") or "Unknown error")
    return {"status": "error"}


# ---------------------------------------------------------------------------
# V2 nodes
# ---------------------------------------------------------------------------


def human_review_node(state: AgentState) -> dict:
    """Pause for human confirmation when document quality is Tier C.

    The node re-runs from the top on resume (LangGraph HITL pattern).
    Only ``_emit()`` is called before ``interrupt()`` — it is idempotent.
    """
    _emit("human_review", "start",
          f"Tier {state['quality_tier']} document (confidence {state['min_confidence']:.2f}) — waiting for review")
    decision = interrupt({
        "question": "Document quality is Tier C (low confidence). Proceed with classification?",
        "quality_tier": state["quality_tier"],
        "min_confidence": state["min_confidence"],
        "options": ["proceed", "abort"],
    })
    if decision == "abort":
        _emit("human_review", "error", "Aborted by user — low quality document")
        return {"error": "Classification aborted by user (low quality).", "status": "error"}
    _emit("human_review", "done", "User confirmed — proceeding despite low quality")
    return {}


def fetch_metadata_node(state: AgentState) -> dict:
    """Look up document registry metadata from documents_system.db."""
    _emit("fetch_metadata", "start", "Looking up document registry...")
    meta = fetch_document_metadata(state["document_path"])
    code_note = meta.get("code") or "not found in registry"
    _emit(
        "fetch_metadata",
        "done",
        f"systeme={meta.get('systeme', '?')}, type={meta.get('types_documents', '?')} [{code_note}]",
    )
    return {"registry_metadata": meta}


def classify_sections_node(state: AgentState) -> dict:
    """Enrich each section in-place with its RetrievalScope, then produce a merged doc-level scope."""
    sections = state["sections"]
    _emit("classify_sections", "start", f"Classifying {len(sections)} sections...")
    meta = state.get("registry_metadata") or {}
    for section in sections:
        section.scope = classify_for_retrieval(section, meta)
    doc_scope = _merge_scopes([s.scope for s in sections])
    _emit(
        "classify_sections",
        "done",
        f"domains={doc_scope.domains}, families={doc_scope.clause_families}, "
        f"clauses={doc_scope.specific_clauses}",
    )
    return {
        "sections": sections,        # sections now carry .scope on each item
        "document_scope": doc_scope,
        "status": "classified",
    }


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _merge_scopes(scopes: list[RetrievalScope]) -> RetrievalScope:
    """Merge a list of per-section RetrievalScopes into one document-level scope."""
    if not scopes:
        return RetrievalScope(
            domains=[],
            domain_confidence=0.0,
            doc_type=None,
            doc_type_confidence=0.0,
            clause_families=[],
            specific_clauses=[],
            confidence=0.0,
            evidence=[],
        )

    seen_domains: list[str] = []
    seen_families: list[str] = []
    seen_clauses: list[str] = []
    seen_evidence: list[str] = []
    doc_type = None
    doc_type_conf = 0.0
    total_conf = 0.0

    for scope in scopes:
        for d in scope.domains:
            if d not in seen_domains:
                seen_domains.append(d)
        for f in scope.clause_families:
            if f not in seen_families:
                seen_families.append(f)
        for c in scope.specific_clauses:
            if c not in seen_clauses:
                seen_clauses.append(c)
        for e in scope.evidence:
            if e not in seen_evidence:
                seen_evidence.append(e)
        if doc_type is None and scope.doc_type is not None:
            doc_type = scope.doc_type
            doc_type_conf = scope.doc_type_confidence
        total_conf += scope.confidence

    avg_conf = round(total_conf / len(scopes), 3)

    return RetrievalScope(
        domains=seen_domains,
        domain_confidence=scopes[0].domain_confidence,
        doc_type=doc_type,
        doc_type_confidence=doc_type_conf,
        clause_families=seen_families,
        specific_clauses=seen_clauses,
        confidence=avg_conf,
        evidence=seen_evidence,
    )
