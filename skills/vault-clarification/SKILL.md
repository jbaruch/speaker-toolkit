---
name: vault-clarification
description: >
  Runs interactive clarification sessions with the speaker after talk processing.
  Resolves ambiguities in rhetoric observations, validates findings, captures speaker
  intent, conducts humor post-mortems, and probes for blind-spot moments invisible to
  transcripts. Stores confirmed intents and infrastructure config in the tracking database.
  Opens with the topics vault-ingress recorded when the speaker accepted the session,
  and closes that session in the run obligations ledger.
  Triggers: "run clarification session", "humor post-mortem", "blind spot review",
  "capture speaker intent", "clarify rhetoric findings", "resume clarification session".
user_invocable: true
---

# Vault Clarification — Interactive Session

Process steps in order. Do not skip ahead.

Each step's output informs the next. The first-session infrastructure capture in
Step 5 gates profile generation downstream.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
vault paths remain consumer-owned.

Run after vault-ingress has processed talks. Purpose: resolve ambiguities, validate
findings, capture intent, and fill in speaker infrastructure config.

vault-ingress Step 9 invokes this skill for an accepted session, and that call
carries `run_id`: the run in `{vault_root}/ingress-obligations.json` whose
session is pending. A call without `run_id` is standalone; Step 2 still checks
the ledger for a session left pending by a host that could not make the call.

The vault lives at `~/.claude/rhetoric-knowledge-vault/` (may be a symlink).
Set `host_python` to the current host's explicit absolute interpreter path (not
a PATH lookup). The sole interpreter-bootstrap exception is this one stdlib-only
strict-owner read; never parse the database directly:

```bash
"{host_python}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/read-tracking-database.py" \
  "~/.claude/rhetoric-knowledge-vault/tracking-database.json"
```

Use the report's database and SHA-256 to resolve `vault_root` and the exact
non-empty `config.python_path`. Set `python_path` to that value, immediately
repeat the owner read with `"{python_path}"` against the resolved
`{vault_root}/tracking-database.json`, and require the database and SHA-256 to
match the bootstrap report. The unconfigured `host_python` is authorized only
for that first owner-reader invocation. For missing, changed, or unusable
configuration, stop and invoke `Skill(skill: "vault-ingress")` at Step 1; never
fall back to `python3` on `PATH` for another toolkit script.

For every tracking-database change, compose a schema-v1 typed plan and run
`mutate-tracking-database.py` in its default dry-run mode. Review `changes`, then
run the same plan with `--apply --expected-sha256 <input_sha256>` and re-read the
database. Every mutation carries an exact value/record expectation; use
`{"$missing": true}` only when absence is expected. A failed precondition applies
nothing. The canonical command and operation contract is in
[../vault-ingress/references/schemas-db.md](../vault-ingress/references/schemas-db.md#owner-read-and-mutation-contract).

## Key Files & References

| File / Reference | Purpose |
|------------------|---------|
| `tracking-database.json` | Source of truth — config, confirmed intents |
| `rhetoric-style-summary.md` | Running rhetoric & style narrative |
| `analyses/{talk_filename}.md` | Per-talk analysis files |
| `ingress-obligations.json` | Run obligations ledger, owned by vault-ingress — the session's seed agenda; read and closed only through `run-obligations.py` |
| [../vault-ingress/references/schemas-obligations.md](../vault-ingress/references/schemas-obligations.md) | Ledger schema, states, and the `session-agenda` reader contract |
| [references/schemas-config.md](references/schemas-config.md) | Config fields + confirmed intents schema |
| [references/humor-post-mortem.md](references/humor-post-mortem.md) | Protocol for grading humor effectiveness |
| [references/blind-spot-moments.md](references/blind-spot-moments.md) | Protocol for capturing audience/room data |

## Step 1 — Verify Tracking Schema

Run the vault-ingress owner migration in dry-run mode before reading session
state:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/migrate-tracking-database.py" \
  "{vault_root}/tracking-database.json"
```

Exit 0 writes one JSON object with `from_schema_version`,
`to_schema_version`, `changed`, `database_written: false`, `input_sha256`, and
`record_counts`. Continue only for `changed: false` at the current database
generation in the [owner compatibility contract](../vault-ingress/references/schemas-db.md#schema-versioning)
with config schema v2. A legacy root or config report requires the owner workflow;
invoke `Skill(skill: "vault-ingress")`
with the migration report as handoff context, then finish this clarification run.
Exit 2 writes one error object to stdout plus an `ERROR:` diagnostic to stderr;
stop without changing session state.

Every tracking write in Steps 3–9 is current-only. Preserve the owner-current root,
config schema 2, talk schema 8, and every unrelated record. Stamp confirmed
intents with schema 1 and new improvement goals with schema 2. Capture the exact
input bytes immediately before each write, reject a changed generation, validate
the complete current shape, and use a same-directory atomic replacement. Never
turn this authorized writer into an implicit migrator.

Proceed immediately to Step 2.

## Step 2 — Resolve the Seed Agenda

The seed agenda is the list of candidate topics vault-ingress recorded when it
offered this session. It lives in the run obligations ledger
([../vault-ingress/references/schemas-obligations.md](../vault-ingress/references/schemas-obligations.md)),
which only `run-obligations.py` writes. Read it through that owner: never open
the ledger file directly, and never write it in this step.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/run-obligations.py" \
  "{vault_root}/tracking-database.json" session-agenda [--run-id "{run_id}"]
```

Pass `--run-id` when the call carries one. Without it, the command selects the
accepted session that never finished, if any; which one, when several are
pending, is the script's rule (`run-obligations.py`, the `pending_sessions`
docstring). Exit 0 with `session: null` means this session is standalone: it
has no seed agenda and touches the ledger no further. Otherwise
`session.run_id` is this session's run and `session.topics`, in its recorded
order, is the seed agenda. Exit 2 writes `{"ok": false, "error",
"reason_code"}` to stdout and the same message to stderr: a named run with no
pending session (`invalid_transition`), an unknown run (`run_not_found`), or a
ledger not yet adopted (`ledger_not_adopted`). Stop and report it; never guess
the topics.

Proceed immediately to Step 3.

## Step 3 — Rhetoric Clarification

Open with the seed agenda when Step 2 found one: put each recorded topic to
the speaker in its recorded order, one topic per `AskUserQuestion`, before
anything this session finds on its own. A topic the speaker chooses not to
discuss is answered as such and moves on, never dropped silently. Then, or
from the start of a standalone session, ask about each surprising,
contradictory, or ambiguous
observation, one topic at a time: intentional vs accidental patterns, invisible
context, conflicting signals, and flagged improvement areas. Update summary and
DB after each answer. Use the typed mutation protocol above for the DB portion;
do not batch answers into one unreviewed write at the end.

Example clarification question:
```
AskUserQuestion(
  question: "Your talks show a delayed self-introduction pattern — brief bio at slide 3,
  then a fuller re-intro mid-talk. Is this intentional or accidental?",
  options: [
    {label: "Deliberate", description: "I do this on purpose to hook first, credential later"},
    {label: "Accidental", description: "I didn't realize I was doing this"},
    {label: "Context-dependent", description: "Depends on the audience/venue"}
  ]
)
```

Proceed immediately to Step 4.

## Step 4 — Blind Spot Moments

Follow [references/blind-spot-moments.md](references/blind-spot-moments.md) — ask about audience reactions,
physical performance, and room context that transcripts cannot capture.

Proceed immediately to Step 5.

## Step 5 — Humor Post-Mortem

Follow [references/humor-post-mortem.md](references/humor-post-mortem.md) — walk through detected humor beats,
grade effectiveness, capture spontaneous material.

Proceed immediately to Step 6.

## Step 6 — Speaker Infrastructure (first session only)

If `config.clarification_sessions_completed` is already ≥ 1, skip this step and
proceed immediately to Step 7.

Otherwise, ask for any empty config fields (`speaker_name` through `publishing_process.*`).
See [references/schemas-config.md](references/schemas-config.md) for the full field list and questions to ask.
Persist each confirmed answer with `set_config`, expecting the exact value observed
by the latest strict read.

Proceed immediately to Step 7.

## Step 7 — Structured Intent Capture

Persist each confirmed intent with `upsert_confirmed_intent`, expecting either the
exact existing record for that pattern or `{"$missing": true}`.
Example:
```json
{
  "schema_version": 1,
  "pattern": "delayed_self_introduction",
  "intent": "deliberate",
  "rule": "Use two-phase intro: brief bio at slide 3, full re-intro mid-talk",
  "note": "Speaker confirmed this is intentional — hooks audience before credentialing"
}
```
See [references/schemas-config.md](references/schemas-config.md) for the full schema.

Proceed immediately to Step 8.

## Step 8 — Set Improvement Goals

Close the coaching loop. Review Section 15 of `rhetoric-style-summary.md` as narrative
coaching context, plus any `regressed`/`stalled` goals from a prior session, then ask
the speaker (via `AskUserQuestion`, one topic at a time) which
**1–2** they want to focus on before the next batch of talks. Coaching only works when
the speaker owns the target, so never auto-pick more than they choose.

For each chosen focus area, persist a **complete** schema-v2 `improvement_goals`
record with `upsert_improvement_goal`, expecting either the exact existing record
or `{"$missing": true}` — every field, not a subset. A partial record cannot be verified:
vault-ingress needs `metric` to compute `current_value`, and `id`/`issue`/`kind` to
identify and route the goal. Set `id` (kebab-case), `issue`, `kind`, `metric`,
`antipattern_id` (the exact ID only for an `antipattern` goal, otherwise `null`),
`baseline_value`, the speaker's stated `target`, `status: "active"`, `set_date` to
today, `set_by: "vault-clarification"`, `current_value: ""`, `last_checked: null`,
`checked_by: null`, `verification_state: "pending"`, `verification_reasons: []`,
`supersedes_goal_id: null`, and `schema_version: 2`.

For speaker-chosen `antipattern` and `underuse` goals, the baseline is
catalog-derived. Read the exact occurrence metric only from a validated schema-v4 or
schema-v5 profile whose pattern provenance matches the active catalog and scoring-v5
contract, copy `pattern_profile.pattern_baseline` unchanged into
`baseline_provenance.pattern_baseline`, and set the lane to `pattern_scoring`. Raw
occurrence rows do not themselves classify a pattern as recurring, underused, or a
signature. A schema-v5 derived label may inform the choices only when its exact
classification domain is `available`; schema v4 supplies no derived labels. The
speaker must explicitly choose the target. Never
parse the numeric baseline or generation identity from Section 15 prose. If no
matching non-empty raw-score-comparable current pattern cohort exists, explain that
the pattern goal has no verifiable baseline yet and do not create it. `pacing` uses the separate `pacing`
lane; a catalog release must not invalidate it. `other` uses `independent` and must
not conceal a catalog-pattern metric.

Run `"{python_path}" "{speaker_toolkit_root}/skills/vault-clarification/scripts/goal_generation_provenance.py"`
before writing the candidate. Send one JSON object on stdin:
`{"goals": [<candidate-goal-object>], "current_pattern_baseline": <pattern_profile.pattern_baseline-object-or-null>}`.
Exit 0 writes one JSON object to stdout:
`{"schema_version": 1, "assessments": [{"goal_id": "<id>", "comparable": <boolean>, "decision": "comparable|needs_rebaseline|unverifiable", "reason_codes": [<stable-code>, ...]}]}`.
Require exit 0 and one assessment for the candidate. Write the candidate only for
`"comparable": true`; surface `decision` and `reason_codes` for a false assessment.
Malformed JSON or a contract violation exits 1, writes no stdout, and writes
`ERROR: <diagnostic>` to stderr; stop without writing the candidate. The script
owns generation comparability; do not reproduce its fingerprint/schema comparison
in prose.

Retire goals the speaker no longer wants with `retire_improvement_goal`, naming
its exact `id` and expecting the complete current record. That operation changes
only `status` to `retired`, so legacy fields and fixed provenance survive unchanged;
leave `achieved` goals in place as history.
A schema-v1 pattern goal is historical and unverifiable, never a baseline to restamp.
If the speaker explicitly chooses to
rebaseline one, retire the old record and create a new schema-v2 record whose
`supersedes_goal_id` points to it. This preserves the old fixed yardstick rather than
silently overwriting it.
Full field list and `kind` values:
[references/schemas-config.md](references/schemas-config.md) Improvement Goals Schema.

A later vault-ingress run verifies these against the fresh baseline — see
[../vault-ingress/references/processing-rules.md](../vault-ingress/references/processing-rules.md)
Improvement Goal Verification.

If Section 15 has no speaker-selected pattern target, or the validated profile has no
non-empty matching raw-score-comparable current pattern cohort, say so and skip
pattern goal-setting. Proceed to Step 9. Independent pacing goals may still be
available.

Proceed immediately to Step 9.

## Step 9 — Mark Session Complete

Using the latest strict read, persist
`config.clarification_sessions_completed + 1` with `set_config`, expecting the
exact prior integer. This counter gates profile generation (vault-profile skill
requires >= 1).
The owner mutation preserves `config.schema_version: 2` and every unrelated
field.

Then close the ledger session Step 2 resolved; a standalone session with no
seed agenda finishes here. Name `profile_inputs`: `changed` when this session
wrote a confirmed intent, created, retired, or changed an improvement goal, or
edited the rhetoric summary; `unchanged` otherwise. List the recorded topics
the session covered.

- Invoked from vault-ingress Step 9: return `run_id`, `profile_inputs`, and the
  covered topics to the caller, which records the session per
  [Clarification Handoff](../vault-ingress/references/clarification-handoff.md#record-the-answer).
  Do not record it here; the caller owns the profile refresh the record may
  require.
- Standalone, with a session `session-agenda` selected: record it yourself, once:

  ```bash
  "{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/run-obligations.py" \
    "{vault_root}/tracking-database.json" record-session \
    --run-id "{run_id}" --now "{iso_timestamp}" --profile-inputs changed|unchanged [--profile-refreshed]
  ```

  Exit 2 with `profile_refresh_required` means `changed` inputs and an existing
  `{vault_root}/speaker-profile.json`: invoke `Skill(skill: "vault-profile")`
  with the resolved `{vault_root}` and exact `{python_path}` as handoff
  context, then repeat the command with `--profile-refreshed`.
  `report_reopened: true` in the output means the run's end report is owed
  again; say so, and the next vault-ingress run delivers it. Any other exit 2
  is reported as returned, and the session stays pending for the next run to
  record.

Finish here.

## Important Notes

- One topic at a time — don't dump all questions at once.
- The seed agenda is the ledger's: never invent a recorded topic, never drop one,
  and never touch `ingress-obligations.json` except through `run-obligations.py`.
- Update the summary and apply one reviewed typed DB plan after each answer, not in
  a batch at the end.
- After completing a session, suggest running the **vault-profile** skill if 10+ talks
  are processed and the profile hasn't been generated yet.
