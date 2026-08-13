#!/usr/bin/env python3
"""Own vault-ingress queue normalization, claims, recovery, and inspection.

The tracking database is the queue authority. This script never reads or replays
subagent returns: an old return may predate a transcript or artifact repair and
must not be allowed to turn an intentional requeue back into ``processed``.
Eligibility is source-capability based: a preflighted transcript, slide, or video
reference can support a claim. Video is not mandatory, and only a legacy record
with none of those capabilities normalizes to ``skipped_no_sources``.
Normalization also routes every valid processed result outside the active
pattern-scoring generation, or whose persisted citation artifacts have drifted,
back to ``needs-reprocessing``. It delegates the cohort decision to
``partition_pattern_scoring_cohort``; malformed current metadata is a
whole-command no-write error, never a migration guess.

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
      "schema_version": 5,
      "run_id": "reparse-2026-07",
      "batch_id": "25",
      "claimed_at": "2026-07-31T18:00:00+00:00",
      "previous_status": "needs-reprocessing",
      "reprocess_generation": 2,
      "state": "claimed",
      "required_return_schema_version": 5,
      "adherence_baseline": {"schema_version": 2, "...": "..."}
    }

Fresh claims always use schema v5 and require return v5. The queue snapshots one
baseline before mutating the selected talks, excludes the exact active batch,
and copies the same immutable payload to every member. Schema-v1/v2 claims are
accepted only for compatibility and authorize return v1/v2; schema-v3 claims
authorize only return v3, and schema-v4 claims authorize only archival return
v4. None of them authorizes v5 or is newly issued.

Stale recovery adds ``released_at`` and ``release_reason`` and changes ``state``
to ``stale_recovered``. A later generation moves the prior claim to
``talk._queue_claim_history`` and marks an unclosed claim ``superseded``. Each
claim/history record carries its own schema version. ``talk.reprocess_generation``
is the monotonic latest generation. Readers may reconstruct a run from the
current claim plus history via ``inspect``. ``persist-results.py`` owns the
successful terminal transition: it changes the matching claim to ``completed``
and records ``result_status`` plus the canonical return-payload SHA-256 receipt
without deleting the generation record.
"""

import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone
from typing import cast
from urllib.parse import parse_qs, urlparse

from ingress_contract import (
    has_video_source,
)
from tracking_database import (
    TrackingDatabaseError,
    assess_tracking_database,
    require_current_tracking_database,
)
from queue_claim_contract import (
    ADHERENCE_QUEUE_CLAIM_SCHEMA_VERSIONS,
    CLAIMABLE_STATUSES,
    CURRENT_QUEUE_CLAIM_SCHEMA_VERSION,
    INFLIGHT_STATUS,
    LEGACY_QUEUE_CLAIM_SCHEMA_VERSION,
    LEGACY_STATUSES,
    PATTERN_SCORING_REPROCESS_REASON_PREFIX,
    PATTERN_SCORING_REPROCESS_REASON_SEQUENCES,
    QueueClaimContractError,
    RECEIPT_QUEUE_CLAIM_SCHEMA_VERSION,
    SUPPORTED_QUEUE_CLAIM_SCHEMA_VERSIONS,
    validate_queue_claim,
    validate_queue_claim_database,
    validate_talk_queue_claim_state,
)
from adherence_baseline import (
    AdherenceBaselineError,
    build_adherence_baseline,
    partition_pattern_scoring_cohort,
)
from persisted_pattern_observations import persisted_observation_assessor
from pattern_evidence import (
    assess_talk_artifact_capabilities,
    required_pptx_evidence_blocking_reason,
)
from video_evidence import VideoEvidenceAssessment
from return_validation import (
    PATTERN_SCORING_SCHEMA_VERSION,
    QUEUE_CLAIM_SCHEMA_VERSION,
    RETURN_SCHEMA_VERSION,
    ReturnValidationError,
    assess_current_persisted_pattern_evidence_freshness,
    load_catalog,
)
from tracking_database_io import (
    TrackingDatabaseIOError,
    TrackingDatabaseSnapshot,
    TrackingDatabaseWriteResult,
    decode_json_object,
    snapshot_tracking_database,
    unchanged_write_result,
    write_json_object,
)
from vault_root_authority import (
    VaultRootAuthorityError,
    materialize_native_authority,
    resolve_vault_root_authority,
)


CLAIM_SCHEMA_VERSION = CURRENT_QUEUE_CLAIM_SCHEMA_VERSION
if CLAIM_SCHEMA_VERSION != QUEUE_CLAIM_SCHEMA_VERSION:
    raise RuntimeError(
        "shared queue-claim and return-validation claim versions must match"
    )
if CLAIM_SCHEMA_VERSION != RETURN_SCHEMA_VERSION:
    raise RuntimeError(
        "current queue-claim and ingress-return schema versions must match"
    )
LEGACY_CLAIM_SCHEMA_VERSION = LEGACY_QUEUE_CLAIM_SCHEMA_VERSION
RECEIPT_CLAIM_SCHEMA_VERSION = RECEIPT_QUEUE_CLAIM_SCHEMA_VERSION
SUPPORTED_CLAIM_SCHEMA_VERSIONS = SUPPORTED_QUEUE_CLAIM_SCHEMA_VERSIONS
ADHERENCE_CLAIM_SCHEMA_VERSIONS = ADHERENCE_QUEUE_CLAIM_SCHEMA_VERSIONS
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
PLAYLIST_FILENAME = re.compile(r"^playlist-([A-Za-z0-9_-]{11})\.md$")
CAPABILITY_ORDER = ("video", "slides", "transcript")


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
        raise QueueStateError(
            f"{label} must be a non-empty string without edge whitespace"
        )
    if any(char.isspace() for char in value):
        raise QueueStateError(
            f"{label} {value!r} contains whitespace — use a stable token"
        )
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
    return has_video_source(talk)


def evidence_roots(database, path):
    """Return the database-bound vault root and configured source roots."""
    source_roots = (
        database.get("config") if isinstance(database.get("config"), dict) else {}
    )
    vault_root = resolve_vault_root_authority(
        database_path=path,
        config=database.get("config"),
    )
    return vault_root, source_roots


def evidence_freshness_assessor(
    database, path, *, video_evidence_assessment: VideoEvidenceAssessment
):
    """Bind the shared read-only assessor to this database's trusted roots."""
    vault_root, source_roots = evidence_roots(database, path)
    cache = {}

    def assess(talk):
        identity = id(talk)
        if identity not in cache:
            cache[identity] = assess_current_persisted_pattern_evidence_freshness(
                talk,
                vault_root=vault_root,
                source_roots=source_roots,
                video_evidence_assessment=video_evidence_assessment,
            )
        return cache[identity]

    return assess


def artifact_capability_assessor(
    database, path, *, video_evidence_assessment: VideoEvidenceAssessment
):
    """Bind root-aware local/acquisition capability checks.

    The bounded PPTX probe owns generation-aware memoization.  Keeping a
    second filename-only cache here could authorize a claim after its deck had
    changed between eligibility selection and the final claim boundary.
    """
    vault_root, source_roots = evidence_roots(database, path)

    def assess(talk):
        return assess_talk_artifact_capabilities(
            talk,
            vault_root=vault_root,
            source_roots=source_roots,
            video_evidence_assessment=video_evidence_assessment,
        )

    return assess


def processable_capabilities(talk, *, capability_assessor):
    """Return verified, repairable-local, and acquisition capabilities."""
    assessment = capability_assessor(talk)
    if not isinstance(assessment, dict):
        raise QueueStateError(
            f"{talk.get('filename')}: artifact capability assessor returned "
            "a non-object result"
        )
    verified = assessment.get("verified_capabilities")
    acquisition = assessment.get("acquisition_capabilities")
    repair = assessment.get("repair_capabilities", ())
    if (
        not isinstance(verified, tuple)
        or not isinstance(acquisition, tuple)
        or not isinstance(repair, tuple)
    ):
        raise QueueStateError(
            f"{talk.get('filename')}: artifact capability assessor returned "
            "a malformed capability contract"
        )
    available = set(verified) | set(repair) | set(acquisition)
    if not available.issubset(CAPABILITY_ORDER):
        raise QueueStateError(
            f"{talk.get('filename')}: artifact capability assessor returned "
            f"unknown capabilities {sorted(available - set(CAPABILITY_ORDER))}"
        )
    return [capability for capability in CAPABILITY_ORDER if capability in available]


def has_processable_source(talk, *, capability_assessor):
    return bool(
        processable_capabilities(
            talk,
            capability_assessor=capability_assessor,
        )
    )


def claim_blocking_artifact_reason(talk, *, capability_assessor):
    """Return a live artifact reason that forbids a fresh current claim."""
    assessment = capability_assessor(talk)
    if not isinstance(assessment, dict):
        raise QueueStateError(
            f"{talk.get('filename')}: artifact capability assessor returned "
            "a non-object result"
        )
    return required_pptx_evidence_blocking_reason(talk, assessment)


def has_claimable_source(talk, *, capability_assessor):
    """Require a processable lane and no mandatory degraded native deck."""
    assessment = capability_assessor(talk)

    def provisional_assessor(_talk):
        return assessment

    return (
        has_processable_source(talk, capability_assessor=provisional_assessor)
        and claim_blocking_artifact_reason(
            talk,
            capability_assessor=provisional_assessor,
        )
        is None
    )


def pattern_scoring_reprocess_reason(reason_codes):
    """Encode one selector-owned, ordered reason sequence."""
    exact_codes = tuple(reason_codes)
    if exact_codes not in PATTERN_SCORING_REPROCESS_REASON_SEQUENCES:
        raise QueueStateError(
            "pattern-scoring cohort selector returned unsupported ordered "
            f"reprocess reasons {list(exact_codes)!r}"
        )
    return PATTERN_SCORING_REPROCESS_REASON_PREFIX + "+".join(exact_codes)


def validate_claim(claim, filename, *, historical=False):
    try:
        validate_queue_claim(claim, filename, historical=historical)
    except QueueClaimContractError as exc:
        raise QueueStateError(str(exc)) from exc


def validate_talk(talk, index, *, allow_claim_status_drift=False):
    try:
        validate_talk_queue_claim_state(
            talk,
            index,
            allow_claim_status_drift=allow_claim_status_drift,
        )
    except QueueClaimContractError as exc:
        raise QueueStateError(str(exc)) from exc
    filename = talk["filename"]

    explicit_id = talk.get("youtube_id")
    if explicit_id in (None, ""):
        explicit_id = None
    elif not isinstance(explicit_id, str) or not YOUTUBE_ID.fullmatch(explicit_id):
        raise QueueStateError(
            f"{filename}: youtube_id {explicit_id!r} is not 11 characters"
        )
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


def validate_database(database, *, allow_claim_status_drift=False):
    try:
        validate_queue_claim_database(
            database,
            allow_claim_status_drift=allow_claim_status_drift,
        )
    except QueueClaimContractError as exc:
        raise QueueStateError(str(exc)) from exc
    for index, talk in enumerate(database["talks"]):
        validate_talk(
            talk,
            index,
            allow_claim_status_drift=allow_claim_status_drift,
        )


def upgrade_claim_for_write(claim):
    """Upgrade one v1 claim only when its owning queue transition is persisted."""
    if claim.get("schema_version") != LEGACY_CLAIM_SCHEMA_VERSION:
        return
    claim["schema_version"] = RECEIPT_CLAIM_SCHEMA_VERSION
    if claim.get("state") == "completed":
        claim["result_payload_sha256"] = None


def load_database_snapshot(
    path,
    *,
    allow_claim_status_drift=False,
    require_current=True,
):
    """Load strict JSON together with the exact generation validation observed."""
    try:
        snapshot = snapshot_tracking_database(path)
        database = decode_json_object(snapshot)
    except TrackingDatabaseIOError as exc:
        raise QueueStateError(str(exc)) from exc
    try:
        if require_current:
            require_current_tracking_database(database)
        else:
            assessment = assess_tracking_database(database)
            if not assessment.usable:
                reasons = ", ".join(assessment.reason_codes)
                raise TrackingDatabaseError(
                    "tracking database is not a supported legacy/current "
                    f"generation ({reasons})"
                )
    except TrackingDatabaseError as exc:
        raise QueueStateError(str(exc)) from exc
    validate_database(
        database,
        allow_claim_status_drift=allow_claim_status_drift,
    )
    return database, snapshot


def load_database(
    path,
    *,
    allow_claim_status_drift=False,
    require_current=True,
):
    """Compatibility wrapper returning only the decoded database."""
    database, _ = load_database_snapshot(
        path,
        allow_claim_status_drift=allow_claim_status_drift,
        require_current=require_current,
    )
    return database


def write_database_atomically(
    path,
    database,
    *,
    expected_snapshot: TrackingDatabaseSnapshot | None = None,
) -> TrackingDatabaseWriteResult:
    """Commit against the exact generation captured before validation."""
    try:
        snapshot = expected_snapshot or snapshot_tracking_database(path)
        return write_json_object(snapshot, database)
    except TrackingDatabaseIOError as exc:
        raise QueueStateError(
            f"cannot safely write tracking database at {path}: {exc}"
        ) from exc


def write_result_fields(
    result: TrackingDatabaseWriteResult,
) -> dict[str, object]:
    """Expose generation identities without changing queue's `changed` count."""
    return {
        "input_sha256": result.input_sha256,
        "output_sha256": result.output_sha256,
        "database_written": result.installed,
        "durability_state": result.durability_state,
        "warnings": list(result.warnings),
    }


def normalize_legacy_statuses(database, *, capability_assessor):
    changes = []
    for talk in database["talks"]:
        previous = talk["status"]
        if previous not in LEGACY_STATUSES:
            continue
        capabilities = processable_capabilities(
            talk,
            capability_assessor=capability_assessor,
        )
        current = "pending" if capabilities else "skipped_no_sources"
        talk["status"] = current
        changes.append(
            {
                "filename": talk["filename"],
                "previous_status": previous,
                "status": current,
                "video_present": has_video(talk),
                "source_capabilities": capabilities,
            }
        )
    return changes


def normalize_pattern_scoring_generations(database, *, evidence_freshness_assessor):
    """Requeue every valid processed talk outside the active score generation.

    "Outside the generation" includes a talk whose persisted observations are
    structurally invalid: its score was computed from a block nothing
    validated, so it is not current evidence however current its stamp says it
    is. Requeueing it here and excluding it from the cohort are the same act,
    because both read `partition_pattern_scoring_cohort` (#167).
    """
    try:
        catalog = load_catalog()
        _, _, exclusion_details = partition_pattern_scoring_cohort(
            database["talks"],
            excluded_filenames=[],
            pattern_catalog_fingerprint=catalog.fingerprint,
            pattern_scoring_schema_version=PATTERN_SCORING_SCHEMA_VERSION,
            evidence_freshness_assessor=evidence_freshness_assessor,
            persisted_observation_assessor=persisted_observation_assessor(catalog),
        )
    except (AdherenceBaselineError, ReturnValidationError, OSError) as exc:
        raise QueueStateError(
            "cannot normalize pattern-scoring generations: "
            f"{exc} — repair the named processed talk before retrying normalize"
        ) from exc

    by_filename = {talk["filename"]: talk for talk in database["talks"]}
    changes = []
    for detail in exclusion_details:
        talk = by_filename[detail["filename"]]
        previous = talk["status"]
        reason_codes = cast(list[str], detail["reason_codes"])
        reprocess_reason = pattern_scoring_reprocess_reason(reason_codes)
        talk["status"] = "needs-reprocessing"
        talk["reprocess_reason"] = reprocess_reason
        changes.append(
            {
                "filename": talk["filename"],
                "previous_status": previous,
                "status": talk["status"],
                "reprocess_reason": reprocess_reason,
                **detail,
            }
        )
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
    return sorted(
        found,
        key=lambda item: (
            item["batch_id"],
            item["filename"],
            item["reprocess_generation"],
        ),
    )


def reconstruct_run(database, run_id):
    claims = claims_for_run(database, run_id)
    grouped = {}
    for claim in claims:
        grouped.setdefault(claim["batch_id"], []).append(claim["filename"])
    batches = [
        {"batch_id": batch_id, "filenames": sorted(filenames)}
        for batch_id, filenames in sorted(grouped.items())
    ]
    return {
        "run_id": run_id,
        "claim_count": len(claims),
        "batches": batches,
        "claims": claims,
    }


def archive_current_claim(talk, now_text):
    current = talk.get("_queue_claim")
    if current is None:
        return
    archived = copy.deepcopy(current)
    upgrade_claim_for_write(archived)
    if archived["state"] == "claimed":
        archived["state"] = "superseded"
        archived["released_at"] = now_text
        archived["release_reason"] = "new_generation_claimed"
    talk.setdefault("_queue_claim_history", []).append(archived)


def claim_talk(
    talk,
    run_id,
    batch_id,
    now_text,
    adherence_baseline,
    *,
    capability_assessor,
):
    previous = talk["status"]
    if previous not in CLAIMABLE_STATUSES:
        raise QueueStateError(
            f"{talk['filename']}: cannot transition {previous!r} to {INFLIGHT_STATUS}"
        )
    # Reassess exactly once at the mutation boundary.  Selection is only a
    # provisional filter: a deck may have changed after it was found eligible.
    final_assessment = capability_assessor(talk)

    def final_capability_assessor(_talk):
        return final_assessment

    blocking_reason = claim_blocking_artifact_reason(
        talk,
        capability_assessor=final_capability_assessor,
    )
    if blocking_reason is not None:
        raise QueueStateError(f"{talk['filename']}: cannot claim: {blocking_reason}")
    if not has_processable_source(
        talk,
        capability_assessor=final_capability_assessor,
    ):
        raise QueueStateError(
            f"{talk['filename']}: cannot claim a talk without a usable transcript, "
            "slide, or video source"
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
        "required_return_schema_version": CLAIM_SCHEMA_VERSION,
        "adherence_baseline": copy.deepcopy(adherence_baseline),
    }
    talk["reprocess_generation"] = generation
    talk["_queue_claim"] = claim
    talk["status"] = INFLIGHT_STATUS
    item = copy.deepcopy(claim)
    item["filename"] = talk["filename"]
    item["current_status"] = talk["status"]
    return item


def command_normalize(
    database,
    path,
    _args,
    *,
    expected_snapshot,
    video_evidence_assessment: VideoEvidenceAssessment,
):
    candidate = copy.deepcopy(database)
    capability_assessor = artifact_capability_assessor(
        candidate, path, video_evidence_assessment=video_evidence_assessment
    )
    normalizations = normalize_legacy_statuses(
        candidate,
        capability_assessor=capability_assessor,
    )
    normalizations.extend(
        normalize_pattern_scoring_generations(
            candidate,
            evidence_freshness_assessor=evidence_freshness_assessor(
                candidate,
                path,
                video_evidence_assessment=video_evidence_assessment,
            ),
        )
    )
    if normalizations:
        validate_database(candidate)
        write_result = write_database_atomically(
            path,
            candidate,
            expected_snapshot=expected_snapshot,
        )
    else:
        write_result = unchanged_write_result(expected_snapshot)
    return {
        "ok": True,
        "action": "normalize",
        "db_path": str(path),
        "changed": len(normalizations),
        "normalizations": normalizations,
        **write_result_fields(write_result),
    }


def command_claim(
    database,
    path,
    args,
    *,
    expected_snapshot,
    video_evidence_assessment: VideoEvidenceAssessment,
):
    run_id = require_identifier(args.run_id, "run_id")
    batch_id = require_identifier(args.batch_id, "batch_id")
    now_text = timestamp_text(parse_timestamp(args.now, "--now"))
    existing = claims_for_run(database, run_id, batch_id)
    requested = args.filename or []
    if len(requested) != len(set(requested)):
        raise QueueStateError("--filename contains duplicates")
    if existing:
        latest_by_filename = {}
        for item in existing:
            filename = item["filename"]
            prior = latest_by_filename.get(filename)
            if (
                prior is None
                or item["reprocess_generation"] > prior["reprocess_generation"]
            ):
                latest_by_filename[filename] = item
        latest = sorted(latest_by_filename.values(), key=lambda item: item["filename"])
        existing_names = set(latest_by_filename)
        if requested and set(requested) != existing_names:
            raise QueueStateError(
                f"run {run_id!r} batch {batch_id!r} already exists for "
                f"{sorted(existing_names)}; requested {sorted(requested)}"
            )
        latest_states = {item["state"] for item in latest}
        if latest_states <= {"claimed", "completed"}:
            write_result = unchanged_write_result(expected_snapshot)
            return {
                "ok": True,
                "action": "claim",
                "db_path": str(path),
                "run_id": run_id,
                "batch_id": batch_id,
                "idempotent_replay": True,
                "normalizations": [],
                "claimed": latest,
                "remaining_eligible": None,
                **write_result_fields(write_result),
            }
        if latest_states == {"stale_recovered"}:
            # Recovery restores the talks to their prior claimable statuses.
            # Reusing the stable batch identity must create a new generation,
            # not replay a closed lease and leave the batch silently idle.
            requested = sorted(existing_names)
        else:
            states_by_filename = {item["filename"]: item["state"] for item in latest}
            raise QueueStateError(
                f"run {run_id!r} batch {batch_id!r} has non-replayable mixed "
                f"claim states {states_by_filename}; retry only recovered talks "
                "under a new batch_id"
            )

    candidate = copy.deepcopy(database)
    capability_assessor = artifact_capability_assessor(
        candidate, path, video_evidence_assessment=video_evidence_assessment
    )
    normalizations = normalize_legacy_statuses(
        candidate,
        capability_assessor=capability_assessor,
    )
    by_filename = {talk["filename"]: talk for talk in candidate["talks"]}
    if requested:
        missing = sorted(set(requested) - set(by_filename))
        if missing:
            raise QueueStateError(
                f"requested filenames are not in the database: {missing}"
            )
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
            provisional_assessment = capability_assessor(talk)

            def provisional_assessor(_talk):
                return provisional_assessment

            blocking_reason = claim_blocking_artifact_reason(
                talk,
                capability_assessor=provisional_assessor,
            )
            if blocking_reason is not None:
                raise QueueStateError(
                    f"{talk['filename']}: cannot claim: {blocking_reason}"
                )
            if not has_processable_source(
                talk,
                capability_assessor=provisional_assessor,
            ):
                raise QueueStateError(
                    f"{talk['filename']}: cannot claim a talk without a usable "
                    "transcript, slide, or video source"
                )
    else:
        eligible = [
            talk
            for talk in candidate["talks"]
            if talk["status"] in CLAIMABLE_STATUSES
            and has_claimable_source(
                talk,
                capability_assessor=capability_assessor,
            )
        ]
        selected = sorted(eligible, key=lambda talk: talk["filename"])[: args.limit]

    selected_filenames = [talk["filename"] for talk in selected]
    try:
        catalog = load_catalog()
        baseline = build_adherence_baseline(
            database["talks"],
            selected_filenames=selected_filenames,
            as_of=now_text,
            pattern_catalog_fingerprint=catalog.fingerprint,
            pattern_scoring_schema_version=PATTERN_SCORING_SCHEMA_VERSION,
            evidence_freshness_assessor=evidence_freshness_assessor(
                database,
                path,
                video_evidence_assessment=video_evidence_assessment,
            ),
            persisted_observation_assessor=persisted_observation_assessor(catalog),
        )
    except (AdherenceBaselineError, ReturnValidationError, OSError) as exc:
        raise QueueStateError(
            f"cannot snapshot the adherence baseline before claiming batch: {exc}"
        ) from exc
    claimed = [
        claim_talk(
            talk,
            run_id,
            batch_id,
            now_text,
            baseline,
            capability_assessor=capability_assessor,
        )
        for talk in selected
    ]
    remaining = sum(
        talk["status"] in CLAIMABLE_STATUSES
        and has_claimable_source(
            talk,
            capability_assessor=capability_assessor,
        )
        for talk in candidate["talks"]
    )
    if normalizations or claimed:
        validate_database(candidate)
        write_result = write_database_atomically(
            path,
            candidate,
            expected_snapshot=expected_snapshot,
        )
    else:
        write_result = unchanged_write_result(expected_snapshot)
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
        **write_result_fields(write_result),
    }


def command_recover(database, path, args, *, expected_snapshot):
    now = parse_timestamp(args.now, "--now")
    now_text = timestamp_text(now)
    run_id = require_identifier(args.run_id, "run_id") if args.run_id else None
    recovered = []
    for talk in sorted(database["talks"], key=lambda item: item["filename"]):
        claim = talk.get("_queue_claim")
        if not isinstance(claim, dict) or claim.get("state") != "claimed":
            continue
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
        status_before = talk["status"]
        status_drift = status_before != INFLIGHT_STATUS
        if not status_drift and age_seconds < args.stale_after_seconds:
            continue
        talk["status"] = claim["previous_status"]
        upgrade_claim_for_write(claim)
        claim["state"] = "stale_recovered"
        claim["released_at"] = now_text
        claim["release_reason"] = (
            "state_status_drift" if status_drift else "lease_expired"
        )
        recovered_item = {
            "filename": talk["filename"],
            "run_id": claim["run_id"],
            "batch_id": claim["batch_id"],
            "reprocess_generation": claim["reprocess_generation"],
            "status": talk["status"],
            "age_seconds": age_seconds,
        }
        if status_drift:
            recovered_item.update(
                {
                    "status_before": status_before,
                    "release_reason": "state_status_drift",
                }
            )
        recovered.append(recovered_item)
    if recovered:
        validate_database(database)
        write_result = write_database_atomically(
            path,
            database,
            expected_snapshot=expected_snapshot,
        )
    else:
        write_result = unchanged_write_result(expected_snapshot)
    return {
        "ok": True,
        "action": "recover",
        "db_path": str(path),
        "now": now_text,
        "stale_after_seconds": args.stale_after_seconds,
        "recovered": recovered,
        **write_result_fields(write_result),
    }


def command_inspect(database, path, args, *, expected_snapshot):
    write_result = unchanged_write_result(expected_snapshot)
    run_id = require_identifier(args.run_id, "run_id")
    return {
        "ok": True,
        "action": "inspect",
        "db_path": str(path),
        **reconstruct_run(database, run_id),
        **write_result_fields(write_result),
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
    parser = JsonArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("database", help="tracking-database.json path")
    actions = parser.add_subparsers(
        dest="action", required=True, parser_class=JsonArgumentParser
    )
    actions.add_parser(
        "normalize",
        help="normalize legacy source statuses and stale scoring generations",
    )

    claim = actions.add_parser("claim", help="claim a deterministic batch")
    claim.add_argument("--run-id", required=True)
    claim.add_argument("--batch-id", required=True)
    claim.add_argument(
        "--now", required=True, help="timezone-aware ISO-8601 claim time"
    )
    claim.add_argument("--limit", type=positive_integer, default=5)
    claim.add_argument(
        "--filename",
        action="append",
        help="claim this filename; repeat for an exact batch",
    )

    recover = actions.add_parser("recover", help="recover expired inflight leases")
    recover.add_argument(
        "--now", required=True, help="timezone-aware ISO-8601 reference time"
    )
    recover.add_argument("--stale-after-seconds", type=positive_integer, required=True)
    recover.add_argument("--run-id", help="recover only this run's expired claims")

    inspect = actions.add_parser("inspect", help="reconstruct claims for one run")
    inspect.add_argument("--run-id", required=True)
    return parser


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        path = materialize_native_authority(
            args.database,
            authority="database_path",
        )
        database, snapshot = load_database_snapshot(
            path,
            allow_claim_status_drift=args.action == "recover",
            require_current=args.action not in {"inspect", "recover"},
        )
        resolve_vault_root_authority(
            database_path=path,
            config=database.get("config"),
        )
        commands = {
            "normalize": command_normalize,
            "claim": command_claim,
            "recover": command_recover,
            "inspect": command_inspect,
        }
        command = commands[args.action]
        if args.action in {"normalize", "claim"}:
            payload = command(
                database,
                path,
                args,
                expected_snapshot=snapshot,
                video_evidence_assessment=VideoEvidenceAssessment(),
            )
        else:
            payload = command(
                database,
                path,
                args,
                expected_snapshot=snapshot,
            )
    except (QueueStateError, VaultRootAuthorityError) as exc:
        payload = {"ok": False, "error": str(exc)}
        print(str(exc), file=sys.stderr)
        print(json.dumps(payload, ensure_ascii=False))
        return 2
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
