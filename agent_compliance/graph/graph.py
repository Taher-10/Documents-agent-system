from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from rag.retrival import RetrievalService

from .nodes import (
    assess_quality_node,
    classify_sections_node,
    extract_sections_node,
    fetch_metadata_node,
    handle_error_node,
    human_review_node,
    parse_document_node,
    validate_input,
)
from .retrieve_node import make_retrieve_node
from .sections_llm import sections_llm_node
from .state import AgentState


def _route_after_validate(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "parse_document"


def _route_after_parse(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "extract_sections"


def _route_after_sections(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "assess_quality"


def _route_after_quality(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    if state.get("low_quality_flag"):
        return "human_review"
    return "fetch_metadata"


def _route_after_human_review(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "fetch_metadata"


def _route_after_retrieve(state: AgentState) -> str:
    return "handle_error" if state.get("error") else END


def build_graph(
    checkpointer: InMemorySaver | None = None,
    retrieval_service: RetrievalService | None = None,
) -> StateGraph:
    if checkpointer is None:
        checkpointer = InMemorySaver()

    if retrieval_service is None:
        async def _noop_retrieve(state: AgentState) -> dict:
            return {"section_retrievals": [], "status": "retrieved"}
        retrieve_fn = _noop_retrieve
    else:
        retrieve_fn = make_retrieve_node(retrieval_service)

    return (
        StateGraph(AgentState)
        # V1 nodes
        .add_node("validate_input", validate_input)
        .add_node("parse_document", parse_document_node)
        .add_node("extract_sections", extract_sections_node)
        .add_node("assess_quality", assess_quality_node)
        .add_node("handle_error", handle_error_node)
        # V2 nodes
        .add_node("human_review", human_review_node)
        .add_node("fetch_metadata", fetch_metadata_node)
        .add_node("classify_sections", classify_sections_node)
        # V3 nodes — LLM section filter + retrieval orchestrator
        .add_node("sections_llm", sections_llm_node)
        .add_node("retrieve", retrieve_fn)
        # Edges — V1
        .add_edge(START, "validate_input")
        .add_conditional_edges(
            "validate_input",
            _route_after_validate,
            ["parse_document", "handle_error"],
        )
        .add_conditional_edges(
            "parse_document",
            _route_after_parse,
            ["extract_sections", "handle_error"],
        )
        .add_conditional_edges(
            "extract_sections",
            _route_after_sections,
            ["assess_quality", "handle_error"],
        )
        # Edges — V2
        .add_conditional_edges(
            "assess_quality",
            _route_after_quality,
            ["human_review", "fetch_metadata", "handle_error"],
        )
        .add_conditional_edges(
            "human_review",
            _route_after_human_review,
            ["fetch_metadata", "handle_error"],
        )
        .add_edge("fetch_metadata", "classify_sections")
        # Edges — V3
        .add_edge("classify_sections", "sections_llm")
        .add_edge("sections_llm", "retrieve")
        .add_conditional_edges("retrieve", _route_after_retrieve, ["handle_error", END])
        .add_edge("handle_error", END)
        .compile(checkpointer=checkpointer)
    )


graph = build_graph()
