from __future__ import annotations

from dataclasses import dataclass

from .type_mappings import TYPE_LEVEL_MAP, derive_norms


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

