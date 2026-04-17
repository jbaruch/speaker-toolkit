"""Tests for generate-illustrations.py — outline parsing and slide selection (no API calls)."""

import os

SAMPLE_OUTLINE = """\
# Illustration Plan

**Model:** `gemini-3-pro-image-preview`

### STYLE ANCHOR (WIDE — 16:9, 1920x1080)
> A warm watercolor illustration with soft edges and muted earth tones.
> Characters rendered in a loose, sketchy style with visible brushstrokes.

---

### Slide 2: The Problem
- Format: **WIDE**
- Image prompt: `[STYLE ANCHOR] A confused developer staring at a tangled web of microservices`
- Builds: 3 steps
  - build-01: Show only the developer
  - build-02: Add the first few microservices
  - build-03: [FULL] Complete tangled web

### Slide 5: The Solution
- Format: **WIDE**
- Image prompt: `[STYLE ANCHOR] A clean architecture diagram with clear boundaries`

### Slide 9: Demo
- Format: **WIDE**
- Image prompt: `A terminal showing green test output`
"""


def test_parse_model(generate_illustrations):
    outline = generate_illustrations.parse_outline.__wrapped__(SAMPLE_OUTLINE) \
        if hasattr(generate_illustrations.parse_outline, '__wrapped__') else None

    # parse_outline takes a file path, so write to a temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(SAMPLE_OUTLINE)
        f.flush()
        result = generate_illustrations.parse_outline(f.name)
    os.unlink(f.name)

    assert result["model"] == "gemini-3-pro-image-preview"


def test_parse_anchors(generate_illustrations):
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(SAMPLE_OUTLINE)
        f.flush()
        result = generate_illustrations.parse_outline(f.name)
    os.unlink(f.name)

    assert "WIDE" in result["anchors"]
    assert "watercolor" in result["anchors"]["WIDE"]


def test_parse_slides(generate_illustrations):
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(SAMPLE_OUTLINE)
        f.flush()
        result = generate_illustrations.parse_outline(f.name)
    os.unlink(f.name)

    nums = [s["slide_num"] for s in result["slides"]]
    assert nums == [2, 5, 9]


def test_parse_builds(generate_illustrations):
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(SAMPLE_OUTLINE)
        f.flush()
        result = generate_illustrations.parse_outline(f.name)
    os.unlink(f.name)

    slide2 = next(s for s in result["slides"] if s["slide_num"] == 2)
    assert "builds" in slide2
    assert slide2["builds"]["count"] == 3
    assert slide2["builds"]["steps"][-1]["is_full"] is True


def test_resolve_prompt_with_anchor(generate_illustrations):
    anchors = {"WIDE": "A warm watercolor illustration."}
    prompt = "[STYLE ANCHOR] A confused developer"
    resolved = generate_illustrations.resolve_prompt(prompt, "WIDE", anchors)
    assert "watercolor" in resolved
    assert "[STYLE ANCHOR]" not in resolved


def test_resolve_prompt_without_anchor_token(generate_illustrations):
    anchors = {"WIDE": "A warm watercolor illustration."}
    prompt = "A terminal showing output"
    resolved = generate_illustrations.resolve_prompt(prompt, "WIDE", anchors)
    assert resolved == prompt


def test_resolve_prompt_missing_anchor(generate_illustrations):
    prompt = "[STYLE ANCHOR] Something"
    resolved = generate_illustrations.resolve_prompt(prompt, "TALL", {})
    assert "[STYLE ANCHOR]" not in resolved


def test_slide_selection_all(generate_illustrations, tmp_path):
    slides = [{"slide_num": 2}, {"slide_num": 5}, {"slide_num": 9}]
    result = generate_illustrations.parse_slide_selection(["all"], slides, str(tmp_path))
    assert result == [2, 5, 9]


def test_slide_selection_explicit(generate_illustrations, tmp_path):
    slides = [{"slide_num": 2}, {"slide_num": 5}, {"slide_num": 9}]
    result = generate_illustrations.parse_slide_selection(["2", "9"], slides, str(tmp_path))
    assert result == [2, 9]


def test_slide_selection_range(generate_illustrations, tmp_path):
    slides = [{"slide_num": n} for n in range(1, 11)]
    result = generate_illustrations.parse_slide_selection(["2-5"], slides, str(tmp_path))
    assert result == [2, 3, 4, 5]


def test_slide_selection_remaining(generate_illustrations, tmp_path):
    slides = [{"slide_num": 2}, {"slide_num": 5}, {"slide_num": 9}]
    # Create a fake existing image for slide 5
    (tmp_path / "slide-05.png").write_bytes(b"fake")
    result = generate_illustrations.parse_slide_selection(["remaining"], slides, str(tmp_path))
    assert 5 not in result
    assert 2 in result
    assert 9 in result


def test_versioning_helpers(generate_illustrations, tmp_path):
    # No existing versions → next_version returns 2
    ver = generate_illustrations.next_version(str(tmp_path), 5)
    assert ver == 2

    # Create a versioned file
    (tmp_path / "slide-05-v2.png").write_bytes(b"fake")
    ver = generate_illustrations.next_version(str(tmp_path), 5)
    assert ver == 3


def test_mime_ext_roundtrip(generate_illustrations):
    assert generate_illustrations.mime_to_ext("image/png") == ".png"
    assert generate_illustrations.mime_to_ext("image/jpeg") == ".jpg"
    assert generate_illustrations.ext_to_mime(".png") == "image/png"
    assert generate_illustrations.ext_to_mime(".jpg") == "image/jpeg"
