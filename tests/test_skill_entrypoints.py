"""Tests for scripts/check_skill_entrypoints.py.

The gate answers two questions about every auto-loaded SKILL.md: does it fit
Tessl's entrypoint token budget, and does every relative link in it resolve to a
file that ships? Both failures are invisible to `tessl plugin publish` — an
oversized entrypoint is a lint advisory that still publishes, and a dangling
reference only surfaces at runtime when the agent follows the pointer and finds
nothing.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from check_skill_entrypoints import (
    CHARS_PER_TOKEN,
    TOKEN_BUDGET,
    estimate_tokens,
    extract_link_destinations,
    is_repo_relative,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "scripts" / "check_skill_entrypoints.py"

# Chars that estimate to exactly TOKEN_BUDGET; one more char tips it over.
BUDGET_CHARS = TOKEN_BUDGET * CHARS_PER_TOKEN


def _write(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def _run(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), str(repo)], capture_output=True, text=True
    )


def _body(chars: int) -> str:
    """A SKILL.md body of exactly `chars` characters."""
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


# --- link destination grammar -------------------------------------------------


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("[a](plain.md)", ["plain.md"]),
        # A title after the destination is not part of the path.
        ('[a](notes.md "A title")', ["notes.md"]),
        ("[a](notes.md 'A title')", ["notes.md"]),
        ("[a](notes.md (A title))", ["notes.md"]),
        # Balanced parentheses belong to the destination.
        ("[a](refs/note_(draft).md)", ["refs/note_(draft).md"]),
        ("[a](refs/a_(b)_(c).md)", ["refs/a_(b)_(c).md"]),
        # Angle-bracket form carries spaces.
        ("[a](<my notes.md>)", ["my notes.md"]),
        ('[a](<refs/with space.md> "t")', ["refs/with space.md"]),
        # Backslash escapes.
        (r"[a](refs/lit\(paren\).md)", ["refs/lit(paren).md"]),
        (r"[a](refs/space\ name.md)", ["refs/space name.md"]),
        # Several links on one line, in source order.
        ("[a](one.md) then [b](two.md)", ["one.md", "two.md"]),
        # Not links.
        ("[a](", []),
        ("plain text with ] and ( apart", []),
        ("[a]()", []),
    ],
)
def test_destination_grammar(markdown: str, expected: list[str]) -> None:
    assert extract_link_destinations(markdown) == expected


@pytest.mark.parametrize(
    "markdown",
    [
        # No closing paren — the angle-bracket destination is not a link.
        "[x](<missing.md>",
        # No closing paren after a title.
        '[x](missing.md "title"',
        # Title opens and never closes.
        '[x](missing.md "title)',
        "[x](missing.md 'title)",
        # Angle-bracket destination never closes.
        "[x](<missing.md",
        # Trailing junk between destination and the closing paren.
        "[x](missing.md junk)",
    ],
)
def test_malformed_links_yield_no_destination(markdown: str) -> None:
    """A malformed construct is not a link, so it cannot be a dangling one.

    Reporting these as live relative links would falsely block a publish.
    """
    assert extract_link_destinations(markdown) == []


def test_a_malformed_link_does_not_swallow_a_later_real_one() -> None:
    assert extract_link_destinations("[a](<broken.md and [b](real.md)") == ["real.md"]


def test_fenced_blocks_and_inline_spans_are_excluded() -> None:
    markdown = (
        "# T\n\n"
        "```markdown\n- [{title}]({url})\n- [View](nope/missing.md)\n```\n\n"
        "Wrap it as `[text](inline.md)` — bare URLs don't render.\n\n"
        "But [this](real.md) counts.\n"
    )
    assert extract_link_destinations(markdown) == ["real.md"]


@pytest.mark.parametrize(
    ("destination", "expected"),
    [
        ("references/notes.md", True),
        ("references/notes.md#anchor", True),
        ("../shared/notes.md", True),
        ("https://example.com/x", False),
        ("mailto:a@example.com", False),
        ("#in-page-anchor", False),
        ("/absolute/path.md", False),
        ("{video_url}", False),
        ("refs/{slug}.md", False),
    ],
)
def test_repo_relative_classification(destination: str, expected: bool) -> None:
    assert is_repo_relative(destination) is expected


# --- token budget -------------------------------------------------------------


@pytest.mark.parametrize(
    ("chars", "tokens"),
    [(0, 0), (1, 1), (4, 1), (5, 2), (20000, 5000), (20001, 5001)],
)
def test_token_estimate_is_a_ceiling(chars: int, tokens: int) -> None:
    assert estimate_tokens("x" * chars) == tokens


def test_clean_plugin_passes(plugin: Path) -> None:
    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["checked"] == 1
    assert report["oversized"] == []
    assert report["dangling"] == []


def test_oversized_entrypoint_fails(plugin: Path) -> None:
    _write(plugin, "skills/builder/SKILL.md", _body(BUDGET_CHARS + 400))
    result = _run(plugin)
    assert result.returncode == 1
    assert "exceed the 5000-token budget" in result.stderr
    assert "skills/builder/SKILL.md" in result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert report["oversized"] == ["skills/builder/SKILL.md"]


def test_entrypoint_exactly_at_budget_passes(plugin: Path) -> None:
    """The budget is a maximum, not an exclusive bound."""
    _write(plugin, "skills/builder/SKILL.md", _body(BUDGET_CHARS))
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("excess", range(1, CHARS_PER_TOKEN + 1))
def test_any_char_over_budget_fails(plugin: Path, excess: int) -> None:
    """Guards the boundary in the other direction — the gate is not slack.

    Every excess below CHARS_PER_TOKEN is the interesting case: truncating
    integer division reports 20,001..20,003 chars as exactly 5,000 tokens and
    passes a file that is over budget. Only a ceiling fails all four.
    """
    _write(plugin, "skills/builder/SKILL.md", _body(BUDGET_CHARS + excess))
    result = _run(plugin)
    assert result.returncode == 1, f"{BUDGET_CHARS + excess} chars passed the gate"
    assert "exceed the 5000-token budget" in result.stderr


# --- link resolution ----------------------------------------------------------


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
    report = json.loads(result.stdout)
    assert report["entrypoints"][0]["dangling_links"] == ["references/missing.md"]


def test_link_with_anchor_resolves_to_the_file(plugin: Path) -> None:
    """A #fragment addresses a heading inside the file, not a different path."""
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [notes](references/notes.md#section-two).\n",
    )
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_titled_link_to_a_real_file_passes(plugin: Path) -> None:
    """A title must not be glued onto the path and reported as dangling."""
    _write(
        plugin,
        "skills/builder/SKILL.md",
        '# Builder\n\nSee [notes](references/notes.md "The notes").\n',
    )
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_parenthesized_filename_resolves(plugin: Path) -> None:
    _write(plugin, "skills/builder/references/note_(draft).md", "draft\n")
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [draft](references/note_(draft).md).\n",
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


# --- aggregation and failure modes -------------------------------------------


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


def test_unreadable_entrypoint_fails_loudly(plugin: Path) -> None:
    """A file the scanner cannot read must not read as "no links found"."""
    target = plugin / "skills" / "builder" / "SKILL.md"
    target.chmod(0o000)
    try:
        result = _run(plugin)
    finally:
        target.chmod(0o644)
    assert result.returncode != 0
    assert "could not scan" in result.stderr


def test_missing_skills_directory_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run(empty)
    assert result.returncode != 0
    assert "no skills/ directory" in result.stderr


def test_skills_directory_without_entrypoints_fails(tmp_path: Path) -> None:
    """A layout with no SKILL.md must fail loudly, not pass vacuously."""
    repo = tmp_path / "plugin"
    (repo / "skills" / "builder").mkdir(parents=True)
    result = _run(repo)
    assert result.returncode != 0
    assert "contains no */SKILL.md entrypoints" in result.stderr


def test_this_repo_keeps_every_entrypoint_in_budget() -> None:
    """Regression guard: speaker-toolkit's own skills stay lint-advisory-free."""
    result = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_gate_runs_in_the_publish_composer() -> None:
    """The gate is worthless if nothing invokes it before a publish."""
    composer = (REPO_ROOT / "scripts" / "pre-publish-checks.sh").read_text()
    assert "check_skill_entrypoints.py" in composer
