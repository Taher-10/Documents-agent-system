"""Thin orchestrator: combines scope deriver + section topic mapper."""

from __future__ import annotations

from typing import Any, Mapping

from agent_compliance.classification.models import RetrievalScope
from agent_compliance.classification.scope_deriver import derive_scope_from_metadata
from agent_compliance.classification.section_topic_mapper import map_section_to_clauses


def classify_for_retrieval(
    section: Any,
    registry_metadata: Mapping[str, Any],
) -> RetrievalScope:
    """Produce a retrieval scope for a document section.

    Domain priority: registry metadata → all-domains fallback.
    Clause inference: keyword scoring against the two-level QHSE map.

    Args:
        section: A ``ParsedSection`` dataclass or any ``Mapping`` with
                 ``title``, ``raw_text``, and ``extraction_confidence`` keys.
        registry_metadata: Document-level registry fields
                           (``systeme``, ``langue``, ``types_documents``, …).

    Returns:
        :class:`RetrievalScope` ready for Qdrant filter construction.
    """
    domains, domain_conf, doc_type, doc_type_conf = derive_scope_from_metadata(
        registry_metadata
    )
    languages = _languages_to_scan(registry_metadata)

    title = _str_field(section, "title")
    raw_text = _str_field(section, "raw_text")
    extraction_confidence = _float_field(section, "extraction_confidence", default=1.0)

    families, specific, evidence, content_conf = map_section_to_clauses(
        section_title=title,
        section_text=raw_text,
        domains=domains,
        languages=languages,
        extraction_confidence=extraction_confidence,
    )

    overall_confidence = round(0.6 * domain_conf + 0.4 * content_conf, 3)
    notes = _build_notes(domain_conf, families, specific)

    return RetrievalScope(
        domains=domains,
        domain_confidence=domain_conf,
        doc_type=doc_type,
        doc_type_confidence=doc_type_conf,
        clause_families=families,
        specific_clauses=specific,
        confidence=overall_confidence,
        evidence=evidence,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _languages_to_scan(registry_metadata: Mapping[str, Any]) -> list[str]:
    """Prefer a known document language, otherwise scan both EN and FR."""
    lang = str(registry_metadata.get("langue", "") or "").upper()
    if lang in {"EN", "FR"}:
        return [lang]
    return ["EN", "FR"]


def _build_notes(
    domain_conf: float,
    families: list[str],
    specific: list[str],
) -> str | None:
    parts: list[str] = []
    if domain_conf < 0.5:
        parts.append("domain inferred from content (no systeme metadata)")
    if not families:
        parts.append("no clause family matched; broad retrieval recommended")
    elif not specific:
        parts.append(f"clause families matched: {', '.join(families)}; no discriminative clause found")
    return "; ".join(parts) or None


def _str_field(section: Any, field_name: str) -> str:
    if isinstance(section, Mapping):
        value = section.get(field_name, "")
    else:
        value = getattr(section, field_name, "")
    return str(value or "")


def _float_field(section: Any, field_name: str, *, default: float) -> float:
    if isinstance(section, Mapping):
        value = section.get(field_name, default)
    else:
        value = getattr(section, field_name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
