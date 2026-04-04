"""Deterministic domain and doc-type derivation from registry metadata only."""

from __future__ import annotations

from typing import Any, Mapping

from agent_compliance.classification.models import DocType, Domain

SYSTEME_TO_DOMAIN: dict[str, Domain] = {
    "Q": "ISO9001",
    "E": "ISO14001",
    "S": "ISO45001",
}

_ALL_DOMAINS: list[Domain] = ["ISO9001", "ISO14001", "ISO45001"]

DOC_TYPE_HINTS: dict[DocType, tuple[str, ...]] = {
    "policy": (
        "policy",
        "politique",
        "charte",
        "manual",
        "manuel",
    ),
    "procedure": (
        "procedure",
        "procédure",
        "process",
        "processus",
        "instruction",
        "mode opératoire",
        "mode operatoire",
        "workflow",
        "sop",
    ),
    "record": (
        "record",
        "enregistrement",
        "form",
        "formulaire",
        "fiche",
        "template",
        "gabarit",
        "checklist",
        "registre",
        "log",
        "job description",
        "fiche de poste",
    ),
}

_DOC_TYPE_FALLBACK_CONFIDENCE = 0.3


def derive_scope_from_metadata(
    registry_metadata: Mapping[str, Any],
) -> tuple[list[Domain], float, DocType | None, float]:
    """Extract domains and doc_type from registry metadata.

    Returns:
        ``(domains, domain_confidence, doc_type, doc_type_confidence)``

    Domain priority:
        1. ``systeme`` field present and recognised → confidence 1.0
        2. Absent / unrecognised → all three domains, confidence 0.3

    Doc-type priority:
        1. Hint keyword found in metadata fields → confidence 1.0
        2. No match → ``"procedure"`` fallback at confidence 0.3
        3. All metadata fields empty → ``None`` at confidence 0.0
    """
    domains, domain_confidence = _derive_domains(registry_metadata)
    doc_type, doc_type_confidence = _derive_doc_type(registry_metadata)
    return domains, domain_confidence, doc_type, doc_type_confidence


def _derive_domains(
    registry_metadata: Mapping[str, Any],
) -> tuple[list[Domain], float]:
    systeme = str(registry_metadata.get("systeme", "") or "").upper()
    domains: list[Domain] = []
    for char in systeme:
        if char in SYSTEME_TO_DOMAIN and SYSTEME_TO_DOMAIN[char] not in domains:
            domains.append(SYSTEME_TO_DOMAIN[char])
    if domains:
        return domains, 1.0
    return list(_ALL_DOMAINS), 0.3


def _derive_doc_type(
    registry_metadata: Mapping[str, Any],
) -> tuple[DocType | None, float]:
    metadata_blob = " ".join(
        str(registry_metadata.get(f, "") or "")
        for f in ("types_documents", "domaines_documents", "sous_domaine_document")
    ).lower()

    for doc_type, hints in DOC_TYPE_HINTS.items():
        if any(hint in metadata_blob for hint in hints):
            return doc_type, 1.0

    if metadata_blob.strip():
        return "procedure", _DOC_TYPE_FALLBACK_CONFIDENCE

    return None, 0.0
