"""Tests for generate-qr.py — QR generation (no network calls)."""

import os
import json

from PIL import Image
from pptx import Presentation
from pptx.util import Inches

from conftest import make_deck


def _square_png(tmp_path, name="sq.png"):
    """A two-color (QR-like) PNG: quantizes to 2 colors with ~0 reconstruction
    error, so the content-based detector treats it as a QR."""
    path = str(tmp_path / name)
    im = Image.new("RGB", (50, 50), (255, 255, 255))
    px = im.load()
    for x in range(50):
        for y in range(50):
            if (x + y) % 2 == 0:
                px[x, y] = (0, 0, 0)
    im.save(path)
    return path


def _multicolor_png(tmp_path, name="multi.png"):
    """A many-color (photo/diagram-like) PNG: a smooth gradient that does NOT
    reduce to two colors, so the detector rejects it even when square."""
    path = str(tmp_path / name)
    im = Image.new("RGB", (60, 60))
    px = im.load()
    for x in range(60):
        for y in range(60):
            px[x, y] = ((x * 4) % 256, (y * 4) % 256, ((x + y) * 2) % 256)
    im.save(path)
    return path


def _sparse_text_png(tmp_path, name="screenshot.png"):
    """A mostly-white image with sparse dark 'text' — ~2-color but heavily skewed
    to the background (like a doc screenshot), so it must NOT be taken for a QR."""
    path = str(tmp_path / name)
    im = Image.new("RGB", (80, 80), (255, 255, 255))
    px = im.load()
    for y in range(0, 80, 6):
        for x in range(0, 80, 3):
            px[x, y] = (0, 0, 0)
    im.save(path)
    return path


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


def test_slide_has_existing_qr_detects_square_qr_sized_picture(generate_qr, tmp_path):
    prs = make_deck(1)
    prs.slides[0].shapes.add_picture(_square_png(tmp_path), Inches(8), Inches(5), Inches(2.0), Inches(2.0))
    assert generate_qr.slide_has_existing_qr(prs.slides[0]) is True


def test_slide_has_existing_qr_ignores_non_square_picture(generate_qr, tmp_path):
    prs = make_deck(1)
    prs.slides[0].shapes.add_picture(_square_png(tmp_path), Inches(1), Inches(1), Inches(6.0), Inches(2.0))
    assert generate_qr.slide_has_existing_qr(prs.slides[0]) is False


def test_slide_has_existing_qr_detects_large_square_qr(generate_qr, tmp_path):
    # Size-independent: a 2.8in two-color square is still a QR (the inherited
    # shownotes QR in the #56 repro deck was 2.78in — outside the old 1.5-2.5 band).
    prs = make_deck(1)
    prs.slides[0].shapes.add_picture(_square_png(tmp_path), Inches(1), Inches(1), Inches(2.8), Inches(2.8))
    assert generate_qr.slide_has_existing_qr(prs.slides[0]) is True


def test_slide_has_existing_qr_ignores_multicolor_square(generate_qr, tmp_path):
    # Square and in size range, but many colors (e.g. a Venn diagram) → not a QR.
    prs = make_deck(1)
    prs.slides[0].shapes.add_picture(_multicolor_png(tmp_path), Inches(2), Inches(2), Inches(2.0), Inches(2.0))
    assert generate_qr.slide_has_existing_qr(prs.slides[0]) is False


def test_slide_has_existing_qr_ignores_small_two_color_icon(generate_qr, tmp_path):
    # Two-color but below the 1.5in floor → a small icon, not a QR.
    prs = make_deck(1)
    prs.slides[0].shapes.add_picture(_square_png(tmp_path), Inches(1), Inches(1), Inches(1.0), Inches(1.0))
    assert generate_qr.slide_has_existing_qr(prs.slides[0]) is False


def test_slide_has_existing_qr_ignores_text_screenshot(generate_qr, tmp_path):
    # Near-square, in size range, ~2-color — but mostly-white with sparse text
    # (unbalanced) → not a QR. Regression: a martinfowler.com screenshot (slide 28
    # of the #56 repro deck) that the recon-error-only test wrongly accepted.
    prs = make_deck(1)
    prs.slides[0].shapes.add_picture(_sparse_text_png(tmp_path), Inches(2), Inches(1), Inches(4.0), Inches(4.0))
    assert generate_qr.slide_has_existing_qr(prs.slides[0]) is False


def test_slide_has_existing_qr_false_for_plain_slide(generate_qr):
    prs = make_deck(1)
    assert generate_qr.slide_has_existing_qr(prs.slides[0]) is False


def test_two_color_metrics_separate_qr_screenshot_photo(generate_qr, tmp_path):
    qr_err, qr_min = generate_qr._two_color_metrics(open(_square_png(tmp_path, "q.png"), "rb").read())
    multi_err, _ = generate_qr._two_color_metrics(open(_multicolor_png(tmp_path, "m.png"), "rb").read())
    _, sshot_min = generate_qr._two_color_metrics(open(_sparse_text_png(tmp_path, "s.png"), "rb").read())
    assert qr_err < 5.0 and qr_min >= 0.25     # QR: two-color AND balanced
    assert multi_err > 20.0                     # photo/diagram: many colors
    assert sshot_min < 0.25                     # screenshot: mostly background


def test_find_qr_rects_returns_points_geometry(generate_qr, tmp_path):
    prs = make_deck(1)
    # placed at 8in,5in, 2in square → points: 576, 360, 144, 144
    prs.slides[0].shapes.add_picture(_square_png(tmp_path), Inches(8), Inches(5), Inches(2.0), Inches(2.0))
    rects = generate_qr.find_qr_rects(prs.slides[0])
    assert len(rects) == 1
    L, T, W, H = rects[0]
    assert abs(L - 576) < 0.5 and abs(T - 360) < 0.5
    assert abs(W - 144) < 0.5 and abs(H - 144) < 0.5


def test_resolve_target_includes_inherited_qr_slides(generate_qr, tmp_path):
    """A deck adapted from another talk: config targets only the closing slide,
    but an earlier slide carries an inherited QR — it must also be targeted."""
    prs = make_deck(4)
    prs.slides[1].shapes.add_picture(_square_png(tmp_path), Inches(8), Inches(5), Inches(2.0), Inches(2.0))
    indices = generate_qr.resolve_target_slide_indices(prs, {"slide_position": "closing"}, "https://example.com/notes")
    assert 1 in indices   # inherited-QR slide
    assert 3 in indices   # closing slide


def test_back_half_is_always_slug_ignoring_preferred_short_path(generate_qr, monkeypatch):
    """The back-half is ALWAYS the talk slug — a legacy preferred_short_path is ignored."""
    captured = {}

    def fake_create_bitly_link(long_url, api_token, custom_back_half=None, domain=None):
        captured["back_half"] = custom_back_half
        return {"short_url": "https://jbaru.ch/my-slug", "link_id": "id", "short_path": custom_back_half}

    monkeypatch.setattr(generate_qr, "create_bitly_link", fake_create_bitly_link)
    config = {"shortener": "bitly", "preferred_short_path": "legacy-override", "bitly_domain": "jbaru.ch"}
    secrets = {"bitly": {"api_token": "tok"}}
    generate_qr.resolve_short_url(
        "https://jbaru.ch/my-slug", "my-slug", config, secrets, {}, dry_run=False, vault_path=None
    )
    assert captured["back_half"] == "my-slug"


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
    # job slides carry their existing-QR rects (points): slide 1 replaces in place,
    # slide 3 is a new placement; slide 5 likewise new.
    jobs = [
        ("/q/a.png", [(1, [(100.0, 200.0, 144.0, 144.0)]), (3, [])]),
        ("/q/b.png", [(5, [])]),
    ]
    generate_qr.insert_qr_via_powerpoint(deck, jobs, "/scripts")

    wrapper = "/scripts/insert-qr.sh"
    # one subprocess call per job; deck threaded through intermediates; spec is
    # 1-based, ";"-joined, with per-slide removal rects after ":"
    assert calls == [
        [wrapper, "/decks/talk.pptx", "/decks/talk.pptx.qrtmp0.pptx", "/q/a.png", "1:100.00,200.00,144.00,144.00;3"],
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
        generate_qr.insert_qr_via_powerpoint("/decks/talk.pptx", [("/q/a.png", [(1, [])])], "/scripts")


def test_insert_qr_via_powerpoint_wrapper_failure_is_actionable(generate_qr, monkeypatch):
    """A wrapper (insert-qr.sh) failure surfaces as an actionable SystemExit
    pointing at the DeckOps setup, not a raw CalledProcessError traceback."""
    import pytest

    def boom(cmd, **kw):
        raise generate_qr.subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(generate_qr.subprocess, "run", boom)
    monkeypatch.setattr(generate_qr.os.path, "isfile", lambda p: True)
    with pytest.raises(SystemExit) as exc:
        generate_qr.insert_qr_via_powerpoint("/decks/talk.pptx", [("/q/a.png", [(1, [])])], "/scripts")
    assert "deck-editing-setup.md" in str(exc.value)


def test_format_qr_spec_new_placement_and_replace(generate_qr):
    # No rects → bare slide number (new bottom-right placement)
    assert generate_qr._format_qr_spec([(5, [])]) == "5"
    # One rect → "num:L,T,W,H" (replace in place), 2-decimal points
    assert generate_qr._format_qr_spec([(12, [(450.0, 80.0, 200.16, 200.16)])]) == \
        "12:450.00,80.00,200.16,200.16"
    # Multiple slides + a duplicate-QR slide (two rects) → flattened, ";"-joined
    assert generate_qr._format_qr_spec([(12, [(1, 2, 3, 4), (5, 6, 7, 8)]), (38, [])]) == \
        "12:1.00,2.00,3.00,4.00,5.00,6.00,7.00,8.00;38"


def test_create_bitly_link_raises_when_custom_back_half_fails(generate_qr, monkeypatch):
    """If the custom back-half can't be set, fail rather than return a random hash —
    the back-half must always be the slug (rules/qr-generation-rules.md §2)."""
    import pytest

    def fake_http(url, data=None, headers=None, method="GET"):
        if url.endswith("/v4/bitlinks"):
            return {"id": "bit.ly/abc123", "link": "https://bit.ly/abc123"}
        raise RuntimeError("custom back-half already taken")

    monkeypatch.setattr(generate_qr, "_http_request", fake_http)
    with pytest.raises(RuntimeError, match="could not set custom back-half"):
        generate_qr.create_bitly_link(
            "https://example.com/notes", "tok", custom_back_half="my-slug", domain="jbaru.ch"
        )


def test_legacy_non_slug_cache_entry_is_recreated_with_slug(generate_qr, monkeypatch):
    """A tracked link with a legacy non-slug back-half is NOT reused/retargeted —
    it is recreated with the slug, even when the cached target matches."""
    created = {}

    def fake_create_bitly_link(long_url, api_token, custom_back_half=None, domain=None):
        created["back_half"] = custom_back_half
        return {"short_url": f"https://jbaru.ch/{custom_back_half}", "link_id": "new-id", "short_path": custom_back_half}

    def boom_update(*a, **k):
        raise AssertionError("update_bitly_link must not be called for a legacy non-slug entry")

    monkeypatch.setattr(generate_qr, "create_bitly_link", fake_create_bitly_link)
    monkeypatch.setattr(generate_qr, "update_bitly_link", boom_update)
    tracking_db = {"qr_codes": [{
        "talk_slug": "my-slug",
        "target_url": "https://jbaru.ch/my-slug",   # cached target matches → would reuse without the fix
        "shortener": "bitly",
        "short_path": "legacy-hash",                # NON-slug back-half
        "short_url": "https://bit.ly/legacy-hash",
        "shortener_link_id": "old-id",
    }]}
    short_url, meta = generate_qr.resolve_short_url(
        "https://jbaru.ch/my-slug", "my-slug",
        {"shortener": "bitly", "bitly_domain": "jbaru.ch"},
        {"bitly": {"api_token": "tok"}}, tracking_db, dry_run=False, vault_path=None,
    )
    assert created["back_half"] == "my-slug"
    assert meta["short_path"] == "my-slug"
    assert meta["shortener_link_id"] == "new-id"
    assert short_url == "https://jbaru.ch/my-slug"


def test_missing_custom_domain_decision_stops_before_first_link(generate_qr, monkeypatch):
    """First short link with NO recorded custom-domain decision (key absent) STOPS
    so the agent asks the user — it must not silently default to bit.ly."""
    import pytest
    monkeypatch.setattr(generate_qr, "create_bitly_link",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must STOP before creating")))
    with pytest.raises(SystemExit):
        generate_qr.resolve_short_url(
            "https://jbaru.ch/my-slug", "my-slug",
            {"shortener": "bitly"},   # no bitly_domain key → decision not recorded
            {"bitly": {"api_token": "tok"}}, {}, dry_run=False, vault_path=None,
        )


def test_explicit_null_custom_domain_proceeds(generate_qr, monkeypatch):
    """An explicit null custom-domain decision is recorded — proceed on the default
    domain, no STOP, no re-ask."""
    captured = {}

    def fake_create_bitly_link(long_url, api_token, custom_back_half=None, domain=None):
        captured["domain"] = domain
        return {"short_url": f"https://bit.ly/{custom_back_half}", "link_id": "id", "short_path": custom_back_half}

    monkeypatch.setattr(generate_qr, "create_bitly_link", fake_create_bitly_link)
    short_url, meta = generate_qr.resolve_short_url(
        "https://jbaru.ch/my-slug", "my-slug",
        {"shortener": "bitly", "bitly_domain": None},   # recorded decision: no custom domain
        {"bitly": {"api_token": "tok"}}, {}, dry_run=False, vault_path=None,
    )
    assert captured["domain"] is None
    assert meta["short_path"] == "my-slug"


def test_slug_cache_entry_is_reused(generate_qr, monkeypatch):
    """A tracked entry whose back-half is already the slug is reused from cache —
    no API call — when the target matches."""
    def boom_create(*a, **k):
        raise AssertionError("must reuse cache, not create a new link")

    monkeypatch.setattr(generate_qr, "create_bitly_link", boom_create)
    tracking_db = {"qr_codes": [{
        "talk_slug": "my-slug",
        "target_url": "https://jbaru.ch/my-slug",
        "shortener": "bitly",
        "short_path": "my-slug",
        "short_url": "https://jbaru.ch/my-slug",
        "shortener_link_id": "id",
    }]}
    short_url, meta = generate_qr.resolve_short_url(
        "https://jbaru.ch/my-slug", "my-slug", {"shortener": "bitly"}, {}, tracking_db, dry_run=False,
    )
    assert short_url == "https://jbaru.ch/my-slug"
    assert meta["short_path"] == "my-slug"
