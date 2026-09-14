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
- A missing ledger means the vault has not adopted this contract yet: `adopt
  --now` at Step 1 creates it and records every claim already closed as
  history by exact identity. Until
  then `pending` reports `adopt_required: true` and reconciles nothing, and
  every other command refuses with `ledger_not_adopted`.
- A ledger carrying another `schema_version` is refused with
  `ledger_schema_unsupported`; the reader neither repairs nor downgrades it.
  Update speaker-toolkit, or inspect the file by hand.

## Root

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | integer | `1` |
| `adopted_at` | timestamp | when `adopt` ran |
| `adopted_facts` | array | the exact identity (`[run_id, filename, batch_id, generation, released_at]`) of every claim already closed at adoption — history, never reconciled; identity rather than time, since `persist-results.py --run-date` can stamp a batch at midnight |
| `dismissed_runs` | array | `{run_id, dismissed_at, reason, facts}` per run the operator chose not to open, `facts` being the exact identities that dismissal covered |
| `runs` | array | one record per `run_id`, in the order runs were opened |

## Run Record

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | integer | `1` — the run record's own version, checked on every read |
| `run_id` | string | the queue claim's run id (`queue-state.py claim --run-id`); the same identifier contract as the claim (non-empty, no whitespace), never used raw as a path |
| `opened_at` | timestamp | first `open` |
| `updated_at` | timestamp | last command that changed the record |
| `talks` | array | every talk `open` recorded for the run, sorted by filename |
| `downstream` | object | `{state: owed \| completed, completed_at}` — the rendering, summary, profile, and goal steps (Step 4's rendering through Step 8) for the run's talks |
| `clarification` | object | the offer, its disposition, and the session |
| `end_report` | object | the delivered report |
| `completed_at` | timestamp or null | set by `record-report`; the run is complete |

Timestamps are the canonical UTC whole-second ISO-8601 form
(`2026-09-14T12:00:00+00:00`), within years 1 to 9999 once normalized; every
command takes them from `--now`, never
from the clock, and stores the normalized form. Every read parses each stored
timestamp, requires that canonical form so stamps compare as text, and checks
the state-dependent invariants below; a record that breaks one is refused as
`ledger_invalid` naming the field.

Every recording command is replay-safe: repeating it with the inputs it
already recorded is an unchanged success carrying `replayed: true`, so a
caller that lost the first response can retry; a different answer to an
already-answered question is refused as `invalid_transition` naming what
stands. A replayed `open` never touches a frozen recency snapshot.

### Talk entry

| Field | Meaning |
|---|---|
| `filename` | the talk's `filename` in the tracking database |
| `status` | the talk's status at the time of `open` |
| `delivery_date` | the talk's `date` when it is a `YYYY-MM-DD` string, else null |
| `days_since_delivery` | whole days between `delivery_date` and `--now`, else null |
| `recency_bucket` | `same_week`, `recent`, `older`, or `unknown` |
| `claim_run_id` | the run id of the closed `return_persisted` claim that persisted the talk: this run's own newest claim when it has one, else the newest of any run; `open` refuses a talk with no such claim (`talk_not_persisted`) |
| `claim_batch_id` | that claim's `batch_id` |
| `claim_generation` | that claim's `reprocess_generation` |
| `claim_released_at` | that claim's `released_at`; with `claim_run_id`, `claim_batch_id`, and `claim_generation` it names one persisted fact — `persist-results.py` stamps one release time on a whole batch — so a talk merged again under the same run is a new fact that re-owes the downstream steps. Newer means a later generation, then a later release; the batch id is identity, never order |

Bucket boundaries and the rule that an undated or future-dated talk is
`unknown` are the script's; the reference to its constants lives in
[clarification-handoff.md](clarification-handoff.md#make-the-offer).

### Downstream steps

`open` owes them whenever a new talk joins the run; `record-downstream`, run
after Step 8, marks them `completed` with its `--now` and is replay-safe.
`record-offer` and `record-report` refuse (`invalid_transition`) while they are
owed, so a run resumed after a crash between the merge and Step 8 goes back
through rendering, summary, profile, and goals before anything is offered or
reported.

### Clarification

| Field | Meaning |
|---|---|
| `state` | one of the states below |
| `offer_mode` | `inline`, `recommend_full`, `recommend_compressed`, or `none`; how the run's talks decide it is the script's rule, referenced from [clarification-handoff.md](clarification-handoff.md#make-the-offer) |
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

State-dependent invariants: `offered_at` is set from `offered` on and null
before; `resolved_at` is set for `accepted`, `declined`, and `deferred` and
null otherwise; `return_condition` is a non-blank string for `deferred` and
null otherwise; `session` is an object only for `accepted`, with
`completed_at`, `profile_inputs`, and a boolean `profile_refreshed` set once
`completed` and null while `pending`.

Transitions: `owed → offered → accepted | declined | deferred`; an accepted
session goes `pending → completed` through `record-session`; a `deferred`
offer is the one answer that can be given again, `deferred → accepted |
declined | deferred`, when the speaker's return condition is met — the report
may already be delivered by then, and a session accepted afterwards is still
listed by `pending` until it completes. `not_applicable` is terminal. Silence,
elapsed time, and an invitation merely sent cause no transition: an `offered`
run stays pending until the speaker answers.

The stored recency is a snapshot, labeled by `recency_as_of`; a refresh never
changes a talk's recorded claim link. `open` recomputes it from the newest
`--now` while the state is `owed` or `not_applicable`; a new fact joining
while the offer is `offered` withdraws the offer back to `owed` so Step 9
makes it again for the fuller scope, and a new fact cannot join once the
offer was answered — it goes under a fresh run id. `record-offer` recomputes
it once more, against the current
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
| `report_path` | `{vault_root}/ingress-reports/{stem}.{sha256}.md`, the byte-exact copy; `stem` is the run id with every character outside `A-Za-z0-9._-` replaced by `_`, bounded for long ids by the script's `REPORT_STEM_*` constants, so a ledger-edited id never names a path outside the directory, a long id never exceeds a filename limit, and the full digest keeps two texts from ever sharing a path |
| `report_sha256` | digest of the delivered text |
| `reopened_at` | when a clarification session accepted after delivery reported changed profile inputs, sending the run back to `owed` for a fresh report; null otherwise |

Once `delivered`, path, digest, and `delivered_at` are set, `completed_at`
equals `delivered_at`, the downstream steps are `completed`, and the offer
has an answer (any state but `owed` or `offered`); while `owed`, path,
digest, `delivered_at`, and `completed_at` are null. A record claiming
delivery without those is refused as `ledger_invalid`.
A `record-session` that reports `changed` profile inputs after the report was
delivered — the only way is a deferred offer answered again — resets the
report to `owed`, stamps `reopened_at`, clears `completed_at`, and answers
`report_reopened: true`; Step 11 runs again so the report carries the
refreshed profile.

`record-report` refuses (`invalid_transition`) until the downstream steps are
recorded and the clarification is resolved: `declined`, `deferred`,
`not_applicable`, or `accepted` with a completed session. An empty or
whitespace-only file is refused
(`report_empty`). The copy is content-addressed and installed with a directory
fsync before the ledger commit binds it. A copy the commit then fails to bind
is retained: identical bytes always name the same file, so it is shared by
every delivery of that text and the retry reuses it; removing it could take a
copy out from under a delivery that did bind it. Re-recording identical bytes
changes nothing in the ledger but still verifies the copy, recreating one that
went missing; different bytes add a second copy (the earlier one stays on
disk) and re-stamp `delivered_at`. The copy is staged and installed relative
to a descriptor opened on the real `ingress-reports` directory without
following links, so a symlink at that path, or anything at the copy path that
is not a regular file, is refused (`report_copy_failed`) and nothing that
happens to the path mid-write can redirect the copy outside the vault. The
`--report-file` input is likewise read only as a regular file; a link or a
special file is `report_unreadable`.

## Commands

| Command | Precondition | Effect |
|---|---|---|
| `adopt --now` | — | creates the ledger with `adopted_at` and `adopted_facts`; replay-safe |
| `open --run-id --now (--talk ... \| --talks-from) [--from-run]` | the ledger is adopted; every talk (from `--talk` or one per line in the `--talks-from` file) is a filename in the current tracking database with a closed `return_persisted` claim (under `--from-run` when given); a completed run accepts only an exact replay of its recorded facts; a run whose offer was answered accepts no new fact | creates or extends the run record; recomputes recency and `offer_mode` while unoffered; a new fact joining while the offer stands withdraws the offer; owes the downstream steps when a new fact joins |
| `record-downstream --run-id --now` | the run exists | downstream `completed`; replay-safe |
| `record-offer --run-id --now [--topic ...]` | downstream `completed`; state `owed` | refreshes recency, then `offered` with `topics` and `offered: true`; or, with no analyzed talk left, `not_applicable` and `offered: false` |
| `record-disposition --run-id --now --disposition ... [--return-condition]` | state `offered` or `deferred`; `deferred` needs `--return-condition` | the disposition; `accepted` opens a pending session |
| `record-session --run-id --now --profile-inputs changed\|unchanged [--profile-refreshed]` | state `accepted`, session pending; `changed` with `{vault_root}/speaker-profile.json` present needs `--profile-refreshed` (`profile_refresh_required` otherwise) | session `completed` with both flags recorded |
| `record-report --run-id --now --report-file` | downstream `completed`; clarification resolved; non-empty file | copies the report, binds its digest, sets `completed_at` |
| `dismiss --run-id --now --reason` | the ledger is adopted; the run has no record and is listed as `unrecorded_run` | records the exact facts listed now as deliberately not opened; a run listed again after an earlier dismissal renews that entry, adding the new facts (`renewed: true`); with nothing new listed, the same reason is a replay and another reason is refused |
| `pending` | — | runs owing a step, deferred offers, and uncovered persisted facts |
| `status --run-id` | the run exists | the record and its summary |

Every command reads the tracking database through the owner's strict reader
and requires the current generation (`database_unusable` otherwise); the
ledger path is derived from the database-bound vault root, which is
re-resolved on every re-read and must not move while a command runs
(`vault_root_changed`).

Every mutating command re-reads the tracking database, re-checks the vault
root, and re-validates the ledger immediately before it writes. Exit 0 emits
one JSON object. A mutating command's object carries `written`
(whether bytes were installed), `durability_state` (`durable`, `unchanged`, or
a named degradation such as `installed_verification_failed`), and `warnings`;
every warning is also printed to stderr. Exit 2 emits
`{"ok": false, "error", "reason_code"}` on stdout and the same message on
stderr; a vault-root authority failure carries its own `reason_code` the same
way. Reason codes: `invalid_arguments`, `invalid_timestamp`,
`database_unusable`, `vault_root_changed`, `ledger_not_adopted`, `talk_not_found`,
`talk_not_persisted`, `run_not_found`, `invalid_transition`,
`profile_refresh_required`, `report_unreadable`,
`report_empty`,
`report_copy_failed`, `ledger_unreadable`, `ledger_invalid`,
`ledger_schema_unsupported`, `ledger_write_failed`.

Every read validates the whole ledger — required keys, container types,
timestamps, state vocabularies, and the state-dependent invariants above —
before any command runs; a malformed field is refused as `ledger_invalid`
naming the field, never repaired and never allowed to surface as a traceback.

## Reader Contract

`pending` emits `{ok, ledger_path, ledger_present, adopt_required,
adopted_at, pending: [...], count, deferred_offers: [...], open_required:
[...]}`. Each `pending` entry is a run
whose `next_action` is not `none`, carrying `run_id`, `opened_at`,
`next_action`, `downstream_state`, `clarification_state`, `offer_mode`,
`recency_as_of`, `end_report_state`, and `talk_count`. Treat an unoffered
entry's `offer_mode`
as the snapshot it is; `record-offer` returns the mode the offer must use.

`deferred_offers` lists every run whose offer is `deferred`, with `run_id`,
`return_condition`, `topics`, and `resolved_at`, so the offer can be raised
again when the speaker's condition is met.

`open_required` reconciles the ledger against the tracking database: a claim
closed with `release_reason: return_persisted` says its talk persisted, and a
persisted fact the ledger neither excludes nor covers crashed between the
merge and `open`. A persisted fact is one closed claim: run id, filename,
batch id, reprocess generation, and release time. It is excluded when
`adopted_facts` or a dismissal's `facts` name that exact identity. It is
covered when any run record lists the talk linked to that claim, or to a
newer claim of the same run (a later generation or release — a run that
merged a talk again superseded its earlier result), whichever run id
recorded it, so a recovery under a fresh run id is never reported again and
a talk merged again under the same run, even within the same second, is a
new fact until it is recorded. An uncovered run stays listed until it is
opened or dismissed; no later run's existence and no timestamp stands in for
either. Each entry carries `run_id`,
`talks` (only the uncovered ones), `latest_released_at`, `reason`, and
`next_action: open_obligations`:

| `reason` | Meaning | Action |
|---|---|---|
| `missing_talks` | a recorded run's closed claims name talks its record lacks — a later batch that never opened | `open` the run with exactly those talks |
| `talks_persisted_after_completion` | the same, on a run whose report is already delivered | open them under a fresh run id with `--from-run` naming the listed run, so the exact fact is covered even when another run merged the talk again since; `open` refuses a completed run |
| `talks_persisted_after_answer` | the same, on a run whose offer was answered but whose report is still owed | the same fresh-run-id recovery; a new fact never joins an answered run |
| `unrecorded_run` | a run with no record at all | `open` it with the listed talks (with `--from-run` when another run merged a talk again since), or `dismiss` it with a reason; only a run listed here can be dismissed, and a dismissal covers the facts that existed when it was recorded — a fact the run persists afterwards is listed again |

The exact coverage predicate is the script's rule — see `run-obligations.py`,
the `open_required` docstring.

`next_action` is one of:

| `next_action` | Resume at |
|---|---|
| `open_obligations` | Step 1: `open` the run with the listed talks |
| `complete_downstream_steps` | Step 4's rendering when the batch returns are still on disk, then Steps 5–8, then `record-downstream` |
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
