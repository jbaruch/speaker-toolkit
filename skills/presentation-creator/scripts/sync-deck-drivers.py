#!/usr/bin/env python3
"""Keep the deck-ops VBA/AppleScript drivers shippable past tessl's extension filter.

`tessl install` only materializes a fixed set of extensions (.md .py .json .sh
.txt) — it STRIPS `.bas` and `.applescript`. The PowerPoint deck layer needs
`RunDeckOps.bas` (imported into DeckOps.pptm) and the eight `*.applescript`
drivers (invoked by the `.sh` wrappers via osascript), so every installed plugin
would otherwise have a dead deck layer.

Fix: each driver has a committed `.txt` mirror (which survives install). This
tool keeps the mirrors in sync with the real files and recreates the real files
from the mirrors on a consumer machine.

Modes:
  materialize [--force]  — for each `<name>.txt` mirror, write `<name>` (the real
                           .bas/.applescript). Default: only when the real file is
                           MISSING (install-restore; a no-op in the dev tree where
                           the reals exist, and never clobbers an in-progress edit).
                           --force overwrites — use after a plugin UPDATE to refresh
                           a stale materialized driver.
  mirror                 — regenerate the `.txt` mirrors from the real files. Run
                           after editing a `.bas`/`.applescript` so the mirror
                           stays byte-identical (the source of truth is the real
                           file; see rules — "keep editing .bas").
  check                  — assert every real driver has a byte-identical mirror and
                           vice versa. Exit 1 listing drift (the CI guard).

The mapping is deterministic file copy -> script, not LLM (rules/script-delegation.md).
The VBA side can't run in CI; this tool is unit-tested in
tests/test_deck_driver_mirrors.py.

Usage:
    sync-deck-drivers.py {materialize|mirror|check} [--force] [--dir DIR]

DIR defaults to this script's own directory (the scripts dir holding the drivers).
"""

import argparse
import shutil
import sys
from pathlib import Path

MIRROR_SUFFIX = ".txt"
DRIVER_GLOBS = ("*.bas", "*.applescript")


def _reals(base: Path) -> list[Path]:
    """The real driver files (*.bas, *.applescript) in base, sorted."""
    out: list[Path] = []
    for g in DRIVER_GLOBS:
        out.extend(base.glob(g))
    return sorted(out)


def _mirrors(base: Path) -> list[Path]:
    """The committed `.txt` mirrors (*.bas.txt, *.applescript.txt) in base, sorted."""
    out: list[Path] = []
    for g in DRIVER_GLOBS:
        out.extend(base.glob(g + MIRROR_SUFFIX))
    return sorted(out)


def _mirror_of(real: Path) -> Path:
    return real.with_name(real.name + MIRROR_SUFFIX)


def _real_of(mirror: Path) -> Path:
    return mirror.with_name(mirror.name[: -len(MIRROR_SUFFIX)])


def materialize(base: Path, force: bool = False) -> list[Path]:
    """Recreate real drivers from their `.txt` mirrors. Returns the files written.

    Create-if-missing by default (install-restore, never clobbers a dev edit);
    --force overwrites to refresh a stale driver after a plugin update.
    """
    written: list[Path] = []
    for m in _mirrors(base):
        target = _real_of(m)
        if force or not target.exists():
            shutil.copyfile(m, target)
            written.append(target)
    return written


def regenerate_mirrors(base: Path) -> list[Path]:
    """Rewrite `.txt` mirrors from the real drivers. Returns the mirrors changed."""
    written: list[Path] = []
    for r in _reals(base):
        m = _mirror_of(r)
        data = r.read_bytes()
        if not m.exists() or m.read_bytes() != data:
            m.write_bytes(data)
            written.append(m)
    return written


def check(base: Path) -> list[str]:
    """Return a list of drift problems (empty == in sync)."""
    problems: list[str] = []
    real_names = {r.name for r in _reals(base)}
    for r in _reals(base):
        m = _mirror_of(r)
        if not m.exists():
            problems.append(
                f"missing mirror for {r.name}: expected {m.name} — "
                "run: sync-deck-drivers.py mirror"
            )
        elif m.read_bytes() != r.read_bytes():
            problems.append(
                f"mirror {m.name} is out of sync with {r.name} — "
                "run: sync-deck-drivers.py mirror"
            )
    for m in _mirrors(base):
        if _real_of(m).name not in real_names:
            problems.append(
                f"orphan mirror {m.name} has no source {_real_of(m).name} — "
                "delete the mirror or restore the source driver"
            )
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Keep deck-ops .bas/.applescript drivers shippable past tessl's extension filter.")
    ap.add_argument("mode", choices=("materialize", "mirror", "check"))
    ap.add_argument("--force", action="store_true",
                    help="materialize: overwrite existing real drivers (refresh after a plugin update)")
    ap.add_argument("--dir", type=Path, default=Path(__file__).resolve().parent,
                    help="the scripts dir holding the drivers (default: this script's dir)")
    args = ap.parse_args(argv)
    base = args.dir

    if not base.is_dir():
        print(f"ERROR: --dir not found: {base}", file=sys.stderr)
        return 2

    if args.mode == "materialize":
        written = materialize(base, force=args.force)
        if written:
            print("materialized: " + ", ".join(p.name for p in written))
        else:
            print("materialize: nothing to do (real drivers already present)")
        return 0

    if args.mode == "mirror":
        written = regenerate_mirrors(base)
        if written:
            print("updated mirrors: " + ", ".join(p.name for p in written))
        else:
            print("mirror: all mirrors already in sync")
        return 0

    # check
    problems = check(base)
    if problems:
        print("deck-driver mirror drift:", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 1
    print("deck-driver mirrors in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
