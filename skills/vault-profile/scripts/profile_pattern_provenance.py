"""Strict, reusable availability contract for profile pattern history.

Owner and consumer skills share this module so a profile either exposes one
auditable current-generation pattern cohort everywhere or exposes no historical
pattern guidance anywhere.  The module performs no writes and does not encode
consumer-specific fallback policy.
"""

from __future__ import annotations

import math
import pathlib
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeGuard


_INGRESS_SCRIPTS = (
    pathlib.Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"
)
if str(_INGRESS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_INGRESS_SCRIPTS))

from adherence_baseline import (  # noqa: E402
    AdherenceBaselineError,
    validate_adherence_baseline,
)
from return_validation import (  # noqa: E402
    PATTERN_SCORING_SCHEMA_VERSION,
    ReturnValidationError,
    load_catalog,
)


REASON_INVALID_CONTRACT = "invalid_pattern_profile_contract"
REASON_ACTIVE_CATALOG_UNAVAILABLE = "active_pattern_catalog_unavailable"
REASON_CATALOG_FINGERPRINT_MISMATCH = "pattern_catalog_fingerprint_mismatch"
REASON_SCORING_SCHEMA_MISMATCH = "pattern_scoring_schema_mismatch"
REASON_EMPTY_CURRENT_COHORT = "empty_current_pattern_cohort"

_REQUIRED_PATTERN_PROFILE_FIELDS = frozenset(
    {
        "pattern_baseline",
        "baseline_talk_filenames",
        "talks_scored",
        "average_pattern_score",
        "score_trend",
        "pattern_breadth",
        "underused_patterns",
        "score_drivers",
        "by_mode",
        "strengths",
        "strengths_note",
        "note",
        "pattern_usage",
        "antipattern_frequency",
        "never_used_patterns",
        "signature_combinations",
        "mastery_levels",
    }
)
_REQUIRED_PATTERN_BREADTH_FIELDS = frozenset(
    {"avg_distinct_patterns_per_talk", "trend", "note"}
)
_REQUIRED_SCORE_DRIVER_FIELDS = frozenset(
    {"direction", "antipattern_drivers", "pattern_drivers", "note"}
)
_ARRAY_PATTERN_PROFILE_FIELDS = (
    "underused_patterns",
    "by_mode",
    "strengths",
    "pattern_usage",
    "antipattern_frequency",
    "never_used_patterns",
    "signature_combinations",
)
_MASTERY_TIERS = (
    "signature",
    "regular",
    "occasional",
    "rare",
    "never_tried",
)


@dataclass(frozen=True)
class PatternProfileAssessment:
    """Availability and diagnostics for one profile's pattern history."""

    current_contract: bool
    catalog_fields_available: bool
    scored_talk_count: int | None
    reason_codes: tuple[str, ...]
    errors: tuple[str, ...]


def active_pattern_generation_identity() -> tuple[str, int]:
    """Return the exact bundled catalog fingerprint and scoring schema."""
    return load_catalog().fingerprint, PATTERN_SCORING_SCHEMA_VERSION


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _append_reason(reason_codes: list[str], reason_code: str) -> None:
    if reason_code not in reason_codes:
        reason_codes.append(reason_code)


def _canonical_cohort_filenames(
    value: object,
) -> tuple[list[str] | None, list[str]]:
    if not isinstance(value, list):
        return None, ["pattern_profile.baseline_talk_filenames must be an array"]

    errors: list[str] = []
    filenames: list[str] = []
    for index, filename in enumerate(value):
        if (
            not isinstance(filename, str)
            or not filename
            or filename != filename.strip()
        ):
            errors.append(
                "pattern_profile.baseline_talk_filenames"
                f"[{index}] must be a non-empty string without edge whitespace"
            )
            continue
        filenames.append(filename)

    if len(filenames) != len(set(filenames)):
        errors.append(
            "pattern_profile.baseline_talk_filenames must not contain duplicates"
        )
    if filenames != sorted(filenames):
        errors.append(
            "pattern_profile.baseline_talk_filenames must be sorted in canonical "
            "filename order"
        )
    return filenames, errors


def _validate_count_denominators(
    value: object,
    *,
    expected_count: int,
    path: str,
) -> list[str]:
    errors: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "out_of":
                if not _is_integer(child) or child != expected_count:
                    errors.append(
                        f"{child_path} must equal the current pattern cohort count "
                        f"{expected_count}, got {child!r}"
                    )
                continue
            errors.extend(
                _validate_count_denominators(
                    child,
                    expected_count=expected_count,
                    path=child_path,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(
                _validate_count_denominators(
                    child,
                    expected_count=expected_count,
                    path=f"{path}[{index}]",
                )
            )
    return errors


def _validate_count_bounds(
    value: object,
    *,
    cohort_count: int,
    path: str,
) -> list[str]:
    errors: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in {"times_used", "times_detected", "frequency"}:
                if (
                    not _is_integer(child)
                    or child < 0
                    or child > cohort_count
                ):
                    errors.append(
                        f"{child_path} must be an integer from 0 through the "
                        f"current pattern cohort count {cohort_count}, got "
                        f"{child!r}"
                    )
                continue
            if key in {"usage_rate", "frequency_rate"}:
                if (
                    isinstance(child, bool)
                    or not isinstance(child, (int, float))
                    or not math.isfinite(child)
                    or child < 0
                    or child > 1
                ):
                    errors.append(
                        f"{child_path} must be a finite number from 0 through 1, "
                        f"got {child!r}"
                    )
                continue
            errors.extend(
                _validate_count_bounds(
                    child,
                    cohort_count=cohort_count,
                    path=child_path,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(
                _validate_count_bounds(
                    child,
                    cohort_count=cohort_count,
                    path=f"{path}[{index}]",
                )
            )
    return errors


def _validate_mode_counts(value: object, cohort_count: int) -> list[str]:
    if not isinstance(value, list):
        return ["pattern_profile.by_mode must be an array"]
    errors: list[str] = []
    for index, mode in enumerate(value):
        if not isinstance(mode, Mapping):
            errors.append(f"pattern_profile.by_mode[{index}] must be an object")
            continue
        count = mode.get("talks_in_mode")
        if not _is_integer(count) or count < 0 or count > cohort_count:
            errors.append(
                f"pattern_profile.by_mode[{index}].talks_in_mode must be an "
                f"integer from 0 through the current pattern cohort count "
                f"{cohort_count}, got {count!r}"
            )
    return errors


def _validate_empty_pattern_cohort(
    pattern_profile: Mapping[str, object],
) -> list[str]:
    errors: list[str] = []
    if pattern_profile.get("score_trend") != "unavailable":
        errors.append(
            "pattern_profile.score_trend must be 'unavailable' when the current "
            "pattern cohort is empty"
        )

    breadth = pattern_profile.get("pattern_breadth")
    if isinstance(breadth, Mapping):
        if breadth.get("avg_distinct_patterns_per_talk") is not None:
            errors.append(
                "pattern_profile.pattern_breadth.avg_distinct_patterns_per_talk "
                "must be null when the current pattern cohort is empty"
            )
        if breadth.get("trend") != "unavailable":
            errors.append(
                "pattern_profile.pattern_breadth.trend must be 'unavailable' when "
                "the current pattern cohort is empty"
            )

    drivers = pattern_profile.get("score_drivers")
    if isinstance(drivers, Mapping):
        if drivers.get("direction") != "unavailable":
            errors.append(
                "pattern_profile.score_drivers.direction must be 'unavailable' "
                "when the current pattern cohort is empty"
            )
        for field in ("antipattern_drivers", "pattern_drivers"):
            if drivers.get(field) != []:
                errors.append(
                    f"pattern_profile.score_drivers.{field} must be [] when the "
                    "current pattern cohort is empty"
                )

    for field in _ARRAY_PATTERN_PROFILE_FIELDS:
        if pattern_profile.get(field) != []:
            errors.append(
                f"pattern_profile.{field} must be [] when the current pattern "
                "cohort is empty"
            )

    mastery = pattern_profile.get("mastery_levels")
    if isinstance(mastery, Mapping):
        for tier in _MASTERY_TIERS:
            if mastery.get(tier) != []:
                errors.append(
                    f"pattern_profile.mastery_levels.{tier} must be [] when the "
                    "current pattern cohort is empty"
                )
    return errors


def assess_pattern_profile(pattern_profile: object) -> PatternProfileAssessment:
    """Assess strict current-generation pattern history without applying fallback.

    A valid zero-talk snapshot is a current contract but has unavailable catalog
    history. Any malformed or stale identity fails closed. Consumers may still
    use unrelated profile fields; this assessment speaks only for catalog-derived
    pattern history.
    """
    errors: list[str] = []
    reason_codes: list[str] = []
    if not isinstance(pattern_profile, Mapping):
        return PatternProfileAssessment(
            current_contract=False,
            catalog_fields_available=False,
            scored_talk_count=None,
            reason_codes=(REASON_INVALID_CONTRACT,),
            errors=("pattern_profile must be an object",),
        )

    missing_fields = sorted(_REQUIRED_PATTERN_PROFILE_FIELDS - set(pattern_profile))
    if missing_fields:
        errors.append(
            "pattern_profile is missing required schema-v3 fields: "
            f"{', '.join(missing_fields)}"
        )
    unknown_fields = sorted(
        set(pattern_profile) - _REQUIRED_PATTERN_PROFILE_FIELDS,
        key=str,
    )
    if unknown_fields:
        errors.append(
            "pattern_profile has unknown schema-v3 fields: "
            f"{', '.join(str(field) for field in unknown_fields)}"
        )

    for field in _ARRAY_PATTERN_PROFILE_FIELDS:
        if field in pattern_profile and not isinstance(pattern_profile[field], list):
            errors.append(f"pattern_profile.{field} must be an array")

    for field in ("strengths_note", "note"):
        if field in pattern_profile and not isinstance(pattern_profile[field], str):
            errors.append(f"pattern_profile.{field} must be a string")

    breadth = pattern_profile.get("pattern_breadth")
    if isinstance(breadth, Mapping):
        missing_breadth = sorted(_REQUIRED_PATTERN_BREADTH_FIELDS - set(breadth))
        if missing_breadth:
            errors.append(
                "pattern_profile.pattern_breadth is missing required fields: "
                f"{', '.join(missing_breadth)}"
            )
        unknown_breadth = sorted(
            set(breadth) - _REQUIRED_PATTERN_BREADTH_FIELDS,
            key=str,
        )
        if unknown_breadth:
            errors.append(
                "pattern_profile.pattern_breadth has unknown fields: "
                f"{', '.join(str(field) for field in unknown_breadth)}"
            )
        if "note" in breadth and not isinstance(breadth["note"], str):
            errors.append("pattern_profile.pattern_breadth.note must be a string")
    else:
        errors.append("pattern_profile.pattern_breadth must be an object")

    drivers = pattern_profile.get("score_drivers")
    if isinstance(drivers, Mapping):
        missing_drivers = sorted(_REQUIRED_SCORE_DRIVER_FIELDS - set(drivers))
        if missing_drivers:
            errors.append(
                "pattern_profile.score_drivers is missing required fields: "
                f"{', '.join(missing_drivers)}"
            )
        unknown_drivers = sorted(
            set(drivers) - _REQUIRED_SCORE_DRIVER_FIELDS,
            key=str,
        )
        if unknown_drivers:
            errors.append(
                "pattern_profile.score_drivers has unknown fields: "
                f"{', '.join(str(field) for field in unknown_drivers)}"
            )
        for field in ("antipattern_drivers", "pattern_drivers"):
            if field in drivers and not isinstance(drivers[field], list):
                errors.append(f"pattern_profile.score_drivers.{field} must be an array")
        if "note" in drivers and not isinstance(drivers["note"], str):
            errors.append("pattern_profile.score_drivers.note must be a string")
    else:
        errors.append("pattern_profile.score_drivers must be an object")

    mastery = pattern_profile.get("mastery_levels")
    if isinstance(mastery, Mapping):
        missing_tiers = sorted(set(_MASTERY_TIERS) - set(mastery))
        if missing_tiers:
            errors.append(
                "pattern_profile.mastery_levels is missing required tiers: "
                f"{', '.join(missing_tiers)}"
            )
        unknown_tiers = sorted(
            set(mastery) - set(_MASTERY_TIERS),
            key=str,
        )
        if unknown_tiers:
            errors.append(
                "pattern_profile.mastery_levels has unknown tiers: "
                f"{', '.join(str(field) for field in unknown_tiers)}"
            )
        for tier in _MASTERY_TIERS:
            if tier in mastery and not isinstance(mastery[tier], list):
                errors.append(f"pattern_profile.mastery_levels.{tier} must be an array")
    else:
        errors.append("pattern_profile.mastery_levels must be an object")

    try:
        baseline = validate_adherence_baseline(
            pattern_profile.get("pattern_baseline")
        )
    except AdherenceBaselineError as exc:
        errors.append(f"pattern_profile.pattern_baseline is invalid: {exc}")
        _append_reason(reason_codes, REASON_INVALID_CONTRACT)
        return PatternProfileAssessment(
            current_contract=False,
            catalog_fields_available=False,
            scored_talk_count=None,
            reason_codes=tuple(reason_codes),
            errors=tuple(errors),
        )

    cohort_count = baseline["scored_talk_count"]
    assert isinstance(cohort_count, int)  # canonical baseline postcondition

    if baseline["active_batch_excluded"] is not False:
        errors.append(
            "pattern_profile.pattern_baseline must be a full-cohort snapshot with "
            "active_batch_excluded=false"
        )
    if baseline["excluded_filenames"] != []:
        errors.append(
            "pattern_profile.pattern_baseline.excluded_filenames must be []"
        )

    active_scoring_schema = PATTERN_SCORING_SCHEMA_VERSION
    try:
        active_fingerprint, _ = active_pattern_generation_identity()
    except ReturnValidationError as exc:
        errors.append(
            "could not resolve the active Presentation Pattern catalog; repair the "
            f"installed catalog before using pattern history: {exc}"
        )
        _append_reason(reason_codes, REASON_ACTIVE_CATALOG_UNAVAILABLE)
        active_fingerprint = None

    if (
        active_fingerprint is not None
        and baseline["pattern_catalog_fingerprint"] != active_fingerprint
    ):
        errors.append(
            "pattern_profile.pattern_baseline.pattern_catalog_fingerprint does not "
            "match the active catalog; regenerate the entire pattern profile as a "
            "new scoring generation"
        )
        _append_reason(reason_codes, REASON_CATALOG_FINGERPRINT_MISMATCH)
    if (
        baseline["pattern_scoring_schema_version"] != active_scoring_schema
    ):
        errors.append(
            "pattern_profile.pattern_baseline.pattern_scoring_schema_version is "
            f"{baseline['pattern_scoring_schema_version']!r}; expected active schema "
            f"{active_scoring_schema}"
        )
        _append_reason(reason_codes, REASON_SCORING_SCHEMA_MISMATCH)

    filenames, filename_errors = _canonical_cohort_filenames(
        pattern_profile.get("baseline_talk_filenames")
    )
    errors.extend(filename_errors)
    if filenames is not None and len(filenames) != cohort_count:
        errors.append(
            "pattern_profile.baseline_talk_filenames length must equal "
            f"pattern_baseline.scored_talk_count {cohort_count}, got "
            f"{len(filenames)}"
        )

    talks_scored = pattern_profile.get("talks_scored")
    if not _is_integer(talks_scored) or talks_scored != cohort_count:
        errors.append(
            "pattern_profile.talks_scored must equal "
            f"pattern_baseline.scored_talk_count {cohort_count}, got "
            f"{talks_scored!r}"
        )

    profile_average = pattern_profile.get("average_pattern_score")
    baseline_average = baseline["average_pattern_score"]
    if cohort_count == 0:
        average_is_valid = profile_average is None
    else:
        average_is_valid = (
            not isinstance(profile_average, bool)
            and isinstance(profile_average, (int, float))
            and math.isfinite(profile_average)
            and profile_average == baseline_average
        )
    if not average_is_valid:
        errors.append(
            "pattern_profile.average_pattern_score must equal the canonical "
            f"pattern baseline average {baseline_average!r}, got "
            f"{profile_average!r}"
        )

    score_trend = pattern_profile.get("score_trend")
    breadth_trend = breadth.get("trend") if isinstance(breadth, Mapping) else None
    breadth_average = (
        breadth.get("avg_distinct_patterns_per_talk")
        if isinstance(breadth, Mapping)
        else None
    )
    driver_direction = (
        drivers.get("direction") if isinstance(drivers, Mapping) else None
    )
    if cohort_count > 0:
        if score_trend not in {"improving", "stable", "declining"}:
            errors.append(
                "pattern_profile.score_trend must be improving, stable, or "
                "declining when the current pattern cohort is non-empty"
            )
        if breadth_trend not in {"widening", "stable", "narrowing"}:
            errors.append(
                "pattern_profile.pattern_breadth.trend must be widening, stable, "
                "or narrowing when the current pattern cohort is non-empty"
            )
        if (
            isinstance(breadth_average, bool)
            or not isinstance(breadth_average, (int, float))
            or not math.isfinite(breadth_average)
            or breadth_average < 0
        ):
            errors.append(
                "pattern_profile.pattern_breadth.avg_distinct_patterns_per_talk "
                "must be a finite non-negative number when the current pattern "
                "cohort is non-empty"
            )
        if cohort_count < 10:
            if score_trend != "stable" or driver_direction != "insufficient_history":
                errors.append(
                    "pattern profiles with fewer than 10 current talks must use "
                    "score_trend='stable' and "
                    "score_drivers.direction='insufficient_history'"
                )
        elif driver_direction != score_trend:
            errors.append(
                "pattern_profile.score_drivers.direction must equal score_trend "
                "when at least 10 current talks are scored"
            )

    errors.extend(
        _validate_count_denominators(
            pattern_profile,
            expected_count=cohort_count,
            path="pattern_profile",
        )
    )
    errors.extend(
        _validate_count_bounds(
            pattern_profile,
            cohort_count=cohort_count,
            path="pattern_profile",
        )
    )
    errors.extend(_validate_mode_counts(pattern_profile.get("by_mode"), cohort_count))
    if cohort_count == 0:
        errors.extend(_validate_empty_pattern_cohort(pattern_profile))

    if errors:
        _append_reason(reason_codes, REASON_INVALID_CONTRACT)
        return PatternProfileAssessment(
            current_contract=False,
            catalog_fields_available=False,
            scored_talk_count=cohort_count,
            reason_codes=tuple(reason_codes),
            errors=tuple(errors),
        )

    if cohort_count == 0:
        return PatternProfileAssessment(
            current_contract=True,
            catalog_fields_available=False,
            scored_talk_count=0,
            reason_codes=(REASON_EMPTY_CURRENT_COHORT,),
            errors=(),
        )
    return PatternProfileAssessment(
        current_contract=True,
        catalog_fields_available=True,
        scored_talk_count=cohort_count,
        reason_codes=(),
        errors=(),
    )
