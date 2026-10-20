---
name: presentation-builder
description: >
  Build a PowerPoint or presenterm deck from an approved talk outline, edit an
  existing deck, or export slides to PDF. Use for slide construction, layout
  changes, deck edits, and standalone exports. New-talk argument and content
  development belongs to presentation-creator.
user-invocable: true
---

# Presentation Builder

This skill is an action router — pick the step that matches the user's intent and execute only that step. Do not run other steps; do not parallelize.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
talk, vault, and output paths remain consumer-owned.

Read [runtime-and-context.md](../presentation-creator/references/runtime-and-context.md)
for the selected action only. Build actions read the current outline through
its non-owner reader and branch on `talk.engine`. A missing engine or rejected
outline invokes `Skill(skill: "presentation-creator")` for that repair; resume
the original action after repair. Do not migrate or edit the owner's outline.

## Step 1 — Build PowerPoint

Input: approved `outline.yaml`, regenerated `slides.md`, template and layout map
from the profile. Read [powerpoint.md](references/powerpoint.md) and
[design.md](references/design.md). Run the deck doctor; load
[deck-editing-setup.md](references/deck-editing-setup.md) only for its named repair.
Read [deckops-spec.md](references/deckops-spec.md) when emitting operations.

Use the real PowerPoint build scripts. If the outline has a style anchor,
invoke `Skill(skill: "illustrations")` after deck structure exists; resume with
approved images and manifests. Complete expansion, remaining notes, and final
backgrounds in that order, keyed on post-expansion positions.

Present the deck, build report, and unresolved author placeholders. Iterate
through Step 3 only when the author requests edits. Finish here when slides are
done; return paths to the calling creator. Export or publishing runs only when
requested, with export chaining explicitly to Step 4.

## Step 2 — Build Presenterm

Input: approved outline and `slides.md`. Read
[presenterm.md](references/presenterm.md) and [design.md](references/design.md).
Author `{slug}.md` using the chosen theme and speaker notes. PowerPoint setup,
layout operations, and illustration credentials are not prerequisites.
Present the deck for iteration. Finish here when done; an explicitly requested
export continues to Step 4.

## Step 3 — Edit a Deck

Input: existing deck, requested change, and relevant profile design settings.
Read [editing.md](references/editing.md) for PowerPoint; presenterm edits use
[presenterm.md](references/presenterm.md). Load design guidance for visual edits.

Content changes to a deck backed by `outline.yaml` first invoke
`Skill(skill: "presentation-creator")` for the source edit and regeneration;
resume with the affected build-sheet. Preserve the original deck and template.
Finish here with the edited deck, or continue to Step 4 when export was requested.

## Step 4 — Export a Deck

Input: existing deck path, requested format, and output path. Read
[export.md](references/export.md). An isolated export needs no complete outline,
rhetoric summary, pattern history, image credentials, QR config, or shownotes.
Return the verified output path. Finish here; do not start publishing.
