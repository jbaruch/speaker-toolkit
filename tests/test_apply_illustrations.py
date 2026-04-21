"""Tests for apply-illustrations-to-deck.py — zone parsing, scrim, title repositioning."""

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from conftest import make_deck


OUTLINE_WITH_ZONES = """\
### Slide 2: The Problem
- Format: **FULL**
- Image prompt: `A confused developer`
- Safe zone: upper_third (painted sky backdrop)
- Text: **The Problem**

### Slide 5: The Solution
- Format: **FULL**
- Image prompt: `A clean architecture`
- Safe zone: lower_third (flat gradient)
- Text: **The Solution**

### Slide 8: Split View
- Format: **FULL**
- Image prompt: `Side by side comparison`
- Safe zone: left_half (studio backdrop)
- Text: **Before and After**
"""

OUTLINE_NO_ZONES = """\
### Slide 1: Title
- Format: **FULL**
- Image prompt: `A title slide`
- Text: **Title**
"""


def test_parse_zones(apply_illustrations, tmp_path):
    outline = tmp_path / "outline.md"
    outline.write_text(OUTLINE_WITH_ZONES)
    zones = apply_illustrations.parse_zones(outline)
    assert zones == {2: "upper_third", 5: "lower_third", 8: "left_half"}


def test_parse_zones_empty(apply_illustrations, tmp_path):
    outline = tmp_path / "outline.md"
    outline.write_text(OUTLINE_NO_ZONES)
    zones = apply_illustrations.parse_zones(outline)
    assert zones == {}


def test_parse_zones_all_types(apply_illustrations, tmp_path):
    text = """\
### Slide 1: A
- Safe zone: upper_third (sky)
### Slide 2: B
- Safe zone: middle_third (frame)
### Slide 3: C
- Safe zone: lower_third (ground)
### Slide 4: D
- Safe zone: left_half (wall)
### Slide 5: E
- Safe zone: right_half (backdrop)
"""
    outline = tmp_path / "outline.md"
    outline.write_text(text)
    zones = apply_illustrations.parse_zones(outline)
    assert len(zones) == 5
    assert zones[1] == "upper_third"
    assert zones[2] == "middle_third"
    assert zones[3] == "lower_third"
    assert zones[4] == "left_half"
    assert zones[5] == "right_half"


def test_zone_layout_keys(apply_illustrations):
    """All five zones have layout entries."""
    for zone in ["upper_third", "middle_third", "lower_third", "left_half", "right_half"]:
        assert zone in apply_illustrations.ZONE_LAYOUT
        layout = apply_illustrations.ZONE_LAYOUT[zone]
        assert "top_in" in layout
        assert "left_in" in layout
        assert "width_in" in layout
        assert "height_in" in layout


def test_scrim_shape_name_constant(apply_illustrations):
    """Scrim uses a named constant for detection."""
    assert apply_illustrations.SCRIM_SHAPE_NAME == "_title_scrim"


def test_ensure_scrim_adds_shape(apply_illustrations, tmp_path):
    """ensure_scrim adds a scrim rectangle to a slide."""
    prs = Presentation()
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    # Add a textbox so the slide has text
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))

    result = apply_illustrations.ensure_scrim(slide, "upper_third", "000000", 45000)
    assert result == 1

    # Verify a shape with the scrim name was added
    scrim_shapes = [s for s in slide.shapes if s.name == "_title_scrim"]
    assert len(scrim_shapes) == 1


def test_ensure_scrim_idempotent(apply_illustrations, tmp_path):
    """Running ensure_scrim twice doesn't add a second scrim."""
    prs = Presentation()
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))

    apply_illustrations.ensure_scrim(slide, "upper_third", "000000", 45000)
    result = apply_illustrations.ensure_scrim(slide, "upper_third", "000000", 45000)
    assert result == 0  # Already present, not added again

    scrim_shapes = [s for s in slide.shapes if s.name == "_title_scrim"]
    assert len(scrim_shapes) == 1


def test_reposition_title(apply_illustrations, tmp_path):
    """Title text shapes are repositioned to the zone."""
    prs = Presentation()
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    tb.text_frame.paragraphs[0].add_run().text = "Title"

    moved = apply_illustrations.reposition_title(slide, "upper_third")
    assert moved == 1
