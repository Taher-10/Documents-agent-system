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

_AUDITOR_PROMPT = """\
You are a strict ISO 9001:2015 / ISO 14001:2015 lead auditor reviewing sections \
of a quality or environmental management system document. Your task is to decide \
whether each section contains compliance-checkable content — meaning content that \
can be verified against a specific ISO clause requirement.

VALID sections (set valid=true) contain ANY of the following:
- Operational controls, process descriptions, step-by-step procedures
- Risk identification, risk assessment, or risk treatment activities
- Competence criteria, training requirements, or qualification records
- Roles, responsibilities, and authorities (organigrams are borderline — mark valid)
- Environmental aspects, significant impacts, or legal compliance obligations
- Objectives, targets, KPIs, or performance indicators
- Documented information control, retention rules, or record-keeping requirements
- Internal audit plans, programs, or audit reports
- Management review agendas, inputs, or outputs
- Corrective action, nonconformity, or continual improvement processes
- Emergency preparedness and response procedures
- Supplier/contractor control and procurement requirements

INVALID sections (set valid=false) are sections that contain ONLY:
- Document cover page, title, revision history, approval signatures, distribution list
- Pure table-of-contents with no procedural content
- Standalone glossary or definitions list with no process context
- Normative references list (list of other standards / documents)
- Generic scope statement that only names departments or sites without any procedure
- Blank pages, page separators, or image-only flowchart pages with no accompanying text
- Page with no clear content

When uncertain, set valid=true (prefer inclusion over exclusion).

You will receive a JSON array of sections. For each section output a JSON array \
(one object per section) with exactly these fields:
  "id"     : the section id (copy verbatim from input)
  "valid"  : true or false
  "reason" : one short sentence explaining your decision (max 20 words)

Output ONLY the JSON array — no preamble, no explanation, no markdown fences. \
The entire output must be on a single line with no newlines between array elements.

Example output:
[{"id":"section_6_1","valid":true,"reason":"Contains risk assessment steps mapped to ISO 6.1."},{"id":"section_1","valid":false,"reason":"Cover page with only document metadata and signatures."}]

SECTIONS TO EVALUATE:
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_sections_payload(sections: list[Any]) -> list[dict]:
    """Build a compact summary list for the LLM prompt.

    Only includes classified sections (scope is not None and has at least one domain).
    Unclassified sections are skipped — they are already omitted by retrieve_node.
    """
    payload = []
    for s in sections:
        scope = s.scope
        if scope is None or not scope.domains:
            continue
        payload.append({
            "id": s.id,
            "title": s.title,
            "section_type": (
                s.section_type.value
                if hasattr(s.section_type, "value")
                else str(s.section_type)
            ),
            "clause_families": scope.clause_families,
            "text_preview": (s.raw_text or "")[:_TEXT_PREVIEW_CHARS].strip(),
        })
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

    classified = [s for s in sections if s.scope is not None and s.scope.domains]

    if not classified:
        _emit(_NODE, "skip", "No classified sections to filter — passing through")
        return {"sections": sections, "status": "sections_filtered"}

    _emit(
        _NODE,
        "start",
        f"ISO auditor LLM evaluating {len(classified)} classified sections "
        f"({len(sections) - len(classified)} unclassified pass-through)...",
    )

    payload = _build_sections_payload(sections)
    prompt = _build_prompt(payload)

    # --- LLM call -----------------------------------------------------------
    try:
        raw_response = await chat_complete(prompt, max_tokens=_MAX_TOKENS, timeout=_LLM_TIMEOUT)
    except Exception as exc:
        _emit(
            _NODE,
            "error",
            f"LLM call failed ({type(exc).__name__}: {exc}) — keeping all {len(classified)} sections",
        )
        return {"sections": sections, "status": "sections_filtered"}

    # --- Parse response -----------------------------------------------------
    try:
        parsed = _parse_llm_response(raw_response)
    except ValueError as exc:
        _emit(
            _NODE,
            "error",
            f"JSON parse failed ({exc}) — keeping all {len(classified)} sections",
        )
        return {"sections": sections, "status": "sections_filtered"}

    # --- Determine invalid set ----------------------------------------------
    invalid_ids = _build_invalid_id_set(parsed)

    # Safety: if ALL classified sections would be nulled, fall back
    classified_ids = {s.id for s in classified}
    if not (classified_ids - invalid_ids):
        _emit(
            _NODE,
            "error",
            f"LLM would filter ALL {len(classified)} classified sections — ignoring result (fallback)",
        )
        return {"sections": sections, "status": "sections_filtered"}

    # --- Apply filter (null out scopes of invalid sections) -----------------
    nulled = 0
    for section in sections:
        if section.id in invalid_ids:
            section.scope = None
            nulled += 1

    kept = len(classified) - nulled
    _emit(
        _NODE,
        "done",
        f"Filtered {nulled} non-compliant sections, {kept} sections proceed to retrieval",
    )
    return {"sections": sections, "status": "sections_filtered"}
