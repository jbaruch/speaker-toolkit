#!/usr/bin/env python3
"""Stage referenced images into PowerPoint's sandbox container and rewrite paths.

macOS PowerPoint is sandboxed: Background.Fill.UserPicture(path) on an image
OUTSIDE the app container (e.g. a Google Drive CloudStorage path) triggers a
per-file Powerbox "grant access" prompt. Copying the images INTO PowerPoint's
own container Data dir — which the sandboxed process can always read without a
prompt — collapses every per-illustration prompt to ZERO, with no Full Disk
Access grant. See rules/deck-editing-rules.md.

Mac PowerPoint VBA has no Application.FileDialog, so a "grant a folder once"
macro is impossible; container-staging is the supported no-FDA path.

This script copies every image referenced by a deck-ops manifest into a staging
directory (created if absent) and emits a NEW manifest whose image paths point
at the staged copies. It handles both manifest shapes the deck-ops passes
consume:

  backgrounds (apply-backgrounds): {"backgrounds": {"<n>": "/abs/img", ...}}
  build-expansion (expand-builds): {"schema_version": 1,
      "builds": [{"parent": N, "frames": ["/abs/img", ...], "notes": "..."}]}

Only image PATH fields are rewritten; slide numbers, parent numbers, notes, and
schema_version are passed through untouched.

Deterministic file copy -> script, not LLM (rules/script-delegation.md). The VBA
side cannot run in CI; this stager is unit-tested in
tests/test_stage_images_into_container.py.

Usage:
    stage-images-into-container.py <manifest.json> --stage-dir <dir> [--out <rewritten.json>]

stdout: the rewritten manifest JSON (also written to --out when given).
Exits non-zero with an actionable stderr message on a missing referenced image,
a copy failure, or an unrecognized manifest shape.
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


def _staged_name(src: Path) -> str:
    """Collision-safe, deterministic staged filename for a source image.

    Two source dirs may both hold `slide-07.jpg`; a hash of the absolute path
    keeps their staged copies distinct, while the same source always maps to the
    same staged name (idempotent re-runs overwrite in place). The original
    extension is preserved so UserPicture recognizes the image type.
    """
    digest = hashlib.sha1(str(src).encode("utf-8")).hexdigest()[:12]
    return f"{digest}-{src.name}"


def _stage_one(raw_path: object, stage_dir: Path, where: str) -> str:
    """Copy one referenced image into stage_dir; return the staged absolute path.

    `where` names the manifest slot (e.g. "slide 7", "parent 14 frame 2") so a
    missing-file error points the author at the offending entry.
    """
    if not isinstance(raw_path, str):
        raise SystemExit(
            f"ERROR: image path for {where} must be a string, got "
            f"{type(raw_path).__name__} — fix the manifest entry."
        )
    src = Path(raw_path).expanduser()
    if not src.is_file():
        raise SystemExit(
            f"ERROR: image for {where} not found: {raw_path} — regenerate the "
            "illustrations or fix the manifest path before staging."
        )
    src = src.resolve()
    dst = stage_dir / _staged_name(src)
    try:
        shutil.copy2(src, dst)
    except OSError as exc:
        raise SystemExit(
            f"ERROR: cannot copy image for {where} into the PowerPoint container "
            f"staging dir {stage_dir}: {exc.strerror or exc} — check that the "
            "container exists and is writable."
        ) from None
    return str(dst)


def stage_manifest(manifest: object, stage_dir: Path) -> dict:
    """Copy every referenced image into stage_dir, return a rewritten manifest.

    Detects the manifest shape by its top-level key: `backgrounds` (object of
    slide # -> path) or `builds` (list of {parent, frames[], notes}). Raises
    SystemExit with an actionable message on an unrecognized shape.
    """
    if not isinstance(manifest, dict):
        raise SystemExit(
            "ERROR: manifest must be a JSON object — a backgrounds manifest "
            '({"backgrounds": {...}}) or a build-expansion manifest '
            '({"builds": [...]}).'
        )

    try:
        stage_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit(
            f"ERROR: cannot create staging dir {stage_dir}: {exc.strerror or exc} — "
            "confirm PowerPoint's container exists and is writable."
        ) from None

    if isinstance(manifest.get("backgrounds"), dict):
        bg = manifest["backgrounds"]
        staged = {
            key: _stage_one(path, stage_dir, f"slide {key}")
            for key, path in bg.items()
        }
        out = dict(manifest)
        out["backgrounds"] = staged
        return out

    if isinstance(manifest.get("builds"), list):
        new_builds = []
        for b in manifest["builds"]:
            if not isinstance(b, dict):
                raise SystemExit(
                    f"ERROR: build entry must be an object, got {type(b).__name__}."
                )
            parent = b.get("parent")
            frames = b.get("frames")
            if not isinstance(frames, list):
                raise SystemExit(
                    f"ERROR: build for parent {parent} has no 'frames' list to stage."
                )
            staged_frames = [
                _stage_one(f, stage_dir, f"parent {parent} frame {i}")
                for i, f in enumerate(frames)
            ]
            nb = dict(b)
            nb["frames"] = staged_frames
            new_builds.append(nb)
        out = dict(manifest)
        out["builds"] = new_builds
        return out

    raise SystemExit(
        "ERROR: unrecognized manifest shape — expected a top-level 'backgrounds' "
        "object or 'builds' list. Pass a backgrounds manifest "
        "(apply-illustrations-to-deck.py --backgrounds-out) or a build-expansion "
        "manifest (build-expansion-manifest.py)."
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Copy a manifest's images into PowerPoint's container; rewrite paths.")
    ap.add_argument("manifest", type=Path, help="Path to the deck-ops manifest JSON")
    ap.add_argument("--stage-dir", type=Path, required=True,
                    help="Staging dir inside PowerPoint's container Data dir")
    ap.add_argument("--out", type=Path, default=None,
                    help="Also write the rewritten manifest JSON here")
    args = ap.parse_args(argv)

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: cannot read manifest {args.manifest}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: manifest {args.manifest} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    rewritten = stage_manifest(manifest, args.stage_dir)
    text = json.dumps(rewritten, indent=2)
    if args.out is not None:
        try:
            args.out.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot write rewritten manifest {args.out}: {exc.strerror or exc} — "
                  "check the path and that its directory is writable", file=sys.stderr)
            return 1
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
