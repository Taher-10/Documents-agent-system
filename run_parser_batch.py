"""
run_parser_batch.py — Run the compliance parser agent on every document in
agent_compliance/qhme_docs/ and write a JSON report to output/.

Accuracy metrics are derived from what the parser actually produces:
  - text_extracted      : bool — was any text found?
  - char_count          : total characters in cleaned text
  - word_count          : whitespace-split word count
  - pages               : page count reported by Docling
  - chars_per_page      : avg chars/page (proxy for extraction density)
  - title_detected      : bool
  - heading_count       : number of heading hints detected
  - furniture_removed   : number of header/footer lines cleaned out
  - accuracy_score      : 0.0–1.0 composite heuristic (see _accuracy_score)

Usage:
    python run_parser_batch.py
    python run_parser_batch.py --docs-dir path/to/docs --out output/my_run.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from agent_compliance.graph.run import run as agent_run


# ---------------------------------------------------------------------------
# Accuracy heuristic
# ---------------------------------------------------------------------------

def _accuracy_score(metrics: dict) -> float:
    """Return a 0–1 composite score based on parser output signals."""
    score = 0.0

    if metrics["text_extracted"]:
        score += 0.40

    if metrics["pages"] and metrics["pages"] > 0:
        score += 0.15

    if metrics["title_detected"]:
        score += 0.15

    cpp = metrics["chars_per_page"] or 0
    if cpp >= 1000:
        score += 0.15
    elif cpp >= 400:
        score += 0.10
    elif cpp >= 100:
        score += 0.05

    if metrics["heading_count"] >= 3:
        score += 0.10
    elif metrics["heading_count"] >= 1:
        score += 0.05

    if metrics["furniture_removed"] > 0:
        score += 0.05  # furniture detection = richer structural parsing

    return round(min(score, 1.0), 4)


# ---------------------------------------------------------------------------
# Per-file metrics extraction
# ---------------------------------------------------------------------------

def _extract_metrics(parse_result) -> dict:
    """Pull measurable signals out of a ParseResult."""
    if parse_result is None:
        return {
            "text_extracted": False,
            "char_count": 0,
            "word_count": 0,
            "pages": None,
            "chars_per_page": None,
            "title_detected": False,
            "heading_count": 0,
            "furniture_removed": 0,
            "accuracy_score": 0.0,
        }

    text = parse_result.text or ""
    pages = parse_result.pages
    meta = parse_result.metadata or {}
    cleanup = meta.get("cleanup", {})

    char_count = len(text)
    word_count = len(text.split())
    title_detected = bool(parse_result.title and parse_result.title.strip())
    heading_count = len(meta.get("heading_hints", []))
    furniture_removed = len(cleanup.get("headers_footers_removed", []))

    chars_per_page = None
    if pages and pages > 0:
        chars_per_page = round(char_count / pages, 1)

    metrics = {
        "text_extracted": char_count > 0,
        "char_count": char_count,
        "word_count": word_count,
        "pages": pages,
        "chars_per_page": chars_per_page,
        "title_detected": title_detected,
        "heading_count": heading_count,
        "furniture_removed": furniture_removed,
        "accuracy_score": 0.0,  # filled below
    }
    metrics["accuracy_score"] = _accuracy_score(metrics)
    return metrics


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

async def _run_one(doc_path: str) -> dict:
    """Run the agent on a single document and return a result record."""
    name = Path(doc_path).name
    print(f"  Parsing: {name}")

    t0 = time.perf_counter()
    try:
        state = await agent_run(doc_path)
        elapsed = round(time.perf_counter() - t0, 3)

        if state.get("error"):
            print(f"    ✗ Error: {state['error']}")
            return {
                "file": name,
                "path": doc_path,
                "status": "error",
                "error": state["error"],
                "elapsed_seconds": elapsed,
                "metrics": _extract_metrics(None),
            }

        pr = state.get("parse_result")
        metrics = _extract_metrics(pr)
        print(
            f"    ✓ {elapsed}s — {metrics['pages']} pages, "
            f"{metrics['word_count']} words, "
            f"accuracy={metrics['accuracy_score']:.2f}"
        )
        return {
            "file": name,
            "path": doc_path,
            "status": "ok",
            "error": None,
            "elapsed_seconds": elapsed,
            "metrics": metrics,
            "title": pr.title if pr else None,
        }

    except Exception as exc:
        elapsed = round(time.perf_counter() - t0, 3)
        print(f"    ✗ Exception: {exc}")
        return {
            "file": name,
            "path": doc_path,
            "status": "error",
            "error": str(exc),
            "elapsed_seconds": elapsed,
            "metrics": _extract_metrics(None),
        }


async def _run_batch(docs_dir: Path, out_path: Path) -> None:
    docs = sorted(
        p for p in docs_dir.iterdir()
        if p.suffix.lower() in {".pdf", ".docx"}
    )
    if not docs:
        print(f"No PDF/DOCX files found in {docs_dir}")
        return

    print(f"\nFound {len(docs)} documents in {docs_dir}\n")

    results = []
    total_t0 = time.perf_counter()

    for doc in docs:
        record = await _run_one(str(doc))
        results.append(record)

    total_elapsed = round(time.perf_counter() - total_t0, 3)

    # --- Summary stats ---
    ok = [r for r in results if r["status"] == "ok"]
    errors = [r for r in results if r["status"] == "error"]
    avg_accuracy = (
        round(sum(r["metrics"]["accuracy_score"] for r in ok) / len(ok), 4)
        if ok else 0.0
    )

    summary = {
        "total_files": len(results),
        "success": len(ok),
        "errors": len(errors),
        "total_elapsed_seconds": total_elapsed,
        "avg_elapsed_seconds": round(total_elapsed / len(results), 3) if results else 0,
        "avg_accuracy_score": avg_accuracy,
    }

    report = {
        "summary": summary,
        "results": results,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(f"\n{'─'*55}")
    print(f"  Files processed  : {summary['total_files']}")
    print(f"  Successes        : {summary['success']}")
    print(f"  Errors           : {summary['errors']}")
    print(f"  Total time       : {summary['total_elapsed_seconds']}s")
    print(f"  Avg time/file    : {summary['avg_elapsed_seconds']}s")
    print(f"  Avg accuracy     : {summary['avg_accuracy_score']:.2%}")
    print(f"\n  Report saved to  : {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Batch parser runner — writes JSON report.")
    p.add_argument(
        "--docs-dir",
        default="agent_compliance/qhme_docs",
        help="Directory containing PDF/DOCX files (default: agent_compliance/qhme_docs)",
    )
    p.add_argument(
        "--out",
        default="output/parser_batch_results.json",
        help="Output JSON file path (default: output/parser_batch_results.json)",
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()
    docs_dir = Path(args.docs_dir)
    out_path = Path(args.out)

    if not docs_dir.exists():
        print(f"Error: docs directory not found: {docs_dir}")
        return 1

    asyncio.run(_run_batch(docs_dir, out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
