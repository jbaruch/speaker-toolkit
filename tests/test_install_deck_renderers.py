"""Contract tests for the CI markdown-deck renderer install.

Every command goes through an injected runner, so the install sequence is
assertable without a network, a node, or a GitHub runner.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_deck_renderers.py"
SPEC = importlib.util.spec_from_file_location("install_deck_renderers", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
install_deck_renderers = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = install_deck_renderers
SPEC.loader.exec_module(install_deck_renderers)


# The real asset nests its payload under a version-stamped directory. Fixtures
# mirror that: a flat archive would have let the member-path extraction that
# `tar: presenterm: Not found in archive` killed in CI pass here.
PRESENTERM_ARCHIVE_PREFIX = "presenterm-0.16.1"


def _tarball(member_names: tuple[str, ...]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in member_names:
            payload = b"#!/bin/sh\nexit 0\n"
            info = tarfile.TarInfo(f"{PRESENTERM_ARCHIVE_PREFIX}/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


class _FakeRunner:
    """Record every command, and act out the side effects a real one has."""

    def __init__(
        self,
        *,
        archive: bytes | None = None,
        failing: str | None = None,
        silent_tar: bool = False,
    ):
        self.commands: list[list[str]] = []
        self._archive = archive
        self._failing = failing
        self._silent_tar = silent_tar

    def __call__(self, command, timeout):  # noqa: D102 - runner protocol
        del timeout  # every command here is instantaneous
        self.commands.append(list(command))
        if self._failing is not None and command[0] == self._failing:
            return 1
        if command[0] == "curl":
            destination = Path(command[command.index("--output") + 1])
            destination.write_bytes(self._archive or b"")
        if command[0] == "tar" and self._silent_tar:
            return 0
        if command[0] == "tar":
            target = Path(command[command.index("-C") + 1])
            with tarfile.open(fileobj=io.BytesIO(self._archive or b"")) as archive:
                for member in archive.getmembers():
                    if not member.isfile():
                        continue
                    handle = archive.extractfile(member)
                    if handle is None:
                        continue
                    destination = target / member.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(handle.read())
        if command[0] == "npm":
            prefix = Path(command[command.index("--prefix") + 1])
            binaries = prefix / "node_modules" / ".bin"
            binaries.mkdir(parents=True, exist_ok=True)
            (binaries / "slidev").write_text("", encoding="utf-8")
        return 0


@pytest.fixture
def pinned_archive(monkeypatch):
    """Return a tarball whose checksum the module accepts as the pinned one."""
    archive = _tarball(("presenterm",))
    monkeypatch.setattr(
        install_deck_renderers,
        "PRESENTERM_SHA512",
        hashlib.sha512(archive).hexdigest(),
    )
    return archive


def test_the_pin_digest_is_stable_and_short():
    first = install_deck_renderers.pin_digest()

    assert first == install_deck_renderers.pin_digest()
    assert re.fullmatch(r"[0-9a-f]{16}", first)


def test_renewing_a_pin_changes_the_cache_key(monkeypatch):
    before = install_deck_renderers.pin_digest()
    monkeypatch.setattr(install_deck_renderers, "PRESENTERM_VERSION", "0.17.0")

    assert install_deck_renderers.pin_digest() != before


def test_a_cached_presenterm_is_left_alone(tmp_path):
    binary = tmp_path / "bin" / "presenterm"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    runner = _FakeRunner()

    assert install_deck_renderers.install_presenterm(tmp_path, runner) == "cached"
    assert runner.commands == []


def test_presenterm_is_downloaded_and_checksum_verified(tmp_path, pinned_archive):
    runner = _FakeRunner(archive=pinned_archive)

    result = install_deck_renderers.install_presenterm(tmp_path, runner)

    assert result == "downloaded"
    assert (tmp_path / "bin" / "presenterm").is_file()
    assert runner.commands[0][0] == "curl"
    assert install_deck_renderers.PRESENTERM_URL in runner.commands[0]
    # The archive is not left behind to be cached as dead weight.
    assert not (tmp_path / install_deck_renderers.PRESENTERM_ASSET).exists()


def test_an_asset_that_changed_under_the_pin_is_refused(tmp_path):
    runner = _FakeRunner(archive=_tarball(("presenterm",)))

    with pytest.raises(install_deck_renderers.InstallFailure) as excinfo:
        install_deck_renderers.install_presenterm(tmp_path, runner)

    assert "checksum" in str(excinfo.value)
    assert not (tmp_path / "bin" / "presenterm").exists()


def test_an_archive_without_the_binary_is_refused(tmp_path, monkeypatch):
    """An asset that carries everything but the binary is a layout change."""
    archive = _tarball(("README.md",))
    monkeypatch.setattr(
        install_deck_renderers,
        "PRESENTERM_SHA512",
        hashlib.sha512(archive).hexdigest(),
    )
    runner = _FakeRunner(archive=archive)

    with pytest.raises(install_deck_renderers.InstallFailure) as excinfo:
        install_deck_renderers.install_presenterm(tmp_path, runner)

    assert "release layout changed" in str(excinfo.value)
    assert not (tmp_path / "bin" / "presenterm").exists()


def test_a_failed_extraction_is_refused(tmp_path, monkeypatch, pinned_archive):
    runner = _FakeRunner(archive=pinned_archive, failing="tar")

    with pytest.raises(install_deck_renderers.InstallFailure) as excinfo:
        install_deck_renderers.install_presenterm(tmp_path, runner)

    assert "could not extract" in str(excinfo.value)


def test_a_binary_nested_under_a_version_directory_is_found(
    tmp_path,
    pinned_archive,
):
    """The real asset nests it; naming a flat member path failed in CI."""
    runner = _FakeRunner(archive=pinned_archive)

    install_deck_renderers.install_presenterm(tmp_path, runner)

    assert (tmp_path / "bin" / "presenterm").is_file()
    # The extraction staging area does not survive into the cached tree.
    assert not (tmp_path / "presenterm-extract").exists()


def test_an_extraction_that_writes_no_binary_is_refused(tmp_path, pinned_archive):
    """A layout change can leave tar happy and the binary somewhere else."""
    runner = _FakeRunner(archive=pinned_archive, silent_tar=True)

    with pytest.raises(install_deck_renderers.InstallFailure) as excinfo:
        install_deck_renderers.install_presenterm(tmp_path, runner)

    assert "release layout changed" in str(excinfo.value)


def test_a_failed_download_names_the_url(tmp_path):
    runner = _FakeRunner(failing="curl")

    with pytest.raises(install_deck_renderers.InstallFailure) as excinfo:
        install_deck_renderers.install_presenterm(tmp_path, runner)

    assert install_deck_renderers.PRESENTERM_URL in str(excinfo.value)


def test_a_cached_npm_tree_is_left_alone(tmp_path):
    binaries = tmp_path / "npm" / "node_modules" / ".bin"
    binaries.mkdir(parents=True)
    (binaries / "slidev").write_text("", encoding="utf-8")
    runner = _FakeRunner()

    assert install_deck_renderers.install_npm_renderers(tmp_path, runner) == "cached"
    assert runner.commands == []


def test_every_npm_pin_reaches_npm_exactly(tmp_path):
    runner = _FakeRunner()

    install_deck_renderers.install_npm_renderers(tmp_path, runner)

    assert runner.commands[0][:2] == ["npm", "install"]
    assert runner.commands[0][-len(install_deck_renderers.NPM_PINS) :] == list(
        install_deck_renderers.NPM_PINS
    )


def test_a_failed_npm_install_names_the_pins(tmp_path):
    runner = _FakeRunner(failing="npm")

    with pytest.raises(install_deck_renderers.InstallFailure) as excinfo:
        install_deck_renderers.install_npm_renderers(tmp_path, runner)

    assert install_deck_renderers.NPM_PINS[0] in str(excinfo.value)


def test_every_npm_pin_carries_an_exact_version():
    for pin in install_deck_renderers.NPM_PINS:
        name, _, version = pin.rpartition("@")

        assert name, f"{pin} must name a package"
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"{pin} is not an exact pin"


def test_the_report_names_how_each_renderer_was_satisfied(tmp_path, pinned_archive):
    runner = _FakeRunner(archive=pinned_archive)

    report = install_deck_renderers.execute(tmp_path, runner)

    assert report["ok"] is True
    assert report["presenterm"] == "downloaded"
    assert report["npm"] == "installed"
    assert report["path_entries"] == install_deck_renderers.path_entries(
        tmp_path / install_deck_renderers.RENDERER_SUBDIR
    )


def test_a_second_run_over_a_restored_cache_installs_nothing(
    tmp_path,
    pinned_archive,
):
    install_deck_renderers.execute(tmp_path, _FakeRunner(archive=pinned_archive))
    second = _FakeRunner(archive=pinned_archive)

    report = install_deck_renderers.execute(tmp_path, second)

    assert report["presenterm"] == "cached"
    assert report["npm"] == "cached"
    assert second.commands == []


def test_the_path_entries_lead_with_the_downloaded_binary(tmp_path):
    entries = install_deck_renderers.path_entries(tmp_path)

    assert entries == [
        str(tmp_path / "bin"),
        str(tmp_path / "npm" / "node_modules" / ".bin"),
    ]


def test_the_pin_digest_mode_prints_only_the_digest(capsys):
    assert install_deck_renderers.main(["--pin-digest"]) == 0

    assert capsys.readouterr().out.strip() == install_deck_renderers.pin_digest()


def test_a_missing_workspace_is_an_argument_error():
    with pytest.raises(SystemExit) as excinfo:
        install_deck_renderers.main([])

    assert excinfo.value.code == 2


def test_a_failed_install_reports_json_and_exits_one(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
        env={"PATH": "", "HOME": str(tmp_path)},
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False
    assert result.stderr


def test_the_workflow_pins_the_node_major_the_installer_requires():
    """One number in two files; the drift shows up here, not on a CI runner."""
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )
    pinned = re.search(r'node-version:\s*"(\d+)\.', workflow)

    assert pinned is not None, "tests.yml must pin an explicit node-version"
    assert int(pinned.group(1)) == install_deck_renderers.REQUIRED_NODE_MAJOR


def test_the_workflow_keys_its_cache_on_the_pin_digest():
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )

    assert "install_deck_renderers.py --pin-digest" in workflow
    assert "deck-renderers-${{ runner.os }}" in workflow
