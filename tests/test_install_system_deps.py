"""Tests for the CI system-dependency installer.

Both failures this script exists for are invisible from inside a green run. A
cache that restores but is never consulted looks exactly like a cache that
works, and a runner that cannot reach any mirror looks exactly like four
archives being slow — the first cost every run a mirror round-trip, the second
cost twenty minutes before the job failed.

So the fake below runs the commands rather than recording them: it copies the
files, tracks who owns them, and answers apt and curl the way a runner would.
The assertions are what came out — which packages ended up installed, which
requests left the machine, what the cache holds afterwards and who can read it —
not which commands were issued to get there.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "install_system_deps.py"
SPEC = importlib.util.spec_from_file_location("install_system_deps", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
install_system_deps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install_system_deps)

AZURE = "http://azure.archive.ubuntu.com/ubuntu"
CANONICAL = "http://archive.ubuntu.com/ubuntu"
ALL_ARCHIVES = tuple(m[0] for m in install_system_deps.MIRRORS)
CODENAME = "noble"
INDEX_NAME = "archive.ubuntu.com_ubuntu_dists_noble_main_binary-amd64_Packages"

# Absolute paths the script hardcodes. Anything else — the caches and sources a
# test injects — is a real pytest temp path and passes through untouched.
SYSTEM_ROOTS = (
    str(install_system_deps.APT_LISTS),
    str(install_system_deps.SOURCES_BACKUP),
    "/etc/apt",
)


class FakeSystem:
    """A runner that carries the commands out against a sandboxed filesystem.

    Only the paths the script hardcodes are redirected under `root`; an injected
    cache or sources path is already a temp path and is used as given, so the
    script's own `exists()` and `glob()` see what the commands did.
    """

    def __init__(
        self,
        root: Path,
        *,
        archive_cache: Path,
        sources: Path,
        sources_d: Path,
        reachable: Sequence[str] = ALL_ARCHIVES,
        update_fails: Sequence[str] = (),
        offline_satisfies: bool = True,
        failing: str | None = None,
    ) -> None:
        self.root = root
        self.archive_cache = archive_cache
        self.reachable = tuple(reachable)
        self.update_fails = tuple(update_fails)
        self.offline_satisfies = offline_satisfies
        self.failing = failing
        self.installed: list[str] = []
        self.probes: list[str] = []
        self.fetches: list[str] = []
        self.sources = sources
        self.sources_d = sources_d
        self.owners: dict[str, str] = {}
        self.mirrors: set[str] = set()

    # --- filesystem ---------------------------------------------------------

    def local(self, path: str) -> Path:
        bare = path[:-2] if path.endswith("/.") else path.rstrip("/")
        for system_root in SYSTEM_ROOTS:
            if bare == system_root or bare.startswith(f"{system_root}/"):
                return self.root / bare.lstrip("/")
        return Path(bare)

    def owner_of(self, path: Path) -> str:
        return self.owners.get(str(path), "root")

    def _copy(self, source: str, target: str) -> None:
        src, dst = self.local(source), self.local(target)
        if source.endswith("/."):
            dst.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            return
        if src.is_dir():
            # `cp -a A B`: B missing means B becomes the copy; B existing as a
            # directory means the copy lands inside it.
            landing = dst / src.name if dst.is_dir() else dst
            shutil.copytree(src, landing, dirs_exist_ok=True)
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst / src.name if dst.is_dir() else dst)

    # --- commands -----------------------------------------------------------

    def __call__(self, command: Sequence[str], timeout: int) -> int:
        del timeout
        if self.failing is not None and self.failing in " ".join(command):
            return 1
        args = [a for a in command if a not in ("sudo", "-E")]
        program = Path(args[0]).name
        if program == "mkdir":
            for path in args[2:]:
                self.local(path).mkdir(parents=True, exist_ok=True)
            return 0
        if program == "chmod":
            return 0
        if program == "chown":
            for path in args[3:]:
                self.owners[str(self.local(path))] = args[2]
            return 0
        if program == "rm":
            for path in args[2:]:
                target = self.local(path)
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
            return 0
        if program == "cp":
            self._copy(args[-2], args[-1])
            return 0
        if program == "curl":
            return self._probe(args[-1])
        if program == "apt-get":
            return self._apt(args[1:])
        if program == "python3":
            # The real rewriter, against the real files. Trusting the argument is
            # what let a rewrite that changed nothing look like a working
            # fallback — every retry then hit the mirror that had just failed.
            subprocess.run([sys.executable, *args[1:]], check=True, capture_output=True)
            self.mirrors = self._archives_in_sources()
            return 0
        raise AssertionError(f"unmodelled command: {' '.join(command)}")

    def _source_files(self) -> list[Path]:
        present = [self.sources] if self.sources.exists() else []
        return present + sorted(self.sources_d.glob("*"))

    def _archives_in_sources(self) -> set[str]:
        """Every archive host apt would fetch from, read off the source files.

        A set, not one host: `apt-get update` fetches all of them and fails if
        any fails. A rewrite that moved one file and missed another leaves the
        dead mirror in the list, which is exactly the shape a single-host model
        cannot see.
        """
        hosts: set[str] = set()
        for path in self._source_files():
            for line in path.read_text().splitlines():
                if line.lower().startswith("uris:"):
                    uri = line.split(":", 1)[1].strip().rstrip("/")
                    if not uri.endswith("security.ubuntu.com/ubuntu"):
                        hosts.add(uri)
                elif line.startswith("deb "):
                    hosts.add(line.split()[1].rstrip("/"))
        return hosts

    def _probe(self, url: str) -> int:
        self.probes.append(url)
        return 0 if any(url.startswith(a) for a in self.reachable) else 7

    def _reachable_everywhere(self) -> bool:
        if not self.mirrors:
            return False
        if any(m in self.update_fails for m in self.mirrors):
            return False
        return all(m in self.reachable for m in self.mirrors)

    def _apt(self, args: Sequence[str]) -> int:
        if args[0] == "update":
            self.fetches.extend(sorted(self.mirrors))
            return 0 if self._reachable_everywhere() else 1
        packages = [a for a in args[1:] if not a.startswith("-")]
        if "--no-download" in args:
            indices = self.local(str(install_system_deps.APT_LISTS))
            has_indices = indices.is_dir() and any(indices.glob("*Packages*"))
            if not (self.offline_satisfies and has_indices):
                return 100
            if not any(self.archive_cache.glob("*.deb")):
                return 100
            self.installed = packages
            return 0
        self.fetches.extend(sorted(self.mirrors))
        if not self._reachable_everywhere():
            return 1
        self.installed = packages
        return 0


def build(tmp_path: Path, **kwargs: object) -> tuple[FakeSystem, dict[str, Path]]:
    """Lay out a runner: apt's own index dir populated, caches empty."""
    root = tmp_path / "system"
    lists = root / str(install_system_deps.APT_LISTS).lstrip("/")
    lists.mkdir(parents=True)
    (lists / INDEX_NAME).write_text("Package: ffmpeg\n")
    paths = {
        "archive_cache": tmp_path / "apt-cache",
        "list_cache": tmp_path / "apt-lists",
        "sources": tmp_path / "sources.list",
        "sources_d": tmp_path / "sources.list.d",
        "staged_conf": tmp_path / "99ci",
        "root": root,
    }
    paths["sources_d"].mkdir()
    (paths["sources_d"] / "ubuntu.sources").write_text(
        "Types: deb\n"
        f"URIs: {AZURE}/\n"
        "Suites: noble noble-updates\n"
        "Components: main restricted\n"
    )
    system = FakeSystem(
        root,
        archive_cache=paths["archive_cache"],
        sources=paths["sources"],
        sources_d=paths["sources_d"],
        **kwargs,  # type: ignore[arg-type]
    )
    return system, paths


def seed_cache(paths: dict[str, Path], *, indices: bool) -> None:
    """Restore a cache entry the way actions/cache would have."""
    paths["archive_cache"].mkdir(parents=True, exist_ok=True)
    (paths["archive_cache"] / "ffmpeg_6.1.1_amd64.deb").write_text("deb")
    paths["list_cache"].mkdir(parents=True, exist_ok=True)
    if indices:
        (paths["list_cache"] / INDEX_NAME).write_text("Package: ffmpeg\n")


def run_install(
    system: FakeSystem, paths: dict[str, Path], *, legacy_sources_list: bool = True
) -> dict[str, object]:
    if legacy_sources_list:
        paths["sources"].write_text(f"deb {AZURE} noble main\n")
    return install_system_deps.install(
        system,
        workspace=Path(__file__).parents[1],
        codename=CODENAME,
        staged_conf=paths["staged_conf"],
        archive_cache=paths["archive_cache"],
        list_cache=paths["list_cache"],
        sources=paths["sources"],
        sources_d=paths["sources_d"],
    )


def test_a_usable_cache_installs_with_nothing_leaving_the_machine(tmp_path: Path):
    """The first failure: the cache hit, and the step fetched the index anyway.

    185 MiB of archives restored and `apt-get update` still ran, so every run
    paid a mirror round-trip for an index it could have cached. The outcome that
    matters is not which commands were skipped — it is that no request left the
    runner and the packages are installed regardless.
    """
    system, paths = build(tmp_path)
    seed_cache(paths, indices=True)

    report = run_install(system, paths)

    assert report == {"installed": True, "source": "cache", "unreachable": []}
    assert system.installed == list(install_system_deps.PACKAGES)
    assert system.probes == []
    assert system.fetches == []


def test_archives_without_indices_cannot_satisfy_an_offline_install(tmp_path: Path):
    """A cache entry written before the indices were cached holds only archives.

    Offline resolution needs both halves, and the cache-hit flag cannot tell
    which shape was restored.
    """
    system, paths = build(tmp_path)
    seed_cache(paths, indices=False)

    report = run_install(system, paths)

    assert report["source"] == AZURE
    assert system.installed == list(install_system_deps.PACKAGES)
    assert set(system.fetches) == {AZURE}


def test_a_cache_that_cannot_satisfy_the_install_still_ends_up_installed(
    tmp_path: Path,
):
    """A runner image that changed leaves the cached set short a dependency.

    The offline attempt fails rather than reaching for it, and the job must
    still end with the packages present.
    """
    system, paths = build(tmp_path, offline_satisfies=False)
    seed_cache(paths, indices=True)

    report = run_install(system, paths)

    assert report["installed"] is True
    assert system.installed == list(install_system_deps.PACKAGES)


def test_nothing_reachable_fails_without_ever_attempting_a_fetch(tmp_path: Path):
    """The second failure: 4 mirrors x a 300s update timeout, 20 minutes wasted.

    Canonical, kernel.org and OSU OSL do not go dark together, so an unanswered
    probe everywhere is the runner's network. Not one fetch may be attempted —
    attempting them is what bought the 20 minutes.
    """
    system, paths = build(tmp_path, reachable=())

    report = run_install(system, paths)

    assert report["installed"] is False
    assert report["unreachable"] == list(ALL_ARCHIVES)
    assert system.fetches == []
    assert system.installed == []
    assert len(system.probes) == len(ALL_ARCHIVES)


def test_one_unreachable_archive_does_not_stop_the_install(tmp_path: Path):
    """One degraded archive is the case the mirror list was built for."""
    system, paths = build(tmp_path, reachable=ALL_ARCHIVES[1:])

    report = run_install(system, paths)

    assert report["source"] == CANONICAL
    assert report["unreachable"] == [AZURE]
    assert system.installed == list(install_system_deps.PACKAGES)
    # Skipped on the probe, so no fetch was ever aimed at it.
    assert AZURE not in system.fetches


def test_a_mirror_that_answers_and_then_fails_still_hands_off(tmp_path: Path):
    """Answering a HEAD is not the same as serving a full index.

    A real mirror failure the probe cannot pre-empt still has to walk the
    fallback chain, and it stays out of the unreachable list so the two failure
    shapes remain distinguishable.
    """
    system, paths = build(tmp_path, update_fails=(AZURE,))

    report = run_install(system, paths)

    assert report["source"] == CANONICAL
    assert report["unreachable"] == []
    assert system.installed == list(install_system_deps.PACKAGES)


def test_after_a_mirror_install_the_cache_holds_a_usable_pair(tmp_path: Path):
    """Nothing seeds the offline path except the save after a mirror install.

    The next run's `cache_is_usable` is the real consumer, so that is the
    assertion: the saved state is a pair it accepts, owned by the user
    actions/cache tars as.
    """
    system, paths = build(tmp_path)
    paths["archive_cache"].mkdir(parents=True)
    (paths["archive_cache"] / "ffmpeg_6.1.1_amd64.deb").write_text("deb")

    run_install(system, paths)

    assert install_system_deps.cache_is_usable(
        paths["archive_cache"], paths["list_cache"]
    )
    runner = install_system_deps._owner()
    assert system.owner_of(paths["list_cache"]) == runner
    assert system.owner_of(paths["archive_cache"]) == runner


def test_apt_is_configured_to_keep_its_downloads_where_the_cache_looks(
    tmp_path: Path,
):
    """`Keep-Downloaded-Packages` is what makes the archive cache exist at all.

    apt discards downloaded .debs after a successful install, so without it the
    archive dir is empty when the cache save runs.
    """
    system, paths = build(tmp_path)

    run_install(system, paths)

    landed = system.local("/etc/apt/apt.conf.d/99ci").read_text()
    assert 'Dir::Cache::Archives "/tmp/apt-cache";' in landed
    assert 'APT::Keep-Downloaded-Packages "true";' in landed


def test_the_probe_requests_an_index_file_every_mirror_must_serve(tmp_path: Path):
    """A directory listing is optional on a mirror; InRelease is not.

    Requesting something a healthy mirror may legitimately 404 would report a
    working host as unreachable.
    """
    system, paths = build(tmp_path, reachable=())

    run_install(system, paths)

    assert system.probes[0] == f"{AZURE}/dists/{CODENAME}/InRelease"


def test_the_fallback_repoints_a_deb822_only_runner(tmp_path: Path):
    """The layout 24.04 actually ships, and the one a glob bug hides in.

    With no `sources.list` beside it, `ubuntu.sources` is the only file naming a
    mirror — if the rewrite misses it, every retry fetches from the host that
    just failed and the fallback is decorative.
    """
    system, paths = build(tmp_path, reachable=ALL_ARCHIVES[1:])

    report = run_install(system, paths, legacy_sources_list=False)

    assert report["source"] == CANONICAL
    assert system.installed == list(install_system_deps.PACKAGES)
    assert AZURE not in system.fetches


def test_a_deb822_only_runner_installs_like_any_other(tmp_path: Path):
    """Ubuntu 24.04 images ship `ubuntu.sources` and no `sources.list`.

    Copying the absent file fails on every healthy deb822 runner, and a required
    command's failure now stops the run — so this layout has to be recognised
    rather than attempted.
    """
    system, paths = build(tmp_path)

    report = run_install(system, paths, legacy_sources_list=False)

    assert report["installed"] is True
    backup = system.local(str(install_system_deps.SOURCES_BACKUP))
    assert not (backup / "sources.list").exists()
    assert (backup / "sources.list.d").is_dir()


def test_a_runner_carrying_both_layouts_preserves_each(tmp_path: Path):
    """A legacy `sources.list` beside a deb822 directory is still a live layout.

    Dropping either half silently loses a repository from the retry.
    """
    system, paths = build(tmp_path)

    run_install(system, paths, legacy_sources_list=True)

    backup = system.local(str(install_system_deps.SOURCES_BACKUP))
    assert (backup / "sources.list").is_file()
    assert (backup / "sources.list.d" / "ubuntu.sources").is_file()


def test_a_failed_setup_command_stops_the_run_instead_of_reporting_success(
    tmp_path: Path,
):
    """A failed copy leaves apt reading whatever was already there.

    The install that follows can still succeed and the step still go green — the
    exact shape that hid an empty cache for months — so a command with no
    recovery path has to end the run.
    """
    system, paths = build(tmp_path, failing="cp -a")

    with pytest.raises(install_system_deps.SystemDepsError, match="re-run the job"):
        run_install(system, paths)

    assert system.installed == []


def test_every_package_carries_an_exact_version(tmp_path: Path):
    """An unpinned apt package resolves to whatever the archive serves that day.

    The pin is the reproducibility, and a bare name silently changes the tested
    toolchain between two runs of the same commit.
    """
    del tmp_path
    for package in install_system_deps.PACKAGES:
        assert "=" in package, package


def test_the_codename_comes_from_the_runner_image(tmp_path: Path):
    os_release = tmp_path / "os-release"
    os_release.write_text('NAME="Ubuntu"\nVERSION_CODENAME=noble\nID=ubuntu\n')

    assert install_system_deps.read_codename(os_release) == CODENAME


def test_a_missing_codename_says_what_to_do_about_it(tmp_path: Path):
    """The probe URL cannot be guessed, and a wrong suite reports every mirror
    unreachable — a silent failure worth an actionable message."""
    os_release = tmp_path / "os-release"
    os_release.write_text('NAME="Something Else"\nID=other\n')

    with pytest.raises(ValueError, match="pin the suite explicitly"):
        install_system_deps.read_codename(os_release)


def test_the_entry_point_refuses_a_call_without_a_workspace_root():
    """The workspace is where the mirror rewriter is found.

    Defaulting it would send `sudo python3` at a path that does not exist and
    read as a mirror failure four times over.
    """
    assert install_system_deps.main(["install_system_deps.py"]) == 2


def test_the_real_runner_keeps_child_output_off_stdout(
    capfd: pytest.CaptureFixture[str],
):
    """apt is chatty and inherits this process's streams by default.

    Its progress landing between the report's braces breaks every caller that
    parses stdout, and the script promises exactly one JSON object there.
    """
    code = install_system_deps.run_command(["printf", "Reading package lists"], 30)

    captured = capfd.readouterr()
    assert code == 0
    assert captured.out == ""
    assert "Reading package lists" in captured.err


def test_a_failed_setup_command_still_leaves_one_json_object_on_stdout(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
):
    """A caller should not tell a failed install from a dead script by whether
    it got parseable JSON back."""
    system, paths = build(tmp_path, failing="mkdir")
    os_release = tmp_path / "os-release"
    os_release.write_text("VERSION_CODENAME=noble\n")

    code = install_system_deps.main(
        ["install_system_deps.py", str(paths["root"])],
        runner=system,
        os_release=os_release,
        staged_conf=paths["staged_conf"],
    )

    captured = capfd.readouterr()
    assert code == 1
    assert json.loads(captured.out) == {
        "installed": False,
        "source": None,
        "unreachable": [],
    }


def test_the_cache_key_digest_tracks_the_pins_and_nothing_else(
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    """The key must invalidate on a renewed pin and survive an edited comment.

    Hashing the file did the first and not the second, throwing away 185 MiB of
    archives every time the fallback order or a docstring changed.
    """
    assert install_system_deps.main(["prog", "--package-digest"]) == 0
    printed = capfd.readouterr().out.strip()

    assert printed == install_system_deps.package_digest()

    renewed = (*install_system_deps.PACKAGES[:-1], "tesseract-ocr=5.3.5-1")
    monkeypatch.setattr(install_system_deps, "PACKAGES", renewed)
    assert install_system_deps.package_digest() != printed
