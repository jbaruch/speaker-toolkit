"""Tests for outline_schema.py — pydantic validators on the outline source-of-truth."""

import copy
import re
import stat
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
    # Discovered from references/patterns/{prepare,build,deliver}/*.md — the
    # filesystem is the source of truth. _index.md mirrors these totals for
    # human readers; adding a pattern means updating both.
    assert len(outline_schema.PATTERN_IDS) == 85
    assert len(outline_schema.ANTIPATTERN_IDS) == 28
    assert "sparkline" in outline_schema.PATTERN_IDS
    assert "slideuments" in outline_schema.ANTIPATTERN_IDS


# ── Audience spread / register (walk-around) ─────────────────────────


def test_homogeneous_requires_dominant_register(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["audience_spread"] = "homogeneous"
    with pytest.raises(ValidationError, match="dominant_register"):
        outline_schema.Outline.model_validate(data)


def test_heterogeneous_rejects_dominant_register(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["audience_spread"] = "heterogeneous"
    data["talk"]["dominant_register"] = "A"
    with pytest.raises(ValidationError, match="dominant_register"):
        outline_schema.Outline.model_validate(data)


def test_homogeneous_with_register_validates(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["audience_spread"] = "homogeneous"
    data["talk"]["dominant_register"] = "A"
    outline = outline_schema.Outline.model_validate(data)
    assert outline.talk.dominant_register.value == "A"


def test_rejects_unknown_audience_spread(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["audience_spread"] = "mostly-engineers"
    with pytest.raises(ValidationError, match="audience_spread"):
        outline_schema.Outline.model_validate(data)


def test_audience_spread_is_required(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    del data["talk"]["audience_spread"]
    with pytest.raises(ValidationError, match="audience_spread"):
        outline_schema.Outline.model_validate(data)


def test_rejects_unknown_register(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["applied_patterns"].append(
        {"id": "walk-around", "registers": ["E"]},
    )
    with pytest.raises(ValidationError, match="registers"):
        outline_schema.Outline.model_validate(data)


def test_walk_around_rejected_at_talk_level(outline_schema, base_data):
    """A talk-level walk-around would satisfy coverage with no per-claim evidence."""
    data = copy.deepcopy(base_data)
    data["talk"]["applied_patterns"].append(
        {"id": "walk-around", "registers": ["A", "B", "C", "D"]},
    )
    with pytest.raises(ValidationError, match="per-claim"):
        outline_schema.Outline.model_validate(data)


def test_registers_rejected_on_other_patterns(outline_schema, base_data):
    """`registers` is walk-around's instance metadata — no other pattern takes it."""
    data = copy.deepcopy(base_data)
    data["talk"]["applied_patterns"].append(
        {"id": "mentor", "registers": ["A"]},
    )
    with pytest.raises(ValidationError, match="registers"):
        outline_schema.Outline.model_validate(data)


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
        data["slides"][1]["n"],
        data["slides"][0]["n"],
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
    data["talk"]["applied_patterns"].append(
        {
            "id": "bookends",
            "flavors": ["personal"],
        }
    )
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
            cb
            for cb in slide.get("callbacks", [])
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
    data["slides"].append(
        {
            "n": 99,
            "chapter": "ch1",
            "title": "DEMO 01 — Live Terminal",
            "format": "DEMO",
            "visual": "Live terminal. Claude Code TUI.",
            "script": [
                {"cue": "TERMINAL UP"},
                {"line": "Let me show you something."},
            ],
        }
    )
    data["talk"]["slide_budget"] = 30
    outline = outline_schema.Outline.model_validate(data)
    assert outline.slides[-1].format.value == "DEMO"


def test_accepts_title_format(outline_schema, base_data):
    """TITLE is a title-card slide — passive display, often n=0."""
    data = copy.deepcopy(base_data)
    data["slides"].append(
        {
            "n": 99,
            "chapter": "ch1",
            "title": "Title Card",
            "format": "TITLE",
        }
    )
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
    data["slides"][0]["script"].insert(
        0,
        {
            "speaker": "Speaker Two",
            "parenthetical": "(to Speaker One)",
        },
    )
    outline = outline_schema.Outline.model_validate(data)
    assert outline.slides[0].script[0].speaker == "Speaker Two"


def test_rejects_speaker_on_parenthetical_single_speaker(outline_schema, base_data):
    """Single-speaker talks must not attribute parentheticals — there's only one voice."""
    data = copy.deepcopy(base_data)
    data["slides"][0]["script"].insert(
        0,
        {
            "speaker": "Speaker One",
            "parenthetical": "(beat)",
        },
    )
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
    data["slides"][0]["script"].insert(
        0,
        {
            "speaker": "Speaker Three",
            "parenthetical": "(to Speaker One)",
        },
    )
    with pytest.raises(ValidationError, match="not in talk.speakers"):
        outline_schema.Outline.model_validate(data)


# ── Interludes ───────────────────────────────────────────────────────


def test_accepts_interlude(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["interludes"] = [
        {
            "id": "demo-01",
            "after_slide": 1,
            "chapter": "ch1",
            "title": "DEMO 01 — Cold Open",
            "script": [
                {"cue": "TERMINAL UP"},
                {"line": "Let me show you something."},
            ],
        }
    ]
    outline = outline_schema.Outline.model_validate(data)
    assert len(outline.interludes) == 1
    assert outline.interludes[0].after_slide == 1


def test_rejects_interlude_unknown_chapter(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["interludes"] = [
        {
            "id": "demo-01",
            "after_slide": 1,
            "chapter": "ch99",
            "title": "DEMO 01",
            "script": [{"cue": "TERMINAL UP"}],
        }
    ]
    with pytest.raises(ValidationError, match="unknown chapter"):
        outline_schema.Outline.model_validate(data)


def test_rejects_interlude_bad_anchor(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["interludes"] = [
        {
            "id": "demo-01",
            "after_slide": 999,
            "chapter": "ch1",
            "title": "DEMO 01",
            "script": [{"cue": "TERMINAL UP"}],
        }
    ]
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
    data["interludes"] = [
        {
            "id": "demo-01",
            "after_slide": 1,
            "chapter": "ch1",
            "title": "DEMO 01",
            "script": [{"cue": "TERMINAL UP"}],
            "callbacks": [{"kind": "plant", "id": "demo-plant"}],
        }
    ]
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
        "Demo Talk",  # spaces + caps
        "demo_talk",  # underscore
        "demo--talk",  # double dash
        "-demo-talk",  # leading dash
        "demo-talk-",  # trailing dash
        "DemoTalk",  # camelCase
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
    with pytest.raises(ValidationError, match="contiguous starting"):
        outline_schema.Outline.model_validate(data)


def test_rejects_out_of_order_build_steps(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    slide_with_builds = next(s for s in data["slides"] if s.get("builds"))
    slide_with_builds["builds"][0]["step"], slide_with_builds["builds"][-1]["step"] = (
        slide_with_builds["builds"][-1]["step"],
        slide_with_builds["builds"][0]["step"],
    )
    with pytest.raises(ValidationError, match="ascending"):
        outline_schema.Outline.model_validate(data)


def test_rejects_builds_not_starting_at_zero(outline_schema, base_data):
    """Build sequences must start at step 0 — the empty frame."""
    data = copy.deepcopy(base_data)
    slide_with_builds = next(s for s in data["slides"] if s.get("builds"))
    for i, b in enumerate(slide_with_builds["builds"]):
        b["step"] = i + 1  # shift to start at 1
    with pytest.raises(ValidationError, match="contiguous starting at 0"):
        outline_schema.Outline.model_validate(data)


def test_rejects_builds_with_holes(outline_schema, base_data):
    """Build sequences must be contiguous — no gaps."""
    data = copy.deepcopy(base_data)
    slide_with_builds = next(s for s in data["slides"] if s.get("builds"))
    slide_with_builds["builds"][-1]["step"] = 99  # gap
    with pytest.raises(ValidationError, match="contiguous"):
        outline_schema.Outline.model_validate(data)


def test_requires_format_on_every_slide(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    del data["slides"][0]["format"]
    with pytest.raises(ValidationError, match="format"):
        outline_schema.Outline.model_validate(data)


# ── Illustration-layer fields (consumed by the illustrations skill) ──


def test_accepts_build_erase_field(outline_schema, base_data):
    """builds[].erase carries the backwards-erase prompt for --build."""
    data = copy.deepcopy(base_data)
    slide_with_builds = next(s for s in data["slides"] if s.get("builds"))
    slide_with_builds["builds"][1]["erase"] = (
        "Erase the middle and right terminals. Keep the three labeled frames."
    )
    outline = outline_schema.Outline.model_validate(data)
    target = next(s for s in outline.slides if s.builds)
    assert target.builds[1].erase.startswith("Erase the middle")
    # Steps without an erase prompt default to None.
    assert target.builds[0].erase is None


def test_rejects_unknown_build_field(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    slide_with_builds = next(s for s in data["slides"] if s.get("builds"))
    slide_with_builds["builds"][0]["eraze"] = "typo"
    with pytest.raises(ValidationError, match="eraze"):
        outline_schema.Outline.model_validate(data)


def test_accepts_build_erase_region(outline_schema, base_data):
    """builds[].erase_region carries the optional normalized mask box (#90)."""
    data = copy.deepcopy(base_data)
    slide_with_builds = next(s for s in data["slides"] if s.get("builds"))
    slide_with_builds["builds"][0]["erase_region"] = [0.1, 0.2, 0.5, 0.8]
    outline = outline_schema.Outline.model_validate(data)
    target = next(s for s in outline.slides if s.builds)
    assert target.builds[0].erase_region == (0.1, 0.2, 0.5, 0.8)
    # Steps without a region default to None (whole-frame edit).
    assert target.builds[1].erase_region is None


def test_rejects_erase_region_out_of_range(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    slide_with_builds = next(s for s in data["slides"] if s.get("builds"))
    slide_with_builds["builds"][0]["erase_region"] = [0.1, 0.2, 1.5, 0.8]  # > 1
    with pytest.raises(ValidationError, match="normalized"):
        outline_schema.Outline.model_validate(data)


def test_rejects_erase_region_inverted_box(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    slide_with_builds = next(s for s in data["slides"] if s.get("builds"))
    slide_with_builds["builds"][0]["erase_region"] = [0.5, 0.2, 0.3, 0.8]  # x0 >= x1
    with pytest.raises(ValidationError, match="x0 < x1"):
        outline_schema.Outline.model_validate(data)


def test_accepts_style_anchor_composition_and_footer(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    # A poster deck illustrates FULL slides only.
    for slide in data["slides"]:
        if slide.get("format") != "FULL":
            slide.pop("image_prompt", None)
    data["style_anchor"]["composition"] = "poster-theatrical"
    data["style_anchor"]["embedded_footer"] = "@speaker · example.com/talk"
    outline = outline_schema.Outline.model_validate(data)
    assert (
        outline.style_anchor.composition == outline_schema.Composition.poster_theatrical
    )
    assert outline.style_anchor.embedded_footer == "@speaker · example.com/talk"


def test_style_anchor_composition_defaults_none(outline_schema):
    """Absent composition means standard overlay (None)."""
    outline = outline_schema.load_outline(FIXTURE)
    assert outline.style_anchor.composition is None
    assert outline.style_anchor.embedded_footer is None


def test_rejects_unknown_composition(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["style_anchor"]["composition"] = "billboard"
    with pytest.raises(ValidationError, match="composition"):
        outline_schema.Outline.model_validate(data)


def test_accepts_style_anchor_text_treatment(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["style_anchor"]["text_treatment"] = (
        "glowing hand-script neon rendered on an in-scene surface"
    )
    outline = outline_schema.Outline.model_validate(data)
    assert outline.style_anchor.text_treatment.startswith("glowing hand-script")


def test_style_anchor_text_treatment_defaults_none(outline_schema):
    outline = outline_schema.load_outline(FIXTURE)
    assert outline.style_anchor.text_treatment is None


def test_accepts_slide_safe_zone(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][0]["safe_zone"] = {
        "zone": "upper_third",
        "surface": "a clean band of sky",
    }
    outline = outline_schema.Outline.model_validate(data)
    assert outline.slides[0].safe_zone.zone == outline_schema.SafeZoneName.upper_third
    assert outline.slides[0].safe_zone.surface == "a clean band of sky"


def test_safe_zone_surface_optional(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][0]["safe_zone"] = {"zone": "lower_third"}
    outline = outline_schema.Outline.model_validate(data)
    assert outline.slides[0].safe_zone.surface is None


def test_rejects_unknown_safe_zone(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][0]["safe_zone"] = {"zone": "diagonal_slash"}
    with pytest.raises(ValidationError, match="zone"):
        outline_schema.Outline.model_validate(data)


def test_rejects_argument_beat_slide_ref_to_missing_slide(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["chapters"][0]["argument_beats"][0]["slide_refs"] = [999]
    with pytest.raises(ValidationError, match="slide_ref 999"):
        outline_schema.Outline.model_validate(data)


# ── Partial (narrative-phase) loader ─────────────────────────────────


def test_partial_accepts_talk_only(outline_schema, base_data):
    """Phase 1: only the talk block exists — no chapters, no slides."""
    data = {"schema_version": 2, "talk": copy.deepcopy(base_data["talk"])}
    partial = outline_schema.PartialOutline.model_validate(data)
    assert partial.talk.title == "Demo Talk"
    assert partial.chapters == []
    assert partial.slides == []


def test_partial_accepts_chapters_without_slides(outline_schema, base_data):
    """Phase 2: chapters authored, slides not yet. Beats carry no slide_refs —
    slides do not exist, so there is nothing to reference."""
    chapters = copy.deepcopy(base_data["chapters"])
    for c in chapters:
        for beat in c.get("argument_beats", []):
            beat["slide_refs"] = []
    data = {
        "schema_version": 2,
        "talk": copy.deepcopy(base_data["talk"]),
        "chapters": chapters,
    }
    partial = outline_schema.PartialOutline.model_validate(data)
    assert len(partial.chapters) == 3
    assert partial.slides == []


def test_partial_rejects_slide_refs_without_slides(outline_schema, base_data):
    """Phase 2 invariant: a beat may not reference a slide that does not exist.
    With no slides authored, every slide_ref is invalid."""
    chapters = copy.deepcopy(base_data["chapters"])
    chapters[0]["argument_beats"][0]["slide_refs"] = [1]
    data = {
        "schema_version": 2,
        "talk": copy.deepcopy(base_data["talk"]),
        "chapters": chapters,
    }
    with pytest.raises(ValidationError, match="slide_ref 1"):
        outline_schema.PartialOutline.model_validate(data)


def test_partial_still_validates_talk_fields(outline_schema, base_data):
    """Field-level validators on talk still fire in partial mode."""
    data = {"schema_version": 2, "talk": copy.deepcopy(base_data["talk"])}
    data["talk"]["architecture"] = "freeform-vibes"
    with pytest.raises(ValidationError, match="architecture"):
        outline_schema.PartialOutline.model_validate(data)


def test_partial_rejects_unknown_field(outline_schema, base_data):
    """extra='forbid' holds — misspelled keys fail loud even in partial mode."""
    data = {
        "schema_version": 2,
        "talk": copy.deepcopy(base_data["talk"]),
        "chapterz": [],
    }
    with pytest.raises(ValidationError, match="chapterz"):
        outline_schema.PartialOutline.model_validate(data)


def test_partial_loader_accepts_full_outline(outline_schema):
    """--partial works at any phase: a complete outline also loads partially."""
    partial = outline_schema.load_outline_partial(FIXTURE)
    assert len(partial.chapters) == 3
    assert len(partial.slides) == 8


# ── CLI: --emit-json contract ─────────────────────────────────────────


def test_cli_emit_json_dumps_validated_outline(outline_schema, capsys):
    """`--emit-json <path>` writes the validated outline to stdout as JSON.

    Shownotes-publisher and other downstream skills rely on this contract
    to pull structured fields (talk.title, talk.slug, etc.) without
    re-parsing YAML by hand."""
    import json as _json

    rc = outline_schema.main(
        [
            "outline_schema.py",
            "--emit-json",
            str(FIXTURE),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = _json.loads(captured.out)
    assert payload["talk"]["title"] == "Demo Talk"
    assert payload["talk"]["slug"] == "demo-conf-2026-demo-talk"
    assert isinstance(payload["chapters"], list)
    assert isinstance(payload["slides"], list)


def test_cli_default_mode_prints_ok_summary(outline_schema, capsys):
    """Default mode (no flag) still prints the human-readable OK line."""
    rc = outline_schema.main(["outline_schema.py", str(FIXTURE)])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("OK: ")
    assert "slides across" in captured.out


def test_cli_emit_json_validation_failure_to_stderr(outline_schema, capsys, tmp_path):
    """Validation failures still go to stderr with exit 1 — JSON mode does
    not silently emit a partial payload on failure."""
    bad = tmp_path / "bad-outline.yaml"
    bad.write_text("talk: {}\n", encoding="utf-8")
    rc = outline_schema.main(
        [
            "outline_schema.py",
            "--emit-json",
            str(bad),
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FAIL:" in captured.err


# ── Engine / theme sourcing fields (Phase 2 Decision #2) ─────────────


def test_accepts_pptx_engine(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["engine"] = "pptx"
    assert outline_schema.Outline.model_validate(data).talk.engine.value == "pptx"


def test_accepts_presenterm_engine(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["engine"] = "presenterm"
    out = outline_schema.Outline.model_validate(data)
    assert out.talk.engine.value == "presenterm"


def test_rejects_unknown_engine(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["engine"] = "reveal.js"
    with pytest.raises(ValidationError, match="engine"):
        outline_schema.Outline.model_validate(data)


def test_absent_engine_still_validates(outline_schema, base_data):
    # Back-compat: legacy outlines without engine/theme load clean and default
    # to None so Phase 5 can fall back to inference.
    data = copy.deepcopy(base_data)
    out = outline_schema.Outline.model_validate(data)
    assert out.talk.engine is None
    assert out.talk.deck_theme is None
    assert out.talk.engine_source is None


def test_accepts_free_string_theme_and_source(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["deck_theme"] = "dark minimal"
    data["talk"]["engine_source"] = "match-mode"
    out = outline_schema.Outline.model_validate(data)
    assert out.talk.deck_theme == "dark minimal"
    assert out.talk.engine_source == "match-mode"


def test_footer_style_needs_outline_schema_2(outline_schema, base_data):
    """footer_style is the v2 shape; a v1 outline carrying it is refused."""
    data = copy.deepcopy(base_data)
    for slide in data["slides"]:
        if slide.get("format") != "FULL":
            slide.pop("image_prompt", None)
    data["style_anchor"].update(
        composition="poster-theatrical",
        embedded_footer="@speaker",
        footer_style={},
    )
    data["schema_version"] = 1
    with pytest.raises(ValidationError, match="belongs to outline schema 2"):
        outline_schema.Outline.model_validate(data)
    data["schema_version"] = 2
    assert outline_schema.Outline.model_validate(data).schema_version == 2


def test_a_poster_deck_refuses_an_illustrated_non_full_slide(outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["style_anchor"]["composition"] = "poster-theatrical"
    with pytest.raises(ValidationError, match="illustrate FULL slides only"):
        outline_schema.Outline.model_validate(data)


def _v1_text(base_data, *, stamp: bool) -> str:
    data = copy.deepcopy(base_data)
    data.pop("schema_version", None)
    body = yaml.safe_dump(data, sort_keys=False)
    head = "# authored outline — keep this comment\n"
    return head + ("schema_version: 1\n" if stamp else "") + body


_HANDOFF = "Hand off to presentation-creator"


def test_the_owner_migration_restamps_an_older_outline_in_place(
    outline_schema, base_data, tmp_path
):
    """Only the root stamp changes; comments and layout survive."""
    path = tmp_path / "outline.yaml"
    before = _v1_text(base_data, stamp=True)
    path.write_text(before, encoding="utf-8")

    result = outline_schema.migrate_outline(path)

    after = path.read_text(encoding="utf-8")
    assert result == {
        "ok": True,
        "path": str(path),
        "migrated": True,
        "from": 1,
        "to": 2,
    }
    assert "# authored outline — keep this comment" in after
    assert yaml.safe_load(after)["schema_version"] == 2
    assert outline_schema.load_outline(path).schema_version == 2
    assert outline_schema.migrate_outline(path)["migrated"] is False


def test_a_non_owner_reader_refuses_an_older_outline(
    outline_schema, base_data, tmp_path
):
    path = tmp_path / "outline.yaml"
    path.write_text(_v1_text(base_data, stamp=True), encoding="utf-8")
    with pytest.raises(outline_schema.OutlineVersionError, match=_HANDOFF):
        outline_schema.require_current_outline(path)
    outline_schema.migrate_outline(path)
    outline_schema.require_current_outline(path)


def _body(base_data) -> str:
    data = copy.deepcopy(base_data)
    data.pop("schema_version", None)
    return yaml.safe_dump(data, sort_keys=False)


@pytest.mark.parametrize(
    "head,expected_head",
    [
        (
            "schema_version: 1  # stamped by the creator\n",
            "schema_version: 2  # stamped by the creator\n",
        ),
        ('"schema_version": 1\n', '"schema_version": 2\n'),
        (
            "# preamble\n\n---\nschema_version: 1\n",
            "# preamble\n\n---\nschema_version: 2\n",
        ),
    ],
    ids=["inline-comment", "quoted-key", "preamble-before-marker"],
)
def test_the_migration_restamps_every_root_layout(
    outline_schema, base_data, tmp_path, head, expected_head
):
    path = tmp_path / "outline.yaml"
    path.write_text(head + _body(base_data), encoding="utf-8")
    outline_schema.migrate_outline(path)
    after = path.read_text(encoding="utf-8")
    assert after.startswith(expected_head)
    assert yaml.safe_load(after)["schema_version"] == 2


def test_the_migration_keeps_crlf_line_endings(outline_schema, base_data, tmp_path):
    path = tmp_path / "outline.yaml"
    crlf = ("schema_version: 1\n" + _body(base_data)).replace("\n", "\r\n")
    path.write_bytes(crlf.encode("utf-8"))
    outline_schema.migrate_outline(path)
    after = path.read_bytes().decode("utf-8")
    assert after == crlf.replace("schema_version: 1", "schema_version: 2", 1)


@pytest.mark.parametrize(
    "version,detail",
    [(3, "update speaker-toolkit"), ("two", "not an integer")],
    ids=["newer", "not-an-integer"],
)
def test_a_non_owner_reader_refuses_every_other_version(
    outline_schema, base_data, tmp_path, version, detail
):
    path = tmp_path / "outline.yaml"
    path.write_text(
        yaml.safe_dump({**base_data, "schema_version": version}, sort_keys=False),
        encoding="utf-8",
    )
    with pytest.raises(outline_schema.OutlineVersionError, match=detail):
        outline_schema.require_current_outline(path)


@pytest.mark.parametrize("version", [2.0, True, 1.0], ids=repr)
def test_a_version_that_only_compares_equal_is_refused(
    outline_schema, base_data, tmp_path, version
):
    """2.0 equals 2 and true equals 1, but neither is the integer stamp."""
    path = tmp_path / "outline.yaml"
    path.write_text(
        yaml.safe_dump({**base_data, "schema_version": version}, sort_keys=False),
        encoding="utf-8",
    )
    with pytest.raises(outline_schema.OutlineVersionError, match="not an integer"):
        outline_schema.require_current_outline(path)
    with pytest.raises(outline_schema.OutlineVersionError, match="not an integer"):
        outline_schema.migrate_outline(path)


def test_the_owner_validation_migrates_before_it_reads(
    outline_schema, base_data, tmp_path, capsys
):
    path = tmp_path / "outline.yaml"
    path.write_text(_v1_text(base_data, stamp=True), encoding="utf-8")
    assert outline_schema.main(["outline_schema.py", str(path)]) == 0
    assert "from outline schema 1 to 2" in capsys.readouterr().err
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["schema_version"] == 2


def test_emit_json_refuses_an_older_outline_without_rewriting_it(
    outline_schema, base_data, tmp_path, capsys
):
    """--emit-json serves non-owner readers, which refuse and never migrate."""
    path = tmp_path / "outline.yaml"
    original = _v1_text(base_data, stamp=True)
    path.write_text(original, encoding="utf-8")
    assert outline_schema.main(["outline_schema.py", "--emit-json", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert _HANDOFF in captured.err
    assert path.read_text(encoding="utf-8") == original


def test_a_missing_root_stamp_is_refused_everywhere(
    outline_schema, base_data, tmp_path, capsys
):
    """No reader defaults a missing stamp to 1; the owner is told the fix and a
    non-owner reader is told to hand off."""
    path = tmp_path / "outline.yaml"
    original = _v1_text(base_data, stamp=False)
    path.write_text(original, encoding="utf-8")
    fix = "add `schema_version: 1`"
    for view in (outline_schema.Outline, outline_schema.PartialOutline):
        with pytest.raises(ValidationError, match=fix):
            view.model_validate(yaml.safe_load(original))
    with pytest.raises(outline_schema.OutlineVersionError, match=fix):
        outline_schema.migrate_outline(path)
    with pytest.raises(outline_schema.OutlineVersionError, match=_HANDOFF):
        outline_schema.require_current_outline(path)
    for mode, expected in (
        ([], fix),
        (["--migrate"], fix),
        (["--emit-json"], _HANDOFF),
    ):
        assert outline_schema.main(["outline_schema.py", *mode, str(path)]) == 1
        assert expected in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == original


def test_a_stamp_the_migration_cannot_find_is_refused(
    outline_schema, base_data, tmp_path
):
    """A flow-style root hides the stamp from the line rewrite; never guess."""
    path = tmp_path / "outline.yaml"
    data = {**copy.deepcopy(base_data), "schema_version": 1}
    original = yaml.safe_dump(data, sort_keys=False, default_flow_style=True)
    path.write_text(original, encoding="utf-8")
    with pytest.raises(outline_schema.OutlineVersionError, match="by hand"):
        outline_schema.migrate_outline(path)
    assert path.read_text(encoding="utf-8") == original


def test_a_non_utf8_outline_is_refused_with_its_fix(
    outline_schema, base_data, tmp_path, capsys
):
    path = tmp_path / "outline.yaml"
    raw = _v1_text(base_data, stamp=True).encode("utf-8") + b"# caf\xe9\n"
    path.write_bytes(raw)
    with pytest.raises(outline_schema.OutlineVersionError, match="not UTF-8"):
        outline_schema.require_current_outline(path)
    fix = "re-save it as UTF-8"
    for mode, expected in (
        ([], fix),
        (["--migrate"], fix),
        (["--emit-json"], _HANDOFF),
    ):
        assert outline_schema.main(["outline_schema.py", *mode, str(path)]) == 1
        assert expected in capsys.readouterr().err
    assert path.read_bytes() == raw


def test_a_root_that_is_not_a_mapping_is_refused(outline_schema, tmp_path):
    path = tmp_path / "outline.yaml"
    path.write_text("- schema_version: 2\n", encoding="utf-8")
    for check in (
        outline_schema.require_current_outline,
        outline_schema.migrate_outline,
    ):
        with pytest.raises(
            outline_schema.OutlineVersionError, match="not a YAML mapping"
        ):
            check(path)


def test_the_worked_example_is_stamped_at_the_current_schema(outline_schema):
    """The CLI tests validate this fixture, and the owner's validation migrates
    an older outline in place, so a stale example would be rewritten by the suite."""
    data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    assert data["schema_version"] == outline_schema.OUTLINE_SCHEMA_VERSION


def _refused_outlines(base_data):
    """Every way the file itself can be refused, as raw bytes."""
    body = yaml.safe_dump({**copy.deepcopy(base_data), "schema_version": 1})
    return {
        "older": body.encode("utf-8"),
        "missing-stamp": _v1_text(base_data, stamp=False).encode("utf-8"),
        "not-an-integer": body.replace(
            "schema_version: 1", "schema_version: 2.0"
        ).encode(),
        "not-utf8": body.encode("utf-8") + b"# caf\xe9\n",
        "not-a-mapping": b"- schema_version: 2\n",
        "invalid-yaml": b"schema_version: 2\ntalk: [unclosed\n",
    }


@pytest.mark.parametrize(
    "kind",
    [
        "older",
        "missing-stamp",
        "not-an-integer",
        "not-utf8",
        "not-a-mapping",
        "invalid-yaml",
    ],
)
def test_every_non_owner_refusal_hands_off_and_names_no_edit(
    outline_schema, base_data, tmp_path, kind
):
    """A non-owner reader never edits outline.yaml, so no refusal it emits may
    tell it to; each one sends the file to presentation-creator."""
    raw = _refused_outlines(base_data)[kind]
    path = tmp_path / "outline.yaml"
    path.write_bytes(raw)
    with pytest.raises(outline_schema.OutlineVersionError) as exc:
        outline_schema.require_current_outline(path)
    message = str(exc.value)
    assert _HANDOFF in message
    for edit in (
        "set it to",
        "add `schema_version",
        "re-save",
        "fix the YAML",
        "restore",
        "--migrate",
    ):
        assert edit not in message, (kind, edit)
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "kind,fix",
    [
        ("missing-stamp", "add `schema_version: 1`"),
        ("not-an-integer", "set it to 2"),
        ("not-utf8", "re-save it as UTF-8"),
        ("not-a-mapping", "restore the outline's root mapping"),
        ("invalid-yaml", "fix the YAML"),
    ],
)
def test_the_owner_migration_names_each_fix(
    outline_schema, base_data, tmp_path, kind, fix
):
    raw = _refused_outlines(base_data)[kind]
    path = tmp_path / "outline.yaml"
    path.write_bytes(raw)
    with pytest.raises(outline_schema.OutlineVersionError, match=re.escape(fix)):
        outline_schema.migrate_outline(path)
    assert path.read_bytes() == raw


def test_migrate_names_a_path_fix_for_a_missing_outline_or_a_directory(
    outline_schema, tmp_path, capsys
):
    missing = tmp_path / "outline.yaml"
    assert outline_schema.main(["outline_schema.py", "--migrate", str(missing)]) == 1
    assert (
        "pass the path to the talk's existing outline.yaml" in capsys.readouterr().err
    )
    assert outline_schema.main(["outline_schema.py", "--migrate", str(tmp_path)]) == 1
    assert "is a directory; pass the outline.yaml inside it" in capsys.readouterr().err


def test_migrate_names_the_fix_for_an_unreadable_outline(
    outline_schema, base_data, tmp_path, monkeypatch, capsys
):
    path = tmp_path / "outline.yaml"
    path.write_text(_v1_text(base_data, stamp=True), encoding="utf-8")
    real = Path.read_bytes

    def denied(self):
        if self == path:
            raise PermissionError(13, "Permission denied", str(self))
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", denied)
    assert outline_schema.main(["outline_schema.py", "--migrate", str(path)]) == 1
    assert "permission denied; make it readable" in capsys.readouterr().err


@pytest.mark.parametrize("stage", ["stage", "replace"])
def test_a_failed_write_names_its_fix_and_leaves_the_outline(
    outline_schema, base_data, tmp_path, monkeypatch, capsys, stage
):
    path = tmp_path / "outline.yaml"
    original = _v1_text(base_data, stamp=True)
    path.write_text(original, encoding="utf-8")
    full = OSError(28, "No space left on device")

    def fail(*args, **kwargs):
        raise full

    if stage == "stage":
        monkeypatch.setattr(outline_schema.tempfile, "mkstemp", fail)
    else:
        monkeypatch.setattr(outline_schema.os, "replace", fail)
    assert outline_schema.main(["outline_schema.py", "--migrate", str(path)]) == 1
    err = capsys.readouterr().err
    assert f"make {tmp_path} writable" in err
    assert "The outline is unchanged" in err
    assert path.read_text(encoding="utf-8") == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["outline.yaml"]


def test_the_migration_stages_privately_and_keeps_the_file_mode(
    outline_schema, base_data, tmp_path
):
    """A leftover staging file from another run is never reused or clobbered."""
    path = tmp_path / "outline.yaml"
    path.write_text(_v1_text(base_data, stamp=True), encoding="utf-8")
    path.chmod(0o640)
    stale = tmp_path / ".outline.yaml.migrating"
    stale.write_text("another run's half-written stage", encoding="utf-8")

    assert outline_schema.migrate_outline(path)["migrated"] is True

    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert stale.read_text(encoding="utf-8") == "another run's half-written stage"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        ".outline.yaml.migrating",
        "outline.yaml",
    ]
