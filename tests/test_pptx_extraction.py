"""Tests for pptx-extraction.py — PPTX visual data extraction."""

import pytest
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


# ── text_extraction_confidence (issue #116) ──────────────────────────
#
# `pptx-extraction.py` reads text out of PPTX shapes. Text rendered inside a
# picture — the norm for AI-generated illustration decks — is invisible to it.
# These tests pin the contract that the extractor reports that blindness
# instead of asserting the slide is wordless.


def _png(path, w=16, h=16):
    """Emit a minimal valid PNG from stdlib only (no image library needed)."""
    import struct
    import zlib

    def chunk(tag, data):
        body = tag + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + b"\x7f\x7f\x7f" * w for _ in range(h))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return str(path)


def _first_slide(pptx_extraction, prs, tmp_path):
    path = str(tmp_path / "deck.pptx")
    prs.save(path)
    return pptx_extraction.extract_pptx(path)["per_slide_visual"][0]


def test_picture_area_ratio_full_bleed(pptx_extraction, tmp_path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(
        _png(tmp_path / "i.png"), 0, 0,
        width=prs.slide_width, height=prs.slide_height,
    )
    data = _first_slide(pptx_extraction, prs, tmp_path)
    assert data["image_area_ratio"] > 0.99


def test_picture_area_ratio_missing_geometry_is_zero(pptx_extraction):
    """Unknown size is not evidence of a large picture."""
    class _Shape:
        width = None
        height = None

    class _Prs:
        slide_width = 9144000
        slide_height = 6858000

    assert pptx_extraction.picture_area_ratio(_Shape(), _Prs()) == 0.0


def test_full_bleed_image_slide_does_not_assert_absence(
    pptx_extraction, tmp_path,
):
    """Issue #116: a full-bleed image slide must not read as 'no text'."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(
        _png(tmp_path / "i.png"), 0, 0,
        width=prs.slide_width, height=prs.slide_height,
    )
    data = _first_slide(pptx_extraction, prs, tmp_path)

    assert data["has_image"] is True
    assert data["has_text_frame_shapes"] is False
    assert data["text_content_preview"] == ""
    # The load-bearing assertion: unreadable is reported as low confidence,
    # never as evidence the slide is wordless.
    assert data["text_extraction_confidence"] == "low"


def test_text_slide_is_high_confidence(pptx_extraction, tmp_path):
    """No picture — extractable text is the whole story."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "A real title"
    data = _first_slide(pptx_extraction, prs, tmp_path)
    assert data["has_text_frame_shapes"] is True
    assert data["text_extraction_confidence"] == "high"


def test_small_decorative_image_stays_high_confidence(
    pptx_extraction, tmp_path,
):
    """A logo-sized picture cannot be hiding the slide's content."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Title"
    slide.shapes.add_picture(
        _png(tmp_path / "i.png"), 0, 0,
        width=int(prs.slide_width * 0.1), height=int(prs.slide_height * 0.1),
    )
    data = _first_slide(pptx_extraction, prs, tmp_path)
    assert data["has_image"] is True
    assert data["image_area_ratio"] < 0.5
    assert data["text_extraction_confidence"] == "high"


def test_text_overlay_over_full_bleed_is_still_low_confidence(
    pptx_extraction, tmp_path,
):
    """Extracting *some* text is not evidence of extracting *all* of it."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Overlay"
    slide.shapes.add_picture(
        _png(tmp_path / "i.png"), 0, 0,
        width=prs.slide_width, height=prs.slide_height,
    )
    data = _first_slide(pptx_extraction, prs, tmp_path)
    assert data["has_text_frame_shapes"] is True
    assert data["text_extraction_confidence"] == "low"


def test_retired_field_is_gone(pptx_extraction, tmp_path):
    """`has_text_placeholder` named a claim the extractor cannot make."""
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    data = _first_slide(pptx_extraction, prs, tmp_path)
    assert "has_text_placeholder" not in data
    assert "has_text_frame_shapes" in data


def test_image_background_slide_is_low_confidence(
    pptx_extraction, tmp_path, monkeypatch,
):
    """An image *background* covers the slide and can carry baked-in text.

    It is not a PICTURE shape, so the shape walk never sees it — the same
    blindness as issue #116, one layer down. python-pptx cannot author an
    image background, so the classifier is stubbed to report one and the
    assertion is on the emitted contract, not on the stub.
    """
    monkeypatch.setattr(
        pptx_extraction, "get_background_color", lambda slide: (None, "image"),
    )
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])  # no pictures, no text
    data = _first_slide(pptx_extraction, prs, tmp_path)

    assert data["background_type"] == "image"
    assert data["has_image"] is False        # not a PICTURE shape
    assert data["image_area_ratio"] == 0.0   # no picture geometry at all
    assert data["text_extraction_confidence"] == "low"


def test_area_ratio_is_not_rounded_across_the_threshold(pptx_extraction):
    """Rounding must not decide classification.

    A picture at 0.4996 of the slide is below the threshold; rounding it to
    0.5 first would flip it and make the threshold depend on the rounding.
    """
    class _Prs:
        slide_width = 10000
        slide_height = 10000

    class _Shape:
        # 0.4996 of the slide area — just under the threshold.
        width = 4996
        height = 10000

    ratio = pptx_extraction.picture_area_ratio(_Shape(), _Prs())
    assert ratio < pptx_extraction._TEXT_BEARING_IMAGE_AREA_RATIO
    assert ratio == pytest.approx(0.4996)
