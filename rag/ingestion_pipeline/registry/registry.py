"""
registry/registry.py
─────────────────────
Phase 6 — Validation and Registry Output

Two responsibilities, kept together because they share the same input type
(SegmenterResult / NormChunk list) and are both output-side concerns:

  Phase 6a — validate_chunks()
      Runs Pydantic v2 validation over every NormChunk.  All violations are
      collected as warnings — none raise in production.  Returns a violation
      count (0 on a clean run).

  Phase 6b — write_registry()
      Serialises the full pipeline result to a timestamped JSON file.
      A stable latest-pointer file is also written (overwriting only the
      tiny pointer, never the registry itself).

Design notes
------------
  • Pydantic is isolated entirely to this module.  No other package in the
    pipeline imports Pydantic — if the validation library changes, only this
    file needs updating.
  • The registry JSON is a lookup index, not a content store: chunk.text and
    chunk.bm25_tokens are excluded from the serialised output.
  • Timestamp uniqueness ensures registry files are never overwritten.

Dependency rule: imports from segmenter.models (ClauseNode), chunker.models
(NormChunk), and the standard library.  No segmenter functions, chunker
functions, or enricher are imported here.
"""

import dataclasses
import datetime
import json as _json
import os
import re
import warnings
from typing import List

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from chunker.models import NormChunk
from segmenter.models import ClauseNode


# ==============================================================================
# SegmenterResult — pipeline output container
# (imported here only for the type annotation on write_registry)
# ==============================================================================

# Avoid circular import: SegmenterResult is defined in pipeline.py which
# imports this module.  We accept it as a duck-typed argument (any object
# with .standard_id, .tree, .chunks attributes).


# ==============================================================================
# Phase 6a — Pydantic validation
# ==============================================================================

# chunk_id must match the canonical format: {standard_id}_{clause_id}_{part}_p{page}
_CHUNK_ID_RE = re.compile(r'^[a-z0-9]+_.+_part\d+_p\d+$')


class _ChunkValidator(BaseModel):
    """
    Validates the structural invariants of a single NormChunk.

    All violations are raised as ValueError (caught by validate_chunks and
    emitted as warnings) — none propagate to the caller.

    Validators
    ----------
    chunk_id_must_match_pattern   : chunk_id must conform to the canonical format.
    requirement_flag_consistency  : has_requirements=True requires shall_count > 0.
    text_length_anomaly           : non-structural/non-informative chunks with
                                    token_count < 3 are considered suspicious.
    """

    model_config = ConfigDict(extra='allow')

    chunk_id:         str
    clause_number:    str
    token_count:      int
    content_type:     str
    shall_count:      int
    has_requirements: bool
    text:             str

    @field_validator('chunk_id')
    @classmethod
    def chunk_id_must_match_pattern(cls, v: str) -> str:
        """chunk_id must match ^[a-z0-9]+_.+_part\\d+_p\\d+$"""
        if not _CHUNK_ID_RE.match(v):
            raise ValueError(f"malformed chunk_id: {v!r}")
        return v

    @model_validator(mode='after')
    def requirement_flag_consistency(self) -> '_ChunkValidator':
        """has_requirements=True must always coincide with shall_count > 0."""
        if self.has_requirements and self.shall_count == 0:
            raise ValueError(
                f"chunk {self.chunk_id!r}: has_requirements=True but shall_count=0"
            )
        return self

    @model_validator(mode='after')
    def text_length_anomaly(self) -> '_ChunkValidator':
        """Non-informative/structural chunks with < 3 tokens are suspicious."""
        if self.content_type not in ('structural', 'informative') and self.token_count < 3:
            raise ValueError(
                f"chunk {self.chunk_id!r}: token_count={self.token_count} "
                f"too low for content_type={self.content_type!r}"
            )
        return self


def validate_chunks(chunks: List[NormChunk]) -> int:
    """
    Run Pydantic validation over every NormChunk in the list.

    Each NormChunk is converted to a dict and validated against _ChunkValidator.
    Violations are emitted as UserWarning — none raise and the pipeline
    continues regardless.

    Parameters
    ----------
    chunks : List of NormChunks from the chunker + enricher phases.

    Returns
    -------
    int — number of validation violations found (0 on a clean run).
    """
    violations = 0
    for chunk in chunks:
        chunk_dict = {
            f.name: getattr(chunk, f.name)
            for f in dataclasses.fields(chunk)
        }
        try:
            _ChunkValidator(**chunk_dict)
        except Exception as exc:
            warnings.warn(f"[Validation] {exc}", UserWarning, stacklevel=2)
            violations += 1
    return violations


# ==============================================================================
# Phase 6b — Registry serialisation helpers
# ==============================================================================

def _tree_to_dict(node: ClauseNode) -> dict:
    """
    Recursively serialise a ClauseNode to a plain dict.

    The 'text' field is excluded — the registry is a structural index, not a
    content store.  Full clause text remains in the NormChunk objects.

    Parameters
    ----------
    node : ClauseNode to serialise (may have children).

    Returns
    -------
    dict — {clause_id, title, level, children: [...]}
    """
    return {
        "clause_id": node.clause_id,
        "title":     node.title,
        "level":     node.level,
        "children":  [_tree_to_dict(c) for c in node.children],
    }


def _chunk_to_registry_dict(chunk: NormChunk) -> dict:
    """
    Serialise a NormChunk to a plain dict for the registry index.

    Excluded fields:
      • text        — registry is a lookup index, not a content store.
      • bm25_tokens — BM25-only field; metadata={"chroma": False}.

    All other fields (provenance, classification, modal counts, keywords,
    related clauses, embedding model) are included.

    Parameters
    ----------
    chunk : Enriched NormChunk.

    Returns
    -------
    dict — JSON-serialisable representation of the chunk metadata.
    """
    return {
        "chunk_id":            chunk.chunk_id,
        "norm_id":             chunk.norm_id,
        "norm_full":           chunk.norm_full,
        "norm_version":        chunk.norm_version,
        "clause_number":       chunk.clause_number,
        "clause_title":        chunk.clause_title,
        "parent_clause":       chunk.parent_clause,
        "page_number":         chunk.page_number,
        "chunk_index":         chunk.chunk_index,
        "total_chunks":        chunk.total_chunks,
        "token_count":         chunk.token_count,
        "content_type":        chunk.content_type.value,
        "shall_count":         chunk.shall_count,
        "should_count":        chunk.should_count,
        "has_requirements":    chunk.has_requirements,
        "has_permissions":     chunk.has_permissions,
        "has_recommendations": chunk.has_recommendations,
        "has_capabilities":    chunk.has_capabilities,
        "keywords":            chunk.keywords,
        "bm25_tokens":         chunk.bm25_tokens,
        "related_clauses":     chunk.related_clauses,
        "embedding_model":     chunk.embedding_model,
    }


# ==============================================================================
# Phase 6b — Registry writer
# ==============================================================================

def write_registry(result, output_dir: str = "output") -> str:
    """
    Write the pipeline result to a timestamped JSON registry file.

    File naming
    -----------
    Each run produces a unique file:
      {output_dir}/{norm_slug}_registry_{YYYYMMDDTHHMMSS}.json
    e.g. output/iso90012015_registry_20260318T154300.json

    A stable pointer file is updated on every run:
      {output_dir}/{norm_slug}_registry_latest.txt
    It contains only the filename (one line) and is the only mutable artifact.

    Registry JSON structure
    -----------------------
    {
      "standard_id":  "ISO 9001:2015",
      "generated_at": "2026-03-18T15:43:00.123456",
      "chunk_count":  95,
      "clause_tree":  { ... },    -- recursive ClauseNode tree (text excluded)
      "chunks":       [ ... ]     -- NormChunk metadata list (text + bm25 excluded)
    }

    An assertion gate ensures chunk_count == len(chunks) before writing.

    Parameters
    ----------
    result     : SegmenterResult (duck-typed: must have .standard_id, .tree, .chunks).
    output_dir : Target directory (created if absent).

    Returns
    -------
    str — absolute path to the written registry file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # "ISO 9001:2015" → "iso90012015"  (remove non-alphanumeric, lowercase)
    norm_slug = re.sub(r'[^a-z0-9]', '', result.standard_id.lower())

    ts       = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    filename = f"{norm_slug}_registry_{ts}.json"
    filepath = os.path.join(output_dir, filename)

    registry = {
        "standard_id":  result.standard_id,
        "generated_at": datetime.datetime.now().isoformat(),
        "chunk_count":  len(result.chunks),
        "clause_tree":  _tree_to_dict(result.tree),
        "chunks":       [_chunk_to_registry_dict(c) for c in result.chunks],
    }

    # Consistency gate — chunk_count must equal the actual serialised count
    assert registry["chunk_count"] == len(registry["chunks"]), (
        f"chunk_count={registry['chunk_count']} != "
        f"len(chunks)={len(registry['chunks'])}"
    )

    with open(filepath, 'w', encoding='utf-8') as fh:
        _json.dump(registry, fh, ensure_ascii=False, indent=2)

    # Update the stable latest-pointer (overwrites only the tiny pointer file)
    latest_path = os.path.join(output_dir, f"{norm_slug}_registry_latest.txt")
    with open(latest_path, 'w', encoding='utf-8') as fh:
        fh.write(filename + '\n')

    return filepath
