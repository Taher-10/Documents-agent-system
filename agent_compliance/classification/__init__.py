"""Classification package public API."""

from agent_compliance.classification.engine import classify_for_retrieval
from agent_compliance.classification.models import DocType, Domain, RetrievalScope
from agent_compliance.classification.scope_deriver import (
    DOC_TYPE_HINTS,
    SYSTEME_TO_DOMAIN,
    derive_scope_from_metadata,
)

__all__ = [
    "classify_for_retrieval",
    "derive_scope_from_metadata",
    "RetrievalScope",
    "Domain",
    "DocType",
    "SYSTEME_TO_DOMAIN",
    "DOC_TYPE_HINTS",
]
