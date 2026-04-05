"""
Quick smoke-test for sections_llm_node.

Runs the compliance graph up to (and including) sections_llm — WITHOUT retrieval —
for each document path passed on the command line, and prints a before/after
comparison of the classified sections.

Usage (from repo root):
    python -m agent_compliance.test_sections_llm \
        "agent_compliance/qhme_docs/PQ-PROD-01 02 Procédure de gestion des gabarits.pdf" \
        "agent_compliance/qhme_docs/General Requirements for Infrequently performed techniques.pdf"

Add --language FR  for French retrieval language (affects classify_sections vocabulary).
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from .graph import build_graph
from .graph.state import AgentState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snapshot_sections(sections: list) -> list[dict]:
    """Capture scope state at a point in time (deep enough to survive later mutations)."""
    snaps = []
    for s in sections:
        scope = s.scope
        snaps.append({
            "id": s.id,
            "title": s.title,
            "section_type": s.section_type.value if hasattr(s.section_type, "value") else str(s.section_type),
            "page_range": s.page_range,
            "has_scope": scope is not None,
            "domains": list(scope.domains) if scope else [],
            "clause_families": list(scope.clause_families) if scope else [],
            "specific_clauses": list(scope.specific_clauses) if scope else [],
            "confidence": scope.confidence if scope else None,
        })
    return snaps


def _snap_row(snap: dict) -> str:
    if not snap["has_scope"] or not snap["domains"]:
        families = "—"
        specifics = "—"
        conf = "—"
        domains = "—"
    else:
        families = ", ".join(snap["clause_families"]) or "—"
        specifics = ", ".join(snap["specific_clauses"]) or "—"
        conf = f"{snap['confidence']:.2f}" if snap["confidence"] is not None else "—"
        domains = ", ".join(str(d) for d in snap["domains"]) or "—"
    pr = snap["page_range"]
    return (
        f"  [{snap['section_type']:18s}] "
        f"{snap['title'][:55]:<55s}  "
        f"p{pr[0]}-{pr[1]}  "
        f"fam=[{families}]  spec=[{specifics}]  conf={conf}  dom=[{domains}]"
    )


def _print_snapshot(snaps: list[dict], label: str) -> None:
    print(f"\n{'─' * 100}")
    print(f"  {label}  ({len(snaps)} sections total)")
    print(f"{'─' * 100}")
    classified = [s for s in snaps if s["has_scope"] and s["domains"]]
    unclassified = [s for s in snaps if s not in classified]
    if classified:
        print(f"  Classified ({len(classified)}):")
        for s in classified:
            print(_snap_row(s))
    if unclassified:
        print(f"  Unclassified / scope=None ({len(unclassified)}):")
        for s in unclassified:
            scope_note = "(scope=None)" if not s["has_scope"] else "(no domains)"
            print(f"    [{s['section_type']:18s}] {s['title'][:60]}  {scope_note}")


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


async def _run_document(file_path: str, language: str) -> None:
    print(f"\n{'═' * 100}")
    print(f"  DOCUMENT: {file_path}")
    print(f"  LANGUAGE: {language}")
    print(f"{'═' * 100}")

    # Build graph with no retrieval service so retrieve_node is a no-op
    g = build_graph(retrieval_service=None)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    initial = {
        "document_path": file_path,
        "parse_result": None,
        "sections": [],
        "quality_tier": None,
        "min_confidence": None,
        "low_quality_flag": False,
        "registry_metadata": {},
        "document_scope": None,
        "retrieval_language": language,
        "section_retrievals": [],
        "error": None,
        "status": "pending",
    }

    before_snap: list[dict] | None = None
    after_snap: list[dict] | None = None
    stream_events: list[str] = []
    last_status: str = ""

    async for mode, chunk in g.astream(
        initial, config, stream_mode=["custom", "values", "updates"]
    ):
        if mode == "custom" and isinstance(chunk, dict) and "node" in chunk:
            line = f"  [{chunk['node']:20s}] {chunk['event']:6s}  {chunk['msg']}"
            stream_events.append(line)

        elif mode == "values":
            state: AgentState = chunk
            status = state.get("status") or ""

            # Snapshot scope state immediately — section objects are mutated later
            if status == "classified" and before_snap is None:
                before_snap = _snapshot_sections(state.get("sections") or [])

            if status == "sections_filtered" and after_snap is None:
                after_snap = _snapshot_sections(state.get("sections") or [])

            last_status = status

    print()
    for line in stream_events:
        print(line)

    if before_snap is not None:
        _print_snapshot(before_snap, "BEFORE sections_llm  (after classify_sections)")
    else:
        print("\n  [warn] classify_sections state not captured (check status flow)")

    if after_snap is not None:
        _print_snapshot(after_snap, "AFTER  sections_llm  (scope=None = filtered out)")

        # Diff summary
        if before_snap is not None:
            b_classified = {s["id"] for s in before_snap if s["has_scope"] and s["domains"]}
            a_classified = {s["id"] for s in after_snap if s["has_scope"] and s["domains"]}
            removed = b_classified - a_classified
            print(f"\n  DIFF: {len(removed)} section(s) filtered out by sections_llm:")
            if removed:
                id_to_title = {s["id"]: s["title"] for s in before_snap}
                for sid in sorted(removed):
                    print(f"    - {sid}  ({id_to_title.get(sid, '?')})")
            else:
                print("    (none — all classified sections kept)")
    else:
        print("\n  [warn] sections_llm state not captured (status never became 'sections_filtered')")

    print(f"\n  Final status: {last_status}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _main(args: argparse.Namespace) -> None:
    for path in args.file_path:
        await _run_document(path, args.language)


def main() -> None:
    p = argparse.ArgumentParser(description="Before/after sections_llm smoke test.")
    p.add_argument("file_path", nargs="+", help="Path(s) to PDF or DOCX files.")
    p.add_argument("--language", choices=["EN", "FR"], default="FR")
    args = p.parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
