#!/usr/bin/env python3
"""Complete weighted returns by filling in the pattern_score_basis they require.

The basis is a pure function of a return's detection lanes and its
not-evaluable ledger, and inserting it is a mechanical JSON edit, so both steps
belong in a script rather than in a worker's reasoning. `return_validation`
owns the weight table and the object's shape; this is a thin entry point onto
that owner, so no caller reproduces either or decides where the field goes.

Return schemas v6 and v7 share scoring schema v6 and therefore require the same
basis. Usage:
    build-score-basis.py <return.json> [...]

Each input is one return object or an array of return objects. The output is
those same returns with `pattern_observations.pattern_score_basis` set — one
object for a single return, an array for several — ready to pass straight to
`validate-returns.py`.

Exit 0 on success. Exit 2 on unreadable, malformed, or duplicate-filename
input, with a diagnostic on stderr and nothing on stdout; callers must stop on
a nonzero exit rather than proceeding with a partial batch.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from return_validation import pattern_score_basis


def _observations(ret: object, label: str) -> dict:
    if not isinstance(ret, dict):
        raise ValueError(f"{label} is not a return object")
    observations = ret.get("pattern_observations")
    if not isinstance(observations, dict):
        raise ValueError(f"{label} has no pattern_observations object")
    return observations


def basis_for(ret: object, label: str) -> dict:
    """Return the exact basis this return's own lanes require."""
    observations = _observations(ret, label)
    lanes = {}
    for name in ("patterns_detected", "antipatterns_detected", "not_evaluable"):
        value = observations.get(name, [])
        if not isinstance(value, list):
            raise ValueError(f"{label} pattern_observations.{name} must be an array")
        lanes[name] = value
    try:
        return pattern_score_basis(
            lanes["patterns_detected"],
            lanes["antipatterns_detected"],
            lanes["not_evaluable"],
        )
    except (TypeError, KeyError) as exc:
        # A malformed detection reaches the owner function as a bad key or a
        # non-mapping and surfaces as a traceback, which callers parsing stdout
        # read as a crash rather than as input they can fix.
        raise ValueError(
            f"{label} has a malformed detection entry ({exc}); every detection "
            "needs an object with a confidence of strong, moderate, or weak"
        ) from exc


def completed(ret: object, label: str) -> dict:
    """Return a copy of this return with its required basis filled in."""
    filled = copy.deepcopy(ret)
    assert isinstance(filled, dict)
    filled["pattern_observations"]["pattern_score_basis"] = basis_for(ret, label)
    return filled


def load(paths: list[Path]) -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot read {path}: {exc}") from exc
        items = payload if isinstance(payload, list) else [payload]
        for index, item in enumerate(items):
            named = item.get("filename") if isinstance(item, dict) else None
            label = (
                named if isinstance(named, str) and named else f"{path.name}[{index}]"
            )
            out.append((label, item))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("returns", nargs="+", type=Path)
    args = parser.parse_args(argv)
    try:
        loaded = load(args.returns)
        seen = [label for label, _ in loaded]
        repeated = sorted({label for label in seen if seen.count(label) > 1})
        if repeated:
            # Keying by filename would drop every return but the last, and a
            # caller merging the output would silently give one talk another
            # talk's basis. The sibling validator rejects duplicate filenames
            # across inputs for the same reason.
            raise ValueError(
                f"duplicate talk filenames across the inputs: {', '.join(repeated)}; "
                "pass each return once, or split the batch so every filename is unique"
            )
        results = [completed(ret, label) for label, ret in loaded]
    except (ValueError, KeyError, TypeError) as exc:
        print(f"cannot build pattern_score_basis: {exc}", file=sys.stderr)
        return 2
    payload = results[0] if len(results) == 1 else results
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
