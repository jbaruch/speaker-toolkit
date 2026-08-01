"""Strict, reusable availability contract for profile pattern history.

Owner and consumer skills share this module so a profile exposes auditable
current-generation occurrence rows independently from policy-derived historical
classifications. The module performs no writes and does not encode consumer-
specific fallback policy.
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

from adherence_baseline import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    AdherenceBaselineError,
    validate_adherence_baseline,
)
from return_validation import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    PATTERN_SCORING_SCHEMA_VERSION,
    ReturnValidationError,
    load_catalog,
)
from pattern_opportunities import (  # noqa: E402
    PatternOpportunityError,
    validate_pattern_opportunity_rows,
)


REASON_INVALID_CONTRACT = "invalid_pattern_profile_contract"
REASON_ACTIVE_CATALOG_UNAVAILABLE = "active_pattern_catalog_unavailable"
REASON_CATALOG_FINGERPRINT_MISMATCH = "pattern_catalog_fingerprint_mismatch"
REASON_SCORING_SCHEMA_MISMATCH = "pattern_scoring_schema_mismatch"
REASON_EMPTY_CURRENT_COHORT = "empty_current_pattern_cohort"
REASON_CLASSIFICATION_POLICY_UNAVAILABLE = "pattern_classification_policy_unavailable"

CLASSIFICATION_AVAILABILITY_SCHEMA_VERSION = 1
CLASSIFICATION_POLICY_UNAVAILABLE_REASON = "owner_policy_unconfigured"
_CLASSIFICATION_AVAILABILITY_FIELDS = frozenset(
    {"schema_version", "status", "reason_codes"}
)

_REQUIRED_PATTERN_PROFILE_FIELDS = frozenset(
    {
        "pattern_baseline",
        "baseline_talk_filenames",
        "eligible_talk_count",
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
        "classification_availability",
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
_DERIVED_ARRAY_PATTERN_PROFILE_FIELDS = (
    "underused_patterns",
    "by_mode",
    "strengths",
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
    eligible_talk_count: int | None = None
    classification_fields_available: bool = False


def active_pattern_generation_identity() -> tuple[str, int]:
    """Return the exact bundled catalog fingerprint and scoring schema."""
    return load_catalog().fingerprint, PATTERN_SCORING_SCHEMA_VERSION


def unavailable_classification_availability() -> dict[str, object]:
    """Return the sole schema-v4 classification state currently authorized."""
    return {
        "schema_version": CLASSIFICATION_AVAILABILITY_SCHEMA_VERSION,
        "status": "unavailable",
        "reason_codes": [CLASSIFICATION_POLICY_UNAVAILABLE_REASON],
    }


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


def _validate_unavailable_classifications(
    pattern_profile: Mapping[str, object],
) -> list[str]:
    """Require fail-closed sentinels until an owner policy is versioned."""
    errors: list[str] = []
    availability = pattern_profile.get("classification_availability")
    expected_availability = unavailable_classification_availability()
    if not isinstance(availability, Mapping):
        errors.append("pattern_profile.classification_availability must be an object")
    else:
        missing = sorted(_CLASSIFICATION_AVAILABILITY_FIELDS - set(availability))
        unknown = sorted(
            set(availability) - _CLASSIFICATION_AVAILABILITY_FIELDS,
            key=str,
        )
        if missing or unknown:
            errors.append(
                "pattern_profile.classification_availability fields are "
                f"noncanonical; missing={missing}, "
                f"unknown={[str(field) for field in unknown]}"
            )
        if dict(availability) != expected_availability:
            errors.append(
                "pattern_profile.classification_availability must use the "
                "owner-policy-unconfigured sentinel until a versioned "
                "classification policy exists"
            )

    if pattern_profile.get("score_trend") != "unavailable":
        errors.append(
            "pattern_profile.score_trend must be 'unavailable' while pattern "
            "classification policy is unavailable"
        )

    breadth = pattern_profile.get("pattern_breadth")
    if isinstance(breadth, Mapping):
        if breadth.get("avg_distinct_patterns_per_talk") is not None:
            errors.append(
                "pattern_profile.pattern_breadth.avg_distinct_patterns_per_talk "
                "must be null while coverage-comparable breadth policy is "
                "unavailable"
            )
        if breadth.get("trend") != "unavailable":
            errors.append(
                "pattern_profile.pattern_breadth.trend must be 'unavailable' when "
                "pattern classification policy is unavailable"
            )

    drivers = pattern_profile.get("score_drivers")
    if isinstance(drivers, Mapping):
        if drivers.get("direction") != "unavailable":
            errors.append(
                "pattern_profile.score_drivers.direction must be 'unavailable' "
                "while pattern classification policy is unavailable"
            )
        for field in ("antipattern_drivers", "pattern_drivers"):
            if drivers.get(field) != []:
                errors.append(
                    f"pattern_profile.score_drivers.{field} must be [] when the "
                    "pattern classification policy is unavailable"
                )

    for field in _DERIVED_ARRAY_PATTERN_PROFILE_FIELDS:
        if pattern_profile.get(field) != []:
            errors.append(
                f"pattern_profile.{field} must be [] while pattern "
                "classification policy is unavailable"
            )

    mastery = pattern_profile.get("mastery_levels")
    if isinstance(mastery, Mapping):
        for tier in _MASTERY_TIERS:
            if mastery.get(tier) != []:
                errors.append(
                    f"pattern_profile.mastery_levels.{tier} must be [] while "
                    "pattern classification policy is unavailable"
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
            "pattern_profile is missing required schema-v4 fields: "
            f"{', '.join(missing_fields)}"
        )
    unknown_fields = sorted(
        set(pattern_profile) - _REQUIRED_PATTERN_PROFILE_FIELDS,
        key=str,
    )
    if unknown_fields:
        errors.append(
            "pattern_profile has unknown schema-v4 fields: "
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
        baseline = validate_adherence_baseline(pattern_profile.get("pattern_baseline"))
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

    score_comparable_count = baseline["scored_talk_count"]
    assert isinstance(score_comparable_count, int)  # canonical baseline postcondition
    raw_eligible_count = baseline.get("eligible_talk_count")
    if not _is_integer(raw_eligible_count) or raw_eligible_count < 0:
        errors.append(
            "pattern_profile.pattern_baseline must use scoring-v5 baseline schema 2 "
            "with a non-negative eligible_talk_count"
        )
        eligible_count = 0
    else:
        eligible_count = raw_eligible_count

    if baseline["active_batch_excluded"] is not False:
        errors.append(
            "pattern_profile.pattern_baseline must be a full-cohort snapshot with "
            "active_batch_excluded=false"
        )
    if baseline["excluded_filenames"] != []:
        errors.append("pattern_profile.pattern_baseline.excluded_filenames must be []")

    active_scoring_schema = PATTERN_SCORING_SCHEMA_VERSION
    active_catalog = None
    try:
        active_catalog = load_catalog()
        active_fingerprint = active_catalog.fingerprint
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
    if baseline["pattern_scoring_schema_version"] != active_scoring_schema:
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
    if filenames is not None and len(filenames) != eligible_count:
        errors.append(
            "pattern_profile.baseline_talk_filenames length must equal "
            f"pattern_baseline.eligible_talk_count {eligible_count}, got "
            f"{len(filenames)}"
        )

    profile_eligible_count = pattern_profile.get("eligible_talk_count")
    if (
        not _is_integer(profile_eligible_count)
        or profile_eligible_count != eligible_count
    ):
        errors.append(
            "pattern_profile.eligible_talk_count must equal "
            f"pattern_baseline.eligible_talk_count {eligible_count}, got "
            f"{profile_eligible_count!r}"
        )

    talks_scored = pattern_profile.get("talks_scored")
    if not _is_integer(talks_scored) or talks_scored != score_comparable_count:
        errors.append(
            "pattern_profile.talks_scored must equal "
            "pattern_baseline.scored_talk_count "
            f"{score_comparable_count}, got "
            f"{talks_scored!r}"
        )

    profile_average = pattern_profile.get("average_pattern_score")
    baseline_average = baseline["average_pattern_score"]
    if score_comparable_count == 0:
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

    if active_catalog is not None:
        try:
            errors.extend(
                validate_pattern_opportunity_rows(
                    pattern_profile.get("pattern_usage"),
                    pattern_profile.get("antipattern_frequency"),
                    eligible_cohort_count=eligible_count,
                    catalog=active_catalog,
                )
            )
        except PatternOpportunityError as exc:
            errors.append(f"pattern opportunity rows are invalid: {exc}")
    errors.extend(_validate_unavailable_classifications(pattern_profile))

    if errors:
        _append_reason(reason_codes, REASON_INVALID_CONTRACT)
        return PatternProfileAssessment(
            current_contract=False,
            catalog_fields_available=False,
            scored_talk_count=score_comparable_count,
            reason_codes=tuple(reason_codes),
            errors=tuple(errors),
            eligible_talk_count=eligible_count,
        )

    if eligible_count == 0:
        return PatternProfileAssessment(
            current_contract=True,
            catalog_fields_available=False,
            scored_talk_count=score_comparable_count,
            reason_codes=(
                REASON_EMPTY_CURRENT_COHORT,
                REASON_CLASSIFICATION_POLICY_UNAVAILABLE,
            ),
            errors=(),
            eligible_talk_count=0,
        )
    return PatternProfileAssessment(
        current_contract=True,
        catalog_fields_available=True,
        scored_talk_count=score_comparable_count,
        reason_codes=(REASON_CLASSIFICATION_POLICY_UNAVAILABLE,),
        errors=(),
        eligible_talk_count=eligible_count,
    )
