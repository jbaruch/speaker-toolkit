#!/usr/bin/env python3
"""Place a decoded PNG/JPEG thumbnail as a verified PNG for shownotes.

Usage: place-thumbnail.py --source IMAGE --destination CONVENTION_PATH.png
Requires Pillow in the configured toolkit runtime. The input must decode at
1280x720. PNG bytes are preserved; JPEG pixels are encoded as PNG without
resizing. This website derivative has no YouTube file-size limit. The source
is unchanged, and the destination is replaced atomically only after validation.
An already-valid PNG at the destination is a no-op when also selected as source.

Stdout: one JSON object with ok, path, mime_type and dimensions on success;
ok and error on failure. Exit 0 success; 1 dependency, image or filesystem
failure; 2 invalid CLI arguments (stderr only). Diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile


DIMENSIONS = (1280, 720)


def place_thumbnail(source: Path, destination: Path) -> dict[str, object]:
    from PIL import Image

    if destination.suffix.lower() != ".png":
        raise ValueError("shownotes destination must have a .png extension")
    original = source.read_bytes()
    try:
        image = Image.open(BytesIO(original))
    except Image.DecompressionBombError as exc:
        raise ValueError("thumbnail source exceeds safe decoding limits") from exc
    with image:
        if image.format not in {"PNG", "JPEG"}:
            raise ValueError("thumbnail source must contain PNG or JPEG bytes")
        if image.size != DIMENSIONS:
            raise ValueError("thumbnail source must be 1280x720; use illustrations")
        image.load()
        source_is_png = image.format == "PNG"
        if source_is_png:
            output = original
        else:
            buffer = BytesIO()
            image.convert("RGB").save(buffer, format="PNG", optimize=True)
            output = buffer.getvalue()

    same_path = source.resolve() == destination.resolve()
    if same_path and not source_is_png:
        raise ValueError("JPEG source and PNG destination must be distinct paths")
    if not same_path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{destination.name}.", dir=destination.parent
        ) as temporary:
            staged = Path(temporary) / "thumbnail.png"
            staged.write_bytes(output)
            with Image.open(staged) as placed:
                if placed.format != "PNG" or placed.size != DIMENSIONS:
                    raise ValueError("placed thumbnail did not validate as PNG")
                placed.load()
            os.replace(staged, destination)

    return {
        "ok": True,
        "path": str(destination.resolve()),
        "mime_type": "image/png",
        "dimensions": list(DIMENSIONS),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = place_thumbnail(args.source, args.destination)
    except ImportError:
        message = "Pillow is required; repair the configured toolkit runtime's pinned dependencies"
        print(json.dumps({"ok": False, "error": message}))
        print(message, file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        print(f"Thumbnail placement failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
