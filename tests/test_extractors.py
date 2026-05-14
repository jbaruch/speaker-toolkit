"""Tests for extract-script.py and extract-slides.py against the fixture outline."""

from pathlib import Path

import pytest


FIXTURE = Path(__file__).parent / "fixtures" / "outline-example.yaml"


@pytest.fixture(scope="session")
def outline(outline_schema):
    return outline_schema.load_outline(FIXTURE)


# ── extract-script.py ────────────────────────────────────────────────


def test_script_renders_with_title(extract_script, outline):
    out = extract_script.render(outline)
    assert out.startswith("# Demo Talk — Script")


def test_script_includes_pacing_metadata(extract_script, outline):
    out = extract_script.render(outline)
    assert "140–160 WPM" in out


def test_script_emits_slide_headers(extract_script, outline):
    out = extract_script.render(outline)
    assert "## Slide 1 — Cold Open" in out
    assert "## Slide 11 — New Bliss" in out


def test_script_omits_image_prompt(extract_script, outline):
    """Image prompts belong in slides.md, not script.md."""
    out = extract_script.render(outline)
    assert "STYLE ANCHOR" not in out
    assert "image_prompt" not in out.lower()


def test_script_omits_applied_patterns(extract_script, outline):
    """Pattern application metadata is build/review concern, not rehearsal."""
    out = extract_script.render(outline)
    assert "opening-punch" not in out
    assert "call-to-adventure" not in out


def test_script_emits_cues_in_bold_brackets(extract_script, outline):
    out = extract_script.render(outline)
    assert "**[SLIDE 1 UP — no title, no bio, no branding]**" in out


def test_script_emits_parentheticals_as_italics(extract_script, outline):
    out = extract_script.render(outline)
    # Slide 1 has "(beat)" — should render as *(beat)*
    assert "*(beat)*" in out


def test_script_emits_text_overlay_on_screen(extract_script, outline):
    out = extract_script.render(outline)
    # Slide 2's overlay should appear as a blockquote
    assert "VALIDATION REMOVED · TESTS DELETED · TAX MISCOMPUTED" in out
    assert "*On screen:*" in out


def test_script_skips_text_overlay_when_none(extract_script, outline):
    """When text_overlay == 'none', don't emit an empty On-screen block."""
    out = extract_script.render(outline)
    # Slide 1 has text_overlay: none — should not have an On-screen block for slide 1
    slide1_section = out.split("## Slide 1 — Cold Open")[1].split("## Slide 2")[0]
    assert "*On screen:*" not in slide1_section


def test_script_renders_single_speaker_without_attribution(extract_script, outline):
    """Single-speaker fixture should not have **SPEAKER ONE** headers."""
    out = extract_script.render(outline)
    assert "**SPEAKER ONE**" not in out


# ── extract-slides.py ────────────────────────────────────────────────


def test_slides_renders_with_title(extract_slides, outline):
    out = extract_slides.render(outline)
    assert out.startswith("# Demo Talk — Slides")


def test_slides_emits_budget_arithmetic(extract_slides, outline):
    out = extract_slides.render(outline)
    # 8 entries, slide 2 has 4 builds → expanded count = 7 + 4 = 11
    assert "slide budget 20" in out
    assert "entries 8" in out
    assert "deck count (builds expanded) 11" in out


def test_slides_emits_format_tags(extract_slides, outline):
    out = extract_slides.render(outline)
    assert "*[FULL]*" in out
    assert "*[EXCEPTION]*" in out
    assert "*[IMG+TXT]*" in out


def test_slides_emits_image_prompts(extract_slides, outline):
    """Image prompts go in slides.md (consumed by the illustrations pipeline)."""
    out = extract_slides.render(outline)
    assert "STYLE ANCHOR" in out
    assert "crumpled paper receipt" in out


def test_slides_emits_builds(extract_slides, outline):
    out = extract_slides.render(outline)
    assert "**Builds:** 4 steps" in out
    assert "`build-00`: Empty triptych frame" in out


def test_slides_emits_exception_justification(extract_slides, outline):
    out = extract_slides.render(outline)
    assert "EXCEPTION justification" in out


def test_slides_marks_big_idea(extract_slides, outline):
    out = extract_slides.render(outline)
    assert "🎯 Big Idea slide" in out


def test_slides_emits_patterns(extract_slides, outline):
    out = extract_slides.render(outline)
    assert "opening-punch" in out
    assert "flavors=['personal', 'unexpected']" in out
    assert "call-to-adventure" in out


def test_slides_emits_callbacks(extract_slides, outline):
    out = extract_slides.render(outline)
    assert "plant: receipt-motif" in out
    assert "pay: receipt-motif" in out


def test_slides_omits_speaker_dialogue(extract_slides, outline):
    """Speaker dialogue belongs in script.md, not slides.md."""
    out = extract_slides.render(outline)
    # Lines that appear ONLY in script (not in text_overlay or visual)
    assert "Not for a coffee. Not for a flight." not in out
    assert "Doers, write the rule." not in out


def test_slides_omits_interludes(extract_slides, outline_schema):
    """The slides extractor walks slides[] only — interludes never appear in
    slides.md, even if the outline declares them."""
    import copy
    import yaml as _yaml

    data = _yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    data["interludes"] = [{
        "id": "demo-test-only",
        "after_slide": 1,
        "chapter": "ch1",
        "title": "DEMO TEST — Should Not Appear In slides.md",
        "script": [
            {"cue": "TERMINAL UP"},
            {"line": "This line should only appear in script.md."},
        ],
    }]
    outline_with_interlude = outline_schema.Outline.model_validate(data)
    out = extract_slides.render(outline_with_interlude)
    assert "demo-test-only" not in out
    assert "DEMO TEST" not in out
    assert "Should Not Appear" not in out


# ── Interlude rendering in script (separate small outline) ───────────


def test_script_interleaves_interludes_after_anchor(extract_script, outline_schema):
    """Build a tiny outline with one interlude anchored after_slide=1, verify
    it appears between slide 1 and slide 2 in the rendered script."""
    import copy
    import yaml

    data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    data["interludes"] = [{
        "id": "demo-X",
        "after_slide": 1,
        "chapter": "ch1",
        "title": "DEMO X — Live Terminal",
        "script": [
            {"cue": "TERMINAL UP"},
            {"line": "Watch this."},
        ],
    }]
    outline_with_interlude = outline_schema.Outline.model_validate(data)
    out = extract_script.render(outline_with_interlude)

    # Verify ordering: slide 1 header appears before interlude header,
    # interlude appears before slide 2 header
    s1 = out.index("## Slide 1 — Cold Open")
    interlude = out.index("## DEMO X — Live Terminal")
    s2 = out.index("## Slide 2 — The Three Failures")
    assert s1 < interlude < s2
