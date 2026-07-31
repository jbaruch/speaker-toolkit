"""Tests for pptx-extraction.py — PPTX visual data extraction."""

import json
import struct
import subprocess
import sys
import zipfile

import pytest
from pptx import Presentation
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls
from pptx.util import Inches, Pt

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
    blindness as issue #116, one layer down. python-pptx has no public authoring
    API for image backgrounds, so this test stubs only the classifier. XML/blob
    extraction is covered by the synthetic background fixture below.
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


# ── OCR inventory on low-confidence slides (issue #129) ──────────────
#
# #116/#119 stopped asserting absence. #129 fills a word inventory from
# picture blobs so analysis can cite and cross-check, without replacing
# the vision pass for design dimensions.


def _png_with_text(path, text="VENUE PREPARATION", w=800, h=200):
    """Build a high-contrast PNG with clear text via Pillow (no binary fixture).

    Prefer a TrueType font when the OS has one; otherwise draw with the
    default bitmap font on a small canvas and nearest-neighbor upscale so OCR
    stays reliable without fixtures.
    """
    from PIL import Image, ImageDraw, ImageFont

    font = None
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # CI (Ubuntu)
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",     # macOS
        "/Library/Fonts/Arial Bold.ttf",
    ):
        try:
            font = ImageFont.truetype(candidate, 48)
            break
        except OSError:
            continue

    if font is None:
        scale = 8
        small = Image.new("RGB", (max(w // scale, 100), max(h // scale, 40)), "white")
        ImageDraw.Draw(small).text(
            (2, 2), text, fill="black", font=ImageFont.load_default(),
        )
        img = small.resize((w, h), Image.Resampling.NEAREST)
    else:
        img = Image.new("RGB", (w, h), "white")
        ImageDraw.Draw(img).text((20, 60), text, fill="black", font=font)

    img.save(path, format="PNG")
    return str(path)


def test_normalize_ocr_text(pptx_extraction):
    assert pptx_extraction.normalize_ocr_text("  a \n\tb  ") == "a b"
    assert pptx_extraction.normalize_ocr_text("") == ""
    assert pptx_extraction.normalize_ocr_text(None) == ""


def test_high_confidence_slide_method_is_shapes_only(pptx_extraction, tmp_path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "A real title"
    data = _first_slide(pptx_extraction, prs, tmp_path)
    assert data["text_extraction_confidence"] == "high"
    assert data["text_extraction_method"] == "shapes"
    assert data["ocr_text"] == ""


def test_full_bleed_runs_ocr_fn_and_records_inventory(
    pptx_extraction, tmp_path,
):
    """Low-confidence picture slide gets ocr_text from the OCR path."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(
        _png_with_text(tmp_path / "labeled.png"), 0, 0,
        width=prs.slide_width, height=prs.slide_height,
    )
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    data = pptx_extraction.extract_pptx(
        path, ocr_fn=lambda blobs: "VENUE PREPARATION",
    )["per_slide_visual"][0]

    assert data["text_extraction_confidence"] == "low"
    assert data["text_content_preview"] == ""  # shapes still empty
    assert data["ocr_text"] == "VENUE PREPARATION"
    assert data["text_extraction_method"] == "shapes+ocr"


def test_no_ocr_flag_skips_inventory(pptx_extraction, tmp_path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(
        _png_with_text(tmp_path / "labeled.png"), 0, 0,
        width=prs.slide_width, height=prs.slide_height,
    )
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    called = []

    def spy(blobs):
        called.append(blobs)
        return "SHOULD NOT APPEAR"

    data = pptx_extraction.extract_pptx(
        path, ocr=False, ocr_fn=spy,
    )["per_slide_visual"][0]

    assert called == []
    assert data["ocr_text"] == ""
    assert data["text_extraction_method"] == "shapes"
    assert data["text_extraction_confidence"] == "low"


def test_small_decorative_image_does_not_ocr(pptx_extraction, tmp_path):
    """High-confidence slides must not pay for OCR."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Title"
    slide.shapes.add_picture(
        _png_with_text(tmp_path / "logo.png", text="LOGO"), 0, 0,
        width=int(prs.slide_width * 0.1), height=int(prs.slide_height * 0.1),
    )
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    called = []
    data = pptx_extraction.extract_pptx(
        path, ocr_fn=lambda blobs: called.append(blobs) or "X",
    )["per_slide_visual"][0]

    assert data["text_extraction_confidence"] == "high"
    assert called == []
    assert data["ocr_text"] == ""
    assert data["text_extraction_method"] == "shapes"


def test_ocr_unavailable_records_method_not_crash(pptx_extraction, tmp_path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(
        _png(tmp_path / "i.png"), 0, 0,
        width=prs.slide_width, height=prs.slide_height,
    )
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    def boom(_blobs):
        raise pptx_extraction.OcrUnavailableError("no engine")

    data = pptx_extraction.extract_pptx(path, ocr_fn=boom)["per_slide_visual"][0]
    assert data["ocr_text"] == ""
    assert data["text_extraction_method"] == "shapes+ocr_unavailable"
    assert data["text_extraction_confidence"] == "low"


def test_reported_image_background_without_blob_does_not_claim_ocr(
    pptx_extraction, tmp_path, monkeypatch,
):
    """A reported background without actual XML/blob never claims OCR ran."""
    monkeypatch.setattr(
        pptx_extraction, "get_background_color", lambda slide: (None, "image"),
    )
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    called = []
    data = pptx_extraction.extract_pptx(
        path, ocr_fn=lambda blobs: called.append(blobs) or "X",
    )["per_slide_visual"][0]

    assert data["text_extraction_confidence"] == "low"
    assert called == []
    assert data["ocr_text"] == ""
    assert data["text_extraction_method"] == "shapes"


def test_ocr_text_capped(pptx_extraction, monkeypatch):
    monkeypatch.setattr(
        pptx_extraction, "ocr_image_bytes", lambda blob: "A" * 9000,
    )
    out = pptx_extraction.ocr_picture_blobs([b"x"])
    assert len(out) == pptx_extraction._OCR_TEXT_MAX_CHARS


def test_ocr_image_bytes_reads_clear_text(pptx_extraction, tmp_path):
    """Integration: real tesseract on a programmatic text PNG."""
    pytesseract = pytest.importorskip("pytesseract")
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        pytest.skip("tesseract binary not installed")

    path = tmp_path / "clear.png"
    _png_with_text(path, text="VENUE PREPARATION")
    text = pptx_extraction.ocr_image_bytes(path.read_bytes())
    assert "VENUE" in text.upper()
    assert "PREPARATION" in text.upper()


def test_full_bleed_with_baked_text_end_to_end(pptx_extraction, tmp_path):
    """Integration: full-bleed labeled picture yields non-empty ocr_text."""
    pytesseract = pytest.importorskip("pytesseract")
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        pytest.skip("tesseract binary not installed")

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(
        _png_with_text(tmp_path / "labeled.png", text="VENUE PREPARATION"),
        0, 0, width=prs.slide_width, height=prs.slide_height,
    )
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    data = pptx_extraction.extract_pptx(path)["per_slide_visual"][0]
    assert data["text_extraction_confidence"] == "low"
    assert data["text_content_preview"] == ""
    assert data["text_extraction_method"] == "shapes+ocr"
    assert "VENUE" in data["ocr_text"].upper()
    assert "PREPARATION" in data["ocr_text"].upper()


# ── recursive/container fidelity and provenance ──────────────────────


def test_grouped_shapes_are_walked_recursively_and_lower_confidence(
    pptx_extraction, tmp_path,
):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    outer = slide.shapes.add_group_shape()
    outer_text = outer.shapes.add_textbox(
        Inches(1), Inches(1), Inches(4), Inches(1),
    )
    outer_text.text_frame.text = "Text inside outer group"
    inner = outer.shapes.add_group_shape()
    inner_text = inner.shapes.add_textbox(
        Inches(2), Inches(2), Inches(4), Inches(1),
    )
    inner_text.text_frame.text = "Text inside nested group"

    data = _first_slide(pptx_extraction, prs, tmp_path)

    assert "Text inside outer group" in data["text_content_preview"]
    assert "Text inside nested group" in data["text_content_preview"]
    assert data["shape_count"] == 1
    assert data["shape_count_recursive"] == 4
    assert data["text_extraction_confidence"] == "low"
    assert data["render_required"] is True
    assert "grouped_shapes" in data["render_required_reasons"]

    nested = next(
        channel for channel in data["text_channels"]
        if channel["text"] == "Text inside nested group"
    )
    assert nested["confidence"] == "medium"
    assert nested["provenance"]["source"] == "pptx_shape_text_frame"
    assert len(nested["provenance"]["shape_path"]) == 3


def test_table_cell_text_has_its_own_provenance_channel(
    pptx_extraction, tmp_path,
):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    table_shape = slide.shapes.add_table(
        2, 2, Inches(1), Inches(1), Inches(6), Inches(2),
    )
    table_shape.table.cell(0, 0).text = "Name"
    table_shape.table.cell(0, 1).text = "Count"
    table_shape.table.cell(1, 0).text = "Hooks"
    table_shape.table.cell(1, 1).text = "12"

    data = _first_slide(pptx_extraction, prs, tmp_path)

    assert "Hooks" in data["text_content_preview"]
    channel = next(
        item for item in data["text_channels"]
        if item["channel"] == "table_cell_text"
    )
    assert channel["confidence"] == "medium"
    assert channel["status"] == "extracted"
    assert channel["provenance"]["source"] == "pptx_table_cells"
    assert channel["provenance"]["cells"] == ["R1C1", "R1C2", "R2C1", "R2C2"]
    assert data["text_extraction_confidence"] == "low"
    assert "table" in data["render_required_reasons"]
    summary = next(
        item for item in data["shapes_summary"]
        if item.get("graphic_frame_type") == "table"
    )
    assert summary["table_rows"] == 2
    assert summary["table_columns"] == 2


def test_smartart_and_unknown_graphic_frames_are_explicitly_unsupported(
    pptx_extraction, tmp_path,
):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    smartart = slide.shapes.add_table(
        1, 1, Inches(1), Inches(1), Inches(3), Inches(1),
    )
    smartart.element.graphic.graphicData.uri = (
        "http://schemas.openxmlformats.org/drawingml/2006/diagram"
    )
    other = slide.shapes.add_table(
        1, 1, Inches(1), Inches(3), Inches(3), Inches(1),
    )
    other.element.graphic.graphicData.uri = "urn:example:unsupported-graphic"

    data = _first_slide(pptx_extraction, prs, tmp_path)

    assert data["has_unsupported_content"] is True
    assert data["text_extraction_confidence"] == "low"
    assert data["render_required"] is True
    kinds = {item["content_type"] for item in data["unsupported_content"]}
    assert kinds == {"smartart", "graphic_frame"}
    assert {
        item["channel"] for item in data["text_channels"]
        if item["status"] == "unsupported"
    } == {"smartart_text", "graphic_frame_text"}
    assert all(
        item["graphic_data_uri"]
        for item in data["unsupported_content"]
    )


def _set_background_image(slide, image_path):
    """Author an image background directly in DrawingML for fixture coverage."""
    _, r_id = slide.part.get_or_add_image_part(str(image_path))
    bg_pr = slide.element.cSld.get_or_add_bgPr()
    existing_fill = bg_pr.eg_fillProperties
    if existing_fill is not None:
        bg_pr.remove(existing_fill)
    blip_fill = parse_xml(
        f'<a:blipFill {nsdecls("a", "r")}>'
        f'<a:blip r:embed="{r_id}"/>'
        '<a:stretch><a:fillRect/></a:stretch>'
        '</a:blipFill>'
    )
    bg_pr.insert(0, blip_fill)
    return r_id


def test_background_image_blob_is_ocrd_with_distinct_provenance(
    pptx_extraction, tmp_path,
):
    image_path = tmp_path / "background.png"
    _png_with_text(image_path, text="BACKGROUND LABEL")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_background_image(slide, image_path)
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    seen = []
    data = pptx_extraction.extract_pptx(
        path,
        ocr_fn=lambda blobs: seen.append(blobs) or "BACKGROUND LABEL",
    )["per_slide_visual"][0]

    assert data["background_type"] == "image"
    assert data["has_image"] is False
    assert data["text_extraction_confidence"] == "low"
    assert data["render_required"] is True
    assert "background_image" in data["render_required_reasons"]
    assert len(seen) == 1 and seen[0][0].startswith(b"\x89PNG")
    channel = next(
        item for item in data["text_channels"]
        if item["channel"] == "background_image_ocr"
    )
    assert channel["status"] == "extracted"
    assert channel["text"] == "BACKGROUND LABEL"
    assert channel["confidence"] == "low"
    assert channel["provenance"]["source"] == "pptx_background_image"
    assert channel["provenance"]["part_name"].startswith("ppt/media/")
    assert data["ocr_text"] == "BACKGROUND LABEL"


def test_background_inspection_does_not_break_inheritance(pptx_extraction):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    assert slide.element.cSld.bg is None

    assert pptx_extraction.get_background_color(slide) == (None, "unknown")

    # Access through python-pptx's public fill property would author a noFill
    # node here and sever inheritance. Extraction must stay read-only.
    assert slide.element.cSld.bg is None


def test_missing_background_blob_requires_render_without_claiming_ocr(
    pptx_extraction, tmp_path,
):
    image_path = tmp_path / "background.png"
    _png(image_path)
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_background_image(slide, image_path)
    blip = next(iter(
        slide.element.cSld.bg.bgPr.eg_fillProperties.iter(
            pptx_extraction.qn("a:blip")
        )
    ))
    blip.set(pptx_extraction.qn("r:embed"), "rIdMissing")

    data = _first_slide(pptx_extraction, prs, tmp_path)

    channel = next(
        item for item in data["text_channels"]
        if item["channel"] == "background_image_ocr"
    )
    assert channel["status"] == "unavailable"
    assert channel["text"] == ""
    assert data["text_extraction_method"] == "shapes"
    assert data["text_extraction_confidence"] == "low"
    assert data["render_required"] is True


def _damage_first_media_member(path):
    """Flip a compressed payload byte without updating its recorded CRC."""
    with zipfile.ZipFile(path) as archive:
        member = next(
            item for item in archive.infolist()
            if item.filename.startswith("ppt/media/") and item.file_size
        )
    package = bytearray(path.read_bytes())
    name_size, extra_size = struct.unpack_from(
        "<HH", package, member.header_offset + 26,
    )
    payload_offset = member.header_offset + 30 + name_size + extra_size
    package[payload_offset + (member.compress_size // 2)] ^= 0xFF
    path.write_bytes(package)
    return member.filename


def test_bad_crc_media_is_recovered_without_losing_the_deck(
    pptx_extraction, tmp_path,
):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    box.text_frame.text = "Healthy native text"
    slide.shapes.add_picture(
        _png(tmp_path / "asset.png"),
        Inches(1), Inches(2), Inches(2), Inches(2),
    )
    path = tmp_path / "corrupt-media.pptx"
    prs.save(path)
    damaged_name = _damage_first_media_member(path)

    result = pptx_extraction.extract_pptx(str(path), ocr=False)
    data = result["per_slide_visual"][0]

    assert result["slide_count"] == 1
    assert result["corrupt_assets"] == [{
        "part_name": damaged_name,
        "error_type": "crc_mismatch",
        "status": "recovered_with_placeholder",
    }]
    assert "Healthy native text" in data["text_content_preview"]
    assert data["text_extraction_confidence"] == "low"
    assert "corrupt_embedded_asset" in data["render_required_reasons"]
    assert any(
        item["content_type"] == "corrupt_embedded_asset"
        for item in data["unsupported_content"]
    )


def test_versions_and_input_fingerprint_are_stable_and_content_addressed(
    pptx_extraction, tmp_path,
):
    prs = make_deck(1)
    source = tmp_path / "source.pptx"
    prs.save(source)
    copy = tmp_path / "copy.pptx"
    copy.write_bytes(source.read_bytes())
    modified = tmp_path / "modified.pptx"
    modified.write_bytes(source.read_bytes() + b"\x00")

    first = pptx_extraction.extract_pptx(str(source), ocr=False)
    second = pptx_extraction.extract_pptx(str(source), ocr=False)
    copied = pptx_extraction.extract_pptx(str(copy), ocr=False)
    changed = pptx_extraction.extract_pptx(str(modified), ocr=False)

    assert first["schema_version"] == pptx_extraction.SCHEMA_VERSION
    assert first["pipeline_version"] == pptx_extraction.PIPELINE_VERSION
    assert first["input_fingerprint"] == second["input_fingerprint"]
    assert first["input_fingerprint"] == copied["input_fingerprint"]
    assert first["input_fingerprint"] != changed["input_fingerprint"]
    assert first["input_fingerprint"]["algorithm"] == "sha256"
    assert len(first["input_fingerprint"]["digest"]) == 64
    assert first["input_fingerprint"]["size_bytes"] == source.stat().st_size


def test_version_flag_is_machine_readable(pptx_extraction):
    proc = subprocess.run(
        [sys.executable, pptx_extraction.__file__, "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(proc.stdout) == {
        "schema_version": pptx_extraction.SCHEMA_VERSION,
        "pipeline_version": pptx_extraction.PIPELINE_VERSION,
    }
