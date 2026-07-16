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

### Step 0.4: Read the Audience Spread

Ask a second audience question, and ask it now rather than at review time — it decides what gets built, not just what gets scored:

> "Is this room mixed in what it accepts as proof, or does it all speak one language?"

This is the `walk-around` cover-or-match decision (see `references/patterns/prepare/walk-around.md`), and it sets the required `talk.audience_spread` field.

- **`heterogeneous`** — a conference keynote, an all-hands, a mixed-seniority room. The talk covers all four registers: **A** precision and evidence, **B** process and sequence, **C** human impact, **D** implication. Each register left unanswered is a slice of the room whose question the talk never reaches.
- **`homogeneous`** — one engineering team, a board, a room of clinicians. The talk matches the room's register, and `talk.dominant_register` names it. Airtime spent on registers nobody in the room uses is stolen from the one everybody uses.

Two failure modes to head off while the speaker is still answering:

1. **Homogeneity asserted from job titles.** "They're all engineers" describes badges, not what persuades them — the engineer who wants to know who gets paged is in that room. Push once: "what makes you confident they all want the same kind of proof?" Unverified ⇒ `heterogeneous`. Coverage is the safe default; matching is the bet.
2. **The speaker's own register answering for the room.** The register a speaker reaches for is the one they find convincing, which makes it invisible to them. Ask what kind of evidence *they* would want, note it, and treat it as the register most at risk of crowding out the other three (see `_anti_golden-rule.md`).

Record the answer in the spec. `check-rhetorical.py` enforces it at Phase 4 — heterogeneous talks must answer all four registers across their declared `walk-around` applications; homogeneous talks must actually answer their declared dominant register. Neither is a judgment the script makes: the agent decides which registers a claim lands, the script checks the union.

### Step 0.5: Report and Advance

Summarize what you know and what you need.
