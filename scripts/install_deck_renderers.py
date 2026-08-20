#!/usr/bin/env python3
"""Install the pinned markdown-deck renderers for CI, and cache what it can.

Four tools render the four markdown deck flavors, and none of them is a Python
package: a Rust binary from a GitHub release, and three npm CLIs, one of which
drags a headless browser behind it. Left uninstalled, the renderer's tests
could only ever drive stand-ins, and `ci-safety` Install, Don't Skip says
install the tool instead.

Everything here is pinned. `--pin-digest` prints a hash of the whole pin set so
the workflow can key its cache on it: a renewed pin misses the cache and
reinstalls, an edited comment does not. Both install paths are idempotent
against a restored cache — a present binary at the pinned version is left
alone, which is what makes a cache hit cheap rather than merely quiet.

Every command goes through an injected runner, so the sequence that does the
work is assertable without a network or a node. Reads of the machine's own
state are direct, since they inspect rather than change it.

Stdout is one JSON object naming how each renderer was satisfied. Exit 0 on
success, 1 when an install failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path


# presenterm ships prebuilt release binaries; the checksum is the one published
# beside the asset. No Dependabot ecosystem tracks a GitHub release referenced
# from a script, so the renewal mechanism is stated here rather than delegated:
# renew quarterly, or when a presenterm behavior this repo depends on changes,
# by reading the latest release and bumping both literals together.
#
#   gh api repos/mfontanini/presenterm/releases/latest --jq .tag_name
#   curl -sL <asset-url>.sha512
PRESENTERM_VERSION = "0.16.1"
PRESENTERM_ASSET = f"presenterm-{PRESENTERM_VERSION}-x86_64-unknown-linux-gnu.tar.gz"
PRESENTERM_URL = (
    "https://github.com/mfontanini/presenterm/releases/download/"
    f"v{PRESENTERM_VERSION}/{PRESENTERM_ASSET}"
)
PRESENTERM_SHA512 = (
    "9b019161384fb88ecc2eeebc03ab4cf414128e64451269c7f272468c0bfb2db8"
    "beb52062494b8d3ebed8cf5662f8dab62a6ec4fb6e81c1529a9d794150cf13b0"
)

# The three npm CLIs, exact. `playwright-chromium` is not a renderer: Slidev's
# PDF export requires it, and its postinstall is what puts a browser on the
# runner — which Marp and reveal-md then find too. Renewal is the same manual
# quarterly read as presenterm's; no scanner tracks a version baked into a
# script.
#
#   npm view <package> version
NPM_PINS = (
    "@slidev/cli@52.19.1",
    "@marp-team/marp-cli@4.5.0",
    "reveal-md@6.1.4",
    "playwright-chromium@1.58.1",
)
# reveal-md 6.1.4 declares `node: ^18.18.0 || ^20.9.0 || ^22.0.0`. The workflow
# pins the runner's node; this literal exists so a drift between the two fails
# a test rather than a CI run.
REQUIRED_NODE_MAJOR = 22

DOWNLOAD_TIMEOUT_SEC = 300
INSTALL_TIMEOUT_SEC = 900
RENDERER_SUBDIR = "deck-renderers"

Runner = Callable[[Sequence[str], int], int]


def _run(command: Sequence[str], timeout: int) -> int:
    """Run one command, letting its output reach the job log."""
    try:
        return subprocess.run(list(command), timeout=timeout, check=False).returncode
    except subprocess.TimeoutExpired:
        print(
            f"install_deck_renderers.py: {command[0]} exceeded {timeout}s",
            file=sys.stderr,
        )
        return 124
    except OSError as exc:
        # An absent `curl`, `tar` or `npm` is a runner-image problem, and the
        # caller turns a non-zero exit into a named install failure. Letting
        # this escape would replace that with a traceback.
        print(
            f"install_deck_renderers.py: cannot run {command[0]}: "
            f"{exc.strerror or exc}",
            file=sys.stderr,
        )
        return 127


def pin_digest() -> str:
    """Return a stable hash of every pin, for the workflow's cache key."""
    material = "\n".join(
        (
            PRESENTERM_VERSION,
            PRESENTERM_SHA512,
            *NPM_PINS,
            str(REQUIRED_NODE_MAJOR),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _sha512(path: Path) -> str:
    digest = hashlib.sha512()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def install_presenterm(root: Path, run: Runner) -> str:
    """Put the pinned presenterm binary in `root/bin`, or leave a cached one."""
    binary = root / "bin" / "presenterm"
    if binary.is_file():
        return "cached"
    binary.parent.mkdir(parents=True, exist_ok=True)
    archive = root / PRESENTERM_ASSET
    if run(
        ["curl", "-fL", "--retry", "3", "--output", str(archive), PRESENTERM_URL],
        DOWNLOAD_TIMEOUT_SEC,
    ):
        raise InstallFailure(f"could not download {PRESENTERM_URL}")
    observed = _sha512(archive)
    if observed != PRESENTERM_SHA512:
        raise InstallFailure(
            f"{PRESENTERM_ASSET} checksum is {observed}, expected "
            f"{PRESENTERM_SHA512} — the release asset changed under the pin"
        )
    if run(
        ["tar", "-xzf", str(archive), "-C", str(binary.parent), "presenterm"],
        DOWNLOAD_TIMEOUT_SEC,
    ):
        raise InstallFailure(f"could not extract presenterm from {PRESENTERM_ASSET}")
    if not binary.is_file():
        raise InstallFailure(
            f"{PRESENTERM_ASSET} extracted without a `presenterm` binary — the "
            "release layout changed under the pin"
        )
    binary.chmod(0o755)
    archive.unlink()
    return "downloaded"


def install_npm_renderers(root: Path, run: Runner) -> str:
    """Install the pinned npm CLIs under `root/npm`, or leave a cached tree."""
    prefix = root / "npm"
    if (prefix / "node_modules" / ".bin" / "slidev").exists():
        return "cached"
    prefix.mkdir(parents=True, exist_ok=True)
    if run(
        [
            "npm",
            "install",
            "--prefix",
            str(prefix),
            "--no-fund",
            "--no-audit",
            *NPM_PINS,
        ],
        INSTALL_TIMEOUT_SEC,
    ):
        raise InstallFailure(f"npm install failed for {', '.join(NPM_PINS)}")
    return "installed"


class InstallFailure(RuntimeError):
    """One renderer could not be installed at its pinned version."""


def path_entries(root: Path) -> list[str]:
    """Return the directories a caller must put on PATH, in order."""
    return [str(root / "bin"), str(root / "npm" / "node_modules" / ".bin")]


def execute(workspace: Path, run: Runner) -> dict[str, object]:
    """Install every renderer under `workspace` and report how each was met."""
    root = workspace / RENDERER_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "ok": True,
        "pin_digest": pin_digest(),
        "presenterm": install_presenterm(root, run),
        "npm": install_npm_renderers(root, run),
        "path_entries": path_entries(root),
    }
    return report


def _export_path(entries: Sequence[str]) -> None:
    """Append the renderer directories to the job's PATH, when there is one."""
    github_path = os.environ.get("GITHUB_PATH")
    if not github_path:
        return
    with open(github_path, "a", encoding="utf-8") as stream:
        for entry in entries:
            stream.write(f"{entry}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument(
        "workspace",
        nargs="?",
        type=Path,
        help="directory to install under; required unless --pin-digest",
    )
    parser.add_argument(
        "--pin-digest",
        action="store_true",
        help="print the cache key for the current pin set and exit",
    )
    args = parser.parse_args(argv)
    if args.pin_digest:
        print(pin_digest())
        return 0
    if args.workspace is None:
        parser.error("workspace is required unless --pin-digest is passed")
    try:
        report = execute(args.workspace, _run)
    except InstallFailure as exc:
        print(f"install_deck_renderers.py: {exc}", file=sys.stderr)
        print(json.dumps({"ok": False, "reason": str(exc)}, sort_keys=True))
        return 1
    _export_path(report["path_entries"])  # type: ignore[arg-type]
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
