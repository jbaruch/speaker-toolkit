"""Tests for scripts/check-skill-entrypoints.sh.

The gate answers two questions about every auto-loaded SKILL.md: does it fit
Tessl's entrypoint token budget, and does every relative link in it resolve to a
file that ships? Both failures are invisible to `tessl plugin publish` — an
oversized entrypoint is a lint advisory that still publishes, and a dangling
reference only surfaces at runtime when the agent follows the pointer and finds
nothing.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "scripts" / "check-skill-entrypoints.sh"

# The gate's own budget, mirrored here so a test failure names the number the
# script enforces rather than a second copy that could drift.
TOKEN_BUDGET = 5000
CHARS_PER_TOKEN = 4
# Chars that estimate to exactly TOKEN_BUDGET; one more char tips it over.
BUDGET_CHARS = TOKEN_BUDGET * CHARS_PER_TOKEN


def _write(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def _run(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(GATE), str(repo)], capture_output=True, text=True)


def _body(chars: int) -> str:
    """A SKILL.md body of exactly `chars` bytes."""
    header = "# Skill\n\n"
    return header + "x" * (chars - len(header))


@pytest.fixture()
def plugin(tmp_path: Path) -> Path:
    """A plugin with one small, link-clean skill entrypoint."""
    repo = tmp_path / "plugin"
    repo.mkdir()
    _write(
        repo,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [notes](references/notes.md).\n",
    )
    _write(repo, "skills/builder/references/notes.md", "notes\n")
    return repo


def test_clean_plugin_passes(plugin: Path) -> None:
    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    assert "all 1 skill entrypoints are within 5000 tokens" in result.stdout


def test_oversized_entrypoint_fails(plugin: Path) -> None:
    _write(plugin, "skills/builder/SKILL.md", _body(BUDGET_CHARS + 400))
    result = _run(plugin)
    assert result.returncode == 1
    assert "exceed the 5000-token budget" in result.stderr
    assert "skills/builder/SKILL.md" in result.stderr
    assert "over budget" in result.stderr


def test_entrypoint_exactly_at_budget_passes(plugin: Path) -> None:
    """The budget is a maximum, not an exclusive bound."""
    _write(plugin, "skills/builder/SKILL.md", _body(BUDGET_CHARS))
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_one_char_over_budget_fails(plugin: Path) -> None:
    """Guards the boundary in the other direction — the gate is not slack."""
    _write(plugin, "skills/builder/SKILL.md", _body(BUDGET_CHARS + CHARS_PER_TOKEN))
    result = _run(plugin)
    assert result.returncode == 1
    assert "exceed the 5000-token budget" in result.stderr


def test_dangling_relative_link_fails(plugin: Path) -> None:
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [gone](references/missing.md).\n",
    )
    result = _run(plugin)
    assert result.returncode == 1
    assert "resolve to nothing" in result.stderr
    assert "references/missing.md" in result.stderr


def test_link_with_anchor_resolves_to_the_file(plugin: Path) -> None:
    """A #fragment addresses a heading inside the file, not a different path."""
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [notes](references/notes.md#section-two).\n",
    )
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_external_urls_are_not_treated_as_paths(plugin: Path) -> None:
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\n[docs](https://example.com/x) and [mail](mailto:a@example.com).\n",
    )
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_links_inside_fenced_code_blocks_are_ignored(plugin: Path) -> None:
    """A fenced block is sample output the skill emits, not pointers it follows."""
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\n```markdown\n- [{title}]({url})\n- [View](nope/missing.md)\n```\n",
    )
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_links_inside_inline_code_spans_are_ignored(plugin: Path) -> None:
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nWrap it as `[text](url)` — bare URLs don't render.\n",
    )
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_placeholder_targets_are_ignored(plugin: Path) -> None:
    """Runtime-substituted `{...}` targets are values, not repo paths."""
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\n**Video:** [View Video]({video_url})\n",
    )
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_a_reference_pointing_at_a_directory_passes(plugin: Path) -> None:
    """Some skills link a directory of references, not a single file."""
    _write(plugin, "skills/builder/references/patterns/_index.md", "index\n")
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [patterns](references/patterns/).\n",
    )
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_both_failures_report_together(plugin: Path) -> None:
    """One run surfaces every problem — no fix-one-rerun-find-another loop."""
    _write(
        plugin,
        "skills/builder/SKILL.md",
        _body(BUDGET_CHARS + 400) + "\n\nSee [gone](references/missing.md).\n",
    )
    result = _run(plugin)
    assert result.returncode == 1
    assert "exceed the 5000-token budget" in result.stderr
    assert "resolve to nothing" in result.stderr


def test_every_entrypoint_is_checked_not_just_the_first(plugin: Path) -> None:
    _write(plugin, "skills/shipper/SKILL.md", _body(BUDGET_CHARS + 400))
    result = _run(plugin)
    assert result.returncode == 1
    assert "skills/shipper/SKILL.md" in result.stderr
    assert "1 of 2 skill entrypoints" in result.stderr


def test_missing_skills_directory_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run(empty)
    assert result.returncode == 1
    assert "no skills/ directory" in result.stderr


def test_skills_directory_without_entrypoints_fails(tmp_path: Path) -> None:
    """A layout with no SKILL.md must fail loudly, not pass vacuously."""
    repo = tmp_path / "plugin"
    (repo / "skills" / "builder").mkdir(parents=True)
    result = _run(repo)
    assert result.returncode == 1
    assert "contains no */SKILL.md entrypoints" in result.stderr


def test_this_repo_keeps_every_entrypoint_in_budget() -> None:
    """Regression guard: speaker-toolkit's own skills stay lint-advisory-free."""
    result = subprocess.run([str(GATE)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_runs_in_the_publish_composer() -> None:
    """The gate is worthless if nothing invokes it before a publish."""
    composer = (REPO_ROOT / "scripts" / "pre-publish-checks.sh").read_text()
    assert "check-skill-entrypoints.sh" in composer
