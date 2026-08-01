"""Synthetic regression tests for improvement-goal generation boundaries."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "vault-clarification"
    / "scripts"
    / "goal_generation_provenance.py"
)


@pytest.fixture
def goal_provenance():
    spec = importlib.util.spec_from_file_location("goal_generation_provenance", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _baseline(*, fingerprint: str = "a" * 64, scoring_schema: int = 3, count: int = 2):
    score_sum = count * 2
    return {
        "schema_version": 1,
        "as_of": "2026-07-31T12:00:00+00:00",
        "scope": "global",
        "active_batch_excluded": False,
        "excluded_filenames": [],
        "eligible_statuses": ["processed", "processed_partial"],
        "pattern_scoring_generation_status": "current",
        "pattern_scoring_generation_reasons": [],
        "pattern_catalog_fingerprint": fingerprint,
        "pattern_scoring_schema_version": scoring_schema,
        "scored_talk_count": count,
        "pattern_score_sum": score_sum,
        "average_pattern_score": 2.0 if count else None,
    }


def _goal(*, kind: str = "underuse", schema_version: int = 2):
    goal = {
        "id": "synthetic-goal",
        "schema_version": schema_version,
        "kind": kind,
    }
    if schema_version == 2:
        lanes = {
            "antipattern": "pattern_scoring",
            "underuse": "pattern_scoring",
            "pacing": "pacing",
            "other": "independent",
        }
        provenance = {"lane": lanes[kind]}
        if kind in {"antipattern", "underuse"}:
            provenance["pattern_baseline"] = _baseline()
        goal["baseline_provenance"] = provenance
    return goal


def test_matching_pattern_generation_is_comparable(goal_provenance):
    goal = _goal()
    before = copy.deepcopy(goal)

    result = goal_provenance.assess_goal_generation(goal, _baseline())

    assert result == {
        "goal_id": "synthetic-goal",
        "comparable": True,
        "decision": "comparable",
        "reason_codes": [],
    }
    assert goal == before


def test_catalog_and_scoring_mismatches_require_explicit_rebaseline(goal_provenance):
    current = _baseline(fingerprint="b" * 64, scoring_schema=4)

    result = goal_provenance.assess_goal_generation(_goal(), current)

    assert result["comparable"] is False
    assert result["decision"] == "needs_rebaseline"
    assert result["reason_codes"] == [
        "pattern_catalog_fingerprint_mismatch",
        "pattern_scoring_schema_version_mismatch",
    ]


def test_legacy_pattern_goal_is_unverifiable_not_silently_stamped(goal_provenance):
    result = goal_provenance.assess_goal_generation(
        _goal(schema_version=1), _baseline()
    )

    assert result == {
        "goal_id": "synthetic-goal",
        "comparable": False,
        "decision": "unverifiable",
        "reason_codes": ["legacy_pattern_goal_schema"],
    }


@pytest.mark.parametrize("kind", ["pacing", "other"])
@pytest.mark.parametrize("schema_version", [1, 2])
def test_nonpattern_goals_ignore_catalog_generation(
    goal_provenance, kind, schema_version
):
    result = goal_provenance.assess_goal_generation(
        _goal(kind=kind, schema_version=schema_version),
        _baseline(fingerprint="b" * 64, scoring_schema=99),
    )

    assert result["comparable"] is True
    assert result["decision"] == "comparable"
    assert result["reason_codes"] == []


def test_missing_current_pattern_baseline_is_unverifiable(goal_provenance):
    result = goal_provenance.assess_goal_generation(_goal(), None)

    assert result["comparable"] is False
    assert result["decision"] == "unverifiable"
    assert result["reason_codes"] == ["current_pattern_baseline_missing"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda goal: goal["baseline_provenance"].update({"lane": "pacing"}),
            "must be 'pattern_scoring'",
        ),
        (
            lambda goal: goal["baseline_provenance"]["pattern_baseline"].update(
                {"active_batch_excluded": True, "excluded_filenames": ["active.md"]}
            ),
            "active_batch_excluded must be false",
        ),
        (
            lambda goal: goal["baseline_provenance"]["pattern_baseline"].update(
                {
                    "scored_talk_count": 0,
                    "pattern_score_sum": 0,
                    "average_pattern_score": None,
                }
            ),
            "scored_talk_count must be greater than zero",
        ),
        (
            lambda goal: goal["baseline_provenance"].update({"future": True}),
            "unknown fields",
        ),
    ],
)
def test_malformed_v2_goal_provenance_fails_closed(
    goal_provenance, mutation, message
):
    goal = _goal()
    mutation(goal)

    with pytest.raises(goal_provenance.GoalGenerationProvenanceError, match=message):
        goal_provenance.assess_goal_generation(goal, _baseline())


@pytest.mark.parametrize("schema_version", [True, 0, 3])
def test_unknown_or_noninteger_goal_schema_fails_closed(
    goal_provenance, schema_version
):
    goal = _goal(schema_version=1)
    goal["schema_version"] = schema_version

    with pytest.raises(goal_provenance.GoalGenerationProvenanceError):
        goal_provenance.assess_goal_generation(goal, _baseline())


def test_nonpattern_v2_goal_cannot_smuggle_pattern_baseline(goal_provenance):
    goal = _goal(kind="pacing")
    goal["baseline_provenance"]["pattern_baseline"] = _baseline()

    with pytest.raises(
        goal_provenance.GoalGenerationProvenanceError,
        match="must not carry pattern_baseline",
    ):
        goal_provenance.assess_goal_generation(goal, _baseline())


def test_duplicate_ids_fail_the_complete_goal_list(goal_provenance):
    with pytest.raises(
        goal_provenance.GoalGenerationProvenanceError,
        match="duplicate goal ids",
    ):
        goal_provenance.assess_goals([_goal(), _goal()], _baseline())


def test_cli_emits_all_decisions_only_after_complete_validation():
    valid_payload = {
        "goals": [_goal(), _goal(kind="pacing", schema_version=1)],
        "current_pattern_baseline": _baseline(),
    }
    valid_payload["goals"][1]["id"] = "pacing-goal"
    valid = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(valid_payload),
        capture_output=True,
        text=True,
    )

    assert valid.returncode == 0, valid.stderr
    assert [
        item["decision"] for item in json.loads(valid.stdout)["assessments"]
    ] == ["comparable", "comparable"]

    invalid_payload = copy.deepcopy(valid_payload)
    invalid_payload["goals"][1]["schema_version"] = 99
    invalid = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(invalid_payload),
        capture_output=True,
        text=True,
    )

    assert invalid.returncode == 1
    assert invalid.stdout == ""
    assert "unknown schemas are read-only" in invalid.stderr
