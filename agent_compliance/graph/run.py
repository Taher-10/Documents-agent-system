from __future__ import annotations

import argparse
import json
import uuid
from typing import Iterator

from langgraph.types import Command

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
        "registry_metadata": {},
        "document_scope": None,
        "error": None,
        "status": "pending",
    }


def _config(thread_id: str | None) -> dict:
    return {"configurable": {"thread_id": thread_id or str(uuid.uuid4())}}


def run(document_path: str, thread_id: str | None = None) -> dict:
    """Invoke the graph and return the final state. Used by the API layer."""
    return graph.invoke(_initial_state(document_path), _config(thread_id))


def stream_run(document_path: str, thread_id: str | None = None) -> Iterator[dict]:
    """Stream log events from the graph as they are emitted.

    Each yielded item is a dict: {"node": str, "event": str, "msg": str}.
    The last item has event == "final" and carries the full result state.

    If the graph pauses at an interrupt (low-quality document), the final
    item will instead have event == "interrupted" and carry the interrupt
    payload so callers can surface it to the user and call ``resume_run()``.
    """
    tid = thread_id or str(uuid.uuid4())
    config = _config(tid)
    final_state: dict = {}
    interrupt_payload: list = []

    for mode, chunk in graph.stream(
        _initial_state(document_path),
        config,
        stream_mode=["custom", "values", "updates"],
    ):
        if mode == "custom" and isinstance(chunk, dict) and "node" in chunk:
            yield chunk
        elif mode == "values":
            final_state = chunk
        elif mode == "updates" and "__interrupt__" in chunk:
            interrupt_payload = chunk["__interrupt__"]

    if interrupt_payload:
        yield {
            "node": "__interrupt__",
            "event": "interrupted",
            "msg": "Graph paused — human review required",
            "thread_id": tid,
            "interrupt": [
                {"value": i.value} for i in interrupt_payload
            ],
        }
    else:
        yield {"node": "__final__", "event": "final", "msg": "", "state": final_state}


def resume_run(thread_id: str, decision: str) -> dict:
    """Resume a paused graph after a human_review interrupt.

    Args:
        thread_id: The thread ID from the interrupted ``stream_run()`` event.
        decision: ``"proceed"`` to continue classification or ``"abort"`` to stop.

    Returns:
        Final agent state after resuming.
    """
    return graph.invoke(Command(resume=decision), _config(thread_id))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compliance document parser + classifier agent (v2).")
    p.add_argument("file_path", nargs="+", help="Path to PDF or DOCX file.")
    p.add_argument("--json", action="store_true", help="Print sections as JSON.")
    p.add_argument("--thread-id", default=None, help="Thread ID for resuming an interrupted run.")
    p.add_argument(
        "--resume",
        choices=["proceed", "abort"],
        default=None,
        help="Resume a paused graph: 'proceed' or 'abort'. Requires --thread-id.",
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()
    file_path = " ".join(args.file_path)

    # --- Resume path ---
    if args.resume:
        if not args.thread_id:
            print("Error: --resume requires --thread-id")
            return 1
        result = resume_run(args.thread_id, args.resume)
        _print_result(result, args.json)
        return 0 if not result.get("error") else 1

    # --- Normal run path ---
    result: dict = {}
    interrupted_event: dict | None = None

    for event in stream_run(file_path, thread_id=args.thread_id):
        if event["event"] == "final":
            result = event["state"]
            break
        if event["event"] == "interrupted":
            interrupted_event = event
            break
        prefix = _EVENT_PREFIX.get(event["event"], "  ")
        print(f"  {prefix} [{event['node']}] {event['msg']}")

    print()

    if interrupted_event:
        payload = interrupted_event["interrupt"][0]["value"]
        print(f"⏸  PAUSED — {payload['question']}")
        print(f"   Quality tier : {payload['quality_tier']}")
        print(f"   Min confidence: {payload['min_confidence']:.2f}")
        print(f"\n   Resume with:")
        print(f"     python -m agent_compliance.graph.run \"{file_path}\" "
              f"--thread-id {interrupted_event['thread_id']} --resume proceed")
        print(f"     python -m agent_compliance.graph.run \"{file_path}\" "
              f"--thread-id {interrupted_event['thread_id']} --resume abort")
        return 0

    _print_result(result, args.json)
    return 0 if not result.get("error") else 1


def _print_result(result: dict, print_json: bool) -> None:
    if result.get("error"):
        print(f"Error: {result['error']}")
        return

    print(f"Quality tier  : {result['quality_tier']}")
    print(f"Min confidence: {result['min_confidence']:.2f}")
    print(f"Low quality   : {result['low_quality_flag']}")
    print(f"Sections      : {len(result['sections'])}")

    doc_scope = result.get("document_scope")
    if doc_scope:
        print(f"\nDocument scope:")
        print(f"  Domains       : {doc_scope.domains}")
        print(f"  Doc type      : {doc_scope.doc_type} (conf {doc_scope.doc_type_confidence:.2f})")
        print(f"  Clause families: {doc_scope.clause_families}")
        print(f"  Specific clauses: {doc_scope.specific_clauses}")
        print(f"  Confidence    : {doc_scope.confidence:.3f}")

    if print_json:
        print(json.dumps([s.to_dict() for s in result["sections"]], ensure_ascii=False, indent=2))
    else:
        for s in result["sections"]:
            scope = s.scope
            clause_hint = f" → {scope.specific_clauses}" if scope and scope.specific_clauses else ""
            print(f"  [{s.section_type.value:16s}] {s.title}  (p{s.page_range[0]}-{s.page_range[1]}){clause_hint}")


if __name__ == "__main__":
    raise SystemExit(main())
