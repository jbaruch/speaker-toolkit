#!/usr/bin/env python3
"""Gate: `tessl plugin lint` must pass before a change can reach publish.

`context-artifacts` -> Plugin Structure says "Validate structure with
`tessl plugin lint` before every publish". The publish workflow does run it, but
only after merge — a manifest or frontmatter error therefore aborted a release
instead of failing the pull request that introduced it. This gate moves that
check onto every PR.

Advisory policy, explicit because the CLI's exit code does not express it:

- `✘` (hard error: frontmatter validation, manifest/skill structure, orphaned
  declared paths) fails the build. `tessl plugin lint` already exits non-zero
  for these; this gate also fails on a printed `✘` with a zero exit, so a CLI
  change that stops exiting non-zero cannot silently un-gate the repo.
- `⚠` (advisory) does not fail the build, and is surfaced as a GitHub warning
  annotation plus a line on stderr so it cannot pass unnoticed. The only
  advisory lint currently raises for this repo is entrypoint size, which
  scripts/check_skill_entrypoints.py already gates deterministically and more
  conservatively — a pass there implies a pass here. Failing on `⚠` would
  double-gate that one and would turn any advisory a future CLI adds into an
  instant build break with no owner decision behind it.

The CLI version is pinned in .github/workflows/tests.yml, with the renewal
cadence recorded beside the pin. This gate exists to predict what the publish
run's own `tessl plugin lint` will say, and that step installs the latest CLI,
so a pin left to rot can pass against an older ruleset and still break the
release: renew quarterly, or as soon as the two disagree.

Usage: check_plugin_lint.py [<repo-root>]   (default: this repo)
Stdout: one JSON object naming every error and advisory lint reported.
Stderr: the CLI's own output, plus one actionable line per finding.
Exit 0 when lint reports no error, 1 otherwise.

Wired into CI by .github/workflows/tests.yml. Deliberately NOT in
scripts/pre-publish-checks.sh: the publish workflow already runs
`tessl plugin lint` as its own step, and it runs the composer before the CLI is
installed, precisely because the composer's gates are self-contained. Adding
this one there would duplicate the publish-path check and give the composer a
tessl dependency it does not otherwise have.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

LINT_COMMAND = ("tessl", "plugin", "lint")

ERROR_MARKER = "✘"
ADVISORY_MARKER = "⚠"


class GateError(Exception):
    """An expected gate failure carrying an actionable, already-formatted message."""


def run_lint(repo_root: Path, *, command: tuple[str, ...] = LINT_COMMAND):
    """Run the CLI against ``repo_root`` and return its completed process."""
    try:
        return subprocess.run(  # noqa: S603
            [*command, str(repo_root)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise GateError(
            f"ERROR: {command[0]} is not on PATH, so plugin structure cannot be"
            f" validated — {error}.\n"
            f"  Install it with the tesslio/setup-tessl action in CI, or"
            f" `curl -fsSL https://install.tessl.io | sh` locally, then re-run."
        ) from error
    except OSError as error:
        raise GateError(
            f"ERROR: could not run {' '.join(command)} — {error}.\n"
            f"  Check the CLI installation, then re-run."
        ) from error


def classify(output: str) -> tuple[list[str], list[str]]:
    """Split lint output into its error and advisory finding lines.

    A finding's first line carries the marker; a hard error may be followed by
    an indented detail block (the frontmatter validator prints JSON). The
    marker lines are the report; the untouched output goes to stderr, so no
    detail is lost by summarizing here.
    """
    errors: list[str] = []
    advisories: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(ERROR_MARKER):
            errors.append(stripped[len(ERROR_MARKER) :].strip())
        elif stripped.startswith(ADVISORY_MARKER):
            advisories.append(stripped[len(ADVISORY_MARKER) :].strip())
    return errors, advisories


def run(repo_root: Path, *, command: tuple[str, ...] = LINT_COMMAND):
    """Lint one plugin repo, returning its JSON report and stderr diagnostics."""
    completed = run_lint(repo_root, command=command)
    output = f"{completed.stdout}\n{completed.stderr}"
    errors, advisories = classify(output)

    diagnostics: list[str] = []
    if completed.stdout.strip():
        diagnostics.append(completed.stdout.rstrip())
    if completed.stderr.strip():
        diagnostics.append(completed.stderr.rstrip())

    for advisory in advisories:
        diagnostics.append(f"ADVISORY: tessl plugin lint — {advisory}")
    if advisories:
        diagnostics.append(
            "  Advisories do not fail this gate. Entrypoint size is separately"
            " gated by scripts/check_skill_entrypoints.py; any other advisory"
            " is a new lint rule that needs an owner decision."
        )

    # Fail on a printed error even when the CLI exited zero: the marker is the
    # finding, and an exit-code-only gate would silently stop gating if the CLI
    # ever changed how it reports.
    failed = bool(errors) or completed.returncode != 0
    if errors:
        diagnostics.append(
            f"ERROR: tessl plugin lint reported {len(errors)} structural error(s):"
        )
        diagnostics.extend(f"  {error}" for error in errors)
        diagnostics.append(
            "  Fix the reported structure or frontmatter and re-run"
            " `tessl plugin lint`. context-artifacts -> Plugin Structure"
            " requires a clean lint before every publish."
        )
    elif completed.returncode != 0:
        diagnostics.append(
            f"ERROR: tessl plugin lint exited {completed.returncode} without"
            f" printing a recognizable finding."
        )
        diagnostics.append(
            "  Read the CLI output above. A non-zero exit is a failure whether"
            " or not this gate could classify it."
        )

    report: dict[str, object] = {
        "ok": not failed,
        "lint_exit_code": completed.returncode,
        "errors": errors,
        "advisories": advisories,
    }
    return report, diagnostics


def _emit_workflow_annotations(advisories: list[str]) -> None:
    """Surface advisories where a GitHub reviewer will actually see them.

    Workflow commands go to stderr, never stdout: stdout is reserved for the
    single JSON report, and the CI step redirects it to /dev/null, which would
    swallow the annotations along with the report.
    """
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    for advisory in advisories:
        print(f"::warning title=tessl plugin lint::{advisory}", file=sys.stderr)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path or not advisories:
        return
    with open(summary_path, "a", encoding="utf-8") as summary:
        summary.write("### `tessl plugin lint` advisories\n\n")
        for advisory in advisories:
            summary.write(f"- {advisory}\n")


def _print_failure(message: str) -> None:
    """Emit the failure shape of the stdout contract."""
    print(
        json.dumps(
            {
                "ok": False,
                "error": message,
                "lint_exit_code": None,
                "errors": [],
                "advisories": [],
            },
            indent=2,
            sort_keys=True,
        )
    )


def main(argv: list[str]) -> int:
    repo_root = (
        Path(argv[1]).resolve()
        if len(argv) > 1
        else Path(__file__).resolve().parent.parent
    )
    try:
        report, diagnostics = run(repo_root)
        # Inside the guarded region and before stdout: a failure writing the
        # step summary must produce the structured failure object, not a
        # traceback trailing a success report that already printed.
        _emit_workflow_annotations([str(item) for item in report["advisories"]])
    except GateError as error:
        # Every run emits one JSON object, including the ones that fail before
        # the CLI produced a verdict — a consumer reading stdout must never
        # have to tell "gate said no" apart from "gate crashed".
        _print_failure(str(error).splitlines()[0])
        print(error, file=sys.stderr)
        return 1
    # outer-boundary-process-contract: stdout is this gate's machine-readable
    # result, and its callers (CI, the tests) read an unparseable stdout as the
    # gate having produced no verdict at all. An unexpected exception
    # propagating here would print a traceback and no JSON, so the catch emits
    # the same failure object plus an actionable stderr line naming the bug.
    # Exception, not BaseException — KeyboardInterrupt and SystemExit must
    # still propagate so the process stays killable.
    except Exception as error:  # noqa: BLE001
        _print_failure(f"unexpected gate failure: {type(error).__name__}")
        print(
            f"ERROR: {Path(__file__).name} failed unexpectedly — "
            f"{type(error).__name__}: {error}\n"
            f"  This is a bug in the gate, not in the plugin. Re-run with a"
            f" traceback"
            f" (`{sys.executable} -X dev {Path(__file__).resolve()}`) and"
            f" report it.",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(report, indent=2, sort_keys=True))
    for line in diagnostics:
        print(line, file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
