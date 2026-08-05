#!/usr/bin/env python3
"""Migrate one tracking database with a hash precondition and exact backup."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import NoReturn

from tracking_database import (
    TrackingDatabaseError,
    migrate_tracking_database,
)
from tracking_database_io import (
    BackupRequest,
    TrackingDatabaseIOError,
    commit_tracking_database,
    decode_json_object,
    render_json_object,
    snapshot_tracking_database,
)


REPORT_SCHEMA_VERSION = 1


class TrackingDatabaseMigrationError(ValueError):
    """Migration input or filesystem state failed a precondition."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Route command-line mistakes through the JSON error contract."""

    def error(self, message: str) -> NoReturn:
        raise TrackingDatabaseMigrationError(f"invalid arguments: {message}")


def _backup_path(path: Path, digest: str) -> Path:
    return path.parent / ".backups" / f"{path.name}.owner-migration-{digest}.bak"


def _validate_expected_digest(value: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise TrackingDatabaseMigrationError(
            "--expected-sha256 must be a 64-character lowercase hexadecimal digest"
        )


def execute(
    path: Path,
    *,
    apply: bool,
    expected_sha256: str | None,
) -> dict[str, object]:
    database_path = path.expanduser().absolute()
    if expected_sha256 is not None:
        _validate_expected_digest(expected_sha256)
    if apply and expected_sha256 is None:
        raise TrackingDatabaseMigrationError(
            "--apply requires --expected-sha256 from a dry-run report"
        )

    try:
        snapshot = snapshot_tracking_database(database_path)
        database = decode_json_object(snapshot)
    except TrackingDatabaseIOError as exc:
        raise TrackingDatabaseMigrationError(str(exc)) from exc
    database_path = snapshot.path
    if expected_sha256 is not None and expected_sha256 != snapshot.sha256:
        raise TrackingDatabaseMigrationError(
            "input sha256 precondition failed: "
            f"expected {expected_sha256}, found {snapshot.sha256}"
        )

    try:
        migration = migrate_tracking_database(database)
        rendered = (
            render_json_object(migration.database)
            if migration.changed
            else snapshot.raw
        )
    except (TrackingDatabaseError, TrackingDatabaseIOError) as exc:
        raise TrackingDatabaseMigrationError(str(exc)) from exc

    predicted_backup = (
        _backup_path(database_path, snapshot.sha256) if migration.changed else None
    )
    output_sha256 = hashlib.sha256(rendered).hexdigest()
    database_written = False
    durability_state = "dry_run"
    warnings: list[str] = []
    reported_backup = str(predicted_backup) if predicted_backup is not None else None

    if apply:
        backup_request = (
            BackupRequest(
                path=predicted_backup,
                input_sha256=snapshot.sha256,
            )
            if predicted_backup is not None
            else None
        )
        try:
            result = commit_tracking_database(
                snapshot,
                rendered,
                backup=backup_request,
            )
        except TrackingDatabaseIOError as exc:
            raise TrackingDatabaseMigrationError(str(exc)) from exc
        output_sha256 = result.output_sha256
        database_written = result.installed
        durability_state = result.durability_state
        warnings = list(result.warnings)
        reported_backup = result.backup

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": True,
        "mode": "apply" if apply else "dry-run",
        "database": str(database_path),
        "input_sha256": snapshot.sha256,
        "from_schema_version": migration.from_schema_version,
        "to_schema_version": migration.to_schema_version,
        "changed": migration.changed,
        "database_written": database_written,
        "backup": reported_backup,
        "output_sha256": output_sha256,
        "record_counts": dict(migration.record_counts),
        "durability_state": durability_state,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-sha256")
    try:
        args = parser.parse_args(argv)
        report = execute(
            args.database,
            apply=args.apply,
            expected_sha256=args.expected_sha256,
        )
    except TrackingDatabaseMigrationError as exc:
        print(
            json.dumps(
                {
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "ok": False,
                    "error": str(exc),
                }
            )
        )
        print(f"tracking-database migration failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
