from __future__ import annotations

from typing import Callable

from langgraph.config import get_stream_writer

from rag.retrival import RetrievalService
from rag.retrival.query_retrival import EmptyCorpusError

from .state import AgentState


def _emit(node: str, event: str, msg: str) -> None:
    """Push a structured log event through the LangGraph stream writer."""
    get_stream_writer()({"node": node, "event": event, "msg": msg})


def make_retrieve_node(service: RetrievalService) -> Callable[[AgentState], dict]:
    """Factory that closes over a RetrievalService and returns an async LangGraph node.

    Iterates over the sections produced by parse + classify nodes and calls
    RetrievalService.retrieve() for each section individually, using:
      - section.raw_text  as the retrieval query
      - section.scope.domains          → norm_filter
      - section.scope.clause_families  → clause_families filter
      - section.scope.specific_clauses → soft BM25 boost

    Sections without a scope or with empty domains are skipped.
    Per-section EmptyCorpusError is logged and treated as zero results (non-fatal).
    Any other unexpected error on a single section is logged and skipped so the
    remaining sections are still processed.

    Args:
        service: A fully-initialised RetrievalService instance.

    Returns:
        An async node function compatible with StateGraph.add_node().
    """

    async def retrieve_node(state: AgentState) -> dict:
        sections = state.get("sections") or []

        if not sections:
            msg = "retrieve_node: sections list is empty — nothing to retrieve"
            _emit("retrieve", "error", msg)
            return {"error": msg, "status": "error"}

        language = state.get("retrieval_language") or "EN"
        results: list[dict] = []
        skipped = 0
        total_chunks = 0

        _emit("retrieve", "start", f"Retrieving norm clauses for {len(sections)} sections (lang={language})...")

        for section in sections:
            scope = section.scope

            # Skip sections that were not classified or have no domain
            if scope is None or not scope.domains:
                skipped += 1
                continue

            # Use raw_text as query; fall back to title for very short sections
            query = (section.raw_text or "").strip()
            if not query:
                query = section.title.strip()
            if not query:
                skipped += 1
                continue

            norm_filter = [str(d) for d in scope.domains]

            try:
                chunks = await service.retrieve(
                    query=query,
                    norm_filter=norm_filter,
                    language=language,
                    clause_families=scope.clause_families,
                    specific_clauses=scope.specific_clauses,
                )
            except EmptyCorpusError:
                # No matching norm clauses for this section — record as empty, continue
                chunks = []
            except ValueError as exc:
                # Empty norm_filter or bad args — log and skip this section
                _emit("retrieve", "start", f"  skip [{section.id}]: invalid args — {exc}")
                skipped += 1
                continue
            except Exception as exc:
                # Network / Qdrant error on a single section — log and skip
                _emit("retrieve", "start", f"  skip [{section.id}]: {type(exc).__name__}: {exc}")
                skipped += 1
                continue

            results.append({
                "section_id": section.id,
                "section_title": section.title,
                "chunks": chunks,
            })
            total_chunks += len(chunks)

        _emit(
            "retrieve",
            "done",
            f"{total_chunks} chunks across {len(results)} sections "
            f"({skipped} skipped)",
        )
        return {"section_retrievals": results, "status": "retrieved"}

    return retrieve_node