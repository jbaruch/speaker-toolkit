"""Tests for scripts/check_skill_entrypoints.py.

The gate answers two questions about every auto-loaded SKILL.md: does it fit
Tessl's entrypoint token budget, and does every relative link in it resolve to a
file that ships? Both failures are invisible to `tessl plugin publish` — an
oversized entrypoint is a lint advisory that still publishes, and a dangling
reference only surfaces at runtime when the agent follows the pointer and finds
nothing.
"""

import json
import os
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
        ".tessl-plugin/plugin.json",
        json.dumps(
            {
                "name": "acme/widget",
                "version": "1.0.0",
                "description": "Test plugin",
                "skills": ["skills/builder", "skills/shipper"],
                "rules": ["rules/house-style.md"],
            }
        ),
    )
    _write(repo, "rules/house-style.md", "# House Style\n")
    _write(
        repo,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [notes](references/notes.md).\n",
    )
    _write(repo, "skills/builder/references/notes.md", "notes\n")
    # Not plugin content: exists in the tree, ships nowhere.
    _write(repo, "tests/helper.md", "helper\n")
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


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("[n]: references/notes.md", ["references/notes.md"]),
        ('[n]: references/notes.md "A title"', ["references/notes.md"]),
        ("[n]: <references/my notes.md>", ["references/my notes.md"]),
        # Up to three leading spaces is still a definition.
        ("   [n]: references/notes.md", ["references/notes.md"]),
        # Four is an indented code block.
        ("    [n]: references/notes.md", []),
        # Usage alone defines nothing.
        ("See [notes][n] for detail.", []),
        # Literal bracketed tags these skills use in prose are not references.
        ("[RECURRING] Presentation Patterns: ...", []),
        ("[NEW] and [CONTEXTUAL] labels", []),
    ],
)
def test_reference_definitions_are_destinations(
    markdown: str, expected: list[str]
) -> None:
    assert extract_link_destinations(markdown) == expected


def test_reference_definition_and_inline_link_both_collected() -> None:
    markdown = (
        "Use [notes][n] and [more](references/more.md).\n\n[n]: references/notes.md\n"
    )
    assert sorted(extract_link_destinations(markdown)) == [
        "references/more.md",
        "references/notes.md",
    ]


def test_fenced_blocks_and_inline_spans_are_excluded() -> None:
    markdown = (
        "# T\n\n"
        "```markdown\n- [{title}]({url})\n- [View](nope/missing.md)\n```\n\n"
        "Wrap it as `[text](inline.md)` — bare URLs don't render.\n\n"
        "But [this](real.md) counts.\n"
    )
    assert extract_link_destinations(markdown) == ["real.md"]


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        # Single-backtick span.
        ("Wrap it as `[t](gone.md)` — ok.", []),
        # Double run: pairing single backticks would split at the first two
        # characters and leak the link.
        ("Use ``[x](gone.md)`` here.", []),
        # A longer run exists precisely so the span can hold a lone backtick.
        ("Use ``a ` [y](gone.md)`` here.", []),
        # A run only closes on an equal-length run.
        ("Mid-line ```[z](gone.md)``` and [yes](real.md)", ["real.md"]),
        # An unterminated run is literal text, not an open span.
        ("A `stray tick and [real](kept.md)", ["kept.md"]),
        # Text after a closed span is still scanned.
        ("`code` then [after](later.md)", ["later.md"]),
    ],
)
def test_code_spans_use_delimiter_runs(markdown: str, expected: list[str]) -> None:
    assert extract_link_destinations(markdown) == expected


def test_line_starting_with_a_backtick_run_is_a_fence() -> None:
    """CommonMark reads a line-leading run as a fence, not an inline span."""
    assert extract_link_destinations("```[z](gone.md)``` and [no](x.md)") == []


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
    assert "will not resolve in the published plugin" in result.stderr
    assert "references/missing.md" in result.stderr
    report = json.loads(result.stdout)
    links = report["entrypoints"][0]["dangling_links"]
    assert [link["destination"] for link in links] == ["references/missing.md"]
    assert links[0]["reason"] == "missing"


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


def test_target_outside_declared_content_fails(plugin: Path) -> None:
    """`tests/helper.md` exists in the tree but ships in no package.

    Existence alone was the old check, and it green-lit exactly the runtime
    dangling reference this gate exists to block.
    """
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [helper](../../tests/helper.md).\n",
    )
    result = _run(plugin)
    assert result.returncode == 1
    assert "not declared plugin content" in result.stderr
    assert "tests/helper.md" in result.stderr


def test_target_escaping_the_repository_fails(plugin: Path) -> None:
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [outside](../../../elsewhere.md).\n",
    )
    result = _run(plugin)
    assert result.returncode == 1
    assert "escapes the repository" in result.stderr


def test_target_excluded_by_tesslignore_fails(plugin: Path) -> None:
    """Declared content a .tesslignore pattern strips is equally absent."""
    _write(plugin, "skills/builder/references/draft.md", "draft\n")
    _write(plugin, ".tesslignore", "draft.md\n")
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [draft](references/draft.md).\n",
    )
    result = _run(plugin)
    assert result.returncode == 1
    assert "excluded from the package by .tesslignore" in result.stderr


def test_a_rule_file_is_valid_plugin_content(plugin: Path) -> None:
    """`rules/` is declared too — a cross-directory link there still ships."""
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [style](../../rules/house-style.md).\n",
    )
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_dangling_reference_definition_fails(plugin: Path) -> None:
    """A reference-style link bypassed the gate entirely."""
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [notes][n] for detail.\n\n[n]: references/missing.md\n",
    )
    result = _run(plugin)
    assert result.returncode == 1
    assert "references/missing.md" in result.stderr


def test_resolving_reference_definition_passes(plugin: Path) -> None:
    _write(
        plugin,
        "skills/builder/SKILL.md",
        "# Builder\n\nSee [notes][n] for detail.\n\n[n]: references/notes.md\n",
    )
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_non_utf8_entrypoint_fails_with_an_encoding_message(plugin: Path) -> None:
    """UnicodeDecodeError is a ValueError — the OSError handler never sees it."""
    (plugin / "skills" / "builder" / "SKILL.md").write_bytes(b"# Builder\n\n\xff\xfe\n")
    result = _run(plugin)
    assert result.returncode != 0
    assert "not valid UTF-8" in result.stderr
    assert "Traceback" not in result.stderr


def test_non_utf8_manifest_fails_with_an_encoding_message(plugin: Path) -> None:
    (plugin / ".tessl-plugin" / "plugin.json").write_bytes(b'{"name": "\xff\xfe"}')
    result = _run(plugin)
    assert result.returncode != 0
    assert "not valid UTF-8" in result.stderr
    assert "Traceback" not in result.stderr


def test_missing_manifest_fails(plugin: Path) -> None:
    (plugin / ".tessl-plugin" / "plugin.json").unlink()
    result = _run(plugin)
    assert result.returncode != 0
    assert "could not read .tessl-plugin/plugin.json" in result.stderr


def test_malformed_manifest_fails(plugin: Path) -> None:
    _write(plugin, ".tessl-plugin/plugin.json", "{not json")
    result = _run(plugin)
    assert result.returncode != 0
    assert "not valid JSON" in result.stderr


def test_manifest_declaring_no_content_fails(plugin: Path) -> None:
    """Without declared content the gate would pass every link vacuously."""
    _write(
        plugin,
        ".tessl-plugin/plugin.json",
        json.dumps({"name": "acme/widget", "version": "1.0.0", "description": "d"}),
    )
    result = _run(plugin)
    assert result.returncode != 0
    assert "declares neither" in result.stderr


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
    assert "will not resolve in the published plugin" in result.stderr


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


def test_unreachable_git_fails_with_json_not_a_traceback(plugin: Path) -> None:
    """The .tesslignore test shells out; git missing must not crash the gate."""
    _write(plugin, ".tesslignore", "nothing-matches\n")
    (plugin / "no-tools").mkdir()
    env = {**os.environ, "PATH": str(plugin / "no-tools")}
    result = subprocess.run(
        [sys.executable, str(GATE), str(plugin)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert json.loads(result.stdout)["ok"] is False
    assert "git" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "break_it",
    [
        pytest.param(lambda p: (p / "skills").rename(p / "elsewhere"), id="no-skills"),
        pytest.param(
            lambda p: (p / ".tessl-plugin" / "plugin.json").unlink(), id="no-manifest"
        ),
        pytest.param(
            lambda p: (p / ".tessl-plugin" / "plugin.json").write_text("{nope"),
            id="bad-manifest",
        ),
    ],
)
def test_every_failure_path_still_emits_json(plugin: Path, break_it) -> None:
    """The stdout contract is "one JSON object", including on failure.

    An empty stdout makes "the gate said no" indistinguishable from "the gate
    crashed" without parsing stderr.
    """
    break_it(plugin)
    result = _run(plugin)
    assert result.returncode != 0
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert report["error"]
    assert result.stderr.strip()
    assert "Traceback" not in result.stderr


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
