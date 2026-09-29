#!/usr/bin/env python3
"""Compose a screencast thumbnail and emit a JSON receipt.

Runs the illustrations skill's generate-thumbnail.py with the same interpreter,
routes its human progress output to stderr, and confirms the image it wrote.

Usage:
    compose-thumbnail.py --slide-image <png> --speaker-photo <path> --title "<TITLE>"
        --aesthetic <photo|comic_book> --vault <vault_root> --output thumbnail.png

Stdout: {"thumbnail": path, "format": "png" | "jpg", "width", "height", "bytes"}.
Over YouTube's 2 MB limit the generator writes a JPEG; the file is renamed to
match. The title may have at most five words. Exit 0 on success, 1 when the
generator fails or writes no image, 2 on usage error.
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
MAX_TITLE_WORDS = 5  # thumbnail-generation-rules: a hook, not the full title
JPEG_FRAME_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


def image_info(path: Path) -> tuple[str, int, int]:
    """(format, width, height) of a PNG or JPEG, read from its header."""
    data = path.read_bytes()
    if data[:8] == PNG_SIGNATURE and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        return "png", width, height
    if data[:2] == b"\xff\xd8":
        offset = 2
        while offset + 9 <= len(data) and data[offset] == 0xFF:
            marker = data[offset + 1]
            length = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
            if marker in JPEG_FRAME_MARKERS:
                height, width = struct.unpack(">HH", data[offset + 5 : offset + 9])
                return "jpg", width, height
            offset += 2 + length
    raise ValueError(f"{path} is neither a PNG nor a JPEG")


def title_words(value: str) -> str:
    if not value.split() or len(value.split()) > MAX_TITLE_WORDS:
        raise argparse.ArgumentTypeError(
            f"--title must be 1 to {MAX_TITLE_WORDS} words"
        )
    return value


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
    kind, width, height = image_info(output)
    # Over 2 MB the generator falls back to JPEG; keep the name true to the bytes.
    if output.suffix.lower().lstrip(".").replace("jpeg", "jpg") != kind:
        renamed = output.with_suffix(f".{kind}")
        output.replace(renamed)
        output = renamed
    return {
        "thumbnail": str(output),
        "format": kind,
        "width": width,
        "height": height,
        "bytes": output.stat().st_size,
    }


def main(argv: list[str] | None = None, generator: Path = GENERATOR) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--slide-image", required=True)
    parser.add_argument("--speaker-photo", required=True)
    parser.add_argument("--title", type=title_words, required=True)
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
