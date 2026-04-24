from __future__ import annotations

import pytest

from agent_compliance.ingestion.document_meta import DocumentMeta
from agent_compliance.ingestion.type_mappings import TYPE_LEVEL_MAP, derive_norms


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("Q", "ISO 9001"),
        ("E", "ISO 14001"),
        ("S", "ISO 45001"),
        ("H", "ISO 45001"),
    ],
)
def test_derive_norms_single_flag(flag: str, expected: str) -> None:
    flags = {"Q": False, "E": False, "S": False, "H": False, flag: True}
    assert derive_norms(flags) == [expected]


def test_derive_norms_empty_when_all_flags_false() -> None:
    assert derive_norms({"Q": False, "E": False, "S": False, "H": False}) == []


def test_derive_norms_deduplicates_s_and_h() -> None:
    assert derive_norms({"Q": False, "E": False, "S": True, "H": True}) == ["ISO 45001"]


def test_derive_norms_returns_deterministic_order() -> None:
    assert derive_norms({"Q": True, "E": True, "S": False, "H": True}) == [
        "ISO 14001",
        "ISO 45001",
        "ISO 9001",
    ]


def test_type_level_map_has_expected_size() -> None:
    assert len(TYPE_LEVEL_MAP) == 26


@pytest.mark.parametrize(
    ("type_designation", "expected"),
    [
        ("Politique qualité", ("policy", 1)),
        ("Plan Qualité", ("manual", 2)),
        ("Procédure", ("procedure", 3)),
        ("Mode opératoire", ("work_instruction", 4)),
        ("Formulaire", ("form", 5)),
        ("AUCUN", ("unknown", 0)),
    ],
)
def test_type_level_map_samples(type_designation: str, expected: tuple[str, int]) -> None:
    assert TYPE_LEVEL_MAP[type_designation] == expected


def test_document_meta_from_request_derives_fields() -> None:
    doc = {
        "id": "doc-1",
        "code": "PRO-QHSE-001",
        "designation": "Procédure QHSE",
        "version": "02",
        "type_designation": "Procédure",
        "Q": True,
        "E": False,
        "S": True,
        "H": True,
        "file_path": "test/PRO-QHSE-001.pdf",
    }
    session = {
        "company_id": "company-1",
        "site_id": "site-1",
    }

    meta = DocumentMeta.from_request(doc=doc, session=session)

    assert meta.doc_id == "doc-1"
    assert meta.doc_code == "PRO-QHSE-001"
    assert meta.designation == "Procédure QHSE"
    assert meta.version == "02"
    assert meta.file_path == "test/PRO-QHSE-001.pdf"
    assert meta.doc_type == "procedure"
    assert meta.doc_level == 3
    assert meta.applicable_norms == ["ISO 45001", "ISO 9001"]
    assert meta.company_id == "company-1"
    assert meta.site_id == "site-1"


def test_document_meta_from_request_unknown_type_fallback() -> None:
    doc = {
        "id": "doc-2",
        "code": "DOC-UNK-001",
        "designation": "Unknown Type",
        "version": "01",
        "type_designation": "Type introuvable",
        "Q": False,
        "E": True,
        "S": False,
        "H": False,
        "file_path": "test/DOC-UNK-001.pdf",
    }
    session = {
        "company_id": "company-2",
        "site_id": "site-2",
    }

    meta = DocumentMeta.from_request(doc=doc, session=session)

    assert meta.doc_type == "unknown"
    assert meta.doc_level == 0
    assert meta.applicable_norms == ["ISO 14001"]

