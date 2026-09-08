#!/usr/bin/env python3
"""Record the provider ceiling for every talk whose delivery date is unrecorded.

Usage: establish-date-provenance.py DATABASE [--apply --expected-sha256 SHA]
       [--as-of TIMEZONE_AWARE_ISO_TIME]

Default is a dry run. The report names every proposal, every talk this owner
cannot bound and why, and a coverage block that makes backlog progress
measurable across runs instead of re-derived by each audit (#430).

This owner writes `date_provenance` records only. It never writes a talk's
`date`, never fetches from a provider, and never invents a delivery day: a
provider upload bounds a recording, and only methods that establish a day may
supply one. Talks whose date is already comparable are left alone — their
provenance is a question about evidence a human holds, not one this owner can
answer from a stored upload date.

Stdout: one schema-v1 {schema_version, ok, ...} report. Exit 0 on a completed
plan or apply, 1 on a refused input or failed precondition, 2 on usage error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, NoReturn

from source_identity_matching import parse_catalog_date
from tracking_database import (
    DATE_PROVENANCE_RECORD_SCHEMA_VERSION,
    TrackingDatabaseError,
    require_current_tracking_database,
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
CEILING_METHOD = "provider_upload_ceiling"
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_SHA256 = re.compile(r"[0-9a-f]{64}")

# Why a talk this owner looked at received no proposal. Closed so a new refusal
# has to be named here rather than disappearing into a silent skip.
BLOCKED_REASONS = (
    "date_already_comparable",
    "date_present_but_uncomparable",
    "provenance_already_recorded",
    "no_provider_upload_date",
)


class DateProvenanceError(RuntimeError):
    """The owner refused an input; the message names the repair."""


def _upload_date(talk: Any) -> str | None:
    """Return the stored provider upload day, or None when there is not one."""
    identity = talk.get("source_identity")
    if not isinstance(identity, dict):
        return None
    value = identity.get("upload_date")
    if not isinstance(value, str) or not _ISO_DAY.fullmatch(value.strip()):
        return None
    stamped = value.strip()
    try:
        dt.date.fromisoformat(stamped)
    except ValueError:
        return None
    return stamped


def classify_talk(talk: Any, *, has_provenance: bool) -> str | None:
    """Name why a talk gets no ceiling, or None when one should be proposed.

    A talk whose date already parses is left alone: this owner knows only that
    the recording was published by some day, which says nothing about how a date
    that exists was arrived at, and one record per talk means writing a ceiling
    there would displace the real account.
    """
    if has_provenance:
        return "provenance_already_recorded"
    recorded = talk.get("date")
    if parse_catalog_date(recorded) is not None:
        return "date_already_comparable"
    absent = recorded is None or (isinstance(recorded, str) and not recorded.strip())
    if not absent:
        # Month precision and anything else the comparator refuses. The ceiling
        # would be unverifiable against it, so the reader refuses it too.
        return "date_present_but_uncomparable"
    if _upload_date(talk) is None:
        return "no_provider_upload_date"
    return None


def plan_ceilings(database: Any, *, established_at: str) -> dict[str, Any]:
    """Return the proposals, the refusals, and the coverage this run observed."""
    talks = database.get("talks")
    if not isinstance(talks, list):
        raise DateProvenanceError("tracking database has no readable talks array")
    recorded = {
        record.get("talk_filename")
        for record in database.get("date_provenance", [])
        if isinstance(record, dict)
    }
    proposals: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    comparable = 0
    for index, talk in enumerate(talks):
        if not isinstance(talk, dict):
            raise DateProvenanceError(f"talks[{index}] must be a JSON object")
        filename = talk.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            raise DateProvenanceError(f"talks[{index}] has no usable filename")
        if parse_catalog_date(talk.get("date")) is not None:
            comparable += 1
        reason = classify_talk(talk, has_provenance=filename in recorded)
        if reason is not None:
            blocked.append({"talk_filename": filename, "reason": reason})
            continue
        upload = _upload_date(talk)
        proposals.append(
            {
                "schema_version": DATE_PROVENANCE_RECORD_SCHEMA_VERSION,
                "talk_filename": filename,
                "method": CEILING_METHOD,
                "evidence": (
                    "stored source_identity.upload_date "
                    f"{upload} for provider video {talk.get('youtube_id')}"
                ),
                "established_at": established_at,
                "not_later_than": upload,
            }
        )
    proposals.sort(key=lambda record: record["talk_filename"])
    blocked.sort(key=lambda item: (item["talk_filename"], item["reason"]))
    return {
        "proposals": proposals,
        "blocked": blocked,
        "coverage": {
            "talks": len(talks),
            "with_comparable_date": comparable,
            "with_provenance_before": len(recorded),
            "with_provenance_after": len(recorded) + len(proposals),
            "blocked_by_reason": {
                reason: sum(1 for item in blocked if item["reason"] == reason)
                for reason in BLOCKED_REASONS
            },
        },
    }


def _validate_expected_digest(value: str) -> None:
    if not _SHA256.fullmatch(value):
        raise DateProvenanceError("--expected-sha256 must be 64 lowercase hex digits")


def _validate_as_of(value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DateProvenanceError(
            "--as-of must be a timezone-aware ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DateProvenanceError("--as-of must be a timezone-aware ISO-8601 timestamp")
    return value


def _backup_path(path: Path, input_sha256: str) -> Path:
    return path.with_name(f"{path.name}.{input_sha256[:12]}.bak")


def execute(
    path: Path,
    *,
    apply: bool,
    expected_sha256: str | None,
    as_of: str,
) -> dict[str, Any]:
    database_path = path.expanduser().absolute()
    if expected_sha256 is not None:
        _validate_expected_digest(expected_sha256)
    if apply and expected_sha256 is None:
        raise DateProvenanceError(
            "--apply requires --expected-sha256 from a dry-run report"
        )
    try:
        snapshot = snapshot_tracking_database(database_path)
        database = decode_json_object(snapshot)
    except TrackingDatabaseIOError as exc:
        raise DateProvenanceError(str(exc)) from exc
    database_path = snapshot.path
    if expected_sha256 is not None and expected_sha256 != snapshot.sha256:
        raise DateProvenanceError(
            "input sha256 precondition failed: "
            f"expected {expected_sha256}, found {snapshot.sha256}"
        )
    try:
        require_current_tracking_database(database)
    except TrackingDatabaseError as exc:
        raise DateProvenanceError(
            f"{exc}; migrate the tracking database before establishing provenance"
        ) from exc

    plan = plan_ceilings(database, established_at=as_of)
    changed = bool(plan["proposals"])
    candidate = json.loads(json.dumps(database))
    if changed:
        candidate.setdefault("date_provenance", [])
        candidate["date_provenance"] = sorted(
            [*candidate["date_provenance"], *plan["proposals"]],
            key=lambda record: record["talk_filename"],
        )
        # The reader is the authority on whether these records are admissible.
        # Validating the candidate before it is rendered keeps a refusal a
        # refusal rather than a file the next reader rejects.
        try:
            require_current_tracking_database(candidate)
        except TrackingDatabaseError as exc:
            raise DateProvenanceError(
                f"proposed provenance would not validate: {exc}"
            ) from exc
    try:
        rendered = render_json_object(candidate) if changed else snapshot.raw
    except (TrackingDatabaseError, TrackingDatabaseIOError) as exc:
        raise DateProvenanceError(str(exc)) from exc

    predicted_backup = _backup_path(database_path, snapshot.sha256) if changed else None
    output_sha256 = hashlib.sha256(rendered).hexdigest()
    database_written = False
    durability_state = "dry_run"
    warnings: list[str] = []
    reported_backup = str(predicted_backup) if predicted_backup is not None else None

    if apply:
        try:
            result = commit_tracking_database(
                snapshot,
                rendered,
                backup=(
                    BackupRequest(path=predicted_backup, input_sha256=snapshot.sha256)
                    if predicted_backup is not None
                    else None
                ),
            )
        except TrackingDatabaseIOError as exc:
            raise DateProvenanceError(str(exc)) from exc
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
        "established_at": as_of,
        "changed": changed,
        "database_written": database_written,
        "backup": reported_backup,
        "output_sha256": output_sha256,
        "durability_state": durability_state,
        "warnings": warnings,
        **plan,
    }


def _fail(message: str) -> NoReturn:
    """Refuse on both channels: stdout stays the report, stderr the diagnostic."""
    print(
        json.dumps(
            {"schema_version": REPORT_SCHEMA_VERSION, "ok": False, "error": message},
            indent=2,
        )
    )
    print(f"establish-date-provenance failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-sha256")
    parser.add_argument(
        "--as-of",
        help="timezone-aware ISO-8601 stamp for established_at; defaults to now",
    )
    args = parser.parse_args(argv)
    try:
        as_of = (
            _validate_as_of(args.as_of)
            if args.as_of is not None
            else dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        )
        report = execute(
            args.database,
            apply=args.apply,
            expected_sha256=args.expected_sha256,
            as_of=as_of,
        )
    except DateProvenanceError as exc:
        _fail(str(exc))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
