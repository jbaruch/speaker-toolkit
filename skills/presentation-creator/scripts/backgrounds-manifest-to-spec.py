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


def manifest_to_spec(manifest: dict) -> str:
    """Return the `#=path;#=path` spec for ApplyBackgrounds, sorted by slide #.

    Raises ValueError on an empty manifest or a path containing a `;`/`=`
    delimiter (which would corrupt the spec the macro parses).
    """
    backgrounds = manifest.get("backgrounds", {})
    if not backgrounds:
        raise ValueError(
            "manifest has no 'backgrounds' entries — nothing to apply; skip the "
            "ApplyBackgrounds pass when there are no FULL (Safe zone) slides"
        )
    tokens = []
    for key in sorted(backgrounds, key=lambda k: int(k)):
        path = backgrounds[key]
        if ";" in path or "=" in path:
            raise ValueError(
                f"image path for slide {key} contains a reserved spec delimiter "
                f"(';' or '='): {path!r} — rename the file so its path has neither"
            )
        tokens.append(f"{int(key)}={path}")
    return ";".join(tokens)


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: backgrounds-manifest-to-spec.py <manifest.json>", file=sys.stderr)
        sys.exit(2)
    try:
        manifest = json.loads(Path(sys.argv[1]).read_text())
        print(manifest_to_spec(manifest))
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
