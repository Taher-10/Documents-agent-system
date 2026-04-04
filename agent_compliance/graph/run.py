from __future__ import annotations

import argparse
import json
from typing import Iterator

from .graph import graph

_EVENT_PREFIX = {"start": "...", "done": "✓", "error": "✗"}


def _initial_state(document_path: str) -> dict:
    return {
        "document_path": document_path,
        "parse_result": None,
        "sections": [],
        "quality_tier": None,
        "min_confidence": None,
        "low_quality_flag": False,
        "error": None,
        "status": "pending",
    }


def run(document_path: str) -> dict:
    """Invoke the graph and return the final state. Used by the API layer."""
    return graph.invoke(_initial_state(document_path))


def stream_run(document_path: str) -> Iterator[dict]:
    """Stream log events from the graph as they are emitted.

    Each yielded item is a dict: {"node": str, "event": str, "msg": str}.
    The last item has event == "final" and carries the full result state.
    """
    final_state: dict = {}
    for mode, chunk in graph.stream(
        _initial_state(document_path),
        stream_mode=["custom", "values"],
    ):
        if mode == "custom" and isinstance(chunk, dict) and "node" in chunk:
            yield chunk
        elif mode == "values":
            final_state = chunk  # updated after every node; last one is the final state
    yield {"node": "__final__", "event": "final", "msg": "", "state": final_state}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compliance document parser agent (v1).")
    p.add_argument("file_path", nargs="+", help="Path to PDF or DOCX file.")
    p.add_argument("--json", action="store_true", help="Print sections as JSON.")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    file_path = " ".join(args.file_path)

    result: dict = {}
    for event in stream_run(file_path):
        if event["event"] == "final":
            result = event["state"]
            break
        prefix = _EVENT_PREFIX.get(event["event"], "  ")
        print(f"  {prefix} [{event['node']}] {event['msg']}")

    print()
    if result.get("error"):
        print(f"Error: {result['error']}")
        return 1

    print(f"Quality tier  : {result['quality_tier']}")
    print(f"Min confidence: {result['min_confidence']:.2f}")
    print(f"Low quality   : {result['low_quality_flag']}")
    print(f"Sections      : {len(result['sections'])}")

    if args.json:
        print(json.dumps([s.to_dict() for s in result["sections"]], ensure_ascii=False, indent=2))
    else:
        for s in result["sections"]:
            print(f"  [{s.section_type.value:16s}] {s.title}  (p{s.page_range[0]}-{s.page_range[1]})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
