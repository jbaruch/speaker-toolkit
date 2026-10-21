#!/usr/bin/env python3
"""Emit a compact current-taxonomy menu without loading the scoring index.

Usage: pattern-menu.py --phase architecture [--kind pattern|antipattern]

Reads the unchanged bundled catalog through its shared YAML reader. Filters by
the entry's declared phase and kind; emits id, name, relative path, summary, and
observability, plus the selected phase's workflow owner/action. Canonical phases
and exact legacy aliases resolve through PHASE_WORKFLOWS and LEGACY_PHASE_ALIASES.
No speaker history, tiers, novelty or scoring claims are inferred.
It never writes the catalog or tracking database. Exit 0 emits one JSON object;
exit 1 emits an actionable diagnostic on stderr with empty stdout; CLI usage
errors exit 2. A null workflow step defers lane selection to the target skill.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

TOOLKIT_ROOT = Path(__file__).resolve().parents[3]
CATALOG_ROOT = Path(__file__).resolve().parent.parent / "references" / "patterns"
PHASE_WORKFLOWS = {
    "intake": {"skill": "presentation-creator", "action": "author", "step": 0},
    "intent": {"skill": "presentation-creator", "action": "author", "step": 1},
    "architecture": {"skill": "presentation-creator", "action": "author", "step": 2},
    "content": {"skill": "presentation-creator", "action": "author", "step": 3},
    "guardrails": {"skill": "presentation-creator", "action": "author", "step": 4},
    "slides": {"skill": "presentation-builder", "action": "build", "step": None},
    "publishing": {"skill": "presentation-publisher", "action": "publish", "step": 1},
}
PHASES = tuple(PHASE_WORKFLOWS)
LEGACY_PHASE_ALIASES = {
    "phase 5": "slides",
    "creator phase 5": "slides",
    "phase 5: slides": "slides",
    "phase 5: slide generation": "slides",
    "phase 6": "publishing",
    "creator phase 6": "publishing",
    "phase 6: publishing": "publishing",
    "creator phase 6 (publishing / go-live)": "publishing",
}
sys.path.insert(0, str(TOOLKIT_ROOT / "skills/vault-ingress/scripts"))
from catalog_io import catalog_entry_paths, load_catalog_yaml  # noqa: E402
import yaml  # noqa: E402


class PatternMenuError(ValueError):
    """Catalog content cannot supply an unambiguous discovery menu."""


def resolve_phase(value: str) -> str:
    """Resolve a canonical lifecycle phase or one explicitly supported alias."""
    phase = " ".join(value.strip().casefold().split())
    if phase in PHASE_WORKFLOWS:
        return phase
    if phase in LEGACY_PHASE_ALIASES:
        return LEGACY_PHASE_ALIASES[phase]
    raise PatternMenuError(f"unknown lifecycle phase {value!r}; choose one from --help")


def phase_argument(value: str) -> str:
    """Keep invalid CLI phases in argparse's usage-error contract."""
    try:
        return resolve_phase(value)
    except PatternMenuError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_menu(root: Path, phase: str, kind: str) -> dict:
    """Return only matching discovery rows; leave policy/scoring to their owners."""
    phase = resolve_phase(phase)
    if not root.is_dir():
        raise PatternMenuError(f"catalog missing at {root}; reinstall speaker-toolkit")
    entries = []
    seen: set[str] = set()
    for path in catalog_entry_paths(root):
        text = path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) != 3 or parts[0].strip():
            raise PatternMenuError(f"{path} lacks YAML frontmatter; repair the catalog")
        metadata = load_catalog_yaml(parts[1])
        if not isinstance(metadata, dict):
            raise PatternMenuError(f"{path} has invalid metadata; repair the catalog")
        identifier = metadata.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise PatternMenuError(
                f"{path} has a missing/duplicate id; repair the catalog"
            )
        seen.add(identifier)
        phases = metadata.get("phase_relevance")
        if not isinstance(phases, list) or not all(isinstance(p, str) for p in phases):
            raise PatternMenuError(
                f"{path} has invalid phase_relevance; repair the catalog"
            )
        if phase not in phases or metadata.get("type") != kind:
            continue
        name = metadata.get("name")
        observable = metadata.get("observable", True)
        _, marker, remainder = parts[2].partition("\n## Summary\n")
        summary = " ".join(remainder.split("\n## ", 1)[0].split())
        if not isinstance(name, str) or not name or not marker or not summary:
            raise PatternMenuError(f"{path} lacks a name/summary; repair the catalog")
        if type(observable) is not bool:
            raise PatternMenuError(
                f"{path} has invalid observability; repair the catalog"
            )
        entries.append(
            {
                "id": identifier,
                "name": name,
                "path": path.relative_to(root).as_posix(),
                "summary": summary,
                "observable": observable,
            }
        )
    return {
        "phase": phase,
        "kind": kind,
        "workflow": dict(PHASE_WORKFLOWS[phase]),
        "catalog_root": str(root),
        "entries": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n")[0],
        epilog="Legacy aliases: " + "; ".join(LEGACY_PHASE_ALIASES),
    )
    parser.add_argument(
        "--phase",
        type=phase_argument,
        metavar="{" + ",".join(PHASES) + "}",
        help="Canonical phase or exact legacy alias (case-insensitive).",
        required=True,
    )
    parser.add_argument("--kind", choices=("pattern", "antipattern"), default="pattern")
    args = parser.parse_args(argv)
    try:
        report = build_menu(CATALOG_ROOT, args.phase, args.kind)
    except (OSError, UnicodeError, yaml.YAMLError, PatternMenuError) as exc:
        print(f"FAIL: cannot read the pattern menu: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
