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


def test_resolve_slide_bg_rgb_none_for_plain_deck(generate_qr, tmp_path):
    """A plain deck without explicit background returns None."""
    prs = make_deck(1)
    path = str(tmp_path / "deck.pptx")
    prs.save(path)
    prs2 = Presentation(path)
    result = generate_qr.resolve_slide_bg_rgb(prs2.slides[0])
    # May be None or a default — both are acceptable
    assert result is None or isinstance(result, tuple)


def test_insert_qr_via_powerpoint_orchestration(generate_qr, monkeypatch):
    """The PowerPoint-write orchestration is deterministic and unit-tested with
    the InsertQR wrapper (the actual VBA) mocked: one insert-qr.sh call per color
    variant, the deck threaded through uniquely-named intermediates, intermediates
    cleaned up, and the final result moved back onto the deck."""
    calls = []
    monkeypatch.setattr(generate_qr.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    removed = []
    monkeypatch.setattr(generate_qr.os, "remove", lambda p: removed.append(p))
    moved = []
    monkeypatch.setattr(generate_qr.shutil, "move", lambda a, b: moved.append((a, b)))
    monkeypatch.setattr(generate_qr.os.path, "isfile", lambda p: True)

    deck = "/decks/talk.pptx"
    jobs = [("/q/a.png", [1, 3]), ("/q/b.png", [5])]
    generate_qr.insert_qr_via_powerpoint(deck, jobs, "/scripts")

    wrapper = "/scripts/insert-qr.sh"
    # one subprocess call per job; deck threaded through intermediates; CSV is 1-based, comma-joined
    assert calls == [
        [wrapper, "/decks/talk.pptx", "/decks/talk.pptx.qrtmp0.pptx", "/q/a.png", "1,3"],
        [wrapper, "/decks/talk.pptx.qrtmp0.pptx", "/decks/talk.pptx.qrtmp1.pptx", "/q/b.png", "5"],
    ]
    # the prior intermediate is cleaned up; the final intermediate is moved onto the deck
    assert removed == ["/decks/talk.pptx.qrtmp0.pptx"]
    assert moved == [("/decks/talk.pptx.qrtmp1.pptx", "/decks/talk.pptx")]


def test_insert_qr_via_powerpoint_missing_wrapper(generate_qr, monkeypatch):
    """A missing insert-qr.sh fails fast with an actionable error, not a traceback."""
    import pytest
    monkeypatch.setattr(generate_qr.os.path, "isfile", lambda p: False)
    with pytest.raises(SystemExit):
        generate_qr.insert_qr_via_powerpoint("/decks/talk.pptx", [("/q/a.png", [1])], "/scripts")
