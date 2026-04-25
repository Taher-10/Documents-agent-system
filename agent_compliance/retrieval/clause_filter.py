"""Fallback section-type to clause-family mapping utilities."""

from __future__ import annotations


SECTION_TYPE_CLAUSE_MAP: dict[str, list[str]] = {
    "METADATA": ["7.5.2"],
    "SCOPE": ["4.1", "4.2", "4.3", "5.2"],
    "DEFINITIONS": ["3", "4.1"],
    "REFERENCES": ["2"],
    "PROCEDURE_TEXT": ["6.1", "6.2", "8.1", "8.4", "8.5"],
    "RECORD_FORM": ["7.5", "9.1", "9.1.1"],
    "PROCESS_DIAGRAM": ["4.4", "8.1"],
    "UNKNOWN": [],
}


def _normalize_section_type(section_type: str) -> str:
    normalized = section_type.strip().upper().replace("-", "_").replace(" ", "_")
    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[-1]
    return normalized


def get_top_level_families(section_type: str) -> list[str]:
    """Return unique top-level families for a section type.

    The returned values are matched against ``iso_clauses.top_level_family`` and
    therefore fan out to all clause depths under a family.
    """
    normalized_type = _normalize_section_type(section_type)
    prefixes = SECTION_TYPE_CLAUSE_MAP.get(normalized_type, [])
    return list(dict.fromkeys(prefix.split(".")[0] for prefix in prefixes))
