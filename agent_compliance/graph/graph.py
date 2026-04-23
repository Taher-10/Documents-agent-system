from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import (
    extract_sections_node,
    handle_error_node,
    parse_document_node,
    validate_input,
)
from .sections_llm import sections_llm_node
from .state import AgentState


def _route_after_validate(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "parse_document"


def _route_after_parse(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "extract_sections"


def _route_after_extract_sections(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "sections_llm"


def _route_after_sections_llm(state: AgentState) -> str:
    return "handle_error" if state.get("error") else END


def build_graph(checkpointer: InMemorySaver | None = None) -> StateGraph:
    if checkpointer is None:
        checkpointer = InMemorySaver()

    return (
        StateGraph(AgentState)
        .add_node("validate_input", validate_input)
        .add_node("parse_document", parse_document_node)
        .add_node("extract_sections", extract_sections_node)
        .add_node("sections_llm", sections_llm_node)
        .add_node("handle_error", handle_error_node)
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
            _route_after_extract_sections,
            ["sections_llm", "handle_error"],
        )
        .add_conditional_edges(
            "sections_llm",
            _route_after_sections_llm,
            [END, "handle_error"],
        )
        .add_edge("handle_error", END)
        .compile(checkpointer=checkpointer)
    )


graph = build_graph()
