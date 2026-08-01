"""Focused tests for the pure adherence-baseline snapshot contract."""

import importlib.util
import math
import sys
from copy import deepcopy
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "vault-ingress"
    / "scripts"
    / "adherence_baseline.py"
)
CATALOG = "a" * 64
OTHER_CATALOG = "b" * 64
AS_OF = "2026-07-31T13:30:45.987654-05:00"


@pytest.fixture(scope="session")
def adherence_baseline():
    spec = importlib.util.spec_from_file_location("adherence_baseline", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["adherence_baseline"] = module
    spec.loader.exec_module(module)
    return module


def _talk(
    filename,
    score,
    *,
    status="processed",
    catalog=CATALOG,
    scoring_schema=2,
    generation_status="current",
    generation_reasons=None,
    nested=True,
):
    if generation_reasons is None:
        generation_reasons = []
    talk = {
        "filename": filename,
        "status": status,
        "pattern_catalog_fingerprint": catalog,
        "pattern_scoring_schema_version": scoring_schema,
        "pattern_scoring_generation_status": generation_status,
        "pattern_scoring_generation_reasons": generation_reasons,
        "pattern_score": score,
    }
    if nested:
        talk["pattern_observations"] = {"pattern_score": score}
    return talk


def _build(adherence_baseline, talks, *, selected=()):
    return adherence_baseline.build_adherence_baseline(
        talks,
        selected_filenames=selected,
        as_of=AS_OF,
        pattern_catalog_fingerprint=CATALOG,
        pattern_scoring_schema_version=2,
    )


def test_builds_deterministic_global_snapshot_with_exact_batch_exclusion(
    adherence_baseline,
):
    talks = [
        _talk("active.md", 100),
        _talk("active.md-copy", 3),
        _talk("partial.md", -1, status="processed_partial"),
        _talk("processed.md", 2),
        _talk("pending.md", 90, status="pending"),
        _talk("old-catalog.md", 80, catalog=OTHER_CATALOG),
        _talk("old-scoring.md", 70, scoring_schema=1),
        _talk(
            "legacy-generation.md",
            60,
            generation_status="legacy_unbaselineable",
        ),
        {
            "filename": "unscored.md",
            "status": "processed",
        },
    ]

    snapshot = _build(
        adherence_baseline,
        talks,
        selected=["unused-selected.md", "active.md"],
    )
    reordered = _build(
        adherence_baseline,
        reversed(talks),
        selected=["active.md", "unused-selected.md"],
    )

    assert snapshot == reordered
    assert snapshot == {
        "schema_version": 1,
        "as_of": "2026-07-31T18:30:45+00:00",
        "scope": "global",
        "active_batch_excluded": True,
        "excluded_filenames": ["active.md", "unused-selected.md"],
        "eligible_statuses": ["processed", "processed_partial"],
        "pattern_scoring_generation_status": "current",
        "pattern_scoring_generation_reasons": [],
        "pattern_catalog_fingerprint": CATALOG,
        "pattern_scoring_schema_version": 2,
        "scored_talk_count": 3,
        "pattern_score_sum": 4,
        "average_pattern_score": 1.33,
    }


def test_builds_distinct_all_inclusive_current_cohort(adherence_baseline):
    snapshot = adherence_baseline.build_current_cohort_baseline(
        [_talk("first.md", 1), _talk("second.md", 2)],
        as_of=AS_OF,
        pattern_catalog_fingerprint=CATALOG,
        pattern_scoring_schema_version=2,
    )

    assert snapshot["active_batch_excluded"] is False
    assert snapshot["excluded_filenames"] == []
    assert snapshot["scored_talk_count"] == 2
    assert snapshot["pattern_score_sum"] == 3
    assert snapshot["average_pattern_score"] == 1.5


def test_full_cohort_shape_cannot_claim_exclusions(adherence_baseline):
    snapshot = _build(adherence_baseline, [], selected=["active.md"])
    snapshot["active_batch_excluded"] = False

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match=r"excluded_filenames must be \[\]",
    ):
        adherence_baseline.validate_adherence_baseline(snapshot)


@pytest.mark.parametrize("missing_lane", ["promoted", "nested"])
def test_current_generation_requires_both_score_lanes(
    adherence_baseline,
    missing_lane,
):
    talk = _talk("missing-score-lane.md", 2)
    if missing_lane == "promoted":
        talk.pop("pattern_score")
    else:
        talk["pattern_observations"].pop("pattern_score")

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match=f"has no {missing_lane}",
    ):
        _build(adherence_baseline, [talk])


def test_rejects_promoted_and_nested_score_divergence(adherence_baseline):
    talk = _talk("divergent.md", 5)
    talk["pattern_observations"]["pattern_score"] = 4

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="promoted pattern_score 5 diverges",
    ):
        _build(adherence_baseline, [talk])


@pytest.mark.parametrize("score", [True, False, 1.0, "1", None])
def test_rejects_non_integer_scores(adherence_baseline, score):
    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="pattern_score must be an integer",
    ):
        _build(adherence_baseline, [_talk("invalid-score.md", score)])


def test_excludes_selected_talk_before_inspecting_stale_score(adherence_baseline):
    selected = _talk("active.md", True)
    selected["pattern_observations"]["pattern_score"] = 999

    snapshot = _build(adherence_baseline, [selected], selected=["active.md"])

    assert snapshot["scored_talk_count"] == 0
    assert snapshot["pattern_score_sum"] == 0
    assert snapshot["average_pattern_score"] is None


@pytest.mark.parametrize(
    ("catalog", "scoring_schema", "message"),
    [
        ("not-a-sha", 2, "pattern_catalog_fingerprint must be a lowercase"),
        (CATALOG, True, "pattern_scoring_schema_version must be an integer"),
    ],
)
def test_rejects_malformed_persisted_generation_identity(
    adherence_baseline,
    catalog,
    scoring_schema,
    message,
):
    talk = _talk(
        "malformed-generation.md",
        1,
        catalog=catalog,
        scoring_schema=scoring_schema,
    )

    with pytest.raises(adherence_baseline.AdherenceBaselineError, match=message):
        _build(adherence_baseline, [talk])


@pytest.mark.parametrize("generation_status", [True, "future", ""])
def test_rejects_malformed_or_unknown_generation_status(
    adherence_baseline,
    generation_status,
):
    talk = _talk(
        "bad-generation-status.md",
        1,
        generation_status=generation_status,
    )

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="pattern_scoring_generation_status must be one of",
    ):
        _build(adherence_baseline, [talk])


def test_missing_and_legacy_generation_statuses_are_excluded(adherence_baseline):
    missing = _talk("missing-status.md", 100)
    missing.pop("pattern_scoring_generation_status")
    legacy = _talk(
        "legacy.md",
        100,
        generation_status="legacy_unbaselineable",
    )
    legacy.pop("pattern_scoring_generation_reasons")

    snapshot = _build(
        adherence_baseline,
        [missing, legacy],
    )

    assert snapshot["scored_talk_count"] == 0
    assert snapshot["pattern_score_sum"] == 0
    assert snapshot["average_pattern_score"] is None


@pytest.mark.parametrize(
    "generation_reasons",
    [["legacy catalog"], "none", False, {}],
)
def test_current_generation_requires_exact_empty_reasons(
    adherence_baseline,
    generation_reasons,
):
    talk = _talk(
        "bad-generation-reasons.md",
        1,
        generation_reasons=generation_reasons,
    )

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="pattern_scoring_generation_reasons must be exactly",
    ):
        _build(adherence_baseline, [talk])


def test_current_generation_requires_present_reasons(adherence_baseline):
    talk = _talk("missing-generation-reasons.md", 1)
    talk.pop("pattern_scoring_generation_reasons")

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="pattern_scoring_generation_reasons must be exactly",
    ):
        _build(adherence_baseline, [talk])


@pytest.mark.parametrize(
    "missing_field",
    ["pattern_catalog_fingerprint", "pattern_scoring_schema_version"],
)
def test_current_generation_requires_complete_generation_identity(
    adherence_baseline,
    missing_field,
):
    talk = _talk("incomplete-current.md", 1)
    talk.pop(missing_field)

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match=f"missing required identity fields .*{missing_field}",
    ):
        _build(adherence_baseline, [talk])


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ([1, 0, 0, 0, 0, 0, 0, 0], 0.12),
        ([1, 1, 1, 0, 0, 0, 0, 0], 0.38),
        ([-1, 0, 0, 0, 0, 0, 0, 0], -0.12),
    ],
)
def test_average_uses_two_place_decimal_round_half_even(
    adherence_baseline,
    scores,
    expected,
):
    talks = [_talk(f"talk-{index}.md", score) for index, score in enumerate(scores)]

    snapshot = _build(adherence_baseline, talks)

    assert snapshot["average_pattern_score"] == expected


def test_zero_population_uses_zero_sum_and_null_average(adherence_baseline):
    snapshot = _build(adherence_baseline, [])

    assert snapshot["scored_talk_count"] == 0
    assert snapshot["pattern_score_sum"] == 0
    assert snapshot["average_pattern_score"] is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", True, "schema_version must be an integer"),
        ("scope", "mode", "scope must be 'global'"),
        (
            "active_batch_excluded",
            1,
            "active_batch_excluded must be a boolean",
        ),
        (
            "eligible_statuses",
            ["processed_partial", "processed"],
            "eligible_statuses must be exactly",
        ),
        (
            "pattern_scoring_generation_status",
            "legacy_unbaselineable",
            "pattern_scoring_generation_status must be exactly 'current'",
        ),
        (
            "pattern_scoring_generation_reasons",
            ["not current"],
            "pattern_scoring_generation_reasons must be exactly",
        ),
        (
            "pattern_scoring_schema_version",
            True,
            "pattern_scoring_schema_version must be an integer",
        ),
        ("scored_talk_count", True, "scored_talk_count must be an integer"),
        ("pattern_score_sum", True, "pattern_score_sum must be an integer"),
    ],
)
def test_validation_rejects_noncanonical_contract_fields(
    adherence_baseline,
    field,
    value,
    message,
):
    snapshot = _build(adherence_baseline, [_talk("talk.md", 1)])
    snapshot[field] = value

    with pytest.raises(adherence_baseline.AdherenceBaselineError, match=message):
        adherence_baseline.validate_adherence_baseline(snapshot)


def test_validation_returns_a_detached_canonical_copy(adherence_baseline):
    snapshot = _build(adherence_baseline, [_talk("talk.md", 1)])

    validated = adherence_baseline.validate_adherence_baseline(snapshot)
    validated["excluded_filenames"].append("later.md")

    assert snapshot["excluded_filenames"] == []


@pytest.mark.parametrize("average", [math.nan, math.inf, -math.inf])
def test_validation_rejects_non_finite_average(adherence_baseline, average):
    snapshot = _build(adherence_baseline, [_talk("talk.md", 1)])
    snapshot["average_pattern_score"] = average

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="average_pattern_score must be finite",
    ):
        adherence_baseline.validate_adherence_baseline(snapshot)


def test_validation_recomputes_count_sum_average_invariant(adherence_baseline):
    snapshot = _build(adherence_baseline, [_talk("talk.md", 1)])
    snapshot["average_pattern_score"] = 1.01

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="does not match ROUND_HALF_EVEN count/sum result",
    ):
        adherence_baseline.validate_adherence_baseline(snapshot)


def test_validation_rejects_huge_integer_average_without_overflow(adherence_baseline):
    snapshot = _build(adherence_baseline, [_talk("talk.md", 1)])
    snapshot["average_pattern_score"] = 10**400

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="does not match ROUND_HALF_EVEN count/sum result",
    ):
        adherence_baseline.validate_adherence_baseline(snapshot)


def test_build_rejects_unrepresentable_huge_score_with_domain_error(
    adherence_baseline,
):
    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="cannot be represented as a finite two-place JSON number",
    ):
        _build(adherence_baseline, [_talk("huge.md", 10**400)])


def test_validation_rejects_unrepresentable_huge_sum_with_domain_error(
    adherence_baseline,
):
    snapshot = _build(adherence_baseline, [_talk("talk.md", 1)])
    snapshot["pattern_score_sum"] = 10**400
    snapshot["average_pattern_score"] = 10**400

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="cannot be represented as a finite two-place JSON number",
    ):
        adherence_baseline.validate_adherence_baseline(snapshot)


@pytest.mark.parametrize(
    ("score_sum", "average", "message"),
    [
        (1, None, "pattern_score_sum must be zero"),
        (0, 0.0, "average_pattern_score must be null"),
    ],
)
def test_validation_enforces_zero_population_invariants(
    adherence_baseline,
    score_sum,
    average,
    message,
):
    snapshot = _build(adherence_baseline, [])
    snapshot["pattern_score_sum"] = score_sum
    snapshot["average_pattern_score"] = average

    with pytest.raises(adherence_baseline.AdherenceBaselineError, match=message):
        adherence_baseline.validate_adherence_baseline(snapshot)


def test_validation_rejects_noncanonical_timestamp_and_filename_order(
    adherence_baseline,
):
    snapshot = _build(
        adherence_baseline,
        [_talk("talk.md", 1)],
        selected=["a.md", "z.md"],
    )
    noncanonical_time = deepcopy(snapshot)
    noncanonical_time["as_of"] = "2026-07-31T18:30:45Z"
    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="as_of must use canonical UTC",
    ):
        adherence_baseline.validate_adherence_baseline(noncanonical_time)

    noncanonical_names = deepcopy(snapshot)
    noncanonical_names["excluded_filenames"] = ["z.md", "a.md"]
    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="must be sorted",
    ):
        adherence_baseline.validate_adherence_baseline(noncanonical_names)


def test_validation_rejects_unknown_fields(adherence_baseline):
    snapshot = _build(adherence_baseline, [])
    snapshot["future_field"] = "unsupported"

    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="fields are noncanonical",
    ):
        adherence_baseline.validate_adherence_baseline(snapshot)


def test_constructor_rejects_duplicate_selected_filenames(adherence_baseline):
    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="selected_filenames contains duplicates",
    ):
        _build(adherence_baseline, [], selected=["same.md", "same.md"])


def test_constructor_rejects_duplicate_talk_filenames(adherence_baseline):
    with pytest.raises(
        adherence_baseline.AdherenceBaselineError,
        match="duplicate filename 'same.md'",
    ):
        _build(
            adherence_baseline,
            [_talk("same.md", 1), _talk("same.md", 1, status="pending")],
        )
