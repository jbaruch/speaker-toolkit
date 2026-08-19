"""Tests for the CI apt mirror rewriter.

CI installs system dependencies from Ubuntu's archives; a degraded host stalls
the job, and the retry is only useful if the sources are genuinely repointed.
Every failure this rewriter can have is silent — the wrong host still parses,
still installs, and still looks green — so the cases below pin the ones that
actually bit: a security stanza sharing the archive host, and a legacy line
whose bracketed options hide the suite.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "apt_set_mirror.py"
SPEC = importlib.util.spec_from_file_location("apt_set_mirror", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
apt_set_mirror = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apt_set_mirror)

ARCHIVE = "http://archive.ubuntu.com/ubuntu"
SECURITY = "http://security.ubuntu.com/ubuntu"
AZURE = "http://azure.archive.ubuntu.com/ubuntu"

AZURE_DEB822 = """Types: deb
URIs: http://azure.archive.ubuntu.com/ubuntu/
Suites: noble noble-updates noble-backports
Components: main restricted

Types: deb
URIs: http://azure.archive.ubuntu.com/ubuntu/
Suites: noble-security
Components: main restricted
"""


def test_a_security_stanza_sharing_the_archive_host_still_moves_to_security():
    """The live failure: Azure serves both pockets from one host.

    Deciding by URI rewrites the security stanza as an archive one, so a
    security-pocket outage retries through the host that just failed.
    """
    result = apt_set_mirror.rewrite_deb822(AZURE_DEB822, ARCHIVE, SECURITY)

    stanzas = result.split("\n\n")
    assert f"URIs: {ARCHIVE}" in stanzas[0]
    assert "Suites: noble noble-updates" in stanzas[0]
    assert f"URIs: {SECURITY}" in stanzas[1]
    assert "Suites: noble-security" in stanzas[1]


def test_both_pockets_may_share_one_host():
    result = apt_set_mirror.rewrite_deb822(AZURE_DEB822, AZURE, AZURE)

    assert result.count(f"URIs: {AZURE}") == 2


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        # The bracketed options hide the suite: the first non-bracket token is
        # the URI, so a naive scan never sees `-security`.
        (
            "deb [arch=amd64] http://azure.archive.ubuntu.com/ubuntu noble-security main",
            SECURITY,
        ),
        (
            "deb [arch=amd64 signed-by=/usr/share/keyrings/u.gpg]"
            " http://azure.archive.ubuntu.com/ubuntu noble-security main",
            SECURITY,
        ),
        ("deb [arch=amd64] http://azure.archive.ubuntu.com/ubuntu noble main", ARCHIVE),
        ("deb http://azure.archive.ubuntu.com/ubuntu noble-security main", SECURITY),
        ("deb http://azure.archive.ubuntu.com/ubuntu noble-updates main", ARCHIVE),
        (
            "deb-src http://azure.archive.ubuntu.com/ubuntu noble-security main",
            SECURITY,
        ),
    ],
)
def test_legacy_lines_are_routed_by_suite_not_by_uri(line: str, expected: str):
    result = apt_set_mirror.rewrite_legacy(line, ARCHIVE, SECURITY)

    assert expected in result


@pytest.mark.parametrize(
    "line",
    [
        "deb https://download.docker.com/linux/ubuntu noble stable",
        "deb http://ppa.launchpadcontent.net/git-core/ppa/ubuntu noble main",
        "# a comment naming noble-security and archive.ubuntu.com",
        "",
    ],
)
def test_a_line_that_is_not_an_official_ubuntu_source_is_untouched(line: str):
    assert (
        apt_set_mirror.rewrite_legacy(line, ARCHIVE, SECURITY).strip() == line.strip()
    )


def test_a_third_party_repo_survives_a_deb822_rewrite():
    text = "Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: noble\n"

    assert apt_set_mirror.rewrite_deb822(text, ARCHIVE, SECURITY) == text


def test_rewriting_is_idempotent(tmp_path: Path):
    target = tmp_path / "ubuntu.sources"
    target.write_text(AZURE_DEB822, encoding="utf-8")

    assert apt_set_mirror.rewrite_file(target, ARCHIVE, SECURITY) is True
    assert apt_set_mirror.rewrite_file(target, ARCHIVE, SECURITY) is False


def test_an_absent_path_is_skipped_rather_than_failing(tmp_path: Path, capsys):
    """The caller passes globs that need not match on every runner image."""
    assert (
        apt_set_mirror.rewrite_file(tmp_path / "nope.sources", ARCHIVE, SECURITY)
        is False
    )
    assert apt_set_mirror.main([ARCHIVE, SECURITY, str(tmp_path / "nope.list")]) == 0

    assert json.loads(capsys.readouterr().out)["rewritten"] == []


def test_stdout_is_one_structured_report(tmp_path: Path, capsys):
    """Deterministic scripts report data, not prose."""
    target = tmp_path / "ubuntu.sources"
    target.write_text(AZURE_DEB822, encoding="utf-8")

    assert apt_set_mirror.main([ARCHIVE, SECURITY, str(target)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report == {
        "schema_version": 1,
        "archive": ARCHIVE,
        "security": SECURITY,
        "rewritten": [str(target)],
    }


def test_a_legacy_file_keeps_its_trailing_newline(tmp_path: Path):
    target = tmp_path / "x.list"
    target.write_text(
        "deb http://azure.archive.ubuntu.com/ubuntu noble main\n", encoding="utf-8"
    )

    apt_set_mirror.rewrite_file(target, ARCHIVE, SECURITY)

    assert target.read_text(encoding="utf-8").endswith("main\n")


def test_missing_arguments_report_usage_without_writing():
    assert apt_set_mirror.main([ARCHIVE]) == 2


MIXED_DEB822 = """Types: deb
URIs: http://azure.archive.ubuntu.com/ubuntu/
Suites: noble noble-updates noble-security
Components: main restricted
"""


def test_a_mixed_pocket_stanza_is_split_by_pocket():
    """One `URIs:` cannot serve both pockets once they diverge.

    security.ubuntu.com does not carry `noble` or `noble-updates`, so pointing
    the whole stanza there fails `apt-get update` — the exact outage the
    fallback exists to route around.
    """
    result = apt_set_mirror.rewrite_deb822(MIXED_DEB822, ARCHIVE, SECURITY)

    stanzas = [s for s in result.split("\n\n") if s.strip()]
    assert len(stanzas) == 2

    archive_stanza = next(s for s in stanzas if ARCHIVE in s)
    security_stanza = next(s for s in stanzas if SECURITY in s)
    assert "Suites: noble noble-updates" in archive_stanza
    assert "noble-security" not in archive_stanza
    assert "Suites: noble-security" in security_stanza
    assert "noble-updates" not in security_stanza
    # Everything else about the stanza survives the split.
    assert archive_stanza.count("Components: main restricted") == 1
    assert security_stanza.count("Types: deb") == 1


def test_a_mixed_stanza_is_not_split_when_both_pockets_share_a_host():
    result = apt_set_mirror.rewrite_deb822(MIXED_DEB822, AZURE, AZURE)

    stanzas = [s for s in result.split("\n\n") if s.strip()]
    assert len(stanzas) == 2
    assert all(AZURE in s for s in stanzas)


def test_a_split_stanza_survives_a_second_pass(tmp_path: Path):
    """After splitting, each stanza is single-pocket and must stay put."""
    target = tmp_path / "ubuntu.sources"
    target.write_text(MIXED_DEB822, encoding="utf-8")

    apt_set_mirror.rewrite_file(target, ARCHIVE, SECURITY)
    once = target.read_text(encoding="utf-8")
    apt_set_mirror.rewrite_file(target, ARCHIVE, SECURITY)

    assert target.read_text(encoding="utf-8") == once


def test_a_split_stanza_leaves_exactly_one_blank_line_between_halves():
    result = apt_set_mirror.rewrite_deb822(MIXED_DEB822, ARCHIVE, SECURITY)

    assert "\n\n\n" not in result
    assert result.endswith("\n")
