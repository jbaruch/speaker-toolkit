#!/usr/bin/env python3
"""Emit the build-expansion manifest for deck assembly.

Reads outline.yaml (the single source of truth) + the generated build frames and
produces a JSON manifest describing how each progressive-reveal parent slide
expands into its sequence of full-bleed frames. The manifest is consumed by the
ExpandBuilds VBA pass (via expand-builds.sh) which replaces each parent slide
with its frames.

Why a manifest (not direct deck edits): structural deck edits go through real
PowerPoint / RunDeckOps, never python-pptx — see rules/deck-editing-rules.md.
This script never touches the deck. Its writes besides ``--out`` are the
``--notes-out`` map and the stamped frame copies described below, when the
outline stamps its footer.

Manifest shape (schema_version 1):

    {
      "schema_version": 1,
      "builds": [
        {
          "parent": 7,
          "frames": ["/abs/builds/slide-07-build-00.jpg", ..., "slide-07-build-03.jpg"],
          "notes": "",
          "frame_notes": ["", "", "", ""]
        }
      ]
    }

- `parent` — the 1-based position, in the built deck, of the slide that
  carries the `builds` block (`outline_schema.deck_positions`): the slide
  ExpandBuilds replaces. It equals the outline number only when numbering runs
  1..N; a zero-based or gapped outline still names the right slide.
- `frames` — absolute paths to build-00 .. build-N, in ascending step order.
  The parent slide is replaced by these frames (build-00 first, build-N last).
- `frame_notes` — one speaker note per frame, in frame order: the parent's
  note split at its `[BUILD NN]` cue lines (`build_notes.split_note`; empty
  without `--notes`). The ExpandBuilds packer ignores it.
- `notes` — the FINAL frame's note, which ExpandBuilds writes onto that frame:
  `frame_notes[-1]`, so the macro's wire format and behaviour are unchanged.

Speaker notes reach the frames through the notes pass, not the macro.
`--notes notes.json --notes-out notes-expanded.json` writes the whole deck's
notes re-keyed for the expanded deck (`build_notes.expanded_notes_map`):
every frame's segment, plus every other slide moved past the frames inserted
before it. Hand that file to `inject-notes.sh` after `expand-builds.sh`. It
rewrites the final frame with the same text ExpandBuilds wrote. A parent whose
note has no cue keeps it whole on frame 00 and warns on stderr; an invalid cue
exits non-zero naming the slide and the repair.

When the outline stamps its footer (`style_anchor.footer_style`), each poster
parent's frames are stamped by `footer_stamp.stamp_footer_file` into
`BUILDS_DIR/footer-stamped/slide-NN-build-MM.png` and `frames` lists those
copies; the raw frames stay footer-free for editing. Every build parent of
such a deck must satisfy `footer_stamp.stamped_slide`, the same answer
apply-illustrations-to-deck.py uses for parent slides; any other parent exits
non-zero naming the slide.

ExpandBuilds processes parents in descending slide order so inserting a parent's
frames never shifts the indices of lower-numbered parents still to be expanded.

Usage:
    build-expansion-manifest.py OUTLINE_YAML BUILDS_DIR [--out manifest.json]
        [--notes notes.json --notes-out notes-expanded.json]

stdout: the manifest JSON (also written to --out when given).
Exit non-zero with a stderr diagnostic when a declared build parent has no
frames on disk, a declared frame is not a file that decodes as an image, or a
build parent's note cannot be split across its frames.
"""

import argparse
import json
import sys
from pathlib import Path

# Sibling modules: this script's own directory is already importable.
from build_notes import (
    BuildNotesError,
    expanded_notes_map,
    normalize_notes_map,
    outline_cues,
    split_note,
)
from footer_stamp import (
    FRAME_RE,
    FooterStampError,
    deck_stamp_set,
    require_one_geometry,
    stamp_footer_file,
    stamp_spec,
    stamped_slide,
    unusable_image,
)

# outline.yaml is the single source of truth; its schema + loader live with the
# presentation-creator scripts.
sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent.parent
        / "presentation-creator"
        / "scripts"
    ),
)
import outline_schema  # noqa: E402  (path appended above)

SCHEMA_VERSION = 1


def parse_build_specs(outline_path: Path) -> list[dict]:
    """Return build specs for each parent slide: {parent, count, steps, footer, cues}.

    Read from outline.yaml's per-slide `builds`. The schema guarantees steps are
    contiguous from 0, so `steps` is [0, 1, ..., N-1] and `count` == len(steps).
    `footer` is the (text, style) to stamp on the parent's frames, or None.
    `cues` is the steps its script's bare `cue: "BUILD NN"` items name, in order.
    """
    outline = outline_schema.load_outline_partial(outline_path)
    footer = stamp_spec(outline.style_anchor)
    specs = []
    for slide in outline.slides:
        if not slide.builds:
            continue
        if footer is not None and not stamped_slide(slide):
            raise SystemExit(
                f"ERROR: slide {slide.n} is a build parent in a poster deck that "
                "stamps its footer, but it is not an illustrated FULL slide "
                "without safe_zone; poster-theatrical decks allow only those. "
                "Set it to format FULL with an image_prompt and remove safe_zone, "
                "or drop its builds."
            )
        steps = sorted(b.step for b in slide.builds)
        specs.append(
            {
                "parent": slide.n,
                "count": len(steps),
                "steps": steps,
                "footer": footer,
                "cues": outline_cues(item.cue for item in slide.script),
            }
        )
    return specs


def frames_for(builds_dir: Path, parent: int) -> dict[int, Path]:
    """Map step number -> build frame file for a parent (slide-NN-build-MM.<ext>)."""
    found = {}
    for p in builds_dir.glob(f"slide-{parent:02d}-build-*"):
        fm = FRAME_RE.search(p.name)
        if fm:
            found[int(fm.group(1))] = p
    return found


def _require_usable_frames(specs: list[dict], builds_dir: Path) -> None:
    """Every declared frame is on disk and decodes, before any is stamped or listed.

    parse_build_specs reads outline.yaml through the schema, which already
    guarantees each slide's build steps are contiguous from 0, so step count,
    ordering and contiguity need no re-checking here.
    """
    for spec in specs:
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
        unusable = [
            why for step in steps if (why := unusable_image(found[step])) is not None
        ]
        if unusable:
            raise SystemExit(
                f"ERROR: slide {parent}'s build frames cannot be placed: "
                f"{'; '.join(unusable)}. ExpandBuilds would fail on them inside "
                f"PowerPoint. Regenerate: generate-illustrations.py <outline> "
                f"--build {parent}"
            )


def _require_one_stamped_geometry(
    outline_path: Path, specs: list[dict], builds_dir: Path
) -> None:
    """The whole deck's stamp set shares one size before any frame is stamped.

    The same set the apply step checks: every stamped slide image and every
    declared build frame, so whichever command runs first refuses a mixed deck.
    A stale frame outside the declared steps is never stamped, so it never
    constrains geometry.
    """
    if not any(spec["footer"] is not None for spec in specs):
        return
    slides = outline_schema.load_outline_partial(outline_path).slides
    try:
        require_one_geometry(deck_stamp_set(slides, builds_dir.parent, builds_dir))
    except FooterStampError as exc:
        raise SystemExit(f"ERROR: cannot stamp the build frames: {exc}") from exc


def build_manifest(
    outline_path: Path, builds_dir: Path, notes_map: object = None
) -> dict:
    """Build the expansion manifest.

    notes_map: optional {"<0-based deck slide #>": "notes"} (the historical
    inject-notes format). A build parent at 1-based deck position P
    (``outline_schema.deck_positions``, so outline numbering may start at 0)
    maps to 0-based key str(P-1), and P is the manifest's ``parent``, the index
    ExpandBuilds replaces. Its note is split at its `[BUILD NN]` cue lines into
    ``frame_notes``, and ``notes`` carries the final frame's segment. When
    omitted, every frame's note is empty. Split warnings go to stderr.
    """
    try:
        notes = normalize_notes_map({} if notes_map is None else notes_map)
    except BuildNotesError as exc:
        raise SystemExit(f"ERROR: {exc} — fix the --notes JSON.") from exc
    # ExpandBuilds and the notes map index the built deck, not outline numbers.
    positions = outline_schema.deck_positions(
        outline_schema.load_outline_partial(outline_path).slides
    )
    specs = sorted(parse_build_specs(outline_path), key=lambda s: s["parent"])
    _require_usable_frames(specs, builds_dir)
    _require_one_stamped_geometry(outline_path, specs, builds_dir)
    builds = []
    for spec in specs:
        parent, steps = spec["parent"], spec["steps"]
        found = frames_for(builds_dir, parent)
        position = positions[parent]
        try:
            frame_notes, warnings = split_note(
                notes.get(position - 1, ""),
                len(steps),
                f"{parent} (notes key {position - 1})",
                spec["cues"],
            )
        except BuildNotesError as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        for warning in warnings:
            print(warning, file=sys.stderr)
        frames = [found[s] for s in steps]
        if spec["footer"] is not None:
            text, style = spec["footer"]
            stamped_dir = builds_dir / "footer-stamped"
            stamped: list[Path] = []
            for frame in frames:
                try:
                    stamped.append(stamp_footer_file(frame, stamped_dir, text, style))
                except FooterStampError as exc:
                    raise SystemExit(
                        f"ERROR: cannot stamp the footer on slide {parent}'s build "
                        f"frames: {exc}"
                    ) from exc
                except OSError as exc:
                    raise SystemExit(
                        f"ERROR: cannot stamp {frame.name} into {stamped_dir} "
                        f"({type(exc).__name__}: {exc.strerror or exc}); regenerate "
                        "or replace that frame if it is unreadable, or make the "
                        "directory writable, then re-run"
                    ) from exc
            frames = stamped
        builds.append(
            {
                "parent": position,
                "frames": [str(frame.resolve()) for frame in frames],
                "notes": frame_notes[-1],
                "frame_notes": frame_notes,
            }
        )
    return {"schema_version": SCHEMA_VERSION, "builds": builds}


def expanded_notes(manifest: dict, notes_map: object) -> dict[str, str]:
    """The whole deck's notes keyed on the deck after ExpandBuilds.

    Every build frame gets its ``frame_notes`` entry; every other note moves
    past the frames inserted before it. The input ``inject-notes.sh`` takes.
    """
    try:
        return expanded_notes_map(
            normalize_notes_map(notes_map),
            {b["parent"]: b["frame_notes"] for b in manifest["builds"]},
        )
    except BuildNotesError as exc:
        raise SystemExit(f"ERROR: {exc} — fix the --notes JSON.") from exc


def _write(path: Path, text: str, what: str) -> int:
    try:
        path.write_text(text + "\n", encoding="utf-8")
    except OSError as exc:
        print(
            f"ERROR: cannot write {what} {path}: {exc.strerror or exc} — "
            "check the path and that its directory is writable",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Emit the build-expansion manifest for deck assembly."
    )
    ap.add_argument(
        "outline", type=Path, help="Path to outline.yaml (the single source of truth)"
    )
    ap.add_argument(
        "builds_dir", type=Path, help="Directory with slide-NN-build-MM.<ext> frames"
    )
    ap.add_argument(
        "--out", type=Path, default=None, help="Also write the manifest JSON here"
    )
    ap.add_argument(
        "--notes",
        type=Path,
        default=None,
        help='Notes JSON {"<0-based slide #>": "text"} keyed on the deck before '
        "expansion; each build parent's note is split across its frames at its "
        "[BUILD NN] cue lines. Requires --notes-out",
    )
    ap.add_argument(
        "--notes-out",
        type=Path,
        default=None,
        help="Write the whole deck's notes keyed on the deck after expansion, "
        "every build frame included: the notes JSON for inject-notes.sh",
    )
    args = ap.parse_args(argv)
    if (args.notes is None) != (args.notes_out is None):
        ap.error(
            "--notes and --notes-out go together: build frames get their notes "
            "only from the expanded map inject-notes.sh applies after expansion"
        )
    if not args.outline.is_file():
        raise SystemExit(f"ERROR: outline not found: {args.outline}")
    try:
        outline_schema.require_current_outline(args.outline)
    except outline_schema.OutlineVersionError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    notes_map = None
    if args.notes is not None:
        try:
            notes_map = json.loads(args.notes.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"ERROR: cannot read notes JSON {args.notes}: {exc}")
        if not isinstance(notes_map, dict):
            raise SystemExit(
                f"ERROR: notes JSON {args.notes} must be an object mapping slide # -> text"
            )

    manifest = build_manifest(args.outline, args.builds_dir, notes_map)
    text = json.dumps(manifest, indent=2)
    if args.out is not None and _write(args.out, text, "manifest"):
        return 1
    if args.notes_out is not None:
        expanded = json.dumps(
            expanded_notes(manifest, notes_map), indent=2, ensure_ascii=False
        )
        if _write(args.notes_out, expanded, "expanded notes"):
            return 1
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
