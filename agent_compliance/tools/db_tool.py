"""Registry metadata lookup from documents_system.db."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

# Resolved once at import time — db lives next to the agent_compliance package root
_DB_PATH = Path(__file__).parent.parent / "documents_system.db"

_CODE_PATTERN = re.compile(r"[A-Z]+-[A-Z]+-\d+")


def fetch_document_metadata(document_path: str) -> dict:
    """Return registry metadata for the document, or {} if not found.

    Extracts the document code from the filename using the pattern
    ``[A-Z]+-[A-Z]+-\\d+`` (e.g. ``PQ-PROD-01``), then queries the
    ``Document`` table.  The returned dict uses the DB column names as keys.
    ``langue`` is not present in the schema; callers should default to
    scanning both EN and FR when it is absent.

    Args:
        document_path: Absolute or relative path to the document file.

    Returns:
        Dict with keys ``code``, ``systeme``, ``types_documents``,
        ``domaines_documents``, ``indice``, ``titre`` — or ``{}`` if the
        code cannot be extracted or is not in the registry.
    """
    filename = Path(document_path).name
    match = _CODE_PATTERN.search(filename)
    if not match:
        return {}

    code = match.group(0)
    if not _DB_PATH.exists():
        return {}

    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT code, systeme, types_documents, domaines_documents, indice, titre"
                " FROM Document WHERE code = ?",
                (code,),
            ).fetchone()
    except sqlite3.Error:
        return {}

    if row is None:
        return {}

    return dict(row)
