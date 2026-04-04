from __future__ import annotations

from typing import Any
from typing_extensions import TypedDict


class AgentState(TypedDict):
    # --- Input ---
    document_path: str

    # --- Intermediate ---
    parse_result: Any | None          # ParseResult dataclass from docling_parser

    # --- Output ---
    sections: list[Any]               # list[ParsedSection]
    quality_tier: str | None          # "A", "B", or "C"
    min_confidence: float | None
    low_quality_flag: bool

    # --- Control ---
    error: str | None
    status: str                        # "pending" | "validated" | "parsed" | "sectioned" | "done" | "error"
