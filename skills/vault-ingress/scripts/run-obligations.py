#!/usr/bin/env python3
"""Own the durable human-facing obligations of one vault-ingress run.

Processing completion and run completion are different events. A queue claim
closes when ``persist-results.py`` merges a batch; that says nothing about the
speaker. This ledger records what the run still owes after the merge: the
downstream steps that turn persisted returns into rendered analyses, summary,
profile, and goal outcomes; the clarification offer and its disposition; the
clarification session when the offer is accepted; and the end report. A run is
complete only when every obligation carries an explicit disposition. Silence,
elapsed time, and an invitation merely sent never resolve an obligation, so an
interrupted run shows up in ``pending`` until the speaker answers or the report
is delivered.

Usage:
    run-obligations.py <tracking-database.json> adopt --now <ISO-8601>
    run-obligations.py <tracking-database.json> open \
        --run-id <id> --now <ISO-8601> (--talk <talk.md> ... | --talks-from <file>) \
        [--from-run <run id whose closed claim persisted the talks>]
    run-obligations.py <tracking-database.json> record-downstream \
        --run-id <id> --now <ISO-8601>
    run-obligations.py <tracking-database.json> record-offer \
        --run-id <id> --now <ISO-8601> [--topic <text> ...] [--topics-from <file>]
    run-obligations.py <tracking-database.json> record-disposition \
        --run-id <id> --now <ISO-8601> \
        --disposition accepted|declined|deferred [--return-condition <text>]
    run-obligations.py <tracking-database.json> record-session \
        --run-id <id> --now <ISO-8601> --profile-inputs changed|unchanged \
        [--profile-refreshed]
    run-obligations.py <tracking-database.json> record-report \
        --run-id <id> --now <ISO-8601> --report-file <delivered-report.md>
    run-obligations.py <tracking-database.json> dismiss \
        --run-id <id> --now <ISO-8601> (--reason <text> | --reason-from <file>)
    run-obligations.py <tracking-database.json> pending
    run-obligations.py <tracking-database.json> status --run-id <id>

Every successful command emits one JSON object on stdout and exits 0. Known
input/state errors emit a JSON error object on stdout, an actionable diagnostic
on stderr, and exit 2. Mutating commands rewrite the ledger atomically under the
same sibling lock discipline as the tracking database, only when state changed.
Every recording command is replay-safe: repeating it with the inputs it already
recorded is an unchanged success, so a caller that lost the first response can
retry; only a conflicting answer is refused.

Ledger: ``{vault_root}/ingress-obligations.json`` (schema 1, run records
schema 1), owned by vault-ingress and created by ``adopt``, which records
every claim already closed at adoption as history by its exact identity —
never by time, which ``persist-results.py --run-date`` can stamp at midnight —
so everything closed afterwards is reconciled. Delivered reports are copied to
``{vault_root}/ingress-reports/{stem}.{sha256}.md`` and bound to the ledger by
that digest. Each recorded talk carries the run id and release time of the
closed claim that persisted it, so ``pending`` can reconcile the ledger against
closed claims and name every persisted fact after the boundary that the ledger
does not cover (a whole run, a later batch of a recorded run, or a talk merged
again under the same run, that crashed between the merge and ``open``) without
repeating talks recovered under a fresh run id. An uncovered run stays listed
until it is opened or explicitly dismissed with a reason; a later run's
existence never stands in for either. ``pending`` also lists every deferred
offer with the speaker's return condition, so it can be raised again. Field
meanings, transitions, and the reader/writer contract live in
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
import stat
import sys
from typing import Any

from queue_claim_contract import (
    KNOWN_STATUSES,
    QueueClaimContractError,
    require_queue_identifier,
)
from tracking_database import (
    TrackingDatabaseError,
    require_current_tracking_database,
)
from tracking_database_io import (
    DATABASE_READ_DIAGNOSTICS,
    DATABASE_READ_FALLBACK,
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
# The report copy is content-addressed: ``{stem}.{sha256}.md`` with the run id
# reduced to a safe filename stem, so two deliveries never overwrite each
# other and a ledger-edited run id can never name a path outside the directory.
_SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]")
REPORT_STEM_MAX = 40
REPORT_STEM_PREFIX = 31
REPORT_STEM_HASH = 8
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
# What ``persist-results.py`` stamps on the claim it closes; a talk whose claim
# carries it persisted, and one the ledger does not cover crashed between the
# merge and ``open``.
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
OFFER_MODES = frozenset({*OFFER_MODE_PRECEDENCE, OFFER_MODE_NONE})

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
DOWNSTREAM_OWED = "owed"
DOWNSTREAM_COMPLETED = "completed"
REPORT_OWED = "owed"
REPORT_DELIVERED = "delivered"

NEXT_OPEN = "open_obligations"
NEXT_DOWNSTREAM = "complete_downstream_steps"
NEXT_OFFER = "offer_clarification"
NEXT_AWAIT = "await_disposition"
NEXT_SESSION = "complete_clarification_session"
NEXT_REPORT = "deliver_end_report"
NEXT_NONE = "none"
REASON_UNRECORDED = "unrecorded_run"
REASON_MISSING_TALKS = "missing_talks"
REASON_AFTER_COMPLETION = "talks_persisted_after_completion"
REASON_AFTER_ANSWER = "talks_persisted_after_answer"

PROFILE_INPUTS_CHANGED = "changed"
PROFILE_INPUTS_UNCHANGED = "unchanged"
PROFILE_INPUTS = (PROFILE_INPUTS_CHANGED, PROFILE_INPUTS_UNCHANGED)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class RunObligationsError(Exception):
    """A known input or state error, reported on stdout as JSON and exit 2."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def _io_failure(
    exc: TrackingDatabaseIOError, subject: str, reason_code: str
) -> RunObligationsError:
    """Report an io-layer failure through its closed vocabulary, never verbatim.

    Decoder messages carry the rejected key or value; only the typed reason
    code travels, mapped to the shared diagnostic text with the subject named.
    """
    _code, message = DATABASE_READ_DIAGNOSTICS.get(
        exc.reason_code, DATABASE_READ_FALLBACK
    )
    return RunObligationsError(
        f"{message.replace('tracking database', subject)} (io reason: {exc.reason_code})",
        reason_code=reason_code,
    )


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
    try:
        return moment.astimezone(timezone.utc).replace(microsecond=0)
    except (OverflowError, ValueError) as exc:
        raise RunObligationsError(
            f"{label} {value!r} is out of range once normalized to UTC — use a "
            "timestamp between years 1 and 9999 in UTC",
            reason_code="invalid_timestamp",
        ) from exc


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
    if run["downstream"]["state"] == DOWNSTREAM_OWED:
        return NEXT_DOWNSTREAM
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
    """A filename stem for the run id: sanitized, and bounded for long ids.

    A run id longer than ``REPORT_STEM_MAX`` characters keeps its first
    ``REPORT_STEM_PREFIX`` characters plus a short hash of the whole id, so the
    copy name stays under filesystem limits while distinct ids stay distinct.
    """
    stem = _SAFE_STEM.sub("_", run_id) or "run"
    if len(stem) <= REPORT_STEM_MAX:
        return stem
    tag = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:REPORT_STEM_HASH]
    return f"{stem[:REPORT_STEM_PREFIX]}-{tag}"


def clarification_resolved(run: dict[str, Any]) -> bool:
    clarification = run["clarification"]
    state = clarification["state"]
    if state in {STATE_DECLINED, STATE_DEFERRED, STATE_NOT_APPLICABLE}:
        return True
    if state == STATE_ACCEPTED:
        return clarification["session"]["state"] == SESSION_COMPLETED
    return False


# ── Ledger validation ─────────────────────────────────────────────────


def empty_ledger(
    adopted_at: str | None = None, adopted_facts: list[list[Any]] | None = None
) -> dict[str, Any]:
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "adopted_at": adopted_at,
        "adopted_facts": adopted_facts or [],
        "dismissed_runs": [],
        "runs": [],
    }


def fact_identity(fact: dict[str, Any], filename: str) -> list[Any]:
    """The exact identity of one persisted fact, as the ledger stores it."""
    return [
        str(fact["run_id"]),
        filename,
        str(fact["batch_id"]),
        int(fact["generation"]),
        str(fact["released_at"]),
    ]


def _validate_fact_identity(value: object, label: str) -> tuple[Any, ...]:
    if not isinstance(value, list) or len(value) != 5:
        raise _invalid(
            label, "must be [run_id, filename, batch_id, generation, released_at]"
        )
    run_id, filename, batch_id, generation, released_at = value
    _require_identifier(run_id, f"{label}[0]")
    if not isinstance(filename, str) or not filename:
        raise _invalid(label, "[1] filename must be a non-empty string")
    _require_identifier(batch_id, f"{label}[2]")
    if type(generation) is not int or generation < 0:
        raise _invalid(label, "[3] generation must be a non-negative integer")
    _require_timestamp(released_at, f"{label}[4]")
    return (run_id, filename, batch_id, generation, released_at)


def _validate_fact_list(value: object, label: str) -> set[tuple[Any, ...]]:
    if not isinstance(value, list):
        raise _invalid(label, "must be an array of fact identities")
    facts: set[tuple[Any, ...]] = set()
    for index, entry in enumerate(value):
        identity = _validate_fact_identity(entry, f"{label}[{index}]")
        if identity in facts:
            raise _invalid(label, f"[{index}] duplicates an identity")
        facts.add(identity)
    return facts


def require_adopted(ledger: dict[str, Any], path: Path) -> str:
    adopted_at = ledger.get("adopted_at")
    if not isinstance(adopted_at, str):
        raise RunObligationsError(
            f"obligations ledger {path} does not exist yet; run `adopt --now` "
            "at Step 1, before any batch, to set the reconciliation boundary",
            reason_code="ledger_not_adopted",
        )
    return adopted_at


def _invalid(label: str, detail: str) -> RunObligationsError:
    return RunObligationsError(f"{label} {detail}", reason_code="ledger_invalid")


def _require_keys(record: Any, keys: tuple[str, ...], label: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise _invalid(label, "must be an object")
    for key in keys:
        if key not in record:
            raise _invalid(label, f"lacks {key}")
    return record


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


def _require_timestamp(value: object, label: str) -> None:
    """Stored stamps are canonical UTC whole seconds, so they compare as text."""
    try:
        moment = parse_timestamp(value, label)
    except RunObligationsError as exc:
        raise _invalid(label, str(exc).removeprefix(label).strip()) from exc
    if render_timestamp(moment) != value:
        raise _invalid(
            label,
            f"{value!r} must be the canonical UTC form {render_timestamp(moment)!r}",
        )


def _require_timestamp_or_null(value: object, label: str, *, present: bool) -> None:
    """A stamp is required exactly when its state says the event happened."""
    if present:
        if value is None:
            raise _invalid(label, "must be set in this state")
        _require_timestamp(value, label)
    elif value is not None:
        raise _invalid(label, "must be null in this state")


def _require_null(value: object, label: str) -> None:
    if value is not None:
        raise _invalid(label, "must be null in this state")


def _require_bool(value: object, label: str) -> None:
    if not isinstance(value, bool):
        raise _invalid(label, "must be a boolean")


def _validate_talk(entry: Any, label: str) -> None:
    talk = _require_keys(
        entry,
        (
            "filename",
            "status",
            "delivery_date",
            "days_since_delivery",
            "recency_bucket",
            "claim_run_id",
            "claim_batch_id",
            "claim_generation",
            "claim_released_at",
        ),
        label,
    )
    if not isinstance(talk["filename"], str) or not talk["filename"]:
        raise _invalid(label, "filename must be a non-empty string")
    _require_choice(talk["status"], KNOWN_STATUSES, f"{label}.status")
    delivered = talk["delivery_date"]
    if delivered is not None and (
        not isinstance(delivered, str) or parse_delivery_date(delivered) is None
    ):
        raise _invalid(label, "delivery_date must be a YYYY-MM-DD string or null")
    days = talk["days_since_delivery"]
    if days is not None and (type(days) is not int):
        raise _invalid(label, "days_since_delivery must be an integer or null")
    _require_choice(
        talk["recency_bucket"], OFFER_MODE_BY_BUCKET, f"{label}.recency_bucket"
    )
    _require_identifier(talk["claim_run_id"], f"{label}.claim_run_id")
    _require_identifier(talk["claim_batch_id"], f"{label}.claim_batch_id")
    generation = talk["claim_generation"]
    if type(generation) is not int or generation < 0:
        raise _invalid(label, "claim_generation must be a non-negative integer")
    _require_timestamp(talk["claim_released_at"], f"{label}.claim_released_at")


def _validate_clarification(record: Any, label: str) -> None:
    clarification = _require_keys(
        record,
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
        label,
    )
    state = _require_choice(
        clarification["state"], CLARIFICATION_STATES, f"{label}.state"
    )
    _require_choice(clarification["offer_mode"], OFFER_MODES, f"{label}.offer_mode")
    if not isinstance(clarification["topics"], list) or not all(
        isinstance(topic, str) for topic in clarification["topics"]
    ):
        raise _invalid(label, "topics must be an array of strings")
    if clarification["recency_as_of"] is not None:
        _require_timestamp(clarification["recency_as_of"], f"{label}.recency_as_of")
    offered = state not in {STATE_OWED, STATE_NOT_APPLICABLE}
    resolved = state in {STATE_ACCEPTED, STATE_DECLINED, STATE_DEFERRED}
    _require_timestamp_or_null(
        clarification["offered_at"], f"{label}.offered_at", present=offered
    )
    _require_timestamp_or_null(
        clarification["resolved_at"], f"{label}.resolved_at", present=resolved
    )
    condition = clarification["return_condition"]
    if state == STATE_DEFERRED:
        if not isinstance(condition, str) or not condition.strip():
            raise _invalid(
                label, "return_condition must name when to raise a deferred offer"
            )
    else:
        _require_null(condition, f"{label}.return_condition")
    session = clarification["session"]
    if state != STATE_ACCEPTED:
        _require_null(session, f"{label}.session")
        return
    session = _require_keys(
        session,
        ("state", "completed_at", "profile_inputs", "profile_refreshed"),
        f"{label}.session",
    )
    session_state = _require_choice(
        session["state"], {SESSION_PENDING, SESSION_COMPLETED}, f"{label}.session.state"
    )
    completed = session_state == SESSION_COMPLETED
    _require_timestamp_or_null(
        session["completed_at"], f"{label}.session.completed_at", present=completed
    )
    if completed:
        _require_choice(
            session["profile_inputs"], PROFILE_INPUTS, f"{label}.session.profile_inputs"
        )
        _require_bool(
            session["profile_refreshed"], f"{label}.session.profile_refreshed"
        )
    else:
        _require_null(session["profile_inputs"], f"{label}.session.profile_inputs")
        _require_null(
            session["profile_refreshed"], f"{label}.session.profile_refreshed"
        )


def _validate_downstream(record: Any, label: str) -> None:
    downstream = _require_keys(record, ("state", "completed_at"), label)
    state = _require_choice(
        downstream["state"], {DOWNSTREAM_OWED, DOWNSTREAM_COMPLETED}, f"{label}.state"
    )
    _require_timestamp_or_null(
        downstream["completed_at"],
        f"{label}.completed_at",
        present=state == DOWNSTREAM_COMPLETED,
    )


def _validate_report(record: Any, label: str, expected_path: Any) -> bool:
    """``expected_path`` maps a digest to the copy path this vault binds."""
    report = _require_keys(
        record,
        ("state", "delivered_at", "report_path", "report_sha256", "reopened_at"),
        label,
    )
    delivered = (
        _require_choice(
            report["state"], {REPORT_OWED, REPORT_DELIVERED}, f"{label}.state"
        )
        == REPORT_DELIVERED
    )
    _require_timestamp_or_null(
        report["delivered_at"], f"{label}.delivered_at", present=delivered
    )
    if delivered:
        if not isinstance(report["report_sha256"], str) or not _SHA256_HEX.match(
            report["report_sha256"]
        ):
            raise _invalid(label, "report_sha256 must be a hex SHA-256 once delivered")
        bound = expected_path(report["report_sha256"])
        if report["report_path"] != bound:
            raise _invalid(
                label,
                f"report_path must be the bound copy {bound!r} for its digest",
            )
    else:
        _require_null(report["report_path"], f"{label}.report_path")
        _require_null(report["report_sha256"], f"{label}.report_sha256")
    if report["reopened_at"] is not None:
        _require_timestamp(report["reopened_at"], f"{label}.reopened_at")
    return delivered


def _validate_run(run: dict[str, Any], label: str, reports_directory: Path) -> None:
    """Refuse a run record whose shape a command would otherwise trip over."""
    _require_keys(
        run,
        (
            "schema_version",
            "opened_at",
            "updated_at",
            "talks",
            "downstream",
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
        _require_timestamp(run[key], f"{label} {key}")
    if not isinstance(run["talks"], list):
        raise _invalid(label, "talks must be an array")
    for position, talk in enumerate(run["talks"]):
        _validate_talk(talk, f"{label} talks[{position}]")
    _validate_downstream(run["downstream"], f"{label} downstream")
    _validate_clarification(run["clarification"], f"{label} clarification")
    delivered = _validate_report(
        run["end_report"],
        f"{label} end_report",
        lambda digest: str(
            reports_directory / f"{safe_report_stem(str(run['run_id']))}.{digest}.md"
        ),
    )
    _require_timestamp_or_null(
        run["completed_at"], f"{label} completed_at", present=delivered
    )
    if delivered:
        # A report goes out only after the downstream steps and the offer's
        # answer; a record claiming otherwise is not one this script wrote.
        if run["downstream"]["state"] != DOWNSTREAM_COMPLETED:
            raise _invalid(label, "end_report is delivered while downstream is owed")
        if run["clarification"]["state"] in {STATE_OWED, STATE_OFFERED}:
            raise _invalid(
                label, "end_report is delivered while the offer has no answer"
            )
        if run["completed_at"] != run["end_report"]["delivered_at"]:
            raise _invalid(label, "completed_at must equal end_report.delivered_at")


def validate_ledger(
    payload: object, path: Path, reports_directory: Path
) -> dict[str, Any]:
    """Accept only the owner's current ledger shape, bound to this vault."""
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
    label = f"obligations ledger {path}"
    if "adopted_at" not in payload:
        raise _invalid(label, "lacks adopted_at")
    _require_timestamp(payload["adopted_at"], f"{label} adopted_at")
    if "adopted_facts" not in payload:
        raise _invalid(label, "lacks adopted_facts")
    _validate_fact_list(payload["adopted_facts"], f"{label} adopted_facts")
    dismissed = payload.get("dismissed_runs")
    if not isinstance(dismissed, list):
        raise _invalid(label, "must carry a dismissed_runs array")
    dismissed_ids: set[str] = set()
    for index, entry in enumerate(dismissed):
        record = _require_keys(
            entry,
            ("run_id", "dismissed_at", "reason", "facts"),
            f"{label} dismissed_runs[{index}]",
        )
        dismissed_id = _require_identifier(
            record["run_id"], f"{label} dismissed_runs[{index}].run_id"
        )
        if dismissed_id in dismissed_ids:
            raise _invalid(
                label, f"dismissed_runs[{index}] duplicates {dismissed_id!r}"
            )
        dismissed_ids.add(dismissed_id)
        _require_timestamp(
            record["dismissed_at"], f"{label} dismissed_runs[{index}].dismissed_at"
        )
        if not isinstance(record["reason"], str) or not record["reason"].strip():
            raise _invalid(label, f"dismissed_runs[{index}].reason must say why")
        for identity in _validate_fact_list(
            record["facts"], f"{label} dismissed_runs[{index}].facts"
        ):
            if identity[0] != dismissed_id:
                raise _invalid(label, f"dismissed_runs[{index}].facts name another run")
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
        _validate_run(
            run, f"obligations ledger {path} run {run_id!r}", reports_directory
        )
    return payload


# ── Ledger IO ─────────────────────────────────────────────────────────


def load_ledger(
    path: Path, reports_directory: Path
) -> tuple[TrackingDatabaseSnapshot | None, dict[str, Any]]:
    """Read the ledger with its generation, or an empty ledger when absent."""
    if not path.exists():
        return None, empty_ledger()
    try:
        snapshot = snapshot_tracking_database(path)
        payload = decode_json_object(snapshot)
    except TrackingDatabaseIOError as exc:
        code = (
            "ledger_invalid"
            if exc.reason_code.startswith(("json_", "encoding_"))
            else "ledger_unreadable"
        )
        raise _io_failure(exc, f"obligations ledger {path}", code) from exc
    return snapshot, validate_ledger(payload, path, reports_directory)


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
        raise _io_failure(
            exc, f"obligations ledger {path}", "ledger_write_failed"
        ) from exc
    for warning in result.warnings:
        print(f"WARNING: obligations ledger {path}: {warning}", file=sys.stderr)
    return {
        "written": bool(result.installed),
        "durability_state": result.durability_state,
        "warnings": list(result.warnings),
    }


def _copy_failed(detail: str) -> RunObligationsError:
    return RunObligationsError(
        f"{detail}; the delivered text was not recorded",
        reason_code="report_copy_failed",
    )


def _open_directory_no_follow(directory: Path) -> int:
    """A descriptor on the real directory; a symlink at that path is refused."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(directory, flags)
    except OSError as exc:
        raise _copy_failed(
            f"{directory} is not a real directory ({exc}); the report copy is "
            "installed only in a plain directory inside the vault — replace "
            "whatever occupies that path with a directory and re-run "
            "record-report"
        ) from exc


def _read_regular_file(
    descriptor_flags: int, name: str, *, dir_fd: int | None
) -> bytes | None:
    """Bytes of an existing regular file, None when nothing is there.

    Anything else at the name — a link, a FIFO, a directory — is refused, and
    a filesystem failure while inspecting or reading it is reported as the
    structured copy failure, so a caller never blocks on, follows, or
    tracebacks over what it did not write.
    """
    try:
        descriptor = os.open(name, descriptor_flags, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _copy_failed(
            f"{name} cannot be opened without following links ({exc})"
        ) from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise _copy_failed(
                f"{name} exists and is not a regular file; remove it and re-run "
                "record-report"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except OSError as exc:
        raise _copy_failed(
            f"{name} could not be read ({exc}); check the filesystem and re-run "
            "record-report"
        ) from exc
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            print(
                f"WARNING: descriptor for {name} did not close: {exc}", file=sys.stderr
            )


def write_report_copy(
    directory: Path, run_id: str, digest: str, content: bytes
) -> tuple[Path, bool]:
    """Install the delivered report beside the ledger, durably.

    Returns the content-addressed path and whether this call created it. Every
    step runs relative to a descriptor opened on the real directory without
    following links, so nothing that happens to the path between the check
    and the write can redirect the copy outside the vault. An existing
    regular-file copy with the same bytes is left alone, so a replayed or
    racing delivery of identical text never rewrites it; anything else at the
    target is refused.
    """
    name = f"{safe_report_stem(run_id)}.{digest}.md"
    target = directory / name
    try:
        created = not directory.exists()
        directory.mkdir(parents=True, exist_ok=True)
        if created:
            # A new directory entry is durable only once its parent is synced;
            # a replay that changes nothing else must not leave it in doubt.
            parent_fd = os.open(directory.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
    except OSError as exc:
        raise _copy_failed(
            f"cannot create {directory}: {exc} — make its parent writable (or "
            "remove whatever occupies that path) and re-run record-report"
        ) from exc
    dir_fd = _open_directory_no_follow(directory)
    try:
        no_follow = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK
        existing = _read_regular_file(no_follow, name, dir_fd=dir_fd)
        if existing == content:
            return target, False
        staged = f".{name}.{os.getpid()}.tmp"
        try:
            descriptor = os.open(
                staged,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=dir_fd,
            )
        except OSError as exc:
            raise _copy_failed(
                f"cannot stage the report copy under {directory}: {exc} — make "
                "it writable and re-run record-report"
            ) from exc
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staged, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            os.fsync(dir_fd)
        except OSError as exc:
            try:
                os.unlink(staged, dir_fd=dir_fd)
            except OSError as cleanup:
                # Best effort: the write failure is the error to report; a
                # staged file that cannot be removed is named, never allowed
                # to mask it.
                print(
                    f"WARNING: staged report copy {directory / staged} was not "
                    f"removed: {cleanup}",
                    file=sys.stderr,
                )
            raise _copy_failed(
                f"cannot write the report copy {target}: {exc} — free the space "
                "or fix the permissions and re-run record-report"
            ) from exc
    finally:
        os.close(dir_fd)
    return target, True


# ── Database context ──────────────────────────────────────────────────


def persisted_claims(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Every closed claim that persisted this talk, by its full identity.

    ``persist-results.py`` stamps one ``released_at`` on a whole batch, so the
    identity of a persisted fact is the claim's run id, batch id, reprocess
    generation, and release time together.
    """
    claims = [record.get("_queue_claim")]
    history = record.get("_queue_claim_history")
    if isinstance(history, list):
        claims.extend(history)
    found: list[dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        generation = claim.get("reprocess_generation")
        if (
            claim.get("state") != "completed"
            or claim.get("release_reason") != PERSISTED_RELEASE_REASON
            or not isinstance(claim.get("run_id"), str)
            or not isinstance(claim.get("batch_id"), str)
            or type(generation) is not int
            or not isinstance(claim.get("released_at"), str)
        ):
            continue
        try:
            released = parse_timestamp(claim["released_at"], "released_at")
        except RunObligationsError:
            continue
        found.append(
            {
                "run_id": claim["run_id"],
                "batch_id": claim["batch_id"],
                "generation": generation,
                "released_at": render_timestamp(released),
            }
        )
    return found


def _fact_order(fact: dict[str, Any]) -> tuple[int, str]:
    """Newer means a later reprocess generation, then a later release.

    The queue assigns each closed claim of a talk its own generation, so two
    facts of one talk under one run never tie; the batch id is identity, never
    order.
    """
    return (int(fact["generation"]), str(fact["released_at"]))


class Context:
    """The database-bound paths every command resolves the same way."""

    def __init__(self, raw_database: str) -> None:
        self.database_path = materialize_native_authority(
            raw_database, authority="database_path"
        )
        self.vault_root: Path | None = None
        self.database = self.refresh()
        assert self.vault_root is not None
        self.ledger_path = self.vault_root / LEDGER_FILENAME
        self.reports_directory = self.vault_root / REPORTS_DIRECTORY
        self.profile_path = self.vault_root / PROFILE_FILENAME

    def refresh(self) -> dict[str, Any]:
        """Re-read the current database generation right before it is used.

        The vault root is re-resolved from the fresh generation's config and
        must agree with the one the command started under; obligations are
        never written under an authority the database no longer asserts.
        """
        try:
            snapshot = snapshot_tracking_database(self.database_path)
            database = decode_json_object(snapshot)
        except TrackingDatabaseIOError as exc:
            raise _io_failure(
                exc, f"tracking database {self.database_path}", "database_unusable"
            ) from exc
        try:
            require_current_tracking_database(database)
        except TrackingDatabaseError as exc:
            # The owner's own generation diagnostics name reason codes and
            # record labels, never raw values.
            raise RunObligationsError(
                str(exc), reason_code="database_unusable"
            ) from exc
        vault_root = resolve_vault_root_authority(
            database_path=self.database_path, config=database.get("config")
        )
        if self.vault_root is not None and vault_root != self.vault_root:
            raise RunObligationsError(
                f"the tracking database now asserts vault root {vault_root} "
                f"but this command started under {self.vault_root}; re-run it",
                reason_code="vault_root_changed",
            )
        self.vault_root = vault_root
        self.database = database
        return database

    def persisted_runs(self) -> dict[str, dict[str, Any]]:
        """Runs whose closed claims say persist-results.py merged their talks.

        ``talks`` maps each filename to every persisted fact under that run,
        so a talk merged again under the same run id is a distinct fact.
        """
        runs: dict[str, dict[str, Any]] = {}
        for record in self.database["talks"]:
            if not isinstance(record, dict):
                continue
            filename = record.get("filename")
            if not isinstance(filename, str):
                continue
            for fact in persisted_claims(record):
                entry = runs.setdefault(
                    fact["run_id"],
                    {"run_id": fact["run_id"], "talks": {}, "latest_released_at": None},
                )
                entry["talks"].setdefault(filename, []).append(fact)
                if (
                    entry["latest_released_at"] is None
                    or fact["released_at"] > entry["latest_released_at"]
                ):
                    entry["latest_released_at"] = fact["released_at"]
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


def newest_claim(
    claims: list[dict[str, Any]], run_id: str | None
) -> dict[str, Any] | None:
    """The newest closed claim under ``run_id``, or of any run when None."""
    matching = [
        claim for claim in claims if run_id is None or claim["run_id"] == run_id
    ]
    return max(matching, key=_fact_order) if matching else None


def describe_talk(
    context: Context,
    filename: str,
    now: datetime,
    run_id: str,
    *,
    source_run: str | None = None,
    keep: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The talk as the run records it, linked to the claim that persisted it.

    ``keep`` preserves an already-recorded link through a recency refresh.
    Otherwise the link is the newest closed claim of ``source_run`` when the
    caller names one (recovery of an exact persisted fact under a fresh run
    id), else this run's own newest claim, else the newest claim of any run.
    """
    record = context.talk(filename)
    claims = persisted_claims(record)
    if keep is not None:
        link: dict[str, Any] | None = keep
    elif source_run is not None:
        link = newest_claim(claims, source_run)
        if link is None:
            raise RunObligationsError(
                f"talk {filename!r} has no closed return_persisted claim under "
                f"run {source_run!r} in {context.database_path}; --from-run "
                "names the run whose claim persisted the talk",
                reason_code="talk_not_persisted",
            )
    else:
        link = newest_claim(claims, run_id) or newest_claim(claims, None)
        if link is None:
            raise RunObligationsError(
                f"talk {filename!r} has no closed return_persisted claim in "
                f"{context.database_path}; open records only talks "
                "persist-results.py merged",
                reason_code="talk_not_persisted",
            )
    delivered = parse_delivery_date(record.get("date"))
    days = (now.date() - delivered).days if delivered is not None else None
    return {
        "filename": filename,
        "status": str(record.get("status")),
        "delivery_date": delivered.isoformat() if delivered is not None else None,
        "days_since_delivery": days,
        "recency_bucket": recency_bucket(days),
        "claim_run_id": link["run_id"],
        "claim_batch_id": link["batch_id"],
        "claim_generation": link["generation"],
        "claim_released_at": link["released_at"],
    }


def _link(talk: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(talk["claim_run_id"]),
        "batch_id": str(talk["claim_batch_id"]),
        "generation": int(talk["claim_generation"]),
        "released_at": str(talk["claim_released_at"]),
    }


def new_run(run_id: str, now: str) -> dict[str, Any]:
    return {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "run_id": run_id,
        "opened_at": now,
        "updated_at": now,
        "talks": [],
        "downstream": {"state": DOWNSTREAM_OWED, "completed_at": None},
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
            "reopened_at": None,
        },
        "completed_at": None,
    }


def summarize(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run["run_id"],
        "opened_at": run["opened_at"],
        "next_action": next_action(run),
        "downstream_state": run["downstream"]["state"],
        "clarification_state": run["clarification"]["state"],
        "offer_mode": run["clarification"]["offer_mode"],
        "recency_as_of": run["clarification"]["recency_as_of"],
        "end_report_state": run["end_report"]["state"],
        "talk_count": len(run["talks"]),
    }


# ── Commands ──────────────────────────────────────────────────────────


def _apply_recency(
    clarification: dict[str, Any], talks: list[dict[str, Any]], stamp: str
) -> None:
    mode = offer_mode_for(talks)
    clarification["offer_mode"] = mode
    clarification["recency_as_of"] = stamp
    clarification["state"] = (
        STATE_NOT_APPLICABLE if mode == OFFER_MODE_NONE else STATE_OWED
    )


def _require_downstream(run: dict[str, Any], command: str) -> None:
    if run["downstream"]["state"] != DOWNSTREAM_COMPLETED:
        raise RunObligationsError(
            f"run {run['run_id']!r} has not recorded its downstream steps "
            f"(rendering, summary, profile, goals); {command} follows "
            "record-downstream, which follows Step 8",
            reason_code="invalid_transition",
        )


def _conflict(run: dict[str, Any], command: str, detail: str) -> RunObligationsError:
    return RunObligationsError(
        f"run {run['run_id']!r} already recorded a different {command}: {detail}; "
        "a retry must repeat the recorded inputs, and a changed answer is a "
        "new transition, not a replay",
        reason_code="invalid_transition",
    )


def command_open(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    now = parse_timestamp(args.now, "--now")
    stamp = render_timestamp(now)
    run_id = require_run_id(args.run_id)
    source_run = require_run_id(args.from_run) if args.from_run else None
    filenames = list(
        dict.fromkeys(list(args.talk) + _lines_from(args.talks_from, "--talks-from"))
    )
    if not filenames:
        raise RunObligationsError(
            "open requires at least one talk, via --talk or a --talks-from file "
            "with one filename per line",
            reason_code="invalid_arguments",
        )
    context.refresh()
    snapshot, ledger = load_ledger(context.ledger_path, context.reports_directory)
    require_adopted(ledger, context.ledger_path)
    try:
        run = find_run(ledger, run_id)
    except RunObligationsError:
        run = new_run(run_id, stamp)
        ledger["runs"].append(run)
    before = json.dumps(run, sort_keys=True)
    clarification = run["clarification"]
    known = {str(talk["filename"]): talk for talk in run["talks"]}
    # A talk joins the run as a new persisted fact when its filename is
    # unrecorded, or when a newer claim persisted it again under the run the
    # record links it to; a known talk otherwise keeps its recorded link.
    joined: dict[str, dict[str, Any]] = {}
    for name in filenames:
        fresh = describe_talk(context, name, now, run_id, source_run=source_run)
        if name not in known:
            joined[name] = fresh
            continue
        recorded = known[name]
        newer = newest_claim(
            persisted_claims(context.talk(name)), str(recorded["claim_run_id"])
        )
        if newer is not None and newer != _link(recorded):
            joined[name] = describe_talk(context, name, now, run_id, keep=newer)
    if run["completed_at"] is not None:
        if joined:
            raise RunObligationsError(
                f"run {run_id!r} completed at {run['completed_at']}; open a new "
                f"run id for {', '.join(sorted(joined))}",
                reason_code="invalid_transition",
            )
        # An exact replay of facts a completed run already recorded.
        return {
            "ok": True,
            "ledger_path": str(context.ledger_path),
            **store_ledger(context.ledger_path, snapshot, ledger),
            "replayed": True,
            "run": run,
        }
    state = clarification["state"]
    if joined and state in DISPOSITIONS:
        raise RunObligationsError(
            f"run {run_id!r} clarification is already {state!r}; a talk joining "
            f"now would never be offered — open {', '.join(sorted(joined))} "
            "under a fresh run id",
            reason_code="invalid_transition",
        )
    if joined and state == STATE_OFFERED:
        # The standing offer covers less than the run now does: withdraw it
        # so Step 9 makes it again with the fuller topics and recency.
        clarification.update({"state": STATE_OWED, "offered_at": None, "topics": []})
    recency_open = clarification["state"] in {STATE_OWED, STATE_NOT_APPLICABLE}
    talks: list[dict[str, Any]] = []
    for name, talk in known.items():
        if name in joined:
            continue
        if recency_open:
            # Recency follows the newest ``--now`` until the offer is made;
            # the recorded claim link is preserved through the refresh.
            talks.append(describe_talk(context, name, now, run_id, keep=_link(talk)))
        else:
            talks.append(talk)
    talks.extend(joined.values())
    talks.sort(key=lambda talk: str(talk["filename"]))
    run["talks"] = talks
    if recency_open:
        _apply_recency(clarification, talks, stamp)
    if joined:
        run["downstream"] = {"state": DOWNSTREAM_OWED, "completed_at": None}
    if json.dumps(run, sort_keys=True) != before:
        run["updated_at"] = stamp
    outcome = store_ledger(context.ledger_path, snapshot, ledger)
    return {"ok": True, "ledger_path": str(context.ledger_path), **outcome, "run": run}


def _transition(
    context: Context,
    args: argparse.Namespace,
    mutate: Any,
) -> dict[str, Any]:
    now = parse_timestamp(args.now, "--now")
    stamp = render_timestamp(now)
    run_id = require_run_id(args.run_id)
    context.refresh()
    snapshot, ledger = load_ledger(context.ledger_path, context.reports_directory)
    require_adopted(ledger, context.ledger_path)
    run = find_run(ledger, run_id)
    before = json.dumps(run, sort_keys=True)
    extras = mutate(run, stamp, now) or {}
    if json.dumps(run, sort_keys=True) != before:
        run["updated_at"] = stamp
    outcome = store_ledger(context.ledger_path, snapshot, ledger)
    return {
        "ok": True,
        "ledger_path": str(context.ledger_path),
        **outcome,
        **extras,
        "run": run,
    }


def command_record_downstream(
    context: Context, args: argparse.Namespace
) -> dict[str, Any]:
    def mutate(run: dict[str, Any], stamp: str, _now: datetime) -> None:
        # Replay-safe: recording twice after a crash is the same fact twice.
        if run["downstream"]["state"] != DOWNSTREAM_COMPLETED:
            run["downstream"] = {"state": DOWNSTREAM_COMPLETED, "completed_at": stamp}

    return _transition(context, args, mutate)


def _lines_from(path_text: str | None, option: str) -> list[str]:
    """Free text arrives through a file, one entry per line, never a shell."""
    if not path_text:
        return []
    try:
        content = Path(path_text).read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise RunObligationsError(
            f"cannot read {option} {path_text!r}: {exc}",
            reason_code="invalid_arguments",
        ) from exc
    return [line.strip() for line in content.splitlines() if line.strip()]


def command_record_offer(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    topics = [topic.strip() for topic in (args.topic or []) if topic.strip()]
    topics.extend(_lines_from(args.topics_from, "--topics-from"))
    topics = list(dict.fromkeys(topics))

    def mutate(run: dict[str, Any], stamp: str, now: datetime) -> dict[str, Any]:
        _require_downstream(run, "record-offer")
        clarification = run["clarification"]
        state = clarification["state"]
        if state == STATE_OFFERED:
            # Replay of a recorded offer: the same topics are the same fact.
            if clarification["topics"] != topics:
                raise _conflict(
                    run, "offer", f"topics {clarification['topics']!r} stand"
                )
            return {"offered": True, "replayed": True}
        if state == STATE_NOT_APPLICABLE:
            return {
                "offered": False,
                "replayed": True,
                "reason": f"run {run['run_id']!r} has nothing to clarify",
            }
        if state != STATE_OWED:
            raise RunObligationsError(
                f"run {run['run_id']!r} clarification is {state!r}; "
                "record-offer applies only while the offer is owed",
                reason_code="invalid_transition",
            )
        # The stored recency is a snapshot from the last ``open``. The offer is
        # being made now, against the current database, so refresh before
        # freezing: a run resumed weeks later must not promise an inline
        # session for a talk that is no longer same-week.
        talks = [
            describe_talk(
                context, str(talk["filename"]), now, run["run_id"], keep=_link(talk)
            )
            for talk in run["talks"]
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
    return_condition = (args.return_condition or "").strip() or None
    if disposition == STATE_DEFERRED and return_condition is None:
        raise RunObligationsError(
            "a deferred offer needs --return-condition naming, in the "
            "speaker's words, when it is raised again",
            reason_code="invalid_arguments",
        )

    def mutate(run: dict[str, Any], stamp: str, _now: datetime) -> dict[str, Any]:
        clarification = run["clarification"]
        state = clarification["state"]
        if state == disposition and (
            disposition != STATE_DEFERRED
            or clarification["return_condition"] == return_condition
        ):
            # Replay of the recorded answer: nothing moves, the session an
            # accepted answer opened is left exactly as it is.
            return {"replayed": True}
        if state not in {STATE_OFFERED, STATE_DEFERRED}:
            if state in DISPOSITIONS:
                raise _conflict(run, "disposition", f"{state!r} stands")
            raise RunObligationsError(
                f"run {run['run_id']!r} clarification is {state!r}; a "
                "disposition needs a recorded offer first",
                reason_code="invalid_transition",
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
        return {}

    return _transition(context, args, mutate)


def command_record_session(
    context: Context, args: argparse.Namespace
) -> dict[str, Any]:
    refreshed = bool(args.profile_refreshed)
    inputs = args.profile_inputs

    def mutate(run: dict[str, Any], stamp: str, _now: datetime) -> dict[str, Any]:
        clarification = run["clarification"]
        session = clarification["session"]
        if clarification["state"] != STATE_ACCEPTED or session is None:
            raise RunObligationsError(
                f"run {run['run_id']!r} has no accepted clarification session",
                reason_code="invalid_transition",
            )
        if session["state"] == SESSION_COMPLETED:
            if (
                session["profile_inputs"] == inputs
                and session["profile_refreshed"] == refreshed
            ):
                return {"replayed": True}
            raise _conflict(
                run,
                "session completion",
                f"profile_inputs={session['profile_inputs']!r}, "
                f"profile_refreshed={session['profile_refreshed']!r} at "
                f"{session['completed_at']}",
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
        report = run["end_report"]
        extras: dict[str, Any] = {}
        if inputs == PROFILE_INPUTS_CHANGED and report["state"] == REPORT_DELIVERED:
            # A session accepted after the report went out (a deferred offer
            # raised again) changed what the report described; the run owes a
            # fresh report that carries the refreshed profile.
            run["end_report"] = {
                "state": REPORT_OWED,
                "delivered_at": None,
                "report_path": None,
                "report_sha256": None,
                "reopened_at": stamp,
            }
            run["completed_at"] = None
            extras["report_reopened"] = True
        return extras

    return _transition(context, args, mutate)


def command_record_report(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    report_file = Path(args.report_file)
    try:
        content = _read_regular_file(
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK,
            str(report_file),
            dir_fd=None,
        )
    except (OSError, ValueError, RunObligationsError) as exc:
        raise RunObligationsError(
            f"cannot read the delivered report {args.report_file!r} as a regular "
            f"file: {exc}",
            reason_code="report_unreadable",
        ) from exc
    if content is None:
        raise RunObligationsError(
            f"delivered report {args.report_file!r} does not exist",
            reason_code="report_unreadable",
        )
    if not content.strip():
        raise RunObligationsError(
            f"delivered report {report_file} is empty; the end report is the "
            "speaker-facing text, not a placeholder",
            reason_code="report_empty",
        )
    digest = hashlib.sha256(content).hexdigest()

    def mutate(run: dict[str, Any], stamp: str, _now: datetime) -> None:
        _require_downstream(run, "record-report")
        if not clarification_resolved(run):
            raise RunObligationsError(
                f"run {run['run_id']!r} still owes its clarification "
                f"disposition ({next_action(run)}); the end report is delivered "
                "after the speaker answers, so the report can carry any profile "
                "refresh the answers caused",
                reason_code="invalid_transition",
            )
        report = run["end_report"]
        # The copy is installed before the ledger commit and kept whatever the
        # commit does: content-addressed, it is shared by every delivery of
        # these bytes, so a copy left unbound by a lost generation race is
        # reused by the retry rather than removed from under a winner. A replay
        # of the recorded digest still goes through here, so a copy deleted
        # after delivery is recreated rather than reported as present.
        copied, _fresh = write_report_copy(
            context.reports_directory, run["run_id"], digest, content
        )
        if report["state"] == REPORT_DELIVERED and report["report_sha256"] == digest:
            report["report_path"] = str(copied)
            return
        report["state"] = REPORT_DELIVERED
        report["delivered_at"] = stamp
        report["report_path"] = str(copied)
        report["report_sha256"] = digest
        run["completed_at"] = stamp

    return _transition(context, args, mutate)


def _excluded_facts(ledger: dict[str, Any]) -> set[tuple[Any, ...]]:
    """Facts adoption recorded as history plus facts each dismissal covered."""
    excluded = {tuple(identity) for identity in ledger["adopted_facts"]}
    for entry in ledger["dismissed_runs"]:
        excluded.update(tuple(identity) for identity in entry["facts"])
    return excluded


def uncovered_facts(
    persisted: dict[str, dict[str, Any]], ledger: dict[str, Any]
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Persisted facts no record covers and no boundary or dismissal excludes.

    A fact is covered when a run record lists the talk with exactly that
    claim, or with a strictly newer claim of the same run (a later generation
    or release) — a run that merged a talk again superseded its earlier
    result — whichever run id recorded it.
    """
    excluded = _excluded_facts(ledger)
    exact: set[tuple[Any, ...]] = set()
    newest: dict[tuple[str, str], tuple[int, str]] = {}
    for run in ledger["runs"]:
        for talk in run["talks"]:
            link = _link(talk)
            name = str(talk["filename"])
            exact.add(tuple(fact_identity(link, name)))
            key = (link["run_id"], name)
            order = _fact_order(link)
            if key not in newest or order > newest[key]:
                newest[key] = order
    result: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for run_id, entry in persisted.items():
        for name, facts in entry["talks"].items():
            open_facts = [
                fact
                for fact in facts
                if tuple(fact_identity(fact, name)) not in excluded
                and tuple(fact_identity(fact, name)) not in exact
                and not (
                    (run_id, name) in newest
                    and _fact_order(fact) < newest[(run_id, name)]
                )
            ]
            if open_facts:
                result.setdefault(run_id, {})[name] = open_facts
    return result


def open_required(
    persisted: dict[str, dict[str, Any]], ledger: dict[str, Any]
) -> list[dict[str, Any]]:
    """Persisted facts the ledger neither covers nor excludes, per run.

    A persisted fact is one closed claim: run id, filename, batch id,
    reprocess generation, and release time. Facts recorded at adoption are
    history and never listed; facts a dismissal covered are left out. Every
    other uncovered fact (see ``uncovered_facts``) lists its run, in run-id
    order, with exactly the talks concerned: a recorded run as
    ``missing_talks``, or ``talks_persisted_after_completion`` when its report
    is already delivered and ``talks_persisted_after_answer`` when its offer
    was answered — in both of those no fact joins the run, so they need a
    fresh run id — and a run with no record as ``unrecorded_run``. No later
    run's existence and no timestamp stands in for coverage.
    """
    records = {run["run_id"]: run for run in ledger["runs"]}
    required: list[dict[str, Any]] = []
    for run_id, talks in sorted(uncovered_facts(persisted, ledger).items()):
        run = records.get(run_id)
        if run is None:
            reason = REASON_UNRECORDED
        elif run["completed_at"] is not None:
            reason = REASON_AFTER_COMPLETION
        elif run["clarification"]["state"] in DISPOSITIONS:
            reason = REASON_AFTER_ANSWER
        else:
            reason = REASON_MISSING_TALKS
        required.append(
            {
                "run_id": run_id,
                "talks": sorted(talks),
                "latest_released_at": max(
                    fact["released_at"] for facts in talks.values() for fact in facts
                ),
                "reason": reason,
                "next_action": NEXT_OPEN,
            }
        )
    return required


def command_adopt(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    """Create the ledger and stamp the reconciliation boundary; replay-safe."""
    now = parse_timestamp(args.now, "--now")
    stamp = render_timestamp(now)
    context.refresh()
    snapshot, ledger = load_ledger(context.ledger_path, context.reports_directory)
    if ledger.get("adopted_at") is None:
        history = sorted(
            fact_identity(fact, name)
            for entry in context.persisted_runs().values()
            for name, facts in entry["talks"].items()
            for fact in facts
        )
        ledger = empty_ledger(stamp, history)
        outcome = store_ledger(context.ledger_path, snapshot, ledger)
        return {
            "ok": True,
            "ledger_path": str(context.ledger_path),
            **outcome,
            "adopted_at": stamp,
            "adopted_fact_count": len(history),
        }
    return {
        "ok": True,
        "ledger_path": str(context.ledger_path),
        "written": False,
        "durability_state": "unchanged",
        "warnings": [],
        "replayed": True,
        "adopted_at": ledger["adopted_at"],
    }


def command_dismiss(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    """Record that an uncovered run is deliberately not being opened."""
    now = parse_timestamp(args.now, "--now")
    stamp = render_timestamp(now)
    run_id = require_run_id(args.run_id)
    reason = " ".join(
        [(args.reason or "").strip()] + _lines_from(args.reason_from, "--reason-from")
    ).strip()
    if not reason:
        raise RunObligationsError(
            "dismiss needs --reason or a --reason-from file saying why this "
            "run's persisted talks are not being opened",
            reason_code="invalid_arguments",
        )
    context.refresh()
    snapshot, ledger = load_ledger(context.ledger_path, context.reports_directory)
    require_adopted(ledger, context.ledger_path)
    if any(run["run_id"] == run_id for run in ledger["runs"]):
        raise RunObligationsError(
            f"run {run_id!r} has an obligations record; it completes through "
            "its obligations, not through dismissal",
            reason_code="invalid_transition",
        )
    uncovered = uncovered_facts(context.persisted_runs(), ledger).get(run_id, {})
    covering = sorted(
        fact_identity(fact, name) for name, facts in uncovered.items() for fact in facts
    )
    existing = next(
        (entry for entry in ledger["dismissed_runs"] if entry["run_id"] == run_id),
        None,
    )
    if covering:
        # Listed now means facts no earlier dismissal covered exist; today's
        # dismissal names exactly those, renewing an older entry in place.
        if existing is None:
            entry = {
                "run_id": run_id,
                "dismissed_at": stamp,
                "reason": reason,
                "facts": covering,
            }
            ledger["dismissed_runs"].append(entry)
            extras: dict[str, Any] = {}
        else:
            known = {tuple(identity) for identity in existing["facts"]}
            existing["facts"] = sorted(
                [list(identity) for identity in known]
                + [identity for identity in covering if tuple(identity) not in known]
            )
            existing.update({"dismissed_at": stamp, "reason": reason})
            entry = existing
            extras = {"renewed": True}
        outcome = store_ledger(context.ledger_path, snapshot, ledger)
        return {
            "ok": True,
            "ledger_path": str(context.ledger_path),
            **outcome,
            **extras,
            "dismissed": entry,
        }
    if existing is None:
        raise RunObligationsError(
            f"run {run_id!r} is not an uncovered persisted run in `pending`; "
            "only a listed unrecorded_run can be dismissed",
            reason_code="invalid_transition",
        )
    if existing["reason"] == reason:
        return {
            "ok": True,
            "ledger_path": str(context.ledger_path),
            "written": False,
            "durability_state": "unchanged",
            "warnings": [],
            "replayed": True,
            "dismissed": existing,
        }
    raise RunObligationsError(
        f"run {run_id!r} was already dismissed at {existing['dismissed_at']} "
        f"for {existing['reason']!r} and nothing new is listed; a retry "
        "repeats that reason",
        reason_code="invalid_transition",
    )


def command_pending(context: Context, _args: argparse.Namespace) -> dict[str, Any]:
    _snapshot, ledger = load_ledger(context.ledger_path, context.reports_directory)
    adopted = isinstance(ledger.get("adopted_at"), str)
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
    return {
        "ok": True,
        "ledger_path": str(context.ledger_path),
        "ledger_present": context.ledger_path.exists(),
        "adopt_required": not adopted,
        "adopted_at": ledger.get("adopted_at"),
        "pending": pending,
        "count": len(pending),
        "deferred_offers": deferred,
        "open_required": (
            open_required(context.persisted_runs(), ledger) if adopted else []
        ),
    }


def command_status(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    _snapshot, ledger = load_ledger(context.ledger_path, context.reports_directory)
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

    adopt = actions.add_parser(
        "adopt", help="create the ledger and stamp the reconciliation boundary"
    )
    adopt.add_argument("--now", required=True, help="timezone-aware ISO-8601 time")

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
    opened.add_argument(
        "--talks-from",
        help="a file naming persisted talks, one filename per line",
    )
    opened.add_argument(
        "--from-run",
        help="recovery: the run whose closed claim persisted these talks",
    )

    downstream = actions.add_parser(
        "record-downstream",
        help="rendering, summary, profile, and goal steps completed for the run",
    )
    with_run(downstream)

    offer = actions.add_parser("record-offer", help="the offer was put to the speaker")
    with_run(offer)
    offer.add_argument(
        "--topic", action="append", help="candidate clarification topic; repeat"
    )
    offer.add_argument(
        "--topics-from", help="a file naming candidate topics, one per line"
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

    dismiss = actions.add_parser(
        "dismiss", help="an uncovered run is deliberately not being opened"
    )
    with_run(dismiss)
    dismiss.add_argument("--reason", help="why, in plain words")
    dismiss.add_argument(
        "--reason-from", help="a file holding the speaker's reason in their words"
    )

    actions.add_parser("pending", help="list runs with unresolved obligations")

    status = actions.add_parser("status", help="show one run's obligations")
    with_run(status, now=False)
    return parser


COMMANDS = {
    "adopt": command_adopt,
    "open": command_open,
    "record-downstream": command_record_downstream,
    "record-offer": command_record_offer,
    "record-disposition": command_record_disposition,
    "record-session": command_record_session,
    "record-report": command_record_report,
    "dismiss": command_dismiss,
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
        reason_code = getattr(exc, "reason_code", None)
        if isinstance(reason_code, str):
            payload["reason_code"] = reason_code
        print(str(exc), file=sys.stderr)
        print(json.dumps(payload, ensure_ascii=False))
        return 2
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
