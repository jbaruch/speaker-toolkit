#!/usr/bin/env python3
"""Clean WebVTT into plain text plus a hash-bound timed-segment sidecar.

The ``.txt`` output stays timestamp-free for readers and models. Cue timings are
preserved beside it as ``.segments.json`` via :mod:`transcript_timing`, so a
later pattern observation can cite the opening (or any other timed position)
without trusting a model-supplied timestamp.

Usage:
    vtt-cleanup.py <input.vtt> [<output.txt>]

    If output is omitted, writes to the same path with .txt extension.

Examples:
    vtt-cleanup.py transcripts/aBcDeFg.en.vtt
    vtt-cleanup.py transcripts/aBcDeFg.ru.vtt transcripts/aBcDeFg.txt
"""

import json
import re
import sys
from pathlib import Path

from transcript_timing import write_transcript_bundle

_TIMING_LINE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+"
    r"(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})"
)


def _seconds(timestamp):
    hours, minutes, remainder = timestamp.split(":")
    seconds, milliseconds = remainder.split(".")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(milliseconds) / 1000
    )


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

        if re.fullmatch(r"\d+", line):
            # Numeric cue identifiers are unambiguous even in lax VTT files that
            # omit the blank line between cues.
            if cue_start is not None and _TIMING_LINE.match(next_nonblank_lines[index]):
                flush_cue()
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
            # Preserve the cleaner's historical behavior for subtitle-like text
            # without cue timing, but naturally omit it from the timed sidecar.
            cleaned.append(line)
            previous_line = line

    flush_cue()
    return "\n".join(cleaned), segments


def clean_vtt(vtt_text):
    """Clean VTT content into plain text."""
    return parse_vtt(vtt_text)[0]


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <input.vtt> [<output.txt>]", file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
    else:
        derived = re.sub(r"\.[^.]+\.vtt$", ".txt", str(input_path))
        output_path = Path(derived)
        if output_path == input_path:
            output_path = input_path.with_suffix(".txt")

    try:
        vtt_text = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read WebVTT input {input_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    cleaned, segments = parse_vtt(vtt_text)

    try:
        timed_path = write_transcript_bundle(
            output_path, cleaned, segments, source="vtt")
    except OSError as exc:
        print(f"ERROR: cannot write transcript bundle at {output_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        json.dumps(
            {
                "ok": True,
                "input_path": str(input_path),
                "path": str(output_path),
                "timed_path": str(timed_path) if timed_path else None,
                "input_lines": len(vtt_text.splitlines()),
                "output_lines": len(cleaned.splitlines()),
                "segments": len(segments),
            }
        )
    )


if __name__ == "__main__":
    main()
