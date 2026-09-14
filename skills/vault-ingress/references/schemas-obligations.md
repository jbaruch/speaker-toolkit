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
| `schema_version` | integer | `1` — the run record's own version, checked on every read |
| `run_id` | string | the queue claim's run id (`queue-state.py claim --run-id`); the same identifier contract as the claim (non-empty, no whitespace), never used raw as a path |
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
| `recency_as_of` | the `--now` the stored recency and `offer_mode` were last computed from; null before the first computation |
| `topics` | the candidate topics recorded with the offer |
| `offered_at` | when the offer was put to the speaker |
| `resolved_at` | when the disposition was recorded |
| `return_condition` | the speaker's words for when a deferred offer is raised again; null otherwise |
| `session` | null, or `{state: pending \| completed, completed_at, profile_inputs, profile_refreshed}` once accepted; `profile_inputs` is `changed` or `unchanged` as the session reported it |

| State | Meaning | Set by |
|---|---|---|
| `owed` | at least one analyzed talk; the offer has not been put to the speaker | `open` |
| `offered` | the offer was put to the speaker and no answer is recorded | `record-offer` |
| `accepted` | the speaker accepted; `session.state` says whether the session finished | `record-disposition` |
| `declined` | the speaker declined | `record-disposition` |
| `deferred` | the speaker deferred, with `return_condition`; answered again when that condition is met | `record-disposition` |
| `not_applicable` | the run analyzed no talk | `open` |

Transitions: `owed → offered → accepted | declined | deferred`; an accepted
session goes `pending → completed` through `record-session`; a `deferred`
offer is the one answer that can be given again, `deferred → accepted |
declined | deferred`, when the speaker's return condition is met — the report
may already be delivered by then, and a session accepted afterwards is still
listed by `pending` until it completes. `not_applicable` is terminal. Silence,
elapsed time, and an invitation merely sent cause no transition: an `offered`
run stays pending until the speaker answers.

The stored recency is a snapshot, labeled by `recency_as_of`. `open`
recomputes it from the newest `--now` while the state is `owed` or
`not_applicable`. `record-offer` recomputes it once more, against the current
database and its own `--now`, at the moment the offer is made, and its output
carries the `offer_mode` the offer must use; a run resumed weeks later never
promises an inline session for a talk that is no longer same-week. If that
refresh finds no analyzed talk left (a talk was requeued since `open`), the
state is persisted as `not_applicable`, the command succeeds with
`offered: false`, and nothing is asked; the report is then no longer blocked
on an offer. Once `offered`, the buckets and `offer_mode` are frozen; later
`open` calls only append talks.

### End report

| Field | Meaning |
|---|---|
| `state` | `owed` or `delivered` |
| `delivered_at` | when `record-report` accepted the delivered text |
| `report_path` | `{vault_root}/ingress-reports/{stem}.{digest prefix}.md`, the byte-exact copy; `stem` is the run id with every character outside `A-Za-z0-9._-` replaced by `_`, so a ledger-edited id never names a path outside the directory |
| `report_sha256` | digest of the delivered text |

`record-report` refuses (`invalid_transition`) until the clarification is
resolved: `declined`, `deferred`, `not_applicable`, or `accepted` with a
completed session. An empty or whitespace-only file is refused
(`report_empty`). The copy is content-addressed and installed with a directory
fsync before the ledger commit binds it; a copy the commit then fails to bind
is removed. Re-recording identical bytes is a no-op; different bytes add a
second copy (the earlier one stays on disk) and re-stamp `delivered_at`.

## Commands

| Command | Precondition | Effect |
|---|---|---|
| `open --run-id --now --talk ...` | every `--talk` is a filename in the current tracking database; the run is not completed | creates or extends the run record; recomputes recency and `offer_mode` while unoffered |
| `record-offer --run-id --now [--topic ...]` | state `owed` | refreshes recency, then `offered` with `topics` and `offered: true`; or, with no analyzed talk left, `not_applicable` and `offered: false` |
| `record-disposition --run-id --now --disposition ... [--return-condition]` | state `offered` or `deferred`; `deferred` needs `--return-condition` | the disposition; `accepted` opens a pending session |
| `record-session --run-id --now --profile-inputs changed\|unchanged [--profile-refreshed]` | state `accepted`, session pending; `changed` with `{vault_root}/speaker-profile.json` present needs `--profile-refreshed` (`profile_refresh_required` otherwise) | session `completed` with both flags recorded |
| `record-report --run-id --now --report-file` | clarification resolved; non-empty file | copies the report, binds its digest, sets `completed_at` |
| `pending` | — | runs with `completed_at` null and their `next_action` |
| `status --run-id` | the run exists | the record and its summary |

Every command reads the tracking database through the owner's strict reader
and requires the current generation (`database_unusable` otherwise); the
ledger path is derived from the database-bound vault root.

Exit 0 emits one JSON object. A mutating command's object carries `written`
(whether bytes were installed), `durability_state` (`durable`, `unchanged`, or
a named degradation such as `installed_verification_failed`), and `warnings`;
every warning is also printed to stderr. Exit 2 emits
`{"ok": false, "error", "reason_code"}` on stdout and the same message on
stderr. Reason codes: `invalid_arguments`, `invalid_timestamp`,
`database_unusable`, `talk_not_found`, `run_not_found`, `invalid_transition`,
`profile_refresh_required`, `report_unreadable`, `report_empty`,
`report_copy_failed`, `ledger_unreadable`, `ledger_invalid`,
`ledger_schema_unsupported`, `ledger_write_failed`.

Every read validates the whole ledger — required keys, container types, state
vocabularies, and the state-dependent `session` shape — before any command
runs; a malformed field is refused as `ledger_invalid` naming the field, never
repaired and never allowed to surface as a traceback.

## Reader Contract

`pending` emits `{ok, ledger_path, ledger_present, pending: [...], count,
deferred_offers: [...], unrecorded_runs: [...]}`. Each `pending` entry is a run
whose `next_action` is not `none`, carrying `run_id`, `opened_at`,
`next_action`, `clarification_state`, `offer_mode`, `recency_as_of`,
`end_report_state`, and `talk_count`. Treat an unoffered entry's `offer_mode`
as the snapshot it is; `record-offer` returns the mode the offer must use.

`deferred_offers` lists every run whose offer is `deferred`, with `run_id`,
`return_condition`, `topics`, and `resolved_at`, so the offer can be raised
again when the speaker's condition is met.

`unrecorded_runs` reconciles the ledger against the tracking database: a run
whose closed claims carry `release_reason: return_persisted` persisted talks,
and if it has no ledger record it crashed between the merge and `open`. At
most one entry is reported — the newest such run, and only when it is newer
than every recorded run's `opened_at`; which runs qualify is the script's rule
(`run-obligations.py`, `unrecorded_run` docstring). The entry carries `run_id`,
`talks`, `latest_released_at`, and `next_action: open_obligations`: run `open`
for it with those talks, then resume at the step its record names.

`next_action` is one of:

| `next_action` | Resume at |
|---|---|
| `open_obligations` | Step 1: `open` the run with the listed talks |
| `offer_clarification` | Step 9: compute topics and make the offer |
| `await_disposition` | Step 9: put the recorded offer to the speaker again and wait |
| `complete_clarification_session` | Step 9: run the accepted session, then record it |
| `deliver_end_report` | Step 11: deliver and record the report |
| `none` | nothing pending (never listed by `pending`) |

## Migration

This release reads ledger schema 1 and run-record schema 1 only; there is no
older generation to upgrade from, and no on-read migration exists yet. Any
shape change bumps the affected `schema_version` and ships its on-read upgrade
in `run-obligations.py` in the same change. A script older than the ledger it
reads refuses it (`ledger_schema_unsupported` for the envelope,
`ledger_invalid` naming the run-record version) and never rewrites it; the
operator updates speaker-toolkit.
