from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from agent_compliance.pdf_parser import docling_to_sections, parse_document
    from .sections_llm import filter_sections_with_llm
except ImportError:  # pragma: no cover - supports direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from agent_compliance.pdf_parser import docling_to_sections, parse_document
    from agent_compliance.graph.sections_llm import filter_sections_with_llm


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the parser and section LLM, then print before/after review output."
    )
    parser.add_argument("file_path", nargs="+", help="Path to the PDF or DOCX file.")
    return parser


def _truncate(text: str, limit: int = 72) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _snapshot_sections(sections: list) -> list[dict]:
    return [
        {
            "id": section.id,
            "title": section.title,
            "section_type": section.section_type.value,
            "page_range": section.page_range,
        }
        for section in sections
    ]


def _print_before(sections: list[dict]) -> None:
    print("Before LLM")
    print("==========")
    for index, section in enumerate(sections, start=1):
        start_page, end_page = section["page_range"]
        print(
            f"{index:02d}. {section['id']} | type={section['section_type']} | "
            f"pages={start_page}-{end_page} | title={_truncate(section['title'])}"
        )
    print()


def _print_after(sections: list) -> None:
    print("After LLM")
    print("=========")
    for index, section in enumerate(sections, start=1):
        validity = (
            "valid"
            if section.llm_valid is True
            else "invalid"
            if section.llm_valid is False
            else "unknown"
        )
        clause_family = section.predicted_clause_family or "-"
        print(
            f"{index:02d}. {section.id} | llm_valid={validity} | "
            f"clause_family={clause_family} | title={_truncate(section.title)}"
        )
    print()


async def _async_main(args: argparse.Namespace) -> int:
    file_path = " ".join(args.file_path)
    source = Path(file_path)

    if not source.exists():
        print(f"Error: file not found: {source}")
        return 1

    if source.suffix.lower() not in {".pdf", ".docx"}:
        print(f"Error: unsupported file type: {source.suffix}")
        return 1

    print(f"Reviewing: {source}")
    print()

    parse_result = parse_document(str(source), remove_headers_footers=True)
    sections = docling_to_sections(parse_result)
    before = _snapshot_sections(sections)

    await filter_sections_with_llm(sections)

    _print_before(before)
    _print_after(sections)

    total = len(sections)
    valid = sum(section.llm_valid is True for section in sections)
    invalid = sum(section.llm_valid is False for section in sections)
    clause_predictions = sum(section.predicted_clause_family is not None for section in sections)

    print("Summary")
    print("=======")
    print(f"sections={total}")
    print(f"llm_valid={valid}")
    print(f"llm_invalid={invalid}")
    print(f"clause_family_predictions={clause_predictions}")
    return 0


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
