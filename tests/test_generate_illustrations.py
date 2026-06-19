"""Tests for generate-illustrations.py — outline parsing and slide selection (no API calls).

parse_outline reads outline.yaml (the single source of truth) and projects it
onto the generator's view; these tests drive the canonical fixture.
"""

import copy
import json
import os
from pathlib import Path

import pytest
import yaml

FIXTURE = Path(__file__).parent / "fixtures" / "outline-example.yaml"
_FIXTURE_DATA = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _write_outline(tmp_path, *, slides, model: str | None = "imagen-4",
                   composition=None, embedded_footer=None, text_treatment=None,
                   name="outline.yaml"):
    """Write a minimal valid outline.yaml (partial view) for parser tests.

    Reuses the canonical fixture's talk block, then sets the style anchor and
    the slides the test cares about. parse_outline reads it via
    load_outline_partial, so full-deck invariants are not required.
    """
    data = {"talk": copy.deepcopy(_FIXTURE_DATA["talk"]), "slides": slides}
    if model:
        anchor = {
            "model": model,
            "full": "A clean editorial illustration, 16:9.",
            "imgtxt": "A portrait illustration, 2:3.",
            "conventions": "Recurring motif.",
        }
        if composition is not None:
            anchor["composition"] = composition
        if embedded_footer is not None:
            anchor["embedded_footer"] = embedded_footer
        if text_treatment is not None:
            anchor["text_treatment"] = text_treatment
        data["style_anchor"] = anchor
    p = tmp_path / name
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return p


def test_parse_model(generate_illustrations):
    result = generate_illustrations.parse_outline(FIXTURE)
    assert result["model"] == "imagen-4"


def test_parse_anchors(generate_illustrations):
    result = generate_illustrations.parse_outline(FIXTURE)
    # Anchors are keyed by the format token the generator resolves against.
    assert "FULL" in result["anchors"]
    assert "IMG+TXT" in result["anchors"]
    assert "Photorealistic" in result["anchors"]["FULL"]


def test_parse_anchors_fold_in_conventions(generate_illustrations):
    # #83: the required `conventions` block holds deck-wide, generation-relevant
    # style rules. It must be folded into EVERY format's anchor so it reaches the
    # model on every slide — parsing it but never injecting it was the bug.
    result = generate_illustrations.parse_outline(FIXTURE)
    assert "brass compass" in result["anchors"]["FULL"]
    assert "brass compass" in result["anchors"]["IMG+TXT"]
    # Also surfaced raw for callers/tests.
    assert result["conventions"] and "brass compass" in result["conventions"]


def test_parse_anchors_no_conventions_is_clean(generate_illustrations, tmp_path):
    # An empty conventions string must not append a stray separator to the anchor.
    data = copy.deepcopy(_FIXTURE_DATA)
    data["style_anchor"]["conventions"] = ""
    p = tmp_path / "outline.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = generate_illustrations.parse_outline(str(p))
    assert result["conventions"] is None
    assert not result["anchors"]["FULL"].endswith(" ")


def test_parse_slides_excludes_promptless(generate_illustrations):
    # Slide 7 is EXCEPTION (a real screenshot) with no image_prompt — it is not
    # an illustration target and must be excluded from the generator's view.
    result = generate_illustrations.parse_outline(FIXTURE)
    nums = [s["slide_num"] for s in result["slides"]]
    assert nums == [1, 2, 3, 5, 8, 10, 11]
    assert 7 not in nums


def test_parse_slide_text_overlay_none_is_dropped(generate_illustrations):
    # Slide 1's text_overlay is the sentinel "none" — it must not surface as
    # on-slide text (which would leak as a poster title).
    result = generate_illustrations.parse_outline(FIXTURE)
    slide1 = next(s for s in result["slides"] if s["slide_num"] == 1)
    assert "text" not in slide1


def test_parse_builds_maps_erase_and_is_full(generate_illustrations, tmp_path):
    # builds[].erase becomes the generator's edit prompt; the final (max) step
    # is is_full and carries no erase prompt (it is copied from the base image).
    data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    slide2 = next(s for s in data["slides"] if s["n"] == 2)
    for b in slide2["builds"][:-1]:
        b["erase"] = f"Erase the step {b['step']} content. Keep the three frames."
    p = tmp_path / "outline.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")

    result = generate_illustrations.parse_outline(str(p))
    s2 = next(s for s in result["slides"] if s["slide_num"] == 2)
    assert s2["builds"]["count"] == 4
    steps = s2["builds"]["steps"]
    assert steps[-1]["is_full"] is True
    assert all(not st["is_full"] for st in steps[:-1])
    assert steps[0]["description"].startswith("Erase the step 0")
    # The final full step needs no erase prompt.
    assert steps[-1]["description"] == ""


def _single_build_slide(steps):
    return {
        "model": "gemini-3-pro-image",
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
    # Render-before-bake gate passes by default here; the gate-fail test overrides it.
    monkeypatch.setattr(gi, "check_style_explore", lambda p: {"gate_passed": True, "error": ""})
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
        gi.run_build("ignored.yaml", "60")

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
        gi.run_build("ignored.yaml", "60")

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

    gi.run_build("ignored.yaml", "60")  # no SystemExit

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
    monkeypatch.setattr(gi, "check_style_explore", lambda p: {"gate_passed": True, "error": ""})
    monkeypatch.setattr(gi, "edit_image", lambda *a, **k: (None, "api boom"))

    with pytest.raises(SystemExit) as exc:
        gi.run_build("ignored.yaml", "60")

    assert exc.value.code == 1
    out = capsys.readouterr()
    # Diagnostic on stderr carries slide + step context; the success-sounding
    # "Done" line never prints on a failed run.
    assert "build-00 edit failed" in out.err
    assert "Done. Review build images" not in out.out


def test_run_build_refuses_when_render_gate_fails(
    generate_illustrations, monkeypatch, tmp_path
):
    # run_build must enforce the same render-before-bake gate as run_generate:
    # an unrendered baked model can't produce build frames either. Refuse before
    # spending any edit API call.
    gi = generate_illustrations
    outline = _single_build_slide([
        {"step": 0, "description": "Erase Panel 1. Keep the chrome.", "is_full": False},
        {"step": 1, "description": "[FULL] all panels", "is_full": True},
    ])
    edit_calls = []
    _stub_build_deps(gi, monkeypatch, tmp_path, outline, edit_calls)
    # gate fails (baked model never rendered / manifest missing)
    monkeypatch.setattr(
        gi, "check_style_explore",
        lambda p: {"gate_passed": False, "error": "model 'x' was never rendered in a grid"},
    )

    with pytest.raises(SystemExit) as exc:
        gi.run_build("ignored.yaml", "60")

    assert exc.value.code == 1
    assert edit_calls == []  # refused before any edit API call


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


def test_parse_safe_zone(generate_illustrations, tmp_path):
    outline = _write_outline(tmp_path, model="gemini-3-pro-image", slides=[
        {"n": 3, "chapter": "c", "title": "The Question", "format": "FULL",
         "image_prompt": "[STYLE ANCHOR] A confused developer",
         "safe_zone": {"zone": "upper_third", "surface": "painted sky"}},
    ])
    result = generate_illustrations.parse_outline(str(outline))
    slide3 = next(s for s in result["slides"] if s["slide_num"] == 3)
    assert "safe_zone" in slide3
    assert slide3["safe_zone"]["zone"] == "upper_third"
    assert slide3["safe_zone"]["surface"] == "painted sky"


def test_parse_no_safe_zone(generate_illustrations, tmp_path):
    outline = _write_outline(tmp_path, model="gemini-3-pro-image", slides=[
        {"n": 7, "chapter": "c", "title": "No Zone", "format": "FULL",
         "image_prompt": "A terminal output"},
    ])
    result = generate_illustrations.parse_outline(str(outline))
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


def test_apply_compose_only_directive(generate_illustrations):
    # #87: the style anchor renders on every slide, so the fresh-gen prompt must
    # carry a guard pinning the model to THIS slide's scene and barring
    # deck-wide page-furniture.
    result = generate_illustrations.apply_compose_only_directive("A lone brick")
    assert "COMPOSE ONLY THE SCENE" in result
    assert result.startswith("A lone brick")
    assert "instruction-page furniture" in result


def test_apply_compose_only_directive_idempotent(generate_illustrations):
    once = generate_illustrations.apply_compose_only_directive("A scene")
    twice = generate_illustrations.apply_compose_only_directive(once)
    assert once == twice
    assert twice.count("COMPOSE ONLY THE SCENE") == 1


def test_apply_compose_only_preserves_caller_text_with_phrase(generate_illustrations):
    # A speaker prompt (or an already-appended safe-zone/poster directive) that
    # happens to contain the words "COMPOSE ONLY THE SCENE" must NOT be truncated:
    # the guard appends, it never splits away caller content.
    gi = generate_illustrations
    prompt = "A lab. COMPOSE ONLY THE SCENE as the author noted. TITLE SAFE ZONE -- reserve the top."
    result = gi.apply_compose_only_directive(prompt)
    assert result.startswith(prompt)            # nothing dropped
    assert "TITLE SAFE ZONE" in result          # prior directive survives
    assert result.endswith(gi.COMPOSE_ONLY_DIRECTIVE)


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
    assert generate_illustrations.model_family("gemini-3-pro-image") == "gemini"
    assert generate_illustrations.model_family("gemini-3.1-flash-image") == "gemini"
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
    assert generate_illustrations.resolve_model_id("nano-banana-pro") == "gemini-3-pro-image"
    # The deprecated preview id is kept as an alias resolving to the GA canonical.
    assert generate_illustrations.resolve_model_id("gemini-3-pro-image-preview") == "gemini-3-pro-image"


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


def test_read_file_with_timeout_returns_bytes(generate_illustrations, tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello")
    assert generate_illustrations._read_file_with_timeout(str(p), 5) == b"hello"


def test_read_file_with_timeout_raises_on_stall(generate_illustrations, tmp_path):
    # A named pipe with no writer blocks the open/read forever — the closest
    # portable stand-in for a cloud "dataless" placeholder that never
    # materializes. The reader must give up and raise TimeoutError, not hang.
    if not hasattr(os, "mkfifo"):
        pytest.skip("os.mkfifo not available on this platform")
    fifo = tmp_path / "stalled.json"
    os.mkfifo(fifo)
    with pytest.raises(TimeoutError):
        generate_illustrations._read_file_with_timeout(str(fifo), 0.5)


def test_load_secrets_timeout_warns_and_falls_back(
    generate_illustrations, tmp_path, monkeypatch, capsys
):
    # A stalled secrets read must degrade to env vars with a loud warning —
    # never hang, never silently swallow.
    gi = generate_illustrations
    (tmp_path / "secrets.json").write_text(json.dumps({"gemini": {"api_key": "g"}}))

    def _boom(path, timeout):
        raise TimeoutError(f"reading {path} timed out after {timeout}s")

    monkeypatch.setattr(gi, "_read_file_with_timeout", _boom)
    monkeypatch.setenv("GEMINI_API_KEY", "env-g")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    keys, _ = gi.load_secrets(str(tmp_path))
    err = capsys.readouterr().err
    assert keys["gemini"] == "env-g"   # fell back to env
    assert keys["openai"] is None
    assert "timed out" in err and "secrets.json" in err


# --- Multipart body for OpenAI edits ---

def test_parse_outline_handles_img_plus_txt_format(generate_illustrations, tmp_path):
    # The IMG+TXT portrait format must survive the round-trip: it keys the
    # anchor map and drives 2:3 sizing in the cross-vendor dispatchers.
    outline = _write_outline(tmp_path, model="gpt-image-2", slides=[
        {"n": 3, "chapter": "c", "title": "A wide slide", "format": "FULL",
         "image_prompt": "[STYLE ANCHOR] something wide"},
        {"n": 7, "chapter": "c", "title": "A portrait slide", "format": "IMG+TXT",
         "image_prompt": "[STYLE ANCHOR] something tall"},
    ])
    result = generate_illustrations.parse_outline(str(outline))

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


def test_parse_empty_builds_list_yields_no_builds_key(generate_illustrations, tmp_path):
    # A slide with an empty `builds: []` is not a build slide — parse_outline
    # must omit the "builds" key entirely (the schema forbids a count without
    # contiguous steps, so the old "declared N steps, zero entries" markdown
    # failure mode can no longer occur).
    outline = _write_outline(tmp_path, model="gemini-3-pro-image", slides=[
        {"n": 4, "chapter": "c", "title": "Empty builds", "format": "FULL",
         "image_prompt": "[STYLE ANCHOR] something", "builds": []},
    ])
    result = generate_illustrations.parse_outline(str(outline))
    slide4 = next(s for s in result["slides"] if s["slide_num"] == 4)
    assert "builds" not in slide4


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
        "models": ["gemini-3-pro-image", "gpt-image-2"],
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
        "/base", "Blueprint Schematic", "IMG+TXT", "gemini-3-pro-image", ".png"
    )
    assert dest == "/base/blueprint-schematic/img-txt/gemini-3-pro-image.png"


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
            str(tmp_path / "outline.yaml"), str(tmp_path / "nope.json")
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
        generate_illustrations.run_style_explore(str(tmp_path / "outline.yaml"), str(p))
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "ERROR" in err and "schema_version" in err


def test_run_style_explore_empty_plan_exits_cleanly(generate_illustrations, tmp_path, monkeypatch, capsys):
    import pytest
    # A schema-valid candidate set whose styles cover none of the selected
    # formats yields zero renders — exit non-zero before writing an empty
    # index.md, rather than succeeding with an empty contact sheet.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    outline = _write_outline(tmp_path, model="gemini-3-pro-image", slides=[
        {"n": 3, "chapter": "c", "title": "Wide", "format": "FULL",
         "image_prompt": "[STYLE ANCHOR] wide"},
    ])
    cand = _candidates(
        slides={"FULL": 3},
        models=["gemini-3-pro-image"],
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
    outline = _write_outline(tmp_path, model="gemini-3-pro-image", slides=[
        {"n": 3, "chapter": "c", "title": "Wide", "format": "FULL",
         "image_prompt": "[STYLE ANCHOR] wide"},
    ])
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
    outline = _write_outline(tmp_path, model="gemini-3-pro-image", slides=[
        {"n": 4, "chapter": "c", "title": "Portrait with zone", "format": "IMG+TXT",
         "image_prompt": "[STYLE ANCHOR] tall",
         "safe_zone": {"zone": "upper_third", "surface": "sky"}},
    ])
    cand = _candidates(
        slides={"IMG+TXT": 4},
        models=["gemini-3-pro-image"],
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
         "model": "gemini-3-pro-image", "status": "FAIL",
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


# ── Render-before-bake gate + rendered.json manifest ─────────────────


def _write_gate_outline(tmp_path, model=None):
    """Write an outline with a style anchor and one FULL slide; optional model."""
    return _write_outline(tmp_path, model=model, slides=[
        {"n": 1, "chapter": "c", "title": "Intro", "format": "FULL",
         "image_prompt": "[STYLE ANCHOR] a thing"},
    ])


def _write_manifest(tmp_path, ok_models, cells=None, outline_dir=None):
    se = tmp_path / "style-explore"
    se.mkdir(exist_ok=True)
    # The gate verifies live evidence: an OK cell whose rendered file exists on
    # disk. When cells aren't supplied, build one per model AND create its file.
    if cells is None:
        cells = []
        for m in ok_models:
            rel = f"style/full/{m}.png"
            fp = se / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(b"img")
            cells.append({
                "style": "S", "format": "FULL", "model": m,
                "model_resolved": m, "status": "OK", "rel_path": rel,
            })
    manifest = {
        "schema_version": 1,
        "outline": "outline.yaml",
        "outline_dir": tmp_path.name if outline_dir is None else outline_dir,
        "rendered_at": "2026-06-08T00:00:00Z",
        "models_rendered_ok": ok_models,
        "cells": cells,
    }
    path = se / "rendered.json"
    path.write_text(json.dumps(manifest))
    return path


def test_rendered_manifest_excludes_failed(generate_illustrations, tmp_path):
    # Outcome: a model that failed every cell never enters models_rendered_ok,
    # so it can't pass the gate — you can't bake a model you never saw render.
    gi = generate_illustrations
    base = tmp_path / "style-explore"
    base.mkdir()
    outline = tmp_path / "outline.yaml"
    outline.write_text("x")
    results = [
        {"style": "A", "format": "FULL", "model": "nano-banana-pro",
         "status": "OK", "rel_path": "a/full/x.png"},
        {"style": "A", "format": "FULL", "model": "gpt-image-2",
         "status": "FAIL", "error": "boom"},
    ]
    path = gi.write_rendered_manifest(str(base), str(outline), results)
    m = json.loads(open(path).read())
    assert m["schema_version"] == 1
    # nano-banana-pro resolves to its canonical id; the failed model is absent
    assert m["models_rendered_ok"] == ["gemini-3-pro-image"]
    assert len(m["cells"]) == 2


def test_gate_passes_when_model_rendered_ok(generate_illustrations, tmp_path):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    _write_manifest(tmp_path, ["gemini-3-pro-image"])
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is True
    assert v["manifest_present"] is True


def test_gate_passes_on_codename_resolution(generate_illustrations, tmp_path):
    # Baking the codename must satisfy a grid that rendered the canonical id.
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="nano-banana-pro")
    _write_manifest(tmp_path, ["gemini-3-pro-image"])
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is True
    assert v["model_resolved"] == "gemini-3-pro-image"


def test_gate_fails_when_model_not_rendered(generate_illustrations, tmp_path):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    _write_manifest(tmp_path, ["gpt-image-2"])
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False
    assert "not rendered" in v["error"]


def test_gate_fails_when_no_manifest(generate_illustrations, tmp_path):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False
    assert v["manifest_present"] is False
    assert "never rendered" in v["error"]


def test_gate_fails_when_no_model_baked(generate_illustrations, tmp_path):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model=None)
    _write_manifest(tmp_path, ["gemini-3-pro-image"])
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False
    assert v["model_baked"] is None


def test_gate_fails_when_model_only_failed(generate_illustrations, tmp_path):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    cells = [{
        "style": "A", "format": "FULL",
        "model": "gemini-3-pro-image",
        "model_resolved": "gemini-3-pro-image",
        "status": "FAIL", "error": "boom",
    }]
    _write_manifest(tmp_path, [], cells=cells)
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False


def _stub_generate(gi, monkeypatch, outline_dict, output_dir, gen_calls):
    monkeypatch.setattr(gi, "_load_context", lambda p: ({}, outline_dict, output_dir))
    monkeypatch.setattr(gi.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(
        gi, "generate_image",
        lambda *a, **k: (gen_calls.append(a), (b"x", "image/png"))[1],
    )


def test_run_generate_refuses_when_gate_fails(
    generate_illustrations, monkeypatch, tmp_path, capsys
):
    # Outcome: with no rendered grid, run_generate exits non-zero BEFORE any
    # image is generated — the model can't have been picked from real samples.
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    outline_dict = gi.parse_outline(str(outline))
    gen_calls = []
    _stub_generate(gi, monkeypatch, outline_dict, str(tmp_path), gen_calls)

    with pytest.raises(SystemExit) as exc:
        gi.run_generate(str(outline), ["all"])

    assert exc.value.code == 1
    assert gen_calls == []
    assert "never rendered" in capsys.readouterr().err


def test_run_generate_proceeds_when_gate_passes(
    generate_illustrations, monkeypatch, tmp_path
):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    outline_dict = gi.parse_outline(str(outline))
    _write_manifest(tmp_path, ["gemini-3-pro-image"])
    gen_calls = []
    _stub_generate(gi, monkeypatch, outline_dict, str(tmp_path), gen_calls)

    gi.run_generate(str(outline), ["all"])  # no SystemExit

    assert len(gen_calls) == 1


# ── Poster-theatrical composition (embedded title + footer) ──────────


def _write_poster_outline(tmp_path, model="gemini-3-pro-image",
                          footer="jbaruch • Devoxx 2026", text="One team, one bench",
                          text_treatment="glowing hand-script neon on an in-scene surface"):
    return _write_outline(
        tmp_path, model=model, composition="poster-theatrical",
        embedded_footer=footer, text_treatment=text_treatment, slides=[
            {"n": 3, "chapter": "c", "title": "The Coordination Tax",
             "format": "FULL", "text_overlay": text,
             "image_prompt": "[STYLE ANCHOR] one team at a shared workbench"},
        ],
    )


def test_parse_poster_composition_and_footer(generate_illustrations, tmp_path):
    gi = generate_illustrations
    outline = _write_poster_outline(tmp_path)
    r = gi.parse_outline(str(outline))
    assert r["composition"] == "poster-theatrical"
    assert r["embedded_footer"] == "jbaruch • Devoxx 2026"
    assert r["text_treatment"] == "glowing hand-script neon on an in-scene surface"
    assert r["slides"][0]["text"] == "One team, one bench"


def test_poster_embed_directive_includes_title_and_footer(generate_illustrations):
    gi = generate_illustrations
    d = gi.apply_poster_embed_directive("a scene", "One team, one bench", "jbaruch • Devoxx 2026")
    assert "EMBEDDED TEXT" in d
    assert "One team, one bench" in d
    assert "jbaruch • Devoxx 2026" in d


def test_poster_embed_directive_uses_anchor_text_treatment(generate_illustrations):
    # The anchor's text_treatment must appear verbatim in the directive so every
    # slide's baked title/footer renders identically.
    gi = generate_illustrations
    d = gi.apply_poster_embed_directive(
        "a scene", "One team, one bench", "footer",
        "glowing hand-script neon on an in-scene surface",
    )
    assert "glowing hand-script neon on an in-scene surface" in d


def test_poster_embed_directive_falls_back_to_default_treatment(generate_illustrations):
    # With no anchor text_treatment, the generic default is used (back-compat).
    gi = generate_illustrations
    d = gi.apply_poster_embed_directive("a scene", "Title", None)
    assert gi.DEFAULT_POSTER_TEXT_TREATMENT in d
    assert "TITLE SAFE ZONE" not in d


def test_poster_embed_directive_omits_footer_when_absent(generate_illustrations):
    gi = generate_illustrations
    d = gi.apply_poster_embed_directive("a scene", "Title only", None)
    assert "Title only" in d
    assert "footer" not in d.lower()


def test_poster_embed_directive_idempotent(generate_illustrations):
    gi = generate_illustrations
    once = gi.apply_poster_embed_directive("a scene", "T", "F")
    twice = gi.apply_poster_embed_directive(once, "T", "F")
    assert twice.count("EMBEDDED TEXT") == 1


def test_run_generate_poster_embeds_text_and_skips_safe_zone(
    generate_illustrations, monkeypatch, tmp_path
):
    # Outcome: in poster mode the generation prompt carries the embedded-text
    # directive (title + footer) and never the safe-zone directive.
    gi = generate_illustrations
    outline = _write_poster_outline(tmp_path)
    outline_dict = gi.parse_outline(str(outline))
    _write_manifest(tmp_path, ["gemini-3-pro-image"])  # satisfy the render gate

    prompts = []
    monkeypatch.setattr(gi, "_load_context", lambda p: ({}, outline_dict, str(tmp_path)))
    monkeypatch.setattr(gi.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(
        gi, "generate_image",
        lambda prompt, *a, **k: (prompts.append(prompt), (b"x", "image/png"))[1],
    )

    gi.run_generate(str(outline), ["all"])

    assert len(prompts) == 1
    assert "EMBEDDED TEXT" in prompts[0]
    assert "One team, one bench" in prompts[0]
    assert "jbaruch • Devoxx 2026" in prompts[0]
    # The anchor's text_treatment rides through run_generate into the prompt.
    assert "glowing hand-script neon on an in-scene surface" in prompts[0]
    assert "TITLE SAFE ZONE" not in prompts[0]


# ── Gate manifest validation + poster invariants (review hardening) ──


def _write_raw_manifest(tmp_path, payload):
    se = tmp_path / "style-explore"
    se.mkdir(exist_ok=True)
    (se / "rendered.json").write_text(json.dumps(payload))


def test_gate_fails_on_unsupported_schema_version(generate_illustrations, tmp_path):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    _write_raw_manifest(tmp_path, {
        "schema_version": 2, "outline": "outline.yaml",
        "models_rendered_ok": ["gemini-3-pro-image"], "cells": [],
    })
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False
    assert "schema_version" in v["error"]


def test_gate_fails_on_outline_mismatch(generate_illustrations, tmp_path):
    # A manifest copied in from a different talk must not pass the gate.
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    _write_raw_manifest(tmp_path, {
        "schema_version": 1, "outline": "some-other-talk.yaml",
        "models_rendered_ok": ["gemini-3-pro-image"], "cells": [],
    })
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False
    assert "copied or stale" in v["error"]


def test_gate_fails_when_rendered_file_missing(generate_illustrations, tmp_path):
    # The core live-evidence check: a manifest can list a model in an OK cell,
    # but if the rendered image file isn't on disk the gate must NOT pass —
    # a hand-edited manifest can't fake a render the speaker never saw.
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    _write_raw_manifest(tmp_path, {
        "schema_version": 1, "outline": "outline.yaml", "outline_dir": tmp_path.name,
        "models_rendered_ok": ["gemini-3-pro-image"],
        "cells": [{
            "style": "S", "format": "FULL", "model": "gemini-3-pro-image",
            "model_resolved": "gemini-3-pro-image", "status": "OK",
            "rel_path": "style/full/gemini-3-pro-image.png",  # never created
        }],
    })
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False
    assert v["rendered_models"] == []


def test_gate_fails_on_outline_dir_mismatch(generate_illustrations, tmp_path):
    # A grid copied from another talk (same outline filename, different dir).
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    _write_manifest(tmp_path, ["gemini-3-pro-image"], outline_dir="some-other-talk")
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False
    assert "copied from" in v["error"]


def test_gate_fails_on_malformed_cells(generate_illustrations, tmp_path):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    _write_raw_manifest(tmp_path, {
        "schema_version": 1, "outline": "outline.yaml", "outline_dir": tmp_path.name,
        "models_rendered_ok": [], "cells": "not-a-list",
    })
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False
    assert "cells" in v["error"]


def test_run_generate_poster_rejects_non_full_slide(
    generate_illustrations, monkeypatch, tmp_path, capsys
):
    # Poster mode must fail fast if a slide isn't FULL or carries a Safe zone.
    gi = generate_illustrations
    outline = _write_poster_outline(tmp_path, text="nope")
    # Override the single slide with a non-FULL one to trip the invariant.
    data = yaml.safe_load(outline.read_text(encoding="utf-8"))
    data["slides"][0]["format"] = "IMG+TXT"
    outline.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    outline_dict = gi.parse_outline(str(outline))
    _write_manifest(tmp_path, ["gemini-3-pro-image"])
    gen_calls = []
    _stub_generate(gi, monkeypatch, outline_dict, str(tmp_path), gen_calls)

    with pytest.raises(SystemExit) as exc:
        gi.run_generate(str(outline), ["all"])

    assert exc.value.code == 1
    assert gen_calls == []
    assert "poster-theatrical" in capsys.readouterr().err


def test_run_generate_poster_validates_whole_outline_not_just_subset(
    generate_illustrations, monkeypatch, tmp_path, capsys
):
    # Even generating a single valid slide must fail if another slide in the
    # outline violates the poster invariant — the invariant is deck-level.
    gi = generate_illustrations
    outline = _write_outline(
        tmp_path, model="gemini-3-pro-image",
        composition="poster-theatrical", embedded_footer="jbaruch • Devoxx 2026",
        slides=[
            {"n": 1, "chapter": "c", "title": "Good", "format": "FULL",
             "text_overlay": "ok", "image_prompt": "[STYLE ANCHOR] a thing"},
            {"n": 2, "chapter": "c", "title": "Bad", "format": "IMG+TXT",
             "text_overlay": "nope", "image_prompt": "[STYLE ANCHOR] another thing"},
        ],
    )
    outline_dict = gi.parse_outline(str(outline))
    _write_manifest(tmp_path, ["gemini-3-pro-image"])
    gen_calls = []
    _stub_generate(gi, monkeypatch, outline_dict, str(tmp_path), gen_calls)

    with pytest.raises(SystemExit) as exc:
        gi.run_generate(str(outline), ["1"])  # subset: only slide 1

    assert exc.value.code == 1
    assert gen_calls == []
    assert "2" in capsys.readouterr().err  # slide 2 named as the offender


def test_gate_rejects_rel_path_traversal(generate_illustrations, tmp_path):
    # A rel_path escaping style-explore/ (../ or absolute) must not count as
    # render evidence, even if a file exists there.
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    (tmp_path / "evil.png").write_bytes(b"img")  # a real file OUTSIDE style-explore/
    _write_raw_manifest(tmp_path, {
        "schema_version": 1, "outline": "outline.yaml", "outline_dir": tmp_path.name,
        "models_rendered_ok": ["gemini-3-pro-image"],
        "cells": [{
            "style": "S", "format": "FULL", "model": "gemini-3-pro-image",
            "model_resolved": "gemini-3-pro-image", "status": "OK",
            "rel_path": "../evil.png",
        }],
    })
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False
    assert v["rendered_models"] == []


def test_gate_fails_when_outline_dir_missing(generate_illustrations, tmp_path):
    # outline_dir is always written by our script; a manifest missing it is
    # hand-edited/stale and must fail closed (can't bypass cross-talk detection).
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    se = tmp_path / "style-explore"
    se.mkdir(exist_ok=True)
    rel = "style/full/gemini-3-pro-image.png"
    (se / rel).parent.mkdir(parents=True, exist_ok=True)
    (se / rel).write_bytes(b"img")
    _write_raw_manifest(tmp_path, {
        "schema_version": 1, "outline": "outline.yaml",  # no outline_dir
        "models_rendered_ok": ["gemini-3-pro-image"],
        "cells": [{
            "style": "S", "format": "FULL", "model": "gemini-3-pro-image",
            "model_resolved": "gemini-3-pro-image", "status": "OK",
            "rel_path": rel,
        }],
    })
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False
    assert "outline_dir" in v["error"]


def test_poster_embed_directive_normalizes_embedded_quotes(generate_illustrations):
    # A title/footer containing double quotes must not create nested double
    # quotes in the directive (they degrade model compliance).
    gi = generate_illustrations
    d = gi.apply_poster_embed_directive('a scene', 'He said "Hello"', 'tag "x"')
    # The wrapping quotes around title/footer remain, but embedded ones are now '
    assert '""' not in d
    assert "He said 'Hello'" in d
    assert "tag 'x'" in d


def test_gate_fails_closed_on_non_dict_manifest(generate_illustrations, tmp_path):
    # A parseable-but-non-object rendered.json (e.g. a list) must fail closed,
    # not crash with AttributeError.
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    se = tmp_path / "style-explore"
    se.mkdir(exist_ok=True)
    (se / "rendered.json").write_text("[1, 2, 3]")
    v = gi.check_style_explore(str(outline))
    assert v["gate_passed"] is False
    assert "not a JSON object" in v["error"]


def test_gate_fails_closed_on_non_string_cell_model(generate_illustrations, tmp_path):
    # A non-string model value in a cell must be skipped, not crash resolve_model_id.
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, model="gemini-3-pro-image")
    se = tmp_path / "style-explore"
    se.mkdir(exist_ok=True)
    rel = "style/full/x.png"
    (se / rel).parent.mkdir(parents=True, exist_ok=True)
    (se / rel).write_bytes(b"img")
    _write_raw_manifest(tmp_path, {
        "schema_version": 1, "outline": "outline.yaml", "outline_dir": tmp_path.name,
        "models_rendered_ok": [],
        "cells": [{
            "style": "S", "format": "FULL", "model": ["not", "a", "string"],
            "model_resolved": None, "status": "OK", "rel_path": rel,
        }],
    })
    v = gi.check_style_explore(str(outline))  # must not raise
    assert v["gate_passed"] is False
