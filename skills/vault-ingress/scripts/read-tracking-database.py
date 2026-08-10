#!/usr/bin/env python3
"""Read one tracking database through the owner strict snapshot contract.

Every agent-driven read of `tracking-database.json` goes through this script,
so its failure path is the one every agent sees. A `TrackingDatabaseIOError`
message names the host database path, and a decoder failure interpolates the
rejected content — a duplicate key, a non-round-trippable number — verbatim.
Failures therefore report a typed code from the shared closed vocabulary in
`tracking_database_io.DATABASE_READ_DIAGNOSTICS`, never the exception text.

Stdout: one JSON object — the database and its digest, or a typed failure.
Stderr: one path-neutral line drawn from that same closed vocabulary.
Exit 0 on success, 2 when the database cannot be read.
"""

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
    DATABASE_READ_DIAGNOSTICS,
    DATABASE_READ_FALLBACK,
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
        # The assessment's own message names the offending record; the typed
        # code is what a caller routes on, and it is what gets reported.
        raise TrackingDatabaseIOError(
            "tracking database owner assessment failed",
            reason_code="owner_assessment_failed",
        ) from exc
    if not assessment.usable:
        raise TrackingDatabaseIOError(
            "tracking database has no usable legacy/current owner state",
            reason_code="owner_state_unusable",
        )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": True,
        "database_path": str(snapshot.path),
        "sha256": snapshot.sha256,
        "database": database,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("database", type=Path)
    args = parser.parse_args(argv)
    try:
        report = execute(args.database)
    except TrackingDatabaseIOError as exc:
        # Never echo the exception: decoder messages carry the host database
        # path and the rejected key or value verbatim. Route the typed reason
        # code through the shared closed vocabulary instead.
        code, message = DATABASE_READ_DIAGNOSTICS.get(
            exc.reason_code, DATABASE_READ_FALLBACK
        )
        print(
            json.dumps(
                {
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "ok": False,
                    "code": code,
                    "error": message,
                }
            )
        )
        print(f"tracking-database read failed: {message}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
