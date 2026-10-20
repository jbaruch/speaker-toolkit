#!/usr/bin/env python3
"""Project only task-relevant speaker configuration into agent context.

Usage: read-task-profile.py <speaker-profile.json> --task export [--allow-missing]

The original profile stays the input to owner validators and history consumers;
this read-only projection is neither validation nor historical authorization.
TASK_FIELDS owns the supported tasks and selected field paths. History, badges,
visual-style history and secrets are never emitted. Missing optional fields stay
absent; no defaults or credentials are invented.

Exit 0 emits {task, profile_available, profile}. An absent profile is accepted
only with --allow-missing. Malformed/unreadable present profiles always refuse:
exit 1, actionable stderr, empty stdout. No files are written.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

COMMON_FIELDS = ("schema_version", "generated_date")
TASK_FIELDS = {
    "authoring": (
        "speaker",
        "presentation_modes",
        "presentation_engines",
        "rhetoric_defaults",
        "confirmed_intents",
        "pacing",
        "instrument_catalog",
        "infrastructure.presentation_file_convention",
        "publishing_process.shownotes",
    ),
    "cfp": (
        "speaker",
        "rhetoric_defaults",
        "confirmed_intents",
        "instrument_catalog.verbal_signatures",
    ),
    "catalog": ("speaker",),
    "build-pptx": ("design_rules", "infrastructure"),
    "build-presenterm": ("presentation_engines", "design_rules"),
    "edit": ("design_rules", "infrastructure"),
    "export": (
        "publishing_process.export_format",
        "publishing_process.export_method",
        "publishing_process.export_script",
    ),
    "resources": ("publishing_process.shownotes",),
    "qr": ("publishing_process.qr_code", "publishing_process.shownotes.url"),
    "delivery": ("publishing_process.additional_steps",),
    "publishing": ("publishing_process",),
}


def project(profile: dict, task: str) -> dict:
    """Copy selected branches, preserving present values without exposing siblings."""
    selected: dict = {}
    for field in (*COMMON_FIELDS, *TASK_FIELDS[task]):
        parts = field.split(".")
        value = profile
        for part in parts:
            if not isinstance(value, dict) or part not in value:
                break
            value = value[part]
        else:
            target = selected
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = deepcopy(value)
    return selected


def read_profile(path: Path, task: str, *, allow_missing: bool = False) -> dict:
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if allow_missing:
            return {"task": task, "profile_available": False, "profile": {}}
        raise
    profile = json.loads(source)
    if not isinstance(profile, dict) or not profile:
        raise ValueError("profile must be a non-empty JSON object")
    return {"task": task, "profile_available": True, "profile": project(profile, task)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("profile", type=Path)
    parser.add_argument("--task", choices=tuple(TASK_FIELDS), required=True)
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = read_profile(args.profile, args.task, allow_missing=args.allow_missing)
    except (OSError, UnicodeError, ValueError) as exc:
        print(
            f"FAIL: cannot select {args.task} profile context from {args.profile}: "
            f"{exc}; repair the present profile through vault-profile, or supply "
            "a readable profile path",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
