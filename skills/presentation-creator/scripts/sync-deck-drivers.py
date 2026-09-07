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
  stamp                  — recompute the content stamp inside RunDeckOps.bas
                           (`DECKOPS_STAMP`, returned by the module's
                           DeckOpsVersion() macro) so deckops-doctor.py can tell a
                           stale import inside DeckOps.pptm from a current one.
                           Implied by `mirror`; run standalone only to inspect it.
  export --to DIR        — materialize if needed, then copy RunDeckOps.bas into DIR
                           and print its path. DIR is a location the user can
                           actually reach in PowerPoint's VBA-editor Import panel:
                           an installed plugin lives under a hidden `.tessl/`
                           directory that a macOS open panel does not show, so the
                           import path has to leave the plugin tree entirely.
  check                  — assert every real driver has a byte-identical mirror and
                           vice versa, and that the stamp is current. Exit 1
                           listing drift (the CI guard).

The mapping is deterministic file copy -> script, not LLM (rules/script-delegation.md).
The VBA side can't run in CI; this tool is unit-tested in
tests/test_deck_driver_mirrors.py.

Usage:
    sync-deck-drivers.py {materialize|mirror|stamp|export|check} [--force]
                        [--dir DIR] [--to DIR]

DIR defaults to this script's own directory (the scripts dir holding the drivers).
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

MIRROR_SUFFIX = ".txt"
DRIVER_GLOBS = ("*.bas", "*.applescript")

# The one driver carrying a content stamp, and the exact line shape holding it.
# A saved .pptm gives up no VBA source, so a stamp travelling INSIDE the module is
# the only thing a running PowerPoint can hand back to prove which build of the
# macro was imported. Content-addressed rather than hand-bumped: an editor who
# forgets to bump a counter ships a lie, and this one cannot be forgotten because
# `mirror` recomputes it and `check` fails on drift.
STAMP_DRIVER = "RunDeckOps.bas"
STAMP_PREFIX = 'Public Const DECKOPS_STAMP As String = "'
STAMP_SUFFIX = '"'
STAMP_PLACEHOLDER = "0" * 16
STAMP_LEN = 16


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


def _stamp_line_bounds(text: str) -> tuple[int, int]:
    """Return the (start, end) offsets of the stamp literal, or raise ValueError."""
    start = text.find(STAMP_PREFIX)
    if start < 0:
        raise ValueError(
            f"{STAMP_DRIVER} has no {STAMP_PREFIX.strip()}... line — restore it from "
            "git; deckops-doctor.py cannot detect a stale macro import without it"
        )
    if text.find(STAMP_PREFIX, start + 1) >= 0:
        raise ValueError(
            f"{STAMP_DRIVER} has more than one {STAMP_PREFIX.strip()}... line — "
            "delete the duplicates, leaving exactly one"
        )
    value_at = start + len(STAMP_PREFIX)
    end = text.find(STAMP_SUFFIX, value_at)
    if end < 0:
        raise ValueError(f"{STAMP_DRIVER} stamp literal is unterminated")
    return value_at, end


def read_stamp(text: str) -> str:
    """The stamp currently written into the module text."""
    a, b = _stamp_line_bounds(text)
    return text[a:b]


def compute_stamp(text: str) -> str:
    """The stamp the module text SHOULD carry: a digest of itself, stamp masked."""
    a, b = _stamp_line_bounds(text)
    masked = text[:a] + STAMP_PLACEHOLDER + text[b:]
    return hashlib.sha256(masked.encode("utf-8")).hexdigest()[:STAMP_LEN]


def restamp(base: Path) -> tuple[str, bool]:
    """Write the current content stamp into the stamped driver.

    Returns (stamp, changed). Idempotent: a second run is a no-op.
    """
    src = base / STAMP_DRIVER
    if not src.exists():
        raise FileNotFoundError(
            f"{src} not found — run: sync-deck-drivers.py materialize"
        )
    text = src.read_text(encoding="utf-8")
    want = compute_stamp(text)
    if read_stamp(text) == want:
        return want, False
    a, b = _stamp_line_bounds(text)
    src.write_text(text[:a] + want + text[b:], encoding="utf-8")
    return want, True


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


def export_stamped_driver(base: Path, dest_dir: Path) -> Path:
    """Copy RunDeckOps.bas into dest_dir (materializing it first). Returns the path.

    Idempotent: an identical copy already there is left alone.
    """
    materialize(base)
    src = base / STAMP_DRIVER
    if not src.exists():
        raise FileNotFoundError(
            f"{src} not found and no {STAMP_DRIVER}{MIRROR_SUFFIX} mirror to "
            "restore it from — reinstall the plugin"
        )
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / STAMP_DRIVER
    if not dest.exists() or dest.read_bytes() != src.read_bytes():
        shutil.copyfile(src, dest)
    return dest


def regenerate_mirrors(base: Path) -> list[Path]:
    """Rewrite `.txt` mirrors from the real drivers. Returns the mirrors changed.

    Stamps the stamped driver first, so a mirror never carries a stale stamp.
    """
    written: list[Path] = []
    if (base / STAMP_DRIVER).exists():
        restamp(base)
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
    src = base / STAMP_DRIVER
    if src.exists():
        text = src.read_text(encoding="utf-8")
        try:
            have, want = read_stamp(text), compute_stamp(text)
        except ValueError as e:
            problems.append(str(e))
        else:
            if have != want:
                problems.append(
                    f"{STAMP_DRIVER} content stamp is stale ({have} != {want}) — "
                    "run: sync-deck-drivers.py mirror"
                )
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Keep deck-ops .bas/.applescript drivers shippable past tessl's extension filter."
    )
    ap.add_argument(
        "mode", choices=("materialize", "mirror", "stamp", "export", "check")
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="materialize: overwrite existing real drivers (refresh after a plugin update)",
    )
    ap.add_argument(
        "--to",
        type=Path,
        help="export: the directory to copy RunDeckOps.bas into (required for export)",
    )
    ap.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="the scripts dir holding the drivers (default: this script's dir)",
    )
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

    if args.mode == "export":
        if args.to is None:
            print(
                "ERROR: export needs --to DIR — the directory to copy "
                f"{STAMP_DRIVER} into, e.g. <vault>/.deckops",
                file=sys.stderr,
            )
            return 2
        try:
            dest = export_stamped_driver(base, args.to.expanduser())
        except (FileNotFoundError, OSError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(json.dumps({"exported": str(dest)}))
        return 0

    if args.mode == "stamp":
        try:
            stamp, changed = restamp(base)
        except (FileNotFoundError, ValueError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"stamp: {stamp}" + ("" if changed else " (already current)"))
        return 0

    if args.mode == "mirror":
        try:
            written = regenerate_mirrors(base)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
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
