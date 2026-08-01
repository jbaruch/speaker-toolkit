#!/usr/bin/env python3
"""Read one tracking database through the owner strict snapshot contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from tracking_database import (
    TrackingDatabaseError,
    assess_tracking_database,
)
from tracking_database_io import (
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)


REPORT_SCHEMA_VERSION = 1


def execute(path: Path) -> dict[str, object]:
    snapshot = snapshot_tracking_database(path)
    database = decode_json_object(snapshot)
    try:
        assessment = assess_tracking_database(database)
    except TrackingDatabaseError as exc:
        raise TrackingDatabaseIOError(
            f"tracking database owner assessment failed: {exc}"
        ) from exc
    if not assessment.usable:
        reasons = ", ".join(assessment.reason_codes) or "unsupported_owner_state"
        raise TrackingDatabaseIOError(
            "tracking database has no usable legacy/current owner state "
            f"({reasons})"
        )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": True,
        "database_path": str(snapshot.path),
        "sha256": snapshot.sha256,
        "database": database,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("database", type=Path)
    args = parser.parse_args(argv)
    try:
        report = execute(args.database)
    except TrackingDatabaseIOError as exc:
        print(
            json.dumps(
                {
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "ok": False,
                    "error": str(exc),
                }
            )
        )
        print(f"tracking-database read failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
