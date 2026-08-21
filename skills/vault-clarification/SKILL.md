---
name: vault-clarification
description: >
  Runs interactive clarification sessions with the speaker after talk processing.
  Resolves ambiguities in rhetoric observations, validates findings, captures speaker
  intent, conducts humor post-mortems, and probes for blind-spot moments invisible to
  transcripts. Stores confirmed intents and infrastructure config in the tracking database.
  Triggers: "run clarification session", "humor post-mortem", "blind spot review",
  "capture speaker intent", "clarify rhetoric findings".
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
`record_counts`. Continue only for `changed: false` at database schema v1 with
config schema v2. A legacy root or config report requires the owner workflow;
invoke `Skill(skill: "vault-ingress")`
with the migration report as handoff context, then finish this clarification run.
Exit 2 writes one error object to stdout plus an `ERROR:` diagnostic to stderr;
stop without changing session state.

Every tracking write in Steps 2–8 is current-only. Preserve database schema 2,
config schema 2, talk schema 7, and every unrelated record. Stamp confirmed
intents with schema 1 and new improvement goals with schema 2. Capture the exact
input bytes immediately before each write, reject a changed generation, validate
the complete current shape, and use a same-directory atomic replacement. Never
turn this authorized writer into an implicit migrator.

Proceed immediately to Step 2.

## Step 2 — Rhetoric Clarification

For each surprising, contradictory, or ambiguous observation, ask one topic at a time
via `AskUserQuestion`: intentional vs accidental patterns, invisible context,
conflicting signals, and flagged improvement areas. Update summary and DB after each answer.
Use the typed mutation protocol above for the DB portion; do not batch answers into
one unreviewed write at the end.

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

Proceed immediately to Step 3.

## Step 3 — Blind Spot Moments

Follow [references/blind-spot-moments.md](references/blind-spot-moments.md) — ask about audience reactions,
physical performance, and room context that transcripts cannot capture.

Proceed immediately to Step 4.

## Step 4 — Humor Post-Mortem

Follow [references/humor-post-mortem.md](references/humor-post-mortem.md) — walk through detected humor beats,
grade effectiveness, capture spontaneous material.

Proceed immediately to Step 5.

## Step 5 — Speaker Infrastructure (first session only)

If `config.clarification_sessions_completed` is already ≥ 1, skip this step and
proceed immediately to Step 6.

Otherwise, ask for any empty config fields (`speaker_name` through `publishing_process.*`).
See [references/schemas-config.md](references/schemas-config.md) for the full field list and questions to ask.
Persist each confirmed answer with `set_config`, expecting the exact value observed
by the latest strict read.

Proceed immediately to Step 6.

## Step 6 — Structured Intent Capture

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

Proceed immediately to Step 7.

## Step 7 — Set Improvement Goals

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
pattern goal-setting. Proceed to Step 8. Independent pacing goals may still be
available.

Proceed immediately to Step 8.

## Step 8 — Mark Session Complete

Using the latest strict read, persist
`config.clarification_sessions_completed + 1` with `set_config`, expecting the
exact prior integer. This counter gates profile generation (vault-profile skill
requires >= 1).
The owner mutation preserves `config.schema_version: 2` and every unrelated
field.

Finish here.

## Important Notes

- One topic at a time — don't dump all questions at once.
- Update the summary and apply one reviewed typed DB plan after each answer, not in
  a batch at the end.
- After completing a session, suggest running the **vault-profile** skill if 10+ talks
  are processed and the profile hasn't been generated yet.
