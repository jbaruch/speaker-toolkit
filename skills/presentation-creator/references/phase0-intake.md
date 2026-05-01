# Phase 0: Intake & Context Loading — Detail

### Step 0.1: Load the Vault

Read three vault documents in order from the vault root.

**A. Rhetoric vault summary** — `rhetoric-style-summary.md`

The constitution. Contains all cataloged patterns across rhetoric dimensions,
areas for improvement, speaker-confirmed intent, and per-talk observation log.

Pay special attention to the Speaker-Confirmed Intent section. These are ground-truth
design decisions that override any pattern inference. Read the `confirmed_intents` array
in the speaker profile for the structured version.

**B. Slide design spec** — `slide-design-spec.md`

Visual design reference: background colors, typography, footer structure, shape census,
template layout catalog, and generation rules.

**C. Speaker profile** — `speaker-profile.json`

Structured design decisions: presentation modes, rhetoric defaults, confirmed intents,
guardrail sources, pacing data, infrastructure, and instrument catalog.

**The summary is the rich narrative; the profile is the structured data.** When you
need nuance, voice examples, or context — read the summary. When you need thresholds,
counts, or rules — read the profile.

**Freshness check:** Compare `speaker-profile.json` → `generated_date` against the
`Last updated` line in `rhetoric-style-summary.md`. If the summary is newer, warn:

> "The vault summary was updated {date} but the speaker profile was generated {date}.
> Run 'update speaker profile' to sync, or proceed with the current profile?"

### Step 0.2: Gather User Context

Extract from the conversation what the user has already shared. Common starting points:

- "I need a talk about X for Y conference" — topic and venue known
- "I got accepted to speak at X, help me build the talk" — venue known, topic TBD
- "I want to adapt my [talk name] talk for X" — adaptation scenario
- "Write me a CFP for X conference" — abstract-writing scenario
- "I have this idea about X, could it be a talk?" — exploratory scenario

### Step 0.3: Set the Audience-as-Hero Stance

Before any further data-gathering, set the planning stance for the rest of the workflow. Per the `mentor` pattern (and Duarte's central reframe in *Resonate*), the talk's planning posture is **audience-as-hero, presenter-as-mentor** — Yoda not Luke; Mr. Miyagi not Daniel.

This is not just a delivery posture; it shapes every Phase 0–6 decision. Before moving to the spec, ask the speaker (or yourself if the speaker has already articulated it):

> "Who is the audience, and what journey are they on that you can mentor them through?"

The answer surfaces three things at once: who the hero is, what their current ordinary world looks like, and what the special world (the proposed change) is. If the speaker frames the answer as "I want to talk about X" (presenter-as-hero — your topic at the center), redirect: "What does the audience need to walk away with, that they don't currently have?" The reframe matters because every downstream decision (thesis, structure, examples, asks, visuals) is sized differently depending on whether the speaker is at the center or the audience is.

### Step 0.4: Report and Advance

Summarize what you know and what you need.
