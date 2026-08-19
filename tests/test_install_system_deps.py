"""Tests for the CI system-dependency installer.

Both failures this script exists for are invisible from inside a green run. A
cache that restores but is never consulted looks exactly like a cache that
works, and a runner that cannot reach any mirror looks exactly like four
archives being slow — the first cost every run a mirror round-trip, the second
cost twenty minutes before the job failed. What separates them is the command
sequence, so that is what these pin: which commands are issued, and which are
never issued at all.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "install_system_deps.py"
SPEC = importlib.util.spec_from_file_location("install_system_deps", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
install_system_deps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install_system_deps)

AZURE = "http://azure.archive.ubuntu.com/ubuntu"
CANONICAL = "http://archive.ubuntu.com/ubuntu"
CODENAME = "noble"


class FakeRunner:
    """Record every command and answer from a caller-supplied verdict."""

    def __init__(self, verdict: Callable[[Sequence[str]], int]) -> None:
        self.commands: list[list[str]] = []
        self._verdict = verdict

    def __call__(self, command: Sequence[str], _timeout: int) -> int:
        self.commands.append(list(command))
        return self._verdict(command)

    def issued(self, *fragments: str) -> list[list[str]]:
        """Commands containing every fragment, matched against the whole line.

        Membership on the argument list would miss a fragment that is part of an
        argument rather than all of it — a script path carries its directory, so
        an exact-element match silently answers "never issued" for a command that
        ran on every attempt.
        """
        return [c for c in self.commands if all(f in " ".join(c) for f in fragments)]


def all_succeed(command: Sequence[str]) -> int:
    del command
    return 0


def seed_cache(archive_cache: Path, list_cache: Path, *, lists: bool) -> None:
    archive_cache.mkdir(parents=True, exist_ok=True)
    (archive_cache / "ffmpeg_7.0_amd64.deb").write_text("deb")
    list_cache.mkdir(parents=True, exist_ok=True)
    if lists:
        (list_cache / "archive.ubuntu.com_ubuntu_dists_noble_main_Packages").write_text(
            "Package: ffmpeg\n"
        )


def run_install(
    runner: FakeRunner, tmp_path: Path, *, legacy_sources_list: bool = True
) -> dict[str, object]:
    """Drive the installer against a fabricated runner layout.

    The source paths are passed explicitly rather than defaulted: the defaults
    are real system paths, so a test that let them through would assert one thing
    on a deb822 Linux runner and another on a developer's macOS checkout.
    """
    sources = tmp_path / "sources.list"
    sources_d = tmp_path / "sources.list.d"
    sources_d.mkdir(exist_ok=True)
    (sources_d / "ubuntu.sources").write_text("Types: deb\n")
    if legacy_sources_list:
        sources.write_text("deb http://archive.ubuntu.com/ubuntu noble main\n")
    return install_system_deps.install(
        runner,
        workspace=tmp_path / "workspace",
        codename=CODENAME,
        staged_conf=tmp_path / "99ci",
        archive_cache=tmp_path / "apt-cache",
        list_cache=tmp_path / "apt-lists",
        sources=sources,
        sources_d=sources_d,
    )


def test_a_usable_cache_installs_without_contacting_any_mirror(tmp_path: Path):
    """The first failure: the cache hit, and the step fetched the index anyway.

    185 MiB of archives restored and `apt-get update` still ran, so every run
    paid a mirror round-trip for an index it could have cached. A cache hit must
    issue no probe, no update, and no mirror rewrite.
    """
    seed_cache(tmp_path / "apt-cache", tmp_path / "apt-lists", lists=True)
    runner = FakeRunner(all_succeed)

    report = run_install(runner, tmp_path)

    assert report == {"installed": True, "source": "cache", "unreachable": []}
    assert runner.issued("apt-get", "update") == []
    assert runner.issued("curl") == []
    assert runner.issued("apt_set_mirror.py") == []
    assert runner.issued("apt-get", "--no-download")


def test_archives_without_indices_are_not_treated_as_a_usable_cache(tmp_path: Path):
    """A cache entry written before the indices were cached holds only archives.

    Offline resolution needs both halves, and the cache-hit flag cannot tell
    which shape was restored — so the pair is what gets checked.
    """
    seed_cache(tmp_path / "apt-cache", tmp_path / "apt-lists", lists=False)
    runner = FakeRunner(all_succeed)

    report = run_install(runner, tmp_path)

    assert report["source"] == AZURE
    assert runner.issued("apt-get", "--no-download") == []
    assert runner.issued("apt-get", "update")


def test_a_cache_that_cannot_satisfy_the_install_falls_back_to_a_mirror(
    tmp_path: Path,
):
    """A runner image that changed leaves the cached set short a dependency.

    `--no-download` fails rather than reaching for it, and that failure has to
    reach the mirror path instead of failing the job.
    """
    seed_cache(tmp_path / "apt-cache", tmp_path / "apt-lists", lists=True)
    runner = FakeRunner(lambda command: 100 if "--no-download" in command else 0)

    report = run_install(runner, tmp_path)

    assert report["installed"] is True
    assert report["source"] == AZURE
    assert runner.issued("apt-get", "update")


def test_every_mirror_unreachable_fails_without_waiting_out_four_timeouts(
    tmp_path: Path,
):
    """The second failure: 4 mirrors x a 300s update timeout, 20 minutes wasted.

    Canonical, kernel.org and OSU OSL do not go dark together, so an unanswered
    probe everywhere is the runner's network. Not one `apt-get update` may be
    issued — issuing one is what bought the 20 minutes.
    """
    runner = FakeRunner(lambda command: 7 if "curl" in command else 0)

    report = run_install(runner, tmp_path)

    assert report["installed"] is False
    assert report["unreachable"] == [m[0] for m in install_system_deps.MIRRORS]
    assert runner.issued("apt-get", "update") == []
    assert len(runner.issued("curl")) == len(install_system_deps.MIRRORS)


def test_an_unreachable_mirror_is_skipped_and_the_next_one_serves(tmp_path: Path):
    """One degraded archive is the case the mirror list was built for.

    It is skipped on the probe rather than on a 300s stall, and the next host
    installs.
    """

    def verdict(command: Sequence[str]) -> int:
        if "curl" in command:
            return 7 if any(AZURE in arg for arg in command) else 0
        return 0

    runner = FakeRunner(verdict)

    report = run_install(runner, tmp_path)

    assert report["installed"] is True
    assert report["source"] == CANONICAL
    assert report["unreachable"] == [AZURE]


def test_a_reachable_mirror_whose_update_fails_moves_to_the_next(tmp_path: Path):
    """Answering a HEAD is not the same as serving a full index.

    A mirror that probes clean and then fails the update is a real failure the
    probe cannot pre-empt, so the fallback chain still has to walk on.
    """
    seen: list[str] = []

    def verdict(command: Sequence[str]) -> int:
        if any(arg.endswith("apt_set_mirror.py") for arg in command):
            seen.append(command[3])
        if "update" in command and seen and seen[-1] == AZURE:
            return 1
        return 0

    runner = FakeRunner(verdict)

    report = run_install(runner, tmp_path)

    assert report["installed"] is True
    assert report["source"] == CANONICAL
    # Probed clean, so it is absent from the unreachable list — the two failure
    # shapes stay distinguishable in the report.
    assert report["unreachable"] == []


def test_a_successful_mirror_install_stages_both_halves_for_the_cache(
    tmp_path: Path,
):
    """Nothing seeds the offline path except the save after a mirror install.

    The indices are copied out of apt's directory and both halves are handed to
    the runner user, or actions/cache tars nothing and the step goes green having
    cached exactly what it started with.
    """
    runner = FakeRunner(all_succeed)

    run_install(runner, tmp_path)

    assert runner.issued("cp", "-a", "/var/lib/apt/lists/.")
    assert runner.issued("chown", "-R")


def test_the_apt_config_points_the_archive_dir_at_the_cached_location(
    tmp_path: Path,
):
    """`Keep-Downloaded-Packages` is what makes the archive cache exist at all.

    apt discards downloaded .debs after a successful install, so without it the
    archive dir is empty when the cache save runs.
    """
    runner = FakeRunner(all_succeed)

    run_install(runner, tmp_path)

    staged = (tmp_path / "99ci").read_text()
    assert 'Dir::Cache::Archives "/tmp/apt-cache";' in staged
    assert 'APT::Keep-Downloaded-Packages "true";' in staged


def test_the_probe_asks_each_mirror_for_an_index_file_it_must_serve(tmp_path: Path):
    """A directory listing is optional on a mirror; InRelease is not.

    Probing something a healthy mirror may legitimately 404 would report a
    working host as unreachable.
    """
    runner = FakeRunner(lambda command: 7 if "curl" in command else 0)

    run_install(runner, tmp_path)

    probed = runner.issued("curl")[0]
    assert f"{AZURE}/dists/{CODENAME}/InRelease" in probed
    assert "--head" in probed


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


def test_a_deb822_only_runner_is_not_asked_to_copy_a_sources_list_it_lacks(
    tmp_path: Path,
):
    """Ubuntu 24.04 images ship `ubuntu.sources` and no `sources.list`.

    Copying the absent file would fail on every healthy deb822 runner, and a
    failure nobody reads is how a real one gets missed.
    """
    runner = FakeRunner(all_succeed)

    report = run_install(runner, tmp_path, legacy_sources_list=False)

    assert report["installed"] is True
    assert runner.issued("cp", "sources.list ") == []
    assert runner.issued("apt_set_mirror.py")


def test_a_runner_carrying_both_layouts_backs_up_and_restores_each(tmp_path: Path):
    """A legacy `sources.list` beside a deb822 directory is still a live layout.

    Both halves are preserved, because the rewrite reads whichever the image
    actually uses and a dropped one silently loses a repository.
    """
    runner = FakeRunner(all_succeed)

    run_install(runner, tmp_path, legacy_sources_list=True)

    assert runner.issued("cp", "-a", "sources.list", "apt-src-orig")
    assert runner.issued("cp", "-a", "sources.list.d", "apt-src-orig")


def test_the_entry_point_refuses_a_call_without_a_workspace_root():
    """The workspace is where the mirror rewriter is found.

    Defaulting it would send `sudo python3` at a path that does not exist and
    read as a mirror failure four times over.
    """
    assert install_system_deps.main(["install_system_deps.py"]) == 2
