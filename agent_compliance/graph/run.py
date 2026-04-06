from __future__ import annotations

import argparse
import asyncio
import uuid
from typing import AsyncIterator

from .graph import build_graph

_EVENT_PREFIX = {"start": "...", "done": "✓", "error": "✗"}


def _initial_state(document_path: str) -> dict:
    return {
        "document_path": document_path,
        "parse_result": None,
        "error": None,
        "status": "pending",
    }


def _config(thread_id: str | None) -> dict:
    return {"configurable": {"thread_id": thread_id or str(uuid.uuid4())}}


async def run(
    document_path: str,
    thread_id: str | None = None,
) -> dict:
    """Invoke the graph and return the final state. Used by the API layer."""
    g = build_graph()
    return await g.ainvoke(_initial_state(document_path), _config(thread_id))


async def stream_run(
    document_path: str,
    thread_id: str | None = None,
) -> AsyncIterator[dict]:
    """Stream log events from the graph as they are emitted.

    Each yielded item is a dict: {"node": str, "event": str, "msg": str}.
    The last item has event == "final" and carries the full result state.
    """
    tid = thread_id or str(uuid.uuid4())
    config = _config(tid)
    final_state: dict = {}

    g = build_graph()
    async for mode, chunk in g.astream(
        _initial_state(document_path),
        config,
        stream_mode=["custom", "values"],
    ):
        if mode == "custom" and isinstance(chunk, dict) and "node" in chunk:
            yield chunk
        elif mode == "values":
            final_state = chunk

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
    print(f"Status        : {result['status']}")
    return 0


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
