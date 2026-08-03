"""Tests for pptx-extraction.py — PPTX visual data extraction."""

import io
import json
import struct
import subprocess
import sys
import zipfile
from types import SimpleNamespace

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


def test_ocr_confidence_is_paired_only_with_retained_token(pptx_extraction):
    text, confidence = pptx_extraction._ocr_text_and_confidence({
        "text": ["", "VISIBLE"],
        "conf": [99.0, 12.0],
    })
    assert text == "VISIBLE"
    assert confidence == 12.0


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


def test_multi_image_ocr_emits_one_identity_and_outcome_receipt_per_asset(
    pptx_extraction, tmp_path,
):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(
        _png_with_text(tmp_path / "left.png", text="LEFT LABEL"),
        0,
        0,
        width=int(prs.slide_width / 2),
        height=prs.slide_height,
    )
    slide.shapes.add_picture(
        _png_with_text(tmp_path / "right.png", text="RIGHT LABEL"),
        int(prs.slide_width / 2),
        0,
        width=int(prs.slide_width / 2),
        height=prs.slide_height,
    )
    path = tmp_path / "multi-image.pptx"
    prs.save(path)
    outcomes = iter([
        {
            "engine": "fixture-ocr",
            "engine_version": "1.0",
            "result_status": "text_recovered",
            "result_confidence": 94.5,
            "recovered_text": "LEFT LABEL",
            "trustworthy_text": True,
            "error": None,
        },
        {
            "engine": "fixture-ocr",
            "engine_version": "1.0",
            "result_status": "low_confidence_text",
            "result_confidence": 31.0,
            "recovered_text": "RIGHT LAB3L",
            "trustworthy_text": False,
            "error": None,
        },
    ])

    data = pptx_extraction.extract_pptx(
        str(path), ocr_fn=lambda _blobs: next(outcomes),
    )["per_slide_visual"][0]
    channel = next(
        item
        for item in data["text_channels"]
        if item["channel"] == "picture_ocr"
    )

    assert channel["status"] == "partial"
    assert channel["reason"] == "partial_ocr_results"
    assert channel["text"] == "LEFT LABEL | RIGHT LAB3L"
    assert channel["result_confidence"] == pytest.approx(62.75)
    receipts = channel["ocr_receipts"]
    assert len(receipts) == 2
    assert [receipt["result_status"] for receipt in receipts] == [
        "text_recovered",
        "low_confidence_text",
    ]
    assert [receipt["part_name"] for receipt in receipts] == [
        "ppt/media/image1.png",
        "ppt/media/image2.png",
    ]
    assert all(len(receipt["asset_sha256"]) == 64 for receipt in receipts)
    assert receipts[0]["asset_sha256"] != receipts[1]["asset_sha256"]
    assert all(receipt["shape_path"] for receipt in receipts)
    assert receipts[1]["recovered_text"] == "RIGHT LAB3L"
    assert receipts[1]["trustworthy_text"] is False


def test_genuine_empty_ocr_is_distinct_from_asset_failure(
    pptx_extraction, tmp_path,
):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for index in range(2):
        slide.shapes.add_picture(
            _png(tmp_path / f"asset-{index}.png", w=16 + index),
            int(prs.slide_width * index / 2),
            0,
            width=int(prs.slide_width / 2),
            height=prs.slide_height,
        )
    path = tmp_path / "empty-vs-failure.pptx"
    prs.save(path)
    outcomes = iter([
        {
            "engine": "fixture-ocr",
            "engine_version": "1.0",
            "result_status": "genuine_empty",
            "result_confidence": None,
            "recovered_text": "",
            "trustworthy_text": False,
            "error": None,
        },
        {
            "engine": "fixture-ocr",
            "engine_version": "1.0",
            "result_status": "failed",
            "result_confidence": None,
            "recovered_text": "",
            "trustworthy_text": False,
            "error": "engine_error: synthetic failure",
        },
    ])

    data = pptx_extraction.extract_pptx(
        str(path), ocr_fn=lambda _blobs: next(outcomes),
    )["per_slide_visual"][0]
    channel = next(
        item
        for item in data["text_channels"]
        if item["channel"] == "picture_ocr"
    )

    assert channel["text"] == ""
    assert channel["status"] == "failed"
    assert [item["result_status"] for item in channel["ocr_receipts"]] == [
        "genuine_empty",
        "failed",
    ]
    assert channel["ocr_receipts"][0]["error"] is None
    assert "synthetic failure" in channel["ocr_receipts"][1]["error"]


def test_truncated_picture_is_one_failed_receipt_not_a_deck_abort(
    pptx_extraction,
    monkeypatch,
    tmp_path,
):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(
        _png(tmp_path / "healthy.png", w=64),
        0,
        0,
        width=int(prs.slide_width / 2),
        height=prs.slide_height,
    )
    slide.shapes.add_picture(
        _png(tmp_path / "truncated.png", w=65),
        int(prs.slide_width / 2),
        0,
        width=int(prs.slide_width / 2),
        height=prs.slide_height,
    )
    path = tmp_path / "mixed-assets.pptx"
    prs.save(path)
    source = io.BytesIO(path.read_bytes())
    rewritten = io.BytesIO()
    with (
        zipfile.ZipFile(source) as archive,
        zipfile.ZipFile(rewritten, "w") as destination,
    ):
        for member in archive.infolist():
            payload = archive.read(member)
            if member.filename == "ppt/media/image2.png":
                payload = payload[:40]
            destination.writestr(member, payload)
    path.write_bytes(rewritten.getvalue())

    class FakeTesseractError(Exception):
        pass

    def image_to_data(image, *, output_type):
        assert output_type == "DICT"
        image.load()
        return {"text": ["HEALTHY"], "conf": ["93"]}

    fake_pytesseract = SimpleNamespace(
        Output=SimpleNamespace(DICT="DICT"),
        TesseractNotFoundError=FakeTesseractError,
        TesseractError=FakeTesseractError,
        image_to_data=image_to_data,
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)
    monkeypatch.setattr(pptx_extraction, "_tesseract_available", True)
    monkeypatch.setattr(pptx_extraction, "_tesseract_version", "fixture-1")

    data = pptx_extraction.extract_pptx(path)["per_slide_visual"][0]
    channel = next(
        item
        for item in data["text_channels"]
        if item["channel"] == "picture_ocr"
    )

    assert channel["status"] == "partial"
    assert channel["text"] == "HEALTHY"
    assert [item["result_status"] for item in channel["ocr_receipts"]] == [
        "text_recovered",
        "failed",
    ]
    assert [item["part_name"] for item in channel["ocr_receipts"]] == [
        "ppt/media/image1.png",
        "ppt/media/image2.png",
    ]
    failed = channel["ocr_receipts"][1]
    assert failed["attempted"] is True
    assert failed["trustworthy_text"] is False
    assert failed["error"].startswith("image_decode_error:")
    assert "/" not in failed["error"]


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
    channel = next(
        item
        for item in data["text_channels"]
        if item["channel"] == "picture_ocr"
    )
    assert channel["status"] == "skipped"
    assert channel["ocr_receipts"][0]["attempted"] is False
    assert channel["ocr_receipts"][0]["result_status"] == "skipped"
    assert channel["ocr_receipts"][0]["part_name"] == "ppt/media/image1.png"


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
    channel = next(
        item
        for item in data["text_channels"]
        if item["channel"] == "picture_ocr"
    )
    assert channel["attempted"] is False
    assert channel["engine"] == "tesseract"
    assert channel["engine_version"] is None
    assert channel["status"] == "unavailable"
    assert channel["reason"] == "ocr_engine_unavailable"
    assert channel["ocr_receipts"][0]["attempted"] is False


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
    channel = next(
        item
        for item in data["text_channels"]
        if item["channel"] == "background_image_ocr"
    )
    assert channel["attempted"] is False
    assert channel["engine"] == "tesseract"
    assert channel["engine_version"] is None
    assert channel["status"] == "unavailable"
    assert channel["reason"] == "no_readable_asset"
    assert channel["ocr_receipts"] == []
    assert data["render_required"] is True


def test_ocr_text_capped(pptx_extraction, monkeypatch):
    monkeypatch.setattr(
        pptx_extraction, "ocr_image_bytes", lambda blob: "A" * 9000,
    )
    out = pptx_extraction.ocr_picture_blobs([b"x"])
    assert len(out) == pptx_extraction._OCR_TEXT_MAX_CHARS


@pytest.mark.parametrize(
    "injected",
    [
        "A" * 9000,
        {
            "engine": "fixture",
            "engine_version": "1",
            "result_status": "text_recovered",
            "result_confidence": 90.0,
            "recovered_text": "A" * 9000,
            "trustworthy_text": True,
            "error": None,
        },
    ],
)
def test_each_ocr_receipt_text_is_capped(pptx_extraction, injected):
    slide_data = {
        "text_channels": [],
        "ocr_text": "",
        "text_extraction_method": "shapes",
    }
    pptx_extraction._run_ocr_channel(
        slide_data,
        [{
            "blob": b"exact-asset",
            "shape_path": ["Picture 1"],
            "part_name": "ppt/media/image1.png",
        }],
        channel="picture_ocr",
        provenance={"source": "embedded_picture_blobs"},
        ocr_fn=lambda _blobs: injected,
    )
    receipt = slide_data["text_channels"][0]["ocr_receipts"][0]
    assert len(receipt["recovered_text"]) == pptx_extraction._OCR_TEXT_MAX_CHARS
    assert len(slide_data["ocr_text"]) == pptx_extraction._OCR_TEXT_MAX_CHARS


def test_untrustworthy_recovered_receipt_keeps_channel_partial(pptx_extraction):
    slide_data = {
        "text_channels": [],
        "ocr_text": "",
        "text_extraction_method": "shapes",
    }
    pptx_extraction._run_ocr_channel(
        slide_data,
        [{
            "blob": b"exact-asset",
            "shape_path": ["Picture 1"],
            "part_name": "ppt/media/image1.png",
        }],
        channel="picture_ocr",
        provenance={"source": "embedded_picture_blobs"},
        ocr_fn=lambda _blobs: {
            "engine": "fixture",
            "engine_version": "1",
            "result_status": "text_recovered",
            "result_confidence": 10.0,
            "recovered_text": "UNCERTAIN",
            "trustworthy_text": False,
            "error": None,
        },
    )
    channel = slide_data["text_channels"][0]
    assert channel["text"] == "UNCERTAIN"
    assert channel["status"] == "partial"
    assert channel["reason"] == "partial_ocr_results"


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
    _append_timing_xml(slide, "<p:animEffect/>")
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
    assert data["native_timing"]["animation_behavior_counts"]["effect"] == 1
    assert data["text_extraction_confidence"] == "low"
    assert "corrupt_embedded_asset" in data["render_required_reasons"]
    assert any(
        item["content_type"] == "corrupt_embedded_asset"
        for item in data["unsupported_content"]
    )
    channel = next(
        item
        for item in data["text_channels"]
        if item["channel"] == "picture_ocr"
    )
    assert channel["attempted"] is False
    assert channel["status"] == "unavailable"
    assert channel["reason"] == "no_readable_asset"
    assert channel["ocr_receipts"] == []
    assert data["render_required"] is True


# ── native timing/build structure (issue #151) ──────────────────────


def _append_timing_xml(slide, behavior_xml):
    """Append a synthetic but package-native PresentationML timing tree."""
    timing = parse_xml(
        f'<p:timing {nsdecls("p")}>'
        '<p:tnLst><p:par><p:cTn id="1"><p:childTnLst>'
        f'{behavior_xml}'
        '</p:childTnLst></p:cTn></p:par></p:tnLst>'
        '</p:timing>'
    )
    slide.element.append(timing)


def _append_transition_xml(slide):
    slide.element.append(parse_xml(
        f'<p:transition {nsdecls("p")}><p:fade/></p:transition>'
    ))


def _append_build_list_xml(slide):
    """Append real PresentationML build entries without inferring playback."""
    timing = slide.element.xpath("./p:timing")[0]
    timing.append(parse_xml(
        f'<p:bldLst {nsdecls("p")}>'
        '<p:bldP spid="2" grpId="0"/>'
        '<p:bldDgm spid="3" grpId="1"/>'
        '<p:bldOleChart spid="4" grpId="2"/>'
        '<p:bldGraphic spid="5" grpId="3"/>'
        '</p:bldLst>'
    ))


def test_native_timing_categories_and_deck_totals_stay_distinct(
        pptx_extraction, tmp_path):
    prs = Presentation()
    animated = prs.slides.add_slide(prs.slide_layouts[6])
    _append_transition_xml(animated)
    _append_timing_xml(animated, (
        '<p:set><p:cBhvr><p:cTn id="2"/><p:attrNameLst>'
        '<p:attrName>style.visibility</p:attrName>'
        '</p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        '<p:set><p:cBhvr><p:cTn id="3"/><p:attrNameLst>'
        '<p:attrName>style.opacity</p:attrName>'
        '</p:attrNameLst></p:cBhvr><p:to><p:fltVal val="1"/></p:to></p:set>'
        '<p:anim/><p:animClr/><p:animEffect/><p:animEffect/>'
        '<p:animMotion/><p:animRot/><p:animScale/>'
        '<p:audio><p:cMediaNode><p:cTn id="4"/></p:cMediaNode></p:audio>'
        '<p:video><p:cMediaNode><p:cTn id="5"/></p:cMediaNode></p:video>'
    ))
    _append_build_list_xml(animated)

    media_only = prs.slides.add_slide(prs.slide_layouts[6])
    _append_timing_xml(media_only, (
        '<p:audio><p:cMediaNode><p:cTn id="6"/></p:cMediaNode></p:audio>'
    ))

    transition_only = prs.slides.add_slide(prs.slide_layouts[6])
    _append_transition_xml(transition_only)

    path = tmp_path / "timing-structure.pptx"
    prs.save(path)
    result = pptx_extraction.extract_pptx(str(path), ocr=False)
    slides = result["per_slide_visual"]

    first = slides[0]["native_timing"]
    assert first["timing_element_present"] is True
    assert first["timing_element_count"] == 1
    assert first["transition_count"] == 1
    assert first["set_action_count"] == 2
    assert first["visibility_set_action_count"] == 1
    assert first["animation_behavior_counts"] == {
        "general": 1,
        "color": 1,
        "effect": 2,
        "motion": 1,
        "rotation": 1,
        "scale": 1,
        "total": 7,
    }
    assert first["media_timing_counts"] == {
        "audio": 1, "video": 1, "total": 2}
    assert first["build_list_present"] is True
    assert first["build_list_count"] == 1
    assert first["build_entry_counts"] == {
        "paragraph": 1,
        "diagram": 1,
        "ole_chart": 1,
        "graphic": 1,
        "total": 4,
    }
    assert first["has_build_entries"] is True
    assert first["has_animation_behaviors"] is True
    assert first["has_media_timing"] is True
    assert first["provenance"] == {
        "source": "pptx_package_xml",
        "measurement": "raw_ooxml_element_counts",
        "observed_playback": False,
        "part_name": "ppt/slides/slide1.xml",
    }

    # A timing container carrying only embedded-media timing is not generic
    # animation and especially not a motion observation.
    second = slides[1]["native_timing"]
    assert second["timing_element_present"] is True
    assert second["has_animation_behaviors"] is False
    assert second["animation_behavior_counts"]["motion"] == 0
    assert second["animation_behavior_counts"]["total"] == 0
    assert second["has_media_timing"] is True
    assert second["media_timing_counts"] == {
        "audio": 1, "video": 0, "total": 1}
    assert second["build_list_present"] is False
    assert second["build_list_count"] == 0
    assert second["build_entry_counts"] == {
        "paragraph": 0,
        "diagram": 0,
        "ole_chart": 0,
        "graphic": 0,
        "total": 0,
    }
    assert second["has_build_entries"] is False

    third = slides[2]["native_timing"]
    assert third["timing_element_present"] is False
    assert third["transition_count"] == 1
    assert third["has_animation_behaviors"] is False
    assert third["has_media_timing"] is False

    assert result["native_timing_summary"] == {
        "slides_with_timing_elements": 2,
        "slides_with_transitions": 2,
        "slides_with_animation_behaviors": 1,
        "slides_with_media_timing": 2,
        "slides_with_build_lists": 1,
        "slides_with_build_entries": 1,
        "timing_element_count": 2,
        "transition_count": 2,
        "set_action_count": 2,
        "visibility_set_action_count": 1,
        "build_list_count": 1,
        "animation_behavior_counts": {
            "general": 1,
            "color": 1,
            "effect": 2,
            "motion": 1,
            "rotation": 1,
            "scale": 1,
            "total": 7,
        },
        "media_timing_counts": {"audio": 2, "video": 1, "total": 3},
        "build_entry_counts": {
            "paragraph": 1,
            "diagram": 1,
            "ole_chart": 1,
            "graphic": 1,
            "total": 4,
        },
        "provenance": {
            "source": "pptx_package_xml",
            "measurement": "raw_ooxml_element_counts",
            "observed_playback": False,
        },
    }


def test_adjacent_static_progressive_builds_do_not_invent_native_timing(
        pptx_extraction, tmp_path):
    """Duplicate-slide builds stay visible states, not inferred animation."""
    prs = Presentation()
    first = prs.slides.add_slide(prs.slide_layouts[6])
    first.shapes.add_textbox(
        Inches(1), Inches(1), Inches(5), Inches(1)).text_frame.text = "Base diagram"
    second = prs.slides.add_slide(prs.slide_layouts[6])
    second.shapes.add_textbox(
        Inches(1), Inches(1), Inches(5), Inches(1)).text_frame.text = "Base diagram"
    second.shapes.add_textbox(
        Inches(1), Inches(2), Inches(5), Inches(1)).text_frame.text = "Step 2 annotation"
    path = tmp_path / "static-progressive-build.pptx"
    prs.save(path)

    result = pptx_extraction.extract_pptx(str(path), ocr=False)

    assert "Base diagram" in result["per_slide_visual"][0]["text_content_preview"]
    assert "Step 2 annotation" in \
        result["per_slide_visual"][1]["text_content_preview"]
    assert all(
        not slide["native_timing"]["timing_element_present"]
        for slide in result["per_slide_visual"]
    )
    assert result["native_timing_summary"]["animation_behavior_counts"]["total"] == 0
    assert result["native_timing_summary"]["media_timing_counts"]["total"] == 0
    assert all(
        slide["native_timing"]["build_list_present"] is False
        and slide["native_timing"]["build_entry_counts"]["total"] == 0
        for slide in result["per_slide_visual"]
    )
    assert result["native_timing_summary"]["build_entry_counts"]["total"] == 0


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

    assert pptx_extraction.SCHEMA_VERSION == 3
    assert pptx_extraction.PIPELINE_VERSION == "1.2.0"
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
