"""Pure construction and validation for batch-stable adherence baselines.

The queue owner will snapshot this payload before it claims a batch.  Profile
generation and other downstream consumers can also use the same exact scoring-
generation selector for post-batch views.  This module deliberately performs
no I/O and never reads the clock: callers supply the complete talk population,
the exact selected filenames, the as-of timestamp, and (for scoring v4+) a pure
artifact-freshness assessor already bound to trusted roots.  Keeping selection
and aggregation here makes queue, return, persistence, rendering, and profile
integrations share one denominator without coupling this contract to any of
those surfaces.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import datetime, timezone
from decimal import Decimal, DecimalException, ROUND_HALF_EVEN
from typing import cast


LEGACY_ADHERENCE_BASELINE_SCHEMA_VERSION = 1
ADHERENCE_BASELINE_SCHEMA_VERSION = 2
ADHERENCE_BASELINE_SCOPE = "global"
ELIGIBLE_STATUSES = ("processed", "processed_partial")
CURRENT_PATTERN_SCORING_GENERATION_STATUS = "current"
_LEGACY_PATTERN_SCORING_GENERATION_STATUS = "legacy_unbaselineable"
MISSING_GENERATION_STATUS_REASON = "missing_generation_status"
LEGACY_GENERATION_REASON = "legacy_generation"
CATALOG_FINGERPRINT_MISMATCH_REASON = "catalog_fingerprint_mismatch"
SCORING_SCHEMA_VERSION_MISMATCH_REASON = "scoring_schema_version_mismatch"
PERSISTED_EVIDENCE_STALE_REASON = "persisted_evidence_stale"
EVIDENCE_BOUND_SCORING_SCHEMA_VERSION = 4
OPPORTUNITY_BOUND_SCORING_SCHEMA_VERSION = 5
NO_EVALUABLE_PATTERN_OPPORTUNITIES_REASON = "no_evaluable_pattern_opportunities"
_PATTERN_OUTCOMES = frozenset(
    {"detected", "undetected", "not_evaluable", "not_applicable"}
)
_EVALUABLE_PATTERN_OUTCOMES = frozenset({"detected", "undetected"})
_KNOWN_PATTERN_SCORING_GENERATION_STATUSES = frozenset(
    {
        CURRENT_PATTERN_SCORING_GENERATION_STATUS,
        _LEGACY_PATTERN_SCORING_GENERATION_STATUS,
    }
)

_CATALOG_FINGERPRINT = re.compile(r"[0-9a-f]{64}")
_OPPORTUNITY_COVERAGE_IDENTITY = re.compile(r"[0-9a-f]{64}")
_MISSING = object()
_TWO_DECIMAL_PLACES = Decimal("0.01")
_LEGACY_SNAPSHOT_FIELDS = (
    "schema_version",
    "as_of",
    "scope",
    "active_batch_excluded",
    "excluded_filenames",
    "eligible_statuses",
    "pattern_scoring_generation_status",
    "pattern_scoring_generation_reasons",
    "pattern_catalog_fingerprint",
    "pattern_scoring_schema_version",
    "scored_talk_count",
    "pattern_score_sum",
    "average_pattern_score",
)
_SNAPSHOT_FIELDS = _LEGACY_SNAPSHOT_FIELDS + (
    "eligible_talk_count",
    "opportunity_coverage_identity",
    "raw_score_comparison_status",
    "raw_score_comparison_reason",
)


class AdherenceBaselineError(ValueError):
    """An adherence-baseline input or snapshot violates schema version 1 or 2."""


EvidenceFreshnessAssessor = Callable[[Mapping[str, object]], Iterable[str]]


def normalize_as_of(value: object) -> str:
    """Normalize a caller-supplied aware timestamp to UTC whole seconds."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise AdherenceBaselineError(
            "as_of must be a non-empty ISO-8601 string without edge whitespace"
        )
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdherenceBaselineError(
            f"as_of must be a valid ISO-8601 timestamp, got {value!r}"
        ) from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise AdherenceBaselineError(
            f"as_of timestamp {value!r} has no timezone; append an explicit offset"
        )
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _require_integer(
    value: object,
    label: str,
    *,
    minimum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AdherenceBaselineError(f"{label} must be an integer, got {value!r}")
    if minimum is not None and value < minimum:
        raise AdherenceBaselineError(f"{label} must be at least {minimum}, got {value}")
    return value


def _require_catalog_fingerprint(value: object, label: str) -> str:
    if not isinstance(value, str) or _CATALOG_FINGERPRINT.fullmatch(value) is None:
        raise AdherenceBaselineError(
            f"{label} must be a lowercase 64-character SHA-256 fingerprint"
        )
    return value


def _require_filename(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AdherenceBaselineError(
            f"{label} must be a non-empty string without edge whitespace"
        )
    return value


def _selected_filenames(value: object) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise AdherenceBaselineError(
            "selected_filenames must be an iterable of exact filename strings"
        )
    filenames = [
        _require_filename(item, f"selected_filenames[{index}]")
        for index, item in enumerate(value)
    ]
    if len(filenames) != len(set(filenames)):
        raise AdherenceBaselineError("selected_filenames contains duplicates")
    return sorted(filenames)


def _talk_records(value: object) -> Iterator[Mapping[str, object]]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise AdherenceBaselineError("talks must be an iterable of talk objects")
    for index, talk in enumerate(value):
        if not isinstance(talk, Mapping):
            raise AdherenceBaselineError(
                f"talks[{index}] must be an object, got {type(talk).__name__}"
            )
        yield cast(Mapping[str, object], talk)


def _classify_generation(
    talk: Mapping[str, object],
    *,
    pattern_catalog_fingerprint: str,
    pattern_scoring_schema_version: int,
    filename: str,
) -> tuple[bool, list[str], str | None, str | None, int | None]:
    raw_status = talk.get("pattern_scoring_generation_status", _MISSING)
    if raw_status is _MISSING:
        return False, [MISSING_GENERATION_STATUS_REASON], None, None, None
    if (
        not isinstance(raw_status, str)
        or raw_status not in _KNOWN_PATTERN_SCORING_GENERATION_STATUSES
    ):
        raise AdherenceBaselineError(
            f"{filename}.pattern_scoring_generation_status must be one of "
            f"{sorted(_KNOWN_PATTERN_SCORING_GENERATION_STATUSES)!r}, got "
            f"{raw_status!r}"
        )
    if raw_status != CURRENT_PATTERN_SCORING_GENERATION_STATUS:
        return False, [LEGACY_GENERATION_REASON], raw_status, None, None
    raw_reasons = talk.get("pattern_scoring_generation_reasons", _MISSING)
    if raw_reasons != []:
        raise AdherenceBaselineError(
            f"{filename}.pattern_scoring_generation_reasons must be exactly [] "
            "when pattern_scoring_generation_status is 'current'"
        )

    raw_fingerprint = talk.get("pattern_catalog_fingerprint", _MISSING)
    raw_version = talk.get("pattern_scoring_schema_version", _MISSING)
    if raw_fingerprint is _MISSING or raw_version is _MISSING:
        missing = []
        if raw_fingerprint is _MISSING:
            missing.append("pattern_catalog_fingerprint")
        if raw_version is _MISSING:
            missing.append("pattern_scoring_schema_version")
        raise AdherenceBaselineError(
            f"{filename} claims the current scoring generation but is missing "
            f"required identity fields {missing}"
        )
    stored_fingerprint = _require_catalog_fingerprint(
        raw_fingerprint, f"{filename}.pattern_catalog_fingerprint"
    )
    stored_version = _require_integer(
        raw_version,
        f"{filename}.pattern_scoring_schema_version",
        minimum=1,
    )
    reason_codes = []
    if stored_fingerprint != pattern_catalog_fingerprint:
        reason_codes.append(CATALOG_FINGERPRINT_MISMATCH_REASON)
    if stored_version != pattern_scoring_schema_version:
        reason_codes.append(SCORING_SCHEMA_VERSION_MISMATCH_REASON)
    return (
        not reason_codes,
        reason_codes,
        raw_status,
        stored_fingerprint,
        stored_version,
    )


def _resolved_pattern_score(
    talk: Mapping[str, object],
    *,
    filename: str,
) -> int:
    top_score = talk.get("pattern_score", _MISSING)
    observations = talk.get("pattern_observations", _MISSING)
    if top_score is _MISSING:
        raise AdherenceBaselineError(
            f"{filename} claims the current scoring generation but has no "
            "promoted pattern_score"
        )
    if not isinstance(observations, Mapping):
        raise AdherenceBaselineError(
            f"{filename} claims the current scoring generation but "
            "pattern_observations is not an object"
        )
    nested_score = observations.get("pattern_score", _MISSING)
    if nested_score is _MISSING:
        raise AdherenceBaselineError(
            f"{filename} claims the current scoring generation but has no "
            "nested pattern_observations.pattern_score"
        )

    validated_top = _require_integer(top_score, f"{filename}.pattern_score")
    validated_nested = _require_integer(
        nested_score,
        f"{filename}.pattern_observations.pattern_score",
    )
    if validated_top != validated_nested:
        raise AdherenceBaselineError(
            f"{filename} promoted pattern_score {validated_top} diverges from "
            f"nested pattern_observations.pattern_score {validated_nested}"
        )
    return validated_top


def _resolved_opportunity_coverage_identity(
    talk: Mapping[str, object], *, filename: str
) -> str:
    observations = talk.get("pattern_observations")
    value = (
        observations.get("opportunity_coverage_identity")
        if isinstance(observations, Mapping)
        else None
    )
    if (
        not isinstance(value, str)
        or _OPPORTUNITY_COVERAGE_IDENTITY.fullmatch(value) is None
    ):
        raise AdherenceBaselineError(
            f"{filename} claims the current opportunity-bound scoring "
            "generation but has no valid "
            "pattern_observations.opportunity_coverage_identity"
        )
    return value


def _has_evaluable_pattern_opportunity(
    talk: Mapping[str, object], *, filename: str
) -> bool:
    """Return whether one scoring-v5 outcome contributes to the raw score.

    The opportunity identity makes like-for-like cohorts comparable, but an
    all-unknown identity still has a numeric score of zero.  Publishing that
    zero as an available average would turn missing opportunity coverage into
    performance evidence.  Inspect the identity's source matrix directly and
    fail closed when no row is detected or undetected.
    """
    observations = talk.get("pattern_observations")
    outcomes = (
        observations.get("pattern_outcomes")
        if isinstance(observations, Mapping)
        else None
    )
    if not isinstance(outcomes, list) or not outcomes:
        raise AdherenceBaselineError(
            f"{filename} claims the current opportunity-bound scoring "
            "generation but has no non-empty "
            "pattern_observations.pattern_outcomes array"
        )

    seen: set[str] = set()
    has_evaluable = False
    for index, item in enumerate(outcomes):
        label = f"{filename}.pattern_observations.pattern_outcomes[{index}]"
        if not isinstance(item, Mapping) or set(item) != {"pattern_id", "outcome"}:
            raise AdherenceBaselineError(
                f"{label} must contain exactly pattern_id and outcome"
            )
        pattern_id = item.get("pattern_id")
        outcome = item.get("outcome")
        if not isinstance(pattern_id, str) or not pattern_id or pattern_id in seen:
            raise AdherenceBaselineError(
                f"{label}.pattern_id must be non-empty and duplicate-free"
            )
        if not isinstance(outcome, str) or outcome not in _PATTERN_OUTCOMES:
            raise AdherenceBaselineError(
                f"{label}.outcome must be one of {sorted(_PATTERN_OUTCOMES)}, "
                f"got {outcome!r}"
            )
        seen.add(pattern_id)
        has_evaluable = has_evaluable or outcome in _EVALUABLE_PATTERN_OUTCOMES
    return has_evaluable


def _evidence_freshness_details(
    talk: Mapping[str, object],
    *,
    filename: str,
    assessor: EvidenceFreshnessAssessor,
) -> list[str]:
    """Return a canonical list of caller-supplied artifact-drift details."""
    try:
        raw_details = assessor(talk)
    except (OSError, ValueError) as exc:
        raise AdherenceBaselineError(
            f"{filename}: evidence freshness assessment failed: {exc}"
        ) from exc
    if isinstance(raw_details, (str, bytes, Mapping)) or not isinstance(
        raw_details, Iterable
    ):
        raise AdherenceBaselineError(
            f"{filename}: evidence freshness assessor must return an iterable "
            "of stable detail strings"
        )
    details: list[str] = []
    for index, detail in enumerate(raw_details):
        if not isinstance(detail, str) or not detail or detail != detail.strip():
            raise AdherenceBaselineError(
                f"{filename}: evidence freshness detail {index} must be a "
                "non-empty string without edge whitespace"
            )
        details.append(detail)
    return sorted(set(details))


def _average_pattern_score(score_sum: int, talk_count: int) -> float | None:
    if talk_count == 0:
        return None
    try:
        average = (Decimal(score_sum) / Decimal(talk_count)).quantize(
            _TWO_DECIMAL_PLACES,
            rounding=ROUND_HALF_EVEN,
        )
        result = float(average)
    except (DecimalException, OverflowError) as exc:
        raise AdherenceBaselineError(
            "average_pattern_score cannot be represented as a finite "
            "two-place JSON number"
        ) from exc
    if not math.isfinite(result):
        raise AdherenceBaselineError(
            "average_pattern_score cannot be represented as a finite "
            "two-place JSON number"
        )
    return result


def partition_pattern_scoring_cohort(
    talks: object,
    *,
    excluded_filenames: object,
    pattern_catalog_fingerprint: object,
    pattern_scoring_schema_version: object,
    evidence_freshness_assessor: EvidenceFreshnessAssessor | None,
) -> tuple[
    list[Mapping[str, object]],
    list[Mapping[str, object]],
    list[dict[str, object]],
]:
    """Partition eligible talks by exact active scoring generation.

    The first list contains talks that match the active catalog fingerprint and
    scoring schema and have valid, equal promoted/nested scores.  The second
    contains eligible talks whose generation is missing, legacy, or valid but
    different.  The third contains a deterministic reason-code record for each
    talk in the second list, in the same order.  Ineligible statuses and exact
    excluded filenames appear in none of the lists.  Exclusion happens before
    generation or score inspection so an active reparse can safely omit its own
    previous records.

    Scoring schema v4 and later also require a caller-supplied, read-only
    artifact-freshness assessor.  A non-empty result excludes the talk with the
    stable ``persisted_evidence_stale`` reason and preserves the assessor's
    canonical details in ``evidence_freshness_details``.  Earlier scoring
    schemas retain their historical generation-only behavior and do not invoke
    the assessor.

    Malformed metadata is never silently classified as legacy: unknown
    statuses, invalid generation identity, incomplete current-generation
    claims, and invalid score lanes raise :class:`AdherenceBaselineError`.
    Input order is preserved within both returned lists.
    """
    exact_fingerprint = _require_catalog_fingerprint(
        pattern_catalog_fingerprint, "pattern_catalog_fingerprint"
    )
    exact_scoring_version = _require_integer(
        pattern_scoring_schema_version,
        "pattern_scoring_schema_version",
        minimum=1,
    )
    if exact_scoring_version >= EVIDENCE_BOUND_SCORING_SCHEMA_VERSION and not callable(
        evidence_freshness_assessor
    ):
        raise AdherenceBaselineError(
            "scoring schema v4 and later require an explicit callable "
            "evidence_freshness_assessor"
        )
    excluded = frozenset(_selected_filenames(excluded_filenames))

    current: list[Mapping[str, object]] = []
    noncurrent: list[Mapping[str, object]] = []
    exclusion_details: list[dict[str, object]] = []
    seen_filenames: set[str] = set()
    for talk in _talk_records(talks):
        filename = _require_filename(talk.get("filename"), "talk filename")
        if filename in seen_filenames:
            raise AdherenceBaselineError(
                f"talk population contains duplicate filename {filename!r}"
            )
        seen_filenames.add(filename)
        if talk.get("status") not in ELIGIBLE_STATUSES or filename in excluded:
            continue
        (
            is_current,
            reason_codes,
            observed_status,
            observed_fingerprint,
            observed_scoring_version,
        ) = _classify_generation(
            talk,
            pattern_catalog_fingerprint=exact_fingerprint,
            pattern_scoring_schema_version=exact_scoring_version,
            filename=filename,
        )
        if not is_current:
            noncurrent.append(talk)
            exclusion_details.append(
                {
                    "filename": filename,
                    "reason_codes": reason_codes,
                    "observed_pattern_scoring_generation_status": observed_status,
                    "observed_pattern_catalog_fingerprint": observed_fingerprint,
                    "observed_pattern_scoring_schema_version": (
                        observed_scoring_version
                    ),
                    "expected_pattern_scoring_generation_status": (
                        CURRENT_PATTERN_SCORING_GENERATION_STATUS
                    ),
                    "expected_pattern_catalog_fingerprint": exact_fingerprint,
                    "expected_pattern_scoring_schema_version": (exact_scoring_version),
                }
            )
            continue
        _resolved_pattern_score(talk, filename=filename)
        if exact_scoring_version >= OPPORTUNITY_BOUND_SCORING_SCHEMA_VERSION:
            _resolved_opportunity_coverage_identity(talk, filename=filename)
        if exact_scoring_version >= EVIDENCE_BOUND_SCORING_SCHEMA_VERSION:
            assert evidence_freshness_assessor is not None
            freshness_details = _evidence_freshness_details(
                talk,
                filename=filename,
                assessor=evidence_freshness_assessor,
            )
            if freshness_details:
                noncurrent.append(talk)
                exclusion_details.append(
                    {
                        "filename": filename,
                        "reason_codes": [PERSISTED_EVIDENCE_STALE_REASON],
                        "evidence_freshness_details": freshness_details,
                        "observed_pattern_scoring_generation_status": (observed_status),
                        "observed_pattern_catalog_fingerprint": (observed_fingerprint),
                        "observed_pattern_scoring_schema_version": (
                            observed_scoring_version
                        ),
                        "expected_pattern_scoring_generation_status": (
                            CURRENT_PATTERN_SCORING_GENERATION_STATUS
                        ),
                        "expected_pattern_catalog_fingerprint": exact_fingerprint,
                        "expected_pattern_scoring_schema_version": (
                            exact_scoring_version
                        ),
                    }
                )
                continue
        current.append(talk)
    return current, noncurrent, exclusion_details


def _build_adherence_baseline(
    talks: object,
    *,
    selected_filenames: object,
    as_of: object,
    pattern_catalog_fingerprint: object,
    pattern_scoring_schema_version: object,
    evidence_freshness_assessor: EvidenceFreshnessAssessor | None,
    active_batch_excluded: bool,
) -> dict[str, object]:
    """Build one deterministic global baseline with explicit cohort scope."""
    normalized_as_of = normalize_as_of(as_of)
    exact_fingerprint = _require_catalog_fingerprint(
        pattern_catalog_fingerprint, "pattern_catalog_fingerprint"
    )
    exact_scoring_version = _require_integer(
        pattern_scoring_schema_version,
        "pattern_scoring_schema_version",
        minimum=1,
    )
    excluded_filenames = _selected_filenames(selected_filenames)
    if not active_batch_excluded and excluded_filenames:
        raise AdherenceBaselineError(
            "a full current-cohort baseline cannot exclude filenames"
        )
    current_talks, _, _ = partition_pattern_scoring_cohort(
        talks,
        excluded_filenames=excluded_filenames,
        pattern_catalog_fingerprint=exact_fingerprint,
        pattern_scoring_schema_version=exact_scoring_version,
        evidence_freshness_assessor=evidence_freshness_assessor,
    )
    opportunity_identity: str | None = None
    comparison_talks = current_talks
    comparison_status = "available"
    comparison_reason: str | None = None
    if exact_scoring_version >= OPPORTUNITY_BOUND_SCORING_SCHEMA_VERSION:
        opportunity_identities = {
            _resolved_opportunity_coverage_identity(
                talk,
                filename=_require_filename(talk.get("filename"), "talk filename"),
            )
            for talk in current_talks
        }
        evaluable_opportunity_flags = [
            _has_evaluable_pattern_opportunity(
                talk,
                filename=_require_filename(talk.get("filename"), "talk filename"),
            )
            for talk in current_talks
        ]
        if len(opportunity_identities) == 1:
            if any(evaluable_opportunity_flags):
                opportunity_identity = next(iter(opportunity_identities))
            else:
                comparison_talks = []
                comparison_status = "unavailable"
                comparison_reason = NO_EVALUABLE_PATTERN_OPPORTUNITIES_REASON
        elif len(opportunity_identities) > 1:
            # A single raw-score baseline cannot represent incompatible
            # opportunity denominators. Keep the exact-generation cohort
            # available to callers, but emit the null/empty comparison sentinel.
            comparison_talks = []
            comparison_status = "unavailable"
            comparison_reason = "mixed_opportunity_coverage"
        else:
            comparison_status = "unavailable"
            comparison_reason = "empty_current_cohort"
    scored_talk_count = len(comparison_talks)
    pattern_score_sum = sum(
        _resolved_pattern_score(
            talk,
            filename=_require_filename(talk.get("filename"), "talk filename"),
        )
        for talk in comparison_talks
    )

    snapshot: dict[str, object] = {
        "schema_version": (
            ADHERENCE_BASELINE_SCHEMA_VERSION
            if exact_scoring_version >= OPPORTUNITY_BOUND_SCORING_SCHEMA_VERSION
            else LEGACY_ADHERENCE_BASELINE_SCHEMA_VERSION
        ),
        "as_of": normalized_as_of,
        "scope": ADHERENCE_BASELINE_SCOPE,
        "active_batch_excluded": active_batch_excluded,
        "excluded_filenames": excluded_filenames,
        "eligible_statuses": list(ELIGIBLE_STATUSES),
        "pattern_scoring_generation_status": (
            CURRENT_PATTERN_SCORING_GENERATION_STATUS
        ),
        "pattern_scoring_generation_reasons": [],
        "pattern_catalog_fingerprint": exact_fingerprint,
        "pattern_scoring_schema_version": exact_scoring_version,
        "scored_talk_count": scored_talk_count,
        "pattern_score_sum": pattern_score_sum,
        "average_pattern_score": _average_pattern_score(
            pattern_score_sum, scored_talk_count
        ),
    }
    if exact_scoring_version >= OPPORTUNITY_BOUND_SCORING_SCHEMA_VERSION:
        snapshot["eligible_talk_count"] = len(current_talks)
        snapshot["opportunity_coverage_identity"] = opportunity_identity
        snapshot["raw_score_comparison_status"] = comparison_status
        snapshot["raw_score_comparison_reason"] = comparison_reason
    return validate_adherence_baseline(snapshot)


def build_adherence_baseline(
    talks: object,
    *,
    selected_filenames: object,
    as_of: object,
    pattern_catalog_fingerprint: object,
    pattern_scoring_schema_version: object,
    evidence_freshness_assessor: EvidenceFreshnessAssessor | None,
) -> dict[str, object]:
    """Build a claim-time baseline excluding the exact active batch.

    Exclusion happens before generation or score inspection, so a reparse can
    never compare a talk with its own previous result.
    """
    return _build_adherence_baseline(
        talks,
        selected_filenames=selected_filenames,
        as_of=as_of,
        pattern_catalog_fingerprint=pattern_catalog_fingerprint,
        pattern_scoring_schema_version=pattern_scoring_schema_version,
        evidence_freshness_assessor=evidence_freshness_assessor,
        active_batch_excluded=True,
    )


def build_current_cohort_baseline(
    talks: object,
    *,
    as_of: object,
    pattern_catalog_fingerprint: object,
    pattern_scoring_schema_version: object,
    evidence_freshness_assessor: EvidenceFreshnessAssessor | None,
) -> dict[str, object]:
    """Build an all-inclusive post-batch snapshot of the current cohort."""
    return _build_adherence_baseline(
        talks,
        selected_filenames=(),
        as_of=as_of,
        pattern_catalog_fingerprint=pattern_catalog_fingerprint,
        pattern_scoring_schema_version=pattern_scoring_schema_version,
        evidence_freshness_assessor=evidence_freshness_assessor,
        active_batch_excluded=False,
    )


def validate_adherence_baseline(snapshot: object) -> dict[str, object]:
    """Validate schema 1 and return its canonical JSON-compatible shape."""
    if not isinstance(snapshot, Mapping):
        raise AdherenceBaselineError("adherence baseline must be an object")
    schema_version = _require_integer(snapshot.get("schema_version"), "schema_version")
    if schema_version not in {
        LEGACY_ADHERENCE_BASELINE_SCHEMA_VERSION,
        ADHERENCE_BASELINE_SCHEMA_VERSION,
    }:
        raise AdherenceBaselineError(
            f"unsupported adherence baseline schema_version {schema_version}; "
            f"expected one of {[LEGACY_ADHERENCE_BASELINE_SCHEMA_VERSION, ADHERENCE_BASELINE_SCHEMA_VERSION]}"
        )
    actual_fields = set(snapshot)
    expected_fields = set(
        _SNAPSHOT_FIELDS
        if schema_version == ADHERENCE_BASELINE_SCHEMA_VERSION
        else _LEGACY_SNAPSHOT_FIELDS
    )
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        unknown = sorted(str(field) for field in actual_fields - expected_fields)
        raise AdherenceBaselineError(
            "adherence baseline fields are noncanonical; "
            f"missing={missing}, unknown={unknown}"
        )

    normalized_as_of = normalize_as_of(snapshot["as_of"])
    if snapshot["as_of"] != normalized_as_of:
        raise AdherenceBaselineError(
            f"as_of must use canonical UTC whole-second form {normalized_as_of!r}"
        )
    if snapshot["scope"] != ADHERENCE_BASELINE_SCOPE:
        raise AdherenceBaselineError(f"scope must be {ADHERENCE_BASELINE_SCOPE!r}")
    active_batch_excluded = snapshot["active_batch_excluded"]
    if not isinstance(active_batch_excluded, bool):
        raise AdherenceBaselineError("active_batch_excluded must be a boolean")

    raw_excluded = snapshot["excluded_filenames"]
    if not isinstance(raw_excluded, list):
        raise AdherenceBaselineError("excluded_filenames must be an array")
    excluded_filenames = _selected_filenames(raw_excluded)
    if raw_excluded != excluded_filenames:
        raise AdherenceBaselineError(
            "excluded_filenames must be sorted in canonical filename order"
        )
    if not active_batch_excluded and excluded_filenames:
        raise AdherenceBaselineError(
            "excluded_filenames must be [] when active_batch_excluded is false"
        )
    if snapshot["eligible_statuses"] != list(ELIGIBLE_STATUSES):
        raise AdherenceBaselineError(
            f"eligible_statuses must be exactly {list(ELIGIBLE_STATUSES)!r}"
        )
    if (
        snapshot["pattern_scoring_generation_status"]
        != CURRENT_PATTERN_SCORING_GENERATION_STATUS
    ):
        raise AdherenceBaselineError(
            "pattern_scoring_generation_status must be exactly "
            f"{CURRENT_PATTERN_SCORING_GENERATION_STATUS!r}"
        )
    if snapshot["pattern_scoring_generation_reasons"] != []:
        raise AdherenceBaselineError(
            "pattern_scoring_generation_reasons must be exactly [] for the "
            "current baseline cohort"
        )

    fingerprint = _require_catalog_fingerprint(
        snapshot["pattern_catalog_fingerprint"],
        "pattern_catalog_fingerprint",
    )
    scoring_version = _require_integer(
        snapshot["pattern_scoring_schema_version"],
        "pattern_scoring_schema_version",
        minimum=1,
    )
    talk_count = _require_integer(
        snapshot["scored_talk_count"],
        "scored_talk_count",
        minimum=0,
    )
    score_sum = _require_integer(snapshot["pattern_score_sum"], "pattern_score_sum")
    expected_average = _average_pattern_score(score_sum, talk_count)
    raw_average = snapshot["average_pattern_score"]
    if talk_count == 0:
        if score_sum != 0:
            raise AdherenceBaselineError(
                "pattern_score_sum must be zero when scored_talk_count is zero"
            )
        if raw_average is not None:
            raise AdherenceBaselineError(
                "average_pattern_score must be null when scored_talk_count is zero"
            )
    else:
        if isinstance(raw_average, bool) or not isinstance(raw_average, (int, float)):
            raise AdherenceBaselineError(
                "average_pattern_score must be a finite JSON number when talks are scored"
            )
        if isinstance(raw_average, float) and not math.isfinite(raw_average):
            raise AdherenceBaselineError("average_pattern_score must be finite")
        if raw_average != expected_average:
            raise AdherenceBaselineError(
                f"average_pattern_score {raw_average!r} does not match "
                f"ROUND_HALF_EVEN count/sum result {expected_average!r}"
            )

    opportunity_identity: str | None = None
    eligible_count = 0
    comparison_status: object = None
    comparison_reason: object = None
    if schema_version == ADHERENCE_BASELINE_SCHEMA_VERSION:
        eligible_count = _require_integer(
            snapshot["eligible_talk_count"],
            "eligible_talk_count",
            minimum=0,
        )
        raw_identity = snapshot["opportunity_coverage_identity"]
        if raw_identity is not None and (
            not isinstance(raw_identity, str)
            or _OPPORTUNITY_COVERAGE_IDENTITY.fullmatch(raw_identity) is None
        ):
            raise AdherenceBaselineError(
                "opportunity_coverage_identity must be null or a lowercase "
                "64-character SHA-256 identity"
            )
        comparison_status = snapshot["raw_score_comparison_status"]
        comparison_reason = snapshot["raw_score_comparison_reason"]
        if comparison_status not in {"available", "unavailable"}:
            raise AdherenceBaselineError(
                "raw_score_comparison_status must be 'available' or 'unavailable'"
            )
        if talk_count > 0 and raw_identity is None:
            raise AdherenceBaselineError(
                "a non-empty schema-v2 adherence baseline requires one exact "
                "opportunity_coverage_identity"
            )
        if talk_count == 0 and raw_identity is not None:
            raise AdherenceBaselineError(
                "an empty schema-v2 adherence baseline must use the null "
                "opportunity_coverage_identity sentinel"
            )
        if comparison_status == "available":
            if (
                comparison_reason is not None
                or talk_count < 1
                or eligible_count != talk_count
            ):
                raise AdherenceBaselineError(
                    "an available raw-score comparison requires null reason, "
                    "one or more scored talks, and equal eligible/scored counts"
                )
        else:
            if comparison_reason not in {
                "empty_current_cohort",
                "mixed_opportunity_coverage",
                NO_EVALUABLE_PATTERN_OPPORTUNITIES_REASON,
            }:
                raise AdherenceBaselineError(
                    "an unavailable raw-score comparison requires a stable "
                    "empty/mixed/no-evaluable opportunity reason"
                )
            if talk_count != 0 or raw_identity is not None:
                raise AdherenceBaselineError(
                    "an unavailable raw-score comparison must use zero scored "
                    "talks and a null opportunity identity"
                )
            if (
                (comparison_reason == "empty_current_cohort" and eligible_count != 0)
                or (
                    comparison_reason == "mixed_opportunity_coverage"
                    and eligible_count < 2
                )
                or (
                    comparison_reason == NO_EVALUABLE_PATTERN_OPPORTUNITIES_REASON
                    and eligible_count < 1
                )
            ):
                raise AdherenceBaselineError(
                    "raw-score comparison reason disagrees with eligible_talk_count"
                )
        opportunity_identity = raw_identity

    canonical = {
        "schema_version": schema_version,
        "as_of": normalized_as_of,
        "scope": ADHERENCE_BASELINE_SCOPE,
        "active_batch_excluded": active_batch_excluded,
        "excluded_filenames": excluded_filenames,
        "eligible_statuses": list(ELIGIBLE_STATUSES),
        "pattern_scoring_generation_status": (
            CURRENT_PATTERN_SCORING_GENERATION_STATUS
        ),
        "pattern_scoring_generation_reasons": [],
        "pattern_catalog_fingerprint": fingerprint,
        "pattern_scoring_schema_version": scoring_version,
        "scored_talk_count": talk_count,
        "pattern_score_sum": score_sum,
        "average_pattern_score": expected_average,
    }
    if schema_version == ADHERENCE_BASELINE_SCHEMA_VERSION:
        canonical["eligible_talk_count"] = eligible_count
        canonical["opportunity_coverage_identity"] = opportunity_identity
        canonical["raw_score_comparison_status"] = comparison_status
        canonical["raw_score_comparison_reason"] = comparison_reason
    return canonical
