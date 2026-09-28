#!/usr/bin/env python3
"""Extract the recorded pointer path from a Camtasia .trec.

The pointer is not in the screen pixels: Camtasia records it separately, in the
TSCM atom at the end of the file. Stills can never show where the presenter was
pointing; this can.

Usage:
    trec-pointer.py <recording.trec> [--out pointer.json]

Output: {"capture": {"x","y","width","height"}, "samples": [[seconds, nx, ny], ...]}
where nx, ny are normalized to the captured display, top-left origin.
Exit 0 on success, 1 when the file carries no pointer data, 2 on usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import camtasia_model as model  # noqa: E402


def extract(recording: Path) -> dict:
    try:
        data = recording.read_bytes()
    except OSError as e:
        raise ValueError(f"cannot read {recording}: {e}") from e
    records = model.tscm_records(data)
    x, y, width, height = model.capture_rect(records)
    samples = [
        [round(t, 4), round((px - x) / width, 5), round((py - y) / height, 5)]
        for t, px, py in model.pointer_path(records)
    ]
    return {
        "capture": {"x": x, "y": y, "width": width, "height": height},
        "samples": samples,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("recording", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = extract(args.recording)
    except ValueError as e:
        print(f"trec-pointer: {e}", file=sys.stderr)
        return 1
    text = json.dumps(result)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(
            f"{len(result['samples'])} pointer samples -> {args.out}", file=sys.stderr
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
