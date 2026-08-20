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
import shutil
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

# The npm side lives in a committed manifest and lock file, installed with
# `npm ci`: exact top-level versions pin four packages and leave the several
# thousand beneath them free to move between runs, which is not a pin at all.
# `playwright-chromium` is not a renderer — Slidev's PDF export requires it,
# and its postinstall is what puts a browser on the runner, which Marp and
# reveal-md then find too.
#
# Renewal is the same manual quarterly read as presenterm's; no scanner tracks
# these. Bump a version in the manifest, re-run `npm install
# --package-lock-only` beside it, and commit both.
NPM_MANIFEST_DIR = Path(__file__).resolve().parent / "deck-renderers"
NPM_MANIFEST = NPM_MANIFEST_DIR / "package.json"
NPM_LOCKFILE = NPM_MANIFEST_DIR / "package-lock.json"
# reveal-md 6.1.4 declares `node: ^18.18.0 || ^20.9.0 || ^22.0.0`. The workflow
# pins the runner's node; this literal exists so a drift between the two fails
# a test rather than a CI run.
REQUIRED_NODE_MAJOR = 22

DOWNLOAD_TIMEOUT_SEC = 300
INSTALL_TIMEOUT_SEC = 900
SYSCTL_TIMEOUT_SEC = 60
RENDERER_SUBDIR = "deck-renderers"

# Ubuntu 23.10 restricts unprivileged user namespaces through AppArmor, and a
# bundled chromium that cannot open its sandbox dies with `No usable sandbox!`
# before rendering a page. reveal-md hits it; Slidev's playwright build does
# not. Chromium suggests `--no-sandbox`, which would ship a weakened browser to
# every operator to work around a property of one CI image — lifting the
# restriction on the runner keeps the renderer sandboxed everywhere else.
APPARMOR_USERNS_SYSCTL = "kernel.apparmor_restrict_unprivileged_userns"
APPARMOR_USERNS_PATH = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")

Runner = Callable[[Sequence[str], int], int]


def _run(command: Sequence[str], timeout: int) -> int:
    """Run one command, relaying its output to stderr.

    Not inherited stdout: this script's stdout carries one JSON object and
    nothing else, and `npm install` alone would put hundreds of lines in front
    of it. The output still reaches the job log, on the stream that carries
    diagnostics.
    """
    try:
        completed = subprocess.run(
            list(command),
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
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
    if completed.stdout:
        sys.stderr.write(completed.stdout.decode("utf-8", "replace"))
    return completed.returncode


def npm_pins() -> tuple[str, ...]:
    """Return the manifest's top-level dependencies as `name@version` strings."""
    manifest = json.loads(NPM_MANIFEST.read_text(encoding="utf-8"))
    dependencies = manifest.get("dependencies", {})
    return tuple(f"{name}@{version}" for name, version in sorted(dependencies.items()))


def pin_digest() -> str:
    """Return a stable hash of every pin, for the workflow's cache key.

    The lock file's own bytes, not the manifest's four lines: a transitive
    version that moves under an unchanged manifest is a different install and
    must miss the cache.
    """
    material = "\n".join(
        (
            PRESENTERM_VERSION,
            PRESENTERM_SHA512,
            hashlib.sha256(NPM_LOCKFILE.read_bytes()).hexdigest(),
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
    # Extract the whole archive and go looking, rather than naming a member
    # path: the asset nests its binary under a version-stamped directory
    # (`presenterm-0.16.1/presenterm`), and a `tar` told to extract
    # `presenterm` fails with `Not found in archive`. Searching survives that
    # layout changing again; an archive with no binary anywhere still fails.
    staging = root / "presenterm-extract"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    if run(["tar", "-xzf", str(archive), "-C", str(staging)], DOWNLOAD_TIMEOUT_SEC):
        raise InstallFailure(f"could not extract {PRESENTERM_ASSET}")
    extracted = next(
        (path for path in sorted(staging.rglob("presenterm")) if path.is_file()),
        None,
    )
    if extracted is None:
        raise InstallFailure(
            f"{PRESENTERM_ASSET} holds no `presenterm` binary — the release "
            "layout changed under the pin"
        )
    extracted.replace(binary)
    binary.chmod(0o755)
    shutil.rmtree(staging)
    archive.unlink()
    return "downloaded"


def install_npm_renderers(root: Path, run: Runner) -> str:
    """Install the locked npm CLIs under `root/npm`, or leave a cached tree."""
    prefix = root / "npm"
    if (prefix / "node_modules" / ".bin" / "slidev").exists():
        return "cached"
    prefix.mkdir(parents=True, exist_ok=True)
    # `npm ci` installs the lock file exactly and refuses a manifest the lock
    # disagrees with, so both are copied beside each other in the prefix.
    for source in (NPM_MANIFEST, NPM_LOCKFILE):
        try:
            shutil.copyfile(source, prefix / source.name)
        except OSError as exc:
            raise InstallFailure(
                f"cannot stage {source.name} in {prefix}: {exc.strerror or exc}"
            ) from exc
    if run(
        ["npm", "ci", "--prefix", str(prefix), "--no-fund", "--no-audit"],
        INSTALL_TIMEOUT_SEC,
    ):
        raise InstallFailure(
            f"npm ci failed for {', '.join(npm_pins())} — see "
            f"{NPM_LOCKFILE} for the locked graph"
        )
    return "installed"


class InstallFailure(RuntimeError):
    """One renderer could not be installed at its pinned version."""


def path_entries(root: Path) -> list[str]:
    """Return the directories a caller must put on PATH, in order."""
    return [str(root / "bin"), str(root / "npm" / "node_modules" / ".bin")]


def permit_browser_sandbox(run: Runner) -> str:
    """Let a bundled chromium open its sandbox, where the kernel forbids it.

    Runs on every invocation, cache hit included: this is kernel state, and a
    restored install directory carries none of it. A failure here is reported
    and not fatal — the render that needs it fails loudly with chromium's own
    message, which names this exact restriction.
    """
    try:
        current = APPARMOR_USERNS_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "not_applicable"
    if current == "0":
        return "already_permitted"
    if run(
        ["sudo", "sysctl", "-w", f"{APPARMOR_USERNS_SYSCTL}=0"],
        SYSCTL_TIMEOUT_SEC,
    ):
        print(
            "install_deck_renderers.py: warning: could not clear "
            f"{APPARMOR_USERNS_SYSCTL} (currently {current}); a bundled "
            "chromium will fail with `No usable sandbox!`",
            file=sys.stderr,
        )
        return "failed"
    return "permitted"


def execute(workspace: Path, run: Runner) -> dict[str, object]:
    """Install every renderer under `workspace` and report how each was met."""
    root = workspace / RENDERER_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "ok": True,
        "pin_digest": pin_digest(),
        "presenterm": install_presenterm(root, run),
        "npm": install_npm_renderers(root, run),
        "browser_sandbox": permit_browser_sandbox(run),
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
        print(json.dumps({"pin_digest": pin_digest()}, sort_keys=True))
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
