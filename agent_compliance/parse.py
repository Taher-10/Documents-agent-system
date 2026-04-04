from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .pdf_parser import assess_quality, docling_to_sections, parse_document
except ImportError:  # pragma: no cover - supports direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from agent_compliance.pdf_parser import assess_quality, docling_to_sections, parse_document


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse PDF/DOCX files with Docling.")
    parser.add_argument("file_path", nargs="+", help="Path to the PDF or DOCX file.")
    parser.add_argument(
        "--sections-json",
        action="store_true",
        help="Output ParsedSection list as JSON using the Docling adapter.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    # Allow unquoted file paths with spaces.
    file_path = " ".join(args.file_path)
    try:
        result = parse_document(file_path, remove_headers_footers=True)
        if args.sections_json:
            sections = docling_to_sections(result)
            quality_tier, min_confidence, low_quality_flag = assess_quality(sections)
            payload = {
                "quality_tier": quality_tier,
                "min_confidence": min_confidence,
                "low_quality_flag": low_quality_flag,
                "sections": [section.to_dict() for section in sections],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Source: {result.source_path}")
    print(f"Pages: {result.pages if result.pages is not None else 'unknown'}")
    print(f"Title: {result.title or 'untitled'}")
    cleanup = (result.metadata or {}).get("cleanup")
    if cleanup:
        removed = cleanup.get("headers_footers_removed", [])
        print(f"Removed headers/footers: {len(removed)}")
    print()
    print(result.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
