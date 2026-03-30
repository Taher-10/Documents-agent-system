"""conftest.py — add src/ to sys.path so tests import document_parser directly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import fitz
import pytest


@pytest.fixture()
def pdf_path(tmp_path: Path) -> Path:
    """Two-page PDF: page 1 is text-rich (>50 chars), page 2 is near-empty."""
    doc = fitz.open()

    p1 = doc.new_page()
    p1.insert_text(
        (72, 72),
        "Objet\nCe document décrit la procédure de gestion des gabarits.\n" * 4,
    )

    p2 = doc.new_page()
    p2.insert_text((72, 72), "ok")  # <50 chars → triggers fitz fallback

    out = tmp_path / "test.pdf"
    out.write_bytes(doc.tobytes())
    doc.close()
    return out