"""Tests for skills/shownotes-publisher/scripts/content-only-gate.sh.

The gate decides whether a git work tree's pending changes touch only the
content-path allowlist (safe to direct-push) or stray outside it (must use
branch + PR). Exit codes: 0 content-only, 1 not, 2 error.
"""

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "skills" / "shownotes-publisher" / "scripts" / "content-only-gate.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A git repo with one committed file, so HEAD exists."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "seed.txt").write_text("seed\n")
    _git(tmp_path, "add", "seed.txt")
    _git(tmp_path, "commit", "-qm", "seed")
    return tmp_path


def _run(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(GATE), str(target)],
                          capture_output=True, text=True)


def test_only_talk_file_is_content_only(repo: Path) -> None:
    (repo / "_talks").mkdir()
    (repo / "_talks" / "geecon-2026.md").write_text("# Talk\n")
    result = _run(repo)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["content_only"] is True
    assert payload["changed"] == ["_talks/geecon-2026.md"]
    assert payload["outside"] == []


def test_talk_plus_thumbnail_is_content_only(repo: Path) -> None:
    (repo / "_talks").mkdir()
    (repo / "_talks" / "geecon-2026.md").write_text("# Talk\n")
    thumb_dir = repo / "assets" / "images" / "thumbnails"
    thumb_dir.mkdir(parents=True)
    (thumb_dir / "geecon-2026-thumbnail.png").write_bytes(b"\x89PNG\r\n")
    result = _run(repo)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["content_only"] is True
    assert set(payload["changed"]) == {
        "_talks/geecon-2026.md",
        "assets/images/thumbnails/geecon-2026-thumbnail.png",
    }
    assert payload["outside"] == []


def test_non_content_file_blocks_direct_push(repo: Path) -> None:
    (repo / "_talks").mkdir()
    (repo / "_talks" / "geecon-2026.md").write_text("# Talk\n")
    (repo / "_config.yml").write_text("url: https://example.com\n")
    result = _run(repo)
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["content_only"] is False
    assert payload["outside"] == ["_config.yml"]


def test_modified_tracked_non_content_file_blocks(repo: Path) -> None:
    (repo / "seed.txt").write_text("changed\n")
    result = _run(repo)
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["content_only"] is False
    assert payload["outside"] == ["seed.txt"]


def test_no_pending_changes_is_error(repo: Path) -> None:
    result = _run(repo)
    assert result.returncode == 2
    assert "no pending changes" in result.stderr


def test_not_a_git_repo_is_error(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "not a git work tree" in result.stderr
