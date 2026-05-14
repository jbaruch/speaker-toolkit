# Route a Single Request to the Right Illustrations Mode

## Problem/Feature Description

A speaker drops into a Claude Code session at a talk's working directory and types one short request. The illustrations skill operates in three modes — Strategy (define visual identity), Generation (produce deck illustrations + builds + apply them to the deck), and Thumbnail (Phase 7 YouTube thumbnail). Picking the wrong mode wastes the speaker's time: starting Strategy when they want a thumbnail means a 20-question style discussion; jumping to Generation when there's no STYLE ANCHOR yet produces empty output.

For each of the three requests below, decide which mode(s) apply and which steps the skill will execute. The talk directory state is given for each request.

### Request A — `"design the visual style for this talk"`

State at trigger time:
- `outline.yaml` exists; the top-level `style_anchor:` key is absent (talk has no illustration strategy yet).
- `illustrations/` directory does not exist.
- No deck `.pptx` file exists yet.
- The speaker has been working through Phase 2 of presentation-creator and decided they want generated illustrations.

### Request B — `"generate the illustrations for this talk"`

State at trigger time:
- `outline.yaml` has a `style_anchor:` block and per-slide `format:` + `image_prompt:` fields.
- Three slides have a `builds:` list defining 3-step progressive reveals.
- `illustrations/` directory has 4 of 12 slide images already (manually uploaded). 8 are missing.
- A clean deck `.pptx` exists from Phase 5 Step 5.1, with structural slides built but no illustrations applied yet.

### Request C — `"make me a YouTube thumbnail for the DevNexus talk"`

State at trigger time:
- The talk was delivered 10 days ago. `outline.yaml` and the final `.pptx` exist.
- The speaker provides a YouTube URL: `https://youtube.com/watch?v=xyz789`.
- `illustrations/` exists with all slide images applied to the final deck.
- No `thumbnail.png` exists yet.

## Output Specification

Produce one file: **`mode-routing-plan.md`**, structured as:

```markdown
# Mode Routing Plan

## Request A — "design the visual style for this talk"
- Mode(s): <list>
- Steps to execute: <list, in order>
- Steps to skip: <list>
- Why this routing: <one sentence>

## Request B — "generate the illustrations for this talk"
- Mode(s): <list>
- Steps to execute: <list, in order>
- Steps to skip: <list>
- Why this routing: <one sentence>

## Request C — "make me a YouTube thumbnail for the DevNexus talk"
- Mode(s): <list>
- Steps to execute: <list, in order>
- Steps to skip: <list>
- Why this routing: <one sentence>
```

## Inputs Provided

No fixture files — the state descriptions above are the inputs.
