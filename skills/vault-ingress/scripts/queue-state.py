#!/usr/bin/env python3
"""Own vault-ingress queue normalization, claims, recovery, and inspection.

The tracking database is the queue authority. This script never reads or replays
subagent returns: an old return may predate a transcript or artifact repair and
must not be allowed to turn an intentional requeue back into ``processed``.

Usage:
    queue-state.py <tracking-database.json> normalize
    queue-state.py <tracking-database.json> claim \
        --run-id <id> --batch-id <id> --now <ISO-8601> [--limit N] \
        [--filename <talk.md> ...]
    queue-state.py <tracking-database.json> recover \
        --now <ISO-8601> --stale-after-seconds N [--run-id <id>]
    queue-state.py <tracking-database.json> inspect --run-id <id>

Every successful command emits one JSON object on stdout and exits 0. Known
input/state errors emit a JSON error object on stdout, an actionable diagnostic
on stderr, and exit 2. Mutating commands rewrite the database atomically only
when state changed.

Claim schema (owned by this script; stored in ``talk._queue_claim``):
    {
      "schema_version": 1,
      "run_id": "reparse-2026-07",
      "batch_id": "25",
      "claimed_at": "2026-07-31T18:00:00+00:00",
      "previous_status": "needs-reprocessing",
      "reprocess_generation": 2,
      "state": "claimed"
    }

Stale recovery adds ``released_at`` and ``release_reason`` and changes ``state``
to ``stale_recovered``. A later generation moves the prior claim to
``talk._queue_claim_history`` and marks an unclosed claim ``superseded``. Each
claim/history record carries its own schema version. ``talk.reprocess_generation``
is the monotonic latest generation. Readers may reconstruct a run from the
current claim plus history via ``inspect``. ``persist-results.py`` owns the
successful terminal transition: it changes the matching claim to ``completed``
and records ``result_status`` without deleting the generation record.
"""

import argparse
import copy
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse


CLAIM_SCHEMA_VERSION = 1
INFLIGHT_STATUS = "reprocessing-inflight"
CLAIMABLE_STATUSES = frozenset({
    "pending",
    "needs-reprocessing",
    "skipped_download_failed",
})
LEGACY_STATUSES = frozenset({"skipped_no_video", "skipped_no_transcript"})
KNOWN_STATUSES = frozenset({
    *CLAIMABLE_STATUSES,
    *LEGACY_STATUSES,
    INFLIGHT_STATUS,
    "processed",
    "processed_partial",
    "skipped_no_sources",
    "skipped_duplicate",
})
CLAIM_STATES = frozenset({"claimed", "completed", "stale_recovered", "superseded"})
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
PLAYLIST_FILENAME = re.compile(r"^playlist-([A-Za-z0-9_-]{11})\.md$")


class QueueStateError(ValueError):
    """A deterministic input or state-contract failure."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Convert argparse failures into the script's JSON error contract."""

    def error(self, message):
        raise QueueStateError(f"invalid arguments: {message}")


def parse_timestamp(value, label):
    """Parse a timezone-aware ISO timestamp and normalize it to UTC seconds."""
    if not isinstance(value, str) or not value:
        raise QueueStateError(f"{label} must be a non-empty ISO-8601 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        moment = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise QueueStateError(
            f"{label} {value!r} is malformed — use a timezone-aware ISO-8601 "
            "timestamp such as 2026-07-31T18:00:00+00:00"
        ) from exc
    if moment.tzinfo is None:
        raise QueueStateError(
            f"{label} {value!r} has no timezone — append an explicit UTC offset"
        )
    return moment.astimezone(timezone.utc).replace(microsecond=0)


def timestamp_text(moment):
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def require_identifier(value, label):
    if not isinstance(value, str) or not value or value.strip() != value:
        raise QueueStateError(f"{label} must be a non-empty string without edge whitespace")
    if any(char.isspace() for char in value):
        raise QueueStateError(f"{label} {value!r} contains whitespace — use a stable token")
    return value


def youtube_id_from_url(value):
    """Return an ID only when a URL is unambiguously a supported YouTube URL."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/", 1)[0]
        return candidate if YOUTUBE_ID.fullmatch(candidate) else None
    if host not in {"youtube.com", "m.youtube.com"}:
        return None
    query_id = (parse_qs(parsed.query).get("v") or [None])[0]
    if query_id and YOUTUBE_ID.fullmatch(query_id):
        return query_id
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live"}:
        return parts[1] if YOUTUBE_ID.fullmatch(parts[1]) else None
    return None


def has_video(talk):
    value = talk.get("video_url")
    return isinstance(value, str) and bool(value.strip())


def validate_claim(claim, filename, *, historical=False):
    if not isinstance(claim, dict):
        raise QueueStateError(f"{filename}: queue claim must be a JSON object")
    if claim.get("schema_version") != CLAIM_SCHEMA_VERSION:
        raise QueueStateError(
            f"{filename}: queue claim schema_version is "
            f"{claim.get('schema_version')!r}; expected {CLAIM_SCHEMA_VERSION}"
        )
    require_identifier(claim.get("run_id"), f"{filename}: claim.run_id")
    require_identifier(claim.get("batch_id"), f"{filename}: claim.batch_id")
    parse_timestamp(claim.get("claimed_at"), f"{filename}: claim.claimed_at")
    previous = claim.get("previous_status")
    if previous not in CLAIMABLE_STATUSES:
        raise QueueStateError(
            f"{filename}: claim.previous_status {previous!r} cannot be restored; "
            f"expected one of {sorted(CLAIMABLE_STATUSES)}"
        )
    generation = claim.get("reprocess_generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise QueueStateError(
            f"{filename}: claim.reprocess_generation must be a positive integer"
        )
    state = claim.get("state")
    if state not in CLAIM_STATES:
        raise QueueStateError(
            f"{filename}: claim.state {state!r} is invalid; expected {sorted(CLAIM_STATES)}"
        )
    released_at = claim.get("released_at")
    if released_at is not None:
        parse_timestamp(released_at, f"{filename}: claim.released_at")
    if state == "claimed" and released_at is not None:
        raise QueueStateError(f"{filename}: an active claim cannot carry released_at")
    if state != "claimed" and released_at is None:
        raise QueueStateError(f"{filename}: a closed claim must carry released_at")
    if state != "claimed" and not isinstance(claim.get("release_reason"), str):
        raise QueueStateError(f"{filename}: a closed claim must carry release_reason")
    if state == "completed":
        if claim.get("result_status") not in {
                "processed", "processed_partial", "skipped_no_sources",
                "skipped_download_failed", "skipped_duplicate"}:
            raise QueueStateError(
                f"{filename}: a completed claim must carry a terminal result_status")
    if historical and state == "claimed":
        raise QueueStateError(f"{filename}: historical claims must be closed")


def validate_talk(talk, index):
    if not isinstance(talk, dict):
        raise QueueStateError(f"talks[{index}] must be a JSON object")
    filename = talk.get("filename")
    if not isinstance(filename, str) or not filename or Path(filename).name != filename:
        raise QueueStateError(
            f"talks[{index}].filename must be a non-empty basename, got {filename!r}"
        )
    if not filename.endswith(".md"):
        raise QueueStateError(f"{filename}: filename must end in .md")
    status = talk.get("status")
    if status not in KNOWN_STATUSES:
        raise QueueStateError(
            f"{filename}: status {status!r} is unknown; reconcile it before queueing"
        )

    explicit_id = talk.get("youtube_id")
    if explicit_id in (None, ""):
        explicit_id = None
    elif not isinstance(explicit_id, str) or not YOUTUBE_ID.fullmatch(explicit_id):
        raise QueueStateError(f"{filename}: youtube_id {explicit_id!r} is not 11 characters")
    url_id = youtube_id_from_url(talk.get("video_url"))
    if url_id and explicit_id is None:
        raise QueueStateError(
            f"{filename}: video_url resolves to {url_id}, but youtube_id is missing — "
            "reconcile the catalog record before queueing"
        )
    if url_id and explicit_id != url_id:
        raise QueueStateError(
            f"{filename}: youtube_id {explicit_id} disagrees with video_url id {url_id}"
        )
    filename_match = PLAYLIST_FILENAME.fullmatch(filename)
    if filename_match:
        filename_id = filename_match.group(1)
        if explicit_id is None:
            raise QueueStateError(
                f"{filename}: filename encodes YouTube id {filename_id}, but "
                "youtube_id is missing"
            )
        if explicit_id != filename_id:
            raise QueueStateError(
                f"{filename}: filename id {filename_id} disagrees with "
                f"youtube_id {explicit_id}"
            )

    generation = talk.get("reprocess_generation", 0)
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise QueueStateError(
            f"{filename}: reprocess_generation must be a non-negative integer"
        )
    current = talk.get("_queue_claim")
    history = talk.get("_queue_claim_history", [])
    if not isinstance(history, list):
        raise QueueStateError(f"{filename}: _queue_claim_history must be a JSON array")
    identities = set()
    for claim in history:
        validate_claim(claim, filename, historical=True)
        identity = (claim["run_id"], claim["batch_id"], claim["reprocess_generation"])
        if identity in identities:
            raise QueueStateError(f"{filename}: duplicate claim history entry {identity!r}")
        identities.add(identity)
    if current is not None:
        validate_claim(current, filename)
        identity = (current["run_id"], current["batch_id"], current["reprocess_generation"])
        if identity in identities:
            raise QueueStateError(f"{filename}: current claim duplicates claim history")
        if current["reprocess_generation"] != generation:
            raise QueueStateError(
                f"{filename}: current claim generation "
                f"{current['reprocess_generation']} disagrees with talk generation {generation}"
            )
    if status == INFLIGHT_STATUS:
        if current is None:
            raise QueueStateError(
                f"{filename}: {INFLIGHT_STATUS} has no reconstructable _queue_claim"
            )
        if current["state"] != "claimed":
            raise QueueStateError(
                f"{filename}: {INFLIGHT_STATUS} requires claim.state='claimed'"
            )


def validate_database(database):
    if not isinstance(database, dict):
        raise QueueStateError("tracking database root must be a JSON object")
    talks = database.get("talks")
    if not isinstance(talks, list):
        raise QueueStateError("tracking database must contain a talks array")
    seen = set()
    for index, talk in enumerate(talks):
        validate_talk(talk, index)
        filename = talk["filename"]
        if filename in seen:
            raise QueueStateError(
                f"duplicate talk filename {filename!r} — filenames are queue identities"
            )
        seen.add(filename)


def load_database(path):
    try:
        with path.open(encoding="utf-8") as handle:
            database = json.load(handle)
    except FileNotFoundError as exc:
        raise QueueStateError(
            f"tracking database not found at {path} — pass the vault's "
            "tracking-database.json"
        ) from exc
    except json.JSONDecodeError as exc:
        raise QueueStateError(
            f"tracking database at {path} is invalid JSON at line {exc.lineno}, "
            f"column {exc.colno}"
        ) from exc
    except OSError as exc:
        raise QueueStateError(f"cannot read tracking database at {path}: {exc}") from exc
    validate_database(database)
    return database


def write_database_atomically(path, database):
    """Replace the database only after a complete same-directory write."""
    try:
        mode = path.stat().st_mode & 0o777
        handle, temporary = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".partial"
        )
        try:
            os.chmod(temporary, mode)
            with os.fdopen(handle, "w", encoding="utf-8") as output:
                json.dump(database, output, indent=2, ensure_ascii=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    except OSError as exc:
        raise QueueStateError(
            f"cannot atomically write tracking database at {path}: {exc}"
        ) from exc


def normalize_legacy_statuses(database):
    changes = []
    for talk in database["talks"]:
        previous = talk["status"]
        if previous not in LEGACY_STATUSES:
            continue
        current = "pending" if has_video(talk) else "skipped_no_sources"
        talk["status"] = current
        changes.append({
            "filename": talk["filename"],
            "previous_status": previous,
            "status": current,
            "video_present": has_video(talk),
        })
    return changes


def all_claims(talk):
    claims = list(talk.get("_queue_claim_history", []))
    current = talk.get("_queue_claim")
    if current is not None:
        claims.append(current)
    return claims


def claims_for_run(database, run_id, batch_id=None):
    found = []
    for talk in database["talks"]:
        for claim in all_claims(talk):
            if claim["run_id"] != run_id:
                continue
            if batch_id is not None and claim["batch_id"] != batch_id:
                continue
            item = copy.deepcopy(claim)
            item["filename"] = talk["filename"]
            item["current_status"] = talk["status"]
            found.append(item)
    return sorted(found, key=lambda item: (
        item["batch_id"], item["filename"], item["reprocess_generation"]
    ))


def reconstruct_run(database, run_id):
    claims = claims_for_run(database, run_id)
    grouped = {}
    for claim in claims:
        grouped.setdefault(claim["batch_id"], []).append(claim["filename"])
    batches = [
        {"batch_id": batch_id, "filenames": sorted(filenames)}
        for batch_id, filenames in sorted(grouped.items())
    ]
    return {"run_id": run_id, "claim_count": len(claims),
            "batches": batches, "claims": claims}


def archive_current_claim(talk, now_text):
    current = talk.get("_queue_claim")
    if current is None:
        return
    archived = copy.deepcopy(current)
    if archived["state"] == "claimed":
        archived["state"] = "superseded"
        archived["released_at"] = now_text
        archived["release_reason"] = "new_generation_claimed"
    talk.setdefault("_queue_claim_history", []).append(archived)


def claim_talk(talk, run_id, batch_id, now_text):
    previous = talk["status"]
    if previous not in CLAIMABLE_STATUSES:
        raise QueueStateError(
            f"{talk['filename']}: cannot transition {previous!r} to {INFLIGHT_STATUS}"
        )
    if not has_video(talk):
        raise QueueStateError(
            f"{talk['filename']}: cannot claim a talk without video_url"
        )
    archive_current_claim(talk, now_text)
    generation = talk.get("reprocess_generation", 0) + 1
    claim = {
        "schema_version": CLAIM_SCHEMA_VERSION,
        "run_id": run_id,
        "batch_id": batch_id,
        "claimed_at": now_text,
        "previous_status": previous,
        "reprocess_generation": generation,
        "state": "claimed",
    }
    talk["reprocess_generation"] = generation
    talk["_queue_claim"] = claim
    talk["status"] = INFLIGHT_STATUS
    item = copy.deepcopy(claim)
    item["filename"] = talk["filename"]
    item["current_status"] = talk["status"]
    return item


def command_normalize(database, path, _args):
    normalizations = normalize_legacy_statuses(database)
    if normalizations:
        validate_database(database)
        write_database_atomically(path, database)
    return {
        "ok": True,
        "action": "normalize",
        "db_path": str(path),
        "changed": len(normalizations),
        "normalizations": normalizations,
    }


def command_claim(database, path, args):
    run_id = require_identifier(args.run_id, "run_id")
    batch_id = require_identifier(args.batch_id, "batch_id")
    now_text = timestamp_text(parse_timestamp(args.now, "--now"))
    existing = claims_for_run(database, run_id, batch_id)
    requested = args.filename or []
    if len(requested) != len(set(requested)):
        raise QueueStateError("--filename contains duplicates")
    if existing:
        existing_names = {item["filename"] for item in existing}
        if requested and set(requested) != existing_names:
            raise QueueStateError(
                f"run {run_id!r} batch {batch_id!r} already exists for "
                f"{sorted(existing_names)}; requested {sorted(requested)}"
            )
        return {
            "ok": True,
            "action": "claim",
            "db_path": str(path),
            "run_id": run_id,
            "batch_id": batch_id,
            "idempotent_replay": True,
            "normalizations": [],
            "claimed": existing,
            "remaining_eligible": None,
        }

    normalizations = normalize_legacy_statuses(database)
    by_filename = {talk["filename"]: talk for talk in database["talks"]}
    if requested:
        missing = sorted(set(requested) - set(by_filename))
        if missing:
            raise QueueStateError(f"requested filenames are not in the database: {missing}")
        if len(requested) > args.limit:
            raise QueueStateError(
                f"requested {len(requested)} filenames exceeds --limit {args.limit}"
            )
        selected = [by_filename[filename] for filename in sorted(requested)]
        for talk in selected:
            if talk["status"] not in CLAIMABLE_STATUSES:
                raise QueueStateError(
                    f"{talk['filename']}: cannot claim status {talk['status']!r}"
                )
            if not has_video(talk):
                raise QueueStateError(
                    f"{talk['filename']}: cannot claim a talk without video_url"
                )
    else:
        eligible = [
            talk for talk in database["talks"]
            if talk["status"] in CLAIMABLE_STATUSES and has_video(talk)
        ]
        selected = sorted(eligible, key=lambda talk: talk["filename"])[:args.limit]

    claimed = [claim_talk(talk, run_id, batch_id, now_text) for talk in selected]
    remaining = sum(
        talk["status"] in CLAIMABLE_STATUSES and has_video(talk)
        for talk in database["talks"]
    )
    if normalizations or claimed:
        validate_database(database)
        write_database_atomically(path, database)
    return {
        "ok": True,
        "action": "claim",
        "db_path": str(path),
        "run_id": run_id,
        "batch_id": batch_id,
        "claimed_at": now_text,
        "idempotent_replay": False,
        "normalizations": normalizations,
        "claimed": claimed,
        "remaining_eligible": remaining,
    }


def command_recover(database, path, args):
    now = parse_timestamp(args.now, "--now")
    now_text = timestamp_text(now)
    run_id = require_identifier(args.run_id, "run_id") if args.run_id else None
    recovered = []
    for talk in sorted(database["talks"], key=lambda item: item["filename"]):
        if talk["status"] != INFLIGHT_STATUS:
            continue
        claim = talk["_queue_claim"]
        if run_id is not None and claim["run_id"] != run_id:
            continue
        claimed_at = parse_timestamp(
            claim["claimed_at"], f"{talk['filename']}: claim.claimed_at"
        )
        age_seconds = int((now - claimed_at).total_seconds())
        if age_seconds < 0:
            raise QueueStateError(
                f"{talk['filename']}: claim.claimed_at is later than --now"
            )
        if age_seconds < args.stale_after_seconds:
            continue
        talk["status"] = claim["previous_status"]
        claim["state"] = "stale_recovered"
        claim["released_at"] = now_text
        claim["release_reason"] = "lease_expired"
        recovered.append({
            "filename": talk["filename"],
            "run_id": claim["run_id"],
            "batch_id": claim["batch_id"],
            "reprocess_generation": claim["reprocess_generation"],
            "status": talk["status"],
            "age_seconds": age_seconds,
        })
    if recovered:
        validate_database(database)
        write_database_atomically(path, database)
    return {
        "ok": True,
        "action": "recover",
        "db_path": str(path),
        "now": now_text,
        "stale_after_seconds": args.stale_after_seconds,
        "recovered": recovered,
    }


def command_inspect(database, path, args):
    run_id = require_identifier(args.run_id, "run_id")
    return {
        "ok": True,
        "action": "inspect",
        "db_path": str(path),
        **reconstruct_run(database, run_id),
    }


def positive_integer(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser():
    parser = JsonArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("database", help="tracking-database.json path")
    actions = parser.add_subparsers(dest="action", required=True,
                                    parser_class=JsonArgumentParser)
    actions.add_parser("normalize", help="normalize legacy queue statuses")

    claim = actions.add_parser("claim", help="claim a deterministic batch")
    claim.add_argument("--run-id", required=True)
    claim.add_argument("--batch-id", required=True)
    claim.add_argument("--now", required=True,
                       help="timezone-aware ISO-8601 claim time")
    claim.add_argument("--limit", type=positive_integer, default=5)
    claim.add_argument("--filename", action="append",
                       help="claim this filename; repeat for an exact batch")

    recover = actions.add_parser("recover", help="recover expired inflight leases")
    recover.add_argument("--now", required=True,
                         help="timezone-aware ISO-8601 reference time")
    recover.add_argument("--stale-after-seconds", type=positive_integer, required=True)
    recover.add_argument("--run-id", help="recover only this run's expired claims")

    inspect = actions.add_parser("inspect", help="reconstruct claims for one run")
    inspect.add_argument("--run-id", required=True)
    return parser


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        path = Path(args.database).expanduser().resolve()
        database = load_database(path)
        commands = {
            "normalize": command_normalize,
            "claim": command_claim,
            "recover": command_recover,
            "inspect": command_inspect,
        }
        payload = commands[args.action](database, path, args)
    except QueueStateError as exc:
        payload = {"ok": False, "error": str(exc)}
        print(str(exc), file=sys.stderr)
        print(json.dumps(payload, ensure_ascii=False))
        return 2
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
