#!/usr/bin/env python3
"""Validate a batch of vault-ingress subagent returns without writing state.

Usage:
    validate-returns.py <batch-or-return.json> [...] [--catalog-dir <patterns-dir>]

Each input may be one return object, an array of returns, or a directory of
`*.json` return files. Inputs are flattened into one batch, so duplicate talk
filenames are caught across files and directories.

The same validator runs inside persist-results.py and write-analysis.py. This
standalone entry point is for the batch gate immediately after agents return.
It prints a structured JSON report on success and a concise stderr diagnostic
with exit code 1 on failure.
"""

import json
import sys
from pathlib import Path

from failure_diagnostics import emit_unexpected_failure
from return_validation import (
    ReturnValidationError,
    audit_batch,
    load_catalog,
    load_json,
    validation_report,
)


def parse_args(argv):
    args, catalog_dir = [], None
    index = 0
    while index < len(argv):
        if argv[index] == "--catalog-dir":
            if index + 1 >= len(argv):
                raise ReturnValidationError("--catalog-dir requires a path")
            catalog_dir = argv[index + 1]
            index += 2
            continue
        args.append(argv[index])
        index += 1
    if not args:
        raise ReturnValidationError(
            f"Usage: {sys.argv[0]} <batch-or-return.json> [...] "
            "[--catalog-dir <patterns-dir>]"
        )
    return args, catalog_dir


def load_inputs(paths):
    """Flatten return objects and arrays from files or shallow directories."""
    returns = []
    files = []
    for raw in paths:
        path = Path(raw)
        candidates = sorted(path.glob("*.json")) if path.is_dir() else [path]
        if path.is_dir() and not candidates:
            raise ReturnValidationError(
                f"return directory contains no *.json files: {path}"
            )
        for candidate in candidates:
            payload = load_json(candidate, "return")
            files.append(str(candidate))
            if isinstance(payload, dict):
                returns.append(payload)
            elif isinstance(payload, list):
                returns.extend(payload)
            else:
                raise ReturnValidationError(
                    f"return file {candidate} must contain an object or array, "
                    f"got {type(payload).__name__}"
                )
    return returns, files


def main():
    try:
        input_paths, catalog_dir = parse_args(sys.argv[1:])
        returns, files = load_inputs(input_paths)
        catalog = load_catalog(catalog_dir) if catalog_dir else None
        resolved_catalog, errors = audit_batch(returns, catalog)
        if errors:
            for error in errors:
                print(f"ERROR: {error['error']}", file=sys.stderr)
            print(
                f"ERROR: {len(errors)} validation error(s) across "
                f"{len(returns)} return(s)",
                file=sys.stderr,
            )
            sys.exit(1)
    except ReturnValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    report = validation_report(returns, resolved_catalog)
    report["input_files"] = files
    # Serialize before writing: a `json.dump` straight to stdout that fails
    # partway leaves a truncated document the batch gate would try to parse.
    sys.stdout.write(json.dumps(report, ensure_ascii=False) + "\n")


def run_cli() -> int:
    """Run the CLI behind its failure boundary. Returns the process exit code.

    Importable so the boundary's contract is testable without executing the
    module as a script.
    """
    try:
        main()
    # The batch gate runs this immediately after agents return and reads a
    # non-zero exit as "the batch is not validated"; emit one closed stderr
    # document because a traceback would leak return paths and rejected values
    # into the gate's log, and the gate could not tell a failed validation from
    # a failed validator.
    except Exception as exc:  # noqa: BLE001 - outer-boundary-process-contract
        emit_unexpected_failure(
            exc,
            "validate_returns_unexpected_failure",
            "vault-ingress return validation failed unexpectedly. This script "
            "writes no state, so nothing was changed — but the batch is "
            "UNVALIDATED and must not be persisted until a clean run reports "
            "on stdout.",
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
