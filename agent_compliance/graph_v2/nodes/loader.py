from __future__ import annotations

from qdrant_client import QdrantClient

from agent_compliance.graph_v2.state import ComplianceState
from agent_compliance.ingestion.qhse_reader import read_document_sections
from agent_compliance.retrieval.clause_store import load_clause_menu


def loader_node(state: ComplianceState, qdrant: QdrantClient, db_path: str) -> dict:
    sections_result = read_document_sections(
        qdrant_client=qdrant,
        doc_id=state["doc_id"],
        company_id=state["company_id"],
    )
    menu = load_clause_menu(
        state["applicable_norms"],
        language=state["language"],
        db_path=db_path,
    )
    metadata = sections_result.metadata
    return {
        "sections": sections_result.sections,
        "clause_menu": menu,
        "doc_code": metadata["doc_code"] if metadata["doc_code"] is not None else state.get("doc_code"),
        "doc_type": metadata["doc_type"] if metadata["doc_type"] is not None else state.get("doc_type"),
        "doc_level": metadata["doc_level"] if metadata["doc_level"] is not None else state.get("doc_level"),
    }
