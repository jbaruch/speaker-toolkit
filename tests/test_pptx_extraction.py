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


def test_template_layouts_emitted(pptx_extraction, tmp_path):
    """extract_pptx must emit a top-level template_layouts key."""
    prs = make_deck(1)
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    result = pptx_extraction.extract_pptx(path)
    assert "template_layouts" in result
    assert isinstance(result["template_layouts"], list)


def test_template_layouts_default_count(pptx_extraction):
    """A default python-pptx Presentation ships with 11 stock layouts under 1 master."""
    prs = Presentation()
    layouts = pptx_extraction.extract_template_layouts(prs)
    assert len(layouts) == 11
    assert all(layout["master_index"] == 0 for layout in layouts)


def test_template_layouts_entry_shape(pptx_extraction):
    """Each layout entry has the canonical keys with the documented types."""
    prs = Presentation()
    layouts = pptx_extraction.extract_template_layouts(prs)
    expected_keys = {"index", "master_index", "name", "placeholders"}
    for layout in layouts:
        assert set(layout.keys()) == expected_keys
        assert isinstance(layout["index"], int)
        assert isinstance(layout["master_index"], int)
        assert isinstance(layout["name"], str)
        assert isinstance(layout["placeholders"], list)


def test_template_layouts_index_is_global_and_sequential(pptx_extraction):
    """The `index` field is a global running counter, not per-master."""
    prs = Presentation()
    layouts = pptx_extraction.extract_template_layouts(prs)
    indices = [layout["index"] for layout in layouts]
    assert indices == list(range(len(layouts)))


def test_template_layouts_placeholder_shape(pptx_extraction):
    """Placeholder entries carry idx (int) + type (canonical name string)."""
    prs = Presentation()
    layouts = pptx_extraction.extract_template_layouts(prs)
    # python-pptx stock template has at least one layout with a TITLE placeholder.
    title_layouts = [
        layout for layout in layouts
        if any(p.get("type") == "TITLE" for p in layout["placeholders"])
    ]
    assert title_layouts, "expected at least one layout with a TITLE placeholder"
    for layout in layouts:
        for p in layout["placeholders"]:
            assert set(p.keys()) == {"idx", "type"}
            assert isinstance(p["idx"], int)
            assert isinstance(p["type"], str)
            # Type names should be canonical enum identifiers (no surrounding " (3)" digits)
            assert "(" not in p["type"]


def test_template_layouts_known_layout_name(pptx_extraction):
    """At least one layout from the python-pptx stock template carries a recognizable name."""
    prs = Presentation()
    layouts = pptx_extraction.extract_template_layouts(prs)
    names = [layout["name"] for layout in layouts]
    # python-pptx stock layouts include "Title Slide" and "Blank" as part of the default master.
    assert "Title Slide" in names
    assert "Blank" in names
