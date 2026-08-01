#!/usr/bin/env python3
"""Validate a current speaker-profile.json before the owner writes it.

Schema version 3 binds every Presentation Pattern aggregate to one exact,
current scoring generation. The reusable strict nested contract lives in
``profile_pattern_provenance.py`` so non-owner readers make the same pattern-
history availability decision as this writer.

Contract
--------
Input:
    Either a path to a JSON file (positional arg) OR JSON on stdin.

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

from profile_pattern_provenance import (  # noqa: E402
    active_pattern_generation_identity as _active_pattern_generation_identity,
    assess_pattern_profile,
)


CURRENT_SCHEMA_VERSION = 3

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
    }
)


def active_pattern_generation_identity() -> tuple[str, int]:
    """Expose the shared active identity for profile construction/tests."""
    return _active_pattern_generation_identity()


def _load_input(argv: list[str]) -> dict[str, Any]:
    if len(argv) > 1:
        return json.loads(pathlib.Path(argv[1]).read_text())
    return json.loads(sys.stdin.read())


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
        forbidden = sorted(
            _FORBIDDEN_NON_PATTERN_ENTRY_FIELDS.intersection(entry)
        )
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
        errors.append("guardrail_sources.recurring_issues is required in schema v3")
    else:
        errors.extend(
            _validate_non_pattern_entries(
                guardrail_sources["recurring_issues"],
                path="guardrail_sources.recurring_issues",
            )
        )

    errors.extend(_validate_non_pattern_entries(profile.get("badges"), path="badges"))
    return errors


def validate_profile(profile: object) -> tuple[list[str], list[str], object]:
    """Return ``(missing_top_level_keys, errors, schema_version)``."""
    if not isinstance(profile, Mapping):
        return [], [f"profile must be a JSON object, got {type(profile).__name__}"], None

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
        profile = _load_input(argv)
    except (json.JSONDecodeError, UnicodeError, FileNotFoundError, OSError) as exc:
        message = f"Could not load profile: {exc}"
        print(f"ERROR: could not load profile input: {exc}", file=sys.stderr)
        _emit_result(
            valid=False,
            schema_version=None,
            missing_keys=[],
            errors=[message],
        )
        return 1

    missing, errors, schema_version = validate_profile(profile)
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
