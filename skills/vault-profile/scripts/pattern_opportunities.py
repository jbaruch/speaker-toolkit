"""Deterministic per-pattern opportunity aggregation for profile consumers.

Scoring-v5 persistence owns one sorted, exhaustive ``pattern_outcomes`` row for
every observable catalog entry on every current talk.  This module is the only
profile-side arithmetic owner for turning those per-talk outcomes into the
positive and negative occurrence lanes published by ``speaker-profile.json``
and Section 15.

No classification policy lives here.  In particular, zero detections never
means ``never_used`` and a frequency never means ``recurring`` without a
separately versioned, speaker-owned policy.
"""

from __future__ import annotations

import math
import pathlib
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, TypeGuard


_INGRESS_SCRIPTS = (
    pathlib.Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"
)
if str(_INGRESS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_INGRESS_SCRIPTS))

from return_validation import (  # noqa: E402
    load_catalog,
)


PATTERN_OUTCOMES = frozenset(
    {"detected", "undetected", "not_evaluable", "not_applicable"}
)
COMMON_OPPORTUNITY_FIELDS = frozenset(
    {
        "pattern_id",
        "detected_count",
        "evaluable_count",
        "unevaluable_count",
        "not_applicable_count",
        "eligible_cohort_count",
        "coverage",
        "out_of",
    }
)
PATTERN_USAGE_FIELDS = COMMON_OPPORTUNITY_FIELDS | frozenset(
    {"times_used", "usage_rate"}
)
ANTIPATTERN_FREQUENCY_FIELDS = COMMON_OPPORTUNITY_FIELDS | frozenset(
    {"times_detected", "frequency_rate"}
)


class PatternOpportunityError(ValueError):
    """Persisted outcomes cannot authorize deterministic opportunity rows."""


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _catalog_lanes(catalog: Any) -> tuple[list[str], list[str], dict[str, str]]:
    entries = getattr(catalog, "entries", None)
    if not isinstance(entries, Mapping):
        raise PatternOpportunityError("active catalog has no entries mapping")
    patterns: list[str] = []
    antipatterns: list[str] = []
    polarity: dict[str, str] = {}
    for pattern_id, entry in entries.items():
        if not isinstance(pattern_id, str) or not pattern_id:
            raise PatternOpportunityError("active catalog contains an invalid id")
        if getattr(entry, "observable", None) is not True:
            continue
        entry_type = getattr(entry, "entry_type", None)
        if entry_type == "pattern":
            patterns.append(pattern_id)
        elif entry_type == "antipattern":
            antipatterns.append(pattern_id)
        else:
            raise PatternOpportunityError(
                f"observable catalog entry {pattern_id!r} has invalid polarity "
                f"{entry_type!r}"
            )
        polarity[pattern_id] = entry_type
    return sorted(patterns), sorted(antipatterns), polarity


def _detection_ids(
    observations: Mapping[object, object],
    field: str,
    *,
    filename: str,
) -> set[str]:
    raw = observations.get(field)
    if not isinstance(raw, list):
        raise PatternOpportunityError(
            f"{filename}: pattern_observations.{field} must be an array"
        )
    result: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise PatternOpportunityError(
                f"{filename}: pattern_observations.{field}[{index}] must be an object"
            )
        pattern_id = item.get("pattern_id")
        if not isinstance(pattern_id, str) or not pattern_id:
            raise PatternOpportunityError(
                f"{filename}: pattern_observations.{field}[{index}].pattern_id "
                "must be a non-empty string"
            )
        if pattern_id in result:
            raise PatternOpportunityError(
                f"{filename}: pattern_observations.{field} duplicates {pattern_id!r}"
            )
        result.add(pattern_id)
    return result


def _canonical_talk_outcomes(
    talk: Mapping[object, object],
    *,
    expected_ids: list[str],
    polarity: Mapping[str, str],
) -> dict[str, str]:
    filename = talk.get("filename")
    if not isinstance(filename, str) or not filename:
        raise PatternOpportunityError("current cohort talk has no filename")
    observations = talk.get("pattern_observations")
    if not isinstance(observations, Mapping):
        raise PatternOpportunityError(
            f"{filename}: pattern_observations must be an object"
        )
    raw_outcomes = observations.get("pattern_outcomes")
    if not isinstance(raw_outcomes, list):
        raise PatternOpportunityError(
            f"{filename}: scoring-v5 pattern_observations.pattern_outcomes "
            "must be an array"
        )
    outcomes: dict[str, str] = {}
    observed_order: list[str] = []
    for index, item in enumerate(raw_outcomes):
        label = f"{filename}: pattern_outcomes[{index}]"
        if not isinstance(item, Mapping):
            raise PatternOpportunityError(f"{label} must be an object")
        if set(item) != {"pattern_id", "outcome"}:
            raise PatternOpportunityError(
                f"{label} must contain exactly pattern_id and outcome"
            )
        pattern_id = item.get("pattern_id")
        outcome = item.get("outcome")
        if not isinstance(pattern_id, str) or not pattern_id:
            raise PatternOpportunityError(
                f"{label}.pattern_id must be a non-empty string"
            )
        if pattern_id in outcomes:
            raise PatternOpportunityError(
                f"{filename}: pattern_outcomes duplicates {pattern_id!r}"
            )
        if not isinstance(outcome, str) or outcome not in PATTERN_OUTCOMES:
            raise PatternOpportunityError(
                f"{label}.outcome must be one of {sorted(PATTERN_OUTCOMES)}, "
                f"got {outcome!r}"
            )
        observed_order.append(pattern_id)
        outcomes[pattern_id] = str(outcome)
    observed_ids = set(outcomes)
    expected_set = set(expected_ids)
    if observed_order != expected_ids:
        missing = sorted(expected_set - observed_ids)
        unknown = sorted(observed_ids - expected_set)
        raise PatternOpportunityError(
            f"{filename}: pattern_outcomes must be sorted and exhaustive for the "
            f"observable catalog; missing={missing}, unknown={unknown}"
        )

    positive_detections = _detection_ids(
        observations, "patterns_detected", filename=filename
    )
    negative_detections = _detection_ids(
        observations, "antipatterns_detected", filename=filename
    )
    expected_positive = {
        pattern_id
        for pattern_id, outcome in outcomes.items()
        if outcome == "detected" and polarity[pattern_id] == "pattern"
    }
    expected_negative = {
        pattern_id
        for pattern_id, outcome in outcomes.items()
        if outcome == "detected" and polarity[pattern_id] == "antipattern"
    }
    if positive_detections != expected_positive:
        raise PatternOpportunityError(
            f"{filename}: patterns_detected does not match detected positive "
            "pattern_outcomes"
        )
    if negative_detections != expected_negative:
        raise PatternOpportunityError(
            f"{filename}: antipatterns_detected does not match detected negative "
            "pattern_outcomes"
        )
    return outcomes


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _opportunity_row(
    pattern_id: str,
    counts: Counter[str],
    *,
    eligible_cohort_count: int,
    polarity: str,
) -> dict[str, object]:
    detected_count = counts["detected"]
    evaluable_count = detected_count + counts["undetected"]
    common: dict[str, object] = {
        "pattern_id": pattern_id,
        "detected_count": detected_count,
        "evaluable_count": evaluable_count,
        "unevaluable_count": counts["not_evaluable"],
        "not_applicable_count": counts["not_applicable"],
        "eligible_cohort_count": eligible_cohort_count,
        "coverage": _rate(evaluable_count, eligible_cohort_count),
        "out_of": evaluable_count,
    }
    if polarity == "pattern":
        common["times_used"] = detected_count
        common["usage_rate"] = _rate(detected_count, evaluable_count)
    else:
        common["times_detected"] = detected_count
        common["frequency_rate"] = _rate(detected_count, evaluable_count)
    return common


def build_pattern_opportunity_rows(
    talks: object,
    *,
    catalog: Any | None = None,
) -> dict[str, object]:
    """Aggregate exact opportunity rows from a fresh current scoring-v5 cohort."""
    if isinstance(talks, (str, bytes, Mapping)) or not isinstance(talks, Sequence):
        raise PatternOpportunityError("current pattern cohort must be an array")
    resolved_catalog = catalog or load_catalog()
    pattern_ids, antipattern_ids, polarity = _catalog_lanes(resolved_catalog)
    expected_ids = sorted(pattern_ids + antipattern_ids)
    counts = {pattern_id: Counter() for pattern_id in expected_ids}
    seen_filenames: set[str] = set()
    for index, talk in enumerate(talks):
        if not isinstance(talk, Mapping):
            raise PatternOpportunityError(
                f"current pattern cohort talk {index} must be an object"
            )
        filename = talk.get("filename")
        if not isinstance(filename, str) or not filename:
            raise PatternOpportunityError(
                f"current pattern cohort talk {index} has no filename"
            )
        if filename in seen_filenames:
            raise PatternOpportunityError(
                f"current pattern cohort duplicates filename {filename!r}"
            )
        seen_filenames.add(filename)
        outcomes = _canonical_talk_outcomes(
            talk, expected_ids=expected_ids, polarity=polarity
        )
        for pattern_id, outcome in outcomes.items():
            counts[pattern_id][outcome] += 1

    eligible_count = len(talks)
    return {
        "eligible_cohort_count": eligible_count,
        "pattern_usage": [
            _opportunity_row(
                pattern_id,
                counts[pattern_id],
                eligible_cohort_count=eligible_count,
                polarity="pattern",
            )
            for pattern_id in pattern_ids
        ],
        "antipattern_frequency": [
            _opportunity_row(
                pattern_id,
                counts[pattern_id],
                eligible_cohort_count=eligible_count,
                polarity="antipattern",
            )
            for pattern_id in antipattern_ids
        ],
    }


def _validate_rate(
    value: object,
    expected: float | None,
    *,
    path: str,
) -> list[str]:
    if expected is None:
        return [] if value is None else [f"{path} must be null, got {value!r}"]
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value != expected
    ):
        return [f"{path} must equal the canonical ratio {expected!r}, got {value!r}"]
    return []


def _validate_lane(
    value: object,
    *,
    lane: str,
    expected_ids: list[str],
    eligible_cohort_count: int,
) -> list[str]:
    if not isinstance(value, list):
        return [f"pattern_profile.{lane} must be an array"]
    fields = (
        PATTERN_USAGE_FIELDS
        if lane == "pattern_usage"
        else ANTIPATTERN_FREQUENCY_FIELDS
    )
    numerator_alias = "times_used" if lane == "pattern_usage" else "times_detected"
    rate_field = "usage_rate" if lane == "pattern_usage" else "frequency_rate"
    errors: list[str] = []
    observed_ids: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(value):
        path = f"pattern_profile.{lane}[{index}]"
        if not isinstance(row, Mapping):
            errors.append(f"{path} must be an object")
            continue
        missing = sorted(fields - set(row))
        unknown = sorted(set(row) - fields, key=str)
        if missing or unknown:
            errors.append(
                f"{path} fields are noncanonical; missing={missing}, "
                f"unknown={[str(item) for item in unknown]}"
            )
        pattern_id = row.get("pattern_id")
        if not isinstance(pattern_id, str) or not pattern_id:
            errors.append(f"{path}.pattern_id must be a non-empty string")
        else:
            observed_ids.append(pattern_id)
            if pattern_id in seen:
                errors.append(f"{path}.pattern_id duplicates {pattern_id!r}")
            seen.add(pattern_id)

        count_fields = (
            "detected_count",
            "evaluable_count",
            "unevaluable_count",
            "not_applicable_count",
            "eligible_cohort_count",
            "out_of",
            numerator_alias,
        )
        counts: dict[str, int] = {}
        for field in count_fields:
            raw = row.get(field)
            if not _is_integer(raw) or raw < 0:
                errors.append(f"{path}.{field} must be a non-negative integer")
            else:
                counts[field] = raw
        if len(counts) != len(count_fields):
            continue
        if counts["eligible_cohort_count"] != eligible_cohort_count:
            errors.append(
                f"{path}.eligible_cohort_count must equal the current pattern "
                f"cohort count {eligible_cohort_count}, got "
                f"{counts['eligible_cohort_count']}"
            )
        if counts["detected_count"] > counts["evaluable_count"]:
            errors.append(f"{path}.detected_count cannot exceed evaluable_count")
        accounted = (
            counts["evaluable_count"]
            + counts["unevaluable_count"]
            + counts["not_applicable_count"]
        )
        if accounted != eligible_cohort_count:
            errors.append(
                f"{path} outcome counts must satisfy evaluable_count + "
                "unevaluable_count + not_applicable_count = "
                f"eligible_cohort_count {eligible_cohort_count}, got {accounted}"
            )
        if counts["out_of"] != counts["evaluable_count"]:
            errors.append(
                f"{path}.out_of must equal evaluable_count "
                f"{counts['evaluable_count']}, got {counts['out_of']}"
            )
        if counts[numerator_alias] != counts["detected_count"]:
            errors.append(
                f"{path}.{numerator_alias} must equal detected_count "
                f"{counts['detected_count']}, got {counts[numerator_alias]}"
            )
        errors.extend(
            _validate_rate(
                row.get("coverage"),
                _rate(counts["evaluable_count"], eligible_cohort_count),
                path=f"{path}.coverage",
            )
        )
        errors.extend(
            _validate_rate(
                row.get(rate_field),
                _rate(counts["detected_count"], counts["evaluable_count"]),
                path=f"{path}.{rate_field}",
            )
        )

    expected_set = set(expected_ids)
    observed_set = set(observed_ids)
    if observed_ids != expected_ids:
        catalog_kind = "pattern" if lane == "pattern_usage" else "antipattern"
        errors.append(
            f"pattern_profile.{lane} must contain one sorted row for every "
            f"observable catalog {catalog_kind}; "
            f"missing={sorted(expected_set - observed_set)}, "
            f"unknown_or_wrong_polarity={sorted(observed_set - expected_set)}"
        )
    return errors


def validate_pattern_opportunity_rows(
    pattern_usage: object,
    antipattern_frequency: object,
    *,
    eligible_cohort_count: int,
    catalog: Any | None = None,
) -> list[str]:
    """Validate exact catalog-aware row completeness and arithmetic."""
    if not _is_integer(eligible_cohort_count) or eligible_cohort_count < 0:
        return ["eligible_cohort_count must be a non-negative integer"]
    resolved_catalog = catalog or load_catalog()
    pattern_ids, antipattern_ids, _ = _catalog_lanes(resolved_catalog)
    return [
        *_validate_lane(
            pattern_usage,
            lane="pattern_usage",
            expected_ids=pattern_ids,
            eligible_cohort_count=eligible_cohort_count,
        ),
        *_validate_lane(
            antipattern_frequency,
            lane="antipattern_frequency",
            expected_ids=antipattern_ids,
            eligible_cohort_count=eligible_cohort_count,
        ),
    ]
