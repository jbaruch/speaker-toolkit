#!/usr/bin/env python3
"""Render the owner status block in rhetoric-style-summary.md (#168).

`rhetoric-style-summary.md` is narrative prose, but its status line is read as
current operational fact. Hand-maintained, it drifts: a verified snapshot had
the summary claiming `199 / 208` with 195 processed while the tracking database
held 209 talks, 116 of them `needs-reprocessing`. Queue normalization and
reparse move statuses without touching the prose, so a human or an agent reads
an obsolete cohort as live — most misleadingly during a long reparse.

This renders that one block from the database and nothing else. Counts are
derived from a single strict snapshot, never hand-calculated, and the block is
delimited and schema-versioned so replacing it cannot disturb a narrative
section.

`--apply` requires `--expected-sha256` from a dry run: the summary is a file a
human also edits, so an apply that cannot prove it read the current bytes must
refuse rather than overwrite an edit it never saw. The read, the digest check,
and the install all run inside the summary's shared cooperative lock, so no
second toolkit writer can land between the check and the swap; the bytes are
rechecked once more immediately before the rename, which is what catches a
human editor, who holds no lock. Replacement is atomic through the shared
retained-stage lifecycle, so an interruption leaves the prior complete summary.

Usage:
  render-vault-status.py <vault-root-or-database-path> [--summary <path>]
  render-vault-status.py <...> --apply --expected-sha256 <hex>
Stdout: one JSON object carrying the rendered block and the derived counts.
Stderr: one actionable, path-neutral line when the database cannot be read.
Exit 0 on success, 2 when the database or summary cannot be read, locked, or
installed, 3 when the summary's bytes do not match `--expected-sha256`.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager, ExitStack
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterator

from cooperative_lock import (
    CooperativeLockError,
    exclusive_file_lock,
)
from retained_stage import (
    RetainedStageError,
    close_retained_stage,
    install_retained_stage,
    open_retained_stage,
)
from tracking_database import (
    TrackingDatabaseError,
    assess_tracking_database,
    tracking_database_schema_version,
)
from tracking_database_io import (
    DATABASE_READ_DIAGNOSTICS,
    DATABASE_READ_FALLBACK,
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)

REPORT_SCHEMA_VERSION = 1
STATUS_BLOCK_SCHEMA_VERSION = 1
DATABASE_BASENAME = "tracking-database.json"
SUMMARY_BASENAME = "rhetoric-style-summary.md"

# Names the summary in every cooperative-lock diagnostic. Every toolkit writer
# of this file takes that lock, so the check-and-swap below is one critical
# section rather than two racing operations.
SUMMARY_LOCK_LABEL = "rhetoric-summary"

# The block is fenced by exact literals so replacement is a delimited splice,
# never a heuristic match against narrative prose that may quote a count.
BLOCK_BEGIN = "<!-- vault-status:begin -->"
BLOCK_END = "<!-- vault-status:end -->"

# Eligibility in the CURRENT generation is a status question. Whether a talk was
# ever analysed is not: normalization flips `status` to `needs-reprocessing` and
# leaves the analysis evidence in place, so reading history off the status would
# erase every requeued talk's past work — the exact misreading this block exists
# to stop. History is therefore read from the persisted evidence itself.
CURRENT_COHORT_STATUSES = frozenset({"processed", "processed_partial"})
ANALYSIS_EVIDENCE_FIELD = "pattern_observations"


class SummaryRenderError(Exception):
    """The summary file cannot be read or replaced, with a typed reason."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def resolve_input(value: str | Path) -> tuple[Path, Path, Path]:
    """Bind a vault root to its database and its summary."""
    path = Path(value).expanduser().absolute()
    root = path.parent if path.name.lower() == DATABASE_BASENAME else path
    return root, root / DATABASE_BASENAME, root / SUMMARY_BASENAME


def _active_claims(talks: list[Any]) -> int:
    """Talks a queue writer currently holds.

    Counted from the same two signals the owner uses elsewhere: an explicit
    in-flight status, or a claim record still in the `claimed` state.
    """
    active = 0
    for talk in talks:
        if not isinstance(talk, dict):
            continue
        claim = talk.get("_queue_claim")
        if talk.get("status") == "reprocessing-inflight" or (
            isinstance(claim, dict) and claim.get("state") == "claimed"
        ):
            active += 1
    return active


def _scoring_generation(database: dict[str, Any]) -> dict[str, Any]:
    """The active scoring/catalog generation identity, as stored.

    Absent is reported as absent. Substituting a default would let a database
    with no recorded generation render a block claiming one.
    """
    config = database.get("config")
    config = config if isinstance(config, dict) else {}
    return {
        "pattern_scoring_schema_version": config.get("pattern_scoring_schema_version"),
        "pattern_catalog_fingerprint": config.get("pattern_catalog_fingerprint"),
    }


def derive_status(database: dict[str, Any], *, input_sha256: str) -> dict[str, Any]:
    """Derive every count from one snapshot. Nothing here is hand-maintained."""
    raw_talks = database.get("talks")
    talks = raw_talks if isinstance(raw_talks, list) else []
    statuses: Counter[str] = Counter()
    for talk in talks:
        if not isinstance(talk, dict):
            continue
        status = talk.get("status")
        if isinstance(status, str):
            statuses[status] += 1
    historically = sum(
        1
        for talk in talks
        if isinstance(talk, dict) and talk.get(ANALYSIS_EVIDENCE_FIELD)
    )
    return {
        "schema_version": STATUS_BLOCK_SCHEMA_VERSION,
        "database_sha256": input_sha256,
        "database_schema_version": tracking_database_schema_version(database),
        "scoring_generation": _scoring_generation(database),
        "total_talks": len(talks),
        "status_counts": {key: statuses[key] for key in sorted(statuses)},
        "active_claim_count": _active_claims(talks),
        # The distinction normalization keeps erasing: a requeued talk still
        # carries its analysis evidence, so it stays historically analysed
        # while ceasing to be eligible in the current generation.
        "historically_analysed_count": historically,
        "current_cohort_count": sum(
            count
            for status, count in statuses.items()
            if status in CURRENT_COHORT_STATUSES
        ),
    }


def render_block(status: dict[str, Any], *, generated_at: str) -> str:
    """Render the delimited block. Byte-stable for one snapshot and timestamp."""
    payload = dict(status)
    payload["generated_at"] = generated_at
    body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    return (
        f"{BLOCK_BEGIN}\n"
        f"<!-- Owner-generated by "
        f"skills/vault-ingress/scripts/render-vault-status.py. Do not hand-edit: "
        f"every value is derived from the tracking database named by "
        f"database_sha256. -->\n"
        f"```json\n{body}\n```\n"
        f"{BLOCK_END}"
    )


def splice_block(summary_text: str, block: str) -> str:
    """Replace the delimited block, or append one when the summary has none."""
    if summary_text.count(BLOCK_BEGIN) > 1 or summary_text.count(BLOCK_END) > 1:
        # A second delimiter pair, or one quoted in narrative, would make the
        # splice target a range this tool never inspected.
        raise SummaryRenderError(
            "summary carries more than one status-block delimiter",
            reason_code="summary_block_malformed",
        )
    begin = summary_text.find(BLOCK_BEGIN)
    end = summary_text.find(BLOCK_END)
    if begin == -1 and end == -1:
        separator = "" if summary_text.endswith("\n\n") else "\n"
        if summary_text and not summary_text.endswith("\n"):
            separator = "\n\n"
        return f"{summary_text}{separator}{block}\n"
    if begin == -1 or end == -1 or end < begin:
        raise SummaryRenderError(
            "summary status-block delimiters are missing or out of order",
            reason_code="summary_block_malformed",
        )
    return summary_text[:begin] + block + summary_text[end + len(BLOCK_END) :]


def _read_summary(path: Path) -> tuple[str, str]:
    """Read the summary's exact bytes, or say what to do about it.

    Messages stay path-neutral — a host path in a failure line is the leak this
    tool's diagnostics contract exists to prevent — so recovery is named by the
    file's canonical basename and by the flag that overrides it.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise SummaryRenderError(
            f"summary file does not exist: create {SUMMARY_BASENAME} in the vault "
            "root, or pass --summary with the path to the existing summary",
            reason_code="summary_missing",
        ) from error
    except OSError as error:
        raise SummaryRenderError(
            f"summary file could not be read: confirm {SUMMARY_BASENAME} is a "
            "readable regular file (not a directory, dangling symlink, or "
            "unreadable mount), then rerun",
            reason_code="summary_unreadable",
        ) from error
    try:
        return raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()
    except UnicodeError as error:
        raise SummaryRenderError(
            f"summary file is not valid UTF-8: re-save {SUMMARY_BASENAME} as UTF-8, "
            "or pass --summary with a UTF-8 copy, then rerun",
            reason_code="summary_not_utf8",
        ) from error


def _precondition_failed() -> SummaryRenderError:
    """One wording for every point the bound digest stops matching."""
    return SummaryRenderError(
        "summary bytes changed since the digest this apply is bound to: rerun the "
        "dry run and apply with the sha256 it reports",
        reason_code="summary_precondition_failed",
    )


def _require_expected_summary(summary_path: Path, expected_sha256: str) -> None:
    """Prove the live summary is still the generation the caller read."""
    _, observed = _read_summary(summary_path)
    if observed != expected_sha256:
        raise _precondition_failed()


@contextmanager
def _summary_lock(summary_path: Path) -> Iterator[None]:
    """Hold the summary's shared writer lock, in this tool's error terms.

    Acquisition is wrapped alone: a lock failure raised by the guarded body
    belongs to that body, not to this acquisition.
    """
    stack = ExitStack()
    try:
        lock = stack.enter_context(
            exclusive_file_lock(summary_path, label=SUMMARY_LOCK_LABEL)
        )
    except CooperativeLockError as error:
        # Path-neutral like every other failure here: the lock's own message
        # names the host path, so it is diagnosed by shape instead.
        raise SummaryRenderError(
            "summary writer lock could not be taken: confirm the vault root is "
            f"writable and that its .{SUMMARY_BASENAME}.lock is a regular file, "
            "then rerun",
            reason_code="summary_lock_failed",
        ) from error
    try:
        with stack:
            yield
    finally:
        for warning in lock.warnings:
            print(f"WARNING: {warning}", file=sys.stderr)


def _plan_replacement(
    summary_path: Path,
    block: str,
    *,
    expected_sha256: str | None = None,
) -> tuple[str, bytes, bool]:
    """Read the summary once and render its replacement from that observation."""
    summary_text, summary_sha256 = _read_summary(summary_path)
    if expected_sha256 is not None and expected_sha256 != summary_sha256:
        raise _precondition_failed()
    payload = splice_block(summary_text, block).encode("utf-8")
    return summary_sha256, payload, payload != summary_text.encode("utf-8")


def _install(summary_path: Path, payload: bytes, *, expected_sha256: str) -> None:
    """Replace the summary, bound to the bytes the caller proved it read.

    Called with the cooperative lock held, so no other toolkit writer sits
    between the check and the rename. The recheck here is what covers the
    writer no lock can reach — a human saving the file in an editor.
    """
    stage = open_retained_stage(
        summary_path,
        payload,
        mode=0o644,
        suffix=".vault-status",
        label="rhetoric summary",
    )
    try:
        _require_expected_summary(summary_path, expected_sha256)
        install_retained_stage(stage, summary_path)
    except OSError as error:
        raise SummaryRenderError(
            "summary replacement could not be installed: confirm the vault root is "
            "writable with free space, then rerun the dry run and apply again",
            reason_code="summary_install_failed",
        ) from error
    finally:
        close_retained_stage(stage)


def execute(
    value: str | Path,
    *,
    generated_at: str,
    apply_requested: bool = False,
    expected_sha256: str | None = None,
    summary_override: Path | None = None,
) -> dict[str, Any]:
    _root, database_path, default_summary = resolve_input(value)  # noqa: F841
    summary_path = summary_override or default_summary

    snapshot = snapshot_tracking_database(database_path)
    database = decode_json_object(snapshot)
    try:
        assessment = assess_tracking_database(database)
    except TrackingDatabaseError as exc:
        raise TrackingDatabaseIOError(
            "tracking database owner assessment failed",
            reason_code="owner_assessment_failed",
        ) from exc
    if not assessment.usable:
        raise TrackingDatabaseIOError(
            "tracking database has no usable legacy/current owner state",
            reason_code="owner_state_unusable",
        )

    status = derive_status(database, input_sha256=snapshot.sha256)
    block = render_block(status, generated_at=generated_at)

    written = False
    if not apply_requested:
        summary_sha256, payload, changed = _plan_replacement(summary_path, block)
    else:
        if expected_sha256 is None:
            raise SummaryRenderError(
                "--apply requires --expected-sha256 from a dry-run report",
                reason_code="summary_precondition_missing",
            )
        # Read, check, and install are one critical section. Splitting them —
        # checking outside the lock and installing inside it — is the race this
        # tool promises it does not have.
        with _summary_lock(summary_path):
            summary_sha256, payload, changed = _plan_replacement(
                summary_path,
                block,
                expected_sha256=expected_sha256,
            )
            # A no-op render installs nothing: rewriting identical bytes would
            # churn the file's identity for consumers watching it.
            if changed:
                _install(summary_path, payload, expected_sha256=expected_sha256)
                written = True

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": True,
        "mode": "apply" if apply_requested else "dry-run",
        "database_path": str(snapshot.path),
        "summary_path": str(summary_path),
        "summary_sha256": summary_sha256,
        "rendered_sha256": hashlib.sha256(payload).hexdigest(),
        "changed": changed,
        "summary_written": written,
        "status": status,
        "block": block,
    }


def _failure(reason_code: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": False,
        "code": reason_code,
        "error": message,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("vault_or_database", type=Path)
    parser.add_argument("--summary", type=Path, help="override the summary path")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-sha256")
    parser.add_argument(
        "--generated-at",
        required=True,
        help="ISO timestamp recorded in the block; supplied so a render is reproducible",
    )
    args = parser.parse_args(argv)

    try:
        report = execute(
            args.vault_or_database,
            generated_at=args.generated_at,
            apply_requested=args.apply,
            expected_sha256=args.expected_sha256,
            summary_override=args.summary,
        )
    except TrackingDatabaseIOError as exc:
        # Never echo the exception: decoder messages carry the host path and
        # the rejected content verbatim.
        code, message = DATABASE_READ_DIAGNOSTICS.get(
            exc.reason_code, DATABASE_READ_FALLBACK
        )
        print(json.dumps(_failure(code, message), sort_keys=True))
        print(f"vault status render failed: {message}", file=sys.stderr)
        return 2
    except SummaryRenderError as exc:
        print(json.dumps(_failure(exc.reason_code, str(exc)), sort_keys=True))
        print(f"vault status render failed: {exc}", file=sys.stderr)
        return 3 if exc.reason_code == "summary_precondition_failed" else 2
    except RetainedStageError as exc:
        print(
            json.dumps(
                _failure(
                    "summary_stage_invariant", "staged summary failed its binding"
                ),
                sort_keys=True,
            )
        )
        print(f"vault status render failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
