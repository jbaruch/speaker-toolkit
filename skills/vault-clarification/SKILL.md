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

Process the steps below in order; each step's output informs the next, and the first-session infrastructure capture in Step 4 gates profile generation downstream. Do not skip ahead.

Run after vault-ingress has processed talks. Purpose: resolve ambiguities, validate
findings, capture intent, and fill in speaker infrastructure config.

The vault lives at `~/.claude/rhetoric-knowledge-vault/` (may be a symlink).
Read `tracking-database.json` from there to get `vault_root`.

## Key Files & References

| File / Reference | Purpose |
|------------------|---------|
| `tracking-database.json` | Source of truth — config, confirmed intents |
| `rhetoric-style-summary.md` | Running rhetoric & style narrative |
| `analyses/{talk_filename}.md` | Per-talk analysis files |
| [references/schemas-config.md](references/schemas-config.md) | Config fields + confirmed intents schema |
| [references/humor-post-mortem.md](references/humor-post-mortem.md) | Protocol for grading humor effectiveness |
| [references/blind-spot-moments.md](references/blind-spot-moments.md) | Protocol for capturing audience/room data |

## Step 1 — Rhetoric Clarification

For each surprising, contradictory, or ambiguous observation, ask one topic at a time
via `AskUserQuestion`: intentional vs accidental patterns, invisible context,
conflicting signals, and flagged improvement areas. Update summary and DB after each answer.

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

Proceed immediately to Step 2.

## Step 2 — Blind Spot Moments

Follow [references/blind-spot-moments.md](references/blind-spot-moments.md) — ask about audience reactions,
physical performance, and room context that transcripts cannot capture.

Proceed immediately to Step 3.

## Step 3 — Humor Post-Mortem

Follow [references/humor-post-mortem.md](references/humor-post-mortem.md) — walk through detected humor beats,
grade effectiveness, capture spontaneous material.

Proceed immediately to Step 4.

## Step 4 — Speaker Infrastructure (first session only)

If `config.clarification_sessions_completed` is already ≥ 1, skip this step — infrastructure was captured in the first session. Proceed immediately to Step 5.

Otherwise, ask for any empty config fields (`speaker_name` through `publishing_process.*`).
See [references/schemas-config.md](references/schemas-config.md) for the full field list and questions to ask.

Proceed immediately to Step 5.

## Step 5 — Structured Intent Capture

Store confirmed intents in the `confirmed_intents` array of the tracking DB.
Example:
```json
{
  "pattern": "delayed_self_introduction",
  "intent": "deliberate",
  "rule": "Use two-phase intro: brief bio at slide 3, full re-intro mid-talk",
  "note": "Speaker confirmed this is intentional — hooks audience before credentialing"
}
```
See [references/schemas-config.md](references/schemas-config.md) for the full schema.

Proceed immediately to Step 6.

## Step 6 — Set Improvement Goals

Close the coaching loop. Review Section 15 of `rhetoric-style-summary.md` — recurring
improvement themes, underused patterns, and any `regressed`/`stalled` goals from a
prior session — then ask the speaker (via `AskUserQuestion`, one topic at a time) which
**1–2** they want to focus on before the next batch of talks. Coaching only works when
the speaker owns the target, so never auto-pick more than they choose.

For each chosen focus area, write a **complete** `improvement_goals` record to the
tracking DB per the schema — every field, not a subset. A partial record can't be
verified: vault-ingress needs `metric` to compute `current_value`, and `id`/`issue`/
`kind` to identify and route the goal. Set `id` (kebab-case), `issue`, `kind`, `metric`,
`baseline_value` (from the current Section 15 figure), the speaker's stated `target`,
`status: "active"`, `set_date` to today, `set_by: "vault-clarification"`, `current_value: ""`,
`last_checked: null`, `checked_by: null`, and `schema_version: 1`. Retire goals the
speaker no longer wants (`status: "retired"`); leave `achieved` goals in place as history.
Full field list and `kind` values:
[references/schemas-config.md](references/schemas-config.md) Improvement Goals Schema.

A later vault-ingress run verifies these against the fresh baseline — see
[../vault-ingress/references/processing-rules.md](../vault-ingress/references/processing-rules.md)
Improvement Goal Verification.

If Section 15 has no recurring themes or underused patterns yet (early vault, too few
talks for a baseline), say so and skip goal-setting — proceed to Step 7.

Proceed immediately to Step 7.

## Step 7 — Mark Session Complete

Increment `config.clarification_sessions_completed` in the tracking DB. This counter
gates profile generation (vault-profile skill requires >= 1).

Finish here.

## Important Notes

- One topic at a time — don't dump all questions at once.
- Update the summary and DB after each answer, not in a batch at the end.
- After completing a session, suggest running the **vault-profile** skill if 10+ talks
  are processed and the profile hasn't been generated yet.
