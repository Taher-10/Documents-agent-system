from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from qdrant_client import QdrantClient

if __package__ in {None, ""}:
    # Support direct execution: python agent_compliance/graph_v2/smoke_live_graph_v2.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_compliance.graph_v2.workflow import build_graph


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Live smoke test for graph_v2 (Qdrant sections + SQLite clause menu)."
    )
    parser.add_argument("--doc-id", required=True, help="Document UUID stored in qhse_sections payload.")
    parser.add_argument(
        "--company-id",
        required=True,
        help="Company UUID stored in qhse_sections payload (tenant guardrail).",
    )
    parser.add_argument(
        "--norm",
        action="append",
        default=None,
        help="Applicable norm label (repeatable). Default: ISO 9001",
    )
    parser.add_argument(
        "--language",
        default="FR",
        help='Clause menu language passed to SQLite retrieval (default: "FR").',
    )
    parser.add_argument(
        "--db-path",
        default="agent_compliance/data/iso_clauses.db",
        help="SQLite registry path (default canonical project path).",
    )
    parser.add_argument("--qdrant-host", default=os.getenv("QDRANT_HOST", "localhost"))
    parser.add_argument("--qdrant-port", type=int, default=int(os.getenv("QDRANT_PORT", "6333")))
    parser.add_argument("--qdrant-api-key", default=os.getenv("QDRANT_API_KEY") or None)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    norms = list(dict.fromkeys(args.norm or ["ISO 9001"]))

    db_exists = Path(args.db_path).exists()
    print(f"Qdrant target: {args.qdrant_host}:{args.qdrant_port}")
    print(f"SQLite path  : {args.db_path} (exists={db_exists})")
    if not db_exists:
        print("FAIL: SQLite DB path does not exist.")
        return 2

    qdrant = QdrantClient(
        host=args.qdrant_host,
        port=args.qdrant_port,
        api_key=args.qdrant_api_key,
    )
    app = build_graph(qdrant=qdrant, db_path=args.db_path)

    state = app.invoke(
        {
            "doc_id": args.doc_id,
            "company_id": args.company_id,
            "applicable_norms": norms,
            "language": args.language,
            "doc_code": None,
            "doc_type": None,
            "doc_level": None,
            "clause_menu": {},
            "sections": [],
            "section_matches": [],
            "report": None,
        }
    )

    sections = state.get("sections") or []
    clause_menu = state.get("clause_menu") or {}
    norm_key = "ISO9001" if any(item.replace(" ", "") == "ISO9001" for item in norms) else None
    norm_menu = clause_menu.get(norm_key, []) if norm_key else []

    print("\n[Graph result]")
    print(f"doc_id={args.doc_id}")
    print(f"company_id={args.company_id}")
    print(f"applicable_norms={norms}")
    print(f"language={args.language}")
    print(f"sections_count={len(sections)}")
    print(f"clause_menu_keys={list(clause_menu.keys())}")
    if norm_key:
        print(f"{norm_key}_menu_count={len(norm_menu)}")
        if norm_menu:
            print(f"{norm_key}_first_3={norm_menu[:3]}")
    if sections:
        first = sections[0]
        print(f"first_section=id={first.id} type={first.section_type.value} title={first.title!r}")

    checks = {
        "sections>0": len(sections) > 0,
        "clause_menu_non_empty": len(clause_menu) > 0,
    }
    if norm_key:
        checks[f"{norm_key}_in_menu"] = norm_key in clause_menu
        checks[f"{norm_key}_menu_gt_10"] = len(norm_menu) > 10

    print("\n[Assertions]")
    for label, passed in checks.items():
        print(f"{label}: {passed}")

    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
