---
name: cfp-writer
description: >
  Write or adapt conference CFP submissions, talk titles, abstracts, takeaways,
  and speaker bios in the speaker's documented voice. Maintain the sessions
  catalog of approved submission materials. Use for CFPs, conference proposals,
  abstract revisions, and sessions-catalog reads or updates.
user-invocable: true
---

# CFP Writer

This skill is an action router — pick the step that matches the user's intent and execute only that step. Do not run other steps; do not parallelize.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
talk, vault, and output paths remain consumer-owned.

Read [runtime-and-context.md](../presentation-creator/references/runtime-and-context.md)
for the CFP/catalog context. Load the speaker's voice/profile and the relevant
sessions-catalog entry. A complete outline, visual design spec, slide engine,
publishing setup, pattern-history classification, and API secrets are not required.
This skill owns sessions-catalog writes; presentation-creator owns outline shape
and migration. Do not write or migrate `outline.yaml` here.

## Step 1 — Write a Submission

Read [submissions.md](references/submissions.md). Capture missing audience, venue,
submission limits, thesis, and takeaways one question at a time. Adapt approved
catalog material before creating another version of the same talk.

Draft title, abstract, takeaways, and speaker bio within the venue's actual limits.
Review the promise against the proposed talk and iterate with the author. Once
approved, explicitly continue to Step 2 to save the approved materials.
Do not start architecture selection, per-slide authoring, or deck building.

## Step 2 — Maintain the Sessions Catalog

Read [catalog.md](references/catalog.md). For a read request, return relevant
entries and finish here. For an approved update, save only the requested title,
abstract, outline, and Program Committee notes; preserve unrelated entries.
Run the documented prose check before saving and maintain the update date.

A handoff from presentation-creator saves its already-approved materials without
restarting the CFP interview. Return the catalog entry to the caller. Finish here.
