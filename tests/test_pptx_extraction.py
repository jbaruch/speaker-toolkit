"""Tests for pptx-extraction.py — PPTX visual data extraction."""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

from conftest import make_deck


def test_slide_count(pptx_extraction, tmp_path):
    prs = make_deck(5)
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    result = pptx_extraction.extract_pptx(path)
    assert result["slide_count"] == 5


def test_slide_dimensions(pptx_extraction, tmp_path):
    prs = make_deck(1)
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    result = pptx_extraction.extract_pptx(path)
    # Default slide dimensions should be reasonable
    assert result["slide_width_inches"] > 0
    assert result["slide_height_inches"] > 0


def test_shape_text_extraction(pptx_extraction, tmp_path):
    prs = Presentation()
    layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = "Hello World"
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    result = pptx_extraction.extract_pptx(path)
    slide_data = result["per_slide_visual"][0]
    assert "Hello World" in slide_data["text_content_preview"]


def test_font_tracking(pptx_extraction, tmp_path):
    prs = Presentation()
    layout = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(layout)
    txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    tf = txBox.text_frame
    run = tf.paragraphs[0].add_run()
    run.text = "Test text"
    run.font.name = "Arial"
    run.font.size = Pt(24)
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    result = pptx_extraction.extract_pptx(path)
    assert "Arial" in result["global_design"]["fonts_used"]


def test_skip_static(pptx_extraction):
    skip, reason = pptx_extraction.should_skip("presentation-static.pptx", [])
    assert skip is True
    assert "static" in reason


def test_skip_conflict_copy(pptx_extraction):
    skip, reason = pptx_extraction.should_skip("deck (1).pptx", [])
    assert skip is True
    assert "conflict" in reason


def test_skip_custom_pattern(pptx_extraction):
    skip, reason = pptx_extraction.should_skip("my-template.pptx", ["template"])
    assert skip is True


def test_no_skip_normal_file(pptx_extraction):
    skip, _ = pptx_extraction.should_skip("great-talk.pptx", [])
    assert skip is False


def test_per_slide_visual_count(pptx_extraction, tmp_path):
    prs = make_deck(3)
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    result = pptx_extraction.extract_pptx(path)
    assert len(result["per_slide_visual"]) == 3
