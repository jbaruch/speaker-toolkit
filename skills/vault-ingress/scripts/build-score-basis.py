#!/usr/bin/env python3
"""Emit the pattern_score_basis a v6 return requires, from its own detections.

The basis is a pure function of a return's detection lanes and its
not-evaluable ledger, so constructing it is a deterministic operation that
belongs in a script rather than in a worker's reasoning. `return_validation`
owns both the weight table and the object's shape; this is a thin entry point
onto that owner so no caller has to reproduce either.

Usage:
    build-score-basis.py <return.json> [...]

Each input is one return object or an array of return objects. For a single
return the basis is printed alone; for several, an object keyed by filename.
The output is the exact value `pattern_observations.pattern_score_basis` must
carry — paste it in, or merge it programmatically.

Exit 0 on success, 2 on unreadable or malformed input.
"""

from __future__ import annotations

import argparse
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
    return pattern_score_basis(
        lanes["patterns_detected"],
        lanes["antipatterns_detected"],
        lanes["not_evaluable"],
    )


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
        results = {label: basis_for(ret, label) for label, ret in loaded}
    except (ValueError, KeyError) as exc:
        print(f"cannot build pattern_score_basis: {exc}", file=sys.stderr)
        return 2
    if len(results) == 1:
        print(json.dumps(next(iter(results.values())), indent=2, sort_keys=True))
    else:
        print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
