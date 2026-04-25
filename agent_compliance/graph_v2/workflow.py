from __future__ import annotations

from functools import partial
from typing import Any

from langgraph.graph import END, StateGraph
from qdrant_client import QdrantClient

from agent_compliance.graph_v2.nodes.loader import loader_node
from agent_compliance.graph_v2.state import ComplianceState


def build_graph(qdrant: QdrantClient, db_path: str) -> Any:
    graph = StateGraph(ComplianceState)
    graph.add_node("loader", partial(loader_node, qdrant=qdrant, db_path=db_path))
    graph.set_entry_point("loader")
    graph.add_edge("loader", END)
    return graph.compile()
