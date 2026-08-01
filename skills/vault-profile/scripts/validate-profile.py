#!/usr/bin/env python3
"""Validate a current speaker-profile.json before the owner writes it.

Schema version 4 binds every Presentation Pattern aggregate to one exact,
current scoring generation and exact per-pattern opportunity denominators. The
reusable strict nested contract lives in
``profile_pattern_provenance.py`` so non-owner readers make the same pattern-
history availability decision as this writer.

Contract
--------
Input:
    A profile path (positional) or JSON on stdin, plus required
    ``--vault-root <path>`` for schema-v4 owner validation. The live vault is
    reparsed with the candidate baseline's ``as_of`` value before acceptance.

Stdout (JSON):
    {
      "valid":          true|false,
      "schema_version": <int|null>,
      "missing_keys":   [ ... ],
      "errors":         [ ... ]
    }

Exit codes:
    0   profile valid
    1   profile invalid (missing keys, wrong schema version, malformed input,
        or stale/inconsistent pattern provenance)
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections.abc import Mapping
from typing import Any


_PROFILE_SCRIPTS = pathlib.Path(__file__).resolve().parent
if str(_PROFILE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PROFILE_SCRIPTS))
_INGRESS_SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"
if str(_INGRESS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_INGRESS_SCRIPTS))

from profile_pattern_provenance import (  # noqa: E402
    active_pattern_generation_identity as _active_pattern_generation_identity,
    assess_pattern_profile,
)
from pattern_cohort_snapshot import (  # noqa: E402
    PatternCohortSnapshot,
    build_current_pattern_snapshot,
    configured_evidence_freshness_assessor,
)
# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from tracking_database import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    TrackingDatabaseError,
    assess_tracking_database,
)
# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from tracking_database_io import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)


CURRENT_SCHEMA_VERSION = 4

REQUIRED_KEYS = [
    "schema_version",
    "generated_date",
    "talks_analyzed",
    "speaker",
    "infrastructure",
    "presentation_modes",
    "instrument_catalog",
    "rhetoric_defaults",
    "confirmed_intents",
    "guardrail_sources",
    "pacing",
    "pattern_profile",
    "visual_style_history",
    "publishing_process",
    "design_rules",
    "badges",
]

_PATTERN_HISTORY_KEYS = frozenset(
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
        "pattern_usage",
        "antipattern_frequency",
        "never_used_patterns",
        "signature_combinations",
        "mastery_levels",
        "classification_availability",
    }
)
_FORBIDDEN_NON_PATTERN_ENTRY_FIELDS = frozenset(
    {
        "pattern_id",
        "pattern_ids",
        "pattern_score",
        "mastery_level",
        "pattern_catalog_fingerprint",
        "pattern_scoring_schema_version",
        "times_used",
        "times_detected",
        "usage_rate",
        "frequency_rate",
        "out_of",
        "detected_count",
        "evaluable_count",
        "unevaluable_count",
        "not_applicable_count",
        "eligible_cohort_count",
        "coverage",
    }
)


def active_pattern_generation_identity() -> tuple[str, int]:
    """Expose the shared active identity for profile construction/tests."""
    return _active_pattern_generation_identity()


def _parse_args(argv: list[str]) -> tuple[pathlib.Path | None, pathlib.Path | None]:
    profile_path: pathlib.Path | None = None
    vault_root: pathlib.Path | None = None
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg == "--vault-root":
            if vault_root is not None:
                raise ValueError("--vault-root may be supplied only once")
            index += 1
            if index >= len(argv):
                raise ValueError("--vault-root requires a path")
            vault_root = pathlib.Path(argv[index]).expanduser().resolve()
        elif arg.startswith("-"):
            raise ValueError(f"unknown option {arg!r}")
        elif profile_path is None:
            profile_path = pathlib.Path(arg)
        else:
            raise ValueError(f"unexpected extra argument {arg!r}")
        index += 1
    return profile_path, vault_root


def _load_input(profile_path: pathlib.Path | None) -> dict[str, Any]:
    if profile_path is not None:
        return json.loads(profile_path.read_text())
    return json.loads(sys.stdin.read())


def _load_live_pattern_snapshot(
    vault_root: pathlib.Path,
    profile: Mapping[str, object],
) -> PatternCohortSnapshot:
    """Recompute the source-exact payload used by ``load-vault.py``."""
    database_path = vault_root / "tracking-database.json"
    try:
        database_snapshot = snapshot_tracking_database(database_path)
        database = decode_json_object(database_snapshot)
    except TrackingDatabaseIOError as exc:
        raise ValueError(f"tracking-database.json is invalid: {exc}") from exc
    try:
        assessment = assess_tracking_database(database)
    except TrackingDatabaseError as exc:
        raise ValueError(f"tracking-database.json schema is invalid: {exc}") from exc
    if not assessment.usable:
        raise ValueError(
            "tracking-database.json has no usable prior state for this reader: "
            + ", ".join(assessment.reason_codes)
        )
    talks = database.get("talks")
    if not isinstance(talks, list) or any(
        not isinstance(talk, Mapping) for talk in talks
    ):
        raise ValueError("tracking-database.json `talks` must be an array of objects")
    pattern_profile = profile.get("pattern_profile")
    baseline = (
        pattern_profile.get("pattern_baseline")
        if isinstance(pattern_profile, Mapping)
        else None
    )
    as_of = baseline.get("as_of") if isinstance(baseline, Mapping) else None
    return build_current_pattern_snapshot(
        talks,
        as_of=as_of,
        evidence_freshness_assessor=configured_evidence_freshness_assessor(
            vault_root,
            database.get("config"),
        ),
    )


def _validate_live_pattern_source(
    profile: Mapping[object, object],
    snapshot: object,
) -> list[str]:
    """Require source fields to equal one freshly recomputed canonical snapshot."""
    if not isinstance(snapshot, Mapping):
        return ["live pattern snapshot must be an object"]
    pattern_profile = profile.get("pattern_profile")
    if not isinstance(pattern_profile, Mapping):
        return ["pattern_profile must be an object before live source validation"]
    opportunities = snapshot.get("pattern_opportunities")
    if not isinstance(opportunities, Mapping):
        return ["live pattern snapshot lacks pattern_opportunities"]

    comparisons = (
        (
            "pattern_baseline",
            snapshot.get("pattern_baseline"),
            "live canonical pattern_baseline",
        ),
        (
            "baseline_talk_filenames",
            snapshot.get("baseline_talk_filenames"),
            "live fresh scoring-v5 cohort filenames",
        ),
        (
            "eligible_talk_count",
            opportunities.get("eligible_cohort_count"),
            "live fresh scoring-v5 eligible cohort count",
        ),
        (
            "pattern_usage",
            opportunities.get("pattern_usage"),
            "live canonical positive opportunity rows",
        ),
        (
            "antipattern_frequency",
            opportunities.get("antipattern_frequency"),
            "live canonical negative opportunity rows",
        ),
    )
    errors: list[str] = []
    for field, expected, description in comparisons:
        if pattern_profile.get(field) != expected:
            errors.append(
                f"pattern_profile.{field} does not equal the {description}; "
                "regenerate it from the current load-vault.py payload"
            )
    return errors


def _validate_non_pattern_entries(
    value: object,
    *,
    path: str,
) -> list[str]:
    if not isinstance(value, list):
        return [f"{path} must be an array"]

    errors: list[str] = []
    for index, entry in enumerate(value):
        entry_path = f"{path}[{index}]"
        if not isinstance(entry, Mapping):
            errors.append(f"{entry_path} must be an object")
            continue
        if entry.get("source_lane") != "non_pattern":
            errors.append(
                f"{entry_path}.source_lane must be exactly 'non_pattern'; "
                "catalog-derived history belongs only in pattern_profile"
            )
        forbidden = sorted(_FORBIDDEN_NON_PATTERN_ENTRY_FIELDS.intersection(entry))
        if forbidden:
            errors.append(
                f"{entry_path} contains catalog-history fields prohibited outside "
                f"pattern_profile: {', '.join(forbidden)}"
            )
    return errors


def _validate_catalog_history_storage(profile: Mapping[object, object]) -> list[str]:
    """Keep all Presentation Pattern history inside ``pattern_profile``."""
    errors: list[str] = []
    rhetoric_defaults = profile.get("rhetoric_defaults")
    if not isinstance(rhetoric_defaults, Mapping):
        errors.append("rhetoric_defaults must be an object")
    else:
        duplicates = sorted(_PATTERN_HISTORY_KEYS.intersection(rhetoric_defaults))
        if duplicates:
            errors.append(
                "rhetoric_defaults duplicates catalog history owned by "
                f"pattern_profile: {', '.join(duplicates)}"
            )

    guardrail_sources = profile.get("guardrail_sources")
    if not isinstance(guardrail_sources, Mapping):
        errors.append("guardrail_sources must be an object")
    elif "recurring_issues" not in guardrail_sources:
        errors.append("guardrail_sources.recurring_issues is required in schema v4")
    else:
        errors.extend(
            _validate_non_pattern_entries(
                guardrail_sources["recurring_issues"],
                path="guardrail_sources.recurring_issues",
            )
        )

    errors.extend(_validate_non_pattern_entries(profile.get("badges"), path="badges"))
    return errors


def validate_profile(
    profile: object,
    *,
    live_pattern_snapshot: object | None = None,
    require_live_source: bool = False,
) -> tuple[list[str], list[str], object]:
    """Return ``(missing_top_level_keys, errors, schema_version)``."""
    if not isinstance(profile, Mapping):
        return (
            [],
            [f"profile must be a JSON object, got {type(profile).__name__}"],
            None,
        )

    missing = [key for key in REQUIRED_KEYS if key not in profile]
    schema_version = profile.get("schema_version")
    errors: list[str] = []
    if schema_version != CURRENT_SCHEMA_VERSION:
        errors.append(
            f"schema_version is {schema_version!r} (expected {CURRENT_SCHEMA_VERSION})"
        )
    if not missing and schema_version == CURRENT_SCHEMA_VERSION:
        assessment = assess_pattern_profile(profile["pattern_profile"])
        if not assessment.current_contract:
            errors.extend(assessment.errors)
        errors.extend(_validate_catalog_history_storage(profile))
        if live_pattern_snapshot is not None:
            errors.extend(_validate_live_pattern_source(profile, live_pattern_snapshot))
        elif require_live_source:
            errors.append(
                "schema-v4 owner validation requires --vault-root so occurrence "
                "rows can be recomputed from the live tracking database"
            )
    return missing, errors, schema_version


def _emit_result(
    *,
    valid: bool,
    schema_version: object,
    missing_keys: list[str],
    errors: list[str],
) -> None:
    print(
        json.dumps(
            {
                "valid": valid,
                "schema_version": schema_version,
                "missing_keys": missing_keys,
                "errors": errors,
            },
            indent=2,
        )
    )


def main(argv: list[str]) -> int:
    try:
        profile_path, vault_root = _parse_args(argv)
        profile = _load_input(profile_path)
    except (
        json.JSONDecodeError,
        UnicodeError,
        FileNotFoundError,
        OSError,
        ValueError,
    ) as exc:
        message = f"Could not load profile: {exc}"
        print(f"ERROR: could not load profile input: {exc}", file=sys.stderr)
        _emit_result(
            valid=False,
            schema_version=None,
            missing_keys=[],
            errors=[message],
        )
        return 1

    live_snapshot: object | None = None
    live_error: str | None = None
    if vault_root is not None and isinstance(profile, Mapping):
        try:
            live_snapshot = _load_live_pattern_snapshot(vault_root, profile)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            live_error = (
                f"could not recompute the live pattern cohort from {vault_root}: {exc}"
            )

    missing, errors, schema_version = validate_profile(
        profile,
        live_pattern_snapshot=live_snapshot,
        require_live_source=True,
    )
    if live_error is not None:
        errors.append(live_error)
    if missing:
        errors.insert(0, f"missing keys: {', '.join(missing)}")
    valid = not missing and not errors

    if not valid:
        print(f"ERROR: profile invalid — {'; '.join(errors)}", file=sys.stderr)
    _emit_result(
        valid=valid,
        schema_version=schema_version,
        missing_keys=missing,
        errors=errors,
    )
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
