from __future__ import annotations

import logging
import re
import time

import groq
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

from agent_compliance.graph_v2.llm import get_llm
from agent_compliance.graph_v2.models import (
    MappingOutput,
    MatchedClause,
    SectionMatch,
    SectionMatchOutput,
    to_section_match,
)
from agent_compliance.graph_v2.state import ComplianceState
from agent_compliance.retrieval.clause_store import (
    ClauseRecord,
    fetch_clauses_by_ids,
    fetch_clauses_by_section_type,
)
from rag.shared.vocabulary.scanner import MODAL_TERMS_EN, MODAL_TERMS_FR

logger = logging.getLogger(__name__)

_NON_MAPPABLE_TITLE_PATTERNS = [
    "historique",
    "révisions",
    "modifications",
    "table des matières",
    "sommaire",
    "objet du document",
    "page de garde",
    "liste de diffusion",
    "approbation",
    "signatures",
    "amendment",
    "change history",
    "table of contents",
]
_SHORT_TEXT_THRESHOLD = 120
_ASSESSMENT_CLAUSE_CAP = 8
_ALWAYS_NON_MAPPABLE_TYPES = {"METADATA", "REFERENCES"}
_DEFINITIONS_CLAUSES = ["3"]
_INVALID_EVIDENCE_GAP = "invalid_evidence"
_SECTION_PACING_SECONDS = 0.5
_EVIDENCE_TOKEN_OVERLAP_THRESHOLD = 0.70


def _normalize_text(text: str | None) -> str:
    return " ".join((text or "").split())


def _tokenize_words(text: str | None) -> list[str]:
    return re.findall(r"\w+", (text or "").lower(), flags=re.UNICODE)


def _retry_after_seconds(exc: BaseException) -> float | None:
    if not isinstance(exc, groq.RateLimitError):
        return None
    response = getattr(exc, "response", None)
    if response is None:
        return None
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        seconds = float(raw.strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


class _wait_exponential_with_retry_after(wait_base):
    def __init__(self, *, multiplier: float, min_wait: float, max_wait: float) -> None:
        self._exponential = wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait)

    def __call__(self, retry_state) -> float:
        base_wait = self._exponential(retry_state)
        outcome = getattr(retry_state, "outcome", None)
        exc = outcome.exception() if outcome is not None and outcome.failed else None
        retry_after = _retry_after_seconds(exc) if exc is not None else None
        if retry_after is None:
            return base_wait
        return max(base_wait, retry_after)


def _is_retryable_llm_error(exc: BaseException) -> bool:
    if isinstance(exc, (OutputParserException, ValidationError)):
        return False

    if isinstance(
        exc,
        (
            groq.RateLimitError,
            groq.APITimeoutError,
            groq.APIConnectionError,
            groq.InternalServerError,
        ),
    ):
        return True

    return isinstance(exc, groq.APIStatusError) and exc.status_code >= 500


@retry(
    stop=stop_after_attempt(3),
    wait=_wait_exponential_with_retry_after(multiplier=1, min_wait=2, max_wait=8),
    retry=retry_if_exception(_is_retryable_llm_error),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _invoke_structured(llm, prompt: list, schema):
    return llm.with_structured_output(schema).invoke(prompt)


def _normalized_section_type(section) -> str:
    section_type = getattr(section, "section_type", "")
    if hasattr(section_type, "name"):
        return str(section_type.name).upper()
    normalized = str(section_type).strip().upper().replace("-", "_").replace(" ", "_")
    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[-1]
    return normalized


def _section_type_value(section) -> str:
    section_type = getattr(section, "section_type", "")
    return section_type.value if hasattr(section_type, "value") else str(section_type)


def _is_mappable(section) -> tuple[bool, str | None]:
    section_type = _normalized_section_type(section)
    if section_type in _ALWAYS_NON_MAPPABLE_TYPES:
        return False, "non_mappable_type"
    if section_type == "DEFINITIONS":
        return False, "non_mappable_definitions"

    title = (section.title or "").lower()
    if any(pattern in title for pattern in _NON_MAPPABLE_TITLE_PATTERNS):
        return False, "non_mappable_title"
    if len((section.raw_text or "").strip()) < _SHORT_TEXT_THRESHOLD:
        return False, "non_mappable_short"
    return True, None


def _render_clause_menu(menu: dict[str, list[tuple[str, str]]]) -> str:
    lines: list[str] = []
    for norm_id, clauses in menu.items():
        lines.append(norm_id + ":")
        for number, title in clauses:
            lines.append(f"  {number}  {title}")
    return "\n".join(lines)


def _document_metadata_line(
    doc_code: str | None,
    doc_type: str | None,
    doc_level: int | None,
) -> str:
    return (
        f"Document: {doc_code or 'unknown'} | "
        f"Type: {doc_type or 'unknown'} | "
        f"Level: {doc_level if doc_level is not None else 'unknown'}"
    )


def _mapping_prompt(
    section,
    menu_text: str,
    doc_code: str | None,
    doc_type: str | None,
    doc_level: int | None,
) -> list:
    return [
        SystemMessage(
            content=(
                "You are a QHSE compliance analyst. Given a document section and a list of "
                "ISO clause numbers with titles, identify which clauses this section addresses. "
                "Output only clause numbers that genuinely relate to the section content. "
                "Output 3 to 6 clause numbers maximum."
            )
        ),
        HumanMessage(
            content=(
                f"{_document_metadata_line(doc_code, doc_type, doc_level)}\n"
                f"Section type: {section.section_type.value} (hint — do not restrict to this type only)\n"
                f"Section title: {section.title}\n"
                f"Section text:\n{section.raw_text}\n\n"
                f"ISO clause menu:\n{menu_text}"
            )
        ),
    ]


def _assessment_prompt(
    section,
    clauses: list[ClauseRecord],
    doc_code: str | None,
    doc_type: str | None,
    doc_level: int | None,
) -> list:
    clause_block = "\n---\n".join(
        f"[{clause.norm_id}] {clause.clause_number} — {clause.clause_title}\n{clause.text}"
        for clause in clauses
    )
    return [
        SystemMessage(
            content=(
                "You are a QHSE compliance analyst. Assess whether the document section "
                "satisfies each ISO clause provided. For each clause:\n"
                "- Quote evidence directly from the section text (verbatim).\n"
                "- State specifically what is missing or non-conforming.\n"
                "- Give concrete advice: what must be added, clarified, or documented.\n\n"
                "Rules:\n"
                "- evidence_text must be a verbatim quote from the section text.\n"
                "- advice must be specific: not 'incomplete documentation' but "
                "  'Add documented criteria for re-evaluation of suppliers'.\n"
                "- Only reference the clause numbers provided to you."
            )
        ),
        HumanMessage(
            content=(
                f"{_document_metadata_line(doc_code, doc_type, doc_level)}\n"
                f"Section type: {section.section_type.value}\n"
                f"Section title: {section.title}\n"
                f"Section text:\n{section.raw_text}\n\n"
                f"ISO clauses to assess:\n{clause_block}"
            )
        ),
    ]


def _missing_match(section, *, gap: str) -> SectionMatch:
    return SectionMatch(
        section_id=section.id,
        section_type=_section_type_value(section),
        title=section.title,
        matched_clauses=[],
        status="MISSING",
        gaps=[gap],
        confidence=0.0,
        has_commitments=False,
    )


def _definitions_match(state: ComplianceState, section, db_path: str) -> SectionMatch:
    fetched = fetch_clauses_by_ids(
        _DEFINITIONS_CLAUSES,
        state["applicable_norms"],
        language=state["language"],
        db_path=db_path,
    )
    if not fetched:
        logger.warning("Clause 3 unavailable for DEFINITIONS section %s", section.id)
        return _missing_match(section, gap="definitions_clause_missing")

    clause = fetched[0]
    return SectionMatch(
        section_id=section.id,
        section_type=_section_type_value(section),
        title=section.title,
        matched_clauses=[
            MatchedClause(
                norm_id=clause.norm_id,
                clause_number=clause.clause_number,
                clause_title=clause.clause_title,
                evidence_text="Definitions section detected; terminology reference only.",
                status="PARTIAL",
                advice="Align terms with Clause 3 vocabulary and reference the controlled glossary where needed.",
            )
        ],
        status="PARTIAL",
        gaps=["non_mappable_definitions"],
        confidence=0.2,
        has_commitments=False,
    )


def _validate_evidence(output: SectionMatchOutput, raw_text: str) -> SectionMatchOutput:
    raw_tokens = set(_tokenize_words(raw_text))
    validated = []
    mutated = False

    for mc in output.matched_clauses:
        evidence_tokens = _tokenize_words(mc.evidence_text)
        if evidence_tokens:
            matched_tokens = sum(1 for token in evidence_tokens if token in raw_tokens)
            overlap_ratio = matched_tokens / len(evidence_tokens)
            if overlap_ratio < _EVIDENCE_TOKEN_OVERLAP_THRESHOLD:
                mutated = True
                continue
        elif mc.status in ("COVERED", "PARTIAL"):
            mc = mc.model_copy(update={"status": "NON_CONFORMING"})
            mutated = True
        validated.append(mc)

    status = output.status
    if status in ("COVERED", "PARTIAL") and not any(
        mc.status in ("COVERED", "PARTIAL") for mc in validated
    ):
        status = "NON_CONFORMING"
        mutated = True

    gaps = list(output.gaps)
    if mutated and _INVALID_EVIDENCE_GAP not in gaps:
        gaps.append(_INVALID_EVIDENCE_GAP)

    return output.model_copy(
        update={
            "matched_clauses": validated,
            "status": status,
            "gaps": gaps,
        }
    )


def react_mapper_node(state: ComplianceState, db_path: str) -> dict:
    section_matches: list[SectionMatch] = []
    llm = None

    for section in state["sections"]:
        is_mappable, reason = _is_mappable(section)
        if not is_mappable:
            if reason == "non_mappable_definitions":
                section_matches.append(_definitions_match(state, section, db_path))
                continue
            section_matches.append(
                SectionMatch(
                    section_id=section.id,
                    section_type=_section_type_value(section),
                    title=section.title,
                    matched_clauses=[],
                    status="NOT_APPLICABLE",
                    gaps=[reason] if reason else [],
                    confidence=1.0,
                    has_commitments=False,
                )
            )
            continue

        used_llm = False
        try:
            used_llm = True
            if llm is None:
                llm = get_llm()

            menu_text = _render_clause_menu(state["clause_menu"])
            mapping: MappingOutput = _invoke_structured(
                llm,
                _mapping_prompt(
                    section,
                    menu_text,
                    state.get("doc_code"),
                    state.get("doc_type"),
                    state.get("doc_level"),
                ),
                MappingOutput,
            )

            fetched = fetch_clauses_by_ids(
                mapping.clause_ids,
                state["applicable_norms"],
                language=state["language"],
                db_path=db_path,
            )

            if not fetched:
                logger.warning("0 valid mapped IDs for section %s — using fallback", section.id)
                fetched = fetch_clauses_by_section_type(
                    section.section_type.value,
                    state["applicable_norms"],
                    language=state["language"],
                    db_path=db_path,
                )

            if not fetched:
                logger.warning("Fallback returned 0 clauses for section %s", section.id)
                section_matches.append(_missing_match(section, gap="no_mapped_clauses"))
                continue

            fetched_for_assessment = fetched[:_ASSESSMENT_CLAUSE_CAP]
            output: SectionMatchOutput = _invoke_structured(
                llm,
                _assessment_prompt(
                    section,
                    fetched_for_assessment,
                    state.get("doc_code"),
                    state.get("doc_type"),
                    state.get("doc_level"),
                ),
                SectionMatchOutput,
            )
            output = _validate_evidence(output, section.raw_text)

            terms = MODAL_TERMS_FR if state["language"].upper() == "FR" else MODAL_TERMS_EN
            raw_text_lower = section.raw_text.lower()
            has_commitments = any(term in raw_text_lower for term in terms)

            section_matches.append(
                to_section_match(output, fetched_for_assessment, section, has_commitments)
            )
        except (OutputParserException, ValidationError):
            logger.exception("Structured output parse error on section %s", section.id)
            section_matches.append(_missing_match(section, gap="llm_parse_error"))
        except Exception:
            logger.exception("All retries exhausted for section %s", section.id)
            section_matches.append(_missing_match(section, gap="llm_exhausted"))
        finally:
            if used_llm:
                time.sleep(_SECTION_PACING_SECONDS)

    return {"section_matches": section_matches}
