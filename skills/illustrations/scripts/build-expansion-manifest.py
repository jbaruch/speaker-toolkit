#!/usr/bin/env python3
"""Emit the build-expansion manifest for deck assembly.

Reads outline.yaml (the single source of truth) + the generated build frames and
produces a JSON manifest describing how each progressive-reveal parent slide
expands into its sequence of full-bleed frames. The manifest is consumed by the
ExpandBuilds VBA pass (via expand-builds.sh) which replaces each parent slide
with its frames.

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

- `parent` — the 1-based outline slide number that carries the `builds` block.
- `frames` — absolute paths to build-00 .. build-N, in ascending step order.
  The parent slide is replaced by these frames (build-00 first, build-N last).
- `notes` — speaker notes for the FINAL frame only (empty when none); earlier
  frames get no notes (see skills/illustrations/references/builds.md).

ExpandBuilds processes parents in descending slide order so inserting a parent's
frames never shifts the indices of lower-numbered parents still to be expanded.

Usage:
    build-expansion-manifest.py OUTLINE_YAML BUILDS_DIR [--out manifest.json]

stdout: the manifest JSON (also written to --out when given).
Exit non-zero with a stderr diagnostic when a declared build parent has no
frames on disk.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# outline.yaml is the single source of truth; its schema + loader live with the
# presentation-creator scripts.
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent.parent
        / "presentation-creator" / "scripts"),
)
import outline_schema  # noqa: E402  (path appended above)

SCHEMA_VERSION = 1

_FRAME_RE = re.compile(r"slide-\d+-build-(\d+)\.[A-Za-z0-9]+$")


def parse_build_specs(outline_path: Path) -> list[dict]:
    """Return build specs for each parent slide: {parent, count, steps}.

    Read from outline.yaml's per-slide `builds`. The schema guarantees steps are
    contiguous from 0, so `steps` is [0, 1, ..., N-1] and `count` == len(steps).
    """
    outline = outline_schema.load_outline_partial(outline_path)
    specs = []
    for slide in outline.slides:
        if not slide.builds:
            continue
        steps = sorted(b.step for b in slide.builds)
        specs.append({"parent": slide.n, "count": len(steps), "steps": steps})
    return specs


def frames_for(builds_dir: Path, parent: int) -> dict[int, Path]:
    """Map step number -> build frame file for a parent (slide-NN-build-MM.<ext>)."""
    found = {}
    for p in builds_dir.glob(f"slide-{parent:02d}-build-*"):
        fm = _FRAME_RE.search(p.name)
        if fm:
            found[int(fm.group(1))] = p
    return found


def build_manifest(outline_path: Path, builds_dir: Path, notes_map: dict | None = None) -> dict:
    """Build the expansion manifest.

    notes_map: optional {"<0-based deck slide #>": "notes"} (the historical
    inject-notes format). A build parent at 1-based outline slide N maps to
    0-based key str(N-1); its notes ride onto the FINAL build frame so expansion
    doesn't drop them. When omitted, notes are empty and the post-expansion
    notes pass must carry them instead.
    """
    notes_map = notes_map or {}
    builds = []
    # parse_build_specs reads outline.yaml through the schema, which already
    # guarantees each slide's build steps are contiguous from 0 — so step
    # count, ordering, and contiguity need no re-checking here. The only
    # remaining failure mode is a declared step whose frame isn't on disk yet.
    for spec in sorted(parse_build_specs(outline_path), key=lambda s: s["parent"]):
        parent, steps = spec["parent"], spec["steps"]
        found = frames_for(builds_dir, parent)
        missing = [s for s in steps if s not in found]
        if missing:
            raise SystemExit(
                f"ERROR: slide {parent} is missing build frame(s) for step(s) "
                f"{missing} (declared build-NN entries: {steps}). A partial "
                "sequence would expand into a broken reveal. Regenerate: "
                f"generate-illustrations.py <outline> --build {parent}"
            )
        # A null/absent note is empty; a non-string note is an error — never
        # coerce it, or a JSON null would become the literal "None" on the final
        # build frame (mirrors notes-to-packed.py's drop-empty contract).
        raw_note = notes_map.get(str(parent - 1))
        if raw_note is None:
            raw_note = ""
        elif not isinstance(raw_note, str):
            raise SystemExit(
                f"ERROR: note for slide {parent} (notes key {parent - 1}) must be a "
                f"string, got {type(raw_note).__name__} — fix the --notes JSON."
            )
        builds.append({
            "parent": parent,
            "frames": [str(found[s].resolve()) for s in steps],
            "notes": raw_note,
        })
    return {"schema_version": SCHEMA_VERSION, "builds": builds}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Emit the build-expansion manifest for deck assembly.")
    ap.add_argument("outline", type=Path, help="Path to outline.yaml (the single source of truth)")
    ap.add_argument("builds_dir", type=Path, help="Directory with slide-NN-build-MM.<ext> frames")
    ap.add_argument("--out", type=Path, default=None, help="Also write the manifest JSON here")
    ap.add_argument("--notes", type=Path, default=None,
                    help='Optional notes JSON {"<0-based slide #>": "text"}; a build '
                         "parent's notes ride onto its final frame so expansion keeps them")
    args = ap.parse_args(argv)

    if not args.outline.is_file():
        raise SystemExit(f"ERROR: outline not found: {args.outline}")

    notes_map = None
    if args.notes is not None:
        try:
            notes_map = json.loads(args.notes.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"ERROR: cannot read notes JSON {args.notes}: {exc}")
        if not isinstance(notes_map, dict):
            raise SystemExit(f"ERROR: notes JSON {args.notes} must be an object mapping slide # -> text")

    manifest = build_manifest(args.outline, args.builds_dir, notes_map)
    text = json.dumps(manifest, indent=2)
    if args.out is not None:
        try:
            args.out.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot write manifest {args.out}: {exc.strerror or exc} — "
                  "check the path and that its directory is writable", file=sys.stderr)
            return 1
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
