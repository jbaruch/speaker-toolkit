#!/usr/bin/env python3
"""Decide which tree of a shownotes site checkout a scan should read.

A shownotes site is published from its default branch, but the configured path is a
working checkout that may sit anywhere: on a feature branch, detached, or behind
`origin`. Reading its working tree then reports every talk published since as nothing
at all, which reads as "no new talks". So a scan reads the working tree only when the
checkout is on the default branch and holds everything published. Otherwise it reads
a snapshot of `origin/<default>`, which disturbs nothing in the speaker's checkout.

`fetch` refreshes the remote-tracking ref first. It touches neither the working tree
nor any local branch. A failed fetch is a warning and the last-fetched commit is used,
since talks published before it are still worth scanning.

Decisions, in the report's `state` field:

- `not_git`: git says the root isn't in a work tree, so its files are all there is.
- `git_unavailable`: git didn't answer, so this may be a checkout on any branch;
  working tree, with a warning.
- `no_default_branch`: `origin/HEAD` isn't set; working tree, with a warning.
- `default_branch`: on the default branch and holding everything published; working
  tree, uncommitted edits included.
- `published_snapshot`: anything else; `origin/<default>` at `scanned_commit`.
"""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Generator

# A fetch that outlives this is treated like any other failed fetch.
GIT_TIMEOUT_SECONDS = 60
SYMLINK_MODE = "120000"
REGULAR_MODES = frozenset({"100644", "100755"})
NOT_A_REPOSITORY = b"not a git repository"


class ShownotesCheckoutError(ValueError):
    """The published tree can't be read; the message says what to do."""


@dataclass(frozen=True)
class CheckoutDecision:
    state: str
    branch: str | None = None
    default_branch: str | None = None
    scanned_commit: str | None = None
    fetch: str = "not_run"
    warnings: tuple[str, ...] = ()

    def as_report(self) -> dict[str, object]:
        return {
            "state": self.state,
            "branch": self.branch,
            "default_branch": self.default_branch,
            "scanned_commit": self.scanned_commit,
            "fetch": self.fetch,
        }


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes] | None:
    """Run git in `root`; None when git is missing or the call timed out."""
    try:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            # LC_ALL pins the one message this module reads, in decide_checkout.
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"},
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_output(root: Path, *arguments: str) -> str | None:
    """Stripped stdout of a git call that succeeded, else None."""
    result = _git(root, *arguments)
    if result is None or result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace").strip()


def decide_checkout(root: Path) -> CheckoutDecision:
    probe = _git(root, "rev-parse", "--is-inside-work-tree")
    if probe is None or (
        probe.returncode != 0 and NOT_A_REPOSITORY not in probe.stderr
    ):
        # Missing git, a timeout or a refusal such as "dubious ownership". This may be
        # a real checkout on any branch, so it can't read as "not a checkout".
        detail = (
            "git is missing or timed out"
            if probe is None
            else probe.stderr.decode("utf-8", errors="replace").strip()
        )
        return CheckoutDecision(
            state="git_unavailable",
            warnings=(
                f"could not ask git about {root} ({detail}), so the scan read the "
                "working tree; if that's a checkout off the default branch, talks "
                "published there are invisible. Fix git access and rescan.",
            ),
        )
    if probe.returncode != 0 or probe.stdout.strip() != b"true":
        return CheckoutDecision(state="not_git")

    remote_head = _git_output(
        root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"
    )
    head = _git_output(root, "rev-parse", "--abbrev-ref", "HEAD")
    branch = None if head in (None, "HEAD") else head
    if remote_head is None:
        return CheckoutDecision(
            state="no_default_branch",
            branch=branch,
            warnings=(
                f"{root} has no origin/HEAD, so its default branch is unknown and the "
                "scan read the working tree; talks published elsewhere are invisible. "
                "Run `git remote set-head origin --auto` there and rescan.",
            ),
        )
    default_branch = remote_head.removeprefix("origin/")

    warnings: list[str] = []
    fetched = _git(root, "fetch", "--quiet", "origin", default_branch)
    fetch = "ok" if fetched is not None and fetched.returncode == 0 else "failed"
    if fetch == "failed":
        warnings.append(
            f"could not fetch origin/{default_branch} in {root}; the scan used the "
            "last fetched commit, so talks published since are invisible. Fix the "
            "remote and rescan."
        )

    published = f"refs/remotes/origin/{default_branch}"
    commit = _git_output(root, "rev-parse", "--verify", f"{published}^{{commit}}")
    if commit is None:
        raise ShownotesCheckoutError(
            f"{root} has no {published}; run `git fetch origin` there and rescan"
        )
    contains = _git(root, "merge-base", "--is-ancestor", published, "HEAD")
    if branch == default_branch and contains is not None and contains.returncode == 0:
        state = "default_branch"
        commit = None
    else:
        state = "published_snapshot"
    return CheckoutDecision(
        state=state,
        branch=branch,
        default_branch=default_branch,
        scanned_commit=commit,
        fetch=fetch,
        warnings=tuple(warnings),
    )


def _write_snapshot(root: Path, commit: str, talks_subdir: str, target: Path) -> None:
    """Write the top level of `talks_subdir` at `commit` into `target`.

    A symlink is recreated rather than followed, so the scanner refuses it exactly as
    it refuses one in a working tree.
    """
    # ls-tree reads this relative to `root`, which may be a repository subdirectory.
    tree_path = f"{talks_subdir}/"
    listing = _git(root, "ls-tree", "-z", commit, "--", tree_path)
    if listing is None or listing.returncode != 0:
        raise ShownotesCheckoutError(
            f"cannot list {tree_path} at {commit} in {root}; check that the checkout "
            "is healthy with `git status` and rescan"
        )
    if not listing.stdout:
        raise ShownotesCheckoutError(
            f"{tree_path} doesn't exist at the default branch's commit {commit}; "
            "correct talks_subdir, or publish the talks, and rescan"
        )
    for item in listing.stdout.split(b"\0"):
        if not item:
            continue
        metadata, _, raw_path = item.partition(b"\t")
        mode, _kind, blob = metadata.decode("ascii").split()
        name = raw_path.decode("utf-8", errors="surrogateescape").rsplit("/", 1)[-1]
        if mode not in REGULAR_MODES and mode != SYMLINK_MODE:
            continue
        content = _git(root, "cat-file", "blob", blob)
        if content is None or content.returncode != 0:
            raise ShownotesCheckoutError(
                f"cannot read {name} at {commit} in {root}; check that the checkout "
                "is healthy with `git status` and rescan"
            )
        destination = target / name
        if mode == SYMLINK_MODE:
            destination.symlink_to(os.fsdecode(content.stdout))
        else:
            destination.write_bytes(content.stdout)


@contextmanager
def published_talks_directory(
    root: Path,
    talks_subdir: str,
    decision: CheckoutDecision,
) -> Generator[Path | None]:
    """Yield the snapshot directory for a `published_snapshot`, else None."""
    if decision.state != "published_snapshot" or decision.scanned_commit is None:
        yield None
        return
    with TemporaryDirectory(prefix="shownotes-published-") as directory:
        # The scanner refuses symlinked ancestors, and macOS's temp path has one.
        target = Path(directory).resolve()
        _write_snapshot(root, decision.scanned_commit, talks_subdir, target)
        yield target
