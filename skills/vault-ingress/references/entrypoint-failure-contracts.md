# Entrypoint Failure Contracts

Every deterministic vault-ingress entrypoint closes its outer failure boundary
(#203). No unexpected exception reaches a caller as a traceback, and no
machine-readable command leaves a truncated document on stdout.

Read this when a script exits non-zero and you need to know what state it left
behind. It inventories the boundary contract only — each script's normal
validation predicates stay in the script (`rules/script-as-black-box.md`).

## The Shared Diagnostic Shape

`skills/vault-ingress/scripts/failure_diagnostics.py` owns the emitted
document. On an unexpected
failure the entrypoint writes to **stderr**, one JSON object on the first line:

```json
{"error": "<entrypoint>_unexpected_failure",
 "error_type": "RuntimeError",
 "origin": ["persist-results.py:412 in merge_return"]}
```

A human-readable recovery note follows on the next lines.

- `error_type` is the exception CLASS. The exception MESSAGE never crosses the
  boundary — `no-secrets` forbids it, and a `FileNotFoundError` message embeds
  the path it could not find.
- `origin` is `basename:line in function`, innermost last. Never a full path.
- Mutating entrypoints add commit-position fields; see the table.

## CLI Contracts

Every script named below lives in `skills/vault-ingress/scripts/`.

| Script | stdout on success | Unexpected-failure exit | Failure identifier | Commit-position field |
|---|---|---|---|---|
| `persist-results.py` | one JSON receipt | 2 | `persist_results_unexpected_failure` | `database_written` |
| `write-analysis.py` | one JSON receipt | 2 | `write_analysis_unexpected_failure` | `analyses_written` |
| `preflight-vault.py` | one JSON report | 2 | `preflight_unexpected_failure` (a blocking finding in a real report, not a stderr document) | — read-only |
| `validate-returns.py` | one JSON report | 2 | `validate_returns_unexpected_failure` | — read-only |
| `audit-pattern-catalog.py` | one JSON report | 3 | `catalog_audit_unexpected_failure` | — read-only |
| `aggregate-catalog-feedback.py` | one JSON report | 3 | `catalog_feedback_unexpected_failure` | — read-only |

The two catalog gates use exit 3 because argparse already owns exit 2 there; a
caller can still tell a malformed invocation from a broken tool.

`preflight-vault.py` is the one entrypoint whose failure lands on **stdout**: a
caller gates claiming on its report, and a missing report reads as "preflight
never ran". It emits a real report — `ok: false`, one blocking finding whose
keys match every other finding — so a consumer parses it normally.

## What an Exit Code Does Not Mean

- Exit 1 is the script's own verdict: a rejected batch, a structurally invalid
  catalog. The tool worked.
- Exit 2 (or 3) with the JSON document above means the tool FAILED. A read-only
  command's inputs are unexamined, not clean. Never read it as a pass.
- `SystemExit` from a documented error path is not caught by these boundaries —
  those exit codes reach the caller unchanged.

## Retrying a Mutating Script

`database_written` and `analyses_written` state whether the atomic commit
landed before the failure:

- `true` — the write is durable. Re-running re-persists the batch. Re-read the
  live state before deciding.
- `false` — every target was rolled back. The batch can be retried as-is.

Never infer commit position from the exit code; read the field.

## Worker Protocol Boundaries

`pptx_evidence.py`, `pptx-extraction.py`, and `pdf_evidence.py` — same
directory — run supervised worker children whose stdout is reserved for one
authenticated frame. Their boundaries emit a path-neutral
`<kind> worker failed: <reason>` line on stderr and exit 2; the supervisor
reads a non-zero child without an authenticated response as a bounded crash.
