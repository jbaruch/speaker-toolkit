"""Tests for guardrail-check.py — profile-aware checks against outline.yaml."""

import copy
import json
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


def test_main_emits_one_structured_json_report(guardrail_check, capsys):
    return_code = guardrail_check.main(["guardrail-check.py", str(FIXTURE), "-"])
    captured = capsys.readouterr()

    assert return_code == 0
    assert captured.err == ""
    report = json.loads(captured.out)
    assert report["schema_version"] == 1
    assert report["talk_title"]
    assert [check["name"] for check in report["checks"]] == [
        "Pattern history",
        "Slide budget",
        "Act 1 ratio",
        "Branding",
        "Profanity",
        "Data attribution",
        "Closing",
        "Cut lines",
    ]
    assert report["pattern_history"]["history_enabled"] is False
    assert report["pattern_history"]["suppressed_fields"]
    assert report["recurring_antipatterns"] == []
    assert report["contextual_taxonomy_scan"] == {
        "enabled": True,
        "history_independent": True,
        "scope": "current_outline",
    }
    assert report["required_companion_check"].endswith("check-rhetorical.py")


def test_main_rejects_invalid_input_without_stdout(guardrail_check, tmp_path, capsys):
    missing_outline = tmp_path / "missing-outline.yaml"

    return_code = guardrail_check.main(
        ["guardrail-check.py", str(missing_outline), "-"]
    )
    captured = capsys.readouterr()

    assert return_code == 1
    assert captured.out == ""
    assert f"failed to load {missing_outline}" in captured.err


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
    """Fixture's Act 1 = ch1 = 6/30 = 20%, well under the 45% cap → PASS exactly."""
    label, _ = guardrail_check.check_act1_ratio(outline, PROFILE)
    assert label == "PASS"


def test_act1_ratio_fail(guardrail_check, outline_schema, base_data):
    """Inflate the first chapter past the Act 1 limit."""
    data = copy.deepcopy(base_data)
    data["chapters"][0]["target_min"] = 20  # 20/30 = 66% > 45%
    o = outline_schema.Outline.model_validate(data)
    label, _ = guardrail_check.check_act1_ratio(o, PROFILE)
    assert label == "FAIL"


# ── Closing ──────────────────────────────────────────────────────────


def test_closing_pass(guardrail_check, outline):
    """Fixture's last chapter includes Call to Action ('Doers, write the rule...')
    and the New Bliss slide. The closing detection should find CTA + social signals."""
    label, detail = guardrail_check.check_closing(outline)
    assert label == "PASS"
    # Confirm the structured summary string is present regardless of pass/fail
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


def test_cut_lines_pass_when_chapter_cuttable(
    guardrail_check, outline_schema, base_data
):
    data = copy.deepcopy(base_data)
    data["chapters"][1]["cuttable"] = True
    o = outline_schema.Outline.model_validate(data)
    profile = copy.deepcopy(PROFILE)
    profile.setdefault("rhetoric_defaults", {})["modular_design"] = True
    label, _ = guardrail_check.check_cut_lines(o, profile)
    assert label == "PASS"


def test_cut_lines_pass_when_slide_cuttable(guardrail_check, outline_schema, base_data):
    data = copy.deepcopy(base_data)
    data["slides"][-1]["cuttable"] = True
    o = outline_schema.Outline.model_validate(data)
    profile = copy.deepcopy(PROFILE)
    profile.setdefault("rhetoric_defaults", {})["modular_design"] = True
    label, _ = guardrail_check.check_cut_lines(o, profile)
    assert label == "PASS"


def test_cut_lines_fail_when_none_cuttable_and_modular_enabled(
    guardrail_check, outline
):
    """Base fixture has no cuttable markers — FAIL when profile expects modularity."""
    profile = copy.deepcopy(PROFILE)
    profile.setdefault("rhetoric_defaults", {})["modular_design"] = True
    label, _ = guardrail_check.check_cut_lines(outline, profile)
    assert label == "FAIL"


def test_cut_lines_pass_when_modular_disabled(guardrail_check, outline):
    """Speakers without modular_design opt out of the cut-lines requirement."""
    profile = copy.deepcopy(PROFILE)
    profile.setdefault("rhetoric_defaults", {})["modular_design"] = False
    label, detail = guardrail_check.check_cut_lines(outline, profile)
    assert label == "PASS"
    assert "modular_design disabled" in detail


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
    guardrail_check,
    outline_schema,
    base_data,
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


def test_data_attribution_fail_when_orphan_pct(
    guardrail_check, outline_schema, base_data
):
    data = copy.deepcopy(base_data)
    data["slides"][0]["text_overlay"] = "84% of developers are tired."
    o = outline_schema.Outline.model_validate(data)
    label, _ = guardrail_check.check_data_attribution(o)
    assert label == "FAIL"


def test_data_attribution_pass_when_source_present(
    guardrail_check, outline_schema, base_data
):
    data = copy.deepcopy(base_data)
    data["slides"][0]["text_overlay"] = (
        "84% of developers (source: Stack Overflow 2024)"
    )
    o = outline_schema.Outline.model_validate(data)
    label, _ = guardrail_check.check_data_attribution(o)
    assert label == "PASS"


# ── Branding ─────────────────────────────────────────────────────────


def test_branding_warns_when_no_footer_elements(guardrail_check, outline):
    profile = {"design_rules": {"footer": {"elements": []}}}
    label, _ = guardrail_check.check_branding(outline, profile)
    assert label == "WARN"
