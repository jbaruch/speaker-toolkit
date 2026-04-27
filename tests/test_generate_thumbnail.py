"""Tests for generate-thumbnail.py — prompt building and image validation (no API calls)."""

from io import BytesIO

from PIL import Image


def test_build_prompt_default(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt("JUDGMENT DAY")
    assert "JUDGMENT DAY" in prompt
    assert "slide_dominant" in prompt or "fills most of the frame" in prompt
    assert "1280x720" in prompt


def test_build_prompt_with_subtitle(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt("Test", subtitle="DevNexus 2026")
    assert "DevNexus 2026" in prompt


def test_build_prompt_split_panel_style(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt("Title", style="split_panel")
    assert "Left half" in prompt or "split" in prompt.lower()


def test_build_prompt_overlay_style(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt("Title", style="overlay")
    assert "cutout" in prompt.lower() or "overlay" in prompt.lower()


def test_build_prompt_brand_colors(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt(
        "Title", brand_colors=["#5B2C6F", "#C0392B"]
    )
    assert "#5B2C6F" in prompt
    assert "#C0392B" in prompt


def test_build_prompt_title_position(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt("Title", title_position="bottom")
    assert "bottom third" in prompt


def test_validate_and_resize_correct_dimensions(generate_thumbnail):
    # Create a 1280x720 image
    img = Image.new("RGB", (1280, 720), (255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    result_bytes, mime = generate_thumbnail.validate_and_resize(image_bytes, "image/png")
    result_img = Image.open(BytesIO(result_bytes))
    assert result_img.size == (1280, 720)


def test_validate_and_resize_rescales(generate_thumbnail):
    # Create a non-standard sized image
    img = Image.new("RGB", (800, 600), (0, 255, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    result_bytes, mime = generate_thumbnail.validate_and_resize(image_bytes, "image/png")
    result_img = Image.open(BytesIO(result_bytes))
    assert result_img.size == (1280, 720)


def test_validate_and_resize_size_limit(generate_thumbnail):
    result_bytes, mime = generate_thumbnail.validate_and_resize(
        _make_large_image_bytes(), "image/png"
    )
    assert len(result_bytes) <= 2 * 1024 * 1024


def test_validate_and_resize_rgba_to_rgb(generate_thumbnail):
    img = Image.new("RGBA", (1280, 720), (255, 0, 0, 128))
    buf = BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    result_bytes, mime = generate_thumbnail.validate_and_resize(image_bytes, "image/png")
    result_img = Image.open(BytesIO(result_bytes))
    assert result_img.mode == "RGB"


# --- Issue #19: softening + safety-filter avoidance ---


def test_default_prompt_drops_assertive_face_preservation(generate_thumbnail):
    """Regression for #19: the phrases that trip Gemini's safety filter must not
    appear in any softness level of the default prompt.

    The filter reliably rejects the pairing of 'maintain exact facial features /
    bone structure / skin texture' with viral-styling demands. We frame the
    request as graphic composition instead.
    """
    forbidden = [
        "exact facial features",
        "bone structure",
        "skin texture",
        # "High visual energy" + "competes against hundreds of others" was the
        # second half of the trigger pair.
        "competes against hundreds",
    ]
    for softness in ("default", "softer", "softest"):
        prompt = generate_thumbnail.build_thumbnail_prompt(
            "JUDGMENT DAY", softness=softness
        )
        for phrase in forbidden:
            assert phrase.lower() not in prompt.lower(), (
                f"softness={softness!r}: forbidden phrase {phrase!r} present"
            )


def test_softness_levels_are_monotonic(generate_thumbnail):
    """softest <= softer <= default in length — retries progressively shorten."""
    default = generate_thumbnail.build_thumbnail_prompt("T", softness="default")
    softer = generate_thumbnail.build_thumbnail_prompt("T", softness="softer")
    softest = generate_thumbnail.build_thumbnail_prompt("T", softness="softest")
    assert len(softest) < len(softer) < len(default)


def test_softest_keeps_core_composition(generate_thumbnail):
    """Softest level must still describe the compositing task so the output
    is usable — not just stripped to uselessness."""
    prompt = generate_thumbnail.build_thumbnail_prompt(
        "JUDGMENT DAY", subtitle="DevNexus 2026", softness="softest"
    )
    assert "1280x720" in prompt
    assert "JUDGMENT DAY" in prompt
    assert "DevNexus 2026" in prompt


def test_brand_colors_carry_through_all_softness_levels(generate_thumbnail):
    """Brand colors are non-visual-filter-triggering metadata; they should
    survive all softness levels so the speaker's color scheme is respected
    even on a retry."""
    for softness in ("default", "softer", "softest"):
        prompt = generate_thumbnail.build_thumbnail_prompt(
            "T", brand_colors=["#5B2C6F", "#C0392B"], softness=softness,
        )
        assert "#5B2C6F" in prompt, f"brand color missing at softness={softness}"
        assert "#C0392B" in prompt, f"brand color missing at softness={softness}"


# --- Issue #23: comic-book aesthetic option ---


def test_aesthetic_default_is_photo(generate_thumbnail):
    """Default aesthetic stays 'photo' until comic-book proves it generalizes."""
    default_prompt = generate_thumbnail.build_thumbnail_prompt("T")
    photo_prompt = generate_thumbnail.build_thumbnail_prompt("T", aesthetic="photo")
    assert default_prompt == photo_prompt


def test_comic_book_prompt_uses_caricature_framing(generate_thumbnail):
    """Comic-book aesthetic must reframe the speaker rendering — caricature,
    not 'natural and unmodified'. The whole point of the option is that
    illustration treatment is acceptable here."""
    prompt = generate_thumbnail.build_thumbnail_prompt(
        "JUDGMENT DAY", aesthetic="comic_book"
    )
    assert "comic-book" in prompt.lower()
    # Caricature/illustration cues should appear:
    assert "caricature" in prompt.lower()
    assert "halftone" in prompt.lower()
    # The photo-aesthetic 'natural and unmodified' clause must NOT appear —
    # otherwise we contradict ourselves.
    assert "natural and unmodified" not in prompt.lower()


def test_comic_book_preserves_identifying_features_language(generate_thumbnail):
    """The speaker still needs to be recognizable in caricature form — the
    prompt must explicitly call out preserving identifying features."""
    prompt = generate_thumbnail.build_thumbnail_prompt(
        "T", aesthetic="comic_book"
    )
    assert "identifying features" in prompt.lower()
    # And we shouldn't fall back to forbidden assertive face-preservation
    # phrases that triggered the safety filter for photo realism (issue #19).
    forbidden = ["exact facial features", "bone structure", "skin texture"]
    for phrase in forbidden:
        assert phrase.lower() not in prompt.lower()


def test_comic_book_softness_levels_monotonic(generate_thumbnail):
    """Softness ladder must shorten progressively for comic-book too — same
    retry contract as photo aesthetic."""
    default = generate_thumbnail.build_thumbnail_prompt(
        "T", aesthetic="comic_book", softness="default"
    )
    softer = generate_thumbnail.build_thumbnail_prompt(
        "T", aesthetic="comic_book", softness="softer"
    )
    softest = generate_thumbnail.build_thumbnail_prompt(
        "T", aesthetic="comic_book", softness="softest"
    )
    assert len(softest) < len(softer) < len(default)


def test_unknown_aesthetic_raises(generate_thumbnail):
    """Unknown aesthetic value should fail loud, not silently fall back."""
    import pytest
    with pytest.raises(ValueError):
        generate_thumbnail.build_thumbnail_prompt("T", aesthetic="watercolor")


def test_unknown_softness_raises(generate_thumbnail):
    """Unknown softness value should fail loud — a typo like 'softrer' must
    not silently produce default-strength output and break the retry ladder
    semantics."""
    import pytest
    with pytest.raises(ValueError):
        generate_thumbnail.build_thumbnail_prompt("T", softness="softrer")


def test_call_gemini_filter_rejection_prefix(generate_thumbnail, monkeypatch):
    """call_gemini must prefix safety-filter rejections with _ERR_FILTER so the
    retry ladder can distinguish them from transport-level failures."""
    class _FakeResp:
        def __init__(self, body):
            self._body = body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return self._body.encode("utf-8")

    # Empty candidates → no image → safety-filter prefix
    monkeypatch.setattr(
        generate_thumbnail.urllib.request,
        "urlopen",
        lambda req, timeout=None: _FakeResp('{"candidates":[]}'),
    )
    image, err = generate_thumbnail.call_gemini([], "model", "key")
    assert image is None
    assert err.startswith(generate_thumbnail._ERR_FILTER), (
        f"expected filter prefix, got: {err}"
    )


def test_call_gemini_http_error_prefix(generate_thumbnail, monkeypatch):
    """HTTP errors must NOT carry the filter prefix — softening won't fix them."""
    import urllib.error
    from io import BytesIO

    def _raise_http(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 429, "Too Many Requests", {}, BytesIO(b"rate limited"),
        )

    monkeypatch.setattr(generate_thumbnail.urllib.request, "urlopen", _raise_http)
    image, err = generate_thumbnail.call_gemini([], "model", "key")
    assert image is None
    assert err.startswith(generate_thumbnail._ERR_HTTP)
    assert not err.startswith(generate_thumbnail._ERR_FILTER)


# --- Issue #31: portrait pre-stylization (two-pass for deck anchors) ---


def test_stylize_portrait_returns_stylized_bytes(generate_thumbnail, monkeypatch):
    """stylize_portrait sends the photo + prompt to Gemini and returns the
    base64-encoded stylized bytes + the response mime type."""
    captured = {}

    def fake_call_gemini(parts, model, api_key):
        captured["parts"] = parts
        return b"STYLIZED_BYTES", "image/png"

    monkeypatch.setattr(generate_thumbnail, "call_gemini", fake_call_gemini)
    b64, mime = generate_thumbnail.stylize_portrait(
        "ORIGINAL_B64", "image/jpeg",
        "retro tech-manual, sepia, pen-and-ink crosshatching",
        "gemini-3-pro-image-preview", "key",
    )
    assert mime == "image/png"
    # Stylized bytes are returned base64-encoded
    import base64
    assert base64.b64decode(b64) == b"STYLIZED_BYTES"
    # The single Gemini call had exactly the photo + a prompt mentioning the anchor
    assert len(captured["parts"]) == 2
    assert captured["parts"][0]["inlineData"]["data"] == "ORIGINAL_B64"
    assert "retro tech-manual" in captured["parts"][1]["text"]
    assert "Preserve identifying features" in captured["parts"][1]["text"]


def test_stylize_portrait_raises_on_filter_rejection(generate_thumbnail, monkeypatch):
    """A filter rejection on the pre-stylize call is unrecoverable here —
    the prompt is already minimal. Surface as a RuntimeError; don't soften."""
    import pytest

    def fake_call_gemini(parts, model, api_key):
        return None, generate_thumbnail._ERR_FILTER + "blocked"

    monkeypatch.setattr(generate_thumbnail, "call_gemini", fake_call_gemini)
    with pytest.raises(RuntimeError) as excinfo:
        generate_thumbnail.stylize_portrait(
            "B64", "image/jpeg", "any anchor", "model", "key",
        )
    assert "Portrait pre-stylization failed" in str(excinfo.value)


def test_stylize_portrait_raises_on_http_error(generate_thumbnail, monkeypatch):
    """HTTP errors are also surfaced as RuntimeError — softening a stylize
    call doesn't help (the prompt has no viral-styling demands to drop)."""
    import pytest

    def fake_call_gemini(parts, model, api_key):
        return None, generate_thumbnail._ERR_HTTP + "429: rate limited"

    monkeypatch.setattr(generate_thumbnail, "call_gemini", fake_call_gemini)
    with pytest.raises(RuntimeError):
        generate_thumbnail.stylize_portrait(
            "B64", "image/jpeg", "any anchor", "model", "key",
        )


def _make_large_image_bytes():
    """Create a large random-ish image that exceeds 2MB as PNG."""
    import random
    random.seed(42)
    img = Image.new("RGB", (1280, 720))
    pixels = img.load()
    for x in range(1280):
        for y in range(720):
            pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
