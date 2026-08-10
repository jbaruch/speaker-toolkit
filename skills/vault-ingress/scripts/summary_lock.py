#!/usr/bin/env python3
"""The one writer lock for ``rhetoric-style-summary.md``.

Two toolkit writers replace parts of this file: the owner status block
(``render-vault-status.py``) and the Section 15 pattern-history block
(``section15_pattern_history.py``). Both read the whole file, splice their own
block, and rename the result over the target — so two writers that do not
exclude each other silently drop one of the two updates, whichever renamed
first.

They exclude each other through this seam rather than each naming the lock
itself. A label is diagnostics; agreement on the lock is the contract, and a
third writer that imports this cannot invent its own.

Cooperative is the exact claim: a human editing the summary holds no lock, so
each writer still rechecks the target's bytes immediately before its rename.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from cooperative_lock import CooperativeLock, exclusive_file_lock

SUMMARY_BASENAME = "rhetoric-style-summary.md"

# Names the summary in every cooperative-lock diagnostic.
SUMMARY_LOCK_LABEL = "rhetoric-summary"


@contextmanager
def rhetoric_summary_lock(summary_path: Path) -> Iterator[CooperativeLock]:
    """Hold the summary's exclusive writer lock for the whole critical section.

    Raises ``CooperativeLockError``; each writer classifies that in its own
    terms. The lock file is the target's persistent sibling, so writers that
    pass different labels still serialize on the same inode.
    """
    with exclusive_file_lock(summary_path, label=SUMMARY_LOCK_LABEL) as lock:
        yield lock
