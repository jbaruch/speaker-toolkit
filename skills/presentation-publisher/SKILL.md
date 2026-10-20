---
name: presentation-publisher
description: >
  Prepare an existing talk for delivery: curate resources, create or replace QR
  codes and short links, coordinate exports and shownotes, and run the speaker's
  publishing checklist. Use for QR requests, resource curation, go-live
  preparation, and full publishing workflows. Shownotes-only requests use
  shownotes-publisher; thumbnails use illustrations.
user-invocable: true
---

# Presentation Publisher

This skill is an action router — pick the step that matches the user's intent and execute only that step. Do not run other steps; do not parallelize.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
talk, vault, and output paths remain consumer-owned.

Read [runtime-and-context.md](../presentation-creator/references/runtime-and-context.md)
for the selected action. Step 5 forwards directly without loading publishing
context. Steps 1–4 load the profile's `publishing_process` and required talk
metadata through the non-owner outline reader. Route refused outlines to
`Skill(skill: "presentation-creator")`; resume after repair. Paired external and
tracking effects require an owner-current database first. Credentials apply only
to the selected service; pass credential paths to scripts without displaying keys.

## Step 1 — Publish a Talk

Input: approved talk directory and deck, plus the requested publishing scope.
Read [workflow.md](references/workflow.md). This action explicitly chains
resource curation, configured shownotes, QR replacement, final export, and delivery
preparation in the documented order. Respect disabled profile features and the
author's exclusions. Obtain missing workflow choices one at a time.
Return the verified publishing report. Finish here.

## Step 2 — Curate Resources

Read [resources.md](references/resources.md). Extract candidates with the existing
script, obtain the author's approval, and persist through the owner mutation
contract when requested. An extraction-only request finishes with the reviewed
local artifact and performs no tracking or publishing side effects.
Finish here; do not run the rest of the workflow.

## Step 3 — Publish a QR Code

Read [qr.md](references/qr.md). Use the confirmed outline slug and configured
target/shortener. Require only the chosen provider's credentials, or the
provider's configured MCP tool. An explicit `shortener: none` needs no API key.
Preserve replacement-in-place, URL verification, short-link identity, and the
script's transaction/error receipts. Finish here with the PNG/deck and link report.

## Step 4 — Prepare Delivery

Read [delivery.md](references/delivery.md). Generate requested timing artifacts,
run configured additional steps within authorization, and surface the go-live
checklist. Finish here with output paths and remaining speaker actions.

## Step 5 — Forward a Publishing Task

For deck export, invoke `Skill(skill: "presentation-builder")` with action export.
For Jekyll shownotes or recording updates, invoke
`Skill(skill: "shownotes-publisher")` with the talk directory and supplied URLs.
For thumbnails, invoke `Skill(skill: "illustrations")` with the requested action.
For another shownotes system, read [shownotes.md](references/shownotes.md), or
[recording.md](references/recording.md) for an existing page's recording update.
Finish here when that single action returns; do not run other publishing steps.
