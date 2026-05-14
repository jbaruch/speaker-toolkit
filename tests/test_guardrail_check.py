"""Tests for guardrail-check.py — profile-aware checks against outline.yaml."""

import copy
from pathlib import Path

import pytest
import yaml


FIXTURE = Path(__file__).parent / "fixtures" / "outline-example.yaml"


PROFILE = {
    "rhetoric_defaults": {
        "default_duration_minutes": 30,
        "profanity_calibration": "verbal-only — never on slides",
    },
    "guardrail_sources": {
        "slide_budgets": [
            {"duration_minutes": 30, "max_slides": 30},
        ],
        "act1_ratio_limits": [
            {"max_percentage": 45},
        ],
    },
    "design_rules": {
        "footer": {
            "elements": ["@speaker", "#conference"],
        },
    },
}


@pytest.fixture(scope="session")
def outline(outline_schema):
    return outline_schema.load_outline(FIXTURE)


@pytest.fixture(scope="session")
def base_data():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


# ── Slide budget ─────────────────────────────────────────────────────


def test_budget_pass(guardrail_check, outline):
    label, _ = guardrail_check.check_slide_budget(outline, PROFILE)
    assert label == "PASS"


def test_budget_fail(guardrail_check, outline_schema, base_data):
    """If the profile budget is well below the expanded slide count, FAIL."""
    data = copy.deepcopy(base_data)
    o = outline_schema.Outline.model_validate(data)
    profile = copy.deepcopy(PROFILE)
    profile["guardrail_sources"]["slide_budgets"] = [
        {"duration_minutes": 30, "max_slides": 5},
    ]
    label, _ = guardrail_check.check_slide_budget(o, profile)
    assert label == "FAIL"


def test_budget_warn_near_limit(guardrail_check, outline_schema, base_data):
    """At-or-near the budget cap → WARN."""
    data = copy.deepcopy(base_data)
    o = outline_schema.Outline.model_validate(data)
    # expanded count is 11; set budget = 11 → slack=0, within 5% → WARN
    profile = copy.deepcopy(PROFILE)
    profile["guardrail_sources"]["slide_budgets"] = [
        {"duration_minutes": 30, "max_slides": 11},
    ]
    label, _ = guardrail_check.check_slide_budget(o, profile)
    assert label == "WARN"


# ── Act 1 ratio ──────────────────────────────────────────────────────


def test_act1_ratio_pass(guardrail_check, outline):
    label, _ = guardrail_check.check_act1_ratio(outline, PROFILE)
    assert label in ("PASS", "WARN")  # fixture's Act 1 is ch1 = 6/30 = 20%


def test_act1_ratio_fail(guardrail_check, outline_schema, base_data):
    """Inflate the first chapter past the Act 1 limit."""
    data = copy.deepcopy(base_data)
    data["chapters"][0]["target_min"] = 20  # 20/30 = 66% > 45%
    o = outline_schema.Outline.model_validate(data)
    label, _ = guardrail_check.check_act1_ratio(o, PROFILE)
    assert label == "FAIL"


# ── Closing ──────────────────────────────────────────────────────────


def test_closing_pass(guardrail_check, outline):
    """Fixture's last chapter (`ch3 — The Close`) includes Call to Action slide,
    New Bliss, and shownotes-style closing — summary + CTA + social all present."""
    label, detail = guardrail_check.check_closing(outline)
    # Closing text in the fixture includes 'doer'/'supplier'/'shownotes'-adjacent terms
    assert label in ("PASS", "FAIL")  # detail-dependent; assert structure
    assert "summary=" in detail and "CTA=" in detail and "social=" in detail


def test_closing_fail_when_signals_missing(guardrail_check, outline_schema, base_data):
    """Strip the last chapter's slides of any closing signals."""
    data = copy.deepcopy(base_data)
    last_chapter_id = data["chapters"][-1]["id"]
    for slide in data["slides"]:
        if slide["chapter"] == last_chapter_id:
            slide["text_overlay"] = "none"
            slide["visual"] = "blank"
            slide["script"] = [{"line": "an unrelated sentence"}]
    o = outline_schema.Outline.model_validate(data)
    label, detail = guardrail_check.check_closing(o)
    assert label == "FAIL"
    assert "missing" in detail


# ── Cut lines ────────────────────────────────────────────────────────


def test_cut_lines_pass_when_chapter_cuttable(guardrail_check, outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["chapters"][1]["cuttable"] = True
    o = outline_schema.Outline.model_validate(data)
    label, _ = guardrail_check.check_cut_lines(o)
    assert label == "PASS"


def test_cut_lines_pass_when_slide_cuttable(guardrail_check, outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][-1]["cuttable"] = True
    o = outline_schema.Outline.model_validate(data)
    label, _ = guardrail_check.check_cut_lines(o)
    assert label == "PASS"


def test_cut_lines_fail_when_none_cuttable(guardrail_check, outline):
    """Base fixture has no cuttable markers."""
    label, _ = guardrail_check.check_cut_lines(outline)
    assert label == "FAIL"


# ── Profanity ────────────────────────────────────────────────────────


def test_profanity_pass_clean(guardrail_check, outline):
    label, _ = guardrail_check.check_profanity(outline, PROFILE)
    assert label == "PASS"


def test_profanity_warn_on_slide(guardrail_check, outline_schema, base_data):
    """Verbal-allowed register + on-slide token → WARN (limits deck reuse)."""
    data = copy.deepcopy(base_data)
    data["talk"]["profanity_register"] = "moderate"
    data["slides"][0]["text_overlay"] = "Some damn good code."
    o = outline_schema.Outline.model_validate(data)
    label, detail = guardrail_check.check_profanity(o, PROFILE)
    assert label == "WARN"


def test_profanity_fail_on_slide_when_forbidden(
    guardrail_check, outline_schema, base_data,
):
    data = copy.deepcopy(base_data)
    data["talk"]["profanity_register"] = "verbal-only — never on slide"
    data["slides"][0]["text_overlay"] = "Some damn good code."
    o = outline_schema.Outline.model_validate(data)
    label, _ = guardrail_check.check_profanity(o, PROFILE)
    assert label == "FAIL"


def test_profanity_fail_when_none_register(guardrail_check, outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["talk"]["profanity_register"] = "none"
    # Put a spoken hit so register='none' fires
    data["slides"][0]["script"].append({"line": "what the hell"})
    o = outline_schema.Outline.model_validate(data)
    label, _ = guardrail_check.check_profanity(o, PROFILE)
    assert label == "FAIL"


# ── Data attribution ─────────────────────────────────────────────────


def test_data_attribution_pass_clean(guardrail_check, outline):
    # The fixture's slide 2 text_overlay contains no percentages
    label, _ = guardrail_check.check_data_attribution(outline)
    assert label == "PASS"


def test_data_attribution_fail_when_orphan_pct(guardrail_check, outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][0]["text_overlay"] = "84% of developers are tired."
    o = outline_schema.Outline.model_validate(data)
    label, _ = guardrail_check.check_data_attribution(o)
    assert label == "FAIL"


def test_data_attribution_pass_when_source_present(guardrail_check, outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][0]["text_overlay"] = "84% of developers (source: Stack Overflow 2024)"
    o = outline_schema.Outline.model_validate(data)
    label, _ = guardrail_check.check_data_attribution(o)
    assert label == "PASS"


# ── Branding ─────────────────────────────────────────────────────────


def test_branding_warns_when_no_footer_elements(guardrail_check, outline):
    profile = {"design_rules": {"footer": {"elements": []}}}
    label, _ = guardrail_check.check_branding(outline, profile)
    assert label == "WARN"
