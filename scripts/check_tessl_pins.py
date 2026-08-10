#!/usr/bin/env python3
"""Deploy-time check for the tessl-version-floating carve-out.

Walks every manifest covered by the carve-out (see
rules/tessl-version-floating.md) and fails if any dependency uses a specifier
other than the permitted floating value "latest" — rejecting literal pins,
version ranges, tags, and anything else per the `jbaruch/coding-policy:
dependency-management` clause "rejecting only literal pins lets a non-literal
pinned/ranged value slip through".

Every covered manifest is inspected on every run: one unreadable manifest must
not hide a pin in the next one.

Usage: check_tessl_pins.py [<repo-root>]   (default: this repo)
Stdout: one JSON object naming every covered manifest and every violation.
Stderr: actionable diagnostics for each violation.
Exit 0 when every dependency floats, 1 otherwise.

Wired into CI by .github/workflows/tests.yml, and into the publish run by
scripts/pre-publish-checks.sh.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Every manifest covered by the carve-out. Keep in sync with
# rules/tessl-version-floating.md -> "Covered Manifests".
COVERED_MANIFESTS = ("tessl.json",)

EXPECTED_SPECIFIER = "latest"


class ManifestError(Exception):
    """One covered manifest could not be inspected, with an actionable reason."""


def _read_manifest(path: Path, relative: str) -> dict:
    """Parse one covered manifest, or say exactly what stopped the check."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ManifestError(
            f"ERROR: covered manifest {relative} not found.\n"
            f"  rules/tessl-version-floating.md lists {relative} as a covered"
            f" manifest, but it does not exist on disk.\n"
            f"  Either restore the manifest or remove it from"
            f" rules/tessl-version-floating.md -> Covered Manifests."
        ) from error
    except OSError as error:
        raise ManifestError(
            f"ERROR: {relative} could not be read — {error.strerror}.\n"
            f"  Check file permissions / disk state. The check can't verify pin"
            f" status until the manifest is readable."
        ) from error
    except UnicodeError as error:
        # UnicodeDecodeError is a ValueError, not an OSError, so it would
        # otherwise escape both handlers as a traceback.
        raise ManifestError(
            f"ERROR: {relative} is not valid UTF-8 — {error}.\n"
            f"  Re-save the manifest as UTF-8, then re-run."
        ) from error

    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ManifestError(
            f"ERROR: {relative} is not valid JSON — {error.msg} "
            f"at line {error.lineno} col {error.colno}.\n"
            f"  Fix the JSON syntax error and re-run. The tessl-version-floating"
            f" check can't verify pin status until the manifest parses."
        ) from error

    if not isinstance(manifest, dict):
        raise ManifestError(
            f"ERROR: {relative} has the wrong top-level shape — expected a JSON"
            f" object, got {type(manifest).__name__}.\n"
            f'  {relative} must be a JSON object ("{{...}}"). Restore the'
            f" manifest shape before re-running the check."
        )
    return manifest


def manifest_violations(manifest: dict) -> list[dict[str, str]]:
    """Every dependency whose specifier is not the permitted floating value.

    A dependency entry that is not an object cannot carry a specifier at all,
    so it is reported as its own violation rather than skipped — skipping is
    how a non-literal pinned value slips through.

    Absence is the only thing that means "nothing declared". A present-but-
    malformed container is a violation even when it is false-valued: coercing
    ``[]``, ``""``, or ``null`` into an empty mapping would make a broken
    manifest pass vacuously, which leaves the carve-out's deterministic-
    enforcement precondition unmet.
    """
    violations: list[dict[str, str]] = []
    if "dependencies" not in manifest:
        return violations
    dependencies = manifest["dependencies"]
    if not isinstance(dependencies, dict):
        return [{"dependency": "dependencies", "specifier": repr(dependencies)}]
    for name, spec in dependencies.items():
        if not isinstance(spec, dict):
            violations.append({"dependency": name, "specifier": repr(spec)})
            continue
        version = spec.get("version")
        if version != EXPECTED_SPECIFIER:
            violations.append({"dependency": name, "specifier": repr(version)})
    return violations


def run(repo_root: Path) -> tuple[dict[str, object], list[str]]:
    """Check every covered manifest, returning the JSON report and diagnostics."""
    manifests: list[dict[str, object]] = []
    diagnostics: list[str] = []
    unreadable: list[str] = []
    all_violations: list[dict[str, str]] = []

    for relative in COVERED_MANIFESTS:
        try:
            manifest = _read_manifest(repo_root / relative, relative)
        except ManifestError as error:
            unreadable.append(relative)
            manifests.append(
                {
                    "path": relative,
                    "readable": False,
                    "violations": [],
                }
            )
            diagnostics.append(str(error))
            continue

        violations = manifest_violations(manifest)
        manifests.append({"path": relative, "readable": True, "violations": violations})
        all_violations.extend({"manifest": relative, **item} for item in violations)
        if violations:
            diagnostics.append(
                f"ERROR: {relative} contains dependencies with non-floating specifiers:"
            )
            diagnostics.extend(
                f"  {item['dependency']}: {item['specifier']}" for item in violations
            )
            diagnostics.append(
                f"  Per rules/tessl-version-floating.md, every dependency in"
                f' this manifest must use "version": "{EXPECTED_SPECIFIER}".'
                f" Pinning here produces silent drift because `tessl update`"
                f" rewrites the manifest in-place at runtime and .tessl/ is"
                f" gitignored."
            )
            diagnostics.append(
                f"  Fix: change the flagged specifier(s) to"
                f' "{EXPECTED_SPECIFIER}", or — if you intentionally want this'
                f" manifest to pin — remove it from the carve-out by editing"
                f" both rules/tessl-version-floating.md -> Covered Manifests AND"
                f" scripts/check_tessl_pins.py -> COVERED_MANIFESTS."
            )

    report: dict[str, object] = {
        "ok": not diagnostics,
        "expected_specifier": EXPECTED_SPECIFIER,
        "checked": len(COVERED_MANIFESTS),
        "unreadable": unreadable,
        "manifests": manifests,
        "violations": all_violations,
    }
    return report, diagnostics


def _print_failure(message: str) -> None:
    """Emit the failure shape of the stdout contract."""
    print(
        json.dumps(
            {
                "ok": False,
                "error": message,
                "expected_specifier": EXPECTED_SPECIFIER,
                "checked": 0,
                "unreadable": [],
                "manifests": [],
                "violations": [],
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
    # outer-boundary-process-contract: stdout is this gate's machine-readable
    # result, and its callers (pre-publish-checks.sh, the tests) read an
    # unparseable stdout as the gate having produced no verdict at all. An
    # unexpected exception propagating here would print a traceback and no
    # JSON, so the catch emits the same failure object plus an actionable
    # stderr line naming the bug. Exception, not BaseException — KeyboardInterrupt
    # and SystemExit must still propagate so the process stays killable.
    try:
        report, diagnostics = run(repo_root)
    except Exception as error:  # noqa: BLE001
        _print_failure(f"unexpected gate failure: {type(error).__name__}")
        print(
            f"ERROR: {Path(__file__).name} failed unexpectedly — "
            f"{type(error).__name__}: {error}\n"
            f"  This is a bug in the gate, not in the manifest. Re-run with a"
            f"  traceback"
            f" (`{sys.executable} -X dev {Path(__file__).resolve()}`) and report it.",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(report, indent=2, sort_keys=True))
    for line in diagnostics:
        print(line, file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
