#!/usr/bin/env python3
"""Extract exact frames from a recording's screen or camera stream.

Decodes from the start and picks frames by number, because the TSCC2 screen
codec does not seek accurately. Used for thumbnail candidates: screen frames as
the background, camera frames as the speaker photo.

Usage:
    extract-frames.py <recording.trec> --stream 0:1 --at 198.6 --at 210 --out <dir> [--prefix camera]

Writes <dir>/<prefix>-<seconds>.png per --at. Stdout: {"frames": [paths]}.
Exit 0 on success, 1 when ffmpeg fails or the output cannot be written, 2 on
usage error.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

SAMPLE_FPS = 10


def seconds(value: str) -> float:
    t = float(value)
    if not math.isfinite(t) or t < 0:
        raise argparse.ArgumentTypeError(
            "--at must be a non-negative number of seconds"
        )
    return t


def extract(
    recording: Path, stream: str, times: list[float], out: Path, prefix: str
) -> list[Path]:
    """Render into a staging directory, then move the finished frames into `out`."""
    staging = out.with_name(f".{out.name}.frames-staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    wanted = sorted({round(t * SAMPLE_FPS) for t in times})
    select = "+".join(f"eq(n,{n})" for n in wanted)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(recording),
        "-map",
        stream,
        "-vf",
        f"fps={SAMPLE_FPS},select='{select}'",
        "-fps_mode",
        "passthrough",
        str(staging / "f-%03d.png"),
    ]
    try:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
        except OSError as e:
            raise ValueError(
                f"cannot run ffmpeg ({e}); install it, e.g. `brew install ffmpeg`"
            ) from e
        if result.returncode != 0:
            raise ValueError(f"ffmpeg failed: {result.stderr.strip()[-400:]}")
        produced = sorted(staging.glob("f-*.png"))
        if len(produced) != len(wanted):
            raise ValueError(
                f"asked for {len(wanted)} frames, got {len(produced)}; is every --at inside the recording?"
            )
        out.mkdir(parents=True, exist_ok=True)
        frames = []
        for n, frame in zip(wanted, produced):
            target = out / f"{prefix}-{n / SAMPLE_FPS:.1f}.png"
            frame.replace(target)
            frames.append(target)
    finally:
        shutil.rmtree(staging)
    return frames


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("recording", type=Path)
    parser.add_argument(
        "--stream",
        required=True,
        help="ffmpeg stream specifier: 0:0 screen, 0:1 camera",
    )
    parser.add_argument(
        "--at",
        type=seconds,
        action="append",
        required=True,
        help="source seconds; repeatable",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--prefix", default="frame")
    args = parser.parse_args(argv)
    try:
        frames = extract(args.recording, args.stream, args.at, args.out, args.prefix)
    except ValueError as e:
        print(f"extract-frames: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(
            f"extract-frames: cannot write under {args.out}: {e}; choose a writable --out",
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"frames": [str(f) for f in frames]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
