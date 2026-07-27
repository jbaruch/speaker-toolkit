#!/usr/bin/env python3
"""Load vault source files for speaker-profile generation.

Reads the rhetoric vault and emits a single JSON payload to stdout containing
all source data needed to construct speaker-profile.json. The skill orchestrator
calls this script once and then aggregates the payload into the profile.

Contract
--------
Args:
    vault_root: optional path to vault root. Defaults to
                ~/.claude/rhetoric-knowledge-vault.

Stdout (JSON):
    {
      "vault_root":        "<absolute path>",
      "config":            { ... }   # tracking-database.json `config` block
      "confirmed_intents": [ ... ]   # tracking-database.json `confirmed_intents`
      "talks":             [ ... ]   # all talks
      "processed_talks":   [ ... ]   # talks with status processed* only
      "baseline_talks":    [ ... ]   # processed talks scored on current instrumentation
      "stale_instrumentation_talks": [ ... ]   # processed, but scored pre-epoch
      "baseline_note":     "...",    # why baselines must use baseline_talks only
      "summary":           "...",    # rhetoric-style-summary.md contents
      "design_spec":       "..."     # slide-design-spec.md contents (or "")
    }

Exit codes:
    0   success
    1   tracking-database.json or rhetoric-style-summary.md missing/malformed.
        Diagnostic message goes to stderr.
"""

from __future__ import annotations

import json
import pathlib
import sys


DEFAULT_VAULT = "~/.claude/rhetoric-knowledge-vault"

# Talks processed on or after this date were scored by an extractor that can read
# text baked into images and payload held in OOXML tables; talks processed before
# it were not. The gap is not noise — measured across the corpus mid-reparse, the
# two cohorts averaged 28.0 and 11.8, and a mixed mean tracks how far the reparse
# has got rather than anything about the speaker. Partitioning here rather than in
# skill prose keeps the two cohorts from being averaged together by accident.
INSTRUMENTATION_EPOCH = "2026-07-26"


def partition_by_instrumentation(processed_talks, epoch=INSTRUMENTATION_EPOCH):
    """Split processed talks into (current-instrumentation, stale) cohorts.

    A talk with no `processed_date` cannot be dated and is treated as stale — the
    safe direction, since including it would silently contaminate a baseline
    while excluding it only narrows the sample.
    """
    current, stale = [], []
    for talk in processed_talks:
        date = talk.get("processed_date") or ""
        (current if date >= epoch else stale).append(talk)
    return current, stale


def main(argv: list[str]) -> int:
    vault_root = pathlib.Path(
        argv[1] if len(argv) > 1 else DEFAULT_VAULT
    ).expanduser().resolve()

    db_path = vault_root / "tracking-database.json"
    if not db_path.exists():
        print(
            f"ERROR: tracking-database.json not found at {db_path} — "
            "vault may be missing or unconfigured.",
            file=sys.stderr,
        )
        return 1
    try:
        db = json.loads(db_path.read_text())
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: tracking-database.json is malformed: {exc}", file=sys.stderr
        )
        return 1

    summary_path = vault_root / "rhetoric-style-summary.md"
    if not summary_path.exists():
        print(
            "ERROR: rhetoric-style-summary.md not found. "
            "Run vault-ingress first to process talks.",
            file=sys.stderr,
        )
        return 1
    summary = summary_path.read_text()

    design_spec_path = vault_root / "slide-design-spec.md"
    design_spec = design_spec_path.read_text() if design_spec_path.exists() else ""

    talks = db.get("talks", [])
    processed_statuses = {"processed", "processed_partial"}
    processed_talks = [t for t in talks if t.get("status") in processed_statuses]

    scoreable, stale = partition_by_instrumentation(processed_talks)

    payload = {
        "vault_root": str(vault_root),
        "config": db.get("config", {}),
        "confirmed_intents": db.get("confirmed_intents", []),
        "talks": talks,
        "processed_talks": processed_talks,
        "baseline_talks": scoreable,
        "stale_instrumentation_talks": stale,
        "baseline_note": (
            f"pattern_score baselines MUST be computed from baseline_talks only "
            f"({len(scoreable)} talks). The {len(stale)} talks in "
            f"stale_instrumentation_talks were scored before "
            f"{INSTRUMENTATION_EPOCH} against an extractor blind to text baked "
            f"into images and to OOXML-table payload; their scores measure scan "
            f"depth, not delivery. Mixing the two cohorts produces an average "
            f"that tracks reparse progress rather than the speaker."
        ),
        "summary": summary,
        "design_spec": design_spec,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
