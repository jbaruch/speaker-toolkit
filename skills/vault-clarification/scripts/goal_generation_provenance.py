#!/usr/bin/env python3
"""Gate improvement-goal verification by immutable baseline generation.

Pattern coaching is meaningful only inside one catalog/scoring generation.  This
module owns the mechanical comparability decision; it deliberately does not
interpret a goal metric or decide whether the speaker improved.

Library contract
----------------
``assess_goal_generation(goal, current_pattern_baseline)`` returns a detached
JSON-ready decision with ``comparable``, ``decision``, and stable
``reason_codes``.  Malformed records raise ``GoalGenerationProvenanceError``.

CLI contract
------------
Stdin::

    {
      "goals": [...],
      "current_pattern_baseline": {...} | null
    }

Stdout::

    {"schema_version": 1, "assessments": [...]}

The complete input is validated before stdout is written.  Exit status is 1 and
the diagnostic goes to stderr on malformed JSON or contract violations.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections.abc import Mapping
from typing import cast


INGRESS_SCRIPTS = (
    pathlib.Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"
)
if str(INGRESS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(INGRESS_SCRIPTS))

from adherence_baseline import (  # noqa: E402
    AdherenceBaselineError,
    validate_adherence_baseline,
)


GOAL_SCHEMA_VERSION = 2
ASSESSMENT_SCHEMA_VERSION = 1

PATTERN_LANE = "pattern_scoring"
PACING_LANE = "pacing"
INDEPENDENT_LANE = "independent"

PATTERN_GOAL_KINDS = frozenset({"antipattern", "underuse"})
KNOWN_GOAL_KINDS = PATTERN_GOAL_KINDS | {"pacing", "other"}

COMPARABLE = "comparable"
NEEDS_REBASELINE = "needs_rebaseline"
UNVERIFIABLE = "unverifiable"

LEGACY_PATTERN_GOAL_SCHEMA = "legacy_pattern_goal_schema"
CURRENT_PATTERN_BASELINE_MISSING = "current_pattern_baseline_missing"
CATALOG_FINGERPRINT_MISMATCH = "pattern_catalog_fingerprint_mismatch"
SCORING_SCHEMA_MISMATCH = "pattern_scoring_schema_version_mismatch"


class GoalGenerationProvenanceError(ValueError):
    """A goal or one of its generation snapshots violates the owner contract."""


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GoalGenerationProvenanceError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _require_nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GoalGenerationProvenanceError(
            f"{label} must be a non-empty string without edge whitespace"
        )
    return value


def _require_schema_version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GoalGenerationProvenanceError(
            f"goal.schema_version must be an integer, got {value!r}"
        )
    if value not in (1, GOAL_SCHEMA_VERSION):
        raise GoalGenerationProvenanceError(
            "goal.schema_version must be one of [1, 2]; unknown schemas are "
            f"read-only, got {value}"
        )
    return value


def _goal_kind(goal: Mapping[str, object]) -> str:
    kind = _require_nonempty_string(goal.get("kind"), "goal.kind")
    if kind not in KNOWN_GOAL_KINDS:
        raise GoalGenerationProvenanceError(
            f"goal.kind must be one of {sorted(KNOWN_GOAL_KINDS)!r}, got {kind!r}"
        )
    return kind


def _expected_lane(kind: str) -> str:
    if kind in PATTERN_GOAL_KINDS:
        return PATTERN_LANE
    if kind == "pacing":
        return PACING_LANE
    return INDEPENDENT_LANE


def _validate_full_pattern_baseline(value: object, label: str) -> dict[str, object]:
    try:
        baseline = validate_adherence_baseline(value)
    except AdherenceBaselineError as exc:
        raise GoalGenerationProvenanceError(f"{label} is invalid: {exc}") from exc
    if baseline["active_batch_excluded"] is not False:
        raise GoalGenerationProvenanceError(
            f"{label}.active_batch_excluded must be false for a post-batch goal "
            "baseline"
        )
    if baseline["excluded_filenames"] != []:
        raise GoalGenerationProvenanceError(
            f"{label}.excluded_filenames must be [] for a full-cohort goal baseline"
        )
    return baseline


def _decision(
    goal_id: str,
    *,
    comparable: bool,
    decision: str,
    reason_codes: list[str],
) -> dict[str, object]:
    return {
        "goal_id": goal_id,
        "comparable": comparable,
        "decision": decision,
        "reason_codes": list(reason_codes),
    }


def assess_goal_generation(
    goal: object,
    current_pattern_baseline: object,
) -> dict[str, object]:
    """Return the generation-comparability decision for one improvement goal.

    Schema-v1 pattern goals have no fixed generation and are intentionally
    unverifiable.  Their pacing/independent siblings remain usable because a
    catalog release does not define those measurements.  Schema-v2 pattern goals
    embed the exact full-cohort snapshot that existed when the speaker accepted
    the goal; only fingerprint and scoring-schema equality are required for a
    later measurement to be comparable.
    """
    record = _require_mapping(goal, "goal")
    goal_id = _require_nonempty_string(record.get("id"), "goal.id")
    schema_version = _require_schema_version(record.get("schema_version"))
    kind = _goal_kind(record)

    if schema_version == 1:
        if kind in PATTERN_GOAL_KINDS:
            return _decision(
                goal_id,
                comparable=False,
                decision=UNVERIFIABLE,
                reason_codes=[LEGACY_PATTERN_GOAL_SCHEMA],
            )
        return _decision(
            goal_id,
            comparable=True,
            decision=COMPARABLE,
            reason_codes=[],
        )

    provenance = _require_mapping(
        record.get("baseline_provenance"), "goal.baseline_provenance"
    )
    allowed_fields = {"lane", "pattern_baseline"}
    unknown_fields = sorted(set(provenance) - allowed_fields)
    if unknown_fields:
        raise GoalGenerationProvenanceError(
            "goal.baseline_provenance has unknown fields: "
            f"{unknown_fields!r}"
        )
    lane = _require_nonempty_string(
        provenance.get("lane"), "goal.baseline_provenance.lane"
    )
    expected_lane = _expected_lane(kind)
    if lane != expected_lane:
        raise GoalGenerationProvenanceError(
            f"goal.baseline_provenance.lane must be {expected_lane!r} for "
            f"kind {kind!r}, got {lane!r}"
        )

    if lane != PATTERN_LANE:
        if "pattern_baseline" in provenance:
            raise GoalGenerationProvenanceError(
                "non-pattern goal provenance must not carry pattern_baseline"
            )
        return _decision(
            goal_id,
            comparable=True,
            decision=COMPARABLE,
            reason_codes=[],
        )

    fixed = _validate_full_pattern_baseline(
        provenance.get("pattern_baseline"),
        "goal.baseline_provenance.pattern_baseline",
    )
    if fixed["scored_talk_count"] == 0:
        raise GoalGenerationProvenanceError(
            "goal.baseline_provenance.pattern_baseline.scored_talk_count must "
            "be greater than zero when a pattern goal is set"
        )

    if current_pattern_baseline is None:
        return _decision(
            goal_id,
            comparable=False,
            decision=UNVERIFIABLE,
            reason_codes=[CURRENT_PATTERN_BASELINE_MISSING],
        )
    current = _validate_full_pattern_baseline(
        current_pattern_baseline, "current_pattern_baseline"
    )

    reason_codes = []
    if (
        fixed["pattern_catalog_fingerprint"]
        != current["pattern_catalog_fingerprint"]
    ):
        reason_codes.append(CATALOG_FINGERPRINT_MISMATCH)
    if (
        fixed["pattern_scoring_schema_version"]
        != current["pattern_scoring_schema_version"]
    ):
        reason_codes.append(SCORING_SCHEMA_MISMATCH)
    if reason_codes:
        return _decision(
            goal_id,
            comparable=False,
            decision=NEEDS_REBASELINE,
            reason_codes=reason_codes,
        )
    return _decision(
        goal_id,
        comparable=True,
        decision=COMPARABLE,
        reason_codes=[],
    )


def assess_goals(
    goals: object,
    current_pattern_baseline: object,
) -> list[dict[str, object]]:
    """Validate and assess a complete goal list without partial output."""
    if not isinstance(goals, list):
        raise GoalGenerationProvenanceError("goals must be an array")
    assessments = [
        assess_goal_generation(goal, current_pattern_baseline) for goal in goals
    ]
    ids = [assessment["goal_id"] for assessment in assessments]
    if len(ids) != len(set(ids)):
        raise GoalGenerationProvenanceError("goals contains duplicate goal ids")
    return assessments


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        root = _require_mapping(payload, "stdin")
        unknown_fields = sorted(
            set(root) - {"goals", "current_pattern_baseline"}
        )
        if unknown_fields:
            raise GoalGenerationProvenanceError(
                f"stdin has unknown fields: {unknown_fields!r}"
            )
        assessments = assess_goals(
            root.get("goals"), root.get("current_pattern_baseline")
        )
    except (GoalGenerationProvenanceError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "schema_version": ASSESSMENT_SCHEMA_VERSION,
                "assessments": assessments,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
