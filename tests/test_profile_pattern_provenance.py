"""Profile schema-v3 tests for exact pattern-cohort provenance."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest


def _pattern_baseline(validate_profile, *, count: int = 2) -> dict[str, Any]:
    score_sum = 14 if count else 0
    average = 7.0 if count else None
    catalog_fingerprint, scoring_schema = (
        validate_profile.active_pattern_generation_identity()
    )
    return {
        "schema_version": 1,
        "as_of": "2025-01-02T03:04:05+00:00",
        "scope": "global",
        "active_batch_excluded": False,
        "excluded_filenames": [],
        "eligible_statuses": ["processed", "processed_partial"],
        "pattern_scoring_generation_status": "current",
        "pattern_scoring_generation_reasons": [],
        "pattern_catalog_fingerprint": catalog_fingerprint,
        "pattern_scoring_schema_version": scoring_schema,
        "scored_talk_count": count,
        "pattern_score_sum": score_sum,
        "average_pattern_score": average,
    }


def _pattern_profile(validate_profile, *, count: int = 2) -> dict[str, Any]:
    empty = count == 0
    filenames = [] if empty else ["example-a.md", "example-b.md"]
    return {
        "pattern_baseline": _pattern_baseline(validate_profile, count=count),
        "baseline_talk_filenames": filenames,
        "talks_scored": count,
        "average_pattern_score": None if empty else 7.0,
        "score_trend": "unavailable" if empty else "stable",
        "pattern_breadth": {
            "avg_distinct_patterns_per_talk": None if empty else 4.5,
            "trend": "unavailable" if empty else "stable",
            "note": "Pattern breadth from the exact current cohort.",
        },
        "underused_patterns": [],
        "score_drivers": {
            "direction": "unavailable" if empty else "insufficient_history",
            "antipattern_drivers": [],
            "pattern_drivers": [],
            "note": "Score drivers from the exact current cohort.",
        },
        "by_mode": [],
        "strengths": [],
        "strengths_note": "Current-generation strengths only.",
        "note": "Only observable catalog entries are included.",
        "pattern_usage": (
            []
            if empty
            else [
                {
                    "pattern_id": "example-pattern",
                    "times_used": 1,
                    "out_of": count,
                }
            ]
        ),
        "antipattern_frequency": (
            []
            if empty
            else [
                {
                    "pattern_id": "example-antipattern",
                    "times_detected": 1,
                    "out_of": count,
                }
            ]
        ),
        "never_used_patterns": [],
        "signature_combinations": [],
        "mastery_levels": {
            "signature": [],
            "regular": [],
            "occasional": [],
            "rare": [],
            "never_tried": [],
        },
    }


def _profile(validate_profile, *, count: int = 2) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "generated_date": "2025-01-02",
        "talks_analyzed": 4,
        "speaker": {},
        "infrastructure": {},
        "presentation_modes": [],
        "instrument_catalog": {},
        "rhetoric_defaults": {},
        "confirmed_intents": [],
        "guardrail_sources": {"recurring_issues": []},
        "pacing": {},
        "pattern_profile": _pattern_profile(validate_profile, count=count),
        "visual_style_history": {},
        "publishing_process": {},
        "design_rules": {},
        "badges": [],
    }


def _run(validate_profile, profile, tmp_path, capsys):
    path = tmp_path / "speaker-profile.json"
    path.write_text(json.dumps(profile))
    return_code = validate_profile.main(["validate-profile.py", str(path)])
    captured = capsys.readouterr()
    return return_code, json.loads(captured.out)


def test_current_profile_binds_every_pattern_denominator_to_one_cohort(
    validate_profile,
    tmp_path,
    capsys,
):
    return_code, report = _run(
        validate_profile,
        _profile(validate_profile),
        tmp_path,
        capsys,
    )

    assert return_code == 0
    assert report == {
        "valid": True,
        "schema_version": 3,
        "missing_keys": [],
        "errors": [],
    }


def test_reusable_assessment_distinguishes_current_empty_and_stale_history(
    validate_profile,
):
    current = validate_profile.assess_pattern_profile(
        _pattern_profile(validate_profile)
    )
    empty = validate_profile.assess_pattern_profile(
        _pattern_profile(validate_profile, count=0)
    )
    stale_profile = _pattern_profile(validate_profile)
    stale_profile["pattern_baseline"]["pattern_catalog_fingerprint"] = "0" * 64
    stale = validate_profile.assess_pattern_profile(stale_profile)

    assert (
        current.current_contract,
        current.catalog_fields_available,
        current.scored_talk_count,
        current.reason_codes,
    ) == (True, True, 2, ())
    assert (
        empty.current_contract,
        empty.catalog_fields_available,
        empty.scored_talk_count,
        empty.reason_codes,
    ) == (True, False, 0, ("empty_current_pattern_cohort",))
    assert stale.current_contract is False
    assert stale.catalog_fields_available is False
    assert stale.reason_codes == (
        "pattern_catalog_fingerprint_mismatch",
        "invalid_pattern_profile_contract",
    )


def test_profile_v2_is_noncurrent_and_rejected(validate_profile, tmp_path, capsys):
    profile = _profile(validate_profile)
    profile["schema_version"] = 2

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert report["valid"] is False
    assert report["errors"] == ["schema_version is 2 (expected 3)"]


def test_missing_pattern_baseline_is_rejected(validate_profile, tmp_path, capsys):
    profile = _profile(validate_profile)
    del profile["pattern_profile"]["pattern_baseline"]

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any(
        "pattern_baseline" in error for error in report["errors"]
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "pattern_catalog_fingerprint",
            "0" * 64,
            "does not match the active catalog",
        ),
        (
            "pattern_scoring_schema_version",
            1,
            "expected active schema",
        ),
    ],
)
def test_stale_scoring_generation_is_rejected(
    validate_profile,
    tmp_path,
    capsys,
    field,
    value,
    message,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["pattern_baseline"][field] = value

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any(message in error for error in report["errors"])


def test_noncanonical_baseline_arithmetic_is_rejected(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["pattern_baseline"][
        "average_pattern_score"
    ] = 7.1

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert "ROUND_HALF_EVEN count/sum result" in report["errors"][0]


def test_claim_time_baseline_is_not_valid_profile_provenance(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    baseline = profile["pattern_profile"]["pattern_baseline"]
    baseline["active_batch_excluded"] = True
    baseline["excluded_filenames"] = ["active-talk.md"]

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any("full-cohort snapshot" in error for error in report["errors"])
    assert any("excluded_filenames must be []" in error for error in report["errors"])


@pytest.mark.parametrize(
    "filenames",
    [
        ["example-b.md", "example-a.md"],
        ["example-a.md", "example-a.md"],
        ["example-a.md"],
    ],
)
def test_cohort_filename_identity_must_be_canonical_and_complete(
    validate_profile,
    tmp_path,
    capsys,
    filenames,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["baseline_talk_filenames"] = filenames

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any("baseline_talk_filenames" in error for error in report["errors"])


def test_talks_scored_must_equal_baseline_count(validate_profile, tmp_path, capsys):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["talks_scored"] = 3

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any("talks_scored must equal" in error for error in report["errors"])


def test_profile_average_must_equal_canonical_baseline(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["average_pattern_score"] = 6.9

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any(
        "average_pattern_score must equal" in error
        for error in report["errors"]
    )


def test_boolean_profile_average_is_not_a_number(validate_profile, tmp_path, capsys):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["pattern_baseline"]["pattern_score_sum"] = 2
    profile["pattern_profile"]["pattern_baseline"]["average_pattern_score"] = 1.0
    profile["pattern_profile"]["average_pattern_score"] = True

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any(
        "average_pattern_score must equal" in error
        for error in report["errors"]
    )


def test_nonempty_profile_requires_complete_nested_schema(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    del profile["pattern_profile"]["pattern_usage"]
    del profile["pattern_profile"]["pattern_breadth"]["note"]

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any("missing required schema-v3 fields" in error for error in report["errors"])
    assert any(
        "pattern_breadth is missing required fields" in error
        for error in report["errors"]
    )


def test_current_profile_rejects_unknown_nested_shape(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["legacy_score"] = 9
    profile["pattern_profile"]["mastery_levels"]["unknown"] = []

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any("unknown schema-v3 fields" in error for error in report["errors"])
    assert any("unknown tiers" in error for error in report["errors"])


def test_nonempty_small_cohort_requires_neutral_trend(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["score_trend"] = "declining"
    profile["pattern_profile"]["score_drivers"]["direction"] = "declining"

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any("fewer than 10 current talks" in error for error in report["errors"])


def test_nested_out_of_denominator_cannot_use_another_cohort(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["pattern_usage"][0]["out_of"] = 4

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any(
        "pattern_profile.pattern_usage[0].out_of" in error
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("pattern_usage", 0, "times_used"), 3, "times_used"),
        (("antipattern_frequency", 0, "times_detected"), -1, "times_detected"),
        (("signature_combinations", 0, "frequency"), 4, "frequency"),
    ],
)
def test_catalog_counts_must_fit_the_current_cohort(
    validate_profile,
    tmp_path,
    capsys,
    path,
    value,
    message,
):
    profile = _profile(validate_profile)
    if path[0] == "signature_combinations":
        profile["pattern_profile"][path[0]] = [
            {"patterns": ["example-pattern"], "frequency": 1, "label": "Example"}
        ]
    profile["pattern_profile"][path[0]][path[1]][path[2]] = value

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any(message in error for error in report["errors"])


def test_per_mode_count_cannot_exceed_global_cohort(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["by_mode"] = [
        {"mode_id": "example", "talks_in_mode": 3, "stable": True}
    ]

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any("talks_in_mode" in error for error in report["errors"])


def test_empty_current_cohort_is_explicitly_unavailable(
    validate_profile,
    tmp_path,
    capsys,
):
    return_code, report = _run(
        validate_profile,
        _profile(validate_profile, count=0),
        tmp_path,
        capsys,
    )

    assert return_code == 0
    assert report["valid"] is True


def test_empty_current_cohort_rejects_legacy_pattern_fallback(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile, count=0)
    pattern_profile = profile["pattern_profile"]
    pattern_profile["score_trend"] = "stable"
    pattern_profile["pattern_usage"] = [
        {"pattern_id": "legacy-pattern", "times_used": 3, "out_of": 0}
    ]
    pattern_profile["mastery_levels"]["signature"] = ["legacy-pattern"]

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any("score_trend must be 'unavailable'" in error for error in report["errors"])
    assert any("pattern_usage must be []" in error for error in report["errors"])
    assert any(
        "mastery_levels.signature must be []" in error
        for error in report["errors"]
    )


def test_pattern_baseline_rejects_unknown_fields(validate_profile, tmp_path, capsys):
    profile = copy.deepcopy(_profile(validate_profile))
    profile["pattern_profile"]["pattern_baseline"]["legacy_average"] = 7.0

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert "fields are noncanonical" in report["errors"][0]


@pytest.mark.parametrize("duplicate", ["signature_combinations", "mastery_levels"])
def test_rhetoric_defaults_cannot_duplicate_pattern_history(
    validate_profile,
    tmp_path,
    capsys,
    duplicate,
):
    profile = _profile(validate_profile)
    profile["rhetoric_defaults"][duplicate] = [] if duplicate.endswith("s") else {}

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any(
        "rhetoric_defaults duplicates catalog history" in error
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    ("container", "entry"),
    [
        ("recurring_issues", {"id": "ambiguous"}),
        ("recurring_issues", {"id": "pattern-copy", "source_lane": "pattern_catalog"}),
        ("badges", {"id": "pattern-copy", "source_lane": "non_pattern", "pattern_id": "example"}),
    ],
)
def test_catalog_history_cannot_hide_in_top_level_entries(
    validate_profile,
    tmp_path,
    capsys,
    container,
    entry,
):
    profile = _profile(validate_profile)
    if container == "recurring_issues":
        profile["guardrail_sources"][container] = [entry]
    else:
        profile[container] = [entry]

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 1
    assert any(container in error for error in report["errors"])


def test_explicit_non_pattern_entries_remain_available(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["guardrail_sources"]["recurring_issues"] = [
        {
            "id": "pacing-overrun",
            "source_lane": "non_pattern",
            "guardrail": "Leave enough time for the close.",
        }
    ]
    profile["badges"] = [
        {
            "id": "visual-continuity",
            "source_lane": "non_pattern",
            "evidence": "A recurring visual device appears across decks.",
        }
    ]

    return_code, report = _run(
        validate_profile, profile, tmp_path, capsys
    )

    assert return_code == 0
    assert report["valid"] is True
