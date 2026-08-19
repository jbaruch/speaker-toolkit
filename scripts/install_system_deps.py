#!/usr/bin/env python3
"""Install the CI system dependencies without paying for the network twice.

Two separate failures live here, and the fix for one is not the fix for the
other.

The first: the job already caches apt's downloaded `.deb` archives, and the
cache hits — 185 MiB restored — but the step ran `apt-get update` ahead of every
install, so each run still fetched the package indices from a mirror. The bytes
were cached; the index was not, and the index fetch is what hung. Caching the
indices beside the archives lets a cache hit install with `--no-download`,
touching no mirror at all.

The second: when the mirror path is taken and the runner cannot reach anything,
four mirrors times a 300s `apt-get update` timeout burned 20 minutes before the
job failed. Canonical, kernel.org and Oregon State do not go dark in lockstep,
so four identical timeouts mean the runner's side of the connection, not four
outages. A cheap HEAD of each mirror's InRelease separates the two: an
unreachable mirror is skipped in seconds, and every mirror unreachable fails the
step immediately naming that as the diagnosis rather than after 20 minutes of
silence.

Every command goes through an injected runner, so the sequence that does the
work is assertable without a runner, sudo, or a network. Reads of the machine's
own state — whether a source file exists, what the cache holds, the release
codename — and the staging write are direct, since they inspect rather than
change the system.

Stdout is one JSON object naming how the install was satisfied and which
mirrors were skipped. Exit 0 on success, 1 when no path installed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

# ffmpeg drives the video-slide-extraction tests; libreoffice-impress drives the
# PPTX->PDF export tests; tesseract drives OCR of baked-in picture text in
# pptx-extraction. Source-video evidence tests require ffmpeg/ffprobe and fail if
# either is absent. OCR unit tests inject a fake engine; integration tests skipif
# tesseract is missing.
#
# Pinned exactly, per `dependency-management` Pinning. No scanner tracks an apt
# version baked into a script, so the renewal mechanism is stated here rather
# than delegated: ffmpeg and tesseract sit in the static `noble` pocket and move
# only at a release rebuild, while libreoffice-impress ships from
# `noble-updates` and is superseded on Ubuntu's security cadence — roughly
# monthly. Ubuntu's archive serves only the current version of each, so a
# superseded pin fails the install loudly rather than silently drifting. Renew by
# reading the current versions and bumping the literals here:
#
#   https://people.canonical.com/~ubuntu-archive/madison.cgi
#     ?package=ffmpeg+libreoffice-impress+tesseract-ocr
#     &table=ubuntu&s=noble,noble-updates,noble-security&a=amd64&text=on
PACKAGES = (
    "ffmpeg=7:6.1.1-3ubuntu5",
    "libreoffice-impress=4:24.2.7-0ubuntu0.24.04.6",
    "tesseract-ocr=5.3.4-1build5",
)

# Ordered fastest-first, then genuinely independent. The first two are
# Canonical's own infrastructure and fail together when Canonical is degraded —
# which is not a fallback at all, so the list continues onto mirrors run by other
# organisations entirely.
#
# A third-party mirror cannot serve tampered packages: apt verifies each Release
# against the ubuntu-archive-keyring signature, so integrity comes from the
# signature, not from who hosts the bytes. Full Ubuntu mirrors carry the
# `-security` suites too, so one host serves both pockets.
MIRRORS = (
    (
        "http://azure.archive.ubuntu.com/ubuntu",
        "http://azure.archive.ubuntu.com/ubuntu",
    ),
    ("http://archive.ubuntu.com/ubuntu", "http://security.ubuntu.com/ubuntu"),
    (
        "http://mirrors.edge.kernel.org/ubuntu",
        "http://mirrors.edge.kernel.org/ubuntu",
    ),
    ("http://ubuntu.osuosl.org/ubuntu", "http://ubuntu.osuosl.org/ubuntu"),
)

ARCHIVE_CACHE = Path("/tmp/apt-cache")
LIST_CACHE = Path("/tmp/apt-lists")
APT_LISTS = Path("/var/lib/apt/lists")
APT_SOURCES = Path("/etc/apt/sources.list")
APT_SOURCES_D = Path("/etc/apt/sources.list.d")
SOURCES_BACKUP = Path("/tmp/apt-src-orig")
APT_CONF = Path("/etc/apt/apt.conf.d/99ci")

# A HEAD of one index file, not a mirror sync — 20s is generous for a reachable
# host and cheap for an unreachable one.
PROBE_TIMEOUT_SEC = 20
# apt has effectively no default connection cap, which is the original hang.
UPDATE_TIMEOUT_SEC = 300
INSTALL_TIMEOUT_SEC = 600


# `APT::Keep-Downloaded-Packages` is what makes the archive cache exist at all:
# apt has discarded downloaded .debs after a successful install since 1.6, so the
# archive dir was empty when the post-step ran and no cache was ever written.
def apt_conf_body(archive_cache: Path) -> str:
    """apt's config, pointed at the archive dir the caller actually passed."""
    return (
        f'Dir::Cache::Archives "{archive_cache}";\n'
        'APT::Keep-Downloaded-Packages "true";\n'
        'Acquire::Retries "3";\n'
        'Acquire::http::Timeout "30";\n'
        'Acquire::https::Timeout "30";\n'
    )


Runner = Callable[[Sequence[str], int], int]


class SystemDepsError(RuntimeError):
    """A command with no recovery path failed."""


def require(run: Runner, command: Sequence[str], timeout: int) -> None:
    """Run a command whose failure leaves nothing sensible to continue into.

    A failed mkdir, copy or mirror rewrite is not a fallback signal — the apt
    call after it can still succeed against whatever state was already there and
    report the step green, which is how a cache that saved nothing looked
    identical to one that worked. Only the probe, the update and the install
    carry a recoverable failure, and those read their own status.
    """
    code = run(command, timeout)
    if code != 0:
        raise SystemDepsError(
            f"{' '.join(command)} exited {code}; the runner is not in the state "
            "the install needs — re-run the job, and if it repeats, inspect the "
            "step log for the failing command above this line"
        )


def run_command(command: Sequence[str], timeout: int) -> int:
    """Run one command, mapping a timeout to a non-zero code rather than a raise.

    A stall is the failure this whole script exists to bound, so it has to read
    as an ordinary failed command — a raise here would abort the fallback chain
    the caller is walking.
    """
    # Diagnostics go to stderr: stdout carries one JSON object and nothing else,
    # so a caller can parse it without stripping anything out first. The child's
    # own stdout is redirected there too — apt is chatty, it inherits this
    # process's streams by default, and its progress would otherwise land in the
    # middle of the report. Redirecting rather than capturing keeps the output
    # live, which is the whole point of it during a 300s stall.
    print(f"+ {' '.join(command)}", file=sys.stderr, flush=True)
    sys.stderr.flush()
    try:
        return subprocess.run(
            command, timeout=timeout, check=False, stdout=sys.stderr
        ).returncode
    except subprocess.TimeoutExpired:
        print(f"timed out after {timeout}s: {' '.join(command)}", file=sys.stderr)
        return 124


def configure_apt(
    run: Runner, staged_conf: Path, archive_cache: Path, list_cache: Path
) -> None:
    """Point apt's archive dir at the cached location and bound its timeouts.

    The config is staged where the runner can write and copied in with sudo,
    rather than piped through a root shell: the staged file is what the tests
    read back, and a heredoc into `sudo tee` is not inspectable.

    Every path here is the caller's, not the module constant. Taking the
    constant while accepting the argument made the parameter a lie — the caller
    redirected nothing and the write landed on the real machine anyway.
    """
    staged_conf.write_text(apt_conf_body(archive_cache))
    require(
        run, ["sudo", "mkdir", "-p", f"{archive_cache}/partial", str(list_cache)], 60
    )
    require(run, ["sudo", "chmod", "-R", "777", str(archive_cache)], 60)
    require(run, ["sudo", "cp", str(staged_conf), str(APT_CONF)], 60)


def cache_is_usable(archive_cache: Path, list_cache: Path) -> bool:
    """Report whether the restored cache can satisfy an offline install.

    Both halves are required and neither implies the other: archives without
    indices cannot be resolved, and indices without archives resolve to a
    download. A cache entry saved before this script existed holds only the
    archives, so the pair is checked rather than the cache-hit flag.
    """
    if not any(archive_cache.glob("*.deb")):
        return False
    return any(list_cache.glob("*Packages*"))


def restore_lists(run: Runner, list_cache: Path) -> None:
    """Put the cached package indices where apt reads them."""
    require(run, ["sudo", "mkdir", "-p", str(APT_LISTS)], 60)
    require(run, ["sudo", "cp", "-a", f"{list_cache}/.", f"{APT_LISTS}/"], 120)


def save_lists(run: Runner, list_cache: Path, archive_cache: Path) -> None:
    """Stage the indices and archives for the cache save, owned by the runner.

    actions/cache tars as the runner user, and apt leaves behind a root-owned
    `lock` and `partial/`. tar cannot read them, the save aborts, and it reports
    a WARNING — so the step goes green having cached nothing, which is how the
    empty archive cache stayed invisible for so long.
    """
    require(run, ["sudo", "rm", "-rf", str(list_cache)], 60)
    require(run, ["sudo", "mkdir", "-p", str(list_cache)], 60)
    require(run, ["sudo", "cp", "-a", f"{APT_LISTS}/.", f"{list_cache}/"], 120)
    require(
        run, ["sudo", "rm", "-rf", f"{list_cache}/partial", f"{list_cache}/lock"], 60
    )
    require(
        run,
        ["sudo", "rm", "-rf", f"{archive_cache}/partial", f"{archive_cache}/lock"],
        60,
    )
    require(
        run,
        ["sudo", "chown", "-R", _owner(), str(list_cache), str(archive_cache)],
        120,
    )


def _owner() -> str:
    return f"{os.getuid()}:{os.getgid()}"


def install_offline(run: Runner) -> bool:
    """Install strictly from the restored cache, contacting no mirror.

    `--no-download` fails rather than reaching for a missing package, which is
    the signal the caller falls through on: a runner image that gained or lost a
    preinstalled library leaves the cached set unable to satisfy the request, and
    that has to reach the mirror path instead of failing the job.
    """
    return (
        run(
            ["sudo", "-E", "apt-get", "install", "-y", "--no-download", *PACKAGES],
            INSTALL_TIMEOUT_SEC,
        )
        == 0
    )


def probe(run: Runner, host: str, suite: str) -> bool:
    """Report whether a host answers for one index file, in seconds not minutes."""
    url = f"{host}/dists/{suite}/InRelease"
    return (
        run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--fail",
                "--head",
                "--max-time",
                str(PROBE_TIMEOUT_SEC),
                url,
            ],
            PROBE_TIMEOUT_SEC + 10,
        )
        == 0
    )


def backup_sources(run: Runner, sources: Path, sources_d: Path) -> None:
    """Keep a pristine copy of the source lists.

    Each mirror attempt restores it before rewriting, so no rewrite ever reads
    already-rewritten state. A deb822-only runner image carries no
    `sources.list` at all, so each half is copied only when it exists — an
    unconditional copy would report a failure on a perfectly healthy runner.
    """
    require(run, ["sudo", "rm", "-rf", str(SOURCES_BACKUP)], 60)
    require(run, ["sudo", "mkdir", "-p", str(SOURCES_BACKUP)], 60)
    if sources.exists():
        require(run, ["sudo", "cp", "-a", str(sources), str(SOURCES_BACKUP)], 60)
    if sources_d.exists():
        require(run, ["sudo", "cp", "-a", str(sources_d), str(SOURCES_BACKUP)], 60)


def set_mirror(
    run: Runner,
    archive: str,
    security: str,
    workspace: Path,
    sources: Path,
    sources_d: Path,
) -> None:
    """Restore the pristine sources, then repoint them at one mirror pair.

    The rewrite is suite-aware and lives in scripts/apt_set_mirror.py with its
    own tests: a line-based rewrite cannot do it correctly, because Azure runners
    serve BOTH pockets from one host and deb822 binds a `URIs:` to the `Suites:`
    in its own stanza. It skips a path that does not exist, so both runner
    layouts pass the same argument list.
    """
    if sources.exists():
        require(
            run,
            ["sudo", "cp", "-a", f"{SOURCES_BACKUP}/sources.list", str(sources)],
            60,
        )
    if sources_d.exists():
        require(run, ["sudo", "rm", "-rf", str(sources_d)], 60)
        require(
            run,
            ["sudo", "cp", "-a", f"{SOURCES_BACKUP}/sources.list.d", str(sources_d)],
            60,
        )
    # Enumerated here rather than passed as `*.list` / `*.sources`. The shell
    # this replaced expanded those globs before apt_set_mirror.py ever saw them;
    # a literal glob reaches it as a path that does not exist, which it skips —
    # so every fallback rewrote nothing, silently, and each retry hit the same
    # mirror that had just failed.
    targets = [str(sources)] if sources.exists() else []
    targets += [
        str(path)
        for pattern in ("*.list", "*.sources")
        for path in sorted(sources_d.glob(pattern))
    ]
    if not targets:
        raise SystemDepsError(
            f"no apt source files found at {sources} or under {sources_d}; the "
            "runner image is not the Ubuntu one this step expects and no mirror "
            "fallback can work — re-run the job on a supported image"
        )
    require(
        run,
        [
            "sudo",
            "python3",
            str(workspace / "scripts" / "apt_set_mirror.py"),
            archive,
            security,
            *targets,
        ],
        120,
    )


def install_from_mirror(
    run: Runner,
    archive: str,
    security: str,
    workspace: Path,
    sources: Path,
    sources_d: Path,
) -> bool:
    """Update the index from one mirror and install against it."""
    set_mirror(run, archive, security, workspace, sources, sources_d)
    if run(["sudo", "-E", "apt-get", "update"], UPDATE_TIMEOUT_SEC) != 0:
        return False
    return (
        run(["sudo", "-E", "apt-get", "install", "-y", *PACKAGES], INSTALL_TIMEOUT_SEC)
        == 0
    )


def read_codename(os_release: Path) -> str:
    """Read the Ubuntu suite name the probe URL needs."""
    for line in os_release.read_text().splitlines():
        key, _, value = line.partition("=")
        if key == "VERSION_CODENAME":
            return value.strip().strip('"')
    raise ValueError(
        f"{os_release} names no VERSION_CODENAME; the runner image is not the "
        "Ubuntu one this step expects — pin the suite explicitly to proceed"
    )


def install(
    run: Runner,
    *,
    workspace: Path,
    codename: str,
    staged_conf: Path,
    archive_cache: Path = ARCHIVE_CACHE,
    list_cache: Path = LIST_CACHE,
    sources: Path = APT_SOURCES,
    sources_d: Path = APT_SOURCES_D,
) -> dict[str, object]:
    """Satisfy the dependencies from cache if possible, else from a mirror."""
    configure_apt(run, staged_conf, archive_cache, list_cache)

    if cache_is_usable(archive_cache, list_cache):
        restore_lists(run, list_cache)
        if install_offline(run):
            return {"installed": True, "source": "cache", "unreachable": []}
        print(
            "cached archives did not satisfy the install; falling back to a mirror",
            file=sys.stderr,
        )

    backup_sources(run, sources, sources_d)
    unreachable: list[str] = []
    skipped = 0
    for archive, security in MIRRORS:
        # Both hosts of the pair, because apt fetches both and a pair whose
        # security host is dead still burns the full update timeout. Only the
        # Canonical pair has a distinct one; the others serve both pockets from
        # one host and are probed once. The suites differ with the host —
        # security.ubuntu.com carries `<codename>-security` and does not serve
        # the plain suite, so probing it for that would report a healthy host as
        # unreachable.
        hosts = [(archive, codename)]
        if security != archive:
            hosts.append((security, f"{codename}-security"))
        unresponsive = [host for host, suite in hosts if not probe(run, host, suite)]
        if unresponsive:
            unreachable.extend(unresponsive)
            skipped += 1
            print(
                f"{', '.join(unresponsive)} did not answer a HEAD of the index; "
                "skipping this mirror",
                file=sys.stderr,
            )
            continue
        if install_from_mirror(run, archive, security, workspace, sources, sources_d):
            save_lists(run, list_cache, archive_cache)
            return {"installed": True, "source": archive, "unreachable": unreachable}
        print(
            f"apt failed against {archive} / {security}; trying the next mirror",
            file=sys.stderr,
        )

    if skipped == len(MIRRORS):
        print(
            "no configured Ubuntu mirror answered — Canonical, kernel.org and "
            "OSU OSL do not fail together, so this is the runner's network, not "
            "the archives; re-run the job",
            file=sys.stderr,
        )
    else:
        print(
            "every reachable Ubuntu mirror failed the install; re-run the job",
            file=sys.stderr,
        )
    return {"installed": False, "source": None, "unreachable": unreachable}


def package_digest() -> str:
    """A short stable digest of the pinned package set.

    The cache key binds to this rather than to the file, so renewing a pin
    invalidates the cache and editing a comment or the fallback order does not
    throw away 185 MiB of archives for nothing.
    """
    joined = "\n".join(PACKAGES).encode()
    return hashlib.sha256(joined).hexdigest()[:16]


def main(
    argv: Sequence[str],
    *,
    runner: Runner = run_command,
    os_release: Path = Path("/etc/os-release"),
    staged_conf: Path = Path("/tmp/apt-99ci.conf"),
) -> int:
    """Run the install and emit its report.

    The runner and the two paths read from the machine are keyword arguments so
    the entry point's own contract — one JSON object on stdout, whatever
    happened — is testable without an Ubuntu runner under it.
    """
    if len(argv) == 2 and argv[1] == "--package-digest":
        print(package_digest())
        return 0
    if len(argv) != 2:
        print(
            "usage: install_system_deps.py <workspace-root> | --package-digest",
            file=sys.stderr,
        )
        return 2
    try:
        report = install(
            runner,
            workspace=Path(argv[1]),
            codename=read_codename(os_release),
            staged_conf=staged_conf,
        )
    # outer-boundary-process-contract: the workflow step reads stdout as the
    # report and a non-zero exit as "the dependencies are not installed", so an
    # unreadable /etc/os-release, an unwritable staged config or a subprocess
    # that will not launch must come back as that report — not as a traceback
    # with empty stdout, which reads to a parser as a malformed contract rather
    # than a failed install. Emits the failure report and the exception text on
    # stderr. KeyboardInterrupt and SystemExit are not caught, so the step stays
    # killable.
    except Exception as error:  # noqa: BLE001
        print(error, file=sys.stderr)
        report = {"installed": False, "source": None, "unreachable": []}
    print(json.dumps(report))
    return 0 if report["installed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
