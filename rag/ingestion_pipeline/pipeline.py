"""
pipeline.py
────────────
Top-level orchestrator for the ISO standard ingestion pipeline.

This module wires together all four pipeline packages (segmenter, chunker,
enricher, registry) into two public entry points:

  segment_document(doc)
      Executes Phases 1–5 in sequence.  No file I/O.  Use this for testing
      or when you need the result without writing registry output.

  segment(doc, output_dir)
      Full pipeline (Phases 1–6).  Calls segment_document(), then validates
      chunks (Phase 6a) and writes the registry JSON (Phase 6b).

  embed_and_store(result, collection)
      Phase 7 — opt-in embedding and Qdrant upsert.  Activate by setting
      EMBEDDING_ENABLED=true.  Never raises; failures are UserWarnings.

Data flow
---------
  ParsedDocument
    → Phase 1  PageTracker.page_at()                — offset → page mapping
    → Phase 2  detect_clause_boundaries()           → List[ClauseSpan]
    → Phase 3  construct_clause_tree()              → ClauseNode (root)
    → Phase 4  assemble_norm_chunks()               → List[NormChunk]
    → Phase 5  Enricher.enrich()                    → List[NormChunk] (enriched)
    → Phase 6a validate_chunks()                    → warnings only
    → Phase 6b write_registry()                     → JSON file
    → SegmenterResult
    → Phase 7  EmbedderService.embed_chunks()       → List[EmbeddedChunk]
               VectorStoreManager.upsert_chunks()   → Qdrant collection

SegmenterResult
---------------
  standard_id : Human-readable standard label, e.g. "ISO 9001:2015".
  tree        : ClauseNode root — full recursive clause hierarchy.
  chunks      : List[NormChunk] — enriched retrieval units.

Design rule: this module contains NO business logic.  Its only job is
orchestration — calling each phase in order and assembling the final result.
If a phase needs to change, only that phase's module changes.

Dependency rule: this is the only module that imports from all four packages.
No other module may import from pipeline.py.
"""

from __future__ import annotations

import asyncio
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import List

from rag.ingestion_pipeline.pdf_parser.document import ParsedDocument

from rag.ingestion_pipeline.chunker import NormChunk, assemble_norm_chunks
from rag.ingestion_pipeline.enricher import Enricher
from rag.ingestion_pipeline.registry import (
    validate_chunks,
    write_normid_clause_bm25_registry,
    write_normid_clause_keywords_registry,
    write_registry,
    write_sqlite_clause_registry,
)
from rag.ingestion_pipeline.segmenter import (
    STANDARD_ID_MAP,
    ClauseNode,
    PageTracker,
    construct_clause_tree,
    detect_clause_boundaries,
)


# ==============================================================================
# Pipeline output container
# ==============================================================================

@dataclass
class SegmenterResult:
    """
    Combined output of the full ingestion pipeline.

    Defined here (not in any sub-package) because it wraps outputs from both
    the segmenter (tree: ClauseNode) and the chunker+enricher (chunks:
    List[NormChunk]).  Placing it in either sub-package would require that
    package to import from the other, reversing the dependency direction.

    Fields
    ------
    standard_id : Human-readable standard label, e.g. "ISO 9001:2015".
    tree        : Root ClauseNode of the full clause hierarchy.
    chunks      : Enriched NormChunk list — the primary retrieval artefacts.
    """

    standard_id: str
    tree: ClauseNode
    chunks: List[NormChunk]


def _env_flag(var_name: str, default: bool = False) -> bool:
    """
    Parse a boolean environment flag.

    Truthy values: 1, true, yes, on, y (case-insensitive).
    """
    raw = os.getenv(var_name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _default_sqlite_registry_path() -> str:
    """
    Canonical default SQLite registry location for all services.

    Points to:
      <repo_root>/agent_compliance/data/iso_clauses.db
    """
    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "agent_compliance" / "data" / "iso_clauses.db")


# ==============================================================================
# Public entry points
# ==============================================================================

def segment_document(doc: ParsedDocument, language: str = "") -> SegmenterResult:
    """
    Execute the core ingestion pipeline (Phases 1–5).  No file I/O.

    Use this entry point for:
      • Unit testing — results are in-memory only.
      • Embedding pipelines that manage their own output.
      • Any caller that does not need registry JSON.

    Phases executed
    ---------------
    1. PageTracker construction  — O(n log n) sort on page_map keys.
    2. Clause boundary detection — heading_positions → List[ClauseSpan].
    3. Clause tree construction  — ClauseSpan list → ClauseNode tree.
    4. NormChunk assembly        — ClauseSpan list → List[NormChunk].
    5. Retrieval enrichment      — TF-IDF keywords + BM25 tokens.

    Parameters
    ----------
    doc      : ParsedDocument produced by parse_iso_pdf().
    language : ISO 639-1 code of the document language ("EN" or "FR").
               Stamped onto every NormChunk.  Empty string when not provided.
               The ingestion API will pass this value; use it directly here
               until that layer exists.

    Returns
    -------
    SegmenterResult — fully populated, keywords and bm25_tokens set.
    """
    # Phase 1 — build page resolver from parser's page_map
    tracker = PageTracker(doc.page_map)

    # Phase 2 — detect clause boundaries from heading_positions
    spans = detect_clause_boundaries(doc)

    # Phase 3 — assemble flat spans into a recursive clause tree
    tree = construct_clause_tree(spans, doc.markdown, doc.standard_id)

    # Phase 4 — convert each span into one or more NormChunks
    chunks = assemble_norm_chunks(spans, doc.markdown, doc.standard_id, tracker)

    # Phase 5 — add TF-IDF keywords and BM25 tokens to every chunk
    # Pass language so the enricher can apply the correct ISO vocabulary
    # (EN or FR) for symmetric BM25 token normalization with the query side.
    Enricher(chunks, language=language or "EN").enrich(chunks)

    # Stamp language onto every chunk (set by caller, not detected)
    if language:
        for chunk in chunks:
            chunk.language = language

    std_name = STANDARD_ID_MAP.get(doc.standard_id, doc.standard_id)
    return SegmenterResult(standard_id=std_name, tree=tree, chunks=chunks)


def segment(
    doc: ParsedDocument,
    output_dir: str = "output",
    language: str = "",
    sqlite_registry_enabled: bool | None = None,
    sqlite_db_path: str | None = None,
    sqlite_if_exists: str | None = None,
) -> SegmenterResult:
    """
    Full pipeline entry point (Phases 1–6).

    Runs segment_document() (Phases 1–5), then:
      Phase 6a — Pydantic structural validation (warnings only, never raises).
      Phase 6b — Writes a timestamped registry JSON file and updates the
                 stable latest-pointer file.
      Phase 6c — Optional SQLite clause registry write (flag-controlled).

    The registry path is printed to stdout for operator visibility.

    Parameters
    ----------
    doc        : ParsedDocument produced by parse_iso_pdf().
    output_dir : Directory to write registry files into (created if absent).
    language   : ISO 639-1 code of the document language ("EN" or "FR").
                 Forwarded to segment_document() and stamped on all chunks.
    sqlite_registry_enabled : Optional override for SQLite registry writing.
                              If None, reads SQLITE_REGISTRY_ENABLED (default false).
    sqlite_db_path          : Optional SQLite DB path override.
                              If None, reads SQLITE_REGISTRY_PATH, falling back to
                              agent_compliance/data/iso_clauses.db.
    sqlite_if_exists        : Behavior when norm already exists in SQLite.
                              One of: "skip" (default), "upsert", "error".
                              If None, reads SQLITE_REGISTRY_IF_EXISTS.

    Returns
    -------
    SegmenterResult — identical to what segment_document() returns.
    """
    result = segment_document(doc, language=language)

    # Phase 6a — validate structural invariants (warnings only)
    validate_chunks(result.chunks)

    # Phase 6b — persist registry JSON + latest-pointer
    registry_path = write_registry(result, output_dir=output_dir)
    print(f"[Registry] Written → {registry_path}")
    write_normid_clause_keywords_registry(result, output_dir=output_dir)
    write_normid_clause_bm25_registry(result, output_dir=output_dir)

    if sqlite_registry_enabled is None:
        sqlite_registry_enabled = _env_flag("SQLITE_REGISTRY_ENABLED", default=False)
    if sqlite_db_path is None:
        sqlite_db_path = os.getenv(
            "SQLITE_REGISTRY_PATH",
            _default_sqlite_registry_path(),
        )
    sqlite_db_path = os.path.join(os.path.dirname(os.path.abspath(sqlite_db_path)), "iso_clauses.db")
    if sqlite_if_exists is None:
        sqlite_if_exists = os.getenv("SQLITE_REGISTRY_IF_EXISTS", "skip")
    if sqlite_registry_enabled:
        clause_count = write_sqlite_clause_registry(
            result,
            db_path=sqlite_db_path,
            if_exists=sqlite_if_exists,
        )
        verb = "inserted" if clause_count else "skipped"
        print(
            f"[Registry] SQLite {verb} {clause_count} clauses "
            f"(if_exists={sqlite_if_exists}) → "
            f"{os.path.abspath(sqlite_db_path)}"
        )

    return result


def embed_and_store(
    result: SegmenterResult,
    collection: str = "norms",
) -> int:
    """
    Phase 7 — Embed enriched chunks and upsert into Qdrant.

    This is a synchronous wrapper around the async EmbedderService.
    asyncio.run() drives the async embedding step; VectorStoreManager
    upsert is synchronous (qdrant-client sync API).

    Imports for embedder and vector_store are deferred inside this function
    so that importing pipeline.py without those packages installed never
    raises ImportError — phases 1–6 remain unaffected.

    Raises
    ------
    RuntimeError
        • If the embedding model does not match the model used to build the
          existing Qdrant collection (model-space mismatch guard).
        • If the embedding failure rate exceeds EMBED_CRITICAL_THRESHOLD
          (default 30 %).  Prevents a partial-failure run from silently
          corrupting the collection with gaps.
    UserWarning
        Emitted (without raising) when failure_rate > EMBED_WARNING_THRESHOLD
        (default 10 %).

    Parameters
    ----------
    result     : SegmenterResult from segment() or segment_document().
    collection : Qdrant collection name to upsert into (default: "norms").

    Returns
    -------
    int — count of chunks successfully embedded and upserted (0 on failure).
    """
    try:
        from rag.ingestion_pipeline.embedder import EmbedderService, EmbeddingResult
        from rag.ingestion_pipeline.embedder.config import EMBED_CRITICAL_THRESHOLD, EMBED_WARNING_THRESHOLD
        from rag.ingestion_pipeline.vector_store import VectorStoreManager
    except ImportError as exc:
        warnings.warn(
            f"[Phase 7] Import failed — embedding skipped: {exc}",
            UserWarning,
            stacklevel=2,
        )
        return 0

    embedder = EmbedderService()
    store = VectorStoreManager()

    # ── Model mismatch guard ─────────────────────────────────────────────────
    # Validate before embedding to avoid wasting compute on an incompatible run.
    # Raises RuntimeError on mismatch; emits UserWarning for legacy collections.
    store.validate_model_consistency(collection, embedder._model_name)

    # ── Embed ────────────────────────────────────────────────────────────────
    embedding_result: EmbeddingResult
    try:
        embedding_result = asyncio.run(embedder.embed_chunks(result.chunks, collection))
    except Exception as exc:
        warnings.warn(
            f"[Phase 7] Embedding step failed: {exc}",
            UserWarning,
            stacklevel=2,
        )
        return 0
    finally:
        try:
            asyncio.run(embedder.close())
        except Exception:
            pass

    # ── Failure-rate thresholds ──────────────────────────────────────────────
    if embedding_result.failure_rate > EMBED_WARNING_THRESHOLD:
        warnings.warn(
            f"[Phase 7] High embedding failure rate: "
            f"{embedding_result.failure_rate:.1%} "
            f"({len(embedding_result.failed_chunks)} chunks failed). "
            "Check Ollama connectivity or model availability.",
            UserWarning,
            stacklevel=2,
        )

    if embedding_result.failure_rate > EMBED_CRITICAL_THRESHOLD:
        raise RuntimeError(
            f"[Phase 7] Critical embedding failure rate "
            f"{embedding_result.failure_rate:.1%} exceeds threshold "
            f"{EMBED_CRITICAL_THRESHOLD:.1%}. Aborting upsert to prevent "
            "partial collection corruption."
        )

    if not embedding_result.embedded:
        return 0

    # ── Upsert ───────────────────────────────────────────────────────────────
    count = store.upsert_chunks(embedding_result.embedded, collection_name=collection)
    print(f"[Phase 7] Upserted {count} chunks into Qdrant collection '{collection}'")
    return count
