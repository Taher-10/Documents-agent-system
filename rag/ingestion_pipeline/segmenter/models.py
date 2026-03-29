"""
segmenter/models.py
────────────────────
Phase 0 — Contract Lock & Data Types

All shared domain types for the segmentation stage of the ingestion pipeline.
These are the foundational data contracts consumed by every downstream package
(chunker, enricher, registry).

Dependency rule: this module imports ONLY from the standard library.
No other package in this pipeline may be imported here.

Type ownership:
  • ClauseSpan   — output of boundary detection (Phase 2)
  • ClauseNode   — output of tree construction (Phase 3)
  • ContentType  — normative classification enum (used by chunker downstream)
  • Constants    — standard ID maps and expected leaf-count bounds
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple


# ==============================================================================
# Standard metadata maps
# this is used in dev and need to be removed later when api interface intruduced
# ==============================================================================

# Maps PDF stem → human-readable standard label
STANDARD_ID_MAP: Dict[str, str] = {
    "n9001":    "ISO 9001:2015",
    "n9001_en": "ISO 9001:2015",
    "n14001":   "ISO 14001:2015",
}

# Maps PDF stem → short norm identifier (used as chunk ID prefix)
NORM_ID_MAP: Dict[str, str] = {
    "n9001":    "ISO9001",
    "n9001_en": "ISO9001",
    "n14001":   "ISO14001",
}

# Maps PDF stem → publication year
NORM_VERSION_MAP: Dict[str, str] = {
    "n9001":    "2015",
    "n9001_en": "2015",
    "n14001":   "2015",
}

# Acceptable leaf-clause count range per standard.
# Used by construct_clause_tree() to validate structural integrity.
# Range: (min_inclusive, max_inclusive)
EXPECTED_LEAF_COUNTS: Dict[str, Tuple[int, int]] = {
    "n9001":    (65, 75),
    "n9001_en": (65, 75),
    "n14001":   (55, 70),
}


# ==============================================================================
# Content classification enum
# ==============================================================================

class ContentType(str, Enum):
    """
    Four-way classification of a clause's normative character.

    Determined by modal verb presence (bilingual — EN + FR):
      REQUIREMENT    — 'shall' / 'must' / 'doit' / 'doivent'
      RECOMMENDATION — 'should' / 'il convient' / 'devrait'
      INFORMATIVE    — plain prose, no modal obligations detected
      STRUCTURAL     — empty or heading-only text (no content)

    Inherits from str so it serialises to its value in JSON.
    """

    REQUIREMENT    = "requirement"
    RECOMMENDATION = "recommendation"
    INFORMATIVE    = "informative"
    STRUCTURAL     = "structural"


# ==============================================================================
# Segmenter output data classes
# ==============================================================================

@dataclass
class ClauseSpan:
    """
    Intermediate boundary marker produced by detect_clause_boundaries().

    Represents a single ISO clause as a character-offset range within the
    assembled markdown string.

    Fields
    ------
    clause_id : Canonical clause identifier extracted from the heading, e.g.
                "4.1.2", "Annex A", or "0" for the preamble.
    start_idx : Inclusive start offset in the markdown string.
    end_idx   : Exclusive end offset in the markdown string.
    level     : Hierarchy depth (1 = top-level clause, 2 = sub-clause, …).
    title     : Verbatim heading text, e.g. "4.1.2 Planning of changes".
    duplicate : True if clause_id was already seen earlier — flagged as a
                structural anomaly but not dropped.
    """

    clause_id: str
    start_idx: int
    end_idx: int
    level: int
    title: str
    duplicate: bool = False


@dataclass
class ClauseNode:
    """
    Recursive tree node produced by construct_clause_tree().

    Represents one ISO clause and its sub-clause hierarchy.  The root node
    has clause_id='root' and level=0.

    Fields
    ------
    clause_id : Same identifier as the corresponding ClauseSpan.
    title     : Verbatim heading text.
    level     : Hierarchy depth (0 = root, 1 = top-level, 2 = sub-clause, …).
    text      : Full clause text slice from the markdown (stripped).
    children  : Ordered list of direct sub-clauses.
    """

    clause_id: str
    title: str
    level: int
    text: str
    children: List[ClauseNode] = field(default_factory=list)
