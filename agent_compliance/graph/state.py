from __future__ import annotations

from typing import Any
from typing_extensions import TypedDict


class AgentState(TypedDict):
    # --- Input ---
    document_path: str

    # --- Intermediate ---
    parse_result: Any | None          # ParseResult dataclass from docling_parser
    sections: list[Any] | None        # ParsedSection list from docling_to_sections

    # --- Control ---
    error: str | None
    status: str                        # "pending" | "validated" | "parsed" | "sectioned" | "error"
