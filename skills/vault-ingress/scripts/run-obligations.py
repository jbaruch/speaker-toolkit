#!/usr/bin/env python3
"""Own the durable human-facing obligations of one vault-ingress run.

Processing completion and run completion are different events. A queue claim
closes when ``persist-results.py`` merges a batch; that says nothing about the
speaker. This ledger records what the run still owes the speaker after the
merge: the clarification offer and its disposition, the clarification session
when the offer is accepted, and the end report. A run is complete only when
every obligation carries an explicit disposition. Silence, elapsed time, and an
invitation merely sent never resolve an obligation, so an interrupted run shows
up in ``pending`` until the speaker answers or the report is delivered.

Usage:
    run-obligations.py <tracking-database.json> open \
        --run-id <id> --now <ISO-8601> --talk <talk.md> [--talk ...]
    run-obligations.py <tracking-database.json> record-offer \
        --run-id <id> --now <ISO-8601> [--topic <text> ...]
    run-obligations.py <tracking-database.json> record-disposition \
        --run-id <id> --now <ISO-8601> \
        --disposition accepted|declined|deferred [--return-condition <text>]
    run-obligations.py <tracking-database.json> record-session \
        --run-id <id> --now <ISO-8601> [--profile-refreshed]
    run-obligations.py <tracking-database.json> record-report \
        --run-id <id> --now <ISO-8601> --report-file <delivered-report.md>
    run-obligations.py <tracking-database.json> pending
    run-obligations.py <tracking-database.json> status --run-id <id>

Every successful command emits one JSON object on stdout and exits 0. Known
input/state errors emit a JSON error object on stdout, an actionable diagnostic
on stderr, and exit 2. Mutating commands rewrite the ledger atomically under the
same sibling lock discipline as the tracking database, only when state changed.

Ledger: ``{vault_root}/ingress-obligations.json`` (schema 1), owned by
vault-ingress. Delivered reports are copied to
``{vault_root}/ingress-reports/{run_id}.md`` and bound to the ledger by SHA-256.
Field meanings, transitions, and the reader/writer contract live in
``skills/vault-ingress/references/schemas-obligations.md``.

Recency policy (the delivery-recency buckets the clarification handoff keys on)
is encoded once, here, in the constants below. ``open`` reads each talk's
``date`` from the tracking database and computes ``days_since_delivery`` from
``--now``; the handoff never recomputes ``today - date`` by hand.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

from tracking_database import (
    TrackingDatabaseError,
    require_current_tracking_database,
)
from tracking_database_io import (
    TrackingDatabaseIOError,
    TrackingDatabaseSnapshot,
    decode_json_object,
    initialize_tracking_database,
    snapshot_tracking_database,
    write_json_object,
)
from vault_root_authority import (
    VaultRootAuthorityError,
    materialize_native_authority,
    resolve_vault_root_authority,
)

LEDGER_FILENAME = "ingress-obligations.json"
REPORTS_DIRECTORY = "ingress-reports"
LEDGER_SCHEMA_VERSION = 1

# Talk statuses whose results can feed a clarification session. Skipped talks
# are recorded for the end report's scope but never generate an offer.
ANALYZED_STATUSES = frozenset({"processed", "processed_partial"})

# Delivery-recency buckets, inclusive upper bounds in whole days since delivery.
# ``same_week`` gets the inline offer; ``recent`` a recommended full session;
# ``older`` a recommended compressed session. A talk with no usable delivery
# date is ``unknown`` and treated like ``recent``: recommend, never auto-invoke.
SAME_WEEK_MAX_DAYS = 7
RECENT_MAX_DAYS = 30
BUCKET_SAME_WEEK = "same_week"
BUCKET_RECENT = "recent"
BUCKET_OLDER = "older"
BUCKET_UNKNOWN = "unknown"
OFFER_MODE_INLINE = "inline"
OFFER_MODE_RECOMMEND_FULL = "recommend_full"
OFFER_MODE_RECOMMEND_COMPRESSED = "recommend_compressed"
OFFER_MODE_NONE = "none"
OFFER_MODE_BY_BUCKET = {
    BUCKET_SAME_WEEK: OFFER_MODE_INLINE,
    BUCKET_RECENT: OFFER_MODE_RECOMMEND_FULL,
    BUCKET_UNKNOWN: OFFER_MODE_RECOMMEND_FULL,
    BUCKET_OLDER: OFFER_MODE_RECOMMEND_COMPRESSED,
}
# Strongest offer wins when a run mixes buckets.
OFFER_MODE_PRECEDENCE = (
    OFFER_MODE_INLINE,
    OFFER_MODE_RECOMMEND_FULL,
    OFFER_MODE_RECOMMEND_COMPRESSED,
)

STATE_OWED = "owed"
STATE_OFFERED = "offered"
STATE_ACCEPTED = "accepted"
STATE_DECLINED = "declined"
STATE_DEFERRED = "deferred"
STATE_NOT_APPLICABLE = "not_applicable"
CLARIFICATION_STATES = frozenset(
    {
        STATE_OWED,
        STATE_OFFERED,
        STATE_ACCEPTED,
        STATE_DECLINED,
        STATE_DEFERRED,
        STATE_NOT_APPLICABLE,
    }
)
DISPOSITIONS = (STATE_ACCEPTED, STATE_DECLINED, STATE_DEFERRED)
SESSION_PENDING = "pending"
SESSION_COMPLETED = "completed"
REPORT_OWED = "owed"
REPORT_DELIVERED = "delivered"

NEXT_OFFER = "offer_clarification"
NEXT_AWAIT = "await_disposition"
NEXT_SESSION = "complete_clarification_session"
NEXT_REPORT = "deliver_end_report"
NEXT_NONE = "none"

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class RunObligationsError(Exception):
    """A known input or state error, reported on stdout as JSON and exit 2."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class JsonArgumentParser(argparse.ArgumentParser):
    """Convert argparse failures into the script's JSON error contract."""

    def error(self, message: str) -> Any:
        raise RunObligationsError(
            f"invalid arguments: {message}", reason_code="invalid_arguments"
        )


def parse_timestamp(value: object, label: str) -> datetime:
    """Parse a timezone-aware ISO-8601 timestamp and normalize it to UTC."""
    if not isinstance(value, str) or not value:
        raise RunObligationsError(
            f"{label} must be a non-empty ISO-8601 timestamp",
            reason_code="invalid_timestamp",
        )
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        moment = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise RunObligationsError(
            f"{label} {value!r} is malformed — use a timezone-aware ISO-8601 "
            "timestamp such as 2026-09-14T18:00:00+00:00",
            reason_code="invalid_timestamp",
        ) from exc
    if moment.tzinfo is None:
        raise RunObligationsError(
            f"{label} {value!r} has no timezone — append an explicit UTC offset",
            reason_code="invalid_timestamp",
        )
    return moment.astimezone(timezone.utc).replace(microsecond=0)


def render_timestamp(moment: datetime) -> str:
    return moment.isoformat()


def parse_delivery_date(value: object) -> date | None:
    """Return the talk's delivery date, or None when it is absent or unusable."""
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def recency_bucket(days_since_delivery: int | None) -> str:
    """Bucket a delivery age; a missing or future date is ``unknown``."""
    if days_since_delivery is None or days_since_delivery < 0:
        return BUCKET_UNKNOWN
    if days_since_delivery <= SAME_WEEK_MAX_DAYS:
        return BUCKET_SAME_WEEK
    if days_since_delivery <= RECENT_MAX_DAYS:
        return BUCKET_RECENT
    return BUCKET_OLDER


def offer_mode_for(talks: list[dict[str, Any]]) -> str:
    """Pick the strongest offer among the run's analyzed talks."""
    modes = {
        OFFER_MODE_BY_BUCKET[str(talk["recency_bucket"])]
        for talk in talks
        if talk["status"] in ANALYZED_STATUSES
    }
    for mode in OFFER_MODE_PRECEDENCE:
        if mode in modes:
            return mode
    return OFFER_MODE_NONE


def next_action(run: dict[str, Any]) -> str:
    clarification = run["clarification"]
    state = clarification["state"]
    if state == STATE_OWED:
        return NEXT_OFFER
    if state == STATE_OFFERED:
        return NEXT_AWAIT
    if state == STATE_ACCEPTED and clarification["session"]["state"] != (
        SESSION_COMPLETED
    ):
        return NEXT_SESSION
    if run["end_report"]["state"] == REPORT_OWED:
        return NEXT_REPORT
    return NEXT_NONE


def clarification_resolved(run: dict[str, Any]) -> bool:
    clarification = run["clarification"]
    state = clarification["state"]
    if state in {STATE_DECLINED, STATE_DEFERRED, STATE_NOT_APPLICABLE}:
        return True
    if state == STATE_ACCEPTED:
        return clarification["session"]["state"] == SESSION_COMPLETED
    return False


# ── Ledger IO ─────────────────────────────────────────────────────────


def empty_ledger() -> dict[str, Any]:
    return {"schema_version": LEDGER_SCHEMA_VERSION, "runs": []}


def validate_ledger(payload: object, path: Path) -> dict[str, Any]:
    """Accept only the owner's current ledger shape."""
    if not isinstance(payload, dict):
        raise RunObligationsError(
            f"obligations ledger {path} must be a JSON object",
            reason_code="ledger_invalid",
        )
    version = payload.get("schema_version")
    if type(version) is not int or version != LEDGER_SCHEMA_VERSION:
        raise RunObligationsError(
            f"obligations ledger {path} has schema_version {version!r}; this "
            f"script reads schema {LEDGER_SCHEMA_VERSION} only — update "
            "speaker-toolkit or inspect the ledger by hand",
            reason_code="ledger_schema_unsupported",
        )
    runs = payload.get("runs")
    if not isinstance(runs, list):
        raise RunObligationsError(
            f"obligations ledger {path} must carry a runs array",
            reason_code="ledger_invalid",
        )
    seen: set[str] = set()
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            raise RunObligationsError(
                f"obligations ledger {path} runs[{index}] must be an object",
                reason_code="ledger_invalid",
            )
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or run_id in seen:
            raise RunObligationsError(
                f"obligations ledger {path} runs[{index}] has a missing or "
                "duplicate run_id",
                reason_code="ledger_invalid",
            )
        seen.add(run_id)
        for key in ("talks", "clarification", "end_report"):
            if key not in run:
                raise RunObligationsError(
                    f"obligations ledger {path} run {run_id!r} lacks {key}",
                    reason_code="ledger_invalid",
                )
        if run["clarification"].get("state") not in CLARIFICATION_STATES:
            raise RunObligationsError(
                f"obligations ledger {path} run {run_id!r} has an unknown "
                "clarification state",
                reason_code="ledger_invalid",
            )
    return payload


def load_ledger(path: Path) -> tuple[TrackingDatabaseSnapshot | None, dict[str, Any]]:
    """Read the ledger with its generation, or an empty ledger when absent."""
    if not path.exists():
        return None, empty_ledger()
    try:
        snapshot = snapshot_tracking_database(path)
        payload = decode_json_object(snapshot)
    except TrackingDatabaseIOError as exc:
        raise RunObligationsError(
            f"cannot read obligations ledger {path}: {exc}",
            reason_code="ledger_unreadable",
        ) from exc
    return snapshot, validate_ledger(payload, path)


def store_ledger(
    path: Path, snapshot: TrackingDatabaseSnapshot | None, payload: dict[str, Any]
) -> bool:
    """Commit the ledger atomically against the generation that was read."""
    try:
        if snapshot is None:
            result = initialize_tracking_database(path, payload)
        else:
            result = write_json_object(snapshot, payload)
    except TrackingDatabaseIOError as exc:
        raise RunObligationsError(
            f"cannot write obligations ledger {path}: {exc}",
            reason_code="ledger_write_failed",
        ) from exc
    return bool(result.installed)


def write_report_copy(directory: Path, run_id: str, content: bytes) -> Path:
    """Place the delivered report beside the ledger with an atomic replace."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{run_id}.md"
    descriptor, staged = tempfile.mkstemp(
        prefix=f".{run_id}.", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, target)
    except OSError:
        if os.path.exists(staged):
            os.unlink(staged)
        raise
    return target


# ── Database context ──────────────────────────────────────────────────


class Context:
    """The database-bound paths every command resolves the same way."""

    def __init__(self, raw_database: str) -> None:
        self.database_path = materialize_native_authority(
            raw_database, authority="database_path"
        )
        try:
            snapshot = snapshot_tracking_database(self.database_path)
            database = decode_json_object(snapshot)
            require_current_tracking_database(database)
        except (TrackingDatabaseIOError, TrackingDatabaseError) as exc:
            raise RunObligationsError(
                str(exc), reason_code="database_unusable"
            ) from exc
        self.database = database
        self.vault_root = resolve_vault_root_authority(
            database_path=self.database_path, config=database.get("config")
        )
        self.ledger_path = self.vault_root / LEDGER_FILENAME
        self.reports_directory = self.vault_root / REPORTS_DIRECTORY

    def talk(self, filename: str) -> dict[str, Any]:
        for record in self.database["talks"]:
            if isinstance(record, dict) and record.get("filename") == filename:
                return record
        raise RunObligationsError(
            f"talk {filename!r} is not in {self.database_path}; pass the exact "
            "filenames persist-results.py merged for this batch",
            reason_code="talk_not_found",
        )


def find_run(ledger: dict[str, Any], run_id: str) -> dict[str, Any]:
    for run in ledger["runs"]:
        if run["run_id"] == run_id:
            return run
    raise RunObligationsError(
        f"run {run_id!r} has no obligations record; run `open` for it after "
        "persisting its first batch",
        reason_code="run_not_found",
    )


def require_run_id(value: str) -> str:
    if not _RUN_ID.match(value):
        raise RunObligationsError(
            f"run id {value!r} must be 1-128 characters of letters, digits, "
            "'.', '_' or '-' and start with a letter or digit",
            reason_code="invalid_arguments",
        )
    return value


def describe_talk(context: Context, filename: str, now: datetime) -> dict[str, Any]:
    record = context.talk(filename)
    delivered = parse_delivery_date(record.get("date"))
    days = (now.date() - delivered).days if delivered is not None else None
    return {
        "filename": filename,
        "status": record.get("status"),
        "delivery_date": delivered.isoformat() if delivered is not None else None,
        "days_since_delivery": days,
        "recency_bucket": recency_bucket(days),
    }


def new_run(run_id: str, now: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "opened_at": now,
        "updated_at": now,
        "talks": [],
        "clarification": {
            "state": STATE_OWED,
            "offer_mode": OFFER_MODE_NONE,
            "topics": [],
            "offered_at": None,
            "resolved_at": None,
            "return_condition": None,
            "session": None,
        },
        "end_report": {
            "state": REPORT_OWED,
            "delivered_at": None,
            "report_path": None,
            "report_sha256": None,
        },
        "completed_at": None,
    }


def summarize(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run["run_id"],
        "opened_at": run["opened_at"],
        "next_action": next_action(run),
        "clarification_state": run["clarification"]["state"],
        "offer_mode": run["clarification"]["offer_mode"],
        "end_report_state": run["end_report"]["state"],
        "talk_count": len(run["talks"]),
    }


# ── Commands ──────────────────────────────────────────────────────────


def command_open(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    now = parse_timestamp(args.now, "--now")
    stamp = render_timestamp(now)
    run_id = require_run_id(args.run_id)
    filenames = list(dict.fromkeys(args.talk))
    if not filenames:
        raise RunObligationsError(
            "open requires at least one --talk filename",
            reason_code="invalid_arguments",
        )
    snapshot, ledger = load_ledger(context.ledger_path)
    try:
        run = find_run(ledger, run_id)
    except RunObligationsError:
        run = new_run(run_id, stamp)
        ledger["runs"].append(run)
    if run["completed_at"] is not None:
        raise RunObligationsError(
            f"run {run_id!r} completed at {run['completed_at']}; open a new "
            "run id for further processing",
            reason_code="invalid_transition",
        )
    before = json.dumps(run, sort_keys=True)
    clarification = run["clarification"]
    recency_open = clarification["state"] in {STATE_OWED, STATE_NOT_APPLICABLE}
    # Recency is frozen once the offer is made; until then the newest ``--now``
    # decides, so a resumed run does not over-promise an inline session for a
    # talk that is no longer same-week.
    talks = [
        describe_talk(context, str(talk["filename"]), now) if recency_open else talk
        for talk in run["talks"]
        if talk["filename"] not in filenames
    ]
    talks.extend(describe_talk(context, filename, now) for filename in filenames)
    talks.sort(key=lambda talk: str(talk["filename"]))
    run["talks"] = talks
    if recency_open:
        mode = offer_mode_for(talks)
        clarification["offer_mode"] = mode
        clarification["state"] = (
            STATE_NOT_APPLICABLE if mode == OFFER_MODE_NONE else STATE_OWED
        )
    if json.dumps(run, sort_keys=True) != before:
        run["updated_at"] = stamp
    written = store_ledger(context.ledger_path, snapshot, ledger)
    return {
        "ok": True,
        "ledger_path": str(context.ledger_path),
        "written": written,
        "run": run,
    }


def _transition(
    context: Context,
    args: argparse.Namespace,
    mutate: Any,
) -> dict[str, Any]:
    now = parse_timestamp(args.now, "--now")
    stamp = render_timestamp(now)
    run_id = require_run_id(args.run_id)
    snapshot, ledger = load_ledger(context.ledger_path)
    run = find_run(ledger, run_id)
    before = json.dumps(run, sort_keys=True)
    mutate(run, stamp)
    if json.dumps(run, sort_keys=True) != before:
        run["updated_at"] = stamp
    written = store_ledger(context.ledger_path, snapshot, ledger)
    return {
        "ok": True,
        "ledger_path": str(context.ledger_path),
        "written": written,
        "run": run,
    }


def command_record_offer(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    topics = [topic for topic in (args.topic or []) if topic.strip()]

    def mutate(run: dict[str, Any], stamp: str) -> None:
        clarification = run["clarification"]
        if clarification["state"] != STATE_OWED:
            raise RunObligationsError(
                f"run {run['run_id']!r} clarification is "
                f"{clarification['state']!r}; record-offer applies only while "
                "the offer is owed",
                reason_code="invalid_transition",
            )
        clarification["state"] = STATE_OFFERED
        clarification["offered_at"] = stamp
        clarification["topics"] = topics

    return _transition(context, args, mutate)


def command_record_disposition(
    context: Context, args: argparse.Namespace
) -> dict[str, Any]:
    disposition = args.disposition
    return_condition = args.return_condition

    def mutate(run: dict[str, Any], stamp: str) -> None:
        clarification = run["clarification"]
        if clarification["state"] != STATE_OFFERED:
            raise RunObligationsError(
                f"run {run['run_id']!r} clarification is "
                f"{clarification['state']!r}; a disposition needs a recorded "
                "offer first, and an offer is answered once",
                reason_code="invalid_transition",
            )
        if disposition == STATE_DEFERRED and not return_condition:
            raise RunObligationsError(
                "a deferred offer needs --return-condition naming when it is "
                "raised again",
                reason_code="invalid_arguments",
            )
        clarification["state"] = disposition
        clarification["resolved_at"] = stamp
        clarification["return_condition"] = (
            return_condition if disposition == STATE_DEFERRED else None
        )
        clarification["session"] = (
            {"state": SESSION_PENDING, "completed_at": None, "profile_refreshed": None}
            if disposition == STATE_ACCEPTED
            else None
        )

    return _transition(context, args, mutate)


def command_record_session(
    context: Context, args: argparse.Namespace
) -> dict[str, Any]:
    refreshed = bool(args.profile_refreshed)

    def mutate(run: dict[str, Any], stamp: str) -> None:
        clarification = run["clarification"]
        session = clarification["session"]
        if clarification["state"] != STATE_ACCEPTED or session is None:
            raise RunObligationsError(
                f"run {run['run_id']!r} has no accepted clarification session",
                reason_code="invalid_transition",
            )
        if session["state"] == SESSION_COMPLETED:
            raise RunObligationsError(
                f"run {run['run_id']!r} clarification session already completed "
                f"at {session['completed_at']}",
                reason_code="invalid_transition",
            )
        session["state"] = SESSION_COMPLETED
        session["completed_at"] = stamp
        session["profile_refreshed"] = refreshed

    return _transition(context, args, mutate)


def command_record_report(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    report_file = Path(args.report_file)
    try:
        content = report_file.read_bytes()
    except OSError as exc:
        raise RunObligationsError(
            f"cannot read the delivered report {report_file}: {exc}",
            reason_code="report_unreadable",
        ) from exc
    if not content.strip():
        raise RunObligationsError(
            f"delivered report {report_file} is empty; the end report is the "
            "speaker-facing text, not a placeholder",
            reason_code="report_empty",
        )
    digest = hashlib.sha256(content).hexdigest()

    def mutate(run: dict[str, Any], stamp: str) -> None:
        if not clarification_resolved(run):
            raise RunObligationsError(
                f"run {run['run_id']!r} still owes its clarification "
                f"disposition ({next_action(run)}); the end report is delivered "
                "after the speaker answers, so the report can carry any profile "
                "refresh the answers caused",
                reason_code="invalid_transition",
            )
        report = run["end_report"]
        if report["state"] == REPORT_DELIVERED and report["report_sha256"] == digest:
            return
        copied = write_report_copy(context.reports_directory, run["run_id"], content)
        report["state"] = REPORT_DELIVERED
        report["delivered_at"] = stamp
        report["report_path"] = str(copied)
        report["report_sha256"] = digest
        run["completed_at"] = stamp

    return _transition(context, args, mutate)


def command_pending(context: Context, _args: argparse.Namespace) -> dict[str, Any]:
    _snapshot, ledger = load_ledger(context.ledger_path)
    pending = [summarize(run) for run in ledger["runs"] if run["completed_at"] is None]
    return {
        "ok": True,
        "ledger_path": str(context.ledger_path),
        "ledger_present": context.ledger_path.exists(),
        "pending": pending,
        "count": len(pending),
    }


def command_status(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    _snapshot, ledger = load_ledger(context.ledger_path)
    run = find_run(ledger, require_run_id(args.run_id))
    return {
        "ok": True,
        "ledger_path": str(context.ledger_path),
        "summary": summarize(run),
        "run": run,
    }


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("database", help="tracking-database.json path")
    actions = parser.add_subparsers(
        dest="action", required=True, parser_class=JsonArgumentParser
    )

    def with_run(sub: argparse.ArgumentParser, *, now: bool = True) -> None:
        sub.add_argument("--run-id", required=True)
        if now:
            sub.add_argument(
                "--now", required=True, help="timezone-aware ISO-8601 event time"
            )

    opened = actions.add_parser(
        "open", help="record the run's obligations for a persisted batch"
    )
    with_run(opened)
    opened.add_argument(
        "--talk",
        action="append",
        default=[],
        help="filename persist-results.py merged; repeat per talk",
    )

    offer = actions.add_parser("record-offer", help="the offer was put to the speaker")
    with_run(offer)
    offer.add_argument(
        "--topic", action="append", help="candidate clarification topic; repeat"
    )

    disposition = actions.add_parser(
        "record-disposition", help="the speaker's explicit answer to the offer"
    )
    with_run(disposition)
    disposition.add_argument("--disposition", choices=DISPOSITIONS, required=True)
    disposition.add_argument(
        "--return-condition", help="when a deferred offer is raised again"
    )

    session = actions.add_parser(
        "record-session", help="the accepted clarification session completed"
    )
    with_run(session)
    session.add_argument(
        "--profile-refreshed",
        action="store_true",
        help="the speaker profile was regenerated from the session's answers",
    )

    report = actions.add_parser(
        "record-report", help="the end report was delivered to the speaker"
    )
    with_run(report)
    report.add_argument(
        "--report-file", required=True, help="the delivered report text"
    )

    actions.add_parser("pending", help="list runs with unresolved obligations")

    status = actions.add_parser("status", help="show one run's obligations")
    with_run(status, now=False)
    return parser


COMMANDS = {
    "open": command_open,
    "record-offer": command_record_offer,
    "record-disposition": command_record_disposition,
    "record-session": command_record_session,
    "record-report": command_record_report,
    "pending": command_pending,
    "status": command_status,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        context = Context(args.database)
        payload = COMMANDS[args.action](context, args)
    except (RunObligationsError, VaultRootAuthorityError) as exc:
        payload: dict[str, Any] = {"ok": False, "error": str(exc)}
        if isinstance(exc, RunObligationsError):
            payload["reason_code"] = exc.reason_code
        print(str(exc), file=sys.stderr)
        print(json.dumps(payload, ensure_ascii=False))
        return 2
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
