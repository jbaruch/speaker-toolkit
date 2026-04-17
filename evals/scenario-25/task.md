# Post-Event Video Publishing: Plan the Workflow

## Problem/Feature Description

A speaker delivered "Robocoders: Judgment Day" at DevNexus 2026 three weeks ago. The recording is now on YouTube at `https://youtube.com/watch?v=abc123`. The speaker wants to add the video recording to their shownotes page so visitors can watch the talk.

However, the talk was rushed to delivery and **Phase 6 publishing was never completed** — shownotes were never published. The tracking database shows `shownotes_published: false` for this talk and there is no `shownotes_url` recorded.

Using the presentation-creator skill, produce a workflow plan for adding the video to shownotes. The plan must identify all prerequisites, flag any blockers, and describe the complete sequence of steps needed — including any prerequisite steps that must happen first.

## Output Specification

Produce the following files:

1. **`workflow-plan.md`** — A complete workflow plan including:
   - All prerequisite checks performed and their results
   - Any blockers or gaps discovered (missing files, missing shownotes, etc.)
   - The full sequence of steps needed, in order, including any prerequisite steps
   - For each step: what it does, what tool/script is used, and what it depends on
   - How the video embed/link will be formatted (per the speaker profile config)
2. **`prerequisites-check.md`** — A checklist of all files and prerequisites verified before planning, and their status (found/missing/not-applicable)

## Input Files

Download vault fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-25"
mkdir -p inputs/vault inputs/talk
curl -L -o inputs/vault/speaker-profile.json "$BASE/speaker-profile.json"
curl -L -o inputs/vault/tracking-database.json "$BASE/tracking-database.json"
curl -L -o inputs/talk/presentation-spec.md "$BASE/presentation-spec.md"
curl -L -o inputs/talk/presentation-outline.md "$BASE/presentation-outline.md"
```

## Key Parameters

- **YouTube URL:** `https://youtube.com/watch?v=abc123`
- **Talk slug:** `2026-04-16-devnexus-robocoders-judgment-day`
- **Shownotes status:** NOT published (shownotes_published: false in tracking DB, no shownotes_url)
- **Video publishing:** enabled in profile (embed_method: both)
