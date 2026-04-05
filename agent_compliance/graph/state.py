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
    registry_metadata: dict[str, Any]  # fetched from documents_system.db; {} if not found
    document_scope: Any | None         # merged RetrievalScope for the whole document (each section carries its own .scope)

    # --- Retrieval ---
    retrieval_language: str            # "EN" or "FR"
    section_retrievals: list[Any]      # list of {"section_id", "section_title", "chunks": list[RetrievedChunk]}; [] until retrieve_node runs

    # --- Control ---
    error: str | None
    status: str                        # "pending" | "validated" | "parsed" | "sectioned" | "classified" | "retrieved" | "done" | "error"
