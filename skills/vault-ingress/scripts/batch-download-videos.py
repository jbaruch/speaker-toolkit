#!/usr/bin/env python3
"""Download YouTube videos in parallel for slide extraction, reporting each outcome.

Usage:
    batch-download-videos.py <vault_root> ID1 [ID2 ...]

Every id must match the shared ingress YouTube grammar; the id becomes both a
directory name and a URL, so it is checked before either boundary. An id
beginning with `-` needs no escaping; a `--` separator is accepted and ignored.

Each video lands at `<vault_root>/slides-rebuild/<youtube_id>/<youtube_id>.mp4`
at 720p, with yt-dlp's combined output kept beside it as `<youtube_id>.yt-dlp.log`.

An id already carrying a non-empty video is skipped, so a large batch resumes
rather than restarting.

Stdout: one JSON object.

    {"schema_version": 1, "ok": false,
     "yt_dlp": {"path": "...", "version": "2026.08.19"},
     "counts": {"ok": 1, "skip": 1, "fail": 1},
     "results": [{"youtube_id": "...", "outcome": "ok|skip|fail", ...}]}

`results` holds one entry per requested id, in the order given. An `ok` or
`skip` entry carries `path` and `bytes`; a `fail` entry carries `exit_code`,
`reason`, and `log`.

A usage or yt-dlp resolution failure is reported the same way, as a typed
object drawn from a closed vocabulary rather than prose:

    {"schema_version": 1, "ok": false, "code": "ytdlp_not_found",
     "error": "cannot find yt-dlp — ..."}

Stderr: the resolved yt-dlp path and version, then one warning line per failure.
A typed failure writes its message there too, so a caller reading only stderr
still sees what to do.

Exit 0 when every id ended `ok` or `skip`, 1 when any id failed, 2 on a usage or
yt-dlp resolution error.

A stale yt-dlp answers every download with HTTP 403 while the pinned one
succeeds, so the binary is resolved explicitly rather than taken from PATH, and
the resolved path and version are announced before the first download.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
import sys

from ingress_contract import YOUTUBE_ID_RE

USAGE = "usage: batch-download-videos.py <vault_root> ID1 [ID2 ...]"

# Closed vocabulary for a typed exit-2 failure. Every code names a condition the
# caller can act on without parsing the message.
FAILURE_CODES = frozenset(
    {
        "usage",
        "youtube_id_invalid",
        "ytdlp_override_invalid",
        "ytdlp_not_found",
        "ytdlp_version_unavailable",
    }
)

REPORT_SCHEMA_VERSION = 1

# Three at a time saturates a home connection without starving any one download.
MAX_CONCURRENT_DOWNLOADS = 3

# 720p reads slide text while staying small enough to extract frames from
# quickly; yt-dlp falls back to the best available when 720p is absent.
VIDEO_FORMAT = (
    "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
    "/best[height<=720][ext=mp4]"
    "/best[height<=720]"
)


class YtDlpResolutionError(RuntimeError):
    """No usable yt-dlp executable, reported with what to do about it."""

    def __init__(self, code: str, message: str) -> None:
        if code not in FAILURE_CODES:
            raise ValueError("invalid yt-dlp resolution failure code")
        super().__init__(message)
        self.code = code


def resolve_ytdlp() -> Path:
    """Find the pinned yt-dlp, falling back to PATH only as a last resort.

    An explicit override wins; then the console script beside the running
    interpreter, which is the pinned one whenever the toolkit runs from the
    environment that declares it; then the toolkit's own virtualenv, for a run
    driven by a system interpreter; then PATH.
    """
    override = os.environ.get("YT_DLP")
    if override:
        candidate = Path(override)
        if os.access(candidate, os.X_OK) and candidate.is_file():
            return candidate
        raise YtDlpResolutionError(
            "ytdlp_override_invalid",
            f"YT_DLP is set to {override!r}, which is not an executable file — "
            "point it at a yt-dlp binary or unset it",
        )

    candidates = [Path(sys.executable).parent / "yt-dlp"]
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        candidates.append(Path(virtual_env) / "bin" / "yt-dlp")
    toolkit_root = Path(__file__).resolve().parents[3]
    candidates.append(toolkit_root / ".venv" / "bin" / "yt-dlp")
    for candidate in candidates:
        if os.access(candidate, os.X_OK) and candidate.is_file():
            return candidate

    found = shutil.which("yt-dlp")
    if found:
        return Path(found)
    raise YtDlpResolutionError(
        "ytdlp_not_found",
        "cannot find yt-dlp — install the pinned version with `pip install .` "
        "into the toolkit environment, or set YT_DLP to its path",
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
            f"cannot run {ytdlp} ({exc}) — reinstall yt-dlp or set YT_DLP to a "
            "working binary",
        ) from exc
    version = completed.stdout.strip()
    if completed.returncode != 0 or not version:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        raise YtDlpResolutionError(
            "ytdlp_version_unavailable",
            f"{ytdlp} did not report a version ({detail}) — reinstall yt-dlp or "
            "set YT_DLP to a working binary",
        )
    return version


def failure_reason(log_path: Path) -> str:
    """Name why a download produced nothing, preferring yt-dlp's own ERROR line."""
    try:
        lines = log_path.read_text(errors="replace").splitlines()
    except OSError:
        return "no output file and no readable yt-dlp log"
    for line in lines:
        if line.startswith("ERROR"):
            return line.strip()
    for line in reversed(lines):
        if line.strip():
            return line.strip()
    return "no output file and no yt-dlp diagnostic"


def download_one(ytdlp: Path, vault_root: Path, youtube_id: str) -> dict[str, object]:
    """Download one video, returning its outcome rather than raising."""
    target_dir = vault_root / "slides-rebuild" / youtube_id
    target = target_dir / f"{youtube_id}.mp4"
    log_path = target_dir / f"{youtube_id}.yt-dlp.log"

    if target.is_file() and target.stat().st_size > 0:
        return {
            "youtube_id": youtube_id,
            "outcome": "skip",
            "path": str(target),
            "bytes": target.stat().st_size,
        }

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "youtube_id": youtube_id,
            "outcome": "fail",
            "exit_code": None,
            "reason": f"cannot create {target_dir}: {exc}",
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
        str(target),
        f"https://www.youtube.com/watch?v={youtube_id}",
    ]
    try:
        with log_path.open("w") as log_file:
            exit_code = subprocess.call(
                command, stdout=log_file, stderr=subprocess.STDOUT
            )
    except OSError as exc:
        return {
            "youtube_id": youtube_id,
            "outcome": "fail",
            "exit_code": None,
            "reason": f"cannot run {ytdlp}: {exc}",
            "log": str(log_path),
        }

    # yt-dlp can exit zero having produced nothing usable after a failed merge,
    # so the file on disk is the verdict and the exit code only sharpens the
    # reason for a failure.
    if target.is_file() and target.stat().st_size > 0:
        return {
            "youtube_id": youtube_id,
            "outcome": "ok",
            "path": str(target),
            "bytes": target.stat().st_size,
        }
    return {
        "youtube_id": youtube_id,
        "outcome": "fail",
        "exit_code": exit_code,
        "reason": failure_reason(log_path),
        "log": str(log_path),
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
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": counts["fail"] == 0,
        "yt_dlp": {"path": str(ytdlp), "version": version},
        "vault_root": str(vault_root),
        "counts": counts,
        "results": results,
    }


def report_failure(code: str, message: str) -> int:
    """Emit one typed failure on stdout and its actionable line on stderr."""
    json.dump(
        {
            "schema_version": REPORT_SCHEMA_VERSION,
            "ok": False,
            "code": code,
            "error": message,
        },
        sys.stdout,
        indent=2,
        sort_keys=True,
    )
    sys.stdout.write("\n")
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

    try:
        report = execute(vault_root, youtube_ids)
    except YtDlpResolutionError as exc:
        return report_failure(exc.code, str(exc))
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
