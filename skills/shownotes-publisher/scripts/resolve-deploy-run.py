#!/usr/bin/env python3
"""Resolve a deployment run by repository, workflow, exact commit, event, and branch."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

POLL_INTERVAL_SECONDS = 5
MAX_ATTEMPTS = 60


def resolve_run(repo: str, workflow: str, commit: str, event: str, branch: str) -> int:
    """Wait for enqueue latency; reject ambiguous matches and API failures."""
    command = [
        "gh",
        "run",
        "list",
        "--repo",
        repo,
        "--workflow",
        workflow,
        "--commit",
        commit,
        "--event",
        event,
        "--branch",
        branch,
        "--limit",
        "100",
        "--json",
        "databaseId,headSha,event,headBranch",
    ]
    for attempt in range(MAX_ATTEMPTS):
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=30
        )
        if result.returncode:
            raise ValueError(
                f"Deployment lookup failed; check gh access/workflow: {result.stderr.strip()}"
            )
        rows = json.loads(result.stdout)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(
                "Deployment lookup returned invalid JSON rows; check gh output"
            )
        matches = [
            row
            for row in rows
            if row.get("headSha") == commit
            and row.get("event") == event
            and row.get("headBranch") == branch
        ]
        if len(matches) > 1:
            raise ValueError(
                "Multiple deployment runs match; resolve the ambiguity before publishing"
            )
        if matches:
            run_id = matches[0].get("databaseId")
            if type(run_id) is not int or run_id <= 0:
                raise ValueError(
                    "Deployment lookup returned an invalid databaseId; check gh output"
                )
            return run_id
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(POLL_INTERVAL_SECONDS)
    raise ValueError(
        "No matching deployment run appeared; check the workflow trigger and commit before retrying"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--repo", required=True, help="GitHub owner/repository")
    parser.add_argument(
        "--workflow", required=True, help="Deployment workflow filename or ID"
    )
    parser.add_argument(
        "--commit", required=True, help="Full pushed or merged commit SHA"
    )
    parser.add_argument("--event", required=True, help="Trigger event, normally push")
    parser.add_argument(
        "--branch", required=True, help="Branch that triggers deployment"
    )
    args = parser.parse_args(argv)
    try:
        if len(args.commit) != 40 or any(
            c not in "0123456789abcdef" for c in args.commit
        ):
            raise ValueError(
                "--commit must be the full lowercase 40-character commit SHA"
            )
        run_id = resolve_run(
            args.repo, args.workflow, args.commit, args.event, args.branch
        )
        print(json.dumps({"ok": True, "database_id": run_id}))
        return 0
    # The publisher expects JSON on failures; a traceback supplies no verdict.
    # Emit ok:false and stderr to preserve the agent-facing process contract.
    except Exception as exc:  # noqa: BLE001 — outer-boundary-process-contract
        print(json.dumps({"ok": False, "error": str(exc)}))
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
