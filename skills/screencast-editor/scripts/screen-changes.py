#!/usr/bin/env python3
"""List the moments the recorded screen changes, decoding from the start.

Camtasia's TSCC2 screen codec does not seek accurately: `ffmpeg -ss` before
`-i` lands seconds away from the requested time. This decodes the whole stream
and reports scene changes by presentation timestamp, so page switches and
scrolls can be placed exactly.

Usage:
    screen-changes.py <recording.trec> [--stream 0:0] [--threshold 0.01] [--fps 4]

Stdout: {"changes": [seconds, ...]}. Exit 0 on success, 1 when ffmpeg fails,
2 on usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PTS = re.compile(r"pts_time:([0-9.]+)")


def changes(recording: Path, stream: str, threshold: float, fps: float) -> list[float]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(recording),
        "-map",
        stream,
        "-vf",
        f"fps={fps},scale=480:-2,select='gt(scene,{threshold})',showinfo",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"ffmpeg failed: {result.stderr.strip()[-400:]}")
    return [float(m) for m in PTS.findall(result.stderr)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("recording", type=Path)
    parser.add_argument(
        "--stream", default="0:0", help="ffmpeg stream specifier of the screen track"
    )
    parser.add_argument("--threshold", type=float, default=0.01)
    parser.add_argument("--fps", type=float, default=4.0)
    args = parser.parse_args(argv)
    try:
        found = changes(args.recording, args.stream, args.threshold, args.fps)
    except ValueError as e:
        print(f"screen-changes: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"changes": found}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
