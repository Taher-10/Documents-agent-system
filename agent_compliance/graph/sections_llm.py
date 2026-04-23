"""sections_llm.py — LLM-based ISO auditor filter for classified sections.

Inserted between classify_sections → retrieve in the compliance graph.

Role
----
Uses chat_complete() to call the LLM as an ISO 9001/14001 lead auditor and decide,
for each classified section, whether it contains compliance-checkable content worth
retrieving norm clauses for.  Invalid sections (pure admin, glossaries, cover pages,
etc.) have their scope set to None so retrieve_node naturally skips them — the full
sections list is otherwise preserved for debugging.

Fallback guarantee
------------------
Any failure (LLM error, JSON parse error, all-filtered result) is non-fatal:
the node logs the issue via _emit and returns all sections untouched.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any

from langgraph.config import get_stream_writer

from rag.retrival.clients.llm_client import chat_complete

from .state import AgentState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NODE = "sections_llm"
_MAX_TOKENS = 2000          # ~20 sections × ~80 tokens per JSON object + prompt overhead
_LLM_TIMEOUT = int(os.getenv("SECTIONS_LLM_TIMEOUT", "120"))  # seconds; increase for slow local models
_TEXT_PREVIEW_CHARS = 300   # chars of raw_text sent to the LLM per section

# ---------------------------------------------------------------------------
# Streaming helper (module-local — matches pattern in nodes.py / retrieve_node.py)
# ---------------------------------------------------------------------------


def _emit(node: str, event: str, msg: str) -> None:
    """Push a structured log event through the LangGraph stream writer."""
    get_stream_writer()({"node": node, "event": event, "msg": msg})


# ---------------------------------------------------------------------------
# ISO auditor prompt
# ---------------------------------------------------------------------------

_VALID_CLAUSE_FAMILIES = {"4", "5", "6", "7", "8", "9", "10"}

_AUDITOR_PROMPT = """\
You are an ISO 9001:2015 / ISO 14001:2015 auditor.

Task:
For each section, determine:
1) valid: does it contain compliance-checkable content?
2) clause_family: most likely ISO clause family (4-10) based on content

VALID (valid=true):
Sections describing processes, controls, responsibilities, risks, objectives, competence, audits, reviews, corrective actions, suppliers, or operational activities.

INVALID (valid=false):
Only metadata (cover, revision, signatures), table of contents, glossary, references, empty/blank pages, or scope with no actionable content.

If unsure -> valid=true.

Clause families:
4 Context | 5 Leadership | 6 Planning | 7 Support | 8 Operation | 9 Evaluation | 10 Improvement

Input: JSON array of sections

Output: JSON array with:
"id" : copy from input
"valid" : true/false
"clause_family" : one of ["4","5","6","7","8","9","10"] or null if invalid
"reason" : short (<=15 words)

Output rules:
- Single line JSON
- No explanations

Example:
[{"id":"s1","valid":true,"clause_family":"6","reason":"Risk assessment and planning activities."},{"id":"s2","valid":false,"clause_family":null,"reason":"Only revision history."}]

SECTIONS:
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_sections_payload(sections: list[Any]) -> list[dict]:
    """Build a compact summary list for the LLM prompt.

    Includes all sections that have at least a title or text preview.
    When a classify_sections node has run, classified sections also carry
    clause_families from their scope — otherwise that field is omitted.
    """
    payload = []
    for s in sections:
        scope = s.scope
        entry: dict = {
            "id": s.id,
            "title": s.title,
            "section_type": (
                s.section_type.value
                if hasattr(s.section_type, "value")
                else str(s.section_type)
            ),
            "text_preview": (s.raw_text or "")[:_TEXT_PREVIEW_CHARS].strip(),
        }
        if scope is not None and scope.domains:
            entry["clause_families"] = scope.clause_families
        payload.append(entry)
    return payload


def _build_prompt(payload: list[dict]) -> str:
    return _AUDITOR_PROMPT + json.dumps(payload, ensure_ascii=False)


def _parse_llm_response(raw: str) -> list[dict]:
    """Extract and validate the JSON array from the LLM response.

    Tries three strategies in order:
    1. Parse the raw string directly.
    2. Strip markdown fences (```json ... ```) then parse.
    3. Regex-extract the first [...] block then parse.

    Raises ValueError if none succeed or if the result is not a list.
    """
    text = raw.strip()

    strategies = [
        lambda t: t,
        lambda t: re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S),
        lambda t: _extract_json_array(t),
    ]

    for strategy in strategies:
        try:
            candidate = strategy(text)
            result = json.loads(candidate)
            if isinstance(result, list):
                return result
        except (ValueError, TypeError):
            continue

    raise ValueError(
        f"Could not parse a JSON array from LLM response: {text[:200]!r}"
    )


def _extract_json_array(text: str) -> str:
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        raise ValueError("No JSON array found in response")
    return match.group(0)


def _build_invalid_id_set(parsed: list[dict]) -> set[str]:
    """Return the set of section IDs that the LLM marked as invalid.

    Skips malformed objects (missing fields, wrong types).
    """
    invalid: set[str] = set()
    for item in parsed:
        if not isinstance(item, dict):
            continue
        sid = item.get("id")
        valid = item.get("valid")
        if not isinstance(sid, str) or not isinstance(valid, bool):
            continue
        if not valid:
            invalid.add(sid)
    return invalid


def _build_clause_family_predictions(parsed: list[dict]) -> dict[str, str | None]:
    """Return validated clause-family predictions keyed by section id."""
    predictions: dict[str, str | None] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue

        sid = item.get("id")
        valid = item.get("valid")
        clause_family = item.get("clause_family")

        if not isinstance(sid, str) or not isinstance(valid, bool):
            continue

        if not valid:
            predictions[sid] = None
            continue

        predictions[sid] = (
            clause_family
            if isinstance(clause_family, str) and clause_family in _VALID_CLAUSE_FAMILIES
            else None
        )
    return predictions


def _build_validity_predictions(parsed: list[dict]) -> dict[str, bool]:
    """Return valid/invalid predictions keyed by section id."""
    predictions: dict[str, bool] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        sid = item.get("id")
        valid = item.get("valid")
        if isinstance(sid, str) and isinstance(valid, bool):
            predictions[sid] = valid
    return predictions


async def filter_sections_with_llm(
    sections: list[Any],
    emit_fn: Callable[[str, str, str], None] | None = None,
) -> dict[str, Any]:
    """Apply the section auditor LLM and mutate sections with its predictions."""
    emitter = emit_fn or (lambda _node, _event, _msg: None)

    if not sections:
        emitter(_NODE, "skip", "No sections to filter — passing through")
        return {"sections": sections, "status": "sections_filtered"}

    classified = [s for s in sections if s.scope is not None and s.scope.domains]
    evaluated_count = len(classified) if classified else len(sections)

    emitter(
        _NODE,
        "start",
        f"ISO auditor LLM evaluating {evaluated_count} sections...",
    )

    payload = _build_sections_payload(sections)
    prompt = _build_prompt(payload)

    try:
        raw_response = await chat_complete(prompt, max_tokens=_MAX_TOKENS, timeout=_LLM_TIMEOUT)
    except Exception as exc:
        emitter(
            _NODE,
            "error",
            f"LLM call failed ({type(exc).__name__}: {exc}) — keeping all {len(classified)} sections",
        )
        return {"sections": sections, "status": "sections_filtered"}

    try:
        parsed = _parse_llm_response(raw_response)
    except ValueError as exc:
        emitter(
            _NODE,
            "error",
            f"JSON parse failed ({exc}) — keeping all {len(classified)} sections",
        )
        return {"sections": sections, "status": "sections_filtered"}

    invalid_ids = _build_invalid_id_set(parsed)
    validity_predictions = _build_validity_predictions(parsed)
    clause_family_predictions = _build_clause_family_predictions(parsed)

    all_ids = {s.id for s in sections}
    if all_ids and not (all_ids - invalid_ids):
        emitter(
            _NODE,
            "error",
            f"LLM would filter ALL {len(sections)} sections — ignoring result (fallback)",
        )
        return {"sections": sections, "status": "sections_filtered"}

    nulled = 0
    predicted = 0
    for section in sections:
        section.llm_valid = validity_predictions.get(section.id)
        section.predicted_clause_family = clause_family_predictions.get(section.id)
        if section.id in invalid_ids:
            section.scope = None
            nulled += 1
        if section.predicted_clause_family is not None:
            predicted += 1

    kept = len(sections) - nulled
    emitter(
        _NODE,
        "done",
        f"Filtered {nulled} sections, kept {kept}, predicted clause families for {predicted}",
    )
    return {"sections": sections, "status": "sections_filtered"}


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------


async def sections_llm_node(state: AgentState) -> dict:
    """LLM-based ISO auditor filter.

    Evaluates each classified section and sets scope=None on sections that
    the LLM determines do not contain compliance-checkable content.

    The full sections list is always returned (non-destructive shape).
    Only section.scope is mutated — retrieve_node already skips scope=None sections.

    Falls back to keeping all classified sections if:
      - LLM call raises any exception
      - LLM response cannot be parsed as a valid JSON array
      - Parsed result would filter out ALL currently-classified sections
    """
    sections: list[Any] = state.get("sections") or []
    return await filter_sections_with_llm(sections, emit_fn=_emit)
