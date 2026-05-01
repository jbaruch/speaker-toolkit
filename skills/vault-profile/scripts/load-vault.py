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

    payload = {
        "vault_root": str(vault_root),
        "config": db.get("config", {}),
        "confirmed_intents": db.get("confirmed_intents", []),
        "talks": talks,
        "processed_talks": processed_talks,
        "summary": summary,
        "design_spec": design_spec,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
