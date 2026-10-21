#!/usr/bin/env python3
"""Place a decoded PNG/JPEG thumbnail as a verified PNG for shownotes.

Usage: place-thumbnail.py --source IMAGE --destination CONVENTION_PATH.png
Requires Pillow in the configured toolkit runtime. Input dimensions are
preserved, including legacy thumbnails. PNG bytes are preserved; JPEG pixels
are encoded as PNG without resizing. This website derivative has no YouTube
file-size limit. The source is unchanged, and the destination is replaced
atomically only after validation.
An already-valid PNG at the destination is a no-op when also selected as source.

Stdout: one JSON object with ok, path, mime_type and dimensions on success;
ok and error on failure. Exit 0 success; 1 dependency, image or filesystem
failure; 2 invalid CLI arguments (stderr only). Diagnostics go to stderr.
Expected failures name the operation and how to repair its source or destination.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile


class ThumbnailPlacementError(ValueError):
    """An expected failure with an operation-specific recovery instruction."""


def place_thumbnail(source: Path, destination: Path) -> dict[str, object]:
    from PIL import Image

    if destination.suffix.lower() != ".png":
        raise ThumbnailPlacementError(
            "Set --destination to the site's convention path ending in .png."
        )
    try:
        original = source.read_bytes()
    except OSError as exc:
        raise ThumbnailPlacementError(
            f"Cannot read thumbnail source {source}: {exc}. "
            "Restore the file or select a readable source with --source, then rerun."
        ) from exc
    try:
        with Image.open(BytesIO(original)) as image:
            if image.format not in {"PNG", "JPEG"}:
                raise ValueError("source must contain PNG or JPEG bytes")
            dimensions = image.size
            image.load()
            source_is_png = image.format == "PNG"
            if source_is_png:
                output = original
            else:
                buffer = BytesIO()
                image.convert("RGB").save(buffer, format="PNG", optimize=True)
                output = buffer.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ThumbnailPlacementError(
            f"Cannot decode thumbnail source {source}: {exc}. "
            "Select a valid PNG/JPEG or regenerate it with illustrations, then rerun."
        ) from exc

    try:
        try:
            destination_path = str(destination.resolve())
            same_path = str(source.resolve()) == destination_path
        except (OSError, RuntimeError) as exc:
            # Python 3.10–3.12 raises RuntimeError for symlink loops even
            # in non-strict mode. Keep this catch at resolution only.
            raise ThumbnailPlacementError(
                f"Cannot resolve thumbnail source {source} or destination {destination}: {exc}. "
                "Remove symlink loops or choose accessible paths, repair path permissions, "
                "then rerun placement."
            ) from exc
        if same_path and not source_is_png:
            raise ThumbnailPlacementError(
                "JPEG source and PNG destination must be distinct paths. "
                "Keep the JPEG at a separate source path and rerun placement."
            )
        if not same_path:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=f".{destination.name}.", dir=destination.parent
            ) as temporary:
                staged = Path(temporary) / "thumbnail.png"
                staged.write_bytes(output)
                with Image.open(staged) as placed:
                    if placed.format != "PNG" or placed.size != dimensions:
                        raise ValueError("placed thumbnail did not validate as PNG")
                    placed.load()
                os.replace(staged, destination)
    except ThumbnailPlacementError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ThumbnailPlacementError(
            f"Cannot place thumbnail at destination {destination}: {exc}. "
            "Check the destination directory, write permissions and free space, "
            "then rerun with a valid source image."
        ) from exc

    return {
        "ok": True,
        "path": destination_path,
        "mime_type": "image/png",
        "dimensions": list(dimensions),
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
    except ThumbnailPlacementError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        print(f"Thumbnail placement failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
