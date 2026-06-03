#!/usr/bin/env python3
"""Convert a backgrounds manifest JSON into the ApplyBackgrounds spec string.

The manifest is produced by `apply-illustrations-to-deck.py --backgrounds-out`:

    {"backgrounds": {"<1-based slide #>": "/abs/image", ...}}

The spec string consumed by the ApplyBackgrounds VBA macro is
`<#>=<path>;<#>=<path>...`, sorted by slide number. Paths may not contain the
`;` or `=` delimiters. This deterministic conversion is split out of
`apply-backgrounds.sh` so it can be unit-tested (the VBA side cannot run in CI).

Usage:
    backgrounds-manifest-to-spec.py <manifest.json>   # prints the spec to stdout
"""
import json
import sys
from pathlib import Path


def manifest_to_spec(manifest: object) -> str:
    """Return the `#=path;#=path` spec for ApplyBackgrounds, sorted by slide #.

    Raises ValueError (with an actionable message) on any malformed input: a
    non-object manifest, a non-object `backgrounds`, an empty manifest, a
    non-integer slide key, a non-string path, or a path containing a `;`/`=`
    delimiter (which would corrupt the spec the macro parses).
    """
    if not isinstance(manifest, dict):
        raise ValueError(
            "manifest must be a JSON object like "
            '{"backgrounds": {"<slide #>": "/abs/image", ...}}'
        )
    backgrounds = manifest.get("backgrounds", {})
    if not isinstance(backgrounds, dict):
        raise ValueError("manifest 'backgrounds' must be an object mapping slide # -> image path")
    if not backgrounds:
        raise ValueError(
            "manifest has no 'backgrounds' entries — nothing to apply; skip the "
            "ApplyBackgrounds pass when there are no FULL (Safe zone) slides"
        )

    def slide_num(key: object) -> int:
        try:
            return int(key)
        except (TypeError, ValueError):
            raise ValueError(f"slide key {key!r} is not an integer") from None

    tokens = []
    for key in sorted(backgrounds, key=slide_num):
        path = backgrounds[key]
        if not isinstance(path, str):
            raise ValueError(f"image path for slide {key} must be a string, got {type(path).__name__}")
        if ";" in path or "=" in path:
            raise ValueError(
                f"image path for slide {key} contains a reserved spec delimiter "
                f"(';' or '='): {path!r} — rename the file so its path has neither"
            )
        tokens.append(f"{slide_num(key)}={path}")
    return ";".join(tokens)


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: backgrounds-manifest-to-spec.py <manifest.json>", file=sys.stderr)
        sys.exit(2)
    path = Path(sys.argv[1])
    try:
        raw = path.read_text()
    except OSError as exc:
        print(f"ERROR: cannot read manifest {path}: {exc.strerror or exc} — "
              f"generate it with apply-illustrations-to-deck.py --backgrounds-out", file=sys.stderr)
        sys.exit(1)
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: manifest {path} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        print(manifest_to_spec(manifest))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
