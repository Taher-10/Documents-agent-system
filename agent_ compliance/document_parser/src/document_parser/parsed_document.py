"""
parsed_document.py — M6: Core data models for the QHSE document parser.

Build order: M6 (this file) → M1 → M2-TierA → M2-DOCX → M3 → M4 → M5 → wire __init__
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal


# ---------------------------------------------------------------------------
# RawPageText
# ---------------------------------------------------------------------------

@dataclass
class RawPageText:
    """Raw text and tables extracted from one page before cleaning/segmenting.

    Attributes:
        page_number: 1-indexed page number.
        text: Extracted text content (may be empty for image-only pages).
        tables: All tables on this page.
                Format: list[table], table = list[rows], row = list[cells (str)].
        extraction_method: "pdfplumber" | "fitz" | "docx" | "ocr_stub".
        confidence: 1.0 = clean selectable text; 0.3 = ocr_stub; 0.1 = tier_c stub.
    """

    page_number: int
    text: str
    tables: list[list[list[str]]]
    extraction_method: str
    confidence: float


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class SectionType(str, Enum):
    """Semantic classification of a parsed document section."""

    METADATA        = "metadata"         # page-1 header: code, edition, redacteur table
    SCOPE           = "scope"            # "Objet" / "Domaine d'application"
    DEFINITIONS     = "definitions"      # "Définitions" / "Glossaire"
    REFERENCES      = "references"       # "Références" / "Documents associés"
    PROCESS_DIAGRAM = "process_diagram"  # logigramme / flowchart page
    PROCEDURE_TEXT  = "procedure_text"   # numbered procedural steps (6.1, 6.2…)
    RECORD_FORM     = "record_form"      # form / fiche at end of document
    UNKNOWN         = "unknown"          # could not classify — LLM fallback result


# ---------------------------------------------------------------------------
# ParsedSection
# ---------------------------------------------------------------------------

@dataclass
class ParsedSection:
    """One logical section extracted from a QHSE document.

    Attributes:
        id: Stable identifier derived from heading (e.g. "section_6_1").
        section_type: Semantic classification of this section.
        title: Heading text as found in the source document.
        raw_text: Cleaned text content of the section body.
        page_range: (start_page, end_page), 1-indexed, inclusive.
        extraction_confidence: 1.0 = clean selectable text; <0.7 = OCR degraded.
        visual_ref: Path to rasterized image when section_type is PROCESS_DIAGRAM.
        heading_level: 1 = top-level heading, 2 = sub-section, 3 = sub-sub-section.
    """

    id: str
    section_type: SectionType
    title: str
    raw_text: str
    page_range: tuple[int, int]
    extraction_confidence: float
    visual_ref: str | None = None
    heading_level: int = 1

    def to_dict(self) -> dict:
        """Serialize to a plain dict (JSON-safe)."""
        d = asdict(self)
        d["section_type"] = self.section_type.value
        d["page_range"] = list(self.page_range)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ParsedSection":
        """Deserialize from a plain dict produced by to_dict()."""
        return cls(
            id=d["id"],
            section_type=SectionType(d["section_type"]),
            title=d["title"],
            raw_text=d["raw_text"],
            page_range=tuple(d["page_range"]),  # type: ignore[arg-type]
            extraction_confidence=float(d["extraction_confidence"]),
            visual_ref=d.get("visual_ref"),
            heading_level=int(d.get("heading_level", 1)),
        )


# ---------------------------------------------------------------------------
# ParsedDocument
# ---------------------------------------------------------------------------

@dataclass
class ParsedDocument:
    """Top-level output of the document parser pipeline.

    Passed to Agent 2 (compliance checker) inside a DocumentJob.
    All fields are populated by the pipeline — never read from the CSV/SQL table.

    Attributes:
        job_id: Unique identifier for this parsing job.
        source_path: Absolute path to the original file.
        file_format: "pdf" or "docx", matched against actual file extension.
        quality_tier: "A" (clean), "B" (hybrid/degraded), "C" (full scan).
        min_confidence: min(section.extraction_confidence) across all sections.
        low_quality_flag: True when quality_tier == "C" or min_confidence < 0.65.
        sections: Ordered list of extracted sections.
        raw_metadata: Best-effort extraction of page-1 identity fields
                      (doc_code, edition, indice, title, redacteur, …).
        parser_version: Semver string of the parser that produced this object.
        parsed_at: ISO 8601 UTC datetime string of when parsing completed.
    """

    # Identity
    job_id: str
    source_path: str
    file_format: Literal["pdf", "docx"]

    # Quality signals
    quality_tier: Literal["A", "B", "C"]
    min_confidence: float
    low_quality_flag: bool

    # Content
    sections: list[ParsedSection]
    raw_metadata: dict = field(default_factory=dict)

    # Provenance
    parser_version: str = "1.0.0"
    parsed_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Validate all structural invariants.

        Raises:
            ValueError: with a descriptive message for the first violated invariant.
        """
        if not self.sections:
            raise ValueError("ParsedDocument.sections must not be empty.")

        # Unique section IDs
        ids = [s.id for s in self.sections]
        seen: set[str] = set()
        for sid in ids:
            if sid in seen:
                raise ValueError(f"Duplicate ParsedSection.id detected: '{sid}'.")
            seen.add(sid)

        # min_confidence consistency
        computed_min = min(s.extraction_confidence for s in self.sections)
        if abs(self.min_confidence - computed_min) > 1e-9:
            raise ValueError(
                f"min_confidence mismatch: stored {self.min_confidence!r}, "
                f"computed {computed_min!r}."
            )

        # low_quality_flag consistency
        expected_flag = self.quality_tier == "C" or self.min_confidence < 0.65
        if self.low_quality_flag != expected_flag:
            raise ValueError(
                f"low_quality_flag should be {expected_flag!r} "
                f"(quality_tier={self.quality_tier!r}, "
                f"min_confidence={self.min_confidence!r})."
            )

        # file_format vs. actual extension
        from pathlib import Path
        suffix = Path(self.source_path).suffix.lstrip(".").lower()
        if suffix != self.file_format:
            raise ValueError(
                f"file_format={self.file_format!r} does not match "
                f"source_path extension '.{suffix}'."
            )

        # At least one non-UNKNOWN section
        if all(s.section_type == SectionType.UNKNOWN for s in self.sections):
            raise ValueError(
                "At least one ParsedSection must have section_type != UNKNOWN."
            )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to a plain dict (JSON-safe, round-trips via from_dict)."""
        return {
            "job_id": self.job_id,
            "source_path": self.source_path,
            "file_format": self.file_format,
            "quality_tier": self.quality_tier,
            "min_confidence": self.min_confidence,
            "low_quality_flag": self.low_quality_flag,
            "sections": [s.to_dict() for s in self.sections],
            "raw_metadata": self.raw_metadata,
            "parser_version": self.parser_version,
            "parsed_at": self.parsed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ParsedDocument":
        """Deserialize from a plain dict produced by to_dict()."""
        return cls(
            job_id=d["job_id"],
            source_path=d["source_path"],
            file_format=d["file_format"],
            quality_tier=d["quality_tier"],
            min_confidence=float(d["min_confidence"]),
            low_quality_flag=bool(d["low_quality_flag"]),
            sections=[ParsedSection.from_dict(s) for s in d["sections"]],
            raw_metadata=d.get("raw_metadata", {}),
            parser_version=d.get("parser_version", "1.0.0"),
            parsed_at=d.get("parsed_at", ""),
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class UnsupportedFormatError(Exception):
    """Raised when the input file is neither PDF nor DOCX."""


class ExtractionFailedError(Exception):
    """Raised when all extraction strategies fail for a document."""


class EmptyDocumentError(Exception):
    """Raised when a document yields zero usable text after cleaning."""
