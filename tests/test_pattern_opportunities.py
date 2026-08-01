"""Deterministic scoring-v5 opportunity-row aggregation tests."""

from __future__ import annotations

import copy
import importlib

import pytest


def _modules():
    opportunities = importlib.import_module("pattern_opportunities")
    catalog = opportunities.load_catalog()
    patterns = sorted(
        pattern_id
        for pattern_id, entry in catalog.entries.items()
        if entry.observable and entry.entry_type == "pattern"
    )
    antipatterns = sorted(
        pattern_id
        for pattern_id, entry in catalog.entries.items()
        if entry.observable and entry.entry_type == "antipattern"
    )
    return opportunities, catalog, patterns, antipatterns


def _talk(filename, overrides=None):
    _, _, patterns, antipatterns = _modules()
    overrides = overrides or {}
    observable_ids = sorted(patterns + antipatterns)
    outcomes = {
        pattern_id: overrides.get(pattern_id, "undetected")
        for pattern_id in observable_ids
    }
    return {
        "filename": filename,
        "pattern_observations": {
            "patterns_detected": [
                {"pattern_id": pattern_id}
                for pattern_id in patterns
                if outcomes[pattern_id] == "detected"
            ],
            "antipatterns_detected": [
                {"pattern_id": pattern_id}
                for pattern_id in antipatterns
                if outcomes[pattern_id] == "detected"
            ],
            "pattern_outcomes": [
                {"pattern_id": pattern_id, "outcome": outcomes[pattern_id]}
                for pattern_id in observable_ids
            ],
        },
    }


def test_aggregates_pattern_specific_denominators_without_global_bias():
    opportunities, catalog, patterns, antipatterns = _modules()
    pattern_id = patterns[0]
    antipattern_id = antipatterns[0]
    rows = opportunities.build_pattern_opportunity_rows(
        [
            _talk(
                "a.md",
                {pattern_id: "detected", antipattern_id: "not_applicable"},
            ),
            _talk("b.md"),
            _talk(
                "c.md",
                {pattern_id: "not_evaluable", antipattern_id: "detected"},
            ),
        ],
        catalog=catalog,
    )

    pattern_row = next(
        row for row in rows["pattern_usage"] if row["pattern_id"] == pattern_id
    )
    assert pattern_row == {
        "pattern_id": pattern_id,
        "detected_count": 1,
        "evaluable_count": 2,
        "unevaluable_count": 1,
        "not_applicable_count": 0,
        "eligible_cohort_count": 3,
        "coverage": 2 / 3,
        "out_of": 2,
        "times_used": 1,
        "usage_rate": 0.5,
    }
    antipattern_row = next(
        row
        for row in rows["antipattern_frequency"]
        if row["pattern_id"] == antipattern_id
    )
    assert antipattern_row == {
        "pattern_id": antipattern_id,
        "detected_count": 1,
        "evaluable_count": 2,
        "unevaluable_count": 0,
        "not_applicable_count": 1,
        "eligible_cohort_count": 3,
        "coverage": 2 / 3,
        "out_of": 2,
        "times_detected": 1,
        "frequency_rate": 0.5,
    }


def test_empty_cohort_still_publishes_exhaustive_unknown_rows():
    opportunities, catalog, patterns, antipatterns = _modules()
    rows = opportunities.build_pattern_opportunity_rows([], catalog=catalog)

    assert len(rows["pattern_usage"]) == len(patterns)
    assert len(rows["antipattern_frequency"]) == len(antipatterns)
    for row in rows["pattern_usage"] + rows["antipattern_frequency"]:
        assert row["detected_count"] == 0
        assert row["evaluable_count"] == 0
        assert row["eligible_cohort_count"] == 0
        assert row["coverage"] is None
        rate = row.get("usage_rate", row.get("frequency_rate"))
        assert rate is None


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda outcomes: outcomes.pop(),
            "sorted and exhaustive",
        ),
        (
            lambda outcomes: outcomes.append(copy.deepcopy(outcomes[0])),
            "duplicates",
        ),
        (
            lambda outcomes: outcomes[0].update(outcome="future"),
            "must be one of",
        ),
        (
            lambda outcomes: outcomes[0].update(outcome=[]),
            "must be one of",
        ),
        (
            lambda outcomes: outcomes[0].update(extra=True),
            "exactly pattern_id and outcome",
        ),
    ],
)
def test_persisted_outcome_matrix_fails_closed(mutation, message):
    opportunities, catalog, _, _ = _modules()
    talk = _talk("bad.md")
    mutation(talk["pattern_observations"]["pattern_outcomes"])

    with pytest.raises(opportunities.PatternOpportunityError, match=message):
        opportunities.build_pattern_opportunity_rows([talk], catalog=catalog)


def test_detected_outcome_must_match_canonical_detection_lane():
    opportunities, catalog, patterns, _ = _modules()
    talk = _talk("bad.md", {patterns[0]: "detected"})
    talk["pattern_observations"]["patterns_detected"] = []

    with pytest.raises(
        opportunities.PatternOpportunityError,
        match="patterns_detected does not match",
    ):
        opportunities.build_pattern_opportunity_rows([talk], catalog=catalog)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda rows: rows["pattern_usage"].pop(),
            "one sorted row for every observable catalog pattern",
        ),
        (
            lambda rows: rows["pattern_usage"].append(
                copy.deepcopy(rows["pattern_usage"][0])
            ),
            "duplicates",
        ),
        (
            lambda rows: rows["pattern_usage"][0].update(
                pattern_id=rows["antipattern_frequency"][0]["pattern_id"]
            ),
            "unknown_or_wrong_polarity",
        ),
        (
            lambda rows: rows["pattern_usage"][0].update(usage_rate=0.123),
            "canonical ratio",
        ),
        (
            lambda rows: rows["pattern_usage"][0].update(coverage=0.123),
            "canonical ratio",
        ),
        (
            lambda rows: rows["pattern_usage"][0].update(out_of=2),
            "out_of must equal evaluable_count",
        ),
        (
            lambda rows: rows["pattern_usage"][0].update(unevaluable_count=1),
            "outcome counts must satisfy",
        ),
    ],
)
def test_catalog_aware_row_validator_rejects_fabrication(mutation, message):
    opportunities, catalog, _, _ = _modules()
    rows = opportunities.build_pattern_opportunity_rows(
        [_talk("a.md")], catalog=catalog
    )
    mutation(rows)

    errors = opportunities.validate_pattern_opportunity_rows(
        rows["pattern_usage"],
        rows["antipattern_frequency"],
        eligible_cohort_count=1,
        catalog=catalog,
    )

    assert any(message in error for error in errors)
