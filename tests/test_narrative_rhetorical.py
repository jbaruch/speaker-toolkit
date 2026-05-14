"""Tests for extract-narrative.py and check-rhetorical.py."""

import copy
from pathlib import Path

import pytest
import yaml


FIXTURE = Path(__file__).parent / "fixtures" / "outline-example.yaml"


@pytest.fixture(scope="session")
def outline(outline_schema):
    return outline_schema.load_outline(FIXTURE)


@pytest.fixture(scope="session")
def base_data():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


# ── extract-narrative.py ─────────────────────────────────────────────


def test_narrative_renders_title(extract_narrative, outline):
    out = extract_narrative.render(outline)
    assert out.startswith("# Demo Talk — Narrative Read")


def test_narrative_includes_chapter_headings(extract_narrative, outline):
    out = extract_narrative.render(outline)
    assert "### The Setup" in out
    assert "### The Turn" in out
    assert "### The Close" in out


def test_narrative_omits_image_prompts(extract_narrative, outline):
    out = extract_narrative.render(outline)
    assert "STYLE ANCHOR" not in out
    assert "crumpled paper receipt" not in out


def test_narrative_omits_script_dialogue(extract_narrative, outline):
    """Speaker dialogue lives in script.md, not narrative.md."""
    out = extract_narrative.render(outline)
    assert "Not for a coffee. Not for a flight." not in out
    assert "Doers, write the rule." not in out


def test_narrative_omits_applied_patterns(extract_narrative, outline):
    """Structural taxonomy lives in rhetorical-review.md, not narrative.md."""
    out = extract_narrative.render(outline)
    assert "opening-punch" not in out
    assert "call-to-adventure" not in out
    assert "applied_patterns" not in out


def test_narrative_includes_argument_beats(extract_narrative, outline):
    out = extract_narrative.render(outline)
    # First chapter's first beat
    assert "Open cold with the receipt" in out
    # Third chapter's beat
    assert "Pay off the master story" in out


def test_narrative_renders_slide_refs(extract_narrative, outline):
    out = extract_narrative.render(outline)
    # Argument beats carry slide_refs — those should appear as a marker
    assert "slide 1" in out
    assert "slide 11" in out


def test_narrative_marks_cuttable_chapters(extract_narrative, outline):
    out = extract_narrative.render(outline)
    # No cuttable chapter in the base fixture — verify mutation surfaces it
    pass  # see test_narrative_marks_cuttable below


def test_narrative_marks_cuttable_chapter(extract_narrative, outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["chapters"][0]["cuttable"] = True
    outline = outline_schema.Outline.model_validate(data)
    out = extract_narrative.render(outline)
    assert "*cuttable*" in out


def test_narrative_renders_thesis_when_present(
    extract_narrative, outline_schema, base_data,
):
    data = copy.deepcopy(base_data)
    data["talk"]["thesis"] = "A two-sentence thesis goes here."
    outline = outline_schema.Outline.model_validate(data)
    out = extract_narrative.render(outline)
    assert "## Thesis" in out
    assert "two-sentence thesis" in out


# ── check-rhetorical.py — happy path ─────────────────────────────────


def test_rhetorical_clean_fixture_has_no_flags(check_rhetorical, outline):
    content, flag_count = check_rhetorical.render(outline)
    assert flag_count == 0
    assert "✅ Summary — no FLAGs" in content


def test_rhetorical_passes_opening_punch(check_rhetorical, outline):
    content, _ = check_rhetorical.render(outline)
    assert "### Opening PUNCH — ✅ **PASS**" in content


def test_rhetorical_reports_big_idea_location(check_rhetorical, outline):
    content, _ = check_rhetorical.render(outline)
    # Fixture has big_idea on slide 5 (Call to Adventure)
    assert 'slide 5: "Call to Adventure"' in content


def test_rhetorical_reports_thesis_ordering(check_rhetorical, outline):
    content, _ = check_rhetorical.render(outline)
    # Fixture: preview slide 5, payoff slide 11
    assert "preview slide 5 → payoff slide 11" in content


def test_rhetorical_passes_sparkline_when_complete(check_rhetorical, outline_schema, base_data):
    """Fixture's architecture is sparkline with call-to-adventure, new-bliss,
    star-moment. Add call-to-action to complete the set."""
    data = copy.deepcopy(base_data)
    # Slide 10 already has call-to-action in the fixture
    outline = outline_schema.Outline.model_validate(data)
    content, _ = check_rhetorical.render(outline)
    assert "### Call to Adventure — ✅ **PASS**" in content
    assert "### Call to Action — ✅ **PASS**" in content
    assert "### New Bliss — ✅ **PASS**" in content
    assert "### S.T.A.R. moments — ✅ **PASS**" in content


def test_rhetorical_reports_master_story_threading(check_rhetorical, outline):
    content, _ = check_rhetorical.render(outline)
    assert "### Master story threading — ✅ **PASS**" in content
    assert "`pandy`" in content
    assert "introduce@slide 3" in content


def test_rhetorical_reports_callback_chains(check_rhetorical, outline):
    content, _ = check_rhetorical.render(outline)
    assert "`receipt-motif`" in content


def test_rhetorical_includes_duration_accounting(check_rhetorical, outline):
    content, _ = check_rhetorical.render(outline)
    assert "### Duration accounting" in content


# ── check-rhetorical.py — FLAG cases via mutation ────────────────────


def test_rhetorical_flags_missing_opening_punch(check_rhetorical, outline_schema, base_data):
    data = copy.deepcopy(base_data)
    # Remove opening-punch from slide 1
    data["slides"][0]["applied_patterns"] = [
        p for p in data["slides"][0]["applied_patterns"]
        if p.get("id") != "opening-punch"
    ]
    outline = outline_schema.Outline.model_validate(data)
    content, flag_count = check_rhetorical.render(outline)
    assert flag_count >= 1
    assert "### Opening PUNCH — ⚠️  **FLAG**" in content


def test_rhetorical_flags_sparkline_missing_call_to_action(
    check_rhetorical, outline_schema, base_data,
):
    data = copy.deepcopy(base_data)
    # Remove call-to-action from slide 10
    slide_10 = next(s for s in data["slides"] if s["n"] == 10)
    slide_10["applied_patterns"] = [
        p for p in slide_10["applied_patterns"]
        if p.get("id") != "call-to-action"
    ]
    outline = outline_schema.Outline.model_validate(data)
    content, flag_count = check_rhetorical.render(outline)
    assert flag_count >= 1
    assert "### Call to Action — ⚠️  **FLAG**" in content


def test_rhetorical_flags_too_many_inoculations(
    check_rhetorical, outline_schema, base_data,
):
    data = copy.deepcopy(base_data)
    # Fixture has 1 inoculation; add 3 more to push past the ≤3 limit
    for slide_n, vector in [(8, "fear"), (10, "obstacles"), (11, "comfort-zone")]:
        slide = next(s for s in data["slides"] if s["n"] == slide_n)
        slide.setdefault("applied_patterns", []).append({
            "id": "inoculation",
            "resistance_vector": vector,
        })
    outline = outline_schema.Outline.model_validate(data)
    content, flag_count = check_rhetorical.render(outline)
    assert flag_count >= 1
    assert "Inoculation count — ⚠️  **FLAG**" in content


def test_rhetorical_na_for_non_sparkline_arch(
    check_rhetorical, outline_schema, base_data,
):
    data = copy.deepcopy(base_data)
    data["talk"]["architecture"] = "talklet"
    # Remove sparkline-only patterns since they only make sense in sparkline talks
    # (test would otherwise fail because call-to-adventure has big_idea_text and
    # we'd need to find another slide to be the big_idea)
    # For this test, just verify the N/A is emitted regardless
    outline = outline_schema.Outline.model_validate(data)
    content, _ = check_rhetorical.render(outline)
    assert "Sparkline elements — — *N/A*" in content


def test_rhetorical_strict_mode_returns_flag_count(check_rhetorical, outline_schema, base_data):
    """Verify the render() function returns the flag count for --strict gating."""
    data = copy.deepcopy(base_data)
    data["slides"][0]["applied_patterns"] = [
        p for p in data["slides"][0]["applied_patterns"]
        if p.get("id") != "opening-punch"
    ]
    outline = outline_schema.Outline.model_validate(data)
    _, flag_count = check_rhetorical.render(outline)
    assert flag_count >= 1
