#!/usr/bin/env python3
"""Emit the build-expansion manifest for deck assembly.

Reads a presentation outline + the generated build frames and produces a JSON
manifest describing how each progressive-reveal parent slide expands into its
sequence of full-bleed frames. The manifest is consumed by the ExpandBuilds VBA
pass (via expand-builds.sh) which replaces each parent slide with its frames.

Why a manifest (not direct deck edits): structural deck edits go through real
PowerPoint / RunDeckOps, never python-pptx — see rules/deck-editing-rules.md.
This script only produces the plan; it does not touch the deck.

Manifest shape (schema_version 1):

    {
      "schema_version": 1,
      "builds": [
        {
          "parent": 7,
          "frames": ["/abs/builds/slide-07-build-00.jpg", ..., "slide-07-build-03.jpg"],
          "notes": ""
        }
      ]
    }

- `parent` — the 1-based outline slide number that carries the `Builds:` block.
- `frames` — absolute paths to build-00 .. build-N, in ascending step order.
  The parent slide is replaced by these frames (build-00 first, build-N last).
- `notes` — speaker notes for the FINAL frame only (empty when none); earlier
  frames get no notes (see skills/illustrations/references/builds.md).

ExpandBuilds processes parents in descending slide order so inserting a parent's
frames never shifts the indices of lower-numbered parents still to be expanded.

Usage:
    build-expansion-manifest.py OUTLINE_MD BUILDS_DIR [--out manifest.json]

stdout: the manifest JSON (also written to --out when given).
Exit non-zero with a stderr diagnostic when a declared build parent has no
frames on disk.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = 1

_SLIDE_BLOCK_RE = re.compile(r"###\s+Slide\s+(\d+):(.*?)(?=\n###\s|\n##\s|\Z)", re.DOTALL)
_BUILDS_RE = re.compile(r"-\s*Builds:\s*(\d+)\s+steps?")
_FRAME_RE = re.compile(r"slide-\d+-build-(\d+)\.[A-Za-z0-9]+$")


def parse_build_parents(outline_path: Path) -> list[int]:
    """Return the slide numbers whose block declares a `Builds: N steps` line."""
    text = outline_path.read_text(encoding="utf-8")
    parents = []
    for m in _SLIDE_BLOCK_RE.finditer(text):
        if _BUILDS_RE.search(m.group(2)):
            parents.append(int(m.group(1)))
    return parents


def frames_for(builds_dir: Path, parent: int) -> list[Path]:
    """Build frame files for a parent, in ascending step order (build-00..N)."""
    matches = []
    for p in builds_dir.glob(f"slide-{parent:02d}-build-*"):
        m = _FRAME_RE.search(p.name)
        if m:
            matches.append((int(m.group(1)), p))
    return [p for _, p in sorted(matches, key=lambda t: t[0])]


def build_manifest(outline_path: Path, builds_dir: Path) -> dict:
    builds = []
    for parent in sorted(parse_build_parents(outline_path)):
        frames = frames_for(builds_dir, parent)
        if not frames:
            raise SystemExit(
                f"ERROR: slide {parent} declares a Builds block but no build "
                f"frames (slide-{parent:02d}-build-NN.*) were found in "
                f"{builds_dir}. Generate them first: generate-illustrations.py "
                f"<outline> --build {parent}"
            )
        builds.append({
            "parent": parent,
            "frames": [str(f.resolve()) for f in frames],
            "notes": "",
        })
    return {"schema_version": SCHEMA_VERSION, "builds": builds}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outline", type=Path, help="Path to the presentation outline markdown")
    ap.add_argument("builds_dir", type=Path, help="Directory with slide-NN-build-MM.<ext> frames")
    ap.add_argument("--out", type=Path, default=None, help="Also write the manifest JSON here")
    args = ap.parse_args(argv)

    if not args.outline.is_file():
        raise SystemExit(f"ERROR: outline not found: {args.outline}")

    manifest = build_manifest(args.outline, args.builds_dir)
    text = json.dumps(manifest, indent=2)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
