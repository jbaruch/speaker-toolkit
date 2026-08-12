#!/usr/bin/env python3
"""Apply a versioned policy to persisted scoring-v5 pattern outcomes.

This is the sole arithmetic owner for speaker-profile pattern classifications,
combinations, and trends. Raw opportunity aggregation remains owned by
``pattern_opportunities.py`` and is deliberately not changed here.

CLI contract
------------
Args:
    vault_root: vault whose optional ``pattern-classification-policy.json`` is
                resolved. An absent override selects the bundled default.

Stdin:
    JSON object with one ``baseline_talks`` array.

Stdout:
    JSON classification bundle suitable for merging into ``pattern_profile``.

Exit codes:
    0   success
    1   invalid arguments, policy, input JSON, or current-generation outcomes
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import pathlib
import re
import stat
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from fractions import Fraction
from typing import Any, NoReturn, TypeGuard, cast


_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_INGRESS_SCRIPTS = (
    pathlib.Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"
)
if str(_INGRESS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_INGRESS_SCRIPTS))

from pattern_opportunities import (  # noqa: E402
    PatternOpportunityError,
    build_pattern_opportunity_rows,
    canonical_talk_outcomes,
)

# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from return_validation import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    load_catalog,
)
from profile_pattern_provenance import absence_provability  # noqa: E402


POLICY_SCHEMA_VERSION = 1
POLICY_STAMP_SCHEMA_VERSION = 1
CLASSIFICATION_SCHEMA_VERSION = 1
CLASSIFICATION_AVAILABILITY_SCHEMA_VERSION = 2
DEFAULT_POLICY_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "references"
    / "pattern-classification-policy-v1.json"
)
OVERRIDE_POLICY_FILENAME = "pattern-classification-policy.json"
MAX_POLICY_BYTES = 64 * 1024
_POLICY_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")

_POLICY_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "policy_version",
        "positive_patterns",
        "antipattern_recurrence",
        "signature_combinations",
        "trends",
    }
)
_POLICY_STAMP_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "policy_version",
        "source",
        "semantic_sha256",
        "semantic_policy",
    }
)
_DOMAIN_NAMES = (
    "mastery_and_novelty",
    "antipattern_recurrence",
    "underuse",
    "signature_combinations",
    "trends",
    "modes",
)


class PatternClassificationError(ValueError):
    """Policy or current-generation evidence cannot authorize classifications."""


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _fail_constant(value: str) -> NoReturn:
    raise PatternClassificationError(f"non-finite JSON number {value!r} is forbidden")


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PatternClassificationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _exact_fields(
    value: object, expected: frozenset[str], *, path: str
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PatternClassificationError(f"{path} must be an object")
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected, key=str)
    if missing or unknown:
        raise PatternClassificationError(
            f"{path} fields are noncanonical; missing={missing}, "
            f"unknown={[str(item) for item in unknown]}"
        )
    return value


def _positive_integer(value: object, *, path: str) -> int:
    if not _is_integer(value) or value < 1:
        raise PatternClassificationError(f"{path} must be a positive integer")
    return value


def _non_negative_integer(value: object, *, path: str) -> int:
    if not _is_integer(value) or value < 0:
        raise PatternClassificationError(f"{path} must be a non-negative integer")
    return value


def _unit_interval(value: object, *, path: str, positive: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or value > 1
        or (positive and value == 0)
    ):
        qualifier = "greater than zero and " if positive else ""
        raise PatternClassificationError(
            f"{path} must be a finite number {qualifier}between zero and one"
        )
    normalized = float(value)
    return 0.0 if normalized == 0 else normalized


def _validate_threshold_rule(
    value: object,
    fields: frozenset[str],
    *,
    path: str,
) -> dict[str, object]:
    rule = _exact_fields(value, fields, path=path)
    normalized: dict[str, object] = {}
    for field in sorted(fields):
        raw = rule[field]
        field_path = f"{path}.{field}"
        if field == "minimum_detections":
            normalized[field] = _positive_integer(raw, path=field_path)
        elif field.startswith("minimum_") and field not in {
            "minimum_lower",
            "minimum_applicable_coverage",
        }:
            normalized[field] = _non_negative_integer(raw, path=field_path)
        elif field == "maximum_detections":
            normalized[field] = _non_negative_integer(raw, path=field_path)
        elif field == "require_complete_evaluation":
            if raw is not True:
                raise PatternClassificationError(f"{field_path} must be true")
            normalized[field] = True
        else:
            normalized[field] = _unit_interval(raw, path=field_path)
    return normalized


def validate_policy(value: object) -> dict[str, object]:
    """Return a normalized strict schema-v1 policy or raise."""
    policy = _exact_fields(value, _POLICY_TOP_LEVEL_FIELDS, path="policy")
    policy_schema_version = policy.get("schema_version")
    if (
        not _is_integer(policy_schema_version)
        or policy_schema_version != POLICY_SCHEMA_VERSION
    ):
        raise PatternClassificationError(
            f"policy.schema_version must be {POLICY_SCHEMA_VERSION}"
        )
    policy_id = policy.get("policy_id")
    if not isinstance(policy_id, str) or _POLICY_ID_RE.fullmatch(policy_id) is None:
        raise PatternClassificationError(
            "policy.policy_id must match [a-z0-9][a-z0-9._-]{0,63}"
        )
    policy_version = _positive_integer(
        policy.get("policy_version"), path="policy.policy_version"
    )

    positive = _exact_fields(
        policy.get("positive_patterns"),
        frozenset({"signature", "regular", "occasional", "rare", "never_tried"}),
        path="policy.positive_patterns",
    )
    normalized_positive: dict[str, dict[str, Any]] = {
        "signature": _validate_threshold_rule(
            positive["signature"],
            frozenset({"minimum_applicable", "minimum_lower"}),
            path="policy.positive_patterns.signature",
        ),
        "regular": _validate_threshold_rule(
            positive["regular"],
            frozenset(
                {
                    "minimum_evaluable",
                    "minimum_applicable_coverage",
                    "minimum_lower",
                    "maximum_upper_exclusive",
                }
            ),
            path="policy.positive_patterns.regular",
        ),
        "occasional": _validate_threshold_rule(
            positive["occasional"],
            frozenset(
                {
                    "minimum_evaluable",
                    "minimum_applicable_coverage",
                    "minimum_lower",
                    "maximum_upper_exclusive",
                }
            ),
            path="policy.positive_patterns.occasional",
        ),
        "rare": _validate_threshold_rule(
            positive["rare"],
            frozenset(
                {
                    "minimum_evaluable",
                    "minimum_applicable_coverage",
                    "minimum_detections",
                    "maximum_upper_exclusive",
                }
            ),
            path="policy.positive_patterns.rare",
        ),
        "never_tried": _validate_threshold_rule(
            positive["never_tried"],
            frozenset(
                {
                    "minimum_applicable",
                    "require_complete_evaluation",
                    "maximum_detections",
                }
            ),
            path="policy.positive_patterns.never_tried",
        ),
    }
    if normalized_positive["never_tried"]["maximum_detections"] != 0:
        raise PatternClassificationError(
            "policy.positive_patterns.never_tried.maximum_detections must be 0"
        )
    for tier in ("signature", "regular", "occasional"):
        if float(normalized_positive[tier]["minimum_lower"]) <= 0:
            raise PatternClassificationError(
                f"policy.positive_patterns.{tier}.minimum_lower must be greater "
                "than zero"
            )

    recurrence = _exact_fields(
        policy.get("antipattern_recurrence"),
        frozenset(
            {"high_frequency", "moderate_frequency", "occasional", "confirmed_none"}
        ),
        path="policy.antipattern_recurrence",
    )
    normalized_recurrence: dict[str, dict[str, Any]] = {
        "high_frequency": _validate_threshold_rule(
            recurrence["high_frequency"],
            frozenset({"minimum_applicable", "minimum_detections", "minimum_lower"}),
            path="policy.antipattern_recurrence.high_frequency",
        ),
        "moderate_frequency": _validate_threshold_rule(
            recurrence["moderate_frequency"],
            frozenset(
                {
                    "minimum_evaluable",
                    "minimum_applicable_coverage",
                    "minimum_detections",
                    "minimum_lower",
                    "maximum_upper_exclusive",
                }
            ),
            path="policy.antipattern_recurrence.moderate_frequency",
        ),
        "occasional": _validate_threshold_rule(
            recurrence["occasional"],
            frozenset(
                {
                    "minimum_evaluable",
                    "minimum_applicable_coverage",
                    "minimum_detections",
                    "maximum_upper_exclusive",
                }
            ),
            path="policy.antipattern_recurrence.occasional",
        ),
        "confirmed_none": _validate_threshold_rule(
            recurrence["confirmed_none"],
            frozenset(
                {
                    "minimum_applicable",
                    "require_complete_evaluation",
                    "maximum_detections",
                }
            ),
            path="policy.antipattern_recurrence.confirmed_none",
        ),
    }
    if normalized_recurrence["confirmed_none"]["maximum_detections"] != 0:
        raise PatternClassificationError(
            "policy.antipattern_recurrence.confirmed_none.maximum_detections must be 0"
        )

    combinations = _exact_fields(
        policy.get("signature_combinations"),
        frozenset(
            {
                "eligible_member_classifications",
                "member_counts",
                "minimum_applicable",
                "minimum_detections",
                "minimum_lower",
                "maximum_results",
            }
        ),
        path="policy.signature_combinations",
    )
    if combinations.get("eligible_member_classifications") != ["regular", "signature"]:
        raise PatternClassificationError(
            "policy.signature_combinations.eligible_member_classifications must "
            "equal ['regular', 'signature']"
        )
    member_counts = combinations.get("member_counts")
    if (
        not isinstance(member_counts, list)
        or any(not _is_integer(item) for item in member_counts)
        or member_counts != [2, 3]
    ):
        raise PatternClassificationError(
            "policy.signature_combinations.member_counts must equal the integer "
            "list [2, 3]"
        )
    normalized_combinations: dict[str, object] = {
        "eligible_member_classifications": ["regular", "signature"],
        "member_counts": [2, 3],
        "minimum_applicable": _positive_integer(
            combinations.get("minimum_applicable"),
            path="policy.signature_combinations.minimum_applicable",
        ),
        "minimum_detections": _positive_integer(
            combinations.get("minimum_detections"),
            path="policy.signature_combinations.minimum_detections",
        ),
        "minimum_lower": _unit_interval(
            combinations.get("minimum_lower"),
            path="policy.signature_combinations.minimum_lower",
            positive=True,
        ),
        "maximum_results": _positive_integer(
            combinations.get("maximum_results"),
            path="policy.signature_combinations.maximum_results",
        ),
    }
    if normalized_combinations["maximum_results"] != 10:
        raise PatternClassificationError(
            "schema-v1 signature combinations require maximum_results=10"
        )

    trends = _exact_fields(
        policy.get("trends"),
        frozenset(
            {
                "minimum_comparable_talks",
                "window_size",
                "score_delta",
                "breadth_delta",
                "pattern_movement_delta",
            }
        ),
        path="policy.trends",
    )
    minimum_comparable = _positive_integer(
        trends.get("minimum_comparable_talks"),
        path="policy.trends.minimum_comparable_talks",
    )
    window_size = _positive_integer(
        trends.get("window_size"), path="policy.trends.window_size"
    )
    if minimum_comparable != 10 or window_size != 5:
        raise PatternClassificationError(
            "schema-v1 trend windows require minimum_comparable_talks=10 and "
            "window_size=5"
        )
    normalized_trends: dict[str, object] = {
        "minimum_comparable_talks": minimum_comparable,
        "window_size": window_size,
        "score_delta": _unit_interval(
            trends.get("score_delta"), path="policy.trends.score_delta", positive=True
        ),
        "breadth_delta": _unit_interval(
            trends.get("breadth_delta"),
            path="policy.trends.breadth_delta",
            positive=True,
        ),
        "pattern_movement_delta": _unit_interval(
            trends.get("pattern_movement_delta"),
            path="policy.trends.pattern_movement_delta",
            positive=True,
        ),
    }

    rare_upper = float(normalized_positive["rare"]["maximum_upper_exclusive"])
    occasional_lower = float(normalized_positive["occasional"]["minimum_lower"])
    occasional_upper = float(
        normalized_positive["occasional"]["maximum_upper_exclusive"]
    )
    regular_lower = float(normalized_positive["regular"]["minimum_lower"])
    regular_upper = float(normalized_positive["regular"]["maximum_upper_exclusive"])
    signature_lower = float(normalized_positive["signature"]["minimum_lower"])
    if not (
        rare_upper <= occasional_lower
        and occasional_lower < occasional_upper <= regular_lower
        and regular_lower < regular_upper <= signature_lower
    ):
        raise PatternClassificationError(
            "policy.positive_patterns bands must be ordered without overlap"
        )

    occasional_recurrence_upper = float(
        normalized_recurrence["occasional"]["maximum_upper_exclusive"]
    )
    moderate_lower = float(normalized_recurrence["moderate_frequency"]["minimum_lower"])
    moderate_upper = float(
        normalized_recurrence["moderate_frequency"]["maximum_upper_exclusive"]
    )
    high_lower = float(normalized_recurrence["high_frequency"]["minimum_lower"])
    if not (
        occasional_recurrence_upper <= moderate_lower
        and moderate_lower < moderate_upper <= high_lower
    ):
        raise PatternClassificationError(
            "policy.antipattern_recurrence bands must be ordered without overlap"
        )

    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "positive_patterns": normalized_positive,
        "antipattern_recurrence": normalized_recurrence,
        "signature_combinations": normalized_combinations,
        "trends": normalized_trends,
    }


def _decode_policy_bytes(raw: bytes, *, path: pathlib.Path) -> dict[str, object]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatternClassificationError(f"{path}: policy is not UTF-8: {exc}") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_fail_constant,
        )
    except (json.JSONDecodeError, PatternClassificationError) as exc:
        raise PatternClassificationError(f"{path}: invalid policy JSON: {exc}") from exc
    return validate_policy(value)


def _read_policy(path: pathlib.Path) -> dict[str, object]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PatternClassificationError(
            f"cannot inspect policy {path}: {exc}"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise PatternClassificationError(f"policy {path} must be a regular file")
    if metadata.st_size > MAX_POLICY_BYTES:
        raise PatternClassificationError(
            f"policy {path} exceeds the {MAX_POLICY_BYTES}-byte limit"
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PatternClassificationError(f"cannot read policy {path}: {exc}") from exc
    if len(raw) > MAX_POLICY_BYTES:
        raise PatternClassificationError(
            f"policy {path} exceeds the {MAX_POLICY_BYTES}-byte limit"
        )
    return _decode_policy_bytes(raw, path=path)


def canonical_policy_sha256(policy: object) -> str:
    """Hash canonical semantic policy JSON, independent of source formatting."""
    normalized = validate_policy(policy)
    encoded = json.dumps(
        normalized,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_classification_policy(
    vault_root: pathlib.Path,
    *,
    bundled_policy_path: pathlib.Path = DEFAULT_POLICY_PATH,
) -> dict[str, object]:
    """Resolve a strict vault override or the bundled default without prompting."""
    if not isinstance(vault_root, pathlib.Path):
        raise PatternClassificationError("vault_root must be a pathlib.Path")
    override_path = vault_root / OVERRIDE_POLICY_FILENAME
    try:
        override_exists = override_path.exists() or override_path.is_symlink()
    except OSError as exc:
        raise PatternClassificationError(
            f"cannot inspect policy override {override_path}: {exc}"
        ) from exc
    if override_exists:
        policy = _read_policy(override_path)
        source = "vault_override"
    else:
        policy = _read_policy(bundled_policy_path)
        source = "bundled_default"
    return {
        "schema_version": POLICY_STAMP_SCHEMA_VERSION,
        "policy_id": policy["policy_id"],
        "policy_version": policy["policy_version"],
        "source": source,
        "semantic_sha256": canonical_policy_sha256(policy),
        "semantic_policy": policy,
    }


def validate_policy_stamp(value: object) -> dict[str, object]:
    """Validate a self-contained profile policy stamp and its semantic digest."""
    stamp = _exact_fields(value, _POLICY_STAMP_FIELDS, path="classification_policy")
    stamp_schema_version = stamp.get("schema_version")
    if (
        not _is_integer(stamp_schema_version)
        or stamp_schema_version != POLICY_STAMP_SCHEMA_VERSION
    ):
        raise PatternClassificationError(
            f"classification_policy.schema_version must be {POLICY_STAMP_SCHEMA_VERSION}"
        )
    source = stamp.get("source")
    if source not in {"bundled_default", "vault_override"}:
        raise PatternClassificationError(
            "classification_policy.source must be bundled_default or vault_override"
        )
    policy = validate_policy(stamp.get("semantic_policy"))
    if stamp.get("policy_id") != policy["policy_id"]:
        raise PatternClassificationError(
            "classification_policy.policy_id does not match semantic_policy"
        )
    stamp_policy_version = stamp.get("policy_version")
    if not _is_integer(stamp_policy_version) or stamp_policy_version < 1:
        raise PatternClassificationError(
            "classification_policy.policy_version must be a positive integer"
        )
    if stamp_policy_version != policy["policy_version"]:
        raise PatternClassificationError(
            "classification_policy.policy_version does not match semantic_policy"
        )
    digest = stamp.get("semantic_sha256")
    if not isinstance(digest, str) or _HEX64_RE.fullmatch(digest) is None:
        raise PatternClassificationError(
            "classification_policy.semantic_sha256 must be lowercase SHA-256 hex"
        )
    expected_digest = canonical_policy_sha256(policy)
    if digest != expected_digest:
        raise PatternClassificationError(
            "classification_policy.semantic_sha256 does not match semantic_policy"
        )
    return {
        "schema_version": POLICY_STAMP_SCHEMA_VERSION,
        "policy_id": policy["policy_id"],
        "policy_version": policy["policy_version"],
        "source": source,
        "semantic_sha256": expected_digest,
        "semantic_policy": policy,
    }


def _evidence_bounds(row: Mapping[str, object]) -> dict[str, Any]:
    required = (
        "eligible_cohort_count",
        "not_applicable_count",
        "evaluable_count",
        "detected_count",
        "unevaluable_count",
    )
    counts: dict[str, int] = {}
    for field in required:
        raw = row.get(field)
        if not _is_integer(raw) or raw < 0:
            raise PatternClassificationError(
                f"opportunity row {row.get('pattern_id')!r}.{field} must be a "
                "non-negative integer"
            )
        counts[field] = raw
    applicable = counts["eligible_cohort_count"] - counts["not_applicable_count"]
    evaluable = counts["evaluable_count"]
    detected = counts["detected_count"]
    unevaluable = counts["unevaluable_count"]
    if applicable < 0 or evaluable + unevaluable != applicable or detected > evaluable:
        raise PatternClassificationError(
            f"opportunity row {row.get('pattern_id')!r} has inconsistent A/E/D/U counts"
        )
    if applicable == 0:
        applicable_coverage = lower = upper = None
    else:
        applicable_coverage = evaluable / applicable
        lower = detected / applicable
        upper = (detected + unevaluable) / applicable
    return {
        "applicable_count": applicable,
        "evaluable_count": evaluable,
        "detected_count": detected,
        "unevaluable_count": unevaluable,
        "applicable_coverage": applicable_coverage,
        "lower": lower,
        "upper": upper,
    }


def _observation_status(
    evidence: Mapping[str, Any], *, absence_conclusion_capable: bool
) -> str:
    applicable = int(evidence["applicable_count"])
    detected = int(evidence["detected_count"])
    evaluable = int(evidence["evaluable_count"])
    if applicable == 0:
        return "unavailable"
    if detected > 0:
        return "observed"
    if absence_conclusion_capable and evaluable == applicable:
        return "confirmed_absent"
    return "not_yet_observed"


def _insufficiency_reasons(
    evidence: Mapping[str, Any],
    *,
    minimum_applicable: int,
    minimum_evaluable: int,
    minimum_coverage: float,
) -> list[str]:
    applicable = int(evidence["applicable_count"])
    evaluable = int(evidence["evaluable_count"])
    coverage = evidence["applicable_coverage"]
    reasons: list[str] = []
    if applicable == 0:
        return ["no_applicable_talks"]
    if applicable < minimum_applicable:
        reasons.append("insufficient_applicable_sample")
    if evaluable < minimum_evaluable:
        reasons.append("insufficient_evaluable_sample")
    if isinstance(coverage, (int, float)) and coverage < minimum_coverage:
        reasons.append("insufficient_applicable_coverage")
    return reasons


def _classify_positive(
    row: Mapping[str, object],
    *,
    absence_conclusion_capable: bool,
    policy: Mapping[str, Any],
) -> dict[str, object]:
    evidence = _evidence_bounds(row)
    pattern_id = row.get("pattern_id")
    if not isinstance(pattern_id, str) or not pattern_id:
        raise PatternClassificationError(
            "positive opportunity row has invalid pattern_id"
        )
    rules = policy["positive_patterns"]
    assert isinstance(rules, Mapping)
    signature = rules["signature"]
    regular = rules["regular"]
    occasional = rules["occasional"]
    rare = rules["rare"]
    never_tried = rules["never_tried"]
    assert all(
        isinstance(rule, Mapping)
        for rule in (signature, regular, occasional, rare, never_tried)
    )
    applicable = int(evidence["applicable_count"])
    evaluable = int(evidence["evaluable_count"])
    detected = int(evidence["detected_count"])
    coverage = evidence["applicable_coverage"]
    lower = evidence["lower"]
    upper = evidence["upper"]
    classification = "unclassified"
    reason_codes: list[str] = []

    if applicable == 0:
        reason_codes = ["no_applicable_talks"]
    elif (
        detected > 0
        and applicable >= int(signature["minimum_applicable"])
        and isinstance(lower, (int, float))
        and lower >= float(signature["minimum_lower"])
    ):
        classification = "signature"
        reason_codes = ["meets_signature_thresholds"]
    elif (
        detected > 0
        and evaluable >= int(regular["minimum_evaluable"])
        and isinstance(coverage, (int, float))
        and coverage >= float(regular["minimum_applicable_coverage"])
        and isinstance(lower, (int, float))
        and lower >= float(regular["minimum_lower"])
        and isinstance(upper, (int, float))
        and upper < float(regular["maximum_upper_exclusive"])
    ):
        classification = "regular"
        reason_codes = ["meets_regular_thresholds"]
    elif (
        detected > 0
        and evaluable >= int(occasional["minimum_evaluable"])
        and isinstance(coverage, (int, float))
        and coverage >= float(occasional["minimum_applicable_coverage"])
        and isinstance(lower, (int, float))
        and lower >= float(occasional["minimum_lower"])
        and isinstance(upper, (int, float))
        and upper < float(occasional["maximum_upper_exclusive"])
    ):
        classification = "occasional"
        reason_codes = ["meets_occasional_thresholds"]
    elif (
        evaluable >= int(rare["minimum_evaluable"])
        and isinstance(coverage, (int, float))
        and coverage >= float(rare["minimum_applicable_coverage"])
        and detected >= int(rare["minimum_detections"])
        and isinstance(upper, (int, float))
        and upper < float(rare["maximum_upper_exclusive"])
    ):
        classification = "rare"
        reason_codes = ["meets_rare_thresholds"]
    elif (
        absence_conclusion_capable
        and applicable >= int(never_tried["minimum_applicable"])
        and evaluable == applicable
        and detected <= int(never_tried["maximum_detections"])
    ):
        classification = "never_tried"
        reason_codes = ["complete_absence_meets_never_tried_thresholds"]
    elif detected == 0 and not (absence_conclusion_capable and evaluable == applicable):
        classification = "not_yet_observed"
        reason_codes = _insufficiency_reasons(
            evidence,
            minimum_applicable=min(
                int(signature["minimum_applicable"]),
                int(never_tried["minimum_applicable"]),
            ),
            minimum_evaluable=min(
                int(regular["minimum_evaluable"]),
                int(occasional["minimum_evaluable"]),
                int(rare["minimum_evaluable"]),
            ),
            minimum_coverage=min(
                float(regular["minimum_applicable_coverage"]),
                float(occasional["minimum_applicable_coverage"]),
                float(rare["minimum_applicable_coverage"]),
            ),
        )
        reason_codes.append(
            "absence_not_supported_by_catalog"
            if not absence_conclusion_capable
            else "incomplete_absence_evidence"
        )
    else:
        reason_codes = _insufficiency_reasons(
            evidence,
            minimum_applicable=int(signature["minimum_applicable"]),
            minimum_evaluable=min(
                int(regular["minimum_evaluable"]),
                int(occasional["minimum_evaluable"]),
                int(rare["minimum_evaluable"]),
            ),
            minimum_coverage=min(
                float(regular["minimum_applicable_coverage"]),
                float(occasional["minimum_applicable_coverage"]),
                float(rare["minimum_applicable_coverage"]),
            ),
        )
        if int(evidence["unevaluable_count"]) > 0:
            reason_codes.append("uncertain_interval_crosses_thresholds")
        if not reason_codes:
            reason_codes.append("no_positive_tier_matched")

    return {
        "pattern_id": pattern_id,
        "classification": classification,
        "observation_status": _observation_status(
            evidence, absence_conclusion_capable=absence_conclusion_capable
        ),
        "absence_conclusion_capable": absence_conclusion_capable,
        "evidence": evidence,
        "reason_codes": reason_codes,
    }


def _classify_antipattern(
    row: Mapping[str, object],
    *,
    absence_conclusion_capable: bool,
    policy: Mapping[str, Any],
) -> dict[str, object]:
    evidence = _evidence_bounds(row)
    pattern_id = row.get("pattern_id")
    if not isinstance(pattern_id, str) or not pattern_id:
        raise PatternClassificationError(
            "antipattern opportunity row has invalid pattern_id"
        )
    rules = policy["antipattern_recurrence"]
    assert isinstance(rules, Mapping)
    high = rules["high_frequency"]
    moderate = rules["moderate_frequency"]
    occasional = rules["occasional"]
    confirmed_none = rules["confirmed_none"]
    assert all(
        isinstance(rule, Mapping)
        for rule in (high, moderate, occasional, confirmed_none)
    )
    applicable = int(evidence["applicable_count"])
    evaluable = int(evidence["evaluable_count"])
    detected = int(evidence["detected_count"])
    coverage = evidence["applicable_coverage"]
    lower = evidence["lower"]
    upper = evidence["upper"]
    classification = "unclassified"
    reason_codes: list[str] = []

    if applicable == 0:
        reason_codes = ["no_applicable_talks"]
    elif (
        applicable >= int(high["minimum_applicable"])
        and detected >= int(high["minimum_detections"])
        and isinstance(lower, (int, float))
        and lower >= float(high["minimum_lower"])
    ):
        classification = "high_frequency"
        reason_codes = ["meets_high_frequency_thresholds"]
    elif (
        evaluable >= int(moderate["minimum_evaluable"])
        and isinstance(coverage, (int, float))
        and coverage >= float(moderate["minimum_applicable_coverage"])
        and detected >= int(moderate["minimum_detections"])
        and isinstance(lower, (int, float))
        and lower >= float(moderate["minimum_lower"])
        and isinstance(upper, (int, float))
        and upper < float(moderate["maximum_upper_exclusive"])
    ):
        classification = "moderate_frequency"
        reason_codes = ["meets_moderate_frequency_thresholds"]
    elif (
        evaluable >= int(occasional["minimum_evaluable"])
        and isinstance(coverage, (int, float))
        and coverage >= float(occasional["minimum_applicable_coverage"])
        and detected >= int(occasional["minimum_detections"])
        and isinstance(upper, (int, float))
        and upper < float(occasional["maximum_upper_exclusive"])
    ):
        classification = "occasional"
        reason_codes = ["meets_occasional_frequency_thresholds"]
    elif (
        absence_conclusion_capable
        and applicable >= int(confirmed_none["minimum_applicable"])
        and evaluable == applicable
        and detected <= int(confirmed_none["maximum_detections"])
    ):
        classification = "confirmed_none"
        reason_codes = ["complete_absence_meets_confirmed_none_thresholds"]
    else:
        reason_codes = _insufficiency_reasons(
            evidence,
            minimum_applicable=min(
                int(high["minimum_applicable"]),
                int(confirmed_none["minimum_applicable"]),
            ),
            minimum_evaluable=min(
                int(moderate["minimum_evaluable"]),
                int(occasional["minimum_evaluable"]),
            ),
            minimum_coverage=min(
                float(moderate["minimum_applicable_coverage"]),
                float(occasional["minimum_applicable_coverage"]),
            ),
        )
        if detected == 0 and not (
            absence_conclusion_capable and evaluable == applicable
        ):
            reason_codes.append(
                "absence_not_supported_by_catalog"
                if not absence_conclusion_capable
                else "incomplete_absence_evidence"
            )
        elif int(evidence["unevaluable_count"]) > 0:
            reason_codes.append("uncertain_interval_crosses_thresholds")
        if not reason_codes:
            reason_codes.append("no_recurrence_tier_matched")

    return {
        "pattern_id": pattern_id,
        "classification": classification,
        "observation_status": _observation_status(
            evidence, absence_conclusion_capable=absence_conclusion_capable
        ),
        "absence_conclusion_capable": absence_conclusion_capable,
        "evidence": evidence,
        "reason_codes": reason_codes,
    }


def _joint_outcome(member_outcomes: Sequence[str]) -> str:
    if all(outcome == "detected" for outcome in member_outcomes):
        return "detected"
    if all(outcome in {"detected", "undetected"} for outcome in member_outcomes):
        return "undetected"
    if any(outcome == "not_applicable" for outcome in member_outcomes):
        return "not_applicable"
    return "not_evaluable"


def _combination_rows(
    talks: Sequence[Mapping[str, object]],
    outcomes_by_talk: Sequence[Mapping[str, str]],
    positive_classifications: Sequence[Mapping[str, object]],
    *,
    policy: Mapping[str, Any],
) -> list[dict[str, object]]:
    combination_policy = policy["signature_combinations"]
    assert isinstance(combination_policy, Mapping)
    eligible_classes = set(combination_policy["eligible_member_classifications"])
    member_ids = sorted(
        str(item["pattern_id"])
        for item in positive_classifications
        if item.get("classification") in eligible_classes
    )
    candidates: list[dict[str, object]] = []
    for member_count in combination_policy["member_counts"]:
        assert isinstance(member_count, int)
        for members in itertools.combinations(member_ids, member_count):
            counts: Counter[str] = Counter()
            for outcomes in outcomes_by_talk:
                counts[_joint_outcome([outcomes[member] for member in members])] += 1
            opportunity = {
                "pattern_id": "+".join(members),
                "eligible_cohort_count": len(talks),
                "not_applicable_count": counts["not_applicable"],
                "evaluable_count": counts["detected"] + counts["undetected"],
                "detected_count": counts["detected"],
                "unevaluable_count": counts["not_evaluable"],
            }
            evidence = _evidence_bounds(opportunity)
            lower = evidence["lower"]
            if (
                int(evidence["applicable_count"])
                >= int(combination_policy["minimum_applicable"])
                and int(evidence["detected_count"])
                >= int(combination_policy["minimum_detections"])
                and isinstance(lower, (int, float))
                and lower >= float(combination_policy["minimum_lower"])
            ):
                candidates.append(
                    {
                        "combination_id": "+".join(members),
                        "pattern_ids": list(members),
                        "evidence": evidence,
                        "reason_codes": ["meets_signature_combination_thresholds"],
                    }
                )

    def candidate_sort_key(
        item: Mapping[str, object],
    ) -> tuple[float, int, tuple[str, ...]]:
        evidence = item.get("evidence")
        pattern_ids = item.get("pattern_ids")
        if not isinstance(evidence, Mapping) or not isinstance(pattern_ids, list):
            raise PatternClassificationError(
                "classifier produced an invalid signature-combination row"
            )
        lower = evidence.get("lower")
        detected = evidence.get("detected_count")
        if (
            isinstance(lower, bool)
            or not isinstance(lower, (int, float))
            or not _is_integer(detected)
            or any(not isinstance(pattern_id, str) for pattern_id in pattern_ids)
        ):
            raise PatternClassificationError(
                "classifier produced invalid signature-combination evidence"
            )
        return -float(lower), -detected, tuple(pattern_ids)

    candidates.sort(key=candidate_sort_key)
    return candidates[: int(combination_policy["maximum_results"])]


def _valid_talk_date(talk: Mapping[str, object]) -> date | None:
    raw = talk.get("date")
    if not isinstance(raw, str) or _DATE_RE.fullmatch(raw) is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _talk_filename(talk: Mapping[str, object]) -> str:
    filename = talk.get("filename")
    if not isinstance(filename, str) or not filename:
        raise PatternClassificationError("baseline talk has no filename")
    return filename


def _talk_score(talk: Mapping[str, object]) -> int:
    score = talk.get("pattern_score")
    observations = talk.get("pattern_observations")
    observed_score = (
        observations.get("pattern_score") if isinstance(observations, Mapping) else None
    )
    if not _is_integer(score):
        raise PatternClassificationError(
            f"{_talk_filename(talk)}: pattern_score must be an integer"
        )
    if not _is_integer(observed_score) or observed_score != score:
        raise PatternClassificationError(
            f"{_talk_filename(talk)}: flattened and observed pattern_score must match"
        )
    return score


def _talk_identity(talk: Mapping[str, object]) -> str | None:
    observations = talk.get("pattern_observations")
    raw = (
        observations.get("opportunity_coverage_identity")
        if isinstance(observations, Mapping)
        else None
    )
    return raw if isinstance(raw, str) and _HEX64_RE.fullmatch(raw) else None


def _window_bounds(outcomes: Sequence[str]) -> dict[str, Any]:
    counts = Counter(outcomes)
    opportunity = {
        "pattern_id": "trend-window",
        "eligible_cohort_count": len(outcomes),
        "not_applicable_count": counts["not_applicable"],
        "evaluable_count": counts["detected"] + counts["undetected"],
        "detected_count": counts["detected"],
        "unevaluable_count": counts["not_evaluable"],
    }
    return _evidence_bounds(opportunity)


def _movement(
    prior: Mapping[str, Any],
    recent: Mapping[str, Any],
    *,
    threshold: float,
    expected_applicable: int = 5,
) -> tuple[str, list[str]]:
    if (
        int(prior["applicable_count"]) != expected_applicable
        or int(recent["applicable_count"]) != expected_applicable
    ):
        return "unavailable", ["incomplete_window_applicability"]
    prior_lower = prior["lower"]
    prior_upper = prior["upper"]
    recent_lower = recent["lower"]
    recent_upper = recent["upper"]
    if not all(
        isinstance(value, (int, float))
        for value in (prior_lower, prior_upper, recent_lower, recent_upper)
    ):
        return "unavailable", ["window_bounds_unavailable"]
    exact_threshold = Fraction(str(threshold))
    minimum_delta = Fraction(str(recent_lower)) - Fraction(str(prior_upper))
    maximum_delta = Fraction(str(recent_upper)) - Fraction(str(prior_lower))
    if minimum_delta >= exact_threshold:
        return "increasing", ["conservative_interval_increase"]
    if maximum_delta <= -exact_threshold:
        return "decreasing", ["conservative_interval_decrease"]
    if maximum_delta < exact_threshold and minimum_delta > -exact_threshold:
        return "stable", ["conservative_interval_stable"]
    return "indeterminate", ["uncertainty_spans_movement_threshold"]


def _trend_analysis(
    talks: Sequence[Mapping[str, object]],
    outcomes_by_talk: Sequence[Mapping[str, str]],
    *,
    pattern_ids: Sequence[str],
    antipattern_ids: Sequence[str],
    policy: Mapping[str, Any],
) -> dict[str, object]:
    trend_policy = policy["trends"]
    assert isinstance(trend_policy, Mapping)
    dated: list[tuple[date, str, Mapping[str, object], Mapping[str, str]]] = []
    invalid_date_filenames: list[str] = []
    for talk, outcomes in zip(talks, outcomes_by_talk, strict=True):
        filename = _talk_filename(talk)
        talk_date = _valid_talk_date(talk)
        if talk_date is None:
            invalid_date_filenames.append(filename)
        else:
            dated.append((talk_date, filename, talk, outcomes))
    dated.sort(key=lambda item: (item[0], item[1]))
    required = int(trend_policy["minimum_comparable_talks"])
    sample: dict[str, object] = {
        "required_talk_count": required,
        "valid_date_talk_count": len(dated),
        "invalid_date_filenames": sorted(invalid_date_filenames),
        "selected_filenames": [],
        "opportunity_coverage_identity": None,
    }
    if len(dated) < required:
        return {
            "status": "unavailable",
            "reason_codes": ["insufficient_valid_date_sample"],
            "sample": sample,
            "score": {
                "status": "unavailable",
                "prior_average": None,
                "recent_average": None,
                "delta": None,
            },
            "breadth": {
                "status": "unavailable",
                "prior_average": None,
                "recent_average": None,
                "delta": None,
            },
            "pattern_movements": [],
            "antipattern_movements": [],
        }
    selected = dated[-required:]
    sample["selected_filenames"] = [item[1] for item in selected]
    identities = {_talk_identity(item[2]) for item in selected}
    if None in identities:
        return {
            "status": "unavailable",
            "reason_codes": ["opportunity_identity_unavailable"],
            "sample": sample,
            "score": {
                "status": "unavailable",
                "prior_average": None,
                "recent_average": None,
                "delta": None,
            },
            "breadth": {
                "status": "unavailable",
                "prior_average": None,
                "recent_average": None,
                "delta": None,
            },
            "pattern_movements": [],
            "antipattern_movements": [],
        }
    if len(identities) != 1:
        return {
            "status": "unavailable",
            "reason_codes": ["incomparable_opportunity_identities"],
            "sample": sample,
            "score": {
                "status": "unavailable",
                "prior_average": None,
                "recent_average": None,
                "delta": None,
            },
            "breadth": {
                "status": "unavailable",
                "prior_average": None,
                "recent_average": None,
                "delta": None,
            },
            "pattern_movements": [],
            "antipattern_movements": [],
        }
    identity = next(iter(identities))
    assert isinstance(identity, str)
    sample["opportunity_coverage_identity"] = identity
    if not any(
        outcome in {"detected", "undetected"}
        for _, _, _, outcomes in selected
        for outcome in outcomes.values()
    ):
        return {
            "status": "unavailable",
            "reason_codes": ["no_evaluable_pattern_opportunities"],
            "sample": sample,
            "score": {
                "status": "unavailable",
                "prior_average": None,
                "recent_average": None,
                "delta": None,
            },
            "breadth": {
                "status": "unavailable",
                "prior_average": None,
                "recent_average": None,
                "delta": None,
            },
            "pattern_movements": [],
            "antipattern_movements": [],
        }
    window_size = int(trend_policy["window_size"])
    prior = selected[:window_size]
    recent = selected[window_size:]
    prior_scores = [_talk_score(item[2]) for item in prior]
    recent_scores = [_talk_score(item[2]) for item in recent]
    prior_breadth = [
        sum(item[3][pattern_id] == "detected" for pattern_id in pattern_ids)
        for item in prior
    ]
    recent_breadth = [
        sum(item[3][pattern_id] == "detected" for pattern_id in pattern_ids)
        for item in recent
    ]

    def metric(
        values_prior: Sequence[int],
        values_recent: Sequence[int],
        threshold: float,
        improving: str,
        declining: str,
    ) -> dict[str, object]:
        exact_prior = Fraction(sum(values_prior), len(values_prior))
        exact_recent = Fraction(sum(values_recent), len(values_recent))
        exact_delta = exact_recent - exact_prior
        exact_threshold = Fraction(str(threshold))
        prior_average = float(exact_prior)
        recent_average = float(exact_recent)
        delta = float(exact_delta)
        status = (
            improving
            if exact_delta >= exact_threshold
            else declining
            if exact_delta <= -exact_threshold
            else "stable"
        )
        return {
            "status": status,
            "prior_average": prior_average,
            "recent_average": recent_average,
            "delta": delta,
        }

    score = metric(
        prior_scores,
        recent_scores,
        float(trend_policy["score_delta"]),
        "improving",
        "declining",
    )
    breadth = metric(
        prior_breadth,
        recent_breadth,
        float(trend_policy["breadth_delta"]),
        "widening",
        "narrowing",
    )
    movement_threshold = float(trend_policy["pattern_movement_delta"])

    def movements(ids: Sequence[str]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for pattern_id in ids:
            prior_bounds = _window_bounds([item[3][pattern_id] for item in prior])
            recent_bounds = _window_bounds([item[3][pattern_id] for item in recent])
            movement, reasons = _movement(
                prior_bounds,
                recent_bounds,
                threshold=movement_threshold,
                expected_applicable=window_size,
            )
            rows.append(
                {
                    "pattern_id": pattern_id,
                    "movement": movement,
                    "prior_evidence": prior_bounds,
                    "recent_evidence": recent_bounds,
                    "reason_codes": reasons,
                }
            )
        return rows

    return {
        "status": "available",
        "reason_codes": [],
        "sample": sample,
        "score": score,
        "breadth": breadth,
        "pattern_movements": movements(pattern_ids),
        "antipattern_movements": movements(antipattern_ids),
    }


def _domain(status: str, reason_codes: Sequence[str]) -> dict[str, object]:
    return {"status": status, "reason_codes": list(reason_codes)}


def classify_pattern_profile(
    talks: object,
    policy_stamp: object,
    *,
    catalog: Any | None = None,
) -> dict[str, object]:
    """Return all deterministic policy-derived profile fields."""
    if isinstance(talks, (str, bytes, Mapping)) or not isinstance(talks, Sequence):
        raise PatternClassificationError("baseline_talks must be an array")
    canonical_talks: list[Mapping[str, object]] = []
    for index, talk in enumerate(talks):
        if not isinstance(talk, Mapping):
            raise PatternClassificationError(
                f"baseline_talks[{index}] must be an object"
            )
        canonical_talks.append(talk)
    stamp = validate_policy_stamp(policy_stamp)
    policy = cast(Mapping[str, Any], stamp["semantic_policy"])
    resolved_catalog = catalog or load_catalog()
    entries = getattr(resolved_catalog, "entries", None)
    if not isinstance(entries, Mapping):
        raise PatternClassificationError("active catalog has no entries mapping")
    try:
        opportunities = build_pattern_opportunity_rows(
            canonical_talks, catalog=resolved_catalog
        )
        outcomes_by_talk = [
            canonical_talk_outcomes(
                cast(Mapping[object, object], talk), catalog=resolved_catalog
            )
            for talk in canonical_talks
        ]
    except PatternOpportunityError as exc:
        raise PatternClassificationError(str(exc)) from exc
    raw_positive = opportunities.get("pattern_usage")
    raw_antipattern = opportunities.get("antipattern_frequency")
    if not isinstance(raw_positive, list) or not isinstance(raw_antipattern, list):
        raise PatternClassificationError(
            "raw opportunity builder returned invalid lanes"
        )

    def absence_capable(pattern_id: str) -> bool:
        entry = entries.get(pattern_id)
        if entry is None:
            raise PatternClassificationError(
                f"active catalog is missing opportunity ID {pattern_id!r}"
            )
        return getattr(entry, "absence_evaluable_from", None) is not None

    positive_classifications = [
        _classify_positive(
            row,
            absence_conclusion_capable=absence_capable(str(row["pattern_id"])),
            policy=policy,
        )
        for row in raw_positive
    ]
    antipattern_classifications = [
        _classify_antipattern(
            row,
            absence_conclusion_capable=absence_capable(str(row["pattern_id"])),
            policy=policy,
        )
        for row in raw_antipattern
    ]
    combinations = _combination_rows(
        canonical_talks,
        outcomes_by_talk,
        positive_classifications,
        policy=policy,
    )
    positive_ids = [str(row["pattern_id"]) for row in raw_positive]
    antipattern_ids = [str(row["pattern_id"]) for row in raw_antipattern]
    trend_analysis = _trend_analysis(
        canonical_talks,
        outcomes_by_talk,
        pattern_ids=positive_ids,
        antipattern_ids=antipattern_ids,
        policy=policy,
    )
    trend_status = str(trend_analysis["status"])
    trend_reasons = trend_analysis["reason_codes"]
    assert isinstance(trend_reasons, list)
    availability = {
        "schema_version": CLASSIFICATION_AVAILABILITY_SCHEMA_VERSION,
        "mastery_and_novelty": _domain("available", []),
        "antipattern_recurrence": _domain("available", []),
        "underuse": _domain("available", []),
        "signature_combinations": _domain("available", []),
        "trends": _domain(trend_status, trend_reasons),
        "modes": _domain("unavailable", ["talk_mode_assignments_unavailable"]),
    }
    mastery_levels = {
        tier: [
            str(row["pattern_id"])
            for row in positive_classifications
            if row["classification"] == tier
        ]
        for tier in ("signature", "regular", "occasional", "rare", "never_tried")
    }
    never_tried_ids = list(mastery_levels["never_tried"])
    underused_ids = sorted(mastery_levels["rare"] + never_tried_ids)
    strength_ids = sorted(mastery_levels["signature"] + mastery_levels["regular"])
    all_positive_breadths = [
        sum(outcomes[pattern_id] == "detected" for pattern_id in positive_ids)
        for outcomes in outcomes_by_talk
    ]
    average_breadth = (
        None
        if not all_positive_breadths
        else math.fsum(all_positive_breadths) / len(all_positive_breadths)
    )
    pattern_movements = trend_analysis.get("pattern_movements", [])
    antipattern_movements = trend_analysis.get("antipattern_movements", [])
    assert isinstance(pattern_movements, list) and isinstance(
        antipattern_movements, list
    )
    pattern_drivers = sorted(
        str(row["pattern_id"])
        for row in pattern_movements
        if isinstance(row, Mapping)
        and row.get("movement") in {"increasing", "decreasing"}
    )
    antipattern_drivers = sorted(
        str(row["pattern_id"])
        for row in antipattern_movements
        if isinstance(row, Mapping)
        and row.get("movement") in {"increasing", "decreasing"}
    )
    score = trend_analysis["score"]
    breadth = trend_analysis["breadth"]
    assert isinstance(score, Mapping) and isinstance(breadth, Mapping)
    return {
        "classification_schema_version": CLASSIFICATION_SCHEMA_VERSION,
        "classification_policy": stamp,
        "classification_availability": availability,
        "pattern_classifications": positive_classifications,
        "antipattern_classifications": antipattern_classifications,
        "trend_analysis": trend_analysis,
        "score_trend": score["status"],
        "pattern_breadth": {
            "avg_distinct_patterns_per_talk": average_breadth,
            "trend": breadth["status"],
            "note": "Breadth is the mean count of detected positive catalog patterns per current-generation talk.",
        },
        "underused_patterns": underused_ids,
        "score_drivers": {
            "direction": score["status"],
            "antipattern_drivers": antipattern_drivers,
            "pattern_drivers": pattern_drivers,
            "note": "Drivers include only catalog IDs whose conservative 5+5 interval crossed the policy movement threshold.",
        },
        "by_mode": [],
        "strengths": strength_ids,
        "strengths_note": "Deterministic projection of regular and signature positive-pattern classifications.",
        "never_used_patterns": never_tried_ids,
        # The denominator has to travel with the list. Absence is provable for a
        # minority of the observable catalog, so a short never-used list is
        # mostly a statement about coverage rather than about the speaker.
        "absence_provability": absence_provability(resolved_catalog),
        "signature_combinations": combinations,
        "mastery_levels": mastery_levels,
    }


def _decode_stdin() -> Mapping[str, object]:
    try:
        payload = json.load(
            sys.stdin, object_pairs_hook=_strict_object, parse_constant=_fail_constant
        )
    except (json.JSONDecodeError, PatternClassificationError) as exc:
        raise PatternClassificationError(f"invalid input JSON: {exc}") from exc
    if not isinstance(payload, Mapping) or set(payload) != {"baseline_talks"}:
        raise PatternClassificationError(
            "stdin must be an object containing exactly baseline_talks"
        )
    return payload


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Usage: {pathlib.Path(argv[0]).name} VAULT_ROOT", file=sys.stderr)
        return 1
    try:
        vault_root = pathlib.Path(argv[1]).expanduser().resolve(strict=True)
        if not vault_root.is_dir():
            raise PatternClassificationError("vault_root must be a directory")
        payload = _decode_stdin()
        policy_stamp = resolve_classification_policy(vault_root)
        result = classify_pattern_profile(payload["baseline_talks"], policy_stamp)
    except (OSError, PatternClassificationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
