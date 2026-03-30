"""test_diagnostician.py — M1 unit tests for document_diagnostician."""

import pytest
from document_parser.document_diagnostician import PageInfo, PageMap


# ---------------------------------------------------------------------------
# Task 1 — Dataclasses
# ---------------------------------------------------------------------------

def test_page_info_construction():
    info = PageInfo(
        page_number=1,
        page_type="text",
        has_selectable_text=True,
        image_count=0,
        font_issue=False,
        text_sample="Procédure de gestion",
    )
    assert info.page_number == 1
    assert info.page_type == "text"
    assert info.has_selectable_text is True
    assert info.image_count == 0
    assert info.font_issue is False
    assert info.text_sample == "Procédure de gestion"


def test_page_info_image_page():
    info = PageInfo(
        page_number=3,
        page_type="image",
        has_selectable_text=False,
        image_count=4,
        font_issue=False,
        text_sample="",
    )
    assert info.page_type == "image"
    assert info.has_selectable_text is False
    assert info.image_count == 4


def test_page_map_construction():
    page = PageInfo(
        page_number=1,
        page_type="text",
        has_selectable_text=True,
        image_count=0,
        font_issue=False,
        text_sample="Hello",
    )
    pm = PageMap(
        total_pages=1,
        file_format="pdf",
        quality_tier="A",
        pages=[page],
        producer="Microsoft Word 2016",
    )
    assert pm.total_pages == 1
    assert pm.file_format == "pdf"
    assert pm.quality_tier == "A"
    assert len(pm.pages) == 1
    assert pm.producer == "Microsoft Word 2016"


def test_page_map_producer_none():
    page = PageInfo(page_number=1, page_type="text", has_selectable_text=True, image_count=0, font_issue=False, text_sample="x" * 150)
    pm = PageMap(total_pages=1, file_format="pdf", quality_tier="A", pages=[page], producer=None)
    assert pm.producer is None
