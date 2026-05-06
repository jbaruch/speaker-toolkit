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


def test_reposition_title_placeholder(apply_illustrations, tmp_path):
    """Placeholder title shapes (from Title layouts) are also repositioned."""
    prs = Presentation()
    title_layout = prs.slide_layouts[0]  # Title Slide layout
    slide = prs.slides.add_slide(title_layout)
    if slide.shapes.title:
        slide.shapes.title.text = "Placeholder Title"

    moved = apply_illustrations.reposition_title(slide, "lower_third")
    # Title Slide has title + subtitle placeholders
    assert moved >= 1


def test_parse_zones_no_cross_slide_match(apply_illustrations, tmp_path):
    """Safe zone from slide 5 doesn't leak into slide 4."""
    text = """\
### Slide 4: No Zone Here
- Format: **FULL**
- Image prompt: `A scene`

### Slide 5: Has Zone
- Format: **FULL**
- Image prompt: `Another scene`
- Safe zone: lower_third (gradient)
"""
    outline = tmp_path / "outline.md"
    outline.write_text(text)
    zones = apply_illustrations.parse_zones(outline)
    assert 4 not in zones
    assert zones.get(5) == "lower_third"


# ── IMG+TXT layout tests ─────────────────────────────────────────────


OUTLINE_MIXED_FORMATS = """\
### Slide 1: Hook
- Format: **FULL**
- Image prompt: `Opening scene`
- Safe zone: upper_third (sky)

### Slide 2: Detail
- Format: **IMG+TXT**
- Image prompt: `A diagram with explanation`

### Slide 3: Exception
- Format: **EXCEPTION** — real screenshot
- Visual: screenshot of the dashboard

### Slide 4: Both fields
- Format: **IMG+TXT**
- Safe zone: lower_third (gradient)
- Image prompt: `Mixed signals`
"""


def test_parse_img_txt_slides(apply_illustrations, tmp_path):
    outline = tmp_path / "outline.md"
    outline.write_text(OUTLINE_MIXED_FORMATS)
    img_txt = apply_illustrations.parse_img_txt_slides(outline)
    # Slide 2 is IMG+TXT only — included
    assert 2 in img_txt
    # Slide 1 is FULL — excluded
    assert 1 not in img_txt
    # Slide 3 is EXCEPTION — excluded
    assert 3 not in img_txt
    # Slide 4 has both Format: IMG+TXT and Safe zone — Safe zone wins, excluded
    assert 4 not in img_txt


def test_parse_img_txt_slides_empty(apply_illustrations, tmp_path):
    outline = tmp_path / "outline.md"
    outline.write_text(OUTLINE_NO_ZONES)
    img_txt = apply_illustrations.parse_img_txt_slides(outline)
    assert img_txt == set()


def test_parse_zones_and_img_txt_disjoint(apply_illustrations, tmp_path):
    """A slide with both Safe zone and Format: IMG+TXT goes to zones, not img_txt."""
    outline = tmp_path / "outline.md"
    outline.write_text(OUTLINE_MIXED_FORMATS)
    zones = apply_illustrations.parse_zones(outline)
    img_txt = apply_illustrations.parse_img_txt_slides(outline)
    # Slide 4 has Safe zone — it's a FULL slide via the zone path
    assert zones.get(4) == "lower_third"
    assert 4 not in img_txt


def test_apply_img_txt_layout_repositions_picture(apply_illustrations, tmp_path):
    """Picture in an IMG+TXT slide is moved to the left column at ~60% width."""
    prs = Presentation()
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    # Add a picture at an arbitrary position
    img = tmp_path / "test.png"
    # Minimal 1x1 PNG
    img.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108020000"
            "00907753de0000000c4944415478da6300010000000500010d0a2db40000"
            "000049454e44ae426082"
        )
    )
    slide.shapes.add_picture(str(img), Inches(2), Inches(2), Inches(4), Inches(3))

    pic_moved, _ = apply_illustrations.apply_img_txt_layout(slide)
    assert pic_moved == 1

    pictures = [s for s in slide.shapes if s.shape_type == 13]  # PICTURE
    bg = pictures[0]
    assert bg.left == Inches(apply_illustrations.IMGTXT_IMG_LEFT_IN)
    assert bg.top == Inches(apply_illustrations.IMGTXT_IMG_TOP_IN)
    assert bg.width == Inches(apply_illustrations.IMGTXT_IMG_WIDTH_IN)
    assert bg.height == Inches(apply_illustrations.IMGTXT_IMG_HEIGHT_IN)


def test_apply_img_txt_layout_repositions_title(apply_illustrations):
    """Title placeholder is repositioned to the right column."""
    prs = Presentation()
    title_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_layout)
    if slide.shapes.title:
        slide.shapes.title.text = "Right Column Title"

    _, text_moved = apply_illustrations.apply_img_txt_layout(slide)
    assert text_moved >= 1
    assert slide.shapes.title.left == Inches(apply_illustrations.IMGTXT_TEXT_LEFT_IN)
    assert slide.shapes.title.top == Inches(apply_illustrations.IMGTXT_TITLE_TOP_IN)


def test_imgtxt_geometry_constants_consistent(apply_illustrations):
    """IMG+TXT image + text columns + margins fit the 13.333" slide."""
    img_right = (
        apply_illustrations.IMGTXT_IMG_LEFT_IN
        + apply_illustrations.IMGTXT_IMG_WIDTH_IN
    )
    text_right = (
        apply_illustrations.IMGTXT_TEXT_LEFT_IN
        + apply_illustrations.IMGTXT_TEXT_WIDTH_IN
    )
    assert img_right < apply_illustrations.IMGTXT_TEXT_LEFT_IN, (
        "Image must finish before the text column starts"
    )
    assert text_right <= apply_illustrations.SLIDE_W_IN, (
        "Text column must fit within the slide width"
    )
