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


def test_narrative_full_renders_per_slide_walk(extract_narrative, outline):
    """Full mode walks slides[] one line each — not the argument beats."""
    out = extract_narrative.render(outline)
    assert "## The Deck, Slide by Slide" in out
    # One line per slide, keyed by slide number + title
    assert "**1. Cold Open**" in out
    assert "**11. New Bliss + Thanks**" in out
    # The argument-beat prose must NOT appear in the full (slide) view
    assert "Open cold with the receipt" not in out
    assert "Pay off the master story" not in out


def test_narrative_slide_synopsis_prefers_overlay_then_visual(
    extract_narrative, outline,
):
    out = extract_narrative.render(outline)
    # Slide 2 has a text_overlay — use it
    assert "VALIDATION REMOVED · TESTS DELETED · TAX MISCOMPUTED" in out
    # Slide 1's text_overlay is the literal "none" — fall back to its visual
    assert "Receipt screenshot with one line circled in red." in out


def test_narrative_inlines_interlude_at_anchor(
    extract_narrative, outline_schema, base_data,
):
    """An interlude renders as a live-demo line right after its anchor slide."""
    data = copy.deepcopy(base_data)
    data["interludes"] = [{
        "id": "demo-vat",
        "after_slide": 8,
        "title": "Live coding: agent rewrites the VAT calc",
        "chapter": "ch2",
        "script": [{"line": "Watch what happens."}],
    }]
    outline = outline_schema.Outline.model_validate(data)
    out = extract_narrative.render(outline)
    assert "- *Live coding: agent rewrites the VAT calc — live demo*" in out
    # It sits between slide 8 and slide 10
    assert out.index("**8. Master Story Recall**") < out.index("Live coding")
    assert out.index("Live coding") < out.index("**10. Call to Action**")


def test_narrative_omits_cuttable_marker_when_none(extract_narrative, outline):
    """Base fixture has no cuttable chapters — the marker must NOT appear."""
    out = extract_narrative.render(outline)
    assert "*cuttable*" not in out


def test_narrative_marks_cuttable_chapter(extract_narrative, outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["chapters"][0]["cuttable"] = True
    outline = outline_schema.Outline.model_validate(data)
    out = extract_narrative.render(outline)
    assert "*cuttable*" in out


def test_narrative_renders_tldr_when_present(extract_narrative, outline):
    """The fixture's tldr renders under a TL;DR heading, bullets preserved."""
    out = extract_narrative.render(outline)
    assert "## TL;DR" in out
    assert "Agents ship code that violates constraints" in out
    assert "- They lack authority to push back." in out


def test_narrative_never_reprints_full_thesis(
    extract_narrative, outline_schema, base_data,
):
    """The elaborated talk.thesis must never appear — only the tldr does."""
    data = copy.deepcopy(base_data)
    data["talk"]["thesis"] = "An elaborated multi-paragraph thesis goes here."
    outline = outline_schema.Outline.model_validate(data)
    out = extract_narrative.render(outline)
    assert "elaborated multi-paragraph thesis" not in out
    assert "## TL;DR" in out


# ── extract-narrative.py — partial (narrative-phase) rendering ───────


def test_narrative_partial_tldr_only_stub(
    extract_narrative, outline_schema, base_data,
):
    """Phase 1 stub: tldr renders, chapter body is a 'not yet authored' note."""
    data = {"talk": copy.deepcopy(base_data["talk"])}
    data["talk"]["tldr"] = "Treat context as a first-class artifact."
    partial = outline_schema.PartialOutline.model_validate(data)
    out = extract_narrative.render(partial)
    assert "## TL;DR" in out
    assert "Treat context as a first-class artifact." in out
    assert "Narrative arc not yet authored" in out
    assert "### The Setup" not in out  # no chapters yet


def test_narrative_partial_renders_chapters_without_slides(
    extract_narrative, outline_schema, base_data,
):
    """Phase 2: chapters present, slides absent — full chapter body renders."""
    chapters = copy.deepcopy(base_data["chapters"])
    for c in chapters:
        for beat in c.get("argument_beats", []):
            beat["slide_refs"] = []  # no slides exist yet in the narrative phase
    data = {"talk": copy.deepcopy(base_data["talk"]), "chapters": chapters}
    partial = outline_schema.PartialOutline.model_validate(data)
    out = extract_narrative.render(partial)
    assert "### The Setup" in out
    assert "### The Turn" in out
    assert "Open cold with the receipt" in out
    assert "Narrative arc not yet authored" not in out


def test_narrative_cli_partial_renders_talk_only(
    extract_narrative, base_data, tmp_path, capsys,
):
    """CLI --partial renders a talk-only outline to stdout."""
    data = {"talk": copy.deepcopy(base_data["talk"])}
    path = tmp_path / "partial.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    rc = extract_narrative.main(["extract-narrative.py", "--partial", str(path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("# Demo Talk — Narrative Read")


def test_narrative_cli_full_mode_rejects_slideless_outline(
    extract_narrative, base_data, tmp_path, capsys,
):
    """Without --partial, a slides-less outline fails full validation (exit 1)."""
    data = {"talk": copy.deepcopy(base_data["talk"])}
    path = tmp_path / "slideless.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    rc = extract_narrative.main(["extract-narrative.py", str(path)])
    assert rc == 1
    assert "failed to load" in capsys.readouterr().err


# ── check-rhetorical.py — happy path ─────────────────────────────────


def test_rhetorical_clean_fixture_has_no_flags(check_rhetorical, outline):
    content, flag_count = check_rhetorical.render(outline)
    assert flag_count == 0
    assert "✅ Summary — no FLAGs" in content


def test_rhetorical_passes_opening_punch(check_rhetorical, outline):
    content, _ = check_rhetorical.render(outline)
    assert "### Opening PUNCH — ✅ **PASS**" in content


# ── check-rhetorical.py — register coverage (walk-around) ────────────


def _outline_from(outline_schema, base_data, mutate):
    data = copy.deepcopy(base_data)
    mutate(data)
    return outline_schema.Outline.model_validate(data)


def test_register_coverage_passes_when_all_four_answered(
    check_rhetorical, outline,
):
    content, flag_count = check_rhetorical.render(outline)
    assert "### Register coverage — ✅ **PASS**" in content
    assert flag_count == 0


def test_register_coverage_flags_missing_register(
    check_rhetorical, outline_schema, base_data,
):
    """Dropping the C+D walk-around leaves a heterogeneous room half-answered."""
    def mutate(data):
        for slide in data["slides"]:
            slide["applied_patterns"] = [
                p for p in slide.get("applied_patterns", [])
                if p.get("id") != "walk-around" or p.get("registers") != ["C", "D"]
            ]
    o = _outline_from(outline_schema, base_data, mutate)
    content, flag_count = check_rhetorical.render(o)
    assert "Register coverage" in content
    assert "['C', 'D'] unanswered" in content
    assert flag_count >= 1


def test_register_coverage_flags_heterogeneous_with_no_walk_around(
    check_rhetorical, outline_schema, base_data,
):
    def mutate(data):
        for slide in data["slides"]:
            slide["applied_patterns"] = [
                p for p in slide.get("applied_patterns", [])
                if p.get("id") != "walk-around"
            ]
    o = _outline_from(outline_schema, base_data, mutate)
    content, flag_count = check_rhetorical.render(o)
    assert "no claim declares a walk-around" in content
    assert flag_count >= 1


def test_register_match_flags_unmatched_homogeneous_room(
    check_rhetorical, outline_schema, base_data,
):
    """A room declared homogeneous on C, with no walk-around answering C."""
    def mutate(data):
        data["talk"]["audience_spread"] = "homogeneous"
        data["talk"]["dominant_register"] = "C"
        for slide in data["slides"]:
            slide["applied_patterns"] = [
                p for p in slide.get("applied_patterns", [])
                if p.get("id") != "walk-around" or p.get("registers") != ["C", "D"]
            ]
    o = _outline_from(outline_schema, base_data, mutate)
    content, flag_count = check_rhetorical.render(o)
    assert "Register match" in content
    assert "no walk-around answers it" in content
    assert flag_count >= 1


def test_register_match_passes_when_dominant_answered(
    check_rhetorical, outline_schema, base_data,
):
    def mutate(data):
        data["talk"]["audience_spread"] = "homogeneous"
        data["talk"]["dominant_register"] = "C"
    o = _outline_from(outline_schema, base_data, mutate)
    content, _ = check_rhetorical.render(o)
    assert "### Register match — ✅ **PASS**" in content


def test_register_match_flags_homogeneous_with_zero_walk_arounds(
    check_rhetorical, outline_schema, base_data,
):
    """A homogeneous room with no audit at all must not pass as N/A.

    Declaring `dominant_register: C` and supplying no register evidence is an
    unanswered claim, not an inapplicable check.
    """
    def mutate(data):
        data["talk"]["audience_spread"] = "homogeneous"
        data["talk"]["dominant_register"] = "C"
        for slide in data["slides"]:
            slide["applied_patterns"] = [
                p for p in slide.get("applied_patterns", [])
                if p.get("id") != "walk-around"
            ]
    o = _outline_from(outline_schema, base_data, mutate)
    content, flag_count = check_rhetorical.render(o)
    assert "Register match — ⚠️" in content
    assert "no claim declares a walk-around answering it" in content
    assert flag_count >= 1
    assert "N/A" not in content.split("### Register match")[1].split("###")[0]


def test_register_coverage_flags_walk_around_without_registers(
    check_rhetorical, outline_schema, base_data,
):
    """A walk-around with no `registers:` is unverifiable, not absent."""
    def mutate(data):
        for slide in data["slides"]:
            for p in slide.get("applied_patterns", []):
                if p.get("id") == "walk-around":
                    p.pop("registers", None)
    o = _outline_from(outline_schema, base_data, mutate)
    content, flag_count = check_rhetorical.render(o)
    assert "no `registers:` set" in content
    assert flag_count >= 1


def test_register_coverage_counts_interlude_walk_around(
    check_rhetorical, outline_schema, base_data,
):
    """An interlude is a located, claim-bearing unit — its walk-around counts.

    A live demo answering "how does it work, in what order" is a B answer no
    slide can match. Only talk-level (which has no claim to locate) is barred.
    """
    def mutate(data):
        # Drop the slide-level C+D audit, and answer C+D from a demo instead.
        for slide in data["slides"]:
            slide["applied_patterns"] = [
                p for p in slide.get("applied_patterns", [])
                if p.get("id") != "walk-around" or p.get("registers") != ["C", "D"]
            ]
        data["interludes"] = [{
            "id": "demo-migration",
            "after_slide": 8,
            "title": "Live: migrating a service",
            "chapter": "ch2",
            "script": [{"line": "Watch who has to be paged."}],
            "applied_patterns": [{"id": "walk-around", "registers": ["C", "D"]}],
        }]
    o = _outline_from(outline_schema, base_data, mutate)
    content, flag_count = check_rhetorical.render(o)
    assert "### Register coverage — ✅ **PASS**" in content
    assert "interlude demo-migration" in content
    assert flag_count == 0


def test_unannotated_walk_around_label_tracks_spread(
    check_rhetorical, outline_schema, base_data,
):
    """The section header must stay 'Register match' for a homogeneous room.

    A homogeneous run that emits 'Register coverage' breaks the header any
    reader — or downstream parse — keys on.
    """
    def mutate(data):
        data["talk"]["audience_spread"] = "homogeneous"
        data["talk"]["dominant_register"] = "A"
        for slide in data["slides"]:
            for p in slide.get("applied_patterns", []):
                if p.get("id") == "walk-around":
                    p.pop("registers", None)
    o = _outline_from(outline_schema, base_data, mutate)
    content, _ = check_rhetorical.render(o)
    assert "### Register match — ⚠️" in content
    assert "### Register coverage" not in content


def test_register_coverage_flags_unannotated_before_absent(
    check_rhetorical, outline_schema, base_data,
):
    """The unannotated message must win over 'no claim declares a walk-around'.

    Reporting an unannotated walk-around as absent misdescribes the outline.
    """
    def mutate(data):
        data["talk"]["audience_spread"] = "homogeneous"
        data["talk"]["dominant_register"] = "A"
        for slide in data["slides"]:
            for p in slide.get("applied_patterns", []):
                if p.get("id") == "walk-around":
                    p.pop("registers", None)
    o = _outline_from(outline_schema, base_data, mutate)
    content, _ = check_rhetorical.render(o)
    assert "no `registers:` set" in content
    assert "no claim declares a walk-around" not in content


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
