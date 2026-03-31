"""Tests for extractors/docx.py — M2-DOCX extractor."""

from document_parser.extractors.docx import extract_docx


def test_returns_single_result(docx_path):
    results = extract_docx(docx_path)
    assert len(results) == 1


def test_page_number_is_one(docx_path):
    results = extract_docx(docx_path)
    assert results[0].page_number == 1


def test_extraction_method_and_confidence(docx_path):
    results = extract_docx(docx_path)
    assert results[0].extraction_method == "docx"
    assert results[0].confidence == 1.0


def test_h1_prefix_in_text(docx_path):
    """Heading 1 paragraphs must be prefixed ##H1## for the M4 segmenter."""
    results = extract_docx(docx_path)
    assert "##H1## Objet" in results[0].text


def test_h2_prefix_in_text(docx_path):
    """Heading 2 paragraphs must be prefixed ##H2##."""
    results = extract_docx(docx_path)
    assert "##H2## Domaine d'application" in results[0].text


def test_table_cells_in_text(docx_path):
    """Table cell content must appear in the flat text dump."""
    results = extract_docx(docx_path)
    assert "Colonne A" in results[0].text
    assert "Valeur 1" in results[0].text


def test_tables_field_structure(docx_path):
    """tables field must hold the structured 2×2 table."""
    results = extract_docx(docx_path)
    tables = results[0].tables
    assert isinstance(tables, list)
    assert len(tables) == 1       # one table in fixture
    assert len(tables[0]) == 2    # 2 rows
    assert len(tables[0][0]) == 2 # 2 cols
