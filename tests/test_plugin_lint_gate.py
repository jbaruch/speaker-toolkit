"""Tests for scripts/check_plugin_lint.py.

`context-artifacts` -> Plugin Structure requires a clean `tessl plugin lint`
before every publish. The publish workflow runs it only after merge, so a
frontmatter or manifest error aborted a release instead of failing the pull
request that introduced it. This gate moves the check onto every PR and makes
the advisory policy explicit, because the CLI's exit code does not express it:
`✘` fails, `⚠` is surfaced without failing.

The classification tests drive an injected fake CLI, so they are deterministic
and run anywhere. The integration test drives the real CLI.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "scripts" / "check_plugin_lint.py"

VALID_OUTPUT = "✔ Plugin acme/widget@1.0.0 is valid\n"
ADVISORY_OUTPUT = (
    "⚠ Skill 'demo': SKILL.md is approximately 12270 tokens "
    "(recommended maximum: 5000). Consider moving detailed content to "
    "separate reference files.\n\n✔ Plugin acme/widget@1.0.0 is valid\n"
)
ERROR_OUTPUT = (
    "✘ Skill 'demo': Frontmatter validation failed: [\n"
    '  {\n    "code": "too_big",\n    "maximum": 1024\n  }\n]\n'
)


def _load_gate():
    """Import the gate as a module — the entry-point guard keeps that side-effect free."""
    spec = importlib.util.spec_from_file_location("check_plugin_lint", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def gate():
    return _load_gate()


def _fake_cli(tmp_path: Path, *, output: str, exit_code: int) -> tuple[str, ...]:
    """A stand-in CLI that prints a captured lint transcript and exits as told."""
    script = tmp_path / "fake_tessl.py"
    script.write_text(
        f"import sys\nsys.stdout.write({output!r})\nraise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    return (sys.executable, str(script))


def test_a_clean_lint_passes(gate, tmp_path: Path) -> None:
    report, diagnostics = gate.run(
        REPO_ROOT, command=_fake_cli(tmp_path, output=VALID_OUTPUT, exit_code=0)
    )

    assert report["ok"] is True
    assert report["errors"] == []
    assert report["advisories"] == []
    assert not [line for line in diagnostics if line.startswith("ERROR")]


def test_a_hard_error_fails_and_is_reported(gate, tmp_path: Path) -> None:
    report, diagnostics = gate.run(
        REPO_ROOT, command=_fake_cli(tmp_path, output=ERROR_OUTPUT, exit_code=1)
    )

    assert report["ok"] is False
    assert report["lint_exit_code"] == 1
    assert "Frontmatter validation failed" in report["errors"][0]
    assert any(line.startswith("ERROR") for line in diagnostics)


def test_a_printed_error_fails_even_on_a_zero_exit(gate, tmp_path: Path) -> None:
    """An exit-code-only gate silently stops gating if the CLI changes."""
    report, _diagnostics = gate.run(
        REPO_ROOT, command=_fake_cli(tmp_path, output=ERROR_OUTPUT, exit_code=0)
    )

    assert report["ok"] is False
    assert report["errors"]


def test_an_advisory_is_surfaced_without_failing(gate, tmp_path: Path) -> None:
    report, diagnostics = gate.run(
        REPO_ROOT, command=_fake_cli(tmp_path, output=ADVISORY_OUTPUT, exit_code=0)
    )

    assert report["ok"] is True
    assert report["errors"] == []
    assert "approximately 12270 tokens" in report["advisories"][0]
    assert any(line.startswith("ADVISORY") for line in diagnostics)


def test_a_non_zero_exit_without_a_finding_still_fails(gate, tmp_path: Path) -> None:
    """A failure this gate cannot classify is still a failure."""
    report, diagnostics = gate.run(
        REPO_ROOT, command=_fake_cli(tmp_path, output="boom\n", exit_code=3)
    )

    assert report["ok"] is False
    assert report["lint_exit_code"] == 3
    assert any(
        "without printing a recognizable finding" in line for line in diagnostics
    )


def test_a_missing_cli_is_an_actionable_failure_not_a_skip(gate) -> None:
    """ci-safety -> Install, Don't Skip: an absent tool fails loudly."""
    with pytest.raises(gate.GateError, match="not on PATH"):
        gate.run(REPO_ROOT, command=("tessl-does-not-exist",))


def test_classification_ignores_the_success_line(gate) -> None:
    errors, advisories = gate.classify(VALID_OUTPUT)

    assert (errors, advisories) == ([], [])


def test_gate_is_importable_without_running() -> None:
    """file-hygiene -> Standalone Scripts: the entry-point guard makes it importable."""
    assert _load_gate().ERROR_MARKER == "✘"


# The real CLI. `tessl` is installed in CI by tesslio/setup-tessl.


def _write_plugin(root: Path, *, description: str) -> None:
    (root / ".tessl-plugin").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "demo").mkdir(parents=True, exist_ok=True)
    (root / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".tessl-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "acme/widget",
                "version": "1.0.0",
                "description": "A test plugin",
                "skills": ["skills/demo"],
                "rules": ["rules/house.md"],
            }
        ),
        encoding="utf-8",
    )
    (root / "skills" / "demo" / "SKILL.md").write_text(
        f"---\nname: demo\ndescription: {description}\n---\n\n"
        "# Demo\n\nProcess steps in order. Do not skip ahead.\n",
        encoding="utf-8",
    )
    (root / "rules" / "house.md").write_text("# House\n\n- Be nice\n", encoding="utf-8")


def _run_gate(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), str(repo)], capture_output=True, text=True
    )


def test_an_over_length_description_fails_the_gate(tmp_path: Path) -> None:
    """The failure that reached publish unchecked: description is capped at 1024."""
    assert shutil.which("tessl") is not None, (
        "the tessl CLI must be installed for this gate's integration test — "
        "CI installs it with tesslio/setup-tessl"
    )
    plugin = tmp_path / "plugin"
    _write_plugin(plugin, description="x" * 1100)

    result = _run_gate(plugin)

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["ok"] is False
    # Assert that the gate rejected, and which skill it rejected — never the
    # sentence tessl phrased it in. Two CLI versions word this rejection
    # differently and truncate it at different points ("Frontmatter validation
    # failed: [" against `SKILL.md frontmatter field "description" must be at
    # most 1024 characters.`), so any prose match passes on one and fails on the
    # other while the gate itself is correct on both.
    assert report["errors"], "an over-length description must produce an error"
    assert any("demo" in error for error in report["errors"]), (
        f"no error named the offending skill: {report['errors']}"
    )


def test_a_valid_plugin_passes_the_gate(tmp_path: Path) -> None:
    assert shutil.which("tessl") is not None
    plugin = tmp_path / "plugin"
    _write_plugin(plugin, description="A demo skill for gate tests")

    result = _run_gate(plugin)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_this_repo_passes_plugin_lint() -> None:
    """Regression guard: speaker-toolkit's own plugin structure must stay valid."""
    assert shutil.which("tessl") is not None
    result = _run_gate(REPO_ROOT)

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_workflow_annotations_never_touch_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stdout is the JSON report; CI redirects it to /dev/null."""
    plugin = tmp_path / "plugin"
    _write_plugin(plugin, description="A demo skill for gate tests")
    oversized = "Filler that pads the entrypoint past the token budget. " * 700
    (plugin / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: A demo skill\n---\n\n# Demo\n\n" + oversized,
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    result = subprocess.run(
        [sys.executable, str(GATE), str(plugin)],
        capture_output=True,
        text=True,
        env={**dict(__import__("os").environ), "GITHUB_ACTIONS": "true"},
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["advisories"]
    assert "::warning" not in result.stdout
    assert "::warning" in result.stderr


def test_a_failing_step_summary_write_emits_the_failure_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No traceback trailing a success report that already printed."""
    plugin = tmp_path / "plugin"
    _write_plugin(plugin, description="A demo skill for gate tests")
    oversized = "Filler that pads the entrypoint past the token budget. " * 700
    (plugin / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: A demo skill\n---\n\n# Demo\n\n" + oversized,
        encoding="utf-8",
    )
    unwritable = tmp_path / "no-such-dir" / "summary.md"

    result = subprocess.run(
        [sys.executable, str(GATE), str(plugin)],
        capture_output=True,
        text=True,
        env={
            **dict(__import__("os").environ),
            "GITHUB_ACTIONS": "true",
            "GITHUB_STEP_SUMMARY": str(unwritable),
        },
    )

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert "unexpected gate failure" in report["error"]
    assert "Traceback" not in result.stdout
