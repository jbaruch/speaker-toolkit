"""Boundary tests for the versioned speaker-pattern classification policy."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest


def _policy(classifier, tmp_path):
    return classifier.resolve_classification_policy(tmp_path)


def _override_policy(classifier, tmp_path, mutate):
    policy = copy.deepcopy(_policy(classifier, tmp_path)["semantic_policy"])
    mutate(policy)
    (tmp_path / "pattern-classification-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    return _policy(classifier, tmp_path)


def _opportunity(pattern_id, *, applicable, evaluable, detected):
    return {
        "pattern_id": pattern_id,
        "eligible_cohort_count": applicable,
        "not_applicable_count": 0,
        "evaluable_count": evaluable,
        "detected_count": detected,
        "unevaluable_count": applicable - evaluable,
    }


def _classify_positive(
    classifier, policy_stamp, *, applicable, evaluable, detected, absence=True
):
    return classifier._classify_positive(
        _opportunity(
            "positive", applicable=applicable, evaluable=evaluable, detected=detected
        ),
        absence_conclusion_capable=absence,
        policy=policy_stamp["semantic_policy"],
    )


def _classify_antipattern(
    classifier, policy_stamp, *, applicable, evaluable, detected, absence=True
):
    return classifier._classify_antipattern(
        _opportunity(
            "negative", applicable=applicable, evaluable=evaluable, detected=detected
        ),
        absence_conclusion_capable=absence,
        policy=policy_stamp["semantic_policy"],
    )


def test_absent_override_selects_bundled_default_without_prompt(
    classify_pattern_profile, tmp_path
):
    stamp = _policy(classify_pattern_profile, tmp_path)

    assert stamp["policy_id"] == "speaker-toolkit-default"
    assert stamp["policy_version"] == 1
    assert stamp["source"] == "bundled_default"
    assert len(stamp["semantic_sha256"]) == 64
    assert classify_pattern_profile.validate_policy_stamp(stamp) == stamp


def test_override_digest_ignores_formatting_only_changes(
    classify_pattern_profile, tmp_path
):
    default = _policy(classify_pattern_profile, tmp_path)
    policy_path = tmp_path / "pattern-classification-policy.json"
    policy_path.write_text(
        json.dumps(default["semantic_policy"], separators=(",", ":")),
        encoding="utf-8",
    )
    compact = _policy(classify_pattern_profile, tmp_path)
    policy_path.write_text(
        json.dumps(default["semantic_policy"], indent=4, sort_keys=True),
        encoding="utf-8",
    )
    formatted = _policy(classify_pattern_profile, tmp_path)

    assert compact["source"] == "vault_override"
    assert compact["semantic_sha256"] == formatted["semantic_sha256"]
    assert compact["semantic_sha256"] == default["semantic_sha256"]


def test_policy_digest_normalizes_signed_numeric_zero(
    classify_pattern_profile, tmp_path
):
    policy = copy.deepcopy(
        _policy(classify_pattern_profile, tmp_path)["semantic_policy"]
    )
    policy["positive_patterns"]["rare"]["maximum_upper_exclusive"] = -0.0
    negative_zero = classify_pattern_profile.canonical_policy_sha256(policy)
    policy["positive_patterns"]["rare"]["maximum_upper_exclusive"] = 0.0
    positive_zero = classify_pattern_profile.canonical_policy_sha256(policy)

    assert negative_zero == positive_zero


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"schema_version":1,"schema_version":1}',
        '{"schema_version": NaN}',
    ],
)
def test_present_invalid_override_aborts_instead_of_falling_back(
    classify_pattern_profile, tmp_path, payload
):
    (tmp_path / "pattern-classification-policy.json").write_text(
        payload, encoding="utf-8"
    )

    with pytest.raises(classify_pattern_profile.PatternClassificationError):
        _policy(classify_pattern_profile, tmp_path)


@pytest.mark.parametrize(
    ("applicable", "evaluable", "detected", "expected"),
    [
        (8, 6, 6, "signature"),
        (10, 8, 4, "regular"),
        (20, 16, 3, "occasional"),
        (20, 19, 1, "rare"),
        (8, 8, 0, "never_tried"),
        (0, 0, 0, "unclassified"),
    ],
)
def test_positive_default_threshold_boundaries(
    classify_pattern_profile,
    tmp_path,
    applicable,
    evaluable,
    detected,
    expected,
):
    row = _classify_positive(
        classify_pattern_profile,
        _policy(classify_pattern_profile, tmp_path),
        applicable=applicable,
        evaluable=evaluable,
        detected=detected,
    )

    assert row["classification"] == expected
    assert row["evidence"] == {
        "applicable_count": applicable,
        "evaluable_count": evaluable,
        "detected_count": detected,
        "unevaluable_count": applicable - evaluable,
        "applicable_coverage": None if applicable == 0 else evaluable / applicable,
        "lower": None if applicable == 0 else detected / applicable,
        "upper": None
        if applicable == 0
        else (detected + applicable - evaluable) / applicable,
    }
    assert row["reason_codes"]


def test_exclusive_positive_upper_boundary_stays_unclassified(
    classify_pattern_profile, tmp_path
):
    row = _classify_positive(
        classify_pattern_profile,
        _policy(classify_pattern_profile, tmp_path),
        applicable=10,
        evaluable=8,
        detected=5,
    )

    assert row["evidence"]["upper"] == 0.7
    assert row["classification"] == "unclassified"


@pytest.mark.parametrize(
    ("applicable", "evaluable", "detected", "excluded_tier"),
    [
        (7, 7, 7, "signature"),
        (10, 10, 6, "signature"),
        (8, 7, 4, "regular"),
        (100, 79, 45, "regular"),
        (10, 10, 3, "regular"),
        (7, 7, 2, "occasional"),
        (100, 79, 15, "occasional"),
        (100, 90, 14, "occasional"),
        (20, 16, 4, "occasional"),
        (7, 7, 1, "rare"),
        (20, 20, 3, "rare"),
    ],
)
def test_positive_default_threshold_fail_sides(
    classify_pattern_profile,
    tmp_path,
    applicable,
    evaluable,
    detected,
    excluded_tier,
):
    row = _classify_positive(
        classify_pattern_profile,
        _policy(classify_pattern_profile, tmp_path),
        applicable=applicable,
        evaluable=evaluable,
        detected=detected,
    )

    assert row["classification"] != excluded_tier


def test_rare_coverage_threshold_is_inclusive_and_enforced(
    classify_pattern_profile, tmp_path
):
    def widen_rare_band(policy):
        policy["positive_patterns"]["rare"]["maximum_upper_exclusive"] = 0.4
        policy["positive_patterns"]["occasional"]["minimum_lower"] = 0.4
        policy["positive_patterns"]["occasional"][
            "maximum_upper_exclusive"
        ] = 0.5
        policy["positive_patterns"]["regular"]["minimum_lower"] = 0.5

    policy = _override_policy(
        classify_pattern_profile, tmp_path, widen_rare_band
    )
    exact = _classify_positive(
        classify_pattern_profile,
        policy,
        applicable=10,
        evaluable=8,
        detected=1,
    )
    below = _classify_positive(
        classify_pattern_profile,
        policy,
        applicable=100,
        evaluable=79,
        detected=1,
    )

    assert exact["evidence"]["applicable_coverage"] == 0.8
    assert exact["classification"] == "rare"
    assert below["evidence"]["applicable_coverage"] == 0.79
    assert below["classification"] != "rare"


def test_positive_only_zero_is_not_yet_observed_never_never_tried(
    classify_pattern_profile, tmp_path
):
    row = _classify_positive(
        classify_pattern_profile,
        _policy(classify_pattern_profile, tmp_path),
        applicable=20,
        evaluable=20,
        detected=0,
        absence=False,
    )

    assert row["classification"] == "not_yet_observed"
    assert row["observation_status"] == "not_yet_observed"
    assert row["absence_conclusion_capable"] is False
    assert "absence_not_supported_by_catalog" in row["reason_codes"]


def test_conclusive_absence_below_sample_is_unclassified_not_not_yet_observed(
    classify_pattern_profile, tmp_path
):
    row = _classify_positive(
        classify_pattern_profile,
        _policy(classify_pattern_profile, tmp_path),
        applicable=7,
        evaluable=7,
        detected=0,
        absence=True,
    )

    assert row["classification"] == "unclassified"
    assert row["observation_status"] == "confirmed_absent"
    assert row["reason_codes"] == [
        "insufficient_applicable_sample",
        "insufficient_evaluable_sample",
    ]


@pytest.mark.parametrize(
    ("applicable", "evaluable", "detected", "expected"),
    [
        (8, 4, 4, "high_frequency"),
        (12, 10, 3, "moderate_frequency"),
        (20, 19, 1, "occasional"),
        (8, 8, 0, "confirmed_none"),
    ],
)
def test_antipattern_default_threshold_boundaries(
    classify_pattern_profile,
    tmp_path,
    applicable,
    evaluable,
    detected,
    expected,
):
    row = _classify_antipattern(
        classify_pattern_profile,
        _policy(classify_pattern_profile, tmp_path),
        applicable=applicable,
        evaluable=evaluable,
        detected=detected,
    )

    assert row["classification"] == expected
    assert row["reason_codes"]


@pytest.mark.parametrize(
    ("applicable", "evaluable", "detected", "excluded_tier"),
    [
        (7, 7, 4, "high_frequency"),
        (10, 10, 4, "high_frequency"),
        (7, 7, 3, "moderate_frequency"),
        (100, 79, 25, "moderate_frequency"),
        (8, 8, 2, "moderate_frequency"),
        (13, 13, 3, "moderate_frequency"),
        (10, 8, 3, "moderate_frequency"),
        (7, 7, 1, "occasional"),
        (100, 79, 1, "occasional"),
        (20, 16, 1, "occasional"),
        (7, 7, 0, "confirmed_none"),
    ],
)
def test_antipattern_default_threshold_fail_sides(
    classify_pattern_profile,
    tmp_path,
    applicable,
    evaluable,
    detected,
    excluded_tier,
):
    row = _classify_antipattern(
        classify_pattern_profile,
        _policy(classify_pattern_profile, tmp_path),
        applicable=applicable,
        evaluable=evaluable,
        detected=detected,
    )

    assert row["classification"] != excluded_tier


def test_antipattern_coverage_thresholds_are_inclusive_and_enforced(
    classify_pattern_profile, tmp_path
):
    policy = _policy(classify_pattern_profile, tmp_path)
    moderate_exact = _classify_antipattern(
        classify_pattern_profile,
        policy,
        applicable=20,
        evaluable=16,
        detected=5,
    )
    occasional_exact = _classify_antipattern(
        classify_pattern_profile,
        policy,
        applicable=100,
        evaluable=80,
        detected=1,
    )

    assert moderate_exact["evidence"]["applicable_coverage"] == 0.8
    assert moderate_exact["classification"] == "moderate_frequency"
    assert occasional_exact["evidence"]["applicable_coverage"] == 0.8
    assert occasional_exact["classification"] == "occasional"


def test_positive_only_antipattern_zero_is_unclassified_with_orthogonal_status(
    classify_pattern_profile, tmp_path
):
    row = _classify_antipattern(
        classify_pattern_profile,
        _policy(classify_pattern_profile, tmp_path),
        applicable=20,
        evaluable=20,
        detected=0,
        absence=False,
    )

    assert row["classification"] == "unclassified"
    assert row["observation_status"] == "not_yet_observed"


def _catalog(*, positive_only=False):
    return SimpleNamespace(
        entries={
            "p1": SimpleNamespace(
                observable=True,
                entry_type="pattern",
                absence_evaluable_from=None if positive_only else (("transcript",),),
            ),
            "p2": SimpleNamespace(
                observable=True,
                entry_type="pattern",
                absence_evaluable_from=(("transcript",),),
            ),
        }
    )


def _talk(index, *, p1, p2="detected", identity="a" * 64, date_value=None):
    outcomes = {"p1": p1, "p2": p2}
    detections = [
        {"pattern_id": pattern_id}
        for pattern_id, outcome in outcomes.items()
        if outcome == "detected"
    ]
    score = len(detections)
    return {
        "filename": f"talk-{index:02d}.md",
        "date": date_value or f"2026-01-{index + 1:02d}",
        "pattern_score": score,
        "pattern_observations": {
            "pattern_score": score,
            "patterns_detected": detections,
            "antipatterns_detected": [],
            "pattern_outcomes": [
                {"pattern_id": pattern_id, "outcome": outcomes[pattern_id]}
                for pattern_id in sorted(outcomes)
            ],
            "opportunity_coverage_identity": identity,
        },
    }


def test_joint_outcomes_and_five_plus_five_trends_are_deterministic(
    classify_pattern_profile, tmp_path
):
    talks = [
        *[_talk(index, p1="undetected") for index in range(5)],
        *[_talk(index, p1="detected") for index in range(5, 10)],
    ]
    result = classify_pattern_profile.classify_pattern_profile(
        talks,
        _policy(classify_pattern_profile, tmp_path),
        catalog=_catalog(),
    )

    p1 = next(
        row for row in result["pattern_classifications"] if row["pattern_id"] == "p1"
    )
    assert p1["classification"] == "regular"
    assert result["signature_combinations"] == [
        {
            "combination_id": "p1+p2",
            "pattern_ids": ["p1", "p2"],
            "evidence": {
                "applicable_count": 10,
                "evaluable_count": 10,
                "detected_count": 5,
                "unevaluable_count": 0,
                "applicable_coverage": 1.0,
                "lower": 0.5,
                "upper": 0.5,
            },
            "reason_codes": ["meets_signature_combination_thresholds"],
        }
    ]
    trend = result["trend_analysis"]
    assert trend["status"] == "available"
    assert trend["score"]["status"] == "improving"
    assert trend["breadth"]["status"] == "widening"
    p1_movement = next(
        row for row in trend["pattern_movements"] if row["pattern_id"] == "p1"
    )
    assert p1_movement["movement"] == "increasing"
    assert result["score_drivers"]["pattern_drivers"] == ["p1"]


def test_joint_denominator_distinguishes_not_applicable_and_unevaluable(
    classify_pattern_profile, tmp_path
):
    outcome_pairs = [
        *[("detected", "detected")] * 5,
        ("detected", "undetected"),
        ("undetected", "undetected"),
        ("not_applicable", "detected"),
        ("not_evaluable", "detected"),
        ("detected", "not_evaluable"),
    ]
    talks = [
        _talk(index, p1=p1, p2=p2)
        for index, (p1, p2) in enumerate(outcome_pairs)
    ]

    result = classify_pattern_profile.classify_pattern_profile(
        talks,
        _policy(classify_pattern_profile, tmp_path),
        catalog=_catalog(),
    )

    assert result["signature_combinations"] == [
        {
            "combination_id": "p1+p2",
            "pattern_ids": ["p1", "p2"],
            "evidence": {
                "applicable_count": 9,
                "evaluable_count": 7,
                "detected_count": 5,
                "unevaluable_count": 2,
                "applicable_coverage": 7 / 9,
                "lower": 5 / 9,
                "upper": 7 / 9,
            },
            "reason_codes": ["meets_signature_combination_thresholds"],
        }
    ]


def test_combination_thresholds_cover_exact_and_fail_sides(
    classify_pattern_profile, tmp_path
):
    policy = _policy(classify_pattern_profile, tmp_path)["semantic_policy"]
    positive = [
        {"pattern_id": "p1", "classification": "regular"},
        {"pattern_id": "p2", "classification": "signature"},
    ]

    def rows(*, total, detected):
        outcomes = [
            *[{"p1": "detected", "p2": "detected"} for _ in range(detected)],
            *[
                {"p1": "undetected", "p2": "detected"}
                for _ in range(total - detected)
            ],
        ]
        return classify_pattern_profile._combination_rows(
            [{} for _ in range(total)], outcomes, positive, policy=policy
        )

    exact_applicable = rows(total=8, detected=4)
    exact_detection_and_lower = rows(total=10, detected=4)
    below_applicable = rows(total=7, detected=4)
    below_detection_and_lower = rows(total=10, detected=3)

    assert exact_applicable[0]["evidence"]["applicable_count"] == 8
    assert exact_detection_and_lower[0]["evidence"] == {
        "applicable_count": 10,
        "evaluable_count": 10,
        "detected_count": 4,
        "unevaluable_count": 0,
        "applicable_coverage": 1.0,
        "lower": 0.4,
        "upper": 0.4,
    }
    assert below_applicable == []
    assert below_detection_and_lower == []


def test_trends_distinguish_stable_indeterminate_and_unavailable(
    classify_pattern_profile, tmp_path
):
    stable, _ = classify_pattern_profile._movement(
        {"applicable_count": 5, "lower": 0.4, "upper": 0.4},
        {"applicable_count": 5, "lower": 0.4, "upper": 0.4},
        threshold=0.2,
    )
    indeterminate, _ = classify_pattern_profile._movement(
        {"applicable_count": 5, "lower": 0.2, "upper": 0.8},
        {"applicable_count": 5, "lower": 0.2, "upper": 0.8},
        threshold=0.2,
    )
    unavailable, _ = classify_pattern_profile._movement(
        {"applicable_count": 4, "lower": 0.2, "upper": 0.8},
        {"applicable_count": 5, "lower": 0.2, "upper": 0.8},
        threshold=0.2,
    )
    unavailable_four_of_five, _ = classify_pattern_profile._movement(
        {"applicable_count": 4, "lower": 0.0, "upper": 0.0},
        {"applicable_count": 4, "lower": 1.0, "upper": 1.0},
        threshold=0.2,
    )

    assert (stable, indeterminate, unavailable) == (
        "stable",
        "indeterminate",
        "unavailable",
    )
    assert unavailable_four_of_five == "unavailable"


def test_movement_threshold_boundaries_are_conservative(
    classify_pattern_profile,
):
    increasing, _ = classify_pattern_profile._movement(
        {"applicable_count": 5, "lower": 0.0, "upper": 0.0},
        {"applicable_count": 5, "lower": 0.2, "upper": 0.2},
        threshold=0.2,
    )
    decreasing, _ = classify_pattern_profile._movement(
        {"applicable_count": 5, "lower": 0.2, "upper": 0.2},
        {"applicable_count": 5, "lower": 0.0, "upper": 0.0},
        threshold=0.2,
    )
    boundary_reachable, _ = classify_pattern_profile._movement(
        {"applicable_count": 5, "lower": 0.0, "upper": 0.0},
        {"applicable_count": 5, "lower": 0.0, "upper": 0.2},
        threshold=0.2,
    )
    fractional_increasing, _ = classify_pattern_profile._movement(
        {"applicable_count": 5, "lower": 0.4, "upper": 0.4},
        {"applicable_count": 5, "lower": 0.6, "upper": 0.6},
        threshold=0.2,
    )
    fractional_decreasing, _ = classify_pattern_profile._movement(
        {"applicable_count": 5, "lower": 0.6, "upper": 0.6},
        {"applicable_count": 5, "lower": 0.4, "upper": 0.4},
        threshold=0.2,
    )
    upper_boundary, _ = classify_pattern_profile._movement(
        {"applicable_count": 5, "lower": 0.8, "upper": 0.8},
        {"applicable_count": 5, "lower": 1.0, "upper": 1.0},
        threshold=0.2,
    )

    assert increasing == "increasing"
    assert decreasing == "decreasing"
    assert boundary_reachable == "indeterminate"
    assert fractional_increasing == "increasing"
    assert fractional_decreasing == "decreasing"
    assert upper_boundary == "increasing"


def test_score_and_breadth_thresholds_bracket_and_include_the_boundary(
    classify_pattern_profile, tmp_path
):
    def result(detected_recent, policy):
        talks = [
            *[_talk(index, p1="undetected") for index in range(5)],
            *[
                _talk(index, p1="detected" if index - 5 < detected_recent else "undetected")
                for index in range(5, 10)
            ],
        ]
        return classify_pattern_profile.classify_pattern_profile(
            talks, policy, catalog=_catalog()
        )["trend_analysis"]

    default = _policy(classify_pattern_profile, tmp_path)
    below = result(2, default)
    above = result(3, default)

    def reachable_boundary(policy):
        policy["trends"]["score_delta"] = 0.4
        policy["trends"]["breadth_delta"] = 0.4

    exact_policy = _override_policy(
        classify_pattern_profile, tmp_path, reachable_boundary
    )
    exact = result(2, exact_policy)

    assert below["score"]["delta"] == pytest.approx(0.4)
    assert below["score"]["status"] == "stable"
    assert below["breadth"]["status"] == "stable"
    assert above["score"]["delta"] == pytest.approx(0.6)
    assert above["score"]["status"] == "improving"
    assert above["breadth"]["status"] == "widening"
    assert exact["score"]["status"] == "improving"
    assert exact["breadth"]["status"] == "widening"


def test_trends_require_at_least_one_evaluable_opportunity(
    classify_pattern_profile, tmp_path
):
    talks = [
        _talk(index, p1="not_evaluable", p2="not_evaluable")
        for index in range(10)
    ]

    result = classify_pattern_profile.classify_pattern_profile(
        talks,
        _policy(classify_pattern_profile, tmp_path),
        catalog=_catalog(),
    )

    assert result["trend_analysis"]["status"] == "unavailable"
    assert result["trend_analysis"]["reason_codes"] == [
        "no_evaluable_pattern_opportunities"
    ]
    assert result["classification_availability"]["trends"] == {
        "status": "unavailable",
        "reason_codes": ["no_evaluable_pattern_opportunities"],
    }
    assert result["score_trend"] == "unavailable"


def test_trend_sample_reports_invalid_dates_and_selects_newest_ten(
    classify_pattern_profile, tmp_path
):
    talks = [_talk(index, p1="detected") for index in range(11)]
    invalid = _talk(11, p1="detected")
    invalid.pop("date")
    talks.append(invalid)

    result = classify_pattern_profile.classify_pattern_profile(
        talks,
        _policy(classify_pattern_profile, tmp_path),
        catalog=_catalog(),
    )

    sample = result["trend_analysis"]["sample"]
    assert result["trend_analysis"]["status"] == "available"
    assert sample["valid_date_talk_count"] == 11
    assert sample["invalid_date_filenames"] == ["talk-11.md"]
    assert sample["selected_filenames"] == [
        f"talk-{index:02d}.md" for index in range(1, 11)
    ]


def test_incomparable_opportunity_identity_makes_trends_unavailable(
    classify_pattern_profile, tmp_path
):
    talks = [_talk(index, p1="detected") for index in range(10)]
    talks[-1] = _talk(9, p1="detected", identity="b" * 64)

    result = classify_pattern_profile.classify_pattern_profile(
        talks,
        _policy(classify_pattern_profile, tmp_path),
        catalog=_catalog(),
    )

    assert result["trend_analysis"]["status"] == "unavailable"
    assert result["trend_analysis"]["reason_codes"] == [
        "incomparable_opportunity_identities"
    ]
    assert result["classification_availability"]["trends"] == {
        "status": "unavailable",
        "reason_codes": ["incomparable_opportunity_identities"],
    }


def test_policy_digest_change_is_visible_as_comparison_reset_identity(
    classify_pattern_profile, tmp_path
):
    default = _policy(classify_pattern_profile, tmp_path)
    override_policy = copy.deepcopy(default["semantic_policy"])
    override_policy["policy_id"] = "speaker-custom"
    (tmp_path / "pattern-classification-policy.json").write_text(
        json.dumps(override_policy), encoding="utf-8"
    )
    override = _policy(classify_pattern_profile, tmp_path)

    assert override["policy_id"] == "speaker-custom"
    assert override["semantic_sha256"] != default["semantic_sha256"]


@pytest.mark.parametrize(
    "lane",
    ["positive_patterns", "antipattern_recurrence"],
)
def test_override_cannot_redefine_confirmed_absence_as_nonzero_detection(
    classify_pattern_profile, tmp_path, lane
):
    default = _policy(classify_pattern_profile, tmp_path)
    override_policy = copy.deepcopy(default["semantic_policy"])
    tier = "never_tried" if lane == "positive_patterns" else "confirmed_none"
    override_policy[lane][tier]["maximum_detections"] = 1
    (tmp_path / "pattern-classification-policy.json").write_text(
        json.dumps(override_policy), encoding="utf-8"
    )

    with pytest.raises(classify_pattern_profile.PatternClassificationError):
        _policy(classify_pattern_profile, tmp_path)


@pytest.mark.parametrize(
    ("lane", "tier"),
    [
        ("positive_patterns", "rare"),
        ("antipattern_recurrence", "high_frequency"),
        ("antipattern_recurrence", "moderate_frequency"),
        ("antipattern_recurrence", "occasional"),
    ],
)
def test_override_requires_usage_classifications_to_have_a_detection(
    classify_pattern_profile, tmp_path, lane, tier
):
    policy = copy.deepcopy(
        _policy(classify_pattern_profile, tmp_path)["semantic_policy"]
    )
    policy[lane][tier]["minimum_detections"] = 0
    (tmp_path / "pattern-classification-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )

    with pytest.raises(
        classify_pattern_profile.PatternClassificationError,
        match="minimum_detections must be a positive integer",
    ):
        _policy(classify_pattern_profile, tmp_path)


@pytest.mark.parametrize("tier", ["signature", "regular", "occasional"])
def test_override_requires_positive_usage_lower_bounds(
    classify_pattern_profile, tmp_path, tier
):
    policy = copy.deepcopy(
        _policy(classify_pattern_profile, tmp_path)["semantic_policy"]
    )
    policy["positive_patterns"][tier]["minimum_lower"] = 0
    (tmp_path / "pattern-classification-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )

    with pytest.raises(
        classify_pattern_profile.PatternClassificationError,
        match=rf"{tier}\.minimum_lower must be greater than zero",
    ):
        _policy(classify_pattern_profile, tmp_path)


def test_schema_v1_override_cannot_change_combination_result_cap(
    classify_pattern_profile, tmp_path
):
    policy = copy.deepcopy(
        _policy(classify_pattern_profile, tmp_path)["semantic_policy"]
    )
    policy["signature_combinations"]["maximum_results"] = 11
    (tmp_path / "pattern-classification-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )

    with pytest.raises(classify_pattern_profile.PatternClassificationError):
        _policy(classify_pattern_profile, tmp_path)


def test_override_rejects_unknown_semantic_fields(
    classify_pattern_profile, tmp_path
):
    policy = copy.deepcopy(
        _policy(classify_pattern_profile, tmp_path)["semantic_policy"]
    )
    policy["future_semantics"] = {"enabled": True}
    (tmp_path / "pattern-classification-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )

    with pytest.raises(
        classify_pattern_profile.PatternClassificationError,
        match="fields are noncanonical",
    ):
        _policy(classify_pattern_profile, tmp_path)
