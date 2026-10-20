---
name: presentation-creator
description: >
  Develop or adapt a speaker's talk from an idea through an approved outline,
  narrative, and speaker notes, grounded in their rhetoric vault. Use for new
  talks, audience adaptations, rhetorical architecture, outline revisions, and
  outline-schema repair. Coordinate deck building and publishing when requested.
user_invocable: true
---

# Presentation Creator

Process steps in order. Do not skip ahead.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
talk, vault, and output paths remain consumer-owned.

## Step 0 — Select Entry

A new talk starts here. For an adaptation, also read
[adapting.md](references/adapting.md). Resume an existing outline at its first
unfinished phase; preserve confirmed metadata and approvals.

Forward independent requests with the talk directory and requested action:

- Build, edit, or export a deck: `Skill(skill: "presentation-builder")`.
- Resources, QR, or publishing coordination: `Skill(skill: "presentation-publisher")`.
- CFP or sessions catalog: `Skill(skill: "cfp-writer")`.
- Thumbnail or illustration: `Skill(skill: "illustrations")`.
- Shownotes or recording update: `Skill(skill: "shownotes-publisher")`.

Finish here after a forwarded single task. An outline repair handoff reads
[outline-handoff.md](references/outline-handoff.md), repairs only that outline,
and returns to the caller; finish here.

For authoring, read [runtime-and-context.md](references/runtime-and-context.md)
and resolve the read-only outline runtime. Load the rhetoric summary and speaker
profile; open slide design guidance when a visual decision needs it.
Read [phase0-intake.md](references/phase0-intake.md) to capture topic, audience,
venue, and constraints. The vault's confirmed speaker intents govern style.
Proceed immediately to Step 1.

## Step 1 — Distill Intent

Read [phase1-intent.md](references/phase1-intent.md). Ask about missing context,
one question at a time. Author the `talk:` metadata in `outline.yaml`, with
root `schema_version: 2`; metadata fields live in
[phase3-content.md](references/phase3-content.md#the-talk-block).

Use the profile's presentation-directory and live slug conventions. The outline
is the source of truth; do not create a separate presentation spec.
Use [outline-artifacts.md](references/outline-artifacts.md) to generate partial
`narrative.md`. Present the TL;DR and metadata for approval.
After the author confirms, proceed immediately to Step 2.

## Step 2 — Architect the Talk

Read [phase2-architecture.md](references/phase2-architecture.md). Select the
rhetorical instruments jointly with the author. Record engine/theme,
architecture, patterns, chapters, timing, and argument beats in the same outline.

Use [pattern-menu.md](references/pattern-menu.md) to find relevant patterns.
Before historical recommendations, read
[pattern-history-authorization.md](references/pattern-history-authorization.md)
and run its status command; require the domain for each historical claim.
With no authorized history, use a flat current-taxonomy menu.

For requested AI illustrations, invoke `Skill(skill: "illustrations")` for
strategy and the approved style anchor; resume here when it returns.
Regenerate partial `narrative.md`. Obtain approval of the argument and
architecture before writing per-slide content. Proceed immediately to Step 3.

## Step 3 — Develop Content

Read [phase3-content.md](references/phase3-content.md). Fill `slides[]`,
`interludes[]`, speaker notes, callbacks, builds, and typed placeholders in
`outline.yaml`. Use the owner narration-rate contract linked there.

Validate and regenerate the four derived artifacts using
[outline-artifacts.md](references/outline-artifacts.md). Deliver the draft.
Proceed immediately to Step 4.

## Step 4 — Revise the Outline

Read [phase4-guardrails.md](references/phase4-guardrails.md). Apply feedback,
regenerate artifacts, and run both structural and speaker-aware checks. Preserve
emitted recurrence records; current-outline warnings remain contextual.
Flag intentional guardrail overrides without blocking them.

After the author declares the outline done, invoke `Skill(skill: "cfp-writer")`
only to save approved submission materials if the catalog lacks this talk;
resume here after the catalog update. Proceed immediately to Step 5.

## Step 5 — Hand Off Approved Work

An outline-only request finishes here with the outline and derived artifact paths.
For an authorized deck build, invoke `Skill(skill: "presentation-builder")`
with the talk directory, approved outline, build-sheet, and chosen engine.
Resume here after the author declares the slides done.

When publishing is in scope, invoke `Skill(skill: "presentation-publisher")`
with the approved deck and talk directory. It returns a publishing report after
verification. Finish here. Post-event requests enter the existing thumbnail or
shownotes skill directly.
