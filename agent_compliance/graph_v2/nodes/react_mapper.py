from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent_compliance.graph_v2.llm import get_llm
from agent_compliance.graph_v2.models import (
    MappingOutput,
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


def _is_mappable(section) -> bool:
    title = (section.title or "").lower()
    if any(pattern in title for pattern in _NON_MAPPABLE_TITLE_PATTERNS):
        return False
    if len((section.raw_text or "").strip()) < _SHORT_TEXT_THRESHOLD:
        return False
    return True


def _render_clause_menu(menu: dict[str, list[tuple[str, str]]]) -> str:
    lines: list[str] = []
    for norm_id, clauses in menu.items():
        lines.append(norm_id + ":")
        for number, title in clauses:
            lines.append(f"  {number}  {title}")
    return "\n".join(lines)


def _mapping_prompt(section, menu_text: str, doc_type: str | None, doc_level: int | None) -> list:
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
                f"Document type: {doc_type or 'unknown'}  Level: {doc_level if doc_level is not None else 'unknown'}\n"
                f"Section type: {section.section_type.value} (hint — do not restrict to this type only)\n"
                f"Section title: {section.title}\n"
                f"Section text:\n{section.raw_text}\n\n"
                f"ISO clause menu:\n{menu_text}"
            )
        ),
    ]


def _assessment_prompt(section, clauses: list[ClauseRecord]) -> list:
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
        section_type=section.section_type.value,
        title=section.title,
        matched_clauses=[],
        status="MISSING",
        gaps=[gap],
        confidence=0.0,
        has_commitments=False,
    )


def react_mapper_node(state: ComplianceState, db_path: str) -> dict:
    section_matches: list[SectionMatch] = []
    llm = None

    for section in state["sections"]:
        if not _is_mappable(section):
            section_matches.append(
                SectionMatch(
                    section_id=section.id,
                    section_type=section.section_type.value,
                    title=section.title,
                    matched_clauses=[],
                    status="NOT_APPLICABLE",
                    gaps=[],
                    confidence=1.0,
                    has_commitments=False,
                )
            )
            continue

        try:
            if llm is None:
                llm = get_llm()

            menu_text = _render_clause_menu(state["clause_menu"])
            mapping: MappingOutput = llm.with_structured_output(MappingOutput).invoke(
                _mapping_prompt(
                    section,
                    menu_text,
                    state.get("doc_type"),
                    state.get("doc_level"),
                )
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
            output: SectionMatchOutput = llm.with_structured_output(SectionMatchOutput).invoke(
                _assessment_prompt(section, fetched_for_assessment)
            )

            terms = MODAL_TERMS_FR if state["language"].upper() == "FR" else MODAL_TERMS_EN
            raw_text_lower = section.raw_text.lower()
            has_commitments = any(term in raw_text_lower for term in terms)

            section_matches.append(
                to_section_match(output, fetched_for_assessment, section, has_commitments)
            )
        except Exception:
            logger.exception("Parse/LLM error on section %s", section.id)
            section_matches.append(_missing_match(section, gap="llm_parse_error"))

    return {"section_matches": section_matches}
