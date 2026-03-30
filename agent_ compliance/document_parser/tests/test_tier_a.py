"""Tests for extractors/tier_a.py — Tier A (clean PDF) extractor."""

import pytest

from document_parser.document_diagnostician import PageInfo, PageMap
from document_parser.extractors.tier_a import extract_tier_a


def _make_page_map(n_pages: int) -> PageMap:
    return PageMap(
        total_pages=n_pages,
        file_format="pdf",
        quality_tier="A",
        pages=[
            PageInfo(
                page_number=i,
                page_type="text",
                has_selectable_text=True,
                image_count=0,
                font_issue=False,
                text_sample="",
            )
            for i in range(1, n_pages + 1)
        ],
        producer="test",
    )


def test_returns_one_result_per_page(pdf_path):
    results = extract_tier_a(pdf_path, _make_page_map(2))
    assert len(results) == 2


def test_page_numbers_are_correct(pdf_path):
    results = extract_tier_a(pdf_path, _make_page_map(2))
    assert results[0].page_number == 1
    assert results[1].page_number == 2


def test_page1_uses_pdfplumber(pdf_path):
    """Page 1 has >50 chars → pdfplumber path, confidence=1.0."""
    results = extract_tier_a(pdf_path, _make_page_map(2))
    assert results[0].extraction_method == "pdfplumber"
    assert results[0].confidence == 1.0
    assert len(results[0].text.strip()) > 50


def test_page2_falls_back_to_fitz(pdf_path):
    """Page 2 has only 2 chars of text → fitz fallback fires and UserWarning is emitted."""
    with pytest.warns(UserWarning, match="falling back to fitz"):
        results = extract_tier_a(pdf_path, _make_page_map(2))
    assert results[1].extraction_method == "fitz"
    assert results[1].confidence == 1.0


def test_tables_field_is_list(pdf_path):
    results = extract_tier_a(pdf_path, _make_page_map(1))
    assert isinstance(results[0].tables, list)
