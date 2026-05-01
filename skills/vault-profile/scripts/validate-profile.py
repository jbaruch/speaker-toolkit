#!/usr/bin/env python3
"""Validate a speaker-profile.json document against the required-keys contract.

The skill orchestrator constructs the profile dict from aggregated vault data
and pipes it (or the file path) to this script for validation before writing
the final profile to disk. The script enforces the top-level keys required by
the schema reference (`references/speaker-profile-schema.md`) and the
schema_version invariant.

Contract
--------
Input:
    Either a path to a JSON file (positional arg) OR JSON on stdin.

Stdout (JSON):
    {
      "valid":          true|false,
      "schema_version": <int|null>,
      "missing_keys":   [ ... ]        # required top-level keys that are absent
    }

Exit codes:
    0   profile valid
    1   profile invalid (missing keys, wrong schema_version, malformed input)
"""

from __future__ import annotations

import json
import pathlib
import sys


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


def _load_input(argv: list[str]) -> dict:
    if len(argv) > 1:
        return json.loads(pathlib.Path(argv[1]).read_text())
    return json.loads(sys.stdin.read())


def main(argv: list[str]) -> int:
    try:
        profile = _load_input(argv)
    except (json.JSONDecodeError, FileNotFoundError, OSError) as exc:
        print(
            f"ERROR: could not load profile input: {exc}", file=sys.stderr
        )
        print(
            json.dumps(
                {
                    "valid": False,
                    "schema_version": None,
                    "missing_keys": [],
                    "error": f"Could not load profile: {exc}",
                }
            )
        )
        return 1

    if not isinstance(profile, dict):
        print(
            f"ERROR: profile must be a JSON object, got {type(profile).__name__}",
            file=sys.stderr,
        )
        print(
            json.dumps(
                {
                    "valid": False,
                    "schema_version": None,
                    "missing_keys": [],
                    "error": (
                        f"Profile must be a JSON object, got "
                        f"{type(profile).__name__}"
                    ),
                }
            )
        )
        return 1

    missing = [k for k in REQUIRED_KEYS if k not in profile]
    schema_version = profile.get("schema_version")
    valid = not missing and schema_version == 1

    if not valid:
        reasons = []
        if missing:
            reasons.append(f"missing keys: {', '.join(missing)}")
        if schema_version != 1:
            reasons.append(f"schema_version is {schema_version!r} (expected 1)")
        print(
            f"ERROR: profile invalid — {'; '.join(reasons)}", file=sys.stderr
        )

    print(
        json.dumps(
            {
                "valid": valid,
                "schema_version": schema_version,
                "missing_keys": missing,
            },
            indent=2,
        )
    )
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
