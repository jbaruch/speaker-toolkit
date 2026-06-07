"""Tests for skills/shownotes-publisher/scripts/content-only-gate.sh.

The gate decides whether a direct push to the protected branch would change only
the content-path allowlist (safe to direct-push, exit 0) or stray outside it
(must use branch + PR, exit 1), with exit 2 for error/empty-push states. It
covers the full push range: committed-but-unpushed changes (origin/main..HEAD)
plus pending work-tree changes (staged, unstaged, untracked).
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


def _commit(repo: Path, rel: str, body: str = "x\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    _git(repo, "add", rel)
    _git(repo, "commit", "-qm", f"add {rel}")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A work repo on `main` tracking a bare origin, seeded and pushed."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   check=True, capture_output=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin), str(work)],
                   check=True, capture_output=True)
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Test")
    _commit(work, "seed.txt", "seed\n")
    _git(work, "push", "-q", "origin", "main")
    return work


def _run(target: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(GATE), str(target), *extra],
                          capture_output=True, text=True)


def _payload(result: subprocess.CompletedProcess) -> dict:
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_content_only_worktree_change_direct_pushes(repo: Path) -> None:
    (repo / "_talks").mkdir()
    (repo / "_talks" / "geecon-2026.md").write_text("# Talk\n")
    result = _run(repo)
    assert result.returncode == 0, result.stderr
    payload = _payload(result)
    assert payload["content_only"] is True
    assert payload["changed"] == ["_talks/geecon-2026.md"]
    assert payload["outside"] == []


def test_content_plus_thumbnail_direct_pushes(repo: Path) -> None:
    (repo / "_talks").mkdir()
    (repo / "_talks" / "geecon-2026.md").write_text("# Talk\n")
    thumb = repo / "assets" / "images" / "thumbnails"
    thumb.mkdir(parents=True)
    (thumb / "geecon-2026-thumbnail.png").write_bytes(b"\x89PNG\r\n")
    result = _run(repo)
    assert result.returncode == 0, result.stderr
    assert _payload(result)["content_only"] is True


def test_non_content_worktree_file_blocks(repo: Path) -> None:
    (repo / "_talks").mkdir()
    (repo / "_talks" / "geecon-2026.md").write_text("# Talk\n")
    (repo / "_config.yml").write_text("url: https://example.com\n")
    result = _run(repo)
    assert result.returncode == 1, result.stderr
    payload = _payload(result)
    assert payload["content_only"] is False
    assert payload["outside"] == ["_config.yml"]


def test_modified_tracked_non_content_file_blocks(repo: Path) -> None:
    (repo / "seed.txt").write_text("changed\n")
    result = _run(repo)
    assert result.returncode == 1, result.stderr
    assert _payload(result)["outside"] == ["seed.txt"]


def test_unpushed_non_content_commit_blocks(repo: Path) -> None:
    # The carve-out scenario: an earlier non-content commit not yet pushed must
    # not ride along on a direct push, even if the work tree is content-only.
    _commit(repo, "_config.yml", "url: https://example.com\n")
    (repo / "_talks").mkdir()
    (repo / "_talks" / "geecon-2026.md").write_text("# Talk\n")
    result = _run(repo)
    assert result.returncode == 1, result.stderr
    payload = _payload(result)
    assert payload["content_only"] is False
    assert "_config.yml" in payload["outside"]


def test_unpushed_content_commit_direct_pushes(repo: Path) -> None:
    _commit(repo, "_talks/devoxx.md", "# Talk\n")
    result = _run(repo)
    assert result.returncode == 0, result.stderr
    payload = _payload(result)
    assert payload["content_only"] is True
    assert payload["changed"] == ["_talks/devoxx.md"]


def test_no_pending_changes_is_error(repo: Path) -> None:
    result = _run(repo)
    assert result.returncode == 2
    assert "empty" in result.stderr


def test_not_on_protected_branch_is_error(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "_talks").mkdir()
    (repo / "_talks" / "geecon-2026.md").write_text("# Talk\n")
    result = _run(repo)
    assert result.returncode == 2
    assert "protected branch" in result.stderr


def test_missing_upstream_is_error(repo: Path) -> None:
    _git(repo, "remote", "remove", "origin")
    (repo / "_talks").mkdir()
    (repo / "_talks" / "geecon-2026.md").write_text("# Talk\n")
    result = _run(repo)
    assert result.returncode == 2
    assert "origin/main" in result.stderr


def test_not_a_git_repo_is_error(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    result = _run(plain)
    assert result.returncode == 2
    assert "not a git work tree" in result.stderr
