"""Tests for generate-illustrations.py — outline parsing and slide selection (no API calls)."""

import json
import os

import pytest

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


def _single_build_slide(steps):
    return {
        "model": "gemini-3-pro-image-preview",
        "slides": [{
            "slide_num": 60, "title": "Trials", "format": "WIDE",
            "builds": {"count": len(steps), "steps": steps},
        }],
    }


def _stub_build_deps(gi, monkeypatch, tmp_path, outline, edit_calls):
    base = tmp_path / "slide-60.png"
    base.write_bytes(b"img")
    monkeypatch.setattr(gi, "_load_context", lambda p: ({}, outline, str(tmp_path)))
    monkeypatch.setattr(gi, "find_base_image", lambda d, n: str(base))
    monkeypatch.setattr(gi, "effective_slide_format", lambda *a, **k: None)
    monkeypatch.setattr(gi.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(
        gi, "edit_image",
        lambda *a, **k: (edit_calls.append(a), (b"x", "image/png"))[1],
    )


def test_run_build_missing_keep_exits_nonzero_without_editing(
    generate_illustrations, monkeypatch, tmp_path, capsys
):
    # Outcome: an erase step with no Keep clause skips the slide *before* any
    # edit API call and exits non-zero so `--build all` automation can detect it.
    gi = generate_illustrations
    outline = _single_build_slide([
        {"step": 0, "description": "Panel 1 revealed -- sergeant", "is_full": False},
        {"step": 1, "description": "[FULL] all panels", "is_full": True},
    ])
    edit_calls = []
    _stub_build_deps(gi, monkeypatch, tmp_path, outline, edit_calls)

    with pytest.raises(SystemExit) as exc:
        gi.run_build("ignored.md", "60")

    assert exc.value.code == 1
    assert edit_calls == []  # skipped before spending any edit API call
    assert "preservation list" in capsys.readouterr().err
    # A skipped slide must leave no build artifact behind (validation runs
    # before the final-image copy), so downstream checks aren't misled.
    builds_dir = tmp_path / "builds"
    assert list(builds_dir.glob("slide-60-build-*")) == []


def test_run_build_negated_keep_is_not_a_preservation_clause(
    generate_illustrations, monkeypatch, tmp_path
):
    # "Do not keep ..." is a removal, not a preservation clause: the slide is
    # skipped (exit 1, no edit) exactly like a bare description, so the bare
    # `keep` token can't satisfy the rule.
    gi = generate_illustrations
    outline = _single_build_slide([
        {"step": 0, "description": "Erase Panel 1. Do not keep the old stamp.", "is_full": False},
        {"step": 1, "description": "[FULL] all panels", "is_full": True},
    ])
    edit_calls = []
    _stub_build_deps(gi, monkeypatch, tmp_path, outline, edit_calls)

    with pytest.raises(SystemExit) as exc:
        gi.run_build("ignored.md", "60")

    assert exc.value.code == 1
    assert edit_calls == []


def test_run_build_with_keep_clause_runs_chain(
    generate_illustrations, monkeypatch, tmp_path
):
    # Outcome: a compliant erase step runs the edit chain. Uppercase KEEP also
    # proves the clause check is case-insensitive at the behavior level.
    gi = generate_illustrations
    outline = _single_build_slide([
        {"step": 0, "description": "Erase Panel 1. KEEP the page chrome.", "is_full": False},
        {"step": 1, "description": "[FULL] all panels", "is_full": True},
    ])
    edit_calls = []
    _stub_build_deps(gi, monkeypatch, tmp_path, outline, edit_calls)

    gi.run_build("ignored.md", "60")  # no SystemExit

    assert len(edit_calls) == 1  # the single erase step was edited


def test_run_build_exits_nonzero_when_edit_fails(
    generate_illustrations, monkeypatch, tmp_path, capsys
):
    # Outcome: an edit failure mid-chain aborts the slide and still exits
    # non-zero (file-hygiene: non-zero on failure), not only on validation.
    gi = generate_illustrations
    base = tmp_path / "slide-60.png"
    base.write_bytes(b"img")
    outline = _single_build_slide([
        {"step": 0, "description": "Erase Panel 1. Keep the page chrome.", "is_full": False},
        {"step": 1, "description": "[FULL] all panels", "is_full": True},
    ])
    monkeypatch.setattr(gi, "_load_context", lambda p: ({}, outline, str(tmp_path)))
    monkeypatch.setattr(gi, "find_base_image", lambda d, n: str(base))
    monkeypatch.setattr(gi, "effective_slide_format", lambda *a, **k: None)
    monkeypatch.setattr(gi.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(gi, "edit_image", lambda *a, **k: (None, "api boom"))

    with pytest.raises(SystemExit) as exc:
        gi.run_build("ignored.md", "60")

    assert exc.value.code == 1
    out = capsys.readouterr()
    # Diagnostic on stderr carries slide + step context; the success-sounding
    # "Done" line never prints on a failed run.
    assert "build-00 edit failed" in out.err
    assert "Done. Review build images" not in out.out


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


def test_effective_slide_format_safe_zone_wins(generate_illustrations):
    # apply-illustrations-to-deck.py gives Safe zone precedence over the
    # Format token — slides with any Safe zone field are treated as
    # FULL/title-overlay regardless of `Format: IMG+TXT` (see
    # apply-illustrations-to-deck.py's `parse_img_txt_slides()`, which
    # only returns IMG+TXT slides that do NOT carry a Safe zone line).
    # The generator's effective_slide_format mirrors that precedence so
    # sizing matches the downstream apply step.
    sz = {"zone": "upper_third", "surface": "painted sky"}
    assert generate_illustrations.effective_slide_format("IMG+TXT", sz) == "FULL"
    assert generate_illustrations.effective_slide_format("FULL", sz) == "FULL"
    assert generate_illustrations.effective_slide_format("DIAGRAM", sz) == "FULL"
    # No safe zone → declared format flows through unchanged
    assert generate_illustrations.effective_slide_format("IMG+TXT", None) == "IMG+TXT"
    assert generate_illustrations.effective_slide_format("FULL", None) == "FULL"
    assert generate_illustrations.effective_slide_format(None, None) is None


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
    # COMPARE_MODELS is re-exported from model_registry.py — it must still
    # carry at least one current-flagship entry per major vendor.
    families = {generate_illustrations.model_family(m)
                for m in generate_illustrations.COMPARE_MODELS}
    assert "openai" in families, "COMPARE_MODELS missing OpenAI entry"
    assert "gemini" in families, "COMPARE_MODELS missing Gemini entry"
    assert "imagen" in families, "COMPARE_MODELS missing Imagen entry"


def test_resolve_model_id_reexported(generate_illustrations):
    # generate-illustrations.py dispatches through resolve_model_id so a baked
    # codename (nano-banana-pro) reaches the canonical API endpoint id.
    assert generate_illustrations.resolve_model_id("nano-banana-pro") == "gemini-3-pro-image-preview"


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


def test_load_secrets_malformed_json_warns(generate_illustrations, tmp_path, monkeypatch, capsys):
    # Malformed secrets.json must not crash — load_secrets warns to stderr
    # and falls through to env-var resolution
    (tmp_path / "secrets.json").write_text("{not valid json")
    monkeypatch.setenv("GEMINI_API_KEY", "env-fallback")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    keys, _ = generate_illustrations.load_secrets(str(tmp_path))
    captured = capsys.readouterr()

    assert keys["gemini"] == "env-fallback"
    assert keys["openai"] is None
    # Warning must mention the file path so the user knows what to fix
    assert "secrets.json" in captured.err
    assert "not valid JSON" in captured.err


def test_load_secrets_partial_file(generate_illustrations, tmp_path, monkeypatch):
    # File has only gemini; openai should fall through to env
    (tmp_path / "secrets.json").write_text(json.dumps({"gemini": {"api_key": "g"}}))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "env-o")
    keys, _ = generate_illustrations.load_secrets(str(tmp_path))
    assert keys["gemini"] == "g"
    assert keys["openai"] == "env-o"


# --- Multipart body for OpenAI edits ---

def test_parse_outline_handles_img_plus_txt_format(generate_illustrations):
    # Outline using the documented `IMG+TXT` portrait format must parse
    # the `+` character — the original `\w+` regex silently dropped it.
    # Mismatched parsing would route non-16:9 slides through the FULL
    # sizing default in the cross-vendor dispatchers.
    import tempfile
    outline = """\
# Plan
**Model:** `gpt-image-2`

### STYLE ANCHOR (FULL — 16:9, 1920x1080)
> A FULL anchor.

### STYLE ANCHOR (IMG+TXT — Portrait 2:3, 1024x1536)
> An IMG+TXT anchor.

### Slide 3: A wide slide
- Format: **FULL**
- Image prompt: `[STYLE ANCHOR] something wide`

### Slide 7: A portrait slide
- Format: **IMG+TXT**
- Image prompt: `[STYLE ANCHOR] something tall`
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(outline)
        f.flush()
        result = generate_illustrations.parse_outline(f.name)
    os.unlink(f.name)

    assert "FULL" in result["anchors"]
    assert "IMG+TXT" in result["anchors"]

    slide3 = next(s for s in result["slides"] if s["slide_num"] == 3)
    slide7 = next(s for s in result["slides"] if s["slide_num"] == 7)
    assert slide3["format"] == "FULL"
    assert slide7["format"] == "IMG+TXT"


def test_sizing_for_format(generate_illustrations):
    # FULL maps to 16:9 landscape on both vendors
    full = generate_illustrations.sizing_for("FULL")
    assert full["openai_size"] == "2048x1152"
    assert full["imagen_aspect"] == "16:9"

    # IMG+TXT maps to 2:3 portrait (Imagen has no native 2:3, 3:4 is
    # closest of the supported aspect ratios)
    portrait = generate_illustrations.sizing_for("IMG+TXT")
    assert portrait["openai_size"] == "1024x1536"
    assert portrait["imagen_aspect"] == "3:4"

    # Unknown / missing falls back to FULL — historical default
    assert generate_illustrations.sizing_for(None) == full
    assert generate_illustrations.sizing_for("DIAGRAM") == full
    assert generate_illustrations.sizing_for("") == full


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


# --- Style exploration (Phase 2 strategy grid) ---

def _candidates(**overrides):
    base = {
        "schema_version": 1,
        "slides": {"FULL": 3, "IMG+TXT": 7},
        "models": ["gemini-3-pro-image-preview", "gpt-image-2"],
        "styles": [
            {"name": "Blueprint Schematic",
             "anchors": {"FULL": "A blueprint anchor.", "IMG+TXT": "A portrait blueprint anchor."}},
            {"name": "Watercolor",
             "anchors": {"FULL": "A watercolor anchor.", "IMG+TXT": "A portrait watercolor anchor."}},
        ],
    }
    base.update(overrides)
    return base


def _write_candidates(tmp_path, data):
    p = tmp_path / "candidates.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_style_slug(generate_illustrations):
    assert generate_illustrations.style_slug("Blueprint Schematic!") == "blueprint-schematic"
    assert generate_illustrations.style_slug("  Mixed_Case 2 ") == "mixed-case-2"
    assert generate_illustrations.style_slug("///") == "style"


def test_format_slug(generate_illustrations):
    assert generate_illustrations._format_slug("IMG+TXT") == "img-txt"
    assert generate_illustrations._format_slug("FULL") == "full"


def test_explore_dest_path(generate_illustrations):
    dest = generate_illustrations.explore_dest(
        "/base", "Blueprint Schematic", "IMG+TXT", "gemini-3-pro-image-preview", ".png"
    )
    assert dest == "/base/blueprint-schematic/img-txt/gemini-3-pro-image-preview.png"


def test_explore_dest_sanitizes_model_slash(generate_illustrations):
    dest = generate_illustrations.explore_dest("/base", "S", "FULL", "vendor/model", ".jpg")
    assert dest.endswith("vendor_model.jpg")


def test_parse_candidates_valid(generate_illustrations, tmp_path):
    path = _write_candidates(tmp_path, _candidates())
    data = generate_illustrations.parse_candidates(path)
    assert data["schema_version"] == 1
    assert len(data["styles"]) == 2


def test_parse_candidates_bad_version(generate_illustrations, tmp_path):
    import pytest
    path = _write_candidates(tmp_path, _candidates(schema_version=2))
    with pytest.raises(ValueError) as exc:
        generate_illustrations.parse_candidates(path)
    assert "schema_version" in str(exc.value)


def test_parse_candidates_missing_models(generate_illustrations, tmp_path):
    import pytest
    path = _write_candidates(tmp_path, _candidates(models=[]))
    with pytest.raises(ValueError) as exc:
        generate_illustrations.parse_candidates(path)
    assert "models" in str(exc.value)


def test_parse_candidates_style_without_anchors(generate_illustrations, tmp_path):
    import pytest
    bad = _candidates(styles=[{"name": "No Anchors"}])
    path = _write_candidates(tmp_path, bad)
    with pytest.raises(ValueError) as exc:
        generate_illustrations.parse_candidates(path)
    assert "anchors" in str(exc.value)


def test_parse_candidates_non_string_model_rejected(generate_illustrations, tmp_path):
    import pytest
    path = _write_candidates(tmp_path, _candidates(models=["gpt-image-2", 7]))
    with pytest.raises(ValueError) as exc:
        generate_illustrations.parse_candidates(path)
    assert "models[1]" in str(exc.value)


def test_parse_candidates_strips_model_whitespace(generate_illustrations, tmp_path):
    path = _write_candidates(tmp_path, _candidates(models=["  gpt-image-2  "]))
    data = generate_illustrations.parse_candidates(path)
    assert data["models"] == ["gpt-image-2"]


def test_parse_candidates_blank_anchor_rejected(generate_illustrations, tmp_path):
    import pytest
    bad = _candidates(styles=[{"name": "S", "anchors": {"FULL": "   "}}])
    path = _write_candidates(tmp_path, bad)
    with pytest.raises(ValueError) as exc:
        generate_illustrations.parse_candidates(path)
    assert "anchor for 'FULL'" in str(exc.value)


def test_parse_candidates_non_string_name_rejected(generate_illustrations, tmp_path):
    import pytest
    bad = _candidates(styles=[{"name": 42, "anchors": {"FULL": "x"}}])
    path = _write_candidates(tmp_path, bad)
    with pytest.raises(ValueError) as exc:
        generate_illustrations.parse_candidates(path)
    assert "non-empty string 'name'" in str(exc.value)


def test_parse_candidates_string_slide_number_rejected(generate_illustrations, tmp_path):
    import pytest
    # A string slide number would key slides_by_num by the wrong type and
    # silently skip the format — reject it up front with an actionable message.
    path = _write_candidates(tmp_path, _candidates(slides={"FULL": "7"}))
    with pytest.raises(ValueError) as exc:
        generate_illustrations.parse_candidates(path)
    assert "integer slide number" in str(exc.value)


def test_parse_candidates_malformed_json(generate_illustrations, tmp_path):
    import pytest
    p = tmp_path / "candidates.json"
    p.write_text("{not json")
    with pytest.raises(ValueError) as exc:
        generate_illustrations.parse_candidates(str(p))
    assert "valid JSON" in str(exc.value)


def test_run_style_explore_missing_candidates_exits_cleanly(generate_illustrations, tmp_path, capsys):
    import pytest
    # A missing candidates file must produce an actionable stderr error + a
    # non-zero exit, not a FileNotFoundError traceback.
    with pytest.raises(SystemExit) as exc:
        generate_illustrations.run_style_explore(
            str(tmp_path / "outline.md"), str(tmp_path / "nope.json")
        )
    assert exc.value.code == 1
    assert "candidates file not found" in capsys.readouterr().err


def test_run_style_explore_bad_candidates_exits_cleanly(generate_illustrations, tmp_path, capsys):
    import pytest
    # A malformed candidates file surfaces the ValueError as a clean stderr
    # message + non-zero exit, not a traceback.
    p = tmp_path / "candidates.json"
    p.write_text(json.dumps({"schema_version": 2}))
    with pytest.raises(SystemExit) as exc:
        generate_illustrations.run_style_explore(str(tmp_path / "outline.md"), str(p))
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "ERROR" in err and "schema_version" in err


def test_run_style_explore_empty_plan_exits_cleanly(generate_illustrations, tmp_path, monkeypatch, capsys):
    import pytest
    # A schema-valid candidate set whose styles cover none of the selected
    # formats yields zero renders — exit non-zero before writing an empty
    # index.md, rather than succeeding with an empty contact sheet.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    outline = tmp_path / "outline.md"
    outline.write_text(
        "# Plan\n\n**Model:** `gemini-3-pro-image-preview`\n\n"
        "### STYLE ANCHOR (FULL — 16:9, 1920x1080)\n> A base.\n\n"
        "### Slide 3: Wide\n- Format: **FULL**\n- Image prompt: `[STYLE ANCHOR] wide`\n"
    )
    cand = _candidates(
        slides={"FULL": 3},
        models=["gemini-3-pro-image-preview"],
        styles=[{"name": "PortraitOnly", "anchors": {"IMG+TXT": "portrait only"}}],
    )
    cpath = _write_candidates(tmp_path, cand)
    with pytest.raises(SystemExit) as exc:
        generate_illustrations.run_style_explore(str(outline), cpath)
    assert exc.value.code == 1
    assert "nothing to render" in capsys.readouterr().err


def test_run_style_explore_unsupported_model_exits(generate_illustrations, tmp_path, monkeypatch, capsys):
    import pytest
    # A candidate model with no vendor adapter must fail fast with an actionable
    # stderr message, not get misrouted to the Gemini endpoint.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    outline = tmp_path / "outline.md"
    outline.write_text(
        "# Plan\n\n**Model:** `gemini-3-pro-image-preview`\n\n"
        "### STYLE ANCHOR (FULL — 16:9, 1920x1080)\n> A base.\n\n"
        "### Slide 3: Wide\n- Format: **FULL**\n- Image prompt: `[STYLE ANCHOR] wide`\n"
    )
    cand = _candidates(
        slides={"FULL": 3},
        models=["midjourney-v7"],
        styles=[{"name": "S", "anchors": {"FULL": "a full anchor"}}],
    )
    cpath = _write_candidates(tmp_path, cand)
    with pytest.raises(SystemExit) as exc:
        generate_illustrations.run_style_explore(str(outline), cpath)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "unsupported model" in err and "midjourney-v7" in err


def test_run_style_explore_safezone_format_mismatch_skipped(generate_illustrations, tmp_path, monkeypatch, capsys):
    import pytest
    # A non-FULL format mapped to a slide whose Safe zone forces FULL is skipped
    # (its geometry would disagree); with no usable targets left, the run exits
    # non-zero and both diagnostics go to stderr.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    outline = tmp_path / "outline.md"
    outline.write_text(
        "# Plan\n\n**Model:** `gemini-3-pro-image-preview`\n\n"
        "### STYLE ANCHOR (IMG+TXT — Portrait 2:3, 1024x1536)\n> A base.\n\n"
        "### Slide 4: Portrait with zone\n- Format: **IMG+TXT**\n"
        "- Image prompt: `[STYLE ANCHOR] tall`\n- Safe zone: upper_third (sky)\n"
    )
    cand = _candidates(
        slides={"IMG+TXT": 4},
        models=["gemini-3-pro-image-preview"],
        styles=[{"name": "S", "anchors": {"IMG+TXT": "portrait"}}],
    )
    cpath = _write_candidates(tmp_path, cand)
    with pytest.raises(SystemExit) as exc:
        generate_illustrations.run_style_explore(str(outline), cpath)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "Safe zone" in err and "usable image prompt" in err


def test_render_explore_index_groups_by_style(generate_illustrations):
    candidates = _candidates()
    results = [
        {"style": "Blueprint Schematic", "format": "FULL",
         "model": "gpt-image-2", "status": "OK",
         "rel_path": "blueprint-schematic/full/gpt-image-2.png"},
        {"style": "Watercolor", "format": "IMG+TXT",
         "model": "gemini-3-pro-image-preview", "status": "FAIL",
         "error": "rate limited"},
    ]
    md = generate_illustrations.render_explore_index(candidates, results)
    assert "# Style Exploration" in md
    assert "## Blueprint Schematic" in md
    assert "## Watercolor" in md
    # OK render links to the relative image path
    assert "(blueprint-schematic/full/gpt-image-2.png)" in md
    # FAIL render surfaces the error, not a broken link
    assert "FAILED: rate limited" in md
    # representative slide mapping is documented in the header
    assert "FULL = slide 3" in md
