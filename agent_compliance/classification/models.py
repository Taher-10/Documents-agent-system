"""Pydantic contracts for retrieval-scope classification."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Domain = Literal["ISO9001", "ISO14001", "ISO45001"]
DocType = Literal["policy", "procedure", "record"]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class RetrievalScope(BaseModel):
    """Retrieval scope produced for a document section.

    Used to narrow Qdrant filters before retrieval:
    - ``domains``          -> ``norm_id`` filter
    - ``clause_families``  -> top-level HLS bucket hints (4–10)
    - ``specific_clauses`` -> fine-grained clause hints (e.g. "9.2", "7.2")
    - ``doc_type``         -> downstream audit/compliance rule selection
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    domains: list[Domain] = Field(
        ...,
        min_length=1,
        description="Applicable standards. Maps to Qdrant payload index `norm_id`.",
    )
    domain_confidence: Confidence = Field(
        ...,
        description="Confidence for domain inference.",
    )
    doc_type: DocType | None = Field(
        default=None,
        description="Normalized document type derived from registry metadata.",
    )
    doc_type_confidence: Confidence = Field(
        default=0.0,
        description="Confidence for doc_type inference.",
    )
    clause_families: list[str] = Field(
        default_factory=list,
        description="HLS top-level clause buckets (4–10) relevant to this section.",
    )
    specific_clauses: list[str] = Field(
        default_factory=list,
        description=(
            "High-value discriminative clause IDs (e.g. '9.2', '7.2') for this section."
        ),
    )
    confidence: Confidence = Field(
        ...,
        description="Overall retrieval-scope confidence (0.0–1.0).",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Keyword/vocabulary hits that contributed to this scope.",
    )
    notes: str | None = Field(
        default=None,
        description="Free-text explanation of inference quality or fallback reasons.",
    )

    @field_validator("domains")
    @classmethod
    def deduplicate_domains_preserving_order(cls, value: list[Domain]) -> list[Domain]:
        """Remove duplicate domains while preserving registry order."""
        return list(dict.fromkeys(value))

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        """Collapse empty strings to None for cleaner downstream logging."""
        if value == "":
            return None
        return value
