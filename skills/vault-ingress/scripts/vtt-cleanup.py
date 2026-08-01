#!/usr/bin/env python3
"""Clean WebVTT into plain text plus a hash-bound timed-segment sidecar.

The ``.txt`` output stays timestamp-free for readers and models. Cue timings are
preserved beside it as ``.segments.json`` via :mod:`transcript_timing`, so a
later pattern observation can cite the opening (or any other timed position)
without trusting a model-supplied timestamp.

Usage:
    vtt-cleanup.py <input.vtt> <output.txt> [--force]

Examples:
    vtt-cleanup.py transcripts/aBcDeFg.ru.vtt transcripts/aBcDeFg.txt

Output is mandatory so language-qualified inputs cannot silently collide at a
derived ``<stem>.txt`` path. Existing transcript bytes are preserved unless
``--force`` explicitly authorizes replacement.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import NoReturn

from transcript_quality import build_quality_policy, count_words, validate_transcript
from transcript_timing import (
    ensure_bundle_destinations_are_not_symlinks,
    quality_sidecar_path,
    validate_vtt_artifact_path,
    vtt_timing_provenance,
    write_transcript_bundle,
)

_TIMING_LINE = re.compile(
    r"(?P<start>(?:\d{2,}:)?\d{2}:\d{2}\.\d{3})\s+-->\s+"
    r"(?P<end>(?:\d{2,}:)?\d{2}:\d{2}\.\d{3})"
)


def _seconds(timestamp):
    parts = timestamp.split(":")
    if len(parts) == 2:
        hours = 0
        minutes, remainder = parts
    else:
        hours_text, minutes, remainder = parts
        hours = int(hours_text)
    seconds, milliseconds = remainder.split(".")
    return hours * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000


def parse_vtt(vtt_text):
    """Return ``(plain text, timed segments)`` from a WebVTT payload."""
    cleaned = []
    segments = []
    previous_line = None
    cue_start = cue_end = None
    cue_lines = []
    skip_block = False

    def flush_cue():
        nonlocal previous_line, cue_start, cue_end, cue_lines
        new_lines = []
        for line in cue_lines:
            if line != previous_line:
                cleaned.append(line)
                new_lines.append(line)
                previous_line = line
        text = " ".join(new_lines).strip()
        if text and cue_start is not None and cue_end is not None:
            segments.append(
                {"text": text, "start_seconds": cue_start, "end_seconds": cue_end}
            )
        cue_start = cue_end = None
        cue_lines = []

    lines = vtt_text.splitlines()
    next_nonblank_lines = [""] * len(lines)
    next_nonblank = ""
    for index in range(len(lines) - 1, -1, -1):
        next_nonblank_lines[index] = next_nonblank
        if lines[index].strip():
            next_nonblank = lines[index].strip()
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()

        if not line:
            flush_cue()
            skip_block = False
            continue

        if skip_block:
            continue
        if cue_start is None and line.startswith(("NOTE", "STYLE", "REGION")):
            flush_cue()
            skip_block = True
            continue

        if cue_start is None and line.startswith(("WEBVTT", "Kind:", "Language:")):
            continue

        timing = _TIMING_LINE.match(line)
        if timing:
            flush_cue()
            cue_start = _seconds(timing.group("start"))
            cue_end = _seconds(timing.group("end"))
            continue

        if (
            cue_start is None
            and re.fullmatch(r"\d+", line)
            and _TIMING_LINE.match(next_nonblank_lines[index])
        ):
            # Numeric identifiers occur in the between-cue identifier state.
            # Inside an active cue, the same text is transcript content even
            # when a lax file omits a separator before the next timing line.
            continue
        if cue_start is None and _TIMING_LINE.match(next_nonblank_lines[index]):
            # Named cue identifiers sit immediately before timing in a fresh cue.
            continue
        if re.match(r"(?:align|position|size|line|vertical):", line):
            continue

        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line:
            continue
        if cue_start is not None:
            cue_lines.append(line)
        elif line != previous_line:
            # Parser callers preserve subtitle-like untimed text. The CLI still
            # rejects such input until a cue-bearing VTT artifact is supplied.
            cleaned.append(line)
            previous_line = line

    flush_cue()
    return "\n".join(cleaned), segments


def clean_vtt(vtt_text):
    """Clean VTT content into plain text."""
    return parse_vtt(vtt_text)[0]


def read_verified_vtt_bytes(
    input_path: Path,
    output_path: Path,
) -> tuple[Path, bytes, tuple[int, int, int, int, int]]:
    """Read a prevalidated regular VTT without following a final symlink.

    A nonblocking descriptor prevents a FIFO replacement race from hanging the
    process. Matching pre/open/post identities ensure the bytes came from the
    regular file that passed lexical, resolved, and component validation.
    """
    safe_path, _relative = validate_vtt_artifact_path(output_path, input_path)
    before = safe_path.lstat()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(safe_path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("VTT input changed to a non-regular file before open")
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        opened_identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        )
        if opened_identity != before_identity:
            raise OSError("VTT input changed between validation and open")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(descriptor)
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if after_identity != opened_identity:
            raise OSError("VTT input changed while it was being read")
        return safe_path, b"".join(chunks), opened_identity
    finally:
        os.close(descriptor)


def emit(ok, input_path, output_path, reason, code, **details) -> NoReturn:
    """Emit one stable CLI result object and exit."""
    print(
        json.dumps(
            {
                "ok": ok,
                "input_path": str(input_path),
                "path": str(output_path),
                "reason": reason,
                **details,
            }
        )
    )
    raise SystemExit(code)


def main(argv: list[str] | None = None) -> NoReturn:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("input", help="source WebVTT artifact")
    parser.add_argument("output", help="explicit transcript .txt path")
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing transcript only after explicit authorization",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code:
            emit(False, "", "", "invalid arguments — see stderr", 2)
        raise

    input_path = Path(args.input)
    output_path = Path(args.output)
    if input_path.suffix.casefold() != ".vtt":
        emit(False, input_path, output_path, "input path must end in .vtt", 2)
    if output_path.suffix.casefold() != ".txt":
        emit(False, input_path, output_path, "output path must end in .txt", 2)
    try:
        ensure_bundle_destinations_are_not_symlinks(output_path)
    except ValueError as exc:
        emit(
            False,
            input_path,
            output_path,
            f"unsafe transcript bundle destination: {exc}; replace each link "
            "with a regular artifact path before retrying",
            2,
        )
    if output_path.exists() and not args.force:
        emit(
            False,
            input_path,
            output_path,
            "output transcript already exists; inspect it and pass --force to "
            "authorize replacement",
            2,
        )

    try:
        _safe_input_path, input_bytes, input_identity = read_verified_vtt_bytes(
            input_path,
            output_path,
        )
        vtt_text = input_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        emit(
            False,
            input_path,
            output_path,
            f"WebVTT input is not UTF-8: {exc}; export it as UTF-8 and retry",
            2,
        )
    except ValueError as exc:
        emit(
            False,
            input_path,
            output_path,
            f"unsafe WebVTT input: {exc}; copy a regular VTT into the transcript "
            "directory and retry",
            2,
        )
    except OSError as exc:
        emit(
            False,
            input_path,
            output_path,
            f"cannot read WebVTT input: {exc}; repair file access or stability "
            "and retry",
            2,
        )

    cleaned, segments = parse_vtt(vtt_text)
    quality_policy = build_quality_policy()
    valid, reason = validate_transcript(cleaned)
    if not valid:
        emit(
            False,
            input_path,
            output_path,
            reason,
            1,
            words=count_words(cleaned),
        )
    if not segments:
        emit(
            False,
            input_path,
            output_path,
            "WebVTT contains no usable timed cues; repair/export the subtitle "
            "track with timestamped cues or supply another cue-bearing VTT",
            1,
            words=count_words(cleaned),
        )
    cue_extent = max(float(segment["end_seconds"]) for segment in segments)

    try:
        current_path, current_bytes, current_identity = read_verified_vtt_bytes(
            input_path,
            output_path,
        )
        if current_identity != input_identity or current_bytes != input_bytes:
            raise ValueError(
                "WebVTT input changed during cleanup; no transcript bundle was written"
            )
        timed_path = write_transcript_bundle(
            output_path,
            cleaned,
            segments,
            source="vtt",
            timing_provenance=vtt_timing_provenance(
                output_path,
                current_path,
                hashlib.sha256(input_bytes).hexdigest(),
                cue_extent,
            ),
            quality_policy=quality_policy,
            quality_policy_provenance={"kind": "fixed_default"},
            force=args.force,
        )
    except (OSError, ValueError) as exc:
        emit(
            False,
            input_path,
            output_path,
            f"cannot write transcript bundle: {exc}; repair the named source or "
            "destination artifact and retry",
            2,
        )

    emit(
        True,
        input_path,
        output_path,
        reason,
        0,
        timed_path=str(timed_path) if timed_path else None,
        quality_path=str(quality_sidecar_path(output_path)),
        words=count_words(cleaned),
        input_lines=len(vtt_text.splitlines()),
        output_lines=len(cleaned.splitlines()),
        segments=len(segments),
    )


if __name__ == "__main__":
    try:
        main()
    # outer-boundary-process-contract: callers treat missing JSON as a silent
    # failure; emit one failure object because propagation breaks orchestration.
    except Exception as exc:  # noqa: BLE001
        print(
            f"unexpected VTT cleanup failure: {type(exc).__name__}: {exc}; "
            "inspect this diagnostic, repair the VTT or destination, and retry",
            file=sys.stderr,
        )
        emit(
            False,
            "",
            "",
            f"unexpected VTT cleanup failure: {exc}; inspect stderr, repair the "
            "VTT or destination, and retry",
            2,
        )
