#!/usr/bin/env python3
"""Apply an evidence-backed source repair plan to a tracking database.

The plan is optimistic and auditable: every repair names a talk, states why it
is needed, declares the exact values it expects to replace, and then lists
top-level fields to set or clear.  The complete plan is validated before any
mutation.  ``--apply`` creates a byte-for-byte backup and replaces the database
atomically; without it, the command is a dry run.

Plan schema v1::

    {
      "schema_version": 1,
      "repairs": [{
        "filename": "talk.md",
        "reason": "provider metadata identifies a non-delivery clip",
        "expect": {"video_url": "https://youtu.be/AbCdEfGhI_1"},
        "clear": ["video_url", "youtube_id"],
        "set": {"transcript_source": "none"}
      }]
    }

Use ``{"$missing": true}`` as an expected value when field absence (rather
than JSON null) is part of the safety check.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


PLAN_SCHEMA_VERSION = 1
MISSING_MARKER = {"$missing": True}
ALLOWED_FIELDS = frozenset({
    "video_url",
    "youtube_id",
    "slides_url",
    "google_drive_id",
    "pptx_path",
    "slides_local_path",
    "slides_pdf_path",
    "pdf_path",
    "transcript_path",
    "transcript_source",
    "slide_source",
    "source_identity",
    "source_relation",
    "source_rejections",
    "status",
    "reprocess_reason",
})
ALLOWED_REPAIR_STATUSES = frozenset({
    "pending", "needs-reprocessing", "processed_partial", "skipped_no_sources",
})


class SourceRepairError(ValueError):
    """A deterministic plan, database, or state mismatch."""


def load_object(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SourceRepairError(f"cannot read {label} {path}: {exc}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SourceRepairError(
            f"{label} {path} is invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(value, dict):
        raise SourceRepairError(f"{label} must be a JSON object")
    return value, raw


def require_nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceRepairError(f"{label} must be a nonempty string")
    return value.strip()


def validate_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise SourceRepairError(
            f"plan schema_version must be {PLAN_SCHEMA_VERSION}"
        )
    repairs = plan.get("repairs")
    if not isinstance(repairs, list) or not repairs:
        raise SourceRepairError("plan repairs must be a nonempty array")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, repair in enumerate(repairs):
        label = f"repairs[{index}]"
        if not isinstance(repair, dict):
            raise SourceRepairError(f"{label} must be an object")
        filename = require_nonempty(repair.get("filename"), f"{label}.filename")
        require_nonempty(repair.get("reason"), f"{label}.reason")
        if filename in seen:
            raise SourceRepairError(
                f"{label}.filename duplicates {filename!r}; combine changes per talk"
            )
        seen.add(filename)

        expect = repair.get("expect")
        set_values = repair.get("set", {})
        clear = repair.get("clear", [])
        if not isinstance(expect, dict) or not expect:
            raise SourceRepairError(f"{label}.expect must be a nonempty object")
        if not isinstance(set_values, dict):
            raise SourceRepairError(f"{label}.set must be an object")
        if (
            not isinstance(clear, list)
            or any(not isinstance(field, str) or not field for field in clear)
            or len(clear) != len(set(clear))
        ):
            raise SourceRepairError(f"{label}.clear must contain unique field names")
        touched = set(set_values) | set(clear)
        if not touched:
            raise SourceRepairError(f"{label} must set or clear at least one field")
        unsupported = (set(expect) | touched) - ALLOWED_FIELDS
        if unsupported:
            raise SourceRepairError(
                f"{label} contains unsupported fields: {sorted(unsupported)}"
            )
        unchecked = touched - set(expect)
        if unchecked:
            raise SourceRepairError(
                f"{label}.expect must cover every changed field; missing "
                f"{sorted(unchecked)}"
            )
        overlap = set(set_values) & set(clear)
        if overlap:
            raise SourceRepairError(
                f"{label} both sets and clears: {sorted(overlap)}"
            )
        if "status" in set_values and set_values["status"] not in ALLOWED_REPAIR_STATUSES:
            raise SourceRepairError(
                f"{label}.set.status must be one of {sorted(ALLOWED_REPAIR_STATUSES)}"
            )
        normalized.append(repair)
    return normalized


def _matches_expected(talk: dict[str, Any], field: str, expected: Any) -> bool:
    if expected == MISSING_MARKER:
        return field not in talk
    return field in talk and talk[field] == expected


def build_repaired_database(
    database: dict[str, Any], repairs: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    talks = database.get("talks")
    if not isinstance(talks, list) or any(not isinstance(talk, dict) for talk in talks):
        raise SourceRepairError("database talks must be an array of objects")
    by_filename: dict[str, dict[str, Any]] = {}
    for talk in talks:
        filename = talk.get("filename")
        if not isinstance(filename, str) or not filename:
            raise SourceRepairError("every talk must have a nonempty filename")
        if filename in by_filename:
            raise SourceRepairError(f"database has duplicate filename {filename!r}")
        by_filename[filename] = talk

    result = copy.deepcopy(database)
    result_by_filename = {talk["filename"]: talk for talk in result["talks"]}
    changes: list[dict[str, Any]] = []
    errors: list[str] = []
    for repair in repairs:
        filename = repair["filename"]
        current = by_filename.get(filename)
        if current is None:
            errors.append(f"{filename}: talk not found")
            continue
        claim = current.get("_queue_claim")
        if current.get("status") == "reprocessing-inflight" or (
            isinstance(claim, dict) and claim.get("state") == "claimed"
        ):
            errors.append(f"{filename}: source repair cannot change an active queue claim")
            continue
        for field, expected in repair["expect"].items():
            if not _matches_expected(current, field, expected):
                actual = current[field] if field in current else MISSING_MARKER
                errors.append(
                    f"{filename}.{field}: expected {expected!r}, found {actual!r}"
                )

    if errors:
        raise SourceRepairError("repair preconditions failed:\n- " + "\n- ".join(errors))

    for repair in repairs:
        filename = repair["filename"]
        talk = result_by_filename[filename]
        before: dict[str, Any] = {}
        after: dict[str, Any] = {}
        for field in repair.get("clear", []):
            if field in talk:
                before[field] = talk[field]
                talk.pop(field)
                after[field] = MISSING_MARKER
        for field, value in repair.get("set", {}).items():
            before[field] = talk[field] if field in talk else MISSING_MARKER
            talk[field] = copy.deepcopy(value)
            after[field] = value
        changes.append({
            "filename": filename,
            "reason": repair["reason"],
            "before": before,
            "after": after,
        })
    return result, changes


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    installed = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        installed = True
    finally:
        if not installed:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def backup_original(database_path: Path, raw: str, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = backup_dir / f"{database_path.stem}.source-repair-{stamp}.json"
    counter = 1
    while candidate.exists():
        candidate = backup_dir / (
            f"{database_path.stem}.source-repair-{stamp}-{counter}.json"
        )
        counter += 1
    candidate.write_text(raw, encoding="utf-8")
    return candidate


def execute(
    database_path: Path, plan_path: Path, *, apply: bool,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    database, raw = load_object(database_path, "database")
    plan, _ = load_object(plan_path, "repair plan")
    repairs = validate_plan(plan)
    repaired, changes = build_repaired_database(database, repairs)
    backup_path = None
    if apply:
        target_backup_dir = backup_dir or database_path.parent / ".backups"
        backup_path = backup_original(database_path, raw, target_backup_dir)
        rendered = json.dumps(repaired, indent=2, ensure_ascii=False) + "\n"
        atomic_write(database_path, rendered)
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "mode": "apply" if apply else "dry-run",
        "database": str(database_path.resolve(strict=False)),
        "plan": str(plan_path.resolve(strict=False)),
        "repair_count": len(changes),
        "backup": str(backup_path.resolve()) if backup_path else None,
        "changes": changes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("database", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        report = execute(
            args.database, args.plan, apply=args.apply, backup_dir=args.backup_dir,
        )
    except (SourceRepairError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        print(f"source repair failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
