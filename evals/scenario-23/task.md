# Plan the Publishing Workflow for a Completed Talk

## Problem/Feature Description

A speaker has finished their presentation "Robocoders: Judgment Day" (all slides done, guardrails passed) and is ready to publish. Their profile has shownotes publishing enabled (git push method) and QR code generation. The speaker wants a complete publishing plan covering all steps from the presentation-creator skill's Phase 6 workflow.

Using the presentation-creator skill, produce a detailed publishing plan that covers every step in the correct order, including how the shownotes resource links section will be populated.

## Output Specification

Produce the following files:

1. **`publishing-plan.md`** — A step-by-step plan for the entire publishing workflow, in execution order. For each step:
   - Step number and name
   - What script or action is used
   - What inputs it needs
   - What it produces
2. **`shownotes-draft.md`** — A draft of the shownotes page content, including the resource links section. Show where resource links come from and how they were gathered.

## Input Files

Download vault fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-23"
mkdir -p inputs/vault inputs/talk
curl -L -o inputs/vault/speaker-profile.json "$BASE/speaker-profile.json"
curl -L -o inputs/vault/tracking-database.json "$BASE/tracking-database.json"
curl -L -o inputs/talk/presentation-spec.md "$BASE/presentation-spec.md"
curl -L -o inputs/talk/presentation-outline.md "$BASE/presentation-outline.md"
```

## Key Parameters

- **Talk slug:** `2026-04-16-devnexus-robocoders-judgment-day`
- **Shownotes URL:** `https://jbaru.ch/2026-04-16-devnexus-robocoders-judgment-day`
- **Shownotes publishing:** enabled, git push method
- **QR code:** enabled, shownotes_url target, shortener: none
- The outline contains several URLs, a GitHub repo, an RFC reference, a book citation, and tool mentions
