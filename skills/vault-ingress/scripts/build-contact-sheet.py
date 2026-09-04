#!/usr/bin/env python3
"""Sample VIDEO into OUTPUT_DIR without approving crops or touching the vault DB.

Usage: build-contact-sheet.py VIDEO OUTPUT_DIR [--frames N] [--timeout-seconds N]
Stdout: one JSON report (manifest path, frame count, reuse status).
Exit 0: complete validated bundle; 1: operational failure; 2: invalid usage.
Output includes individual frames and a separate classification contact sheet.
The sampling constants and failure codes live in crop_frames.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import NoReturn

from artifact_supervisor import SupervisorError
from crop_frames import CropFramesError, DEFAULT_FRAMES, LIMITS, sample_video
from video_evidence import VideoEvidenceError


USAGE = "build-contact-sheet.py VIDEO OUTPUT_DIR [--frames N] [--timeout-seconds N]"


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        print(json.dumps({"ok": False, "code": "crop_usage_invalid", "usage": USAGE}))
        print(f"invalid sampling command; usage: {USAGE}", file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments in (["--help"], ["-h"]):
        print(json.dumps({"ok": True, "usage": USAGE}))
        return 0
    parser = ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("video", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    parser.add_argument("--timeout-seconds", type=float, default=LIMITS.wall_seconds)
    args = parser.parse_args(arguments)
    try:
        report = sample_video(
            args.video,
            args.output_dir,
            count=args.frames,
            timeout_seconds=args.timeout_seconds,
        )
    except (CropFramesError, VideoEvidenceError, SupervisorError, OSError) as exc:
        code = (
            exc.code
            if isinstance(exc, CropFramesError)
            else exc.reason_code
            if isinstance(exc, (VideoEvidenceError, SupervisorError))
            else "crop_io_failure"
        )
        print(json.dumps({"ok": False, "code": code}))
        print(str(CropFramesError(code)), file=sys.stderr)
        return 1
    print(json.dumps(report))
    return 0


def run_cli() -> int:
    try:
        return main()
    # Agent callers interpret absent JSON as a lost process contract. Emit a
    # closed failure; a traceback would drop that contract and expose paths.
    # outer-boundary-process-contract
    except Exception:  # noqa: BLE001
        print(json.dumps({"ok": False, "code": "crop_unexpected_failure"}))
        print(
            "sampling failed unexpectedly; repair the runtime and retry",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())
