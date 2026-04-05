from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from typing import AsyncIterator

import requests
from langgraph.types import Command
from qdrant_client import QdrantClient

from rag.retrival import RetrievalService
from rag.retrival.re_ranker import Reranker

from .graph import build_graph

_QDRANT_HOST  = os.getenv("QDRANT_HOST", "localhost")
_QDRANT_PORT  = int(os.getenv("QDRANT_PORT", "6333"))
_OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
_COLLECTION   = os.getenv("QDRANT_COLLECTION", "norms")

_EVENT_PREFIX = {"start": "...", "done": "✓", "error": "✗"}


class _OllamaEmbedder:
    """Minimal async embedder backed by a local Ollama server."""

    def __init__(self, base_url: str, model: str) -> None:
        self._endpoint = f"{base_url}/api/embeddings"
        self._model = model

    async def embed_text(self, text: str) -> list:
        resp = await asyncio.to_thread(
            requests.post,
            self._endpoint,
            json={"model": self._model, "prompt": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    async def close(self) -> None:
        pass  # no persistent connection to release


def _build_retrieval_service() -> RetrievalService:
    """Construct a live RetrievalService from environment variables."""
    embedder = _OllamaEmbedder(_OLLAMA_URL, _OLLAMA_MODEL)
    qdrant   = QdrantClient(host=_QDRANT_HOST, port=_QDRANT_PORT)
    reranker = Reranker()
    return RetrievalService(
        embedder=embedder,
        qdrant=qdrant,
        reranker=reranker,
        collection=_COLLECTION,
    )


def _initial_state(document_path: str, language: str = "EN") -> dict:
    return {
        "document_path": document_path,
        "parse_result": None,
        "sections": [],
        "quality_tier": None,
        "min_confidence": None,
        "low_quality_flag": False,
        "registry_metadata": {},
        "document_scope": None,
        "retrieval_language": language,
        "section_retrievals": [],
        "error": None,
        "status": "pending",
    }


def _config(thread_id: str | None) -> dict:
    return {"configurable": {"thread_id": thread_id or str(uuid.uuid4())}}


async def run(
    document_path: str,
    thread_id: str | None = None,
    language: str = "EN",
    retrieval_service: RetrievalService | None = None,
) -> dict:
    """Invoke the graph and return the final state. Used by the API layer."""
    g = build_graph(retrieval_service=retrieval_service)
    return await g.ainvoke(_initial_state(document_path, language=language), _config(thread_id))


async def stream_run(
    document_path: str,
    thread_id: str | None = None,
    language: str = "EN",
    retrieval_service: RetrievalService | None = None,
) -> AsyncIterator[dict]:
    """Stream log events from the graph as they are emitted.

    Each yielded item is a dict: {"node": str, "event": str, "msg": str}.
    The last item has event == "final" and carries the full result state.

    If the graph pauses at an interrupt (low-quality document), the final
    item will instead have event == "interrupted" and carry the interrupt
    payload so callers can surface it to the user and call ``resume_run()``.
    """
    tid = thread_id or str(uuid.uuid4())
    config = _config(tid)
    final_state: dict = {}
    interrupt_payload: list = []

    g = build_graph(retrieval_service=retrieval_service)
    async for mode, chunk in g.astream(
        _initial_state(document_path, language=language),
        config,
        stream_mode=["custom", "values", "updates"],
    ):
        if mode == "custom" and isinstance(chunk, dict) and "node" in chunk:
            yield chunk
        elif mode == "values":
            final_state = chunk
        elif mode == "updates" and "__interrupt__" in chunk:
            interrupt_payload = chunk["__interrupt__"]

    if interrupt_payload:
        yield {
            "node": "__interrupt__",
            "event": "interrupted",
            "msg": "Graph paused — human review required",
            "thread_id": tid,
            "interrupt": [
                {"value": i.value} for i in interrupt_payload
            ],
        }
    else:
        yield {"node": "__final__", "event": "final", "msg": "", "state": final_state}


async def resume_run(
    thread_id: str,
    decision: str,
    retrieval_service: RetrievalService | None = None,
) -> dict:
    """Resume a paused graph after a human_review interrupt.

    Args:
        thread_id:         The thread ID from the interrupted ``stream_run()`` event.
        decision:          ``"proceed"`` to continue classification or ``"abort"`` to stop.
        retrieval_service: Service instance needed to execute retrieve_node after resuming.

    Returns:
        Final agent state after resuming.
    """
    g = build_graph(retrieval_service=retrieval_service)
    return await g.ainvoke(Command(resume=decision), _config(thread_id))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compliance document parser + classifier + retrieval agent (v3).")
    p.add_argument("file_path", nargs="+", help="Path to PDF or DOCX file.")
    p.add_argument("--json", action="store_true", help="Print sections and retrievals as JSON.")
    p.add_argument("--thread-id", default=None, help="Thread ID for resuming an interrupted run.")
    p.add_argument(
        "--resume",
        choices=["proceed", "abort"],
        default=None,
        help="Resume a paused graph: 'proceed' or 'abort'. Requires --thread-id.",
    )
    p.add_argument("--language", choices=["EN", "FR"], default="EN", help="Retrieval language (default: EN).")
    p.add_argument("--no-retrieval", action="store_true", help="Skip retrieval (classify only, no Qdrant calls).")
    return p


async def _async_main(args: argparse.Namespace) -> int:
    file_path = " ".join(args.file_path)

    retrieval_service: RetrievalService | None = None
    if not getattr(args, "no_retrieval", False):
        retrieval_service = _build_retrieval_service()
        print(f"  [retrieval] Qdrant={_QDRANT_HOST}:{_QDRANT_PORT}  model={_OLLAMA_MODEL}  collection={_COLLECTION}")

    # --- Resume path ---
    if args.resume:
        if not args.thread_id:
            print("Error: --resume requires --thread-id")
            return 1
        result = await resume_run(args.thread_id, args.resume, retrieval_service=retrieval_service)
        _print_result(result, args.json)
        return 0 if not result.get("error") else 1

    # --- Normal run path ---
    result: dict = {}
    interrupted_event: dict | None = None

    async for event in stream_run(file_path, thread_id=args.thread_id, language=args.language, retrieval_service=retrieval_service):
        if event["event"] == "final":
            result = event["state"]
            break
        if event["event"] == "interrupted":
            interrupted_event = event
            break
        prefix = _EVENT_PREFIX.get(event["event"], "  ")
        print(f"  {prefix} [{event['node']}] {event['msg']}")

    print()

    if interrupted_event:
        payload = interrupted_event["interrupt"][0]["value"]
        print(f"⏸  PAUSED — {payload['question']}")
        print(f"   Quality tier : {payload['quality_tier']}")
        print(f"   Min confidence: {payload['min_confidence']:.2f}")
        print(f"\n   Resume with:")
        print(f"     python -m agent_compliance.graph.run \"{file_path}\" "
              f"--thread-id {interrupted_event['thread_id']} --resume proceed")
        print(f"     python -m agent_compliance.graph.run \"{file_path}\" "
              f"--thread-id {interrupted_event['thread_id']} --resume abort")
        return 0

    _print_result(result, args.json)
    return 0 if not result.get("error") else 1


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_async_main(args))


def _print_result(result: dict, print_json: bool) -> None:
    if result.get("error"):
        print(f"Error: {result['error']}")
        return

    print(f"Quality tier  : {result['quality_tier']}")
    print(f"Min confidence: {result['min_confidence']:.2f}")
    print(f"Low quality   : {result['low_quality_flag']}")
    print(f"Sections      : {len(result['sections'])}")

    doc_scope = result.get("document_scope")
    if doc_scope:
        print(f"\nDocument scope:")
        print(f"  Domains       : {doc_scope.domains}")
        print(f"  Doc type      : {doc_scope.doc_type} (conf {doc_scope.doc_type_confidence:.2f})")
        print(f"  Clause families: {doc_scope.clause_families}")
        print(f"  Specific clauses: {doc_scope.specific_clauses}")
        print(f"  Confidence    : {doc_scope.confidence:.3f}")

    section_retrievals = result.get("section_retrievals") or []
    if section_retrievals:
        total = sum(len(r["chunks"]) for r in section_retrievals)
        print(f"\nRetrieved chunks : {total} across {len(section_retrievals)} sections")
        for r in section_retrievals:
            chunks = r["chunks"]
            print(f"\n  [{r['section_id']}] {r['section_title'][:60]}  ({len(chunks)} chunks)")
            for i, c in enumerate(chunks, 1):
                preview = c.text[:120].replace("\n", " ")
                print(f"    {i:2}. {c.norm_id} {c.clause_number:<10} score={c.rerank_score:.3f}"
                      f"  [{c.content_type}]")
                print(f"        {preview}{'…' if len(c.text) > 120 else ''}")

    if print_json:
        retrievals_json = [
            {
                "section_id": r["section_id"],
                "section_title": r["section_title"],
                "chunks": [
                    {
                        "chunk_id": c.chunk_id,
                        "norm_id": c.norm_id,
                        "clause_number": c.clause_number,
                        "clause_title": c.clause_title,
                        "content_type": c.content_type,
                        "rerank_score": c.rerank_score,
                        "rrf_score": c.rrf_score,
                        "text": c.text,
                        "keywords": c.keywords,
                    }
                    for c in r["chunks"]
                ],
            }
            for r in section_retrievals
        ]
        print(json.dumps(retrievals_json, ensure_ascii=False, indent=2))
        print(json.dumps([s.to_dict() for s in result["sections"]], ensure_ascii=False, indent=2))
    else:
        for s in result["sections"]:
            scope = s.scope
            clause_hint = f" → {scope.specific_clauses}" if scope and scope.specific_clauses else ""
            print(f"  [{s.section_type.value:16s}] {s.title}  (p{s.page_range[0]}-{s.page_range[1]}){clause_hint}")


if __name__ == "__main__":
    raise SystemExit(main())