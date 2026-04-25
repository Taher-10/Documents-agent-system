"""SQLite-backed retrieval utilities for clause access."""

from .clause_filter import SECTION_TYPE_CLAUSE_MAP, get_top_level_families
from .clause_store import (
    NORMS_DB_PATH,
    ClauseRecord,
    fetch_clauses_by_ids,
    fetch_clauses_by_section_type,
    load_clause_menu,
)
from .norm_normalizer import normalize_norm_id

__all__ = [
    "SECTION_TYPE_CLAUSE_MAP",
    "NORMS_DB_PATH",
    "ClauseRecord",
    "fetch_clauses_by_ids",
    "fetch_clauses_by_section_type",
    "get_top_level_families",
    "load_clause_menu",
    "normalize_norm_id",
]
