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
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from tracking_database import (
    TrackingDatabaseError,
    require_current_tracking_database,
)
from tracking_database_io import (
    BackupRequest,
    TrackingDatabaseIOError,
    TrackingDatabaseSnapshot,
    commit_tracking_database,
    decode_json_object,
    json_values_equal,
    render_json_object,
    snapshot_tracking_database,
)


PLAN_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 2
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
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise SourceRepairError(f"cannot read {label} {path}: {exc}") from exc

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SourceRepairError(
                    f"{label} {path} contains duplicate object key {key!r}"
                )
            result[key] = value
        return result

    def reject_non_finite(value: str) -> None:
        raise SourceRepairError(
            f"{label} {path} contains non-standard JSON number {value}"
        )

    try:
        raw = raw_bytes.decode("utf-8")
        value = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_finite,
        )
    except SourceRepairError:
        raise
    except UnicodeDecodeError as exc:
        raise SourceRepairError(f"{label} {path} is not valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SourceRepairError(
            f"{label} {path} is invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(value, dict):
        raise SourceRepairError(f"{label} must be a JSON object")
    return value, raw


def load_database(
    path: Path,
) -> tuple[dict[str, Any], TrackingDatabaseSnapshot]:
    """Load strict JSON and retain the exact generation used for validation."""
    try:
        snapshot = snapshot_tracking_database(path)
        return decode_json_object(snapshot), snapshot
    except TrackingDatabaseIOError as exc:
        raise SourceRepairError(str(exc)) from exc


def require_nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceRepairError(f"{label} must be a nonempty string")
    return value.strip()


def validate_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    if not json_values_equal(plan.get("schema_version"), PLAN_SCHEMA_VERSION):
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
    if json_values_equal(expected, MISSING_MARKER):
        return field not in talk
    return field in talk and json_values_equal(talk[field], expected)


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
            if field in talk and json_values_equal(talk[field], value):
                continue
            before[field] = talk[field] if field in talk else MISSING_MARKER
            talk[field] = copy.deepcopy(value)
            after[field] = value
        if before:
            changes.append({
                "filename": filename,
                "reason": repair["reason"],
                "before": before,
                "after": after,
            })
    return result, changes


def atomic_write(
    path: Path,
    text: str | bytes,
    *,
    expected_snapshot: TrackingDatabaseSnapshot | None = None,
    backup: BackupRequest | None = None,
):
    """Commit text against the exact generation captured before validation."""
    try:
        snapshot = expected_snapshot or snapshot_tracking_database(path)
        return commit_tracking_database(
            snapshot,
            text.encode("utf-8") if isinstance(text, str) else text,
            backup=backup,
        )
    except TrackingDatabaseIOError as exc:
        raise SourceRepairError(str(exc)) from exc


def execute(
    database_path: Path, plan_path: Path, *, apply: bool,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    database, database_snapshot = load_database(database_path)
    try:
        require_current_tracking_database(database)
    except TrackingDatabaseError as exc:
        raise SourceRepairError(str(exc)) from exc
    plan, _ = load_object(plan_path, "repair plan")
    repairs = validate_plan(plan)
    repaired, changes = build_repaired_database(database, repairs)
    if changes:
        try:
            rendered = render_json_object(repaired)
        except TrackingDatabaseIOError as exc:
            raise SourceRepairError(str(exc)) from exc
    else:
        rendered = database_snapshot.raw
    output_sha256 = hashlib.sha256(rendered).hexdigest()
    backup_path: str | None = None
    database_written = False
    durability_state = "dry_run"
    warnings: list[str] = []
    try:
        require_current_tracking_database(repaired)
    except TrackingDatabaseError as exc:
        raise SourceRepairError(
            f"repair would violate the current tracking schema: {exc}"
        ) from exc
    if apply:
        target_backup_dir = backup_dir or database_path.parent / ".backups"
        backup_request = BackupRequest(
            path=(
                target_backup_dir
                / f"{database_path.name}.source-repair-"
                f"{database_snapshot.sha256}.bak"
            ),
            input_sha256=database_snapshot.sha256,
        )
        result = atomic_write(
            database_path,
            rendered,
            expected_snapshot=database_snapshot,
            backup=backup_request,
        )
        backup_path = result.backup
        output_sha256 = result.output_sha256
        database_written = result.installed
        durability_state = result.durability_state
        warnings = list(result.warnings)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "mode": "apply" if apply else "dry-run",
        "database": str(database_path.resolve(strict=False)),
        "plan": str(plan_path.resolve(strict=False)),
        "repair_count": len(changes),
        "backup": backup_path,
        "input_sha256": database_snapshot.sha256,
        "output_sha256": output_sha256,
        "database_written": database_written,
        "durability_state": durability_state,
        "warnings": warnings,
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
        print(
            json.dumps(
                {
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "ok": False,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        print(f"source repair failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
