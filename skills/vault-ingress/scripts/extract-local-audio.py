#!/usr/bin/env python3
"""Extract one recording's first audio stream for a local audio declaration (#485).

A recording over the bounded media owner's input ceiling
(``local_media_contract.MEDIA_MAX_INPUT_BYTES``) cannot be acquired whole, but
its audio stream usually can. This script writes that stream to an audio file
the owner admits, so ``fetch-transcript.py --audio`` can transcribe it and the
``declare_local_audio`` mutation can declare it.

Usage:
    extract-local-audio.py --recording <video file> --output <audio file>

The output suffix picks the mode: ``.m4a`` and ``.mp3`` copy the stream without
re-encoding (the stream must already be AAC/ALAC or MP3); ``.wav`` decodes it to
16-bit PCM. The suffix must be one of
``tracking_database.AUDIO_DECLARATION_SUFFIXES``.

Bounds and contract, all named constants below:

- ``ffmpeg`` runs under a wall-clock limit (``EXTRACT_TIMEOUT_SECONDS``) and
  stops writing at the owner's input ceiling; an output at or over it is
  refused, since the owner could not admit it either.
- The recording's size, mtime, inode and device are compared before and after
  the run; a recording that changed mid-extraction is refused.
- ffmpeg writes a private staged file beside the output, the bounded media
  owner probes it (``probe_local_media``), and only a probed file is installed,
  never over an existing one. An existing output with the same bytes is an
  unchanged success; different bytes are refused, so a file a receipt may
  already bind is never replaced.
- Every refusal removes the staged file; a staged file that cannot be removed
  is named on stderr and in the error.

Stdout: one JSON object. Success is ``{"ok": true, "output", "written",
"media_sha256", "size_bytes", "duration_seconds", "mode"}``. A refusal is
``{"ok": false, "reason_code", "error"}`` with the same message on stderr, exit
2. Reason codes: ``invalid_arguments``, ``recording_unreadable``,
``ffmpeg_unavailable``, ``extraction_failed``, ``extraction_timeout``,
``output_over_ceiling``, ``recording_changed``, ``output_unusable``,
``output_exists``, ``output_write_failed``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys

from local_media_contract import MEDIA_MAX_INPUT_BYTES, LocalMediaError
from local_media_evidence import probe_local_media
from tracking_database import AUDIO_DECLARATION_SUFFIXES

EXTRACT_TIMEOUT_SECONDS = 2 * 60 * 60
# How much of ffmpeg's stderr a refusal quotes; it runs at `-loglevel error`.
DIAGNOSTIC_TAIL_BYTES = 2000
DIGEST_CHUNK_BYTES = 1024 * 1024
# Output suffix -> (ffmpeg muxer, audio codec arguments, reported mode).
MODES = {
    ".m4a": ("ipod", ["-c:a", "copy"], "copy"),
    ".mp3": ("mp3", ["-c:a", "copy"], "copy"),
    ".wav": ("wav", ["-c:a", "pcm_s16le"], "pcm_s16le"),
}


class ExtractionError(RuntimeError):
    """A refusal with a stable reason code and an actionable message."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class RecordingGeneration:
    size: int
    mtime_ns: int
    inode: int
    device: int


def _recording_generation(recording: Path) -> RecordingGeneration:
    try:
        value = os.stat(recording)
    except OSError as exc:
        raise ExtractionError(
            "recording_unreadable",
            f"cannot stat the recording {recording}: {exc} — pass an existing "
            "local video file",
        ) from exc
    if not stat.S_ISREG(value.st_mode):
        raise ExtractionError(
            "recording_unreadable",
            f"the recording {recording} is not a regular file — pass the video "
            "file itself",
        )
    return RecordingGeneration(
        value.st_size, value.st_mtime_ns, value.st_ino, value.st_dev
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(DIGEST_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _run_ffmpeg(
    command: list[str], timeout_seconds: float
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError(
            "extraction_timeout",
            f"ffmpeg did not finish within {timeout_seconds} seconds; copy the "
            "recording to a local disk and re-run",
        ) from exc
    except OSError as exc:
        raise ExtractionError(
            "ffmpeg_unavailable",
            f"cannot run ffmpeg ({exc}); install ffmpeg and re-run",
        ) from exc


def _remove_staged(staged: Path) -> str | None:
    try:
        staged.unlink(missing_ok=True)
    except OSError as exc:
        print(
            f"WARNING: staged audio {staged} was not removed: {exc}", file=sys.stderr
        )
        return f"; the staged file {staged} was not removed ({exc})"
    return None


def _install(staged: Path, output: Path, digest: str) -> bool:
    """Install ``staged`` at ``output``; whether a new file was written."""
    if output.is_symlink() or (output.exists() and not output.is_file()):
        raise ExtractionError(
            "output_exists",
            f"{output} exists and is not a regular file — choose another output",
        )
    if output.exists():
        if _sha256(output) == digest:
            return False
        raise ExtractionError(
            "output_exists",
            f"{output} already holds different audio; a transcript receipt may "
            "bind it, so it is never replaced — choose another output name",
        )
    try:
        # A hard link installs without replacing anything a racing writer put
        # there; volumes without links take the checked rename instead.
        os.link(staged, output)
    except FileExistsError as exc:
        raise ExtractionError(
            "output_exists",
            f"{output} appeared during extraction — re-run to compare it",
        ) from exc
    except OSError:
        if output.exists():
            raise ExtractionError(
                "output_exists",
                f"{output} appeared during extraction — re-run to compare it",
            ) from None
        try:
            os.rename(staged, output)
        except OSError as exc:
            raise ExtractionError(
                "output_write_failed",
                f"cannot install {output}: {exc} — make its directory writable "
                "and re-run",
            ) from exc
    try:
        directory = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as exc:
        raise ExtractionError(
            "output_write_failed",
            f"{output} was installed but its directory did not sync: {exc} — "
            "re-run once the volume is healthy",
        ) from exc
    return True


def extract(
    recording: Path,
    output: Path,
    *,
    max_output_bytes: int = MEDIA_MAX_INPUT_BYTES,
    timeout_seconds: float = EXTRACT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    suffix = output.suffix.lower()
    if suffix not in AUDIO_DECLARATION_SUFFIXES or suffix not in MODES:
        raise ExtractionError(
            "invalid_arguments",
            f"--output must end in one of {sorted(AUDIO_DECLARATION_SUFFIXES)}, "
            f"not {output.name!r}",
        )
    if not output.parent.is_dir():
        raise ExtractionError(
            "invalid_arguments",
            f"the output directory {output.parent} does not exist — create it first",
        )
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise ExtractionError(
            "ffmpeg_unavailable", "ffmpeg is not on PATH; install it and re-run"
        )
    before = _recording_generation(recording)
    muxer, codec, mode = MODES[suffix]
    staged = output.parent / f".{output.stem}.{secrets.token_hex(8)}.partial{suffix}"
    command = [
        executable,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(recording),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        *codec,
        "-fs",
        str(max_output_bytes),
        "-f",
        muxer,
        str(staged),
    ]
    try:
        completed = _run_ffmpeg(command, timeout_seconds)
        if completed.returncode != 0:
            tail = completed.stderr[-DIAGNOSTIC_TAIL_BYTES:].decode(
                "utf-8", errors="replace"
            )
            raise ExtractionError(
                "extraction_failed",
                f"ffmpeg exited {completed.returncode}: {tail.strip()} — the "
                "recording may have no audio stream, or its codec does not fit "
                f"{suffix}; try a .wav output",
            )
        size = staged.stat().st_size
        if size >= max_output_bytes:
            raise ExtractionError(
                "output_over_ceiling",
                f"the extracted audio reached {max_output_bytes} bytes, the "
                "bounded media owner's input ceiling; a .m4a or .mp3 copy of a "
                "compressed stream is the smallest lossless output",
            )
        if _recording_generation(recording) != before:
            raise ExtractionError(
                "recording_changed",
                f"{recording} changed during extraction — let any sync or copy "
                "finish and re-run",
            )
        try:
            probe = probe_local_media(staged, trusted_root=output.parent)
        except LocalMediaError as exc:
            raise ExtractionError(
                "output_unusable",
                f"the bounded media owner refused the extracted audio "
                f"({exc.reason_code}); try a .wav output",
            ) from exc
        written = _install(staged, output, probe.source_sha256)
        return {
            "ok": True,
            "output": str(output),
            "written": written,
            "media_sha256": probe.source_sha256,
            "size_bytes": probe.source_size_bytes,
            "duration_seconds": probe.duration_seconds,
            "mode": mode,
        }
    except ExtractionError as exc:
        leftover = _remove_staged(staged)
        if leftover is not None:
            raise ExtractionError(exc.reason_code, f"{exc}{leftover}") from exc
        raise
    finally:
        if staged.exists():
            _remove_staged(staged)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--recording", required=True, help="the local video file")
    parser.add_argument("--output", required=True, help="the audio file to write")
    args = parser.parse_args(argv)
    try:
        result = extract(
            Path(args.recording).expanduser(), Path(args.output).expanduser()
        )
    except ExtractionError as exc:
        print(
            json.dumps(
                {"ok": False, "reason_code": exc.reason_code, "error": str(exc)}
            )
        )
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
