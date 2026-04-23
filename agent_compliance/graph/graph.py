from __future__ import annotations

from typing import Any, AsyncIterator

from .run import run as orchestrator_run
from .run import stream_run
from .state import AgentState


class ComplianceOrchestrator:
    """Compatibility adapter exposing ainvoke/astream over the plain orchestrator."""

    async def ainvoke(self, state: AgentState, config: dict | None = None) -> AgentState:
        thread_id = _extract_thread_id(config)
        return await orchestrator_run(state["document_path"], thread_id=thread_id)

    async def astream(
        self,
        state: AgentState,
        config: dict | None = None,
        stream_mode: list[str] | None = None,
    ) -> AsyncIterator[tuple[str, dict]]:
        modes = set(stream_mode or ["custom", "values"])
        thread_id = _extract_thread_id(config)

        async for event in stream_run(state["document_path"], thread_id=thread_id):
            if event.get("event") == "final":
                if "values" in modes:
                    yield "values", event["state"]
            elif "custom" in modes:
                yield "custom", event


def _extract_thread_id(config: dict | None) -> str | None:
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    thread_id = configurable.get("thread_id")
    return thread_id if isinstance(thread_id, str) else None


def build_graph(checkpointer: Any | None = None) -> ComplianceOrchestrator:
    """Return a plain Python orchestrator (no LangGraph runtime)."""
    _ = checkpointer  # kept for backward-compatible signature
    return ComplianceOrchestrator()


graph = build_graph()
