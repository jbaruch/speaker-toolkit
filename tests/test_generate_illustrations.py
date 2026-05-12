"""Tests for generate-illustrations.py — outline parsing and slide selection (no API calls)."""

import json
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


# --- Safe zone directive tests ---

OUTLINE_WITH_SAFE_ZONE = """\
# Illustration Plan

**Model:** `gemini-3-pro-image-preview`

### STYLE ANCHOR (WIDE — 16:9, 1920x1080)
> A warm watercolor illustration.

---

### Slide 3: The Question
- Format: **WIDE**
- Image prompt: `[STYLE ANCHOR] A confused developer`
- Safe zone: upper_third (painted sky)
- Text: **The Question**

### Slide 7: No Zone
- Format: **WIDE**
- Image prompt: `A terminal output`
"""


def test_parse_safe_zone(generate_illustrations):
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(OUTLINE_WITH_SAFE_ZONE)
        f.flush()
        result = generate_illustrations.parse_outline(f.name)
    os.unlink(f.name)

    slide3 = next(s for s in result["slides"] if s["slide_num"] == 3)
    assert "safe_zone" in slide3
    assert slide3["safe_zone"]["zone"] == "upper_third"
    assert slide3["safe_zone"]["surface"] == "painted sky"


def test_parse_no_safe_zone(generate_illustrations):
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(OUTLINE_WITH_SAFE_ZONE)
        f.flush()
        result = generate_illustrations.parse_outline(f.name)
    os.unlink(f.name)

    slide7 = next(s for s in result["slides"] if s["slide_num"] == 7)
    assert "safe_zone" not in slide7


def test_apply_safe_zone_directive(generate_illustrations):
    prompt = "A confused developer"
    safe_zone = {"zone": "upper_third", "surface": "painted sky"}
    result = generate_illustrations.apply_safe_zone_directive(prompt, safe_zone)
    assert "TITLE SAFE ZONE" in result
    assert "upper third" in result
    assert "painted sky" in result


def test_apply_safe_zone_directive_none(generate_illustrations):
    prompt = "A confused developer"
    result = generate_illustrations.apply_safe_zone_directive(prompt, None)
    assert result == prompt


def test_apply_safe_zone_directive_idempotent(generate_illustrations):
    prompt = "A dev TITLE SAFE ZONE -- old directive here"
    safe_zone = {"zone": "lower_third", "surface": "gradient"}
    result = generate_illustrations.apply_safe_zone_directive(prompt, safe_zone)
    assert result.count("TITLE SAFE ZONE") == 1
    assert "lower third" in result


def test_apply_safe_zone_default_surface(generate_illustrations):
    safe_zone = {"zone": "left_half", "surface": None}
    result = generate_illustrations.apply_safe_zone_directive("A scene", safe_zone)
    assert "TITLE SAFE ZONE" in result
    assert "left half" in result


# --- Model family dispatch ---

def test_model_family_openai(generate_illustrations):
    assert generate_illustrations.model_family("gpt-image-2") == "openai"
    assert generate_illustrations.model_family("gpt-image-1") == "openai"


def test_model_family_imagen(generate_illustrations):
    assert generate_illustrations.model_family("imagen-4.0-ultra-generate-001") == "imagen"
    assert generate_illustrations.model_family("imagen-3.0-generate-002") == "imagen"


def test_model_family_gemini_default(generate_illustrations):
    assert generate_illustrations.model_family("gemini-3-pro-image-preview") == "gemini"
    assert generate_illustrations.model_family("gemini-3.1-flash-image-preview") == "gemini"
    assert generate_illustrations.model_family("nano-banana-pro-preview") == "gemini"
    assert generate_illustrations.model_family("some-unknown-model") == "gemini"


def test_family_key_name(generate_illustrations):
    # Gemini and Imagen both authenticate with the Google AI Studio key
    assert generate_illustrations.family_key_name("gemini") == "gemini"
    assert generate_illustrations.family_key_name("imagen") == "gemini"
    assert generate_illustrations.family_key_name("openai") == "openai"


def test_compare_models_curated_list(generate_illustrations):
    # The freshness check in SKILL.md Step 2 tracks this list — it must
    # contain at least one current-flagship entry per major vendor
    families = {generate_illustrations.model_family(m)
                for m in generate_illustrations.COMPARE_MODELS}
    assert "openai" in families, "COMPARE_MODELS missing OpenAI entry"
    assert "gemini" in families, "COMPARE_MODELS missing Gemini entry"
    assert "imagen" in families, "COMPARE_MODELS missing Imagen entry"


# --- Secrets loading ---

def test_load_secrets_from_file(generate_illustrations, tmp_path, monkeypatch):
    secrets = {"gemini": {"api_key": "g-key"}, "openai": {"api_key": "o-key"}}
    (tmp_path / "secrets.json").write_text(json.dumps(secrets))
    # Block env-var fallback so we're testing file resolution
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    keys, path = generate_illustrations.load_secrets(str(tmp_path))
    assert keys["gemini"] == "g-key"
    assert keys["openai"] == "o-key"
    assert path == str(tmp_path / "secrets.json")


def test_load_secrets_env_fallback(generate_illustrations, tmp_path, monkeypatch):
    # No secrets.json file in this vault
    monkeypatch.setenv("GEMINI_API_KEY", "env-g")
    monkeypatch.setenv("OPENAI_API_KEY", "env-o")
    keys, _ = generate_illustrations.load_secrets(str(tmp_path))
    assert keys["gemini"] == "env-g"
    assert keys["openai"] == "env-o"


def test_load_secrets_partial_file(generate_illustrations, tmp_path, monkeypatch):
    # File has only gemini; openai should fall through to env
    (tmp_path / "secrets.json").write_text(json.dumps({"gemini": {"api_key": "g"}}))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "env-o")
    keys, _ = generate_illustrations.load_secrets(str(tmp_path))
    assert keys["gemini"] == "g"
    assert keys["openai"] == "env-o"


# --- Multipart body for OpenAI edits ---

def test_final_build_dest_preserves_extension(generate_illustrations, tmp_path):
    builds_dir = str(tmp_path / "builds")
    # Each base extension should propagate to the build dest path
    assert generate_illustrations.final_build_dest(
        builds_dir, 5, 3, "/tmp/slide-05.jpg"
    ).endswith("slide-05-build-03.jpg")
    assert generate_illustrations.final_build_dest(
        builds_dir, 5, 3, "/tmp/slide-05.png"
    ).endswith("slide-05-build-03.png")
    assert generate_illustrations.final_build_dest(
        builds_dir, 5, 3, "/tmp/slide-05.webp"
    ).endswith("slide-05-build-03.webp")
    # No extension on the source falls back to .jpg (matches the historic
    # hard-coded default rather than producing a path without a suffix)
    assert generate_illustrations.final_build_dest(
        builds_dir, 5, 3, "/tmp/slide-05"
    ).endswith("slide-05-build-03.jpg")


def test_parse_builds_empty_step_list(generate_illustrations):
    # An outline that declares `- Builds: N steps` without any parsable
    # `build-XX:` entries must not crash the parser, and the resulting
    # `steps` list must be empty so run_build's empty-guard fires.
    import tempfile
    outline = """\
# Plan
**Model:** `gemini-3-pro-image-preview`

### STYLE ANCHOR (WIDE — 16:9, 1920x1080)
> A style.

### Slide 4: Empty builds
- Format: **WIDE**
- Image prompt: `[STYLE ANCHOR] something`
- Builds: 5 steps
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(outline)
        f.flush()
        result = generate_illustrations.parse_outline(f.name)
    os.unlink(f.name)

    slide4 = next(s for s in result["slides"] if s["slide_num"] == 4)
    assert slide4["builds"]["count"] == 5
    assert slide4["builds"]["steps"] == []


def test_multipart_body_structure(generate_illustrations):
    body, boundary = generate_illustrations._multipart_body(
        fields={"model": "gpt-image-2", "prompt": "edit this", "n": "1"},
        files=[("image", "input.png", "image/png", b"\x89PNG\r\n")],
    )
    assert boundary.startswith("----GenIllustBnd")
    text = body.decode("utf-8", errors="replace")
    # Every field present with form-data disposition
    assert 'name="model"' in text
    assert "gpt-image-2" in text
    assert 'name="prompt"' in text
    assert "edit this" in text
    # File field carries filename + content-type
    assert 'name="image"' in text
    assert 'filename="input.png"' in text
    assert "Content-Type: image/png" in text
    # Body terminates with the closing boundary
    assert body.endswith(f"--{boundary}--\r\n".encode())
