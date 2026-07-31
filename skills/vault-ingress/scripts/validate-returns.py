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
            "[--catalog-dir <patterns-dir>]")
    return args, catalog_dir


def load_inputs(paths):
    """Flatten return objects and arrays from files or shallow directories."""
    returns = []
    files = []
    for raw in paths:
        path = Path(raw)
        candidates = sorted(path.glob("*.json")) if path.is_dir() else [path]
        if path.is_dir() and not candidates:
            raise ReturnValidationError(f"return directory contains no *.json files: {path}")
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
                    f"got {type(payload).__name__}")
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
            print(f"ERROR: {len(errors)} validation error(s) across "
                  f"{len(returns)} return(s)", file=sys.stderr)
            sys.exit(1)
    except ReturnValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    report = validation_report(returns, resolved_catalog)
    report["input_files"] = files
    json.dump(report, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
