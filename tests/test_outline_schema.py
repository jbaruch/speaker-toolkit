"""Tests for outline_schema.py — pydantic validators on the outline source-of-truth."""

import copy
import os
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError


FIXTURE = Path(__file__).parent / "fixtures" / "outline-example.yaml"


@pytest.fixture(scope="session")
def base_data():
    """Parsed YAML of the canonical valid fixture — returned as a dict.

    Tests use copy.deepcopy(base_data) and mutate one field to assert a
    specific validator fires. Provides fixed test data per testing-standards;
    each test owns its mutation."""
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


# ── Happy path ────────────────────────────────────────────────────────


def test_fixture_loads_clean(outline_schema):
    outline = outline_schema.load_outline(FIXTURE)
    assert outline.talk.title == "Demo Talk"
    assert len(outline.chapters) == 3
    assert len(outline.slides) == 8


def test_pattern_enum_discovered(outline_schema):
    # 77 patterns + 25 antipatterns per _index.md taxonomy
    assert len(outline_schema.PATTERN_IDS) == 77
    assert len(outline_schema.ANTIPATTERN_IDS) == 25
    assert "sparkline" in outline_schema.PATTERN_IDS
    assert "slideuments" in outline_schema.ANTIPATTERN_IDS


# ── Talk-level validators ────────────────────────────────────────────


def test_rejects_unknown_architecture(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["architecture"] = "freeform-vibes"
    with pytest.raises(ValidationError, match="architecture"):
        outline_schema.Outline.model_validate(data)


def test_rejects_empty_speakers(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["speakers"] = []
    with pytest.raises(ValidationError):
        outline_schema.Outline.model_validate(data)


# ── Slide-level validators ───────────────────────────────────────────


def test_rejects_unknown_chapter_ref(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][0]["chapter"] = "ch99"
    with pytest.raises(ValidationError, match="unknown chapter"):
        outline_schema.Outline.model_validate(data)


def test_rejects_duplicate_slide_numbers(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    # Add a duplicate slide entry without breaking slide_refs (which now validate too)
    last = copy.deepcopy(data["slides"][-1])
    last["n"] = data["slides"][0]["n"]
    data["slides"].append(last)
    data["talk"]["slide_budget"] = 99
    with pytest.raises(ValidationError, match="duplicate slide numbers"):
        outline_schema.Outline.model_validate(data)


def test_rejects_out_of_order_slides(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    # Swap first two slide numbers without duplicating
    data["slides"][0]["n"], data["slides"][1]["n"] = (
        data["slides"][1]["n"], data["slides"][0]["n"],
    )
    with pytest.raises(ValidationError, match="ascending order"):
        outline_schema.Outline.model_validate(data)


def test_rejects_exception_without_justification(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    slide = next(s for s in data["slides"] if s["format"] == "EXCEPTION")
    slide["format_justification"] = ""
    with pytest.raises(ValidationError, match="format_justification"):
        outline_schema.Outline.model_validate(data)


# ── big_idea singleton ───────────────────────────────────────────────


def test_rejects_zero_big_ideas(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    for s in data["slides"]:
        s["big_idea"] = False
    with pytest.raises(ValidationError, match="big_idea"):
        outline_schema.Outline.model_validate(data)


def test_rejects_multiple_big_ideas(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][0]["big_idea"] = True
    data["slides"][1]["big_idea"] = True
    with pytest.raises(ValidationError, match="big_idea"):
        outline_schema.Outline.model_validate(data)


# ── Speaker attribution ──────────────────────────────────────────────


def test_rejects_speaker_on_single_speaker_line(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    # Find first line item and attribute it (illegal in single-speaker mode)
    for slide in data["slides"]:
        for item in slide.get("script", []):
            if item.get("line") is not None:
                item["speaker"] = "Speaker One"
                break
        else:
            continue
        break
    with pytest.raises(ValidationError, match="single-speaker talk must not"):
        outline_schema.Outline.model_validate(data)


def test_requires_speaker_on_multi_speaker_line(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["speakers"] = ["Speaker One", "Speaker Two"]
    with pytest.raises(ValidationError, match="multi-speaker talk requires"):
        outline_schema.Outline.model_validate(data)


def test_rejects_unknown_speaker_attribution(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["speakers"] = ["Speaker One", "Speaker Two"]
    # Now attribute every line, but use a name not in talk.speakers
    for slide in data["slides"]:
        for item in slide.get("script", []):
            if item.get("line") is not None:
                item["speaker"] = "Speaker Three"
    with pytest.raises(ValidationError, match="not in talk.speakers"):
        outline_schema.Outline.model_validate(data)


def test_accepts_valid_multi_speaker(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["speakers"] = ["Speaker One", "Speaker Two"]
    for slide in data["slides"]:
        for item in slide.get("script", []):
            if item.get("line") is not None:
                item["speaker"] = "Speaker One"
    outline = outline_schema.Outline.model_validate(data)
    assert len(outline.talk.speakers) == 2


# ── Slide budget ─────────────────────────────────────────────────────


def test_rejects_slide_budget_exceeded(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["slide_budget"] = 5
    with pytest.raises(ValidationError, match="slide budget exceeded"):
        outline_schema.Outline.model_validate(data)


def test_builds_count_toward_budget(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    # Fixture has 8 slide entries; slide n=2 has 4 build steps.
    # Expanded count = 7 (non-build slides) + 4 (builds on slide 2) = 11
    data["talk"]["slide_budget"] = 11
    outline_schema.Outline.model_validate(data)  # exactly at budget — OK
    data["talk"]["slide_budget"] = 10
    with pytest.raises(ValidationError, match="slide budget exceeded"):
        outline_schema.Outline.model_validate(data)


# ── Pattern validation ───────────────────────────────────────────────


def test_rejects_antipattern_in_outline(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["applied_patterns"].append({"id": "slideuments"})
    with pytest.raises(ValidationError, match="antipattern"):
        outline_schema.Outline.model_validate(data)


def test_rejects_unknown_pattern_id(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["applied_patterns"].append({"id": "fictional-pattern"})
    with pytest.raises(ValidationError, match="not found"):
        outline_schema.Outline.model_validate(data)


def test_rejects_instance_field_on_wrong_pattern(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    # flavors only belongs on opening-punch — putting it on bookends should fail
    data["talk"]["applied_patterns"].append({
        "id": "bookends",
        "flavors": ["personal"],
    })
    with pytest.raises(ValidationError, match="does not accept"):
        outline_schema.Outline.model_validate(data)


def test_accepts_deliver_phase_pattern(outline_schema, base_data):
    # `mentor` lives in deliver/ but shapes the outline — must be accepted
    data = copy.deepcopy(base_data)
    data["talk"]["applied_patterns"].append({"id": "mentor"})
    outline = outline_schema.Outline.model_validate(data)
    assert any(p.id == "mentor" for p in outline.talk.applied_patterns)


# ── Callback ledger ──────────────────────────────────────────────────


def test_rejects_unpaid_callback_plant(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    # Remove the pay for receipt-motif (currently on slide n=7)
    for slide in data["slides"]:
        slide["callbacks"] = [
            cb for cb in slide.get("callbacks", [])
            if not (cb.get("kind") == "pay" and cb.get("id") == "receipt-motif")
        ]
    with pytest.raises(ValidationError, match="unpaid plants"):
        outline_schema.Outline.model_validate(data)


def test_rejects_orphan_callback_pay(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][0]["callbacks"].append(
        {"kind": "pay", "id": "no-such-plant"},
    )
    with pytest.raises(ValidationError, match="pays without plants"):
        outline_schema.Outline.model_validate(data)


# ── Script item shape ────────────────────────────────────────────────


def test_rejects_script_item_with_multiple_content_fields(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][0]["script"][0] = {"cue": "SLIDE 1 UP", "line": "Hello."}
    with pytest.raises(ValidationError, match="exactly one"):
        outline_schema.Outline.model_validate(data)


def test_rejects_script_item_with_no_content(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][0]["script"][0] = {}
    with pytest.raises(ValidationError, match="exactly one"):
        outline_schema.Outline.model_validate(data)


# ── Slide-0 title cards + DEMO interludes ────────────────────────────


def test_accepts_slide_n_zero(outline_schema, base_data):
    """Title-card / pre-talk slides start at n=0 in some talk shapes."""
    data = copy.deepcopy(base_data)
    # Shift all slide numbers down by 1 so the first slide is n=0;
    # rewrite argument_beats slide_refs to match the new numbering.
    for s in data["slides"]:
        s["n"] -= 1
    for c in data["chapters"]:
        for beat in c.get("argument_beats", []):
            beat["slide_refs"] = [r - 1 for r in beat.get("slide_refs", [])]
    data["talk"]["slide_budget"] = 30
    outline = outline_schema.Outline.model_validate(data)
    assert outline.slides[0].n == 0


def test_accepts_demo_format(outline_schema, base_data):
    """DEMO is a production-interlude slide — live terminal, no image prompt."""
    data = copy.deepcopy(base_data)
    data["slides"].append({
        "n": 99,
        "chapter": "ch1",
        "title": "DEMO 01 — Live Terminal",
        "format": "DEMO",
        "visual": "Live terminal. Claude Code TUI.",
        "script": [
            {"cue": "TERMINAL UP"},
            {"line": "Let me show you something."},
        ],
    })
    data["talk"]["slide_budget"] = 30
    outline = outline_schema.Outline.model_validate(data)
    assert outline.slides[-1].format.value == "DEMO"


def test_accepts_title_format(outline_schema, base_data):
    """TITLE is a title-card slide — passive display, often n=0."""
    data = copy.deepcopy(base_data)
    data["slides"].append({
        "n": 99,
        "chapter": "ch1",
        "title": "Title Card",
        "format": "TITLE",
    })
    data["talk"]["slide_budget"] = 30
    outline = outline_schema.Outline.model_validate(data)
    assert outline.slides[-1].format.value == "TITLE"


def test_accepts_cuttable_flag(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][-1]["cuttable"] = True
    data["chapters"][-1]["cuttable"] = True
    outline = outline_schema.Outline.model_validate(data)
    assert outline.slides[-1].cuttable is True
    assert outline.chapters[-1].cuttable is True


def test_accepts_chapter_accent(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["chapters"][0]["accent"] = "red"
    outline = outline_schema.Outline.model_validate(data)
    assert outline.chapters[0].accent == "red"


# ── Speaker-attributed parentheticals (screenplay form) ──────────────


def test_accepts_speaker_on_parenthetical_multi_speaker(outline_schema, base_data):
    """In screenplay form, a parenthetical can belong to a specific speaker
    (e.g., PATRICK (to Baruch))."""
    data = copy.deepcopy(base_data)
    data["talk"]["speakers"] = ["Speaker One", "Speaker Two"]
    # Attribute all line items so multi-speaker validation passes
    for slide in data["slides"]:
        for item in slide.get("script", []):
            if item.get("line") is not None:
                item["speaker"] = "Speaker One"
    # Add a speaker-attributed parenthetical
    data["slides"][0]["script"].insert(0, {
        "speaker": "Speaker Two",
        "parenthetical": "(to Speaker One)",
    })
    outline = outline_schema.Outline.model_validate(data)
    assert outline.slides[0].script[0].speaker == "Speaker Two"


def test_rejects_speaker_on_parenthetical_single_speaker(outline_schema, base_data):
    """Single-speaker talks must not attribute parentheticals — there's only one voice."""
    data = copy.deepcopy(base_data)
    data["slides"][0]["script"].insert(0, {
        "speaker": "Speaker One",
        "parenthetical": "(beat)",
    })
    with pytest.raises(ValidationError, match="must not attribute parentheticals"):
        outline_schema.Outline.model_validate(data)


def test_rejects_speaker_on_cue(outline_schema, base_data):
    """Cues are scene-level production directions, never attributed."""
    data = copy.deepcopy(base_data)
    data["slides"][0]["script"][0] = {
        "speaker": "Speaker One",
        "cue": "SLIDE UP",
    }
    with pytest.raises(ValidationError, match="does not apply to cue"):
        outline_schema.Outline.model_validate(data)


def test_rejects_unknown_speaker_on_parenthetical(outline_schema, base_data):
    """Attributed parentheticals must use a real speaker name."""
    data = copy.deepcopy(base_data)
    data["talk"]["speakers"] = ["Speaker One", "Speaker Two"]
    for slide in data["slides"]:
        for item in slide.get("script", []):
            if item.get("line") is not None:
                item["speaker"] = "Speaker One"
    data["slides"][0]["script"].insert(0, {
        "speaker": "Speaker Three",
        "parenthetical": "(to Speaker One)",
    })
    with pytest.raises(ValidationError, match="not in talk.speakers"):
        outline_schema.Outline.model_validate(data)


# ── Interludes ───────────────────────────────────────────────────────


def test_accepts_interlude(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["interludes"] = [{
        "id": "demo-01",
        "after_slide": 1,
        "chapter": "ch1",
        "title": "DEMO 01 — Cold Open",
        "script": [
            {"cue": "TERMINAL UP"},
            {"line": "Let me show you something."},
        ],
    }]
    outline = outline_schema.Outline.model_validate(data)
    assert len(outline.interludes) == 1
    assert outline.interludes[0].after_slide == 1


def test_rejects_interlude_unknown_chapter(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["interludes"] = [{
        "id": "demo-01",
        "after_slide": 1,
        "chapter": "ch99",
        "title": "DEMO 01",
        "script": [{"cue": "TERMINAL UP"}],
    }]
    with pytest.raises(ValidationError, match="unknown chapter"):
        outline_schema.Outline.model_validate(data)


def test_rejects_interlude_bad_anchor(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["interludes"] = [{
        "id": "demo-01",
        "after_slide": 999,
        "chapter": "ch1",
        "title": "DEMO 01",
        "script": [{"cue": "TERMINAL UP"}],
    }]
    with pytest.raises(ValidationError, match="after_slide=999"):
        outline_schema.Outline.model_validate(data)


def test_rejects_duplicate_interlude_ids(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["interludes"] = [
        {
            "id": "demo-01",
            "after_slide": 1,
            "chapter": "ch1",
            "title": "DEMO 01",
            "script": [{"cue": "TERMINAL UP"}],
        },
        {
            "id": "demo-01",
            "after_slide": 2,
            "chapter": "ch1",
            "title": "DEMO 01 again",
            "script": [{"cue": "TERMINAL UP"}],
        },
    ]
    with pytest.raises(ValidationError, match="duplicate interlude ids"):
        outline_schema.Outline.model_validate(data)


def test_interlude_callbacks_count_toward_ledger(outline_schema, base_data):
    """An interlude that plants a callback must be paid (somewhere)."""
    data = copy.deepcopy(base_data)
    data["interludes"] = [{
        "id": "demo-01",
        "after_slide": 1,
        "chapter": "ch1",
        "title": "DEMO 01",
        "script": [{"cue": "TERMINAL UP"}],
        "callbacks": [{"kind": "plant", "id": "demo-plant"}],
    }]
    with pytest.raises(ValidationError, match="unpaid plants"):
        outline_schema.Outline.model_validate(data)


# ── Slug + collapsed-spec metadata ───────────────────────────────────


def test_requires_slug(outline_schema, base_data):
    """slug is mandatory — it names the presenterm/pptx deck and the
    shownotes URL path."""
    data = copy.deepcopy(base_data)
    del data["talk"]["slug"]
    with pytest.raises(ValidationError):
        outline_schema.Outline.model_validate(data)


def test_rejects_non_kebab_slug(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    bad_slugs = [
        "Demo Talk",          # spaces + caps
        "demo_talk",          # underscore
        "demo--talk",         # double dash
        "-demo-talk",         # leading dash
        "demo-talk-",         # trailing dash
        "DemoTalk",           # camelCase
    ]
    for slug in bad_slugs:
        data["talk"]["slug"] = slug
        with pytest.raises(ValidationError, match="kebab-case"):
            outline_schema.Outline.model_validate(data)


def test_accepts_kebab_slugs(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    good_slugs = [
        "demo",
        "demo-talk",
        "geecon-2026-absolutely-right",
        "devoxx-uk-2026-300-tokens",
        "talk-1",
        "v3",
    ]
    for slug in good_slugs:
        data["talk"]["slug"] = slug
        outline = outline_schema.Outline.model_validate(data)
        assert outline.talk.slug == slug


def test_accepts_spec_fields(outline_schema, base_data):
    """Optional spec metadata collapsed from the retired presentation-spec.md."""
    data = copy.deepcopy(base_data)
    data["talk"]["thesis"] = "Treat context as a first-class artifact."
    data["talk"]["shownotes_url_base"] = "https://speaking.example.com/"
    data["talk"]["commercial_intent"] = "subtle"
    data["talk"]["profanity_register"] = "moderate — verbal only, never on slides"
    data["talk"]["must_include"] = ["the receipt motif", "Mr. Fusion callback"]
    data["talk"]["must_avoid"] = ["no competitor disparagement"]
    data["talk"]["catalog_reference"] = "sessions-catalog.md#absolutely-right"
    data["talk"]["delivery_count"] = 1
    data["talk"]["delivery_date"] = "2026-05-14"
    outline = outline_schema.Outline.model_validate(data)
    assert outline.talk.thesis.startswith("Treat context")
    assert outline.talk.delivery_count == 1
    assert outline.talk.delivery_date == "2026-05-14"


def test_rejects_bad_delivery_date(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["delivery_date"] = "May 14, 2026"
    with pytest.raises(ValidationError, match="ISO YYYY-MM-DD"):
        outline_schema.Outline.model_validate(data)


def test_rejects_zero_delivery_count(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["delivery_count"] = 0
    with pytest.raises(ValidationError):
        outline_schema.Outline.model_validate(data)


# ── Strict-schema + structural-integrity validators (PR-#45 review) ──


def test_rejects_unknown_top_level_field(outline_schema, base_data):
    """extra='forbid' on every model — misspelled YAML keys fail loud."""
    data = copy.deepcopy(base_data)
    data["talk"]["audiance"] = "typo!"  # 'audience' misspelled
    with pytest.raises(ValidationError, match="audiance"):
        outline_schema.Outline.model_validate(data)


def test_rejects_unknown_slide_field(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][0]["formaat"] = "FULL"
    with pytest.raises(ValidationError, match="formaat"):
        outline_schema.Outline.model_validate(data)


def test_rejects_duplicate_chapter_ids(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["chapters"][1]["id"] = data["chapters"][0]["id"]
    with pytest.raises(ValidationError, match="duplicate chapter ids"):
        outline_schema.Outline.model_validate(data)


def test_rejects_duplicate_build_steps(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    slide_with_builds = next(s for s in data["slides"] if s.get("builds"))
    slide_with_builds["builds"][1]["step"] = slide_with_builds["builds"][0]["step"]
    with pytest.raises(ValidationError, match="duplicate build steps"):
        outline_schema.Outline.model_validate(data)


def test_rejects_out_of_order_build_steps(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    slide_with_builds = next(s for s in data["slides"] if s.get("builds"))
    slide_with_builds["builds"][0]["step"], slide_with_builds["builds"][-1]["step"] = (
        slide_with_builds["builds"][-1]["step"],
        slide_with_builds["builds"][0]["step"],
    )
    with pytest.raises(ValidationError, match="not ascending"):
        outline_schema.Outline.model_validate(data)


def test_rejects_argument_beat_slide_ref_to_missing_slide(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["chapters"][0]["argument_beats"][0]["slide_refs"] = [999]
    with pytest.raises(ValidationError, match="slide_ref 999"):
        outline_schema.Outline.model_validate(data)
