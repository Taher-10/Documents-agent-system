"""Two-level QHSE map: clause families (4–10) + high-value specific clauses."""

from __future__ import annotations

import re
from typing import Any, Mapping

from agent_compliance.classification.models import Domain

# ---------------------------------------------------------------------------
# Level A — top-level HLS clause family keywords (4–10)
# ---------------------------------------------------------------------------

CLAUSE_FAMILY_KEYWORDS: dict[str, list[str]] = {
    "4": [
        "contexte", "context",
        "parties intéressées", "interested parties",
        "enjeux", "issues",
        "domaine d'application", "scope of the management system",
    ],
    "5": [
        "politique", "policy",
        "leadership", "engagement",
        "responsabilité", "authority",
        "direction", "top management",
        "rôles et responsabilités", "organizational roles",
    ],
    "6": [
        "risques", "risks",
        "opportunités", "opportunities",
        "planification", "planning",
        "aspects environnementaux", "environmental aspects",
        "dangers", "hazards",
        "identification des risques", "risk identification",
        "objectifs", "objectives",
    ],
    "7": [
        "compétence", "competence",
        "formation", "training",
        "sensibilisation", "awareness",
        "communication",
        "information documentée", "documented information",
        "ressources", "resources",
        "habilitation", "qualification",
    ],
    "8": [
        "opérationnel", "operational",
        "contrôle opérationnel", "operational control",
        "réalisation", "production",
        "prestataires", "suppliers",
        "urgence", "emergency",
        "préparation", "preparedness",
        "maîtrise", "control",
        "exigences", "requirements",
    ],
    "9": [
        "audit", "surveillance",
        "monitoring", "measurement",
        "mesure", "performance",
        "évaluation", "evaluation",
        "revue de direction", "management review",
        "indicateurs", "indicators",
        "conformité", "compliance evaluation",
    ],
    "10": [
        "non-conformité", "nonconformity",
        "action corrective", "corrective action",
        "amélioration", "improvement",
        "incident",
        "réclamation", "complaint",
        "traitement des NC",
    ],
}

# ---------------------------------------------------------------------------
# Level B — high-value discriminative specific clauses
# ---------------------------------------------------------------------------

SPECIFIC_CLAUSE_KEYWORDS: dict[str, list[str]] = {
    "4.1": [
        "contexte de l'organisation", "context of the organization",
        "enjeux internes", "internal issues",
        "enjeux externes", "external issues",
    ],
    "4.2": [
        "parties intéressées", "interested parties",
        "exigences des parties", "needs and expectations",
    ],
    "5.2": [
        "politique qualité", "quality policy",
        "politique environnementale", "environmental policy",
        "politique sst", "occupational health and safety policy",
        "politique de management",
    ],
    "6.1": [
        "risques et opportunités", "risks and opportunities",
        "aspects environnementaux", "environmental aspects",
        "identification des dangers", "hazard identification",
        "évaluation des risques", "risk assessment",
        # ISO 45001 — hierarchy of controls
        "hiérarchie des mesures de prévention", "hierarchy of controls",
        "élimination", "substitution",
        # ISO 14001 — life-cycle + compliance obligations
        "perspective du cycle de vie", "life-cycle perspective",
        "obligations de conformité", "compliance obligations",
        "aspects significatifs", "significant environmental aspects",
    ],
    "6.2": [
        "objectifs qualité", "quality objectives",
        "objectifs environnementaux", "environmental objectives",
        "objectifs sst", "OH&S objectives",
        "cibles", "targets",
        "planification pour atteindre les objectifs", "planning to achieve objectives",
    ],
    "7.2": [
        "compétence", "competence",
        "habilitation", "qualification",
        "formation requise", "required training",
    ],
    "7.5": [
        "information documentée", "documented information",
        "maîtrise des documents", "control of documented information",
        "tenir à jour", "retain documented",
    ],
    "8.1": [
        "planification opérationnelle", "operational planning",
        "contrôle opérationnel", "operational control",
        "maîtrise opérationnelle",
        # ISO 45001 — management of change + contractors
        "pilotage du changement", "management of change",
        "intervenants extérieurs", "contractors",
        "équipement de protection individuelle", "EPI",
        # ISO 14001 — mitigation of environmental impacts
        "atténuation des impacts", "mitigation of impacts",
    ],
    "8.4": [
        "prestataires externes", "externally provided processes",
        "sous-traitance", "outsourced processes",
        "approvisionnement", "procurement",
        "fournisseurs", "suppliers",
        "sélection des prestataires", "selection of external providers",
    ],
    "8.2": [
        "préparation aux situations d'urgence", "emergency preparedness",
        "plan d'urgence", "emergency plan",
        "réponse aux urgences", "emergency response",
    ],
    "9.1": [
        "surveillance et mesure", "monitoring and measurement",
        "étalonnage", "calibration",
        "équipement de mesure vérifié", "calibrated equipment",
        # ISO 9001 — customer satisfaction
        "satisfaction du client", "customer satisfaction",
        "enquête de satisfaction", "customer survey",
        # ISO 14001 / 45001 — compliance evaluation
        "évaluation de la conformité", "evaluation of compliance",
        "obligations légales", "legal compliance",
    ],
    "9.2": [
        "audit interne", "internal audit",
        "programme d'audit", "audit programme",
        "auditeur", "auditor",
    ],
    "9.3": [
        "revue de direction", "management review",
        "compte rendu de revue", "review output",
    ],
    "10.2": [
        "non-conformité", "nonconformity",
        "action corrective", "corrective action",
        "traitement des NC", "nc",
        "correction",
        # ISO 45001 — root cause analysis
        "analyse des causes racines", "root cause analysis",
        "causes premières", "root causes",
        # ISO 45001 — incident investigation
        "enquête sur incident", "incident investigation",
    ],
}

# ---------------------------------------------------------------------------
# Pre-compiled regex patterns (lazy-init caches)
# ---------------------------------------------------------------------------

_FAMILY_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] | None = None
_SPECIFIC_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] | None = None

_TITLE_WEIGHT = 3
_EXTRACTION_CONFIDENCE_THRESHOLD = 0.70


def _kw_pattern(kw: str) -> re.Pattern[str]:
    """Compile a word-boundary pattern that tolerates French/English plural suffixes."""
    return re.compile(r"\b" + re.escape(kw) + r"[es]?\b", re.IGNORECASE)


def _get_family_patterns() -> dict[str, list[tuple[str, re.Pattern[str]]]]:
    global _FAMILY_PATTERNS
    if _FAMILY_PATTERNS is None:
        _FAMILY_PATTERNS = {
            family: [(kw, _kw_pattern(kw)) for kw in keywords]
            for family, keywords in CLAUSE_FAMILY_KEYWORDS.items()
        }
    return _FAMILY_PATTERNS


def _get_specific_patterns() -> dict[str, list[tuple[str, re.Pattern[str]]]]:
    global _SPECIFIC_PATTERNS
    if _SPECIFIC_PATTERNS is None:
        _SPECIFIC_PATTERNS = {
            clause: [(kw, _kw_pattern(kw)) for kw in keywords]
            for clause, keywords in SPECIFIC_CLAUSE_KEYWORDS.items()
        }
    return _SPECIFIC_PATTERNS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def map_section_to_clauses(
    section_title: str,
    section_text: str,
    domains: list[Domain],
    languages: list[str],
    extraction_confidence: float,
) -> tuple[list[str], list[str], list[str], float]:
    """Map section content to HLS clause families and specific clauses.

    Args:
        section_title: Section heading text.
        section_text: Section body (raw text).
        domains: Applicable standards (used for vocab scanning).
        languages: Languages to scan (``["EN"]``, ``["FR"]``, or both).
        extraction_confidence: PDF extraction quality (0.0–1.0).

    Returns:
        ``(clause_families, specific_clauses, evidence_terms, confidence)``

        - ``clause_families``: sorted list of matching HLS buckets (e.g. ``["7", "9"]``)
        - ``specific_clauses``: sorted list of discriminative clause IDs (e.g. ``["9.2"]``)
        - ``evidence_terms``: all keyword/vocab hits that contributed
        - ``confidence``: 0.0–1.0 based on hit count + extraction quality
    """
    title = (section_title or "").strip()
    body = (section_text or "").strip()

    if not title and not body:
        return [], [], [], 0.0

    body_window = body[:600]

    family_patterns = _get_family_patterns()
    specific_patterns = _get_specific_patterns()

    # --- Base family scores (CLAUSE_FAMILY_KEYWORDS) -------------------------
    base_family_scores: dict[str, float] = {}
    family_hits: dict[str, set[str]] = {}
    for family, pattern_list in family_patterns.items():
        title_hits = {kw for kw, pat in pattern_list if pat.search(title)}
        body_hits = {kw for kw, pat in pattern_list if pat.search(body_window)}
        score = len(title_hits) * _TITLE_WEIGHT + len(body_hits)
        if score > 0:
            base_family_scores[family] = score
            family_hits[family] = title_hits | body_hits

    # --- Specific clause scores (SPECIFIC_CLAUSE_KEYWORDS) ------------------
    specific_scores: dict[str, float] = {}
    specific_hits: dict[str, set[str]] = {}
    for clause, pattern_list in specific_patterns.items():
        title_hits = {kw for kw, pat in pattern_list if pat.search(title)}
        body_hits = {kw for kw, pat in pattern_list if pat.search(body_window)}
        score = len(title_hits) * _TITLE_WEIGHT + len(body_hits)
        if score > 0:
            specific_scores[clause] = score
            specific_hits[clause] = title_hits | body_hits

    # --- Concentration heuristic ---------------------------------------------
    # For each HLS family the single highest-scoring specific clause drives a
    # bonus.  Using max (not sum) means concentrated evidence — many keyword
    # hits from one sub-clause such as 9.2 — beats scattered evidence (one hit
    # each across 9.1, 9.2, 9.3).  A family that has no direct family-keyword
    # match but whose specific clause fires still appears in the output.
    specific_bonus: dict[str, float] = {}
    for clause, score in specific_scores.items():
        family = clause.split(".")[0]
        specific_bonus[family] = max(specific_bonus.get(family, 0.0), score)
        if family not in family_hits:
            family_hits[family] = set()
        family_hits[family] |= specific_hits[clause]

    family_scores: dict[str, float] = {
        f: base_family_scores.get(f, 0.0) + specific_bonus.get(f, 0.0)
        for f in set(base_family_scores) | set(specific_bonus)
    }

    # Collect all matched terms for evidence
    evidence: set[str] = set()
    for hits in family_hits.values():
        evidence.update(hits)
    for hits in specific_hits.values():
        evidence.update(hits)

    # ISO vocabulary scan for additional evidence terms
    try:
        from rag.shared.vocabulary.scanner import scan_iso_vocabulary  # type: ignore[import]

        for language in languages:
            full_text = f"{title}\n{body_window}"
            vocab_hits = scan_iso_vocabulary(
                text=full_text,
                language=language,
                norm_filter=list(domains),
            )
            evidence.update(vocab_hits)
    except Exception:
        pass  # vocab scan is best-effort; do not break classification

    # Sort outputs by clause id
    clause_families = sorted(family_scores.keys(), key=lambda x: int(x))
    specific_clauses = sorted(
        specific_scores.keys(),
        key=lambda x: (int(x.split(".")[0]), int(x.split(".")[1]) if "." in x else 0),
    )
    evidence_list = sorted(evidence)

    confidence = _compute_confidence(evidence_list, extraction_confidence)
    return clause_families, specific_clauses, evidence_list, confidence


def _compute_confidence(evidence: list[str], extraction_confidence: float) -> float:
    """Map evidence count + extraction quality to a 0–1 confidence score."""
    hit_count = len(evidence)
    if hit_count >= 3:
        base = 0.8
    elif hit_count >= 1:
        base = 0.6
    else:
        base = 0.3

    dampening = _extraction_dampening(extraction_confidence)
    return round(base * dampening, 3)


def _extraction_dampening(extraction_confidence: float) -> float:
    if extraction_confidence >= _EXTRACTION_CONFIDENCE_THRESHOLD:
        return 1.0
    return 0.5 + 0.5 * (extraction_confidence / _EXTRACTION_CONFIDENCE_THRESHOLD)
