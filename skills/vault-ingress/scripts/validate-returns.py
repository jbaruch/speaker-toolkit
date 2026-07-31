#!/usr/bin/env python3
"""Validate a batch of vault-ingress subagent returns without writing state.

Usage:
    validate-returns.py <batch-returns.json> [--catalog-dir <patterns-dir>]

The same validator runs inside persist-results.py and write-analysis.py. This
standalone entry point is for the batch gate immediately after agents return.
It prints a structured JSON report on success and a concise stderr diagnostic
with exit code 1 on failure.
"""

import json
import sys

from return_validation import (
    ReturnValidationError,
    load_catalog,
    load_json,
    validate_batch,
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
    if len(args) != 1:
        raise ReturnValidationError(
            f"Usage: {sys.argv[0]} <batch-returns.json> [--catalog-dir <patterns-dir>]")
    return args[0], catalog_dir


def main():
    try:
        batch_path, catalog_dir = parse_args(sys.argv[1:])
        returns = load_json(batch_path, "batch-returns")
        catalog = load_catalog(catalog_dir) if catalog_dir else None
        resolved_catalog = validate_batch(returns, catalog)
    except ReturnValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    json.dump(validation_report(returns, resolved_catalog), sys.stdout,
              ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
