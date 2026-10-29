#!/usr/bin/env python3
"""Atomically replace one file with another, refusing a directory target.

Usage:
    atomic-replace.py <src> <dst>

Moves src over dst with os.replace, which on POSIX is rename(2): afterwards
dst holds either its previous content or all of src, never a partial file.
src and dst must be on one filesystem; inject-notes.sh creates src beside dst.
A dst that is a directory, or a symlink to one, is refused; rename(2) also
refuses a directory that appears between that check and the rename.

Exit 0 on success. Exit 1 prints `ERROR: ...` with the repair on stderr and
leaves both paths as they were. Exit 2 is a usage error.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def replace(src: Path, dst: Path) -> None:
    """Rename src onto dst. Raises ValueError with the repair on failure."""
    if dst.is_dir():
        raise ValueError(
            f"{dst} is a directory, so nothing was delivered — pass the path of "
            "the deck file to write"
        )
    try:
        os.replace(src, dst)
    except IsADirectoryError as exc:
        raise ValueError(
            f"{dst} became a directory before the rename, so nothing was "
            "delivered — remove or rename that directory and re-run"
        ) from exc
    except OSError as exc:
        raise ValueError(
            f"cannot rename {src} to {dst} ({exc.strerror}), so {dst} is unchanged "
            "— make its folder writable and re-run"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: atomic-replace.py <src> <dst>", file=sys.stderr)
        return 2
    try:
        replace(Path(args[0]), Path(args[1]))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
