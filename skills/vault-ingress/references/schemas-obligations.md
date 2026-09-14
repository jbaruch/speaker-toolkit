# Ingress Run Obligations Schema

`{vault_root}/ingress-obligations.json` records what each vault-ingress run
still owes the speaker after its batches persist. A closed queue claim in
`tracking-database.json` is processing completion; this ledger holds run
completion, which arrives only when the clarification offer carries an
explicit disposition and the end report has been delivered.

## Ownership and Access

- Owner: vault-ingress. `skills/vault-ingress/scripts/run-obligations.py` is
  the only writer and owns every shape change and migration.
- Readers: vault-ingress Step 1 (`pending`) and Steps 9 and 11 (`status`).
  vault-clarification and vault-profile never read it.
- Every write goes through the tracking-database io helpers: sibling lock file,
  exact-generation check, staged candidate, atomic replace. Never edit the
  ledger by hand.
- A missing ledger means no run has opened obligations; the first `open`
  creates it. `pending` on a missing ledger reports `ledger_present: false`
  and an empty list.
- A ledger carrying another `schema_version` is refused with
  `ledger_schema_unsupported`; the reader neither repairs nor downgrades it.
  Update speaker-toolkit, or inspect the file by hand.

## Root

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | integer | `1` |
| `runs` | array | one record per `run_id`, in the order runs were opened |

## Run Record

| Field | Type | Meaning |
|---|---|---|
| `run_id` | string | the queue claim's run id (`queue-state.py claim --run-id`) |
| `opened_at` | timestamp | first `open` |
| `updated_at` | timestamp | last command that changed the record |
| `talks` | array | every talk `open` recorded for the run, sorted by filename |
| `clarification` | object | the offer, its disposition, and the session |
| `end_report` | object | the delivered report |
| `completed_at` | timestamp or null | set by `record-report`; the run is complete |

Timestamps are timezone-aware ISO-8601 normalized to UTC seconds; every
command takes them from `--now`, never from the clock.

### Talk entry

| Field | Meaning |
|---|---|
| `filename` | the talk's `filename` in the tracking database |
| `status` | the talk's status at the time of `open` |
| `delivery_date` | the talk's `date` when it is a `YYYY-MM-DD` string, else null |
| `days_since_delivery` | whole days between `delivery_date` and `--now`, else null |
| `recency_bucket` | `same_week`, `recent`, `older`, or `unknown` |

Bucket boundaries and the rule that an undated or future-dated talk is
`unknown` are the script's: see `run-obligations.py`, the top-of-file
constants `SAME_WEEK_MAX_DAYS`, `RECENT_MAX_DAYS`, and `OFFER_MODE_BY_BUCKET`.

### Clarification

| Field | Meaning |
|---|---|
| `state` | one of the states below |
| `offer_mode` | `inline`, `recommend_full`, `recommend_compressed`, or `none` — the strongest bucket among the run's analyzed talks (`processed`, `processed_partial`); skipped talks never drive it |
| `topics` | the candidate topics recorded with the offer |
| `offered_at` | when the offer was put to the speaker |
| `resolved_at` | when the disposition was recorded |
| `return_condition` | the speaker's words for when a deferred offer is raised again; null otherwise |
| `session` | null, or `{state: pending \| completed, completed_at, profile_refreshed}` once accepted |

| State | Meaning | Set by |
|---|---|---|
| `owed` | at least one analyzed talk; the offer has not been put to the speaker | `open` |
| `offered` | the offer was put to the speaker and no answer is recorded | `record-offer` |
| `accepted` | the speaker accepted; `session.state` says whether the session finished | `record-disposition` |
| `declined` | the speaker declined | `record-disposition` |
| `deferred` | the speaker deferred, with `return_condition` | `record-disposition` |
| `not_applicable` | the run analyzed no talk | `open` |

Transitions: `owed → offered → accepted | declined | deferred`; an accepted
session goes `pending → completed` through `record-session`. `not_applicable`
is terminal. Silence, elapsed time, and an invitation merely sent cause no
transition: an `offered` run stays pending until the speaker answers.

Recency is recomputed from the newest `--now` on every `open` while the state
is `owed` or `not_applicable`, so a run resumed weeks later does not promise an
inline session for a talk that is no longer same-week. Once `offered`, the
buckets and `offer_mode` are frozen; later `open` calls only append talks.

### End report

| Field | Meaning |
|---|---|
| `state` | `owed` or `delivered` |
| `delivered_at` | when `record-report` accepted the delivered text |
| `report_path` | `{vault_root}/ingress-reports/{run_id}.md`, the byte-exact copy |
| `report_sha256` | digest of the delivered text |

`record-report` refuses (`invalid_transition`) until the clarification is
resolved: `declined`, `deferred`, `not_applicable`, or `accepted` with a
completed session. An empty or whitespace-only file is refused
(`report_empty`). Re-recording identical bytes is a no-op; different bytes
replace the copy and re-stamp `delivered_at`.

## Commands

| Command | Precondition | Effect |
|---|---|---|
| `open --run-id --now --talk ...` | every `--talk` is a filename in the current tracking database; the run is not completed | creates or extends the run record; recomputes recency and `offer_mode` while unoffered |
| `record-offer --run-id --now [--topic ...]` | state `owed` | `offered`, stores `topics` |
| `record-disposition --run-id --now --disposition ... [--return-condition]` | state `offered`; `deferred` needs `--return-condition` | terminal disposition; `accepted` opens a pending session |
| `record-session --run-id --now [--profile-refreshed]` | state `accepted`, session pending | session `completed` |
| `record-report --run-id --now --report-file` | clarification resolved; non-empty file | copies the report, binds its digest, sets `completed_at` |
| `pending` | — | runs with `completed_at` null and their `next_action` |
| `status --run-id` | the run exists | the record and its summary |

Every command reads the tracking database through the owner's strict reader
and requires the current generation (`database_unusable` otherwise); the
ledger path is derived from the database-bound vault root.

Exit 0 emits one JSON object. Exit 2 emits `{"ok": false, "error", "reason_code"}`
on stdout and the same message on stderr. Reason codes: `invalid_arguments`,
`invalid_timestamp`, `database_unusable`, `talk_not_found`, `run_not_found`,
`invalid_transition`, `report_unreadable`, `report_empty`, `ledger_unreadable`,
`ledger_invalid`, `ledger_schema_unsupported`, `ledger_write_failed`.

## Reader Contract

`pending` emits `{ok, ledger_path, ledger_present, pending: [...], count}`.
Each entry carries `run_id`, `opened_at`, `next_action`, `clarification_state`,
`offer_mode`, `end_report_state`, and `talk_count`. `next_action` is one of:

| `next_action` | Resume at |
|---|---|
| `offer_clarification` | Step 9: compute topics and make the offer |
| `await_disposition` | Step 9: put the recorded offer to the speaker again and wait |
| `complete_clarification_session` | Step 9: run the accepted session, then record it |
| `deliver_end_report` | Step 11: deliver and record the report |
| `none` | nothing pending (never listed by `pending`) |

## Migration

Any shape change bumps `schema_version`. Only `run-obligations.py` migrates,
on read, by upgrading the record and rewriting. A script older than the ledger
refuses it as `ledger_schema_unsupported`, which the operator resolves by
updating speaker-toolkit; the ledger is never rewritten by a reader.
