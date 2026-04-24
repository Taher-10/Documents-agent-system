from __future__ import annotations

# Compatibility shim: ingestion domain owns metadata and mapping logic.
from agent_compliance.ingestion.document_meta import DocumentMeta
from agent_compliance.ingestion.type_mappings import NORM_FLAG_MAP, TYPE_LEVEL_MAP, derive_norms

__all__ = [
    "DocumentMeta",
    "TYPE_LEVEL_MAP",
    "NORM_FLAG_MAP",
    "derive_norms",
]
