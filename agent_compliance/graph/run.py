from __future__ import annotations

import argparse
import asyncio
from typing import AsyncIterator

from dotenv import load_dotenv

load_dotenv()

from .nodes import (
    extract_sections_node,
    handle_error_node,
    parse_document_node,
    validate_input,
)
from .sections_llm import sections_llm_node
from .state import AgentState

_EVENT_PREFIX = {"start": "...", "done": "✓", "error": "✗"}


def _initial_state(document_path: str) -> AgentState:
    return {
        "document_path": document_path,
        "parse_result": None,
        "sections": None,
        "error": None,
        "status": "pending",
    }


def _noop_emit(_node: str, _event: str, _msg: str) -> None:
    pass


def _apply_update(state: AgentState, update: dict | None) -> None:
    if update:
        state.update(update)


async def _run_pipeline(
    state: AgentState,
    emit_fn,
) -> AgentState:
    try:
        _apply_update(state, validate_input(state, emit_fn=emit_fn))
        if state.get("error"):
            _apply_update(state, handle_error_node(state, emit_fn=emit_fn))
            return state

        _apply_update(state, parse_document_node(state, emit_fn=emit_fn))
        if state.get("error"):
            _apply_update(state, handle_error_node(state, emit_fn=emit_fn))
            return state

        _apply_update(state, extract_sections_node(state, emit_fn=emit_fn))
        if state.get("error"):
            _apply_update(state, handle_error_node(state, emit_fn=emit_fn))
            return state

        _apply_update(state, await sections_llm_node(state, emit_fn=emit_fn))
        if state.get("error"):
            _apply_update(state, handle_error_node(state, emit_fn=emit_fn))

        return state
    except Exception as exc:  # pragma: no cover - defensive top-level guard
        state["error"] = str(exc)
        state["status"] = "error"
        try:
            _apply_update(state, handle_error_node(state, emit_fn=emit_fn))
        except Exception:
            pass
        return state


async def run(
    document_path: str,
    thread_id: str | None = None,
) -> AgentState:
    """Run the compliance pipeline and return the final state."""
    _ = thread_id  # kept for backward-compatible signature
    return await _run_pipeline(_initial_state(document_path), _noop_emit)


async def stream_run(
    document_path: str,
    thread_id: str | None = None,
) -> AsyncIterator[dict]:
    """Stream log events from the orchestrator as they are emitted.

    Each yielded item is a dict: {"node": str, "event": str, "msg": str}.
    The last item has event == "final" and carries the full result state.
    """
    _ = thread_id  # kept for backward-compatible signature
    event_queue: asyncio.Queue[dict] = asyncio.Queue()

    def emit(node: str, event: str, msg: str) -> None:
        event_queue.put_nowait({"node": node, "event": event, "msg": msg})

    state = _initial_state(document_path)
    task = asyncio.create_task(_run_pipeline(state, emit))

    while True:
        if task.done() and event_queue.empty():
            break
        try:
            event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            continue
        yield event

    final_state = await task
    yield {"node": "__final__", "event": "final", "msg": "", "state": final_state}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compliance document parser agent.")
    p.add_argument("file_path", nargs="+", help="Path to PDF or DOCX file.")
    p.add_argument("--thread-id", default=None, help="Thread ID for this run.")
    return p


async def _async_main(args: argparse.Namespace) -> int:
    file_path = " ".join(args.file_path)

    async for event in stream_run(file_path, thread_id=args.thread_id):
        if event["event"] == "final":
            result = event["state"]
            break
        prefix = _EVENT_PREFIX.get(event["event"], "  ")
        print(f"  {prefix} [{event['node']}] {event['msg']}")

    print()

    if result.get("error"):
        print(f"Error: {result['error']}")
        return 1

    parse_result = result.get("parse_result")
    if parse_result:
        pages = parse_result.pages or len(parse_result.page_texts or []) or "?"
        print(f"Pages parsed  : {pages}")
    sections = result.get("sections")
    if sections is not None:
        print(f"Sections found: {len(sections)}")
    print(f"Status        : {result['status']}")
    return 0


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
