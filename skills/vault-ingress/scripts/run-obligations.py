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
        --run-id <id> --now <ISO-8601> --profile-inputs changed|unchanged \
        [--profile-refreshed]
    run-obligations.py <tracking-database.json> record-report \
        --run-id <id> --now <ISO-8601> --report-file <delivered-report.md>
    run-obligations.py <tracking-database.json> pending
    run-obligations.py <tracking-database.json> status --run-id <id>

Every successful command emits one JSON object on stdout and exits 0. Known
input/state errors emit a JSON error object on stdout, an actionable diagnostic
on stderr, and exit 2. Mutating commands rewrite the ledger atomically under the
same sibling lock discipline as the tracking database, only when state changed.

Ledger: ``{vault_root}/ingress-obligations.json`` (schema 1, run records
schema 1), owned by vault-ingress. Delivered reports are copied to
``{vault_root}/ingress-reports/{run_id}.{digest}.md`` and bound to the ledger
by SHA-256. ``pending`` also names the newest persisted run that never opened
its obligations (a crash between the merge and ``open``) and every deferred
offer with the speaker's return condition, so both can be raised again.
Field meanings, transitions, and the reader/writer contract live in
``skills/vault-ingress/references/schemas-obligations.md``.

Recency policy (the delivery-recency buckets the clarification handoff keys on)
is encoded once, here, in the constants below. ``open`` and ``record-offer``
read each talk's ``date`` from the tracking database and compute
``days_since_delivery`` from ``--now``; the stored recency is a snapshot
labeled ``recency_as_of``, refreshed by ``record-offer`` at the moment the offer
is made and frozen from then on. The handoff never recomputes ``today - date``
by hand and reads the offer mode from ``record-offer``'s own output.
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

from queue_claim_contract import QueueClaimContractError, require_queue_identifier
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
PROFILE_FILENAME = "speaker-profile.json"
LEDGER_SCHEMA_VERSION = 1
RUN_RECORD_SCHEMA_VERSION = 1
# The report copy is content-addressed: ``{run_id}.{digest prefix}.md`` with the
# run id reduced to a safe filename stem, so two deliveries never overwrite each
# other and a ledger-edited run id can never name a path outside the directory.
REPORT_DIGEST_PREFIX = 12
_SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]")
# What ``persist-results.py`` stamps on the claim it closes; a run whose claims
# carry it but that has no ledger record persisted talks and never opened its
# obligations (a crash between the merge and ``open``).
PERSISTED_RELEASE_REASON = "return_persisted"

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

NEXT_OPEN = "open_obligations"
NEXT_OFFER = "offer_clarification"
NEXT_AWAIT = "await_disposition"
NEXT_SESSION = "complete_clarification_session"
NEXT_REPORT = "deliver_end_report"
NEXT_NONE = "none"

PROFILE_INPUTS_CHANGED = "changed"
PROFILE_INPUTS_UNCHANGED = "unchanged"
PROFILE_INPUTS = (PROFILE_INPUTS_CHANGED, PROFILE_INPUTS_UNCHANGED)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def safe_report_stem(run_id: str) -> str:
    return _SAFE_STEM.sub("_", run_id) or "run"


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
        run_id = _require_identifier(
            run.get("run_id"), f"obligations ledger {path} runs[{index}].run_id"
        )
        if run_id in seen:
            raise RunObligationsError(
                f"obligations ledger {path} runs[{index}] duplicates run_id {run_id!r}",
                reason_code="ledger_invalid",
            )
        seen.add(run_id)
        _validate_run(run, f"obligations ledger {path} run {run_id!r}")
    return payload


def _invalid(label: str, detail: str) -> RunObligationsError:
    return RunObligationsError(f"{label} {detail}", reason_code="ledger_invalid")


def _require_keys(record: Any, keys: tuple[str, ...], label: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise _invalid(label, "must be an object")
    for key in keys:
        if key not in record:
            raise _invalid(label, f"lacks {key}")
    return record


def _require_optional_text(value: object, label: str) -> None:
    if value is not None and not isinstance(value, str):
        raise _invalid(label, "must be a string or null")


def _require_choice(value: object, choices: Any, label: str) -> str:
    """Type before membership: a list or object must not raise TypeError."""
    if not isinstance(value, str):
        raise _invalid(label, "must be a string")
    if value not in choices:
        raise _invalid(label, f"{value!r} is not one of the known values")
    return value


def _require_identifier(value: object, label: str) -> str:
    """Run ids share the queue claim's identifier contract."""
    try:
        return require_queue_identifier(value, label)
    except QueueClaimContractError as exc:
        raise _invalid(label, str(exc).removeprefix(label).strip()) from exc


def _validate_run(run: dict[str, Any], label: str) -> None:
    """Refuse a run record whose shape a command would otherwise trip over."""
    _require_keys(
        run,
        (
            "schema_version",
            "opened_at",
            "updated_at",
            "talks",
            "clarification",
            "end_report",
            "completed_at",
        ),
        label,
    )
    version = run["schema_version"]
    if type(version) is not int or version != RUN_RECORD_SCHEMA_VERSION:
        raise _invalid(
            label,
            f"has run-record schema_version {version!r}; this script reads "
            f"{RUN_RECORD_SCHEMA_VERSION} only",
        )
    for key in ("opened_at", "updated_at"):
        if not isinstance(run[key], str):
            raise _invalid(label, f"{key} must be a string")
    _require_optional_text(run["completed_at"], f"{label} completed_at")
    if not isinstance(run["talks"], list):
        raise _invalid(label, "talks must be an array")
    for position, talk in enumerate(run["talks"]):
        entry = _require_keys(
            talk,
            (
                "filename",
                "status",
                "delivery_date",
                "days_since_delivery",
                "recency_bucket",
            ),
            f"{label} talks[{position}]",
        )
        if not isinstance(entry["filename"], str):
            raise _invalid(label, f"talks[{position}].filename must be a string")
        _require_choice(
            entry["recency_bucket"],
            OFFER_MODE_BY_BUCKET,
            f"{label} talks[{position}].recency_bucket",
        )
    clarification = _require_keys(
        run["clarification"],
        (
            "state",
            "offer_mode",
            "topics",
            "recency_as_of",
            "offered_at",
            "resolved_at",
            "return_condition",
            "session",
        ),
        f"{label} clarification",
    )
    state = _require_choice(
        clarification["state"], CLARIFICATION_STATES, f"{label} clarification.state"
    )
    _require_choice(
        clarification["offer_mode"],
        {*OFFER_MODE_PRECEDENCE, OFFER_MODE_NONE},
        f"{label} clarification.offer_mode",
    )
    if not isinstance(clarification["topics"], list) or not all(
        isinstance(topic, str) for topic in clarification["topics"]
    ):
        raise _invalid(label, "clarification.topics must be an array of strings")
    for key in ("recency_as_of", "offered_at", "resolved_at", "return_condition"):
        _require_optional_text(clarification[key], f"{label} clarification.{key}")
    session = clarification["session"]
    if state == STATE_ACCEPTED:
        session = _require_keys(
            session,
            ("state", "completed_at", "profile_inputs", "profile_refreshed"),
            f"{label} clarification.session",
        )
        _require_choice(
            session["state"],
            {SESSION_PENDING, SESSION_COMPLETED},
            f"{label} clarification.session.state",
        )
        _require_optional_text(
            session["completed_at"], f"{label} clarification.session.completed_at"
        )
        if session["profile_inputs"] is not None:
            _require_choice(
                session["profile_inputs"],
                PROFILE_INPUTS,
                f"{label} clarification.session.profile_inputs",
            )
        if session["profile_refreshed"] not in (None, True, False):
            raise _invalid(
                label,
                "clarification.session.profile_refreshed must be a boolean or null",
            )
    elif session is not None:
        raise _invalid(label, "clarification.session belongs to an accepted offer only")
    report = _require_keys(
        run["end_report"],
        ("state", "delivered_at", "report_path", "report_sha256"),
        f"{label} end_report",
    )
    _require_choice(
        report["state"], {REPORT_OWED, REPORT_DELIVERED}, f"{label} end_report.state"
    )
    for key in ("delivered_at", "report_path", "report_sha256"):
        _require_optional_text(report[key], f"{label} end_report.{key}")


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
) -> dict[str, Any]:
    """Commit the ledger atomically against the generation that was read.

    The returned fields say what the write achieved. ``durability_state`` other
    than ``durable`` or ``unchanged`` means the bytes were installed but a
    verification or directory fsync failed; every such warning also goes to
    stderr so a caller reading only the exit code still sees it.
    """
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
    for warning in result.warnings:
        print(f"WARNING: obligations ledger {path}: {warning}", file=sys.stderr)
    return {
        "written": bool(result.installed),
        "durability_state": result.durability_state,
        "warnings": list(result.warnings),
    }


def write_report_copy(
    directory: Path, run_id: str, digest: str, content: bytes
) -> tuple[Path, bool]:
    """Install the delivered report beside the ledger, durably.

    Returns the content-addressed path and whether this call created it. An
    existing copy with the same bytes is left alone, so a replayed or racing
    delivery of identical text never rewrites it.
    """
    target = (
        directory / f"{safe_report_stem(run_id)}.{digest[:REPORT_DIGEST_PREFIX]}.md"
    )
    try:
        if target.exists() and target.read_bytes() == content:
            return target, False
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, staged = tempfile.mkstemp(
            prefix=f".{target.stem}.", suffix=".tmp", dir=directory
        )
    except OSError as exc:
        raise RunObligationsError(
            f"cannot stage the report copy under {directory}: {exc} — make it "
            "a writable directory (or remove whatever occupies that path) and "
            "re-run record-report; the delivered text was not recorded",
            reason_code="report_copy_failed",
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, target)
        directory_descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        if os.path.exists(staged):
            os.unlink(staged)
        raise RunObligationsError(
            f"cannot write the report copy {target}: {exc} — free the space or "
            "fix the permissions and re-run record-report; the delivered text "
            "was not recorded",
            reason_code="report_copy_failed",
        ) from exc
    return target, True


# ── Database context ──────────────────────────────────────────────────


class Context:
    """The database-bound paths every command resolves the same way."""

    def __init__(self, raw_database: str) -> None:
        self.database_path = materialize_native_authority(
            raw_database, authority="database_path"
        )
        self.database = self.refresh()
        self.vault_root = resolve_vault_root_authority(
            database_path=self.database_path, config=self.database.get("config")
        )
        self.ledger_path = self.vault_root / LEDGER_FILENAME
        self.reports_directory = self.vault_root / REPORTS_DIRECTORY
        self.profile_path = self.vault_root / PROFILE_FILENAME

    def refresh(self) -> dict[str, Any]:
        """Re-read the current database generation right before it is used."""
        try:
            snapshot = snapshot_tracking_database(self.database_path)
            database = decode_json_object(snapshot)
            require_current_tracking_database(database)
        except (TrackingDatabaseIOError, TrackingDatabaseError) as exc:
            raise RunObligationsError(
                str(exc), reason_code="database_unusable"
            ) from exc
        self.database = database
        return database

    def persisted_runs(self) -> dict[str, dict[str, Any]]:
        """Runs whose closed claims say persist-results.py merged their talks."""
        runs: dict[str, dict[str, Any]] = {}
        for record in self.database["talks"]:
            if not isinstance(record, dict):
                continue
            claims = [record.get("_queue_claim")]
            history = record.get("_queue_claim_history")
            if isinstance(history, list):
                claims.extend(history)
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                if (
                    claim.get("state") != "completed"
                    or claim.get("release_reason") != PERSISTED_RELEASE_REASON
                    or not isinstance(claim.get("run_id"), str)
                    or not isinstance(claim.get("released_at"), str)
                ):
                    continue
                try:
                    released = parse_timestamp(claim["released_at"], "released_at")
                except RunObligationsError:
                    continue
                entry = runs.setdefault(
                    claim["run_id"],
                    {
                        "run_id": claim["run_id"],
                        "talks": [],
                        "latest_released_at": None,
                    },
                )
                filename = record.get("filename")
                if isinstance(filename, str) and filename not in entry["talks"]:
                    entry["talks"].append(filename)
                stamp = render_timestamp(released)
                if (
                    entry["latest_released_at"] is None
                    or stamp > entry["latest_released_at"]
                ):
                    entry["latest_released_at"] = stamp
        for entry in runs.values():
            entry["talks"].sort()
        return runs

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
    try:
        return require_queue_identifier(value, "--run-id")
    except QueueClaimContractError as exc:
        raise RunObligationsError(str(exc), reason_code="invalid_arguments") from exc


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
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "run_id": run_id,
        "opened_at": now,
        "updated_at": now,
        "talks": [],
        "clarification": {
            "state": STATE_OWED,
            "offer_mode": OFFER_MODE_NONE,
            "topics": [],
            "recency_as_of": None,
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
        "recency_as_of": run["clarification"]["recency_as_of"],
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
    context.refresh()
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
        _apply_recency(clarification, talks, stamp)
    if json.dumps(run, sort_keys=True) != before:
        run["updated_at"] = stamp
    outcome = store_ledger(context.ledger_path, snapshot, ledger)
    return {"ok": True, "ledger_path": str(context.ledger_path), **outcome, "run": run}


def _apply_recency(
    clarification: dict[str, Any], talks: list[dict[str, Any]], stamp: str
) -> None:
    mode = offer_mode_for(talks)
    clarification["offer_mode"] = mode
    clarification["recency_as_of"] = stamp
    clarification["state"] = (
        STATE_NOT_APPLICABLE if mode == OFFER_MODE_NONE else STATE_OWED
    )


def _transition(
    context: Context,
    args: argparse.Namespace,
    mutate: Any,
    *,
    on_commit_failure: Any = None,
) -> dict[str, Any]:
    now = parse_timestamp(args.now, "--now")
    stamp = render_timestamp(now)
    run_id = require_run_id(args.run_id)
    snapshot, ledger = load_ledger(context.ledger_path)
    run = find_run(ledger, run_id)
    before = json.dumps(run, sort_keys=True)
    extras = mutate(run, stamp, now) or {}
    if json.dumps(run, sort_keys=True) != before:
        run["updated_at"] = stamp
    try:
        outcome = store_ledger(context.ledger_path, snapshot, ledger)
    except RunObligationsError:
        if on_commit_failure is not None:
            on_commit_failure()
        raise
    return {
        "ok": True,
        "ledger_path": str(context.ledger_path),
        **outcome,
        **extras,
        "run": run,
    }


def command_record_offer(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    topics = [topic for topic in (args.topic or []) if topic.strip()]

    def mutate(run: dict[str, Any], stamp: str, now: datetime) -> dict[str, Any]:
        clarification = run["clarification"]
        if clarification["state"] != STATE_OWED:
            raise RunObligationsError(
                f"run {run['run_id']!r} clarification is "
                f"{clarification['state']!r}; record-offer applies only while "
                "the offer is owed",
                reason_code="invalid_transition",
            )
        # The stored recency is a snapshot from the last ``open``. The offer is
        # being made now, against the current database, so refresh before
        # freezing: a run resumed weeks later must not promise an inline
        # session for a talk that is no longer same-week.
        context.refresh()
        talks = [
            describe_talk(context, str(talk["filename"]), now) for talk in run["talks"]
        ]
        run["talks"] = talks
        _apply_recency(clarification, talks, stamp)
        if clarification["state"] == STATE_NOT_APPLICABLE:
            # Persisted as not applicable: the database changed since the run
            # opened and no analyzed talk remains, so nothing is asked and the
            # report is no longer blocked on an offer.
            return {
                "offered": False,
                "reason": (
                    f"run {run['run_id']!r} no longer has an analyzed talk to "
                    "clarify; recorded as not applicable, nothing to ask"
                ),
            }
        clarification["state"] = STATE_OFFERED
        clarification["offered_at"] = stamp
        clarification["topics"] = topics
        return {"offered": True}

    return _transition(context, args, mutate)


def command_record_disposition(
    context: Context, args: argparse.Namespace
) -> dict[str, Any]:
    disposition = args.disposition
    return_condition = args.return_condition

    def mutate(run: dict[str, Any], stamp: str, _now: datetime) -> None:
        clarification = run["clarification"]
        if clarification["state"] not in {STATE_OFFERED, STATE_DEFERRED}:
            raise RunObligationsError(
                f"run {run['run_id']!r} clarification is "
                f"{clarification['state']!r}; a disposition needs a recorded "
                "offer first, and only a deferred offer is answered again",
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
            {
                "state": SESSION_PENDING,
                "completed_at": None,
                "profile_inputs": None,
                "profile_refreshed": None,
            }
            if disposition == STATE_ACCEPTED
            else None
        )

    return _transition(context, args, mutate)


def command_record_session(
    context: Context, args: argparse.Namespace
) -> dict[str, Any]:
    refreshed = bool(args.profile_refreshed)
    inputs = args.profile_inputs

    def mutate(run: dict[str, Any], stamp: str, _now: datetime) -> None:
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
        if (
            inputs == PROFILE_INPUTS_CHANGED
            and not refreshed
            and context.profile_path.exists()
        ):
            raise RunObligationsError(
                f"the session changed profile inputs and {context.profile_path} "
                "exists; regenerate the profile (Step 7) first, then record the "
                "session with --profile-refreshed",
                reason_code="profile_refresh_required",
            )
        session["state"] = SESSION_COMPLETED
        session["completed_at"] = stamp
        session["profile_inputs"] = inputs
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
    created: list[Path] = []

    def mutate(run: dict[str, Any], stamp: str, _now: datetime) -> None:
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
        copied, fresh = write_report_copy(
            context.reports_directory, run["run_id"], digest, content
        )
        if fresh:
            created.append(copied)
        report["state"] = REPORT_DELIVERED
        report["delivered_at"] = stamp
        report["report_path"] = str(copied)
        report["report_sha256"] = digest
        run["completed_at"] = stamp

    def discard_copy() -> None:
        # The ledger commit lost its generation race; the copy it would have
        # bound is an orphan. Leave a copy another delivery already owns alone.
        for path in created:
            try:
                path.unlink()
            except OSError as exc:
                print(
                    f"WARNING: could not remove the unbound report copy {path}: {exc}",
                    file=sys.stderr,
                )

    return _transition(context, args, mutate, on_commit_failure=discard_copy)


def unrecorded_run(
    persisted: dict[str, dict[str, Any]], ledger: dict[str, Any]
) -> dict[str, Any] | None:
    """The newest persisted run with no ledger record, if it postdates the ledger.

    Every run recorded later than an unrecorded one moved past it under this
    contract, so only the newest unrecorded run, newer than every recorded
    run's ``opened_at``, is reported as unfinished. Older history is history.
    """
    recorded = {run["run_id"] for run in ledger["runs"]}
    latest_recorded = max((run["opened_at"] for run in ledger["runs"]), default=None)
    candidates = [
        entry
        for run_id, entry in persisted.items()
        if run_id not in recorded
        and (latest_recorded is None or entry["latest_released_at"] > latest_recorded)
    ]
    if not candidates:
        return None
    newest = max(candidates, key=lambda entry: entry["latest_released_at"])
    return {**newest, "next_action": NEXT_OPEN}


def command_pending(context: Context, _args: argparse.Namespace) -> dict[str, Any]:
    _snapshot, ledger = load_ledger(context.ledger_path)
    pending = [
        summarize(run) for run in ledger["runs"] if next_action(run) != NEXT_NONE
    ]
    deferred = [
        {
            "run_id": run["run_id"],
            "return_condition": run["clarification"]["return_condition"],
            "topics": run["clarification"]["topics"],
            "resolved_at": run["clarification"]["resolved_at"],
        }
        for run in ledger["runs"]
        if run["clarification"]["state"] == STATE_DEFERRED
    ]
    unrecorded = unrecorded_run(context.persisted_runs(), ledger)
    return {
        "ok": True,
        "ledger_path": str(context.ledger_path),
        "ledger_present": context.ledger_path.exists(),
        "pending": pending,
        "count": len(pending),
        "deferred_offers": deferred,
        "unrecorded_runs": [unrecorded] if unrecorded is not None else [],
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
        "--profile-inputs",
        choices=PROFILE_INPUTS,
        required=True,
        help="whether the session changed confirmed intents, goals, or summary",
    )
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
