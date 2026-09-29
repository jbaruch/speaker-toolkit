#!/usr/bin/env python3
"""Compose a screencast thumbnail and emit a JSON receipt.

Runs the illustrations skill's generate-thumbnail.py with the same interpreter,
routes its human progress output to stderr, and confirms the image it wrote.

Usage:
    compose-thumbnail.py --slide-image <png> --speaker-photo <path> --title "<TITLE>"
        --aesthetic <photo|comic_book> --vault <vault_root> --output thumbnail.png

Stdout: {"thumbnail": path, "width": int, "height": int, "bytes": int}.
Exit 0 on success, 1 when the generator fails or writes no PNG, 2 on usage
error.
"""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

GENERATOR = (
    Path(__file__).resolve().parents[2]
    / "illustrations"
    / "scripts"
    / "generate-thumbnail.py"
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a PNG")
    width, height = struct.unpack(">II", head[16:24])
    return width, height


def compose(generator: Path, forwarded: list[str], output: Path) -> dict:
    try:
        result = subprocess.run(
            [sys.executable, str(generator), *forwarded, "--output", str(output)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        raise ValueError(f"cannot run {generator}: {e}") from e
    sys.stderr.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise ValueError(
            f"generate-thumbnail.py exited {result.returncode}; see the messages above"
        )
    if not output.is_file():
        raise ValueError(
            f"generate-thumbnail.py reported success but wrote no {output}"
        )
    width, height = png_size(output)
    return {
        "thumbnail": str(output),
        "width": width,
        "height": height,
        "bytes": output.stat().st_size,
    }


def main(argv: list[str] | None = None, generator: Path = GENERATOR) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--slide-image", required=True)
    parser.add_argument("--speaker-photo", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--aesthetic", choices=["photo", "comic_book"], required=True)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    forwarded = [
        "--slide-image",
        args.slide_image,
        "--speaker-photo",
        args.speaker_photo,
        "--title",
        args.title,
        "--aesthetic",
        args.aesthetic,
        "--vault",
        args.vault,
    ]
    try:
        receipt = compose(generator, forwarded, args.output)
    except (ValueError, OSError) as e:
        print(f"compose-thumbnail: {e}", file=sys.stderr)
        return 1
    print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
