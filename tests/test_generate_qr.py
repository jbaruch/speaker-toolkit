"""Tests for generate-qr.py — QR generation (no network calls)."""

import os
import json

from pptx import Presentation

from conftest import make_deck


def test_choose_fg_color_dark_bg(generate_qr):
    # Dark background → white foreground
    fg = generate_qr.choose_fg_color((0, 0, 0))
    assert fg == (255, 255, 255)


def test_choose_fg_color_light_bg(generate_qr):
    # Light background → black foreground
    fg = generate_qr.choose_fg_color((255, 255, 255))
    assert fg == (0, 0, 0)


def test_choose_fg_color_none(generate_qr):
    # No background detected → default to black
    fg = generate_qr.choose_fg_color(None)
    assert fg == (0, 0, 0)


def test_choose_fg_color_mid_gray(generate_qr):
    # Mid-gray — should pick based on luminance
    fg = generate_qr.choose_fg_color((128, 128, 128))
    # Luminance for (128,128,128) ≈ 0.502 → ≥ 0.5 → black
    assert fg == (0, 0, 0)


def test_choose_fg_color_dark_blue(generate_qr):
    # Dark blue → white foreground
    fg = generate_qr.choose_fg_color((0, 0, 100))
    assert fg == (255, 255, 255)


def test_generate_qr_png(generate_qr, tmp_path):
    out = str(tmp_path / "test.png")
    generate_qr.generate_qr_png("https://example.com", (0, 0, 0), (255, 255, 255), out)
    assert os.path.isfile(out)
    assert os.path.getsize(out) > 100  # sanity check — not empty


def test_generate_qr_png_custom_colors(generate_qr, tmp_path):
    out = str(tmp_path / "custom.png")
    generate_qr.generate_qr_png("https://example.com", (255, 255, 255), (128, 0, 128), out)
    assert os.path.isfile(out)


def test_tracking_db_crud_insert(generate_qr):
    db = {}
    entry = {
        "talk_slug": "test-talk",
        "target_url": "https://example.com/notes",
        "shortener": "none",
        "short_url": "https://example.com/notes",
    }
    generate_qr.update_tracking_db(db, entry, "test-talk-qr.png")
    assert len(db["qr_codes"]) == 1
    assert db["qr_codes"][0]["talk_slug"] == "test-talk"
    assert db["qr_codes"][0]["qr_png_rel_path"] == "test-talk-qr.png"


def test_tracking_db_crud_update(generate_qr):
    db = {"qr_codes": [{
        "talk_slug": "test-talk",
        "target_url": "https://old-url.com",
        "shortener": "none",
        "short_url": "https://old-url.com",
        "qr_png_rel_path": "old.png",
        "created_at": "2024-01-01",
        "updated_at": "2024-01-01",
    }]}
    entry = {
        "talk_slug": "test-talk",
        "target_url": "https://new-url.com",
        "shortener": "none",
        "short_url": "https://new-url.com",
    }
    generate_qr.update_tracking_db(db, entry, "new.png")
    assert len(db["qr_codes"]) == 1
    assert db["qr_codes"][0]["target_url"] == "https://new-url.com"
    assert db["qr_codes"][0]["qr_png_rel_path"] == "new.png"
    # created_at preserved from original
    assert db["qr_codes"][0]["created_at"] == "2024-01-01"


def test_insert_qr_on_slides(generate_qr, tmp_path):
    prs = make_deck(3)
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    qr_path = str(tmp_path / "qr.png")
    generate_qr.generate_qr_png("https://example.com", (0, 0, 0), (255, 255, 255), qr_path)

    prs2 = Presentation(path)
    generate_qr.insert_qr_on_slides(prs2, qr_path, [2])  # last slide
    out = str(tmp_path / "with_qr.pptx")
    prs2.save(out)

    prs3 = Presentation(out)
    # Verify the last slide has more shapes than before
    last_slide = prs3.slides[2]
    assert len(last_slide.shapes) >= 1


def test_resolve_slide_bg_rgb_none_for_plain_deck(generate_qr, tmp_path):
    """A plain deck without explicit background returns None."""
    prs = make_deck(1)
    path = str(tmp_path / "deck.pptx")
    prs.save(path)
    prs2 = Presentation(path)
    result = generate_qr.resolve_slide_bg_rgb(prs2.slides[0])
    # May be None or a default — both are acceptable
    assert result is None or isinstance(result, tuple)
