#!/usr/bin/env python3
"""Pack a build-expansion manifest into the ExpandBuilds wire format.

The manifest is produced by `build-expansion-manifest.py`:

    {"schema_version": 1, "builds": [{"parent": 7, "frames": [...], "notes": ""}]}

The ExpandBuilds VBA macro consumes a control-char-delimited string (read from
file as UTF-8 by expand-builds.applescript, so VBA never decodes UTF-8 itself):

    record   = parent <US> notes <US> frame0 <GS> frame1 <GS> ...
    records joined by <RS>

where RS=Chr(30), US=Chr(31), GS=Chr(29) — non-printing controls that don't
occur in prose notes or POSIX paths. Records are emitted **descending by parent
slide** so the macro can insert each parent's frames without shifting the
indices of lower-numbered parents still to be expanded.

This deterministic conversion is split out of expand-builds.sh so it can be
unit-tested (the VBA side cannot run in CI).

Usage:
    build-expansion-to-packed.py <manifest.json> <packed_out>
"""

import json
import sys
from pathlib import Path

RS, US, GS = chr(30), chr(31), chr(29)


def manifest_to_packed(manifest: object) -> str:
    """Return the ExpandBuilds packed wire string, descending by parent slide.

    Raises ValueError (actionable message) on malformed input: non-object
    manifest, missing/empty builds, a build with no frames, a non-int parent, or
    any frame path / notes text containing a reserved control delimiter.
    """
    if not isinstance(manifest, dict):
        raise ValueError('manifest must be a JSON object like {"builds": [...]}')
    if manifest.get("schema_version") != 1:
        raise ValueError(
            f"unsupported manifest schema_version {manifest.get('schema_version')!r} "
            "(expected 1) — regenerate it with build-expansion-manifest.py"
        )
    builds = manifest.get("builds")
    if not isinstance(builds, list) or not builds:
        raise ValueError(
            "manifest has no 'builds' entries — nothing to expand; skip the "
            "ExpandBuilds pass when the outline declares no build sequences"
        )

    def parent_of(b: object) -> int:
        if not isinstance(b, dict):
            raise ValueError(f"build entry must be an object, got {type(b).__name__}")
        try:
            return int(b["parent"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"build entry has no integer 'parent': {b!r}") from None

    records = []
    for b in sorted(builds, key=parent_of, reverse=True):
        parent = parent_of(b)
        frames = b.get("frames")
        if not isinstance(frames, list) or not frames:
            raise ValueError(f"build for parent {parent} has no frames")
        notes = b.get("notes", "") or ""
        for f in frames:
            if not isinstance(f, str):
                raise ValueError(f"frame for parent {parent} must be a string path")
            if any(c in f for c in (RS, US, GS)):
                raise ValueError(f"frame path for parent {parent} contains a reserved control char: {f!r}")
        if any(c in notes for c in (RS, US, GS)):
            raise ValueError(f"notes for parent {parent} contain a reserved control char")
        records.append(f"{parent}{US}{notes}{US}{GS.join(frames)}")
    return RS.join(records)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("usage: build-expansion-to-packed.py <manifest.json> <packed_out>", file=sys.stderr)
        return 2
    manifest_path, out_path = Path(argv[0]), Path(argv[1])
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: cannot read manifest {manifest_path}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: manifest {manifest_path} is not valid JSON: {exc}", file=sys.stderr)
        return 1
    try:
        packed = manifest_to_packed(manifest)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    out_path.write_text(packed, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
