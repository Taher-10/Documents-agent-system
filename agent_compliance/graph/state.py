from __future__ import annotations

from typing import Any
from typing_extensions import TypedDict


class AgentState(TypedDict):
    # --- Input ---
    document_path: str

    # --- Intermediate ---
    parse_result: Any | None          # ParseResult dataclass from docling_parser

    # --- Control ---
    error: str | None
    status: str                        # "pending" | "validated" | "parsed" | "error"
