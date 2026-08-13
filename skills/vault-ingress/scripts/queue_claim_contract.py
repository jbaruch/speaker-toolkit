"""Pure validation for queue claims stored in the tracking database.

This module is the single owner of queue-claim, claim-history, talk lifecycle,
and adherence-batch validation.  It deliberately has no tracking-database or
queue command imports so both the database schema owner and queue-state can use
the same contract without a circular dependency.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
import re

from adherence_baseline import (
    ADHERENCE_BASELINE_SCHEMA_VERSION,
    AdherenceBaselineError,
    CATALOG_FINGERPRINT_MISMATCH_REASON,
    LEGACY_ADHERENCE_BASELINE_SCHEMA_VERSION,
    LEGACY_GENERATION_REASON,
    MISSING_GENERATION_STATUS_REASON,
    PERSISTED_EVIDENCE_STALE_REASON,
    PERSISTED_OBSERVATIONS_INVALID_REASON,
    SCORING_SCHEMA_VERSION_MISMATCH_REASON,
    validate_adherence_baseline,
)


CURRENT_QUEUE_CLAIM_SCHEMA_VERSION = 5
LEGACY_QUEUE_CLAIM_SCHEMA_VERSION = 1
RECEIPT_QUEUE_CLAIM_SCHEMA_VERSION = 2
ADHERENCE_QUEUE_CLAIM_SCHEMA_VERSION = 3
SUPPORTED_QUEUE_CLAIM_SCHEMA_VERSIONS = frozenset(
    range(
        LEGACY_QUEUE_CLAIM_SCHEMA_VERSION,
        CURRENT_QUEUE_CLAIM_SCHEMA_VERSION + 1,
    )
)
RECEIPT_QUEUE_CLAIM_SCHEMA_VERSIONS = frozenset(
    range(
        RECEIPT_QUEUE_CLAIM_SCHEMA_VERSION,
        CURRENT_QUEUE_CLAIM_SCHEMA_VERSION + 1,
    )
)
ADHERENCE_QUEUE_CLAIM_SCHEMA_VERSIONS = frozenset(
    range(
        ADHERENCE_QUEUE_CLAIM_SCHEMA_VERSION,
        CURRENT_QUEUE_CLAIM_SCHEMA_VERSION + 1,
    )
)
INFLIGHT_STATUS = "reprocessing-inflight"
CLAIMABLE_STATUSES = frozenset(
    {
        "pending",
        "needs-reprocessing",
        "skipped_download_failed",
    }
)
LEGACY_STATUSES = frozenset({"skipped_no_video", "skipped_no_transcript"})
KNOWN_STATUSES = frozenset(
    {
        *CLAIMABLE_STATUSES,
        *LEGACY_STATUSES,
        INFLIGHT_STATUS,
        "processed",
        "processed_partial",
        "skipped_no_sources",
        "skipped_duplicate",
    }
)
QUEUE_CLAIM_STATES = frozenset(
    {"claimed", "completed", "stale_recovered", "superseded"}
)
TERMINAL_RESULT_STATUSES = frozenset(
    {
        "processed",
        "processed_partial",
        "skipped_no_sources",
        "skipped_download_failed",
        "skipped_duplicate",
    }
)

PATTERN_SCORING_REPROCESS_REASON_PREFIX = "pattern_scoring_generation:"
PATTERN_SCORING_REPROCESS_REASON_SEQUENCES = frozenset(
    {
        (MISSING_GENERATION_STATUS_REASON,),
        (LEGACY_GENERATION_REASON,),
        (CATALOG_FINGERPRINT_MISMATCH_REASON,),
        (SCORING_SCHEMA_VERSION_MISMATCH_REASON,),
        (PERSISTED_EVIDENCE_STALE_REASON,),
        (PERSISTED_OBSERVATIONS_INVALID_REASON,),
        (
            CATALOG_FINGERPRINT_MISMATCH_REASON,
            SCORING_SCHEMA_VERSION_MISMATCH_REASON,
        ),
    }
)
LEGACY_REPROCESS_REASONS = frozenset(
    {"pattern_scoring_added", "source_identity_correction"}
)

QUEUE_CLAIM_SCHEMA_UNSUPPORTED_REASON = "queue_claim_schema_version_unsupported"
ADHERENCE_BASELINE_SCHEMA_UNSUPPORTED_REASON = (
    "adherence_baseline_schema_version_unsupported"
)


class QueueClaimContractError(ValueError):
    """Stored queue lifecycle state violates the shared pure contract."""


def parse_queue_timestamp(value: object, label: str) -> datetime:
    """Parse a timezone-aware timestamp and normalize it to UTC seconds."""
    if not isinstance(value, str) or not value:
        raise QueueClaimContractError(f"{label} must be a non-empty ISO-8601 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        moment = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise QueueClaimContractError(
            f"{label} {value!r} is malformed — use a timezone-aware ISO-8601 "
            "timestamp such as 2026-07-31T18:00:00+00:00"
        ) from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise QueueClaimContractError(
            f"{label} {value!r} has no timezone — append an explicit UTC offset"
        )
    return moment.astimezone(timezone.utc).replace(microsecond=0)


def queue_timestamp_text(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def require_queue_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise QueueClaimContractError(
            f"{label} must be a non-empty string without edge whitespace"
        )
    if any(character.isspace() for character in value):
        raise QueueClaimContractError(
            f"{label} {value!r} contains whitespace — use a stable token"
        )
    return value


def is_deliberate_reprocess_reason(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if value in LEGACY_REPROCESS_REASONS:
        return True
    if not value.startswith(PATTERN_SCORING_REPROCESS_REASON_PREFIX):
        return False
    encoded_codes = value.removeprefix(PATTERN_SCORING_REPROCESS_REASON_PREFIX).split(
        "+"
    )
    return tuple(encoded_codes) in PATTERN_SCORING_REPROCESS_REASON_SEQUENCES


def _classify_queue_claim_version(
    claim: object,
    *,
    label: str,
) -> str | None:
    if not isinstance(claim, Mapping):
        raise QueueClaimContractError(f"{label} must be a JSON object")
    version = claim.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise QueueClaimContractError(
            f"{label}.schema_version must be an integer, got {version!r}"
        )
    if version > CURRENT_QUEUE_CLAIM_SCHEMA_VERSION:
        return QUEUE_CLAIM_SCHEMA_UNSUPPORTED_REASON
    if version not in SUPPORTED_QUEUE_CLAIM_SCHEMA_VERSIONS:
        raise QueueClaimContractError(
            f"{label}.schema_version {version!r} is unsupported; expected "
            f"one of {sorted(SUPPORTED_QUEUE_CLAIM_SCHEMA_VERSIONS)}"
        )
    if version not in ADHERENCE_QUEUE_CLAIM_SCHEMA_VERSIONS:
        return None
    baseline = claim.get("adherence_baseline")
    if not isinstance(baseline, Mapping) or "schema_version" not in baseline:
        return None
    baseline_version = baseline["schema_version"]
    if isinstance(baseline_version, bool) or not isinstance(baseline_version, int):
        raise QueueClaimContractError(
            f"{label}.adherence_baseline.schema_version must be an integer, "
            f"got {baseline_version!r}"
        )
    if baseline_version > ADHERENCE_BASELINE_SCHEMA_VERSION:
        return ADHERENCE_BASELINE_SCHEMA_UNSUPPORTED_REASON
    return None


def classify_queue_claim_versions(
    talks: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    """Classify future claim/baseline generations before old-shape checks.

    Malformed or explicit pre-versioning sentinels raise.  A well-formed future
    version returns a no-usable-state reason so callers never interpret its
    fields using an older schema.
    """
    for index, talk in enumerate(talks):
        current = talk.get("_queue_claim")
        if current is not None:
            reason = _classify_queue_claim_version(
                current,
                label=f"talks[{index}]._queue_claim",
            )
            if reason is not None:
                return (reason,)
        history = talk.get("_queue_claim_history", [])
        if not isinstance(history, list):
            raise QueueClaimContractError(
                f"talks[{index}]._queue_claim_history must be an array"
            )
        for history_index, claim in enumerate(history):
            reason = _classify_queue_claim_version(
                claim,
                label=f"talks[{index}]._queue_claim_history[{history_index}]",
            )
            if reason is not None:
                return (reason,)
    return ()


def validate_queue_claim(
    claim: object,
    filename: str,
    *,
    historical: bool = False,
) -> None:
    if not isinstance(claim, Mapping):
        raise QueueClaimContractError(f"{filename}: queue claim must be a JSON object")
    version = claim.get("schema_version")
    if (
        isinstance(version, int)
        and not isinstance(version, bool)
        and version > CURRENT_QUEUE_CLAIM_SCHEMA_VERSION
    ):
        raise QueueClaimContractError(
            f"{filename}: queue claim schema_version {version} is newer than "
            f"supported version {CURRENT_QUEUE_CLAIM_SCHEMA_VERSION}; upgrade "
            "queue-state before continuing"
        )
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version not in SUPPORTED_QUEUE_CLAIM_SCHEMA_VERSIONS
    ):
        raise QueueClaimContractError(
            f"{filename}: queue claim schema_version is {version!r}; expected one "
            f"of {sorted(SUPPORTED_QUEUE_CLAIM_SCHEMA_VERSIONS)}"
        )
    require_queue_identifier(claim.get("run_id"), f"{filename}: claim.run_id")
    require_queue_identifier(claim.get("batch_id"), f"{filename}: claim.batch_id")
    claimed_at = queue_timestamp_text(
        parse_queue_timestamp(claim.get("claimed_at"), f"{filename}: claim.claimed_at")
    )
    previous = claim.get("previous_status")
    if previous not in CLAIMABLE_STATUSES:
        raise QueueClaimContractError(
            f"{filename}: claim.previous_status {previous!r} cannot be restored; "
            f"expected one of {sorted(CLAIMABLE_STATUSES)}"
        )
    generation = claim.get("reprocess_generation")
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 1
    ):
        raise QueueClaimContractError(
            f"{filename}: claim.reprocess_generation must be a positive integer"
        )
    state = claim.get("state")
    if state not in QUEUE_CLAIM_STATES:
        raise QueueClaimContractError(
            f"{filename}: claim.state {state!r} is invalid; expected "
            f"{sorted(QUEUE_CLAIM_STATES)}"
        )

    if version in ADHERENCE_QUEUE_CLAIM_SCHEMA_VERSIONS:
        if claim.get("claimed_at") != claimed_at:
            raise QueueClaimContractError(
                f"{filename}: schema-v{version} claim.claimed_at must use "
                f"canonical UTC whole-second form {claimed_at!r}"
            )
        required_return = claim.get("required_return_schema_version")
        if (
            isinstance(required_return, bool)
            or not isinstance(required_return, int)
            or required_return != version
        ):
            raise QueueClaimContractError(
                f"{filename}: schema-v{version} "
                "claim.required_return_schema_version must equal its claim "
                f"schema version {version}"
            )
        try:
            baseline = validate_adherence_baseline(claim.get("adherence_baseline"))
        except AdherenceBaselineError as exc:
            raise QueueClaimContractError(
                f"{filename}: invalid schema-v{version} claim adherence_baseline: {exc}"
            ) from exc
        expected_baseline_schema = (
            ADHERENCE_BASELINE_SCHEMA_VERSION
            if version == CURRENT_QUEUE_CLAIM_SCHEMA_VERSION
            else LEGACY_ADHERENCE_BASELINE_SCHEMA_VERSION
        )
        if baseline.get("schema_version") != expected_baseline_schema:
            raise QueueClaimContractError(
                f"{filename}: schema-v{version} claim requires adherence "
                f"baseline schema {expected_baseline_schema}"
            )
        if baseline["as_of"] != claim["claimed_at"]:
            raise QueueClaimContractError(
                f"{filename}: claim adherence_baseline.as_of must equal "
                "claim.claimed_at"
            )
        if baseline["active_batch_excluded"] is not True:
            raise QueueClaimContractError(
                f"{filename}: schema-v{version} claim adherence_baseline must "
                "exclude the active batch"
            )
    elif "required_return_schema_version" in claim or "adherence_baseline" in claim:
        raise QueueClaimContractError(
            f"{filename}: schema-v{version} claim cannot carry adherence-claim "
            "return or adherence-baseline fields"
        )

    released_at = claim.get("released_at")
    if released_at is not None:
        parse_queue_timestamp(released_at, f"{filename}: claim.released_at")
    if state == "claimed" and released_at is not None:
        raise QueueClaimContractError(
            f"{filename}: an active claim cannot carry released_at"
        )
    if state != "claimed" and released_at is None:
        raise QueueClaimContractError(
            f"{filename}: a closed claim must carry released_at"
        )
    if state != "claimed" and not isinstance(claim.get("release_reason"), str):
        raise QueueClaimContractError(
            f"{filename}: a closed claim must carry release_reason"
        )
    if state == "completed":
        if claim.get("result_status") not in TERMINAL_RESULT_STATUSES:
            raise QueueClaimContractError(
                f"{filename}: a completed claim must carry a terminal result_status"
            )
        if (
            version in RECEIPT_QUEUE_CLAIM_SCHEMA_VERSIONS
            and "result_payload_sha256" not in claim
        ):
            raise QueueClaimContractError(
                f"{filename}: a schema-v{version} completed claim must carry "
                "result_payload_sha256"
            )
        receipt = claim.get("result_payload_sha256")
        if (
            receipt is None
            and version in RECEIPT_QUEUE_CLAIM_SCHEMA_VERSIONS
            and not historical
        ):
            raise QueueClaimContractError(
                f"{filename}: a current schema-v{version} completed claim must "
                "carry a return-payload SHA-256 receipt"
            )
        if receipt is not None and (
            not isinstance(receipt, str)
            or re.fullmatch(r"[0-9a-f]{64}", receipt) is None
        ):
            raise QueueClaimContractError(
                f"{filename}: completed claim result_payload_sha256 must be null "
                "for a migrated legacy claim or a lowercase SHA-256 receipt"
            )
    if historical and state == "claimed":
        raise QueueClaimContractError(f"{filename}: historical claims must be closed")


def validate_talk_queue_claim_state(
    talk: object,
    index: int,
    *,
    allow_claim_status_drift: bool = False,
) -> None:
    if not isinstance(talk, Mapping):
        raise QueueClaimContractError(f"talks[{index}] must be a JSON object")
    filename = talk.get("filename")
    if not isinstance(filename, str) or not filename or Path(filename).name != filename:
        raise QueueClaimContractError(
            f"talks[{index}].filename must be a non-empty basename, got {filename!r}"
        )
    if not filename.endswith(".md"):
        raise QueueClaimContractError(f"{filename}: filename must end in .md")
    status = talk.get("status")
    if status not in KNOWN_STATUSES:
        raise QueueClaimContractError(
            f"{filename}: status {status!r} is unknown; reconcile it before queueing"
        )

    generation = talk.get("reprocess_generation", 0)
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 0
    ):
        raise QueueClaimContractError(
            f"{filename}: reprocess_generation must be a non-negative integer"
        )
    current = talk.get("_queue_claim")
    history = talk.get("_queue_claim_history", [])
    if not isinstance(history, list):
        raise QueueClaimContractError(
            f"{filename}: _queue_claim_history must be a JSON array"
        )
    identities: set[tuple[object, object, object]] = set()
    for claim in history:
        validate_queue_claim(claim, filename, historical=True)
        assert isinstance(claim, Mapping)
        identity = (
            claim["run_id"],
            claim["batch_id"],
            claim["reprocess_generation"],
        )
        if identity in identities:
            raise QueueClaimContractError(
                f"{filename}: duplicate claim history entry {identity!r}"
            )
        identities.add(identity)
    if current is not None:
        validate_queue_claim(current, filename)
        assert isinstance(current, Mapping)
        identity = (
            current["run_id"],
            current["batch_id"],
            current["reprocess_generation"],
        )
        if identity in identities:
            raise QueueClaimContractError(
                f"{filename}: current claim duplicates claim history"
            )
        if current["reprocess_generation"] != generation:
            raise QueueClaimContractError(
                f"{filename}: current claim generation "
                f"{current['reprocess_generation']} disagrees with talk "
                f"generation {generation}"
            )
    if status == INFLIGHT_STATUS:
        if current is None:
            raise QueueClaimContractError(
                f"{filename}: {INFLIGHT_STATUS} has no reconstructable _queue_claim"
            )
        assert isinstance(current, Mapping)
        if current["state"] != "claimed":
            raise QueueClaimContractError(
                f"{filename}: {INFLIGHT_STATUS} requires claim.state='claimed'"
            )
    if (
        isinstance(current, Mapping)
        and current["state"] == "claimed"
        and status != INFLIGHT_STATUS
        and not allow_claim_status_drift
    ):
        raise QueueClaimContractError(
            f"{filename}: claim.state='claimed' requires status "
            f"{INFLIGHT_STATUS!r}, got {status!r}; run recover to repair the "
            "stranded lease"
        )
    deliberate_requeue = status == "needs-reprocessing" and (
        is_deliberate_reprocess_reason(talk.get("reprocess_reason"))
    )
    if (
        isinstance(current, Mapping)
        and current["state"] == "completed"
        and status != current.get("result_status")
        and not deliberate_requeue
    ):
        raise QueueClaimContractError(
            f"{filename}: completed claim result_status "
            f"{current.get('result_status')!r} disagrees with talk status "
            f"{status!r}"
        )


def validate_queue_claim_database(
    database: object,
    *,
    allow_claim_status_drift: bool = False,
) -> None:
    if not isinstance(database, Mapping):
        raise QueueClaimContractError("tracking database root must be a JSON object")
    talks = database.get("talks")
    if not isinstance(talks, list):
        raise QueueClaimContractError("tracking database must contain a talks array")
    seen: set[str] = set()
    typed_talks: list[Mapping[str, object]] = []
    for index, talk in enumerate(talks):
        validate_talk_queue_claim_state(
            talk,
            index,
            allow_claim_status_drift=allow_claim_status_drift,
        )
        assert isinstance(talk, Mapping)
        filename = talk["filename"]
        assert isinstance(filename, str)
        if filename in seen:
            raise QueueClaimContractError(
                f"duplicate talk filename {filename!r} — filenames are queue identities"
            )
        seen.add(filename)
        typed_talks.append(talk)
    _validate_adherence_claim_batches(typed_talks)


def _validate_adherence_claim_batches(
    talks: Sequence[Mapping[str, object]],
) -> None:
    """Require every stored v3/v4/v5 batch snapshot to be exact and shared."""
    current_batches: dict[
        tuple[object, object], list[tuple[str, Mapping[str, object]]]
    ] = {}
    claim_epochs: dict[
        tuple[object, object, object],
        list[tuple[str, Mapping[str, object]]],
    ] = {}
    for talk in talks:
        filename = talk["filename"]
        assert isinstance(filename, str)
        current = talk.get("_queue_claim")
        if (
            isinstance(current, Mapping)
            and current.get("schema_version") in ADHERENCE_QUEUE_CLAIM_SCHEMA_VERSIONS
        ):
            identity = (current["run_id"], current["batch_id"])
            current_batches.setdefault(identity, []).append((filename, current))
            epoch = (*identity, current["claimed_at"])
            claim_epochs.setdefault(epoch, []).append((filename, current))
        history = talk.get("_queue_claim_history", [])
        assert isinstance(history, list)
        for claim in history:
            assert isinstance(claim, Mapping)
            if claim.get("schema_version") not in ADHERENCE_QUEUE_CLAIM_SCHEMA_VERSIONS:
                continue
            epoch = (
                claim["run_id"],
                claim["batch_id"],
                claim["claimed_at"],
            )
            claim_epochs.setdefault(epoch, []).append((filename, claim))
    for identity, members in current_batches.items():
        claimed_at = members[0][1]["claimed_at"]
        if any(claim["claimed_at"] != claimed_at for _, claim in members):
            raise QueueClaimContractError(
                f"adherence current claims for run {identity[0]!r} batch "
                f"{identity[1]!r} do not share one claimed_at timestamp"
            )
    for epoch, members in claim_epochs.items():
        _validate_adherence_claim_batch_members(epoch[:2], members)


def _validate_adherence_claim_batch_members(
    identity: tuple[object, object],
    members: list[tuple[str, Mapping[str, object]]],
) -> None:
    expected_filenames = sorted(filename for filename, _ in members)
    canonical = members[0][1]["adherence_baseline"]
    canonical_version = members[0][1]["schema_version"]
    for filename, claim in members:
        if claim["schema_version"] != canonical_version:
            raise QueueClaimContractError(
                f"{filename}: claims for run {identity[0]!r} batch "
                f"{identity[1]!r} mix adherence schema versions"
            )
        if claim["adherence_baseline"] != canonical:
            raise QueueClaimContractError(
                f"{filename}: schema-v{canonical_version} claims for run "
                f"{identity[0]!r} batch {identity[1]!r} do not share one "
                "immutable adherence_baseline"
            )
        baseline = claim["adherence_baseline"]
        assert isinstance(baseline, Mapping)
        if baseline["excluded_filenames"] != expected_filenames:
            raise QueueClaimContractError(
                f"{filename}: schema-v{canonical_version} adherence_baseline "
                "excluded_filenames must equal the exact stored batch "
                f"{expected_filenames}"
            )
