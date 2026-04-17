"""Tests for guardrail-check.py — outline guardrail validation."""


OUTLINE_PASSING = """\
## Opening [2 min, slides 1-3]

### Slide 1: Title Slide

### Slide 2: Agenda

### Slide 3: Hook

## Act 1: The Challenge [5 min, slides 4-8]

### Slide 4: Problem Statement

### Slide 5: Context

### Slide 6: Data
### Slide 7: More Data
### Slide 8: Summary

## Act 2: The Solution [8 min, slides 9-18]

### Slide 9: Approach

### Slide 10: Implementation

### Slide 18: Demo

## Closing [3 min, slides 19-20]
### Slide 19: Summary
- Speaker: Here are the key takeaways and summary of what we covered.

### Slide 20: Call to Action
- Speaker: Your call to action: try this technique this week.
- Visual: shownotes QR code and social handles

Total slides: 20

[CUT LINE after slide 12]
"""

PROFILE = {
    "rhetoric_defaults": {
        "default_duration_minutes": 45,
        "profanity_calibration": "none",
    },
    "guardrail_sources": {
        "slide_budgets": [
            {"duration_minutes": 45, "max_slides": 60}
        ],
        "act1_ratio_limits": [
            {"max_percentage": 45}
        ],
    },
}


def test_count_single_slides(guardrail_check):
    text = "### Slide 1: A\n### Slide 2: B\n### Slide 3: C\n"
    assert guardrail_check.count_slides(text) == 3


def test_count_range_slides(guardrail_check):
    text = "### Slide 30-33: Group\n"
    assert guardrail_check.count_slides(text) == 4


def test_count_total_slides_line(guardrail_check):
    text = "### Slide 1: A\n### Slide 2: B\nTotal slides: 20\n"
    # "Total slides:" overrides header count
    assert guardrail_check.count_slides(text) == 20


def test_budget_pass(guardrail_check):
    label, _ = guardrail_check.check_slide_budget(20, PROFILE)
    assert label == "PASS"


def test_budget_fail(guardrail_check):
    label, _ = guardrail_check.check_slide_budget(65, PROFILE)
    assert label == "FAIL"


def test_budget_warn_near_limit(guardrail_check):
    label, _ = guardrail_check.check_slide_budget(58, PROFILE)
    assert label == "WARN"


def test_act1_ratio_pass(guardrail_check):
    sections = guardrail_check.find_sections(OUTLINE_PASSING)
    total = guardrail_check.count_slides(OUTLINE_PASSING)
    label, _ = guardrail_check.check_act1_ratio(sections, total, PROFILE)
    assert label == "PASS"


def test_act1_ratio_fail(guardrail_check):
    # Act 1 taking 60% of slides
    outline = """\
## Opening [2 min, slides 1-2]
## Act 1: The Problem [10 min, slides 3-14]
## Act 2: Solution [5 min, slides 15-20]
Total slides: 20
"""
    sections = guardrail_check.find_sections(outline)
    label, _ = guardrail_check.check_act1_ratio(sections, 20, PROFILE)
    assert label == "FAIL"


def test_closing_pass(guardrail_check):
    label, _ = guardrail_check.check_closing(OUTLINE_PASSING)
    assert label == "PASS"


def test_closing_fail_missing_cta(guardrail_check):
    outline = "## Closing\n### Slide 20: Thank You\n- Visual: QR code\n"
    label, detail = guardrail_check.check_closing(outline)
    assert label == "FAIL"
    assert "CTA" in detail


def test_cut_lines_pass(guardrail_check):
    label, _ = guardrail_check.check_cut_lines(OUTLINE_PASSING)
    assert label == "PASS"


def test_cut_lines_fail(guardrail_check):
    label, _ = guardrail_check.check_cut_lines("No cut lines here")
    assert label == "FAIL"


def test_profanity_pass(guardrail_check):
    label, _ = guardrail_check.check_profanity(OUTLINE_PASSING, PROFILE)
    assert label == "PASS"


def test_profanity_fail(guardrail_check):
    outline = "- Speaker: This is some damn fine code\n"
    label, _ = guardrail_check.check_profanity(outline, PROFILE)
    assert label == "FAIL"


def test_profanity_warn_when_allowed(guardrail_check):
    profile = dict(PROFILE)
    profile["rhetoric_defaults"] = {"profanity_calibration": "mild"}
    outline = "- Speaker: What the hell happened here\n"
    label, _ = guardrail_check.check_profanity(outline, profile)
    assert label == "WARN"
