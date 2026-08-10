#!/usr/bin/env python3
"""Persistent sibling lock shared by every writer of one owner file.

A writer that checks a target's bytes and then renames a replacement over it
has performed two operations, not one. Between them another writer can install
its own generation, and the rename overwrites it while reporting success. No
POSIX rename is conditional, so the compare-and-swap has to be closed by
excluding the other writers instead: every writer of the same target takes this
lock, and the whole check-stage-recheck-install sequence runs inside it.

The lock is a persistent `.<target>.lock` sibling, flocked exclusively. It is
never removed: unlinking it lets a second process create and lock a different
inode under the same name, which is two writers holding "the" lock at once.

Cooperative is the exact claim. A human editor holds no lock, so the owner
still rechecks the target's bytes immediately before installing — the lock
serializes the toolkit's writers, the recheck catches everyone else.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import fcntl
import os
from pathlib import Path
import stat
from typing import Iterator


class CooperativeLockError(Exception):
    """The cooperative lock could not be opened, acquired, or trusted."""


@dataclass
class CooperativeLock:
    """One acquired lock plus cleanup warnings collected after the body.

    Release failures are warnings, never exceptions: the guarded work already
    happened, and turning its cleanup into a failure would misreport it.
    """

    descriptor: int
    path: Path
    warnings: list[str] = field(default_factory=list)


def lock_path_for(path: str | os.PathLike[str]) -> Path:
    """Return the persistent cooperative lock shared by every toolkit writer."""
    target = Path(path).expanduser().absolute()
    return target.parent / f".{target.name}.lock"


def _identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


@contextmanager
def exclusive_file_lock(path: Path, *, label: str) -> Iterator[CooperativeLock]:
    """Hold the exclusive cooperative lock for ``path`` across the body.

    ``label`` names the guarded artifact in every diagnostic, so a caller's own
    error type can carry the message unchanged.
    """
    lock_path = lock_path_for(path)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise CooperativeLockError(
            f"cannot open cooperative {label} lock {lock_path}: {exc}"
        ) from exc
    acquired = False
    initialized = False
    try:
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise CooperativeLockError(
                    f"cooperative {label} lock {lock_path} must be one regular file"
                )
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            acquired = True
            try:
                visible = lock_path.lstat()
            except OSError as exc:
                raise CooperativeLockError(
                    f"cannot verify cooperative {label} lock {lock_path}: {exc}"
                ) from exc
            locked = os.fstat(descriptor)
            if (
                stat.S_ISLNK(visible.st_mode)
                or not stat.S_ISREG(visible.st_mode)
                or _identity(visible) != _identity(locked)
                or locked.st_nlink != 1
            ):
                raise CooperativeLockError(
                    f"cooperative {label} lock {lock_path} changed while locking; "
                    "restore the persistent regular lock file and retry"
                )
        except OSError as exc:
            raise CooperativeLockError(
                f"cannot acquire {label} lock through {lock_path}: {exc}"
            ) from exc
        initialized = True
    finally:
        if not initialized:
            try:
                os.close(descriptor)
            except OSError:
                # The acquisition failure is the diagnostic; a close failure on
                # top of it has nowhere to go and must not mask it.
                pass

    lock = CooperativeLock(descriptor=descriptor, path=lock_path, warnings=[])
    try:
        yield lock
    finally:
        if acquired:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError as exc:
                lock.warnings.append(
                    f"could not unlock cooperative {label} lock {lock_path}: {exc}"
                )
        try:
            os.close(descriptor)
        except OSError as exc:
            lock.warnings.append(
                f"could not close cooperative {label} lock {lock_path}: {exc}"
            )
