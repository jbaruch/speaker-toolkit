#!/usr/bin/env python3
"""Download YouTube videos in parallel for slide extraction, reporting each outcome.

Usage:
    batch-download-videos.py <vault_root> ID1 [ID2 ...]

Every id must match the shared ingress YouTube grammar; the id becomes both a
directory name and a URL, so it is checked before either boundary. An id
beginning with `-` needs no escaping; a `--` separator is accepted and ignored.

Each video lands at `<vault_root>/slides-rebuild/<youtube_id>/<youtube_id>.mp4`
at 720p, with yt-dlp's combined output kept beside it as `<youtube_id>.yt-dlp.log`.

An id already carrying a complete, decode-verified video is skipped, so a large
batch resumes rather than restarting. Non-empty but damaged files fail visibly;
the owner can move them aside and retry. They are never silently overwritten.

Stdout: one JSON object.

    {"schema_version": 1, "ok": false,
     "yt_dlp": {"path": "...", "version": "2026.08.19"},
     "counts": {"ok": 1, "skip": 1, "fail": 1},
     "results": [{"youtube_id": "...", "outcome": "ok|skip|fail", ...}]}

`results` holds one entry per requested id, in the order given; an id repeated
in one invocation is rejected rather than downloaded twice. An `ok` or `skip`
entry carries `path`, `bytes`, and `integrity`; a `fail` entry carries `exit_code`,
`reason`, and `log`. An `ok` requires a zero exit, a non-empty file, and full
decode verification by video_integrity.py before promotion — a run that
exits non-zero having left a truncated file behind fails, and its partial output
is discarded so the next run retries rather than skipping it.

A usage or yt-dlp resolution failure is reported the same way, as a typed
object drawn from a closed vocabulary rather than prose:

    {"schema_version": 1, "ok": false, "code": "ytdlp_not_found",
     "error": "cannot find yt-dlp — ..."}

An `unexpected_failure` adds `error_type` and `origin`, the exception's type and
its sanitized code locations. Its message never crosses the boundary: an OSError
message embeds the host path it could not reach.

Stderr: the resolved yt-dlp path and version, then one warning line per failure.
A typed failure writes its message there too, so a caller reading only stderr
still sees what to do.

Exit 0 when every id ended `ok` or `skip`, 1 when any id failed, 2 on a usage or
yt-dlp resolution error, 3 when the run failed unexpectedly. Every one of those
exits writes a JSON object to stdout.

A stale yt-dlp answers every download with HTTP 403 while the pinned one
succeeds, so the binary is resolved explicitly rather than taken from PATH, and
the resolved path and version are announced before the first download.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

from failure_diagnostics import sanitized_frames
from artifact_supervisor import FileGeneration, SupervisorError
from ingress_contract import YOUTUBE_ID_RE
from video_evidence import VideoEvidenceError, probe_video_artifact
from video_integrity import VideoIntegrityError, verify_video_integrity
from ytdlp_runtime import YtDlpResolutionError, resolve_ytdlp

USAGE = "usage: batch-download-videos.py <vault_root> ID1 [ID2 ...]"

# Closed vocabulary for a typed exit-2 failure. Every code names a condition the
# caller can act on without parsing the message.
FAILURE_CODES = frozenset(
    {
        "usage",
        "youtube_id_invalid",
        "youtube_id_duplicated",
        "ytdlp_override_invalid",
        "ytdlp_not_found",
        "ytdlp_version_unavailable",
        "unexpected_failure",
    }
)

REPORT_SCHEMA_VERSION = 1

# Three at a time saturates a home connection without starving any one download.
MAX_CONCURRENT_DOWNLOADS = 3

# yt-dlp diagnostics quote the signed media URLs it was handed, whose query
# strings carry expiry and signature parameters. Both patterns are fully
# enumerable, so redaction is a script's job rather than a judgement call.
_URL_QUERY_RE = re.compile(r"(https?://[^\s?#]*)[?#]\S*")
# A header value may contain spaces (`Authorization: Bearer <token>`), so this
# form redacts to end of line. Over-redacting a diagnostic line is safe; leaving
# half a credential in it is not.
_SENSITIVE_HEADER_RE = re.compile(
    r"\b(authorization|proxy-authorization|set-cookie|cookie|x-api-key|api-key"
    r"|token|password|passwd|secret)\s*:\s*.*",
    re.IGNORECASE,
)
# A query or form parameter ends at its own delimiter, so redaction stops there
# and whatever followed — an HTTP status, the next parameter — still reads.
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"\b(token|signature|sig|secret|password|passwd|auth|authorization|cookie"
    r"|session|api[_-]?key)\s*=\s*[^\s&;]+",
    re.IGNORECASE,
)

# 720p reads slide text while staying small enough to extract frames from
# quickly; yt-dlp falls back to the best available when 720p is absent.
VIDEO_FORMAT = (
    "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
    "/best[height<=720][ext=mp4]"
    "/best[height<=720]"
)


def probe_version(ytdlp: Path) -> str:
    """Read the resolved binary's version, so a stale build is visible up front."""
    try:
        completed = subprocess.run(
            [str(ytdlp), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise YtDlpResolutionError(
            "ytdlp_version_unavailable",
            f"cannot run {ytdlp} ({redact(str(exc))}) — reinstall yt-dlp or set "
            "YT_DLP to a working binary",
        ) from exc
    version = completed.stdout.strip()
    if completed.returncode != 0 or not version:
        # A configured executable is not trusted to keep credentials out of
        # its own diagnostics, so its words cross this boundary redacted.
        detail = redact(completed.stderr.strip()) or f"exit {completed.returncode}"
        raise YtDlpResolutionError(
            "ytdlp_version_unavailable",
            f"{ytdlp} did not report a version ({detail}) — reinstall yt-dlp or "
            "set YT_DLP to a working binary",
        )
    return version


def redact(text: str) -> str:
    """Strip signed-URL query strings and credential-bearing values from text."""
    text = _URL_QUERY_RE.sub(r"\1?<redacted>", text)
    text = _SENSITIVE_HEADER_RE.sub(lambda match: f"{match.group(1)}: <redacted>", text)
    return _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}=<redacted>", text
    )


def failure_reason(output: str) -> str:
    """Name why a download produced nothing, preferring yt-dlp's own ERROR line."""
    lines = output.splitlines()
    for line in lines:
        if line.startswith("ERROR"):
            return line.strip()
    for line in reversed(lines):
        if line.strip():
            return line.strip()
    return "no output file and no yt-dlp diagnostic"


def _verify_download(path: Path) -> dict[str, object]:
    try:
        receipt = verify_video_integrity(path)
        if (
            FileGeneration.from_stat(path.lstat()).to_dict()
            != receipt["source_generation"]
        ):
            raise VideoIntegrityError("integrity_source_changed")
        return receipt
    except (SupervisorError, VideoEvidenceError) as exc:
        raise VideoIntegrityError(exc.reason_code, exc.details) from exc
    except OSError as exc:
        raise VideoIntegrityError("integrity_source_unavailable") from exc


def _bind_promoted_integrity(path: Path, receipt: dict[str, object]) -> None:
    """A rename changes ctime, not the verified object, bytes, or other metadata."""
    raw = receipt["source_generation"]
    if not isinstance(raw, dict):
        raise VideoIntegrityError("integrity_source_changed")
    expected = FileGeneration.from_dict(raw)
    try:
        observed = FileGeneration.from_stat(path.lstat())
    except OSError as exc:
        raise VideoIntegrityError("integrity_source_changed") from exc
    if replace(observed, ctime_ns=expected.ctime_ns) != expected:
        raise VideoIntegrityError("integrity_source_changed")
    # A rename and an in-place write both change ctime. Re-probe the promoted
    # bytes so a same-size write with restored mtime cannot hide in that carve-out.
    try:
        probe = probe_video_artifact(path)
    except (VideoEvidenceError, SupervisorError) as exc:
        raise VideoIntegrityError(exc.reason_code, exc.details) from exc
    if probe.generation != observed or probe.source_sha256 != receipt["source_sha256"]:
        raise VideoIntegrityError("integrity_source_changed")
    receipt["source_generation"] = probe.generation.to_dict()


def download_one(ytdlp: Path, vault_root: Path, youtube_id: str) -> dict[str, object]:
    """Download one video, returning its outcome rather than raising."""
    target_dir = vault_root / "slides-rebuild" / youtube_id
    target = target_dir / f"{youtube_id}.mp4"
    # yt-dlp writes here and the file is promoted to `target` only once the run
    # verifies, so nothing unverified can ever satisfy the resume check above —
    # not even when the cleanup below cannot remove it. The `.mp4` suffix stays
    # last so yt-dlp still picks the right container for the merge.
    staging = target_dir / f"{youtube_id}.incomplete.mp4"
    log_path = target_dir / f"{youtube_id}.yt-dlp.log"

    if target.is_file() and target.stat().st_size > 0:
        try:
            integrity = _verify_download(target)
        except VideoIntegrityError as exc:
            return {
                "youtube_id": youtube_id,
                "outcome": "fail",
                "exit_code": None,
                "reason_code": exc.code,
                "reason": f"existing recording failed integrity verification ({exc.code}) — "
                "check the runtime or move the damaged file aside, then rerun this id",
                "log": None,
                "integrity_details": exc.details,
            }
        return {
            "youtube_id": youtube_id,
            "outcome": "skip",
            "path": str(target),
            "bytes": target.stat().st_size,
            "integrity": integrity,
        }

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "youtube_id": youtube_id,
            "outcome": "fail",
            "exit_code": None,
            "reason": (
                f"cannot create {target_dir} ({redact(str(exc))}) — check the "
                "vault root exists and is writable, then rerun this id"
            ),
            "log": None,
        }

    # A staging file surviving an earlier attempt must not reach yt-dlp: it
    # reports a non-empty output path as already downloaded and exits zero,
    # which would promote the stale partial as this run's video.
    if staging.exists():
        try:
            staging.unlink()
        except OSError as exc:
            return {
                "youtube_id": youtube_id,
                "outcome": "fail",
                "exit_code": None,
                "reason": (
                    f"a partial download at {staging} could not be removed "
                    f"({redact(str(exc))}) — delete that file, then rerun this "
                    "id"
                ),
                "log": None,
            }

    command = [
        str(ytdlp),
        "-f",
        VIDEO_FORMAT,
        "--merge-output-format",
        "mp4",
        "--no-progress",
        "-o",
        str(staging),
        f"https://www.youtube.com/watch?v={youtube_id}",
    ]
    # Captured rather than streamed straight to the log: yt-dlp quotes the
    # signed URL it was handed, and writing that to disk first would leave the
    # credential there for any interrupt or rewrite failure to make permanent.
    # `--no-progress` keeps the captured output to a few kilobytes.
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
    except OSError as exc:
        return {
            "youtube_id": youtube_id,
            "outcome": "fail",
            "exit_code": None,
            "reason": (
                f"cannot run {ytdlp} ({redact(str(exc))}) — reinstall yt-dlp "
                "into the toolkit environment, or point YT_DLP at a working "
                "binary, then rerun this id"
            ),
            "log": None,
        }
    exit_code = completed.returncode
    output = redact(completed.stdout or "")
    log_fields: dict[str, object] = {}
    try:
        log_path.write_text(output)
        log_fields["log"] = str(log_path)
    except OSError as exc:
        # The download's own outcome still stands; what is lost is the record of
        # how it went, and losing that quietly is the failure this script exists
        # to remove.
        log_fields["log"] = None
        log_fields["log_error"] = (
            f"the yt-dlp log could not be written to {log_path} "
            f"({redact(str(exc))}); the outcome below stands, but this run's "
            "diagnostic output was not kept — check write permission on that "
            "directory before relying on the log next time"
        )

    # Success needs both halves: yt-dlp can exit zero having produced nothing
    # usable after a failed merge, and it can exit non-zero having left a
    # truncated file behind.
    written = staging.is_file() and staging.stat().st_size > 0
    if exit_code == 0 and written:
        try:
            integrity = _verify_download(staging)
        except VideoIntegrityError as exc:
            return {
                "youtube_id": youtube_id,
                "outcome": "fail",
                "exit_code": exit_code,
                "reason_code": exc.code,
                "reason": f"download failed integrity verification ({exc.code}) — "
                "check the runtime and retry; unverified staging output was not promoted",
                "integrity_details": exc.details,
                **log_fields,
            }
        size = integrity["source_size_bytes"]
        try:
            staging.replace(target)
        except OSError as exc:
            return {
                "youtube_id": youtube_id,
                "outcome": "fail",
                "exit_code": exit_code,
                "reason": (
                    f"downloaded but could not be promoted to {target} "
                    f"({redact(str(exc))}) — check free space and write "
                    "permission on that directory, then rerun this id; the "
                    "download starts over"
                ),
                **log_fields,
            }
        try:
            _bind_promoted_integrity(target, integrity)
        except VideoIntegrityError as exc:
            return {
                "youtube_id": youtube_id,
                "outcome": "fail",
                "exit_code": exit_code,
                "reason_code": exc.code,
                "reason": "recording changed during promotion — inspect the target and "
                "rerun verification before using it as evidence",
                **log_fields,
            }
        return {
            "youtube_id": youtube_id,
            "outcome": "ok",
            "path": str(target),
            "bytes": size,
            "integrity": integrity,
            **log_fields,
        }

    reason = failure_reason(output)
    if written:
        # Best-effort here; the next attempt removes it up front, and refuses to
        # run when it cannot.
        try:
            staging.unlink()
        except OSError:
            reason = f"{reason} (partial output left in {target_dir})"
    elif exit_code == 0:
        reason = f"exited 0 without producing a video — {reason}"
    return {
        "youtube_id": youtube_id,
        "outcome": "fail",
        "exit_code": exit_code,
        "reason": reason,
        **log_fields,
    }


def execute(vault_root: Path, youtube_ids: list[str]) -> dict[str, object]:
    """Download every id and assemble the report, failures included."""
    ytdlp = resolve_ytdlp()
    version = probe_version(ytdlp)
    print(f"yt-dlp: {ytdlp} ({version})", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS) as pool:
        results = list(
            pool.map(
                lambda youtube_id: download_one(ytdlp, vault_root, youtube_id),
                youtube_ids,
            )
        )

    counts = {"ok": 0, "skip": 0, "fail": 0}
    for result in results:
        outcome = result["outcome"]
        assert isinstance(outcome, str)
        counts[outcome] += 1
        if outcome == "fail":
            print(
                f"warning: {result['youtube_id']} — {result['reason']}",
                file=sys.stderr,
            )
        log_error = result.get("log_error")
        if log_error:
            print(f"warning: {result['youtube_id']} — {log_error}", file=sys.stderr)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": counts["fail"] == 0,
        "yt_dlp": {"path": str(ytdlp), "version": version},
        "vault_root": str(vault_root),
        "counts": counts,
        "results": results,
    }


def report_failure(
    code: str,
    message: str,
    *,
    error_type: str | None = None,
    origin: list[str] | None = None,
) -> int:
    """Emit one typed failure on stdout and its actionable line on stderr.

    Serialized before it is written, so a failure while building the document
    leaves stdout empty rather than holding half of one.
    """
    document: dict[str, object] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": False,
        "code": code,
        "error": message,
    }
    if error_type is not None:
        document["error_type"] = error_type
    if origin is not None:
        document["origin"] = origin
    sys.stdout.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(message, file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    # Hand-parsed rather than argparse: a YouTube id may legitimately begin with
    # `-`, which argparse reads as a flag.
    # There is no `--help` path: stdout carries one JSON object on every exit,
    # and prose there would hand a JSON-consuming caller non-JSON on a zero
    # exit. The docstring above is the help.
    arguments = list(sys.argv[1:] if argv is None else argv)
    # No argument is a flag, so a leading-dash id already reads as an id; a `--`
    # separator is accepted out of habit and dropped.
    if "--" in arguments:
        arguments.remove("--")
    if len(arguments) < 2:
        return report_failure("usage", USAGE)

    vault_root = Path(arguments[0])
    youtube_ids = arguments[1:]
    # The id becomes a directory name and a URL, so it is checked against the
    # shared ingress grammar before either boundary.
    invalid = [value for value in youtube_ids if YOUTUBE_ID_RE.fullmatch(value) is None]
    if invalid:
        return report_failure(
            "youtube_id_invalid",
            f"not YouTube ids: {' '.join(invalid)} — each must match "
            f"{YOUTUBE_ID_RE.pattern}",
        )
    # Two workers on one id would write the same file at the same time. Rejected
    # rather than deduplicated, so `results` keeps one entry per argument.
    counted: set[str] = set()
    repeated = sorted(
        {value for value in youtube_ids if value in counted or counted.add(value)}
    )
    if repeated:
        return report_failure(
            "youtube_id_duplicated",
            f"repeated YouTube ids: {' '.join(repeated)} — pass each id once",
        )

    try:
        report = execute(vault_root, youtube_ids)
    except YtDlpResolutionError as exc:
        return report_failure(exc.code, str(exc))
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["ok"] else 1


def run_cli(argv: list[str] | None = None) -> int:
    """Run the CLI behind its failure boundary. Returns the process exit code.

    Importable so the boundary's contract is testable without executing the
    module as a script.
    """
    try:
        return main(argv)
    # A caller parses stdout as one JSON object on every exit, so a traceback
    # with empty stdout reads as "no videos were requested" rather than as a
    # failed run — the same silence this script exists to remove. The catch
    # emits the typed `unexpected_failure` object naming the exception; letting
    # it propagate would break the contract at the only boundary that has one.
    except Exception as exc:  # noqa: BLE001 - outer-boundary-process-contract
        # `no-secrets`: the exception TYPE and sanitized frames cross the
        # boundary, never its message — an OSError message embeds the host path
        # it could not reach.
        report_failure(
            "unexpected_failure",
            "the download run failed unexpectedly — no video is guaranteed "
            "downloaded; rerun once the cause is fixed, since ids already on "
            "disk are skipped",
            error_type=type(exc).__name__,
            origin=sanitized_frames(exc),
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(run_cli())
