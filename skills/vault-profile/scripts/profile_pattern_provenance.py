"""Strict reusable contract for profile pattern history.

Schema-v4 pattern profiles remain readable as occurrence-only inputs with every
classification domain disabled. Schema-v5 profiles add a self-contained,
policy-bound classification contract with independent domain availability.
This module validates provenance and projections; classification arithmetic is
owned only by ``classify-pattern-profile.py``.
"""

from __future__ import annotations

import math
import pathlib
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import TypeGuard


_INGRESS_SCRIPTS = (
    pathlib.Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"
)
if str(_INGRESS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_INGRESS_SCRIPTS))

# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from adherence_baseline import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    AdherenceBaselineError,
    validate_adherence_baseline,
)
from pattern_classification_runtime import validate_policy_stamp  # noqa: E402
from pattern_opportunities import (  # noqa: E402
    PatternOpportunityError,
    validate_pattern_opportunity_rows,
)

# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from return_validation import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    PATTERN_SCORING_SCHEMA_VERSION,
    ReturnValidationError,
    load_catalog,
)


REASON_INVALID_CONTRACT = "invalid_pattern_profile_contract"
REASON_ACTIVE_CATALOG_UNAVAILABLE = "active_pattern_catalog_unavailable"
REASON_CATALOG_FINGERPRINT_MISMATCH = "pattern_catalog_fingerprint_mismatch"
REASON_SCORING_SCHEMA_MISMATCH = "pattern_scoring_schema_mismatch"
REASON_EMPTY_CURRENT_COHORT = "empty_current_pattern_cohort"
REASON_CLASSIFICATION_POLICY_UNAVAILABLE = "pattern_classification_policy_unavailable"
REASON_CLASSIFICATION_POLICY_INVALID = "pattern_classification_policy_invalid"

LEGACY_CLASSIFICATION_AVAILABILITY_SCHEMA_VERSION = 1
CLASSIFICATION_AVAILABILITY_SCHEMA_VERSION = 2
CLASSIFICATION_SCHEMA_VERSION = 1
CLASSIFICATION_POLICY_UNAVAILABLE_REASON = "owner_policy_unconfigured"

_LEGACY_AVAILABILITY_FIELDS = frozenset({"schema_version", "status", "reason_codes"})
CLASSIFICATION_DOMAINS = (
    "mastery_and_novelty",
    "antipattern_recurrence",
    "underuse",
    "signature_combinations",
    "trends",
    "modes",
)
_DOMAIN_STATUS_FIELDS = frozenset({"status", "reason_codes"})
_AVAILABILITY_V2_FIELDS = frozenset({"schema_version", *CLASSIFICATION_DOMAINS})

_COMMON_PATTERN_PROFILE_FIELDS = frozenset(
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
_V4_PATTERN_PROFILE_FIELDS = _COMMON_PATTERN_PROFILE_FIELDS
_V5_PATTERN_PROFILE_FIELDS = _COMMON_PATTERN_PROFILE_FIELDS | frozenset(
    {
        "classification_schema_version",
        "classification_policy",
        "pattern_classifications",
        "antipattern_classifications",
        "trend_analysis",
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
_POSITIVE_CLASSIFICATIONS = frozenset(
    {
        "signature",
        "regular",
        "occasional",
        "rare",
        "never_tried",
        "not_yet_observed",
        "unclassified",
    }
)
_ANTIPATTERN_CLASSIFICATIONS = frozenset(
    {
        "high_frequency",
        "moderate_frequency",
        "occasional",
        "confirmed_none",
        "unclassified",
    }
)
_OBSERVATION_STATUSES = frozenset(
    {"observed", "confirmed_absent", "not_yet_observed", "unavailable"}
)
_CLASSIFICATION_ROW_FIELDS = frozenset(
    {
        "pattern_id",
        "classification",
        "observation_status",
        "absence_conclusion_capable",
        "evidence",
        "reason_codes",
    }
)
_EVIDENCE_COUNT_FIELDS = (
    "applicable_count",
    "evaluable_count",
    "detected_count",
    "unevaluable_count",
)
_EVIDENCE_RATE_FIELDS = ("applicable_coverage", "lower", "upper")
_EVIDENCE_FIELDS = frozenset((*_EVIDENCE_COUNT_FIELDS, *_EVIDENCE_RATE_FIELDS))
_COMBINATION_FIELDS = frozenset(
    {"combination_id", "pattern_ids", "evidence", "reason_codes"}
)
_TREND_ANALYSIS_FIELDS = frozenset(
    {
        "status",
        "reason_codes",
        "sample",
        "score",
        "breadth",
        "pattern_movements",
        "antipattern_movements",
    }
)
_TREND_SAMPLE_FIELDS = frozenset(
    {
        "required_talk_count",
        "valid_date_talk_count",
        "invalid_date_filenames",
        "selected_filenames",
        "opportunity_coverage_identity",
    }
)
_TREND_METRIC_FIELDS = frozenset({"status", "prior_average", "recent_average", "delta"})
_TREND_MOVEMENT_FIELDS = frozenset(
    {"pattern_id", "movement", "prior_evidence", "recent_evidence", "reason_codes"}
)
_TREND_UNAVAILABLE_REASONS = frozenset(
    {
        "insufficient_valid_date_sample",
        "opportunity_identity_unavailable",
        "incomparable_opportunity_identities",
        "no_evaluable_pattern_opportunities",
    }
)
_MOVEMENT_REASON_CODES = {
    "increasing": ("conservative_interval_increase",),
    "decreasing": ("conservative_interval_decrease",),
    "stable": ("conservative_interval_stable",),
    "indeterminate": ("uncertainty_spans_movement_threshold",),
}
_UNAVAILABLE_MOVEMENT_REASON_CODES = frozenset(
    {"incomplete_window_applicability", "window_bounds_unavailable"}
)
_LOWER_HEX_CHARS = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class PatternProfileAssessment:
    """Availability and diagnostics for one nested pattern profile."""

    current_contract: bool
    catalog_fields_available: bool
    scored_talk_count: int | None
    reason_codes: tuple[str, ...]
    errors: tuple[str, ...]
    eligible_talk_count: int | None = None
    classification_fields_available: bool = False
    available_classification_domains: frozenset[str] = frozenset()
    contract_version: int | None = None
    policy_semantic_sha256: str | None = None

    def domain_available(self, domain: str) -> bool:
        """Return whether one policy-derived domain is independently enabled."""
        return domain in self.available_classification_domains


def active_pattern_generation_identity() -> tuple[str, int]:
    """Return the exact bundled catalog fingerprint and scoring schema."""
    return load_catalog().fingerprint, PATTERN_SCORING_SCHEMA_VERSION


def unavailable_classification_availability() -> dict[str, object]:
    """Return the schema-v4 occurrence-only classification sentinel."""
    return {
        "schema_version": LEGACY_CLASSIFICATION_AVAILABILITY_SCHEMA_VERSION,
        "status": "unavailable",
        "reason_codes": [CLASSIFICATION_POLICY_UNAVAILABLE_REASON],
    }


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_optional_unit_interval(value: object) -> bool:
    return value is None or (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and 0 <= value <= 1
        and math.isfinite(value)
    )


def _is_finite_number(value: object) -> TypeGuard[int | float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not isinstance(value, float) or math.isfinite(value)


def _is_lower_hex64(value: object) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _LOWER_HEX_CHARS for character in value)
    )


def _unit_ratio(numerator: int, denominator: int) -> float:
    return float(Fraction(numerator, denominator))


def _append_reason(reason_codes: list[str], reason_code: str) -> None:
    if reason_code not in reason_codes:
        reason_codes.append(reason_code)


def _exact_fields(
    value: Mapping[object, object], expected: frozenset[str], *, path: str
) -> list[str]:
    missing = sorted(field for field in expected if field not in value)
    unknown = sorted((field for field in value if field not in expected), key=str)
    if not missing and not unknown:
        return []
    return [
        f"{path} fields are noncanonical; missing={missing}, "
        f"unknown={[str(item) for item in unknown]}"
    ]


def _string_array(
    value: object, *, path: str, sorted_required: bool = False
) -> list[str]:
    if not isinstance(value, list):
        return [f"{path} must be an array"]
    errors: list[str] = []
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item or item != item.strip():
            errors.append(
                f"{path}[{index}] must be a non-empty string without edge whitespace"
            )
        else:
            strings.append(item)
    if len(strings) != len(set(strings)):
        errors.append(f"{path} must not contain duplicates")
    if sorted_required and strings != sorted(strings):
        errors.append(f"{path} must be sorted")
    return errors


def _canonical_cohort_filenames(value: object) -> tuple[list[str] | None, list[str]]:
    errors = _string_array(
        value, path="pattern_profile.baseline_talk_filenames", sorted_required=True
    )
    if errors or not isinstance(value, list):
        return None, errors
    return list(value), []


def _validate_common_shape(pattern_profile: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    for field in _ARRAY_PATTERN_PROFILE_FIELDS:
        if field in pattern_profile and not isinstance(pattern_profile[field], list):
            errors.append(f"pattern_profile.{field} must be an array")
    for field in ("strengths_note", "note"):
        if field in pattern_profile and not isinstance(pattern_profile[field], str):
            errors.append(f"pattern_profile.{field} must be a string")

    breadth = pattern_profile.get("pattern_breadth")
    if isinstance(breadth, Mapping):
        missing_breadth = sorted(_REQUIRED_PATTERN_BREADTH_FIELDS - set(breadth))
        unknown_breadth = sorted(
            set(breadth) - _REQUIRED_PATTERN_BREADTH_FIELDS, key=str
        )
        if missing_breadth:
            errors.append(
                "pattern_profile.pattern_breadth is missing required fields: "
                + ", ".join(missing_breadth)
            )
        if unknown_breadth:
            errors.append(
                "pattern_profile.pattern_breadth has unknown fields: "
                + ", ".join(str(field) for field in unknown_breadth)
            )
        if "note" in breadth and not isinstance(breadth["note"], str):
            errors.append("pattern_profile.pattern_breadth.note must be a string")
    else:
        errors.append("pattern_profile.pattern_breadth must be an object")

    drivers = pattern_profile.get("score_drivers")
    if isinstance(drivers, Mapping):
        errors.extend(
            _exact_fields(
                drivers,
                _REQUIRED_SCORE_DRIVER_FIELDS,
                path="pattern_profile.score_drivers",
            )
        )
        for field in ("antipattern_drivers", "pattern_drivers"):
            if field in drivers:
                errors.extend(
                    _string_array(
                        drivers[field],
                        path=f"pattern_profile.score_drivers.{field}",
                        sorted_required=True,
                    )
                )
        if "note" in drivers and not isinstance(drivers["note"], str):
            errors.append("pattern_profile.score_drivers.note must be a string")
    else:
        errors.append("pattern_profile.score_drivers must be an object")

    mastery = pattern_profile.get("mastery_levels")
    if isinstance(mastery, Mapping):
        missing_tiers = sorted(set(_MASTERY_TIERS) - set(mastery))
        unknown_tiers = sorted(set(mastery) - set(_MASTERY_TIERS), key=str)
        if missing_tiers:
            errors.append(
                "pattern_profile.mastery_levels is missing required tiers: "
                + ", ".join(missing_tiers)
            )
        if unknown_tiers:
            errors.append(
                "pattern_profile.mastery_levels has unknown tiers: "
                + ", ".join(str(field) for field in unknown_tiers)
            )
        for tier in _MASTERY_TIERS:
            if tier in mastery:
                errors.extend(
                    _string_array(
                        mastery[tier],
                        path=f"pattern_profile.mastery_levels.{tier}",
                        sorted_required=True,
                    )
                )
    else:
        errors.append("pattern_profile.mastery_levels must be an object")
    return errors


def _validate_v4_unavailable(pattern_profile: Mapping[str, object]) -> list[str]:
    """Require fail-closed schema-v4 derived sentinels."""
    errors: list[str] = []
    availability = pattern_profile.get("classification_availability")
    expected = unavailable_classification_availability()
    if not isinstance(availability, Mapping):
        errors.append("pattern_profile.classification_availability must be an object")
    else:
        errors.extend(
            _exact_fields(
                availability,
                _LEGACY_AVAILABILITY_FIELDS,
                path="pattern_profile.classification_availability",
            )
        )
        if dict(availability) != expected:
            errors.append(
                "pattern_profile.classification_availability must use the "
                "owner-policy-unconfigured schema-v4 sentinel"
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
                "must be null while coverage-comparable breadth policy is unavailable"
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
                f"pattern_profile.{field} must be [] while pattern classification "
                "policy is unavailable"
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


def _validate_availability_v2(
    value: object,
) -> tuple[frozenset[str], list[str]]:
    if not isinstance(value, Mapping):
        return frozenset(), [
            "pattern_profile.classification_availability must be an object"
        ]
    errors = _exact_fields(
        value,
        _AVAILABILITY_V2_FIELDS,
        path="pattern_profile.classification_availability",
    )
    availability_schema_version = value.get("schema_version")
    if (
        not _is_integer(availability_schema_version)
        or availability_schema_version != CLASSIFICATION_AVAILABILITY_SCHEMA_VERSION
    ):
        errors.append(
            "pattern_profile.classification_availability.schema_version must be 2"
        )
    available: set[str] = set()
    for domain in CLASSIFICATION_DOMAINS:
        item = value.get(domain)
        path = f"pattern_profile.classification_availability.{domain}"
        if not isinstance(item, Mapping):
            errors.append(f"{path} must be an object")
            continue
        errors.extend(_exact_fields(item, _DOMAIN_STATUS_FIELDS, path=path))
        status = item.get("status")
        if status not in {"available", "unavailable"}:
            errors.append(f"{path}.status must be available or unavailable")
        reason_codes = item.get("reason_codes")
        errors.extend(_string_array(reason_codes, path=f"{path}.reason_codes"))
        if status == "available":
            available.add(domain)
            if reason_codes != []:
                errors.append(f"{path}.reason_codes must be [] when available")
        elif status == "unavailable" and reason_codes == []:
            errors.append(f"{path}.reason_codes must explain unavailability")
    modes = value.get("modes")
    if isinstance(modes, Mapping) and modes != {
        "status": "unavailable",
        "reason_codes": ["talk_mode_assignments_unavailable"],
    }:
        errors.append(
            "pattern_profile.classification_availability.modes must fail closed "
            "with talk_mode_assignments_unavailable"
        )
    return frozenset(available), errors


def _expected_evidence(raw: Mapping[str, object]) -> dict[str, object] | None:
    fields = (
        "eligible_cohort_count",
        "not_applicable_count",
        "evaluable_count",
        "detected_count",
        "unevaluable_count",
    )
    counts: dict[str, int] = {}
    for field in fields:
        value = raw.get(field)
        if not _is_integer(value) or value < 0:
            return None
        counts[field] = value
    eligible = counts["eligible_cohort_count"]
    not_applicable = counts["not_applicable_count"]
    evaluable = counts["evaluable_count"]
    detected = counts["detected_count"]
    unevaluable = counts["unevaluable_count"]
    applicable = eligible - not_applicable
    if applicable < 0 or evaluable + unevaluable != applicable or detected > evaluable:
        return None
    if applicable == 0:
        coverage = lower = upper = None
    else:
        coverage = _unit_ratio(evaluable, applicable)
        lower = _unit_ratio(detected, applicable)
        upper = _unit_ratio(detected + unevaluable, applicable)
    return {
        "applicable_count": applicable,
        "evaluable_count": evaluable,
        "detected_count": detected,
        "unevaluable_count": unevaluable,
        "applicable_coverage": coverage,
        "lower": lower,
        "upper": upper,
    }


def _validate_evidence(value: Mapping[object, object], *, path: str) -> list[str]:
    errors = _exact_fields(value, _EVIDENCE_FIELDS, path=path)
    counts: dict[str, int] = {}
    for field in _EVIDENCE_COUNT_FIELDS:
        count = value.get(field)
        if not _is_integer(count) or count < 0:
            errors.append(f"{path}.{field} must be a non-negative integer")
        else:
            counts[field] = count

    for field in _EVIDENCE_RATE_FIELDS:
        if not _is_optional_unit_interval(value.get(field)):
            errors.append(
                f"{path}.{field} must be null or a finite number between zero and one"
            )

    if len(counts) != len(_EVIDENCE_COUNT_FIELDS):
        return errors
    applicable = counts["applicable_count"]
    evaluable = counts["evaluable_count"]
    detected = counts["detected_count"]
    unevaluable = counts["unevaluable_count"]
    if evaluable + unevaluable != applicable:
        errors.append(f"{path} must satisfy applicable_count = E + U")
        return errors
    if detected > evaluable:
        errors.append(f"{path}.detected_count cannot exceed evaluable_count")
        return errors

    expected_rates: dict[str, float | None]
    if applicable == 0:
        expected_rates = {
            "applicable_coverage": None,
            "lower": None,
            "upper": None,
        }
    else:
        expected_rates = {
            "applicable_coverage": _unit_ratio(evaluable, applicable),
            "lower": _unit_ratio(detected, applicable),
            "upper": _unit_ratio(detected + unevaluable, applicable),
        }
    for field, expected in expected_rates.items():
        actual = value.get(field)
        if _is_optional_unit_interval(actual) and actual != expected:
            errors.append(
                f"{path}.{field} must equal the canonical ratio {expected!r}, "
                f"got {actual!r}"
            )
    return errors


def _validate_classification_lane(
    value: object,
    raw_rows: object,
    *,
    lane: str,
    allowed_classifications: frozenset[str],
    active_catalog: object,
) -> tuple[list[Mapping[str, object]], list[str]]:
    errors: list[str] = []
    if not isinstance(value, list):
        return [], [f"pattern_profile.{lane} must be an array"]
    if not isinstance(raw_rows, list):
        return [], [f"pattern_profile.{lane} cannot bind missing raw rows"]
    raw_by_id = {
        row.get("pattern_id"): row
        for row in raw_rows
        if isinstance(row, Mapping) and isinstance(row.get("pattern_id"), str)
    }
    expected_ids = list(raw_by_id)
    observed_ids: list[str] = []
    canonical: list[Mapping[str, object]] = []
    entries = getattr(active_catalog, "entries", {})
    for index, item in enumerate(value):
        path = f"pattern_profile.{lane}[{index}]"
        if not isinstance(item, Mapping):
            errors.append(f"{path} must be an object")
            continue
        errors.extend(_exact_fields(item, _CLASSIFICATION_ROW_FIELDS, path=path))
        pattern_id = item.get("pattern_id")
        if not isinstance(pattern_id, str) or not pattern_id:
            errors.append(f"{path}.pattern_id must be a non-empty string")
            continue
        canonical.append(item)
        observed_ids.append(pattern_id)
        classification = item.get("classification")
        if classification not in allowed_classifications:
            errors.append(f"{path}.classification is invalid: {classification!r}")
        observation_status = item.get("observation_status")
        if observation_status not in _OBSERVATION_STATUSES:
            errors.append(
                f"{path}.observation_status is invalid: {observation_status!r}"
            )
        absence_capable = item.get("absence_conclusion_capable")
        entry = entries.get(pattern_id) if isinstance(entries, Mapping) else None
        expected_absence = (
            getattr(entry, "absence_evaluable_from", None) is not None
            if entry is not None
            else None
        )
        if not isinstance(absence_capable, bool) or absence_capable != expected_absence:
            errors.append(
                f"{path}.absence_conclusion_capable must match active catalog metadata"
            )
        evidence = item.get("evidence")
        applicable_count: object = None
        detected_count: object = None
        if not isinstance(evidence, Mapping):
            errors.append(f"{path}.evidence must be an object")
        else:
            errors.extend(_validate_evidence(evidence, path=f"{path}.evidence"))
            applicable_count = evidence.get("applicable_count")
            detected_count = evidence.get("detected_count")
            raw = raw_by_id.get(pattern_id)
            expected_evidence = (
                _expected_evidence(raw) if isinstance(raw, Mapping) else None
            )
            if expected_evidence is not None and dict(evidence) != expected_evidence:
                errors.append(
                    f"{path}.evidence does not match the exact raw A/E/D/U row"
                )
        errors.extend(
            _string_array(item.get("reason_codes"), path=f"{path}.reason_codes")
        )
        if item.get("reason_codes") == []:
            errors.append(f"{path}.reason_codes must not be empty")
        if absence_capable is False and classification in {
            "never_tried",
            "confirmed_none",
        }:
            errors.append(
                f"{path}.classification cannot conclude absence for a positive-only entry"
            )
        if (
            absence_capable is False
            and _is_integer(applicable_count)
            and applicable_count > 0
            and _is_integer(detected_count)
            and detected_count == 0
        ):
            required_classification = (
                "not_yet_observed"
                if lane == "pattern_classifications"
                else "unclassified"
            )
            if (
                classification != required_classification
                or observation_status != "not_yet_observed"
            ):
                errors.append(
                    f"{path} positive-only zero detection must be "
                    f"{required_classification}/not_yet_observed"
                )
    if observed_ids != expected_ids:
        errors.append(
            f"pattern_profile.{lane} must be sorted and exhaustive for its raw lane; "
            f"expected={expected_ids}, got={observed_ids}"
        )
    return canonical, errors


def _validate_combinations(
    value: object,
    positive_rows: Sequence[Mapping[str, object]],
    *,
    eligible_talk_count: int,
) -> list[str]:
    if not isinstance(value, list):
        return ["pattern_profile.signature_combinations must be an array"]
    errors: list[str] = []
    eligible = {
        row.get("pattern_id")
        for row in positive_rows
        if row.get("classification") in {"regular", "signature"}
    }
    ids: list[str] = []
    previous_sort_key: tuple[float, int, tuple[str, ...]] | None = None
    for index, item in enumerate(value):
        path = f"pattern_profile.signature_combinations[{index}]"
        if not isinstance(item, Mapping):
            errors.append(f"{path} must be an object")
            continue
        errors.extend(_exact_fields(item, _COMBINATION_FIELDS, path=path))
        members = item.get("pattern_ids")
        if not isinstance(members, list) or len(members) not in {2, 3}:
            errors.append(f"{path}.pattern_ids must contain exactly two or three IDs")
            continue
        errors.extend(
            _string_array(members, path=f"{path}.pattern_ids", sorted_required=True)
        )
        combination_id = item.get("combination_id")
        expected_id = "+".join(str(member) for member in members)
        if combination_id != expected_id:
            errors.append(f"{path}.combination_id must equal {expected_id!r}")
        elif isinstance(combination_id, str):
            ids.append(combination_id)
        if any(member not in eligible for member in members):
            errors.append(f"{path} members must each be regular or signature")
        evidence = item.get("evidence")
        if not isinstance(evidence, Mapping):
            errors.append(f"{path}.evidence must be an object")
            continue
        evidence_errors = _validate_evidence(evidence, path=f"{path}.evidence")
        errors.extend(evidence_errors)
        lower = evidence.get("lower")
        detected = evidence.get("detected_count")
        applicable = evidence.get("applicable_count")
        if evidence_errors:
            continue
        assert _is_integer(applicable)
        if applicable > eligible_talk_count:
            errors.append(
                f"{path}.evidence.applicable_count cannot exceed the eligible "
                f"talk count {eligible_talk_count}"
            )
        if not isinstance(lower, (int, float)) or isinstance(lower, bool):
            errors.append(f"{path}.evidence.lower must be numeric")
            continue
        assert _is_integer(detected)
        sort_key = (-float(lower), -detected, tuple(str(member) for member in members))
        if previous_sort_key is not None and sort_key < previous_sort_key:
            errors.append(
                "pattern_profile.signature_combinations must use canonical ranking"
            )
        previous_sort_key = sort_key
        errors.extend(
            _string_array(item.get("reason_codes"), path=f"{path}.reason_codes")
        )
        if item.get("reason_codes") == []:
            errors.append(f"{path}.reason_codes must not be empty")
    if len(ids) != len(set(ids)):
        errors.append(
            "pattern_profile.signature_combinations duplicates a canonical ID"
        )
    if len(value) > 10:
        errors.append(
            "pattern_profile.signature_combinations may contain at most 10 rows"
        )
    return errors


def _validate_trend_metric(
    value: object,
    *,
    path: str,
    available: bool,
    allowed_statuses: frozenset[str],
) -> tuple[object, list[str]]:
    if not isinstance(value, Mapping):
        return None, [f"{path} must be an object"]
    errors = _exact_fields(value, _TREND_METRIC_FIELDS, path=path)
    status = value.get("status")
    if not available:
        expected = {
            "status": "unavailable",
            "prior_average": None,
            "recent_average": None,
            "delta": None,
        }
        if dict(value) != expected:
            errors.append(f"{path} must use the unavailable null sentinel")
        return status, errors

    if status not in allowed_statuses:
        errors.append(f"{path}.status is invalid: {status!r}")
    numbers: dict[str, int | float] = {}
    for field in ("prior_average", "recent_average", "delta"):
        raw = value.get(field)
        if not _is_finite_number(raw):
            errors.append(f"{path}.{field} must be a finite number")
        else:
            numbers[field] = raw
    if len(numbers) == 3:
        try:
            delta_matches = math.isclose(
                float(numbers["delta"]),
                float(numbers["recent_average"]) - float(numbers["prior_average"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        except OverflowError:
            delta_matches = False
        if not delta_matches:
            errors.append(f"{path}.delta must equal recent_average - prior_average")
    return status, errors


def _validate_trend_movement_lane(
    value: object,
    *,
    path: str,
    expected_ids: list[str],
    window_size: int | None,
) -> tuple[list[Mapping[str, object]], list[str]]:
    if not isinstance(value, list):
        return [], [f"{path} must be an array"]
    rows: list[Mapping[str, object]] = []
    observed_ids: list[str] = []
    errors: list[str] = []
    for index, item in enumerate(value):
        row_path = f"{path}[{index}]"
        if not isinstance(item, Mapping):
            errors.append(f"{row_path} must be an object")
            continue
        errors.extend(_exact_fields(item, _TREND_MOVEMENT_FIELDS, path=row_path))
        pattern_id = item.get("pattern_id")
        if not isinstance(pattern_id, str) or not pattern_id:
            errors.append(f"{row_path}.pattern_id must be a non-empty string")
        else:
            observed_ids.append(pattern_id)
            rows.append(item)

        movement = item.get("movement")
        reason_codes = item.get("reason_codes")
        errors.extend(_string_array(reason_codes, path=f"{row_path}.reason_codes"))
        normalized_reasons = (
            tuple(reason_codes)
            if isinstance(reason_codes, list)
            and all(isinstance(reason, str) for reason in reason_codes)
            else ()
        )
        if movement == "unavailable":
            if (
                len(normalized_reasons) != 1
                or normalized_reasons[0] not in _UNAVAILABLE_MOVEMENT_REASON_CODES
            ):
                errors.append(
                    f"{row_path}.reason_codes must explain unavailable movement"
                )
        elif movement in _MOVEMENT_REASON_CODES:
            if normalized_reasons != _MOVEMENT_REASON_CODES[movement]:
                errors.append(
                    f"{row_path}.reason_codes must match movement {movement!r}"
                )
        else:
            errors.append(f"{row_path}.movement is invalid: {movement!r}")

        evidence_by_window: dict[str, Mapping[object, object]] = {}
        evidence_errors_by_window: dict[str, list[str]] = {}
        for field in ("prior_evidence", "recent_evidence"):
            evidence = item.get(field)
            evidence_path = f"{row_path}.{field}"
            if not isinstance(evidence, Mapping):
                errors.append(f"{evidence_path} must be an object")
                continue
            evidence_errors = _validate_evidence(evidence, path=evidence_path)
            errors.extend(evidence_errors)
            evidence_by_window[field] = evidence
            evidence_errors_by_window[field] = evidence_errors

        if window_size is not None and len(evidence_by_window) == 2:
            applicable_counts = [
                evidence_by_window[field].get("applicable_count")
                for field in ("prior_evidence", "recent_evidence")
            ]
            for field, applicable in zip(
                ("prior_evidence", "recent_evidence"),
                applicable_counts,
                strict=True,
            ):
                if _is_integer(applicable) and applicable > window_size:
                    errors.append(
                        f"{row_path}.{field}.applicable_count cannot exceed "
                        f"trend window size {window_size}"
                    )
            complete_windows = all(
                _is_integer(applicable) and applicable == window_size
                for applicable in applicable_counts
            )
            if movement == "unavailable":
                reason = normalized_reasons[0] if len(normalized_reasons) == 1 else None
                if reason == "incomplete_window_applicability" and complete_windows:
                    errors.append(
                        f"{row_path}.movement cannot report incomplete applicability "
                        "for complete windows"
                    )
                if reason == "window_bounds_unavailable" and not any(
                    evidence_errors_by_window.values()
                ):
                    errors.append(
                        f"{row_path}.movement cannot report unavailable bounds for "
                        "valid evidence"
                    )
            elif movement in _MOVEMENT_REASON_CODES and not complete_windows:
                errors.append(
                    f"{row_path}.movement must be unavailable unless both windows "
                    f"have {window_size} applicable talks"
                )

    if observed_ids != expected_ids:
        errors.append(
            f"{path} must be sorted and exhaustive; "
            f"expected={expected_ids}, got={observed_ids}"
        )
    return rows, errors


def _validate_trend_analysis(
    pattern_profile: Mapping[str, object],
    positive_rows: Sequence[Mapping[str, object]],
    antipattern_rows: Sequence[Mapping[str, object]],
    *,
    eligible_talk_count: int,
    required_talk_count: int | None,
    window_size: int | None,
) -> list[str]:
    value = pattern_profile.get("trend_analysis")
    if not isinstance(value, Mapping):
        return ["pattern_profile.trend_analysis must be an object"]
    path = "pattern_profile.trend_analysis"
    errors = _exact_fields(value, _TREND_ANALYSIS_FIELDS, path=path)
    status = value.get("status")
    reason_codes = value.get("reason_codes")
    errors.extend(_string_array(reason_codes, path=f"{path}.reason_codes"))
    reasons = (
        list(reason_codes)
        if isinstance(reason_codes, list)
        and all(isinstance(reason, str) for reason in reason_codes)
        else []
    )
    available = status == "available"
    unavailable_reason: str | None = None
    if available:
        if reasons != []:
            errors.append(f"{path}.reason_codes must be [] when available")
    elif status == "unavailable":
        if len(reasons) != 1 or reasons[0] not in _TREND_UNAVAILABLE_REASONS:
            errors.append(
                f"{path}.reason_codes must contain one supported unavailability reason"
            )
        else:
            unavailable_reason = reasons[0]
    else:
        errors.append(f"{path}.status must be available or unavailable")

    availability = pattern_profile.get("classification_availability")
    trend_availability = (
        availability.get("trends") if isinstance(availability, Mapping) else None
    )
    expected_availability = {"status": status, "reason_codes": reasons}
    if (
        not isinstance(trend_availability, Mapping)
        or dict(trend_availability) != expected_availability
    ):
        errors.append(
            "pattern_profile.classification_availability.trends must exactly mirror "
            "trend_analysis status and reasons"
        )

    baseline_value = pattern_profile.get("baseline_talk_filenames")
    baseline_filenames = (
        list(baseline_value)
        if isinstance(baseline_value, list)
        and all(isinstance(filename, str) for filename in baseline_value)
        else []
    )
    baseline_set = set(baseline_filenames)
    sample = value.get("sample")
    sample_required: int | None = None
    valid_date_count: int | None = None
    invalid_filenames: list[str] | None = None
    selected_filenames: list[str] | None = None
    identity: object = None
    if not isinstance(sample, Mapping):
        errors.append(f"{path}.sample must be an object")
    else:
        sample_path = f"{path}.sample"
        errors.extend(_exact_fields(sample, _TREND_SAMPLE_FIELDS, path=sample_path))
        raw_required = sample.get("required_talk_count")
        if not _is_integer(raw_required) or raw_required < 1:
            errors.append(
                f"{sample_path}.required_talk_count must be a positive integer"
            )
        else:
            sample_required = raw_required
            if (
                required_talk_count is not None
                and sample_required != required_talk_count
            ):
                errors.append(
                    f"{sample_path}.required_talk_count must equal the applied policy "
                    f"value {required_talk_count}"
                )
        raw_valid = sample.get("valid_date_talk_count")
        if not _is_integer(raw_valid) or raw_valid < 0:
            errors.append(
                f"{sample_path}.valid_date_talk_count must be a non-negative integer"
            )
        else:
            valid_date_count = raw_valid

        raw_invalid = sample.get("invalid_date_filenames")
        invalid_errors = _string_array(
            raw_invalid,
            path=f"{sample_path}.invalid_date_filenames",
            sorted_required=True,
        )
        errors.extend(invalid_errors)
        if not invalid_errors and isinstance(raw_invalid, list):
            invalid_filenames = list(raw_invalid)
        raw_selected = sample.get("selected_filenames")
        selected_errors = _string_array(
            raw_selected, path=f"{sample_path}.selected_filenames"
        )
        errors.extend(selected_errors)
        if not selected_errors and isinstance(raw_selected, list):
            selected_filenames = list(raw_selected)

        for field, filenames in (
            ("invalid_date_filenames", invalid_filenames),
            ("selected_filenames", selected_filenames),
        ):
            if filenames is not None:
                unknown = sorted(set(filenames) - baseline_set)
                if unknown:
                    errors.append(
                        f"{sample_path}.{field} contains filenames outside the "
                        f"baseline: {unknown}"
                    )
        if (
            invalid_filenames is not None
            and selected_filenames is not None
            and set(invalid_filenames).intersection(selected_filenames)
        ):
            errors.append(
                f"{sample_path}.selected_filenames cannot include invalid-date talks"
            )
        if valid_date_count is not None and invalid_filenames is not None:
            if valid_date_count + len(invalid_filenames) != eligible_talk_count:
                errors.append(
                    f"{sample_path} valid and invalid date counts must equal the "
                    f"eligible talk count {eligible_talk_count}"
                )
        identity = sample.get("opportunity_coverage_identity")

    if available:
        if (
            sample_required is not None
            and selected_filenames is not None
            and len(selected_filenames) != sample_required
        ):
            errors.append(
                f"{path}.sample.selected_filenames must contain exactly "
                f"{sample_required} talks when trends are available"
            )
        if valid_date_count is not None and sample_required is not None:
            if valid_date_count < sample_required:
                errors.append(
                    f"{path}.sample does not have enough valid dated talks for trends"
                )
        if not _is_lower_hex64(identity):
            errors.append(
                f"{path}.sample.opportunity_coverage_identity must be lowercase hex64 "
                "when trends are available"
            )
    elif unavailable_reason == "insufficient_valid_date_sample":
        if valid_date_count is not None and sample_required is not None:
            if valid_date_count >= sample_required:
                errors.append(
                    f"{path}.sample must have fewer valid talks than required for "
                    "insufficient_valid_date_sample"
                )
        if selected_filenames not in (None, []):
            errors.append(
                f"{path}.sample.selected_filenames must be [] for an insufficient sample"
            )
        if identity is not None:
            errors.append(
                f"{path}.sample.opportunity_coverage_identity must be null for an "
                "insufficient sample"
            )
    elif unavailable_reason in {
        "opportunity_identity_unavailable",
        "incomparable_opportunity_identities",
        "no_evaluable_pattern_opportunities",
    }:
        if (
            sample_required is not None
            and selected_filenames is not None
            and len(selected_filenames) != sample_required
        ):
            errors.append(
                f"{path}.sample.selected_filenames must contain exactly "
                f"{sample_required} talks after sample selection"
            )
        if valid_date_count is not None and sample_required is not None:
            if valid_date_count < sample_required:
                errors.append(f"{path}.sample must have enough valid dated talks")
        if unavailable_reason == "no_evaluable_pattern_opportunities":
            if not _is_lower_hex64(identity):
                errors.append(
                    f"{path}.sample.opportunity_coverage_identity must be lowercase "
                    "hex64 after identity resolution"
                )
        elif identity is not None:
            errors.append(
                f"{path}.sample.opportunity_coverage_identity must be null while "
                "identity resolution is unavailable"
            )

    score_status, metric_errors = _validate_trend_metric(
        value.get("score"),
        path=f"{path}.score",
        available=available,
        allowed_statuses=frozenset({"improving", "declining", "stable"}),
    )
    errors.extend(metric_errors)
    breadth_status, metric_errors = _validate_trend_metric(
        value.get("breadth"),
        path=f"{path}.breadth",
        available=available,
        allowed_statuses=frozenset({"widening", "narrowing", "stable"}),
    )
    errors.extend(metric_errors)

    pattern_rows: list[Mapping[str, object]] = []
    antipattern_movement_rows: list[Mapping[str, object]] = []
    if available:
        pattern_rows, movement_errors = _validate_trend_movement_lane(
            value.get("pattern_movements"),
            path=f"{path}.pattern_movements",
            expected_ids=[
                str(row["pattern_id"])
                for row in positive_rows
                if isinstance(row.get("pattern_id"), str)
            ],
            window_size=window_size,
        )
        errors.extend(movement_errors)
        antipattern_movement_rows, movement_errors = _validate_trend_movement_lane(
            value.get("antipattern_movements"),
            path=f"{path}.antipattern_movements",
            expected_ids=[
                str(row["pattern_id"])
                for row in antipattern_rows
                if isinstance(row.get("pattern_id"), str)
            ],
            window_size=window_size,
        )
        errors.extend(movement_errors)
    else:
        for field in ("pattern_movements", "antipattern_movements"):
            if value.get(field) != []:
                errors.append(f"{path}.{field} must be [] when trends are unavailable")

    if pattern_profile.get("score_trend") != score_status:
        errors.append(
            "pattern_profile.score_trend must project trend_analysis.score.status"
        )
    profile_breadth = pattern_profile.get("pattern_breadth")
    if (
        not isinstance(profile_breadth, Mapping)
        or profile_breadth.get("trend") != breadth_status
    ):
        errors.append(
            "pattern_profile.pattern_breadth.trend must project "
            "trend_analysis.breadth.status"
        )

    expected_pattern_drivers = sorted(
        str(row["pattern_id"])
        for row in pattern_rows
        if row.get("movement") in {"increasing", "decreasing"}
        and isinstance(row.get("pattern_id"), str)
    )
    expected_antipattern_drivers = sorted(
        str(row["pattern_id"])
        for row in antipattern_movement_rows
        if row.get("movement") in {"increasing", "decreasing"}
        and isinstance(row.get("pattern_id"), str)
    )
    score_drivers = pattern_profile.get("score_drivers")
    if not isinstance(score_drivers, Mapping):
        errors.append("pattern_profile.score_drivers must be an object")
    else:
        if score_drivers.get("direction") != score_status:
            errors.append(
                "pattern_profile.score_drivers.direction must project "
                "trend_analysis.score.status"
            )
        if score_drivers.get("pattern_drivers") != expected_pattern_drivers:
            errors.append(
                "pattern_profile.score_drivers.pattern_drivers must project "
                "pattern trend movements"
            )
        if score_drivers.get("antipattern_drivers") != expected_antipattern_drivers:
            errors.append(
                "pattern_profile.score_drivers.antipattern_drivers must project "
                "antipattern trend movements"
            )
    return errors


def _validate_v5_policy_fields(
    pattern_profile: Mapping[str, object],
    active_catalog: object,
    *,
    eligible_talk_count: int,
) -> tuple[frozenset[str], str | None, list[str]]:
    errors: list[str] = []
    required_talk_count: int | None = None
    window_size: int | None = None
    classification_schema_version = pattern_profile.get("classification_schema_version")
    if (
        not _is_integer(classification_schema_version)
        or classification_schema_version != CLASSIFICATION_SCHEMA_VERSION
    ):
        errors.append("pattern_profile.classification_schema_version must be 1")
    try:
        stamp = validate_policy_stamp(pattern_profile.get("classification_policy"))
        digest = str(stamp["semantic_sha256"])
        semantic_policy = stamp.get("semantic_policy")
        trend_policy = (
            semantic_policy.get("trends")
            if isinstance(semantic_policy, Mapping)
            else None
        )
        if isinstance(trend_policy, Mapping):
            raw_required = trend_policy.get("minimum_comparable_talks")
            raw_window = trend_policy.get("window_size")
            if _is_integer(raw_required):
                required_talk_count = raw_required
            if _is_integer(raw_window):
                window_size = raw_window
    except (RuntimeError, ValueError) as exc:
        errors.append(f"pattern_profile.classification_policy is invalid: {exc}")
        digest = None
    domains, availability_errors = _validate_availability_v2(
        pattern_profile.get("classification_availability")
    )
    errors.extend(availability_errors)
    positive_rows, lane_errors = _validate_classification_lane(
        pattern_profile.get("pattern_classifications"),
        pattern_profile.get("pattern_usage"),
        lane="pattern_classifications",
        allowed_classifications=_POSITIVE_CLASSIFICATIONS,
        active_catalog=active_catalog,
    )
    errors.extend(lane_errors)
    antipattern_rows, lane_errors = _validate_classification_lane(
        pattern_profile.get("antipattern_classifications"),
        pattern_profile.get("antipattern_frequency"),
        lane="antipattern_classifications",
        allowed_classifications=_ANTIPATTERN_CLASSIFICATIONS,
        active_catalog=active_catalog,
    )
    errors.extend(lane_errors)

    expected_mastery = {
        tier: [
            str(row["pattern_id"])
            for row in positive_rows
            if row.get("classification") == tier
        ]
        for tier in _MASTERY_TIERS
    }
    if pattern_profile.get("mastery_levels") != expected_mastery:
        errors.append(
            "pattern_profile.mastery_levels is not the deterministic projection"
        )
    never_tried = expected_mastery["never_tried"]
    if pattern_profile.get("never_used_patterns") != never_tried:
        errors.append(
            "pattern_profile.never_used_patterns must equal confirmed never_tried IDs"
        )
    underused = sorted(expected_mastery["rare"] + never_tried)
    if pattern_profile.get("underused_patterns") != underused:
        errors.append(
            "pattern_profile.underused_patterns must equal sorted rare + never_tried IDs"
        )
    strengths = sorted(expected_mastery["regular"] + expected_mastery["signature"])
    if pattern_profile.get("strengths") != strengths:
        errors.append(
            "pattern_profile.strengths must equal sorted regular + signature IDs"
        )
    errors.extend(
        _validate_combinations(
            pattern_profile.get("signature_combinations"),
            positive_rows,
            eligible_talk_count=eligible_talk_count,
        )
    )
    if pattern_profile.get("by_mode") != []:
        errors.append(
            "pattern_profile.by_mode must be [] while talk mode assignments are unavailable"
        )

    errors.extend(
        _validate_trend_analysis(
            pattern_profile,
            positive_rows,
            antipattern_rows,
            eligible_talk_count=eligible_talk_count,
            required_talk_count=required_talk_count,
            window_size=window_size,
        )
    )
    if "antipattern_recurrence" not in domains:
        actionable = {
            row.get("classification")
            for row in antipattern_rows
            if row.get("classification") in {"high_frequency", "moderate_frequency"}
        }
        if actionable:
            errors.append(
                "unavailable antipattern recurrence cannot expose actionable tiers"
            )
    return domains, digest, errors


def assess_pattern_profile(
    pattern_profile: object,
    *,
    expected_contract_version: int | None = None,
) -> PatternProfileAssessment:
    """Assess v4 occurrence-only or v5 policy-bound pattern history."""
    errors: list[str] = []
    reason_codes: list[str] = []
    if not isinstance(pattern_profile, Mapping):
        return PatternProfileAssessment(
            current_contract=False,
            catalog_fields_available=False,
            scored_talk_count=None,
            reason_codes=(REASON_INVALID_CONTRACT,),
            errors=("pattern_profile must be an object",),
            contract_version=expected_contract_version,
        )

    inferred_version = (
        5
        if any(
            field in pattern_profile
            for field in _V5_PATTERN_PROFILE_FIELDS - _V4_PATTERN_PROFILE_FIELDS
        )
        else 4
    )
    contract_version = expected_contract_version or inferred_version
    if contract_version not in {4, 5}:
        return PatternProfileAssessment(
            current_contract=False,
            catalog_fields_available=False,
            scored_talk_count=None,
            reason_codes=(REASON_INVALID_CONTRACT,),
            errors=(
                f"unsupported pattern-profile contract version {contract_version!r}",
            ),
            contract_version=contract_version,
        )
    required_fields = (
        _V5_PATTERN_PROFILE_FIELDS
        if contract_version == 5
        else _V4_PATTERN_PROFILE_FIELDS
    )
    missing_fields = sorted(required_fields - set(pattern_profile))
    unknown_fields = sorted(set(pattern_profile) - required_fields, key=str)
    if missing_fields:
        errors.append(
            f"pattern_profile is missing required schema-v{contract_version} fields: "
            f"{', '.join(missing_fields)}"
        )
    if unknown_fields:
        errors.append(
            f"pattern_profile has unknown schema-v{contract_version} fields: "
            f"{', '.join(str(field) for field in unknown_fields)}"
        )
    errors.extend(_validate_common_shape(pattern_profile))

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
            contract_version=contract_version,
        )

    score_comparable_count = baseline["scored_talk_count"]
    assert isinstance(score_comparable_count, int)
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
    if baseline["pattern_scoring_schema_version"] != PATTERN_SCORING_SCHEMA_VERSION:
        errors.append(
            "pattern_profile.pattern_baseline.pattern_scoring_schema_version is "
            f"{baseline['pattern_scoring_schema_version']!r}; expected active schema "
            f"{PATTERN_SCORING_SCHEMA_VERSION}"
        )
        _append_reason(reason_codes, REASON_SCORING_SCHEMA_MISMATCH)

    filenames, filename_errors = _canonical_cohort_filenames(
        pattern_profile.get("baseline_talk_filenames")
    )
    errors.extend(filename_errors)
    if filenames is not None and len(filenames) != eligible_count:
        errors.append(
            "pattern_profile.baseline_talk_filenames length must equal "
            f"pattern_baseline.eligible_talk_count {eligible_count}, got {len(filenames)}"
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
            "pattern_profile.talks_scored must equal pattern_baseline.scored_talk_count "
            f"{score_comparable_count}, got {talks_scored!r}"
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
            f"pattern baseline average {baseline_average!r}, got {profile_average!r}"
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

    domains = frozenset()
    policy_digest = None
    if contract_version == 4:
        errors.extend(_validate_v4_unavailable(pattern_profile))
    elif active_catalog is not None:
        domains, policy_digest, policy_errors = _validate_v5_policy_fields(
            pattern_profile,
            active_catalog,
            eligible_talk_count=eligible_count,
        )
        errors.extend(policy_errors)
        if policy_digest is None:
            _append_reason(reason_codes, REASON_CLASSIFICATION_POLICY_INVALID)

    if errors:
        _append_reason(reason_codes, REASON_INVALID_CONTRACT)
        return PatternProfileAssessment(
            current_contract=False,
            catalog_fields_available=False,
            scored_talk_count=score_comparable_count,
            reason_codes=tuple(reason_codes),
            errors=tuple(errors),
            eligible_talk_count=eligible_count,
            available_classification_domains=frozenset(),
            contract_version=contract_version,
            policy_semantic_sha256=policy_digest,
        )

    if eligible_count == 0:
        _append_reason(reason_codes, REASON_EMPTY_CURRENT_COHORT)
    if contract_version == 4:
        _append_reason(reason_codes, REASON_CLASSIFICATION_POLICY_UNAVAILABLE)
    return PatternProfileAssessment(
        current_contract=True,
        catalog_fields_available=eligible_count > 0,
        scored_talk_count=score_comparable_count,
        reason_codes=tuple(reason_codes),
        errors=(),
        eligible_talk_count=eligible_count,
        classification_fields_available=bool(domains),
        available_classification_domains=domains,
        contract_version=contract_version,
        policy_semantic_sha256=policy_digest,
    )
