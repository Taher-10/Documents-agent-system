from __future__ import annotations

from dataclasses import dataclass


TYPE_LEVEL_MAP: dict[str, tuple[str, int]] = {
    "Procédure": ("procedure", 2),
    "Processus": ("process", 1),
    "Instruction": ("instruction", 3),
    "Mode opératoire": ("work_instruction", 3),
    "Enregistrement": ("record", 4),
    "Politique": ("policy", 1),
    "Manuel": ("manual", 1),
}


def derive_norms(flags: dict[str, bool]) -> list[str]:
    """Derive applicable ISO norms from Q/E/S/H boolean flags."""
    norms: list[str] = []
    if flags.get("Q", False):
        norms.append("ISO 9001")
    if flags.get("E", False):
        norms.append("ISO 14001")
    if flags.get("S", False):
        norms.append("ISO 22000")
    if flags.get("H", False):
        norms.append("ISO 45001")
    return norms


@dataclass(slots=True)
class DocumentMeta:
    doc_id: str
    doc_code: str
    designation: str
    version: str
    file_path: str
    doc_type: str
    doc_level: int
    applicable_norms: list[str]
    company_id: str
    site_id: str

    @classmethod
    def from_request(cls, doc: dict, session: dict) -> "DocumentMeta":
        type_label = doc["type_designation"]
        doc_type, doc_level = TYPE_LEVEL_MAP.get(type_label, ("unknown", 0))

        return cls(
            doc_id=doc["id"],
            doc_code=doc["code"],
            designation=doc["designation"],
            version=doc["version"],
            file_path=doc["file_path"],
            doc_type=doc_type,
            doc_level=doc_level,
            applicable_norms=derive_norms(doc),
            company_id=session["company_id"],
            site_id=session["site_id"],
        )
