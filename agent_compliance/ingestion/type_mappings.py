from __future__ import annotations


TYPE_LEVEL_MAP: dict[str, tuple[str, int]] = {
    # Level 1 — Strategic
    "Politique qualité": ("policy", 1),
    # Level 2 — System
    "Manuel Qualité": ("manual", 2),
    "Plan Qualité": ("manual", 2),
    "Fiche Descriptive d'un Processus": ("process_sheet", 2),
    # Level 3 — Operational
    "Procédure": ("procedure", 3),
    "Document": ("document", 3),
    "Document Production": ("document", 3),
    "Fiche Technique": ("technical_sheet", 3),
    "Liste": ("list", 3),
    "Norme": ("norm_ref", 3),
    "Loi": ("regulation", 3),
    "Gamme": ("routing", 3),
    "Gamme accessoires": ("routing", 3),
    "Gamme barre stabilisatrice": ("routing", 3),
    # Level 4 — Instructions
    "Instruction": ("work_instruction", 4),
    "Mode opératoire": ("work_instruction", 4),
    "Fiche Fonction": ("job_sheet", 4),
    "Plan accessoires": ("plan", 4),
    "Plan outillage": ("plan", 4),
    "Plan de définition accessoires": ("plan", 4),
    "Plan de définition outillage": ("plan", 4),
    "Projets": ("project", 4),
    # Level 5 — Records
    "Formulaire": ("form", 5),
    "Fiche": ("form", 5),
    "Document d'enregistrement": ("record", 5),
    # Unknown
    "AUCUN": ("unknown", 0),
}


NORM_FLAG_MAP: dict[str, str] = {
    "Q": "ISO 9001",
    "E": "ISO 14001",
    "S": "ISO 45001",
    "H": "ISO 45001",
}


def derive_norms(flags: dict[str, bool]) -> list[str]:
    """Derive applicable ISO norms from Q/E/S/H boolean flags."""
    norms = {
        NORM_FLAG_MAP[flag]
        for flag in ("Q", "E", "S", "H")
        if flags.get(flag) is True
    }
    return sorted(norms)

