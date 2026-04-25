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
import sqlite3
import warnings
from typing import Dict, List, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from rag.ingestion_pipeline.chunker.models import NormChunk
from rag.ingestion_pipeline.segmenter.models import ClauseNode

_CANONICAL_SQLITE_DB_FILENAME = "iso_clauses.db"
_LEGACY_ALIAS_SQLITE_DB_FILENAME = "iso_norms.db"


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
        "clause_family":       chunk.clause_family,
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


def _sqlite_effective_clause_title(
    clause_title: str,
    clause_number: str,
    merged_text: str,
    max_len: int = 80,
) -> str:
    """
    Produce a display title suitable for SQLite clause rows.

    If the extracted title is blank or only the bare clause number (e.g. "4.4.1"),
    fallback to the first max_len characters of clause text so downstream LLM
    consumers get semantic signal.
    """
    title = (clause_title or "").strip()
    number = (clause_number or "").strip()
    if title and title != number:
        return title

    text = " ".join((merged_text or "").split()).strip()
    if not text:
        return number
    return text[:max_len].strip()




    


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



def write_normid_clause_keywords_registry(result, output_dir: str = "output") -> str:
    """
    Write a specialized registry containing only norm_id, clause_number, and keywords.
    
    This registry focuses on the relationship between norms, their clause structure,
    and extracted keywords for lightweight analysis and quick lookup.
    
    File naming
    -----------
    Each run produces a unique file:
      {output_dir}/{norm_slug}_keywords_registry_{YYYYMMDDTHHMMSS}.json
    e.g. output/iso90012015_keywords_registry_20260318T154300.json
    
    Registry JSON structure
    -----------------------
    {
      "standard_id":  "ISO 9001:2015",
      "generated_at": "2026-03-18T15:43:00.123456",
      "chunk_count":  95,
      "entries": [
        {
          "norm_id": "ISO 9001:2015",
          "clause_number": "4.1",
          "keywords": ["context", "organization", "understanding"]
        },
        ...
      ]
    }
    
    Parameters
    ----------
    result     : SegmenterResult (duck-typed: must have .standard_id, .chunks).
    output_dir : Target directory (created if absent).
    
    Returns
    -------
    str — absolute path to the written registry file.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # "ISO 9001:2015" → "iso90012015"  (remove non-alphanumeric, lowercase)
    norm_slug = re.sub(r'[^a-z0-9]', '', result.standard_id.lower())
    
    ts       = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    filename = f"{norm_slug}_keywords_registry_{ts}.json"
    filepath = os.path.join(output_dir, filename)
    
    # Build entries list
    entries = []
    for chunk in result.chunks:
        entries.append({
            "norm_id": chunk.norm_full,  # Full norm identifier
            "clause_number": chunk.clause_number,
            "keywords": chunk.keywords if chunk.keywords else []
        })
    
    registry = {
        "standard_id": result.standard_id,
        "generated_at": datetime.datetime.now().isoformat(),
        "chunk_count": len(entries),
        "entries": entries
    }
    
    # Consistency gate
    assert registry["chunk_count"] == len(registry["entries"]), (
        f"chunk_count={registry['chunk_count']} != "
        f"len(entries)={len(registry['entries'])}"
    )
    
    with open(filepath, 'w', encoding='utf-8') as fh:
        _json.dump(registry, fh, ensure_ascii=False, indent=2)
    
    # Update the stable latest-pointer for keywords registry
    latest_path = os.path.join(output_dir, f"{norm_slug}_keywords_registry_latest.txt")
    with open(latest_path, 'w', encoding='utf-8') as fh:
        fh.write(filename + '\n')
    
    return filepath


def write_normid_clause_bm25_registry(result, output_dir: str = "output") -> str:
    """
    Write a specialized registry containing norm_id, clause_number, and BM25 tokens.
    
    This registry focuses on BM25 tokenization data for retrieval-augmented
    generation (RAG) systems, providing token-level search capabilities.
    
    File naming
    -----------
    Each run produces a unique file:
      {output_dir}/{norm_slug}_bm25_registry_{YYYYMMDDTHHMMSS}.json
    e.g. output/iso90012015_bm25_registry_20260318T154300.json
    
    Registry JSON structure
    -----------------------
    {
      "standard_id":  "ISO 9001:2015",
      "generated_at": "2026-03-18T15:43:00.123456",
      "chunk_count":  95,
      "entries": [
        {
          "norm_id": "ISO 9001:2015",
          "clause_number": "4.1",
          "bm25_tokens": ["context", "organization", "understand", "requirement"],
          "token_count": 4
        },
        ...
      ]
    }
    
    Parameters
    ----------
    result     : SegmenterResult (duck-typed: must have .standard_id, .chunks).
    output_dir : Target directory (created if absent).
    
    Returns
    -------
    str — absolute path to the written registry file.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # "ISO 9001:2015" → "iso90012015"  (remove non-alphanumeric, lowercase)
    norm_slug = re.sub(r'[^a-z0-9]', '', result.standard_id.lower())
    
    ts       = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    filename = f"{norm_slug}_bm25_registry_{ts}.json"
    filepath = os.path.join(output_dir, filename)
    
    # Build entries list
    entries = []
    for chunk in result.chunks:
        bm25_tokens = chunk.bm25_tokens if chunk.bm25_tokens else []
        entries.append({
            "norm_id": chunk.norm_full,  # Full norm identifier
            "clause_number": chunk.clause_number,
            "bm25_tokens": bm25_tokens,
            "token_count": len(bm25_tokens)
        })
    
    registry = {
        "standard_id": result.standard_id,
        "generated_at": datetime.datetime.now().isoformat(),
        "chunk_count": len(entries),
        "entries": entries
    }
    
    # Consistency gate
    assert registry["chunk_count"] == len(registry["entries"]), (
        f"chunk_count={registry['chunk_count']} != "
        f"len(entries)={len(registry['entries'])}"
    )
    
    with open(filepath, 'w', encoding='utf-8') as fh:
        _json.dump(registry, fh, ensure_ascii=False, indent=2)
    
    # Update the stable latest-pointer for BM25 registry
    latest_path = os.path.join(output_dir, f"{norm_slug}_bm25_registry_latest.txt")
    with open(latest_path, 'w', encoding='utf-8') as fh:
        fh.write(filename + '\n')
    
    return filepath


def _sqlite_norm_key(norm_id: str, norm_version: str, language: str) -> str:
    return f"{norm_id}:{norm_version}:{language}"


def _sqlite_extract_norm_identity(chunks: List[NormChunk]) -> Tuple[str, str, str]:
    if not chunks:
        return "", "", "EN"
    first = chunks[0]
    norm_id = (first.norm_id or "").strip()
    norm_version = (first.norm_version or "").strip()
    language = (first.language or "EN").strip().upper()
    return norm_id, norm_version, language


def _canonical_sqlite_db_path(db_path: str) -> str:
    requested = os.path.abspath(db_path)
    directory = os.path.dirname(requested)
    return os.path.join(directory, _CANONICAL_SQLITE_DB_FILENAME)


def _sqlite_create_persistent_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS iso_norms (
            norm_key      TEXT PRIMARY KEY,
            norm_id       TEXT NOT NULL,
            norm_version  TEXT NOT NULL DEFAULT '',
            language      TEXT NOT NULL DEFAULT 'EN',
            norm_full     TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(norm_id, norm_version, language)
        );

        CREATE TABLE IF NOT EXISTS iso_clauses (
            norm_key          TEXT NOT NULL,
            norm_id           TEXT NOT NULL,
            norm_version      TEXT NOT NULL DEFAULT '',
            language          TEXT NOT NULL DEFAULT 'EN',
            clause_number     TEXT NOT NULL,
            clause_title      TEXT NOT NULL,
            parent_clause     TEXT NOT NULL,
            top_level_family  TEXT NOT NULL DEFAULT '',
            text              TEXT NOT NULL,
            has_requirements  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (norm_key, clause_number),
            FOREIGN KEY (norm_key) REFERENCES iso_norms(norm_key) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_iso_norm_identity
            ON iso_norms(norm_id, norm_version, language);
        CREATE INDEX IF NOT EXISTS idx_clause_norm_key
            ON iso_clauses(norm_key);
        CREATE INDEX IF NOT EXISTS idx_clause_norm_id
            ON iso_clauses(norm_id);
        CREATE INDEX IF NOT EXISTS idx_clause_family
            ON iso_clauses(norm_id, top_level_family);
        """
    )


def _sqlite_migrate_legacy_if_needed(conn: sqlite3.Connection) -> None:
    table = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name='iso_clauses'
        """
    ).fetchone()
    if not table:
        return

    columns = [
        row[1]
        for row in conn.execute("PRAGMA table_info(iso_clauses)").fetchall()
    ]
    if "norm_key" in columns:
        return

    legacy_table = "iso_clauses_legacy"
    conn.execute(f"DROP TABLE IF EXISTS {legacy_table}")
    conn.execute("ALTER TABLE iso_clauses RENAME TO iso_clauses_legacy")

    _sqlite_create_persistent_schema(conn)

    legacy_cols = {
        row[1] for row in conn.execute(f"PRAGMA table_info({legacy_table})").fetchall()
    }
    has_top_level_family = "top_level_family" in legacy_cols
    has_language = "language" in legacy_cols

    legacy_rows = conn.execute(
        f"""
        SELECT
            norm_id,
            clause_number,
            clause_title,
            parent_clause,
            {"top_level_family," if has_top_level_family else "'' AS top_level_family,"}
            {"language," if has_language else "'EN' AS language,"}
            text,
            has_requirements
        FROM {legacy_table}
        """
    ).fetchall()

    norm_rows: Dict[str, Tuple[str, str, str, str]] = {}
    clause_rows: List[Tuple[str, str, str, str, str, str, str, str, str, int]] = []
    for row in legacy_rows:
        norm_id = (row[0] or "").strip()
        clause_number = (row[1] or "").strip()
        clause_title = row[2] or ""
        parent_clause = row[3] or ""
        top_level_family = (row[4] or "").strip()
        language = (row[5] or "EN").strip().upper()
        text = row[6] or ""
        has_requirements = int(row[7] or 0)

        norm_version = ""
        norm_key = _sqlite_norm_key(norm_id, norm_version, language)
        norm_rows[norm_key] = (norm_key, norm_id, norm_version, language, norm_id or "UNKNOWN")

        if not top_level_family:
            top_level_family = clause_number.split(".")[0] if clause_number else ""

        clause_rows.append(
            (
                norm_key,
                norm_id,
                norm_version,
                language,
                clause_number,
                clause_title,
                parent_clause,
                top_level_family,
                text,
                has_requirements,
            )
        )

    if norm_rows:
        conn.executemany(
            """
            INSERT OR IGNORE INTO iso_norms (
                norm_key,
                norm_id,
                norm_version,
                language,
                norm_full
            ) VALUES (?, ?, ?, ?, ?)
            """,
            list(norm_rows.values()),
        )
    if clause_rows:
        conn.executemany(
            """
            INSERT INTO iso_clauses (
                norm_key,
                norm_id,
                norm_version,
                language,
                clause_number,
                clause_title,
                parent_clause,
                top_level_family,
                text,
                has_requirements
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            clause_rows,
        )

    conn.execute(f"DROP TABLE {legacy_table}")


def _merge_sqlite_db_files(source_path: str, target_path: str) -> None:
    source_abs = os.path.abspath(source_path)
    target_abs = os.path.abspath(target_path)
    if source_abs == target_abs or not os.path.exists(source_abs):
        return

    target_dir = os.path.dirname(target_abs)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)

    with sqlite3.connect(target_abs) as target_conn, sqlite3.connect(source_abs) as source_conn:
        target_conn.execute("PRAGMA foreign_keys = ON")
        source_conn.execute("PRAGMA foreign_keys = ON")

        _sqlite_migrate_legacy_if_needed(source_conn)
        _sqlite_create_persistent_schema(source_conn)
        _sqlite_migrate_legacy_if_needed(target_conn)
        _sqlite_create_persistent_schema(target_conn)

        norm_rows = source_conn.execute(
            """
            SELECT norm_key, norm_id, norm_version, language, norm_full, created_at
            FROM iso_norms
            """
        ).fetchall()
        if norm_rows:
            target_conn.executemany(
                """
                INSERT OR IGNORE INTO iso_norms (
                    norm_key, norm_id, norm_version, language, norm_full, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                norm_rows,
            )

        clause_rows = source_conn.execute(
            """
            SELECT
                norm_key,
                norm_id,
                norm_version,
                language,
                clause_number,
                clause_title,
                parent_clause,
                top_level_family,
                text,
                has_requirements
            FROM iso_clauses
            """
        ).fetchall()
        if clause_rows:
            target_conn.executemany(
                """
                INSERT INTO iso_clauses (
                    norm_key,
                    norm_id,
                    norm_version,
                    language,
                    clause_number,
                    clause_title,
                    parent_clause,
                    top_level_family,
                    text,
                    has_requirements
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(norm_key, clause_number) DO UPDATE SET
                    clause_title = excluded.clause_title,
                    parent_clause = excluded.parent_clause,
                    top_level_family = excluded.top_level_family,
                    text = excluded.text,
                    has_requirements = excluded.has_requirements
                """,
                clause_rows,
            )
        target_conn.commit()

    os.remove(source_abs)


def write_sqlite_clause_registry(
    result,
    db_path: str = "output/iso_clauses.db",
    if_exists: str = "skip",
) -> int:
    """
    Persist clause data into a norm-aware SQLite schema.

    Behavior for existing norm identity (norm_id, norm_version, language):
      • "skip"   (default): add-only, no overwrite
      • "upsert": replace rows for that norm by upserting clauses
      • "error" : raise RuntimeError
    """
    if if_exists not in {"skip", "upsert", "error"}:
        raise ValueError(f"Unsupported if_exists mode: {if_exists!r}")

    requested_db_path = os.path.abspath(db_path)
    db_path = _canonical_sqlite_db_path(requested_db_path)
    if requested_db_path != db_path:
        warnings.warn(
            f"[Registry] Normalizing SQLite path to canonical file {db_path} "
            f"(requested {requested_db_path})",
            UserWarning,
            stacklevel=2,
        )
        _merge_sqlite_db_files(requested_db_path, db_path)

    alias_path = os.path.join(
        os.path.dirname(db_path),
        _LEGACY_ALIAS_SQLITE_DB_FILENAME,
    )
    _merge_sqlite_db_files(alias_path, db_path)

    chunks = list(result.chunks)
    if not chunks:
        return 0

    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    norm_id, norm_version, language = _sqlite_extract_norm_identity(chunks)
    norm_key = _sqlite_norm_key(norm_id, norm_version, language)
    norm_full = chunks[0].norm_full or norm_id

    grouped: Dict[str, List[NormChunk]] = {}
    for chunk in chunks:
        grouped.setdefault(chunk.clause_number, []).append(chunk)

    rows: List[Tuple[str, str, str, str, str, str, str, str, str, int]] = []
    for clause_number, clause_chunks in grouped.items():
        ordered = sorted(
            clause_chunks,
            key=lambda c: (c.chunk_index, c.page_number, c.chunk_id),
        )
        first = ordered[0]
        top_level_family = first.clause_family or (
            clause_number.split(".")[0] if clause_number else ""
        )
        merged_text = "\n\n".join(
            part.text.strip() for part in ordered if part.text and part.text.strip()
        )
        effective_title = _sqlite_effective_clause_title(
            clause_title=first.clause_title,
            clause_number=clause_number,
            merged_text=merged_text,
        )
        rows.append(
            (
                norm_key,
                norm_id,
                norm_version,
                language,
                clause_number,
                effective_title,
                first.parent_clause or "",
                top_level_family,
                merged_text,
                1 if any(part.has_requirements for part in ordered) else 0,
            )
        )

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _sqlite_migrate_legacy_if_needed(conn)
        _sqlite_create_persistent_schema(conn)

        existing = conn.execute(
            """
            SELECT 1
            FROM iso_norms
            WHERE norm_id = ? AND norm_version = ? AND language = ?
            LIMIT 1
            """,
            (norm_id, norm_version, language),
        ).fetchone()

        if existing:
            if if_exists == "skip":
                return 0
            if if_exists == "error":
                raise RuntimeError(
                    "Norm already exists in SQLite registry: "
                    f"{norm_id}:{norm_version}:{language}"
                )
        else:
            conn.execute(
                """
                INSERT INTO iso_norms (
                    norm_key,
                    norm_id,
                    norm_version,
                    language,
                    norm_full
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (norm_key, norm_id, norm_version, language, norm_full),
            )

        if if_exists == "upsert":
            conn.execute(
                "DELETE FROM iso_clauses WHERE norm_key = ?",
                (norm_key,),
            )

        conn.executemany(
            """
            INSERT INTO iso_clauses (
                norm_key,
                norm_id,
                norm_version,
                language,
                clause_number,
                clause_title,
                parent_clause,
                top_level_family,
                text,
                has_requirements
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(norm_key, clause_number) DO UPDATE SET
                clause_title = excluded.clause_title,
                parent_clause = excluded.parent_clause,
                top_level_family = excluded.top_level_family,
                text = excluded.text,
                has_requirements = excluded.has_requirements
            """,
            rows,
        )
        conn.commit()

    return len(rows)


def delete_norm_from_sqlite_registry(
    db_path: str,
    norm_id: str,
    norm_version: str = "",
    language: str = "EN",
) -> int:
    """
    Delete one norm identity from SQLite registry.

    Returns the number of deleted norm records (0 or 1).
    Clause rows are deleted automatically by ON DELETE CASCADE.
    """
    requested_db_path = os.path.abspath(db_path)
    db_path = _canonical_sqlite_db_path(requested_db_path)
    if requested_db_path != db_path:
        _merge_sqlite_db_files(requested_db_path, db_path)

    alias_path = os.path.join(
        os.path.dirname(db_path),
        _LEGACY_ALIAS_SQLITE_DB_FILENAME,
    )
    _merge_sqlite_db_files(alias_path, db_path)

    if not os.path.exists(db_path):
        return 0

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _sqlite_migrate_legacy_if_needed(conn)
        _sqlite_create_persistent_schema(conn)
        cur = conn.execute(
            """
            DELETE FROM iso_norms
            WHERE norm_id = ? AND norm_version = ? AND language = ?
            """,
            (norm_id, norm_version, language.upper()),
        )
        conn.commit()
        return cur.rowcount
