# Phase 0: Intake and Context

Resolve the read-only outline runtime using
[runtime-and-context.md](runtime-and-context.md). Read the rhetoric summary and
speaker profile for voice, confirmed intent, and structured configuration. Read
only a relevant sessions-catalog entry when checking overlap with active talks.
The visual design spec is opened when a visual decision needs it.

The summary supplies nuance and examples; the profile supplies configuration.
Compare freshness when both are loaded. Pattern-history authorization is deferred
to historical pattern selection/review; use
[pattern-history-authorization.md](pattern-history-authorization.md) before any
such claim. An unavailable history domain does not disable independent profile
configuration.

### Gather User Context

Extract from the conversation what the user has already shared. Common starting points:

- "I need a talk about X for Y conference" — topic and venue known
- "I got accepted to speak at X, help me build the talk" — venue known, topic TBD
- "I want to adapt my [talk name] talk for X" — adaptation scenario
- "Write me a CFP for X conference" — abstract-writing scenario
- "I have this idea about X, could it be a talk?" — exploratory scenario

### Set the Audience-as-Hero Stance

Before any further data-gathering, set the planning stance for the rest of the workflow. Per the `mentor` pattern (and Duarte's central reframe in *Resonate*), the talk's planning posture is **audience-as-hero, presenter-as-mentor** — Yoda not Luke; Mr. Miyagi not Daniel.

This is not just a delivery posture; it shapes every Phase 0–6 decision. Before moving to the spec, ask the speaker (or yourself if the speaker has already articulated it):

> "Who is the audience, and what journey are they on that you can mentor them through?"

The answer surfaces three things at once: who the hero is, what their current ordinary world looks like, and what the special world (the proposed change) is. If the speaker frames the answer as "I want to talk about X" (presenter-as-hero — your topic at the center), redirect: "What does the audience need to walk away with, that they don't currently have?" The reframe matters because every downstream decision (thesis, structure, examples, asks, visuals) is sized differently depending on whether the speaker is at the center or the audience is.

### Read the Audience Spread

Ask a second audience question, and ask it now rather than at review time — it decides what gets built, not just what gets scored:

> "Is this room mixed in what it accepts as proof, or does it all speak one language?"

This is the `walk-around` cover-or-match decision (see `references/patterns/prepare/walk-around.md`), and it sets the required `talk.audience_spread` field.

- **`heterogeneous`** — a conference keynote, an all-hands, a mixed-seniority room. The talk covers all four registers: **A** precision and evidence, **B** process and sequence, **C** human impact, **D** implication. Each register left unanswered is a slice of the room whose question the talk never reaches.
- **`homogeneous`** — one engineering team, a board, a room of clinicians. The talk matches the room's register, and `talk.dominant_register` names it. Airtime spent on registers nobody in the room uses is stolen from the one everybody uses.

Two failure modes to head off while the speaker is still answering:

1. **Homogeneity asserted from job titles.** "They're all engineers" describes badges, not what persuades them — the engineer who wants to know who gets paged is in that room. Push once: "what makes you confident they all want the same kind of proof?" Unverified ⇒ `heterogeneous`. Coverage is the safe default; matching is the bet.
2. **The speaker's own register answering for the room.** The register a speaker reaches for is the one they find convincing, which makes it invisible to them. Ask what kind of evidence *they* would want, note it, and treat it as the register most at risk of crowding out the other three (see `references/patterns/prepare/_anti_golden-rule.md`).

Record the answer in the spec. `check-rhetorical.py` enforces the declaration at Phase 4; its decision contract lives in `_check_register_coverage`'s docstring.

What this step owes that check: `talk.audience_spread`, `talk.dominant_register` when the room is homogeneous, and — during Phase 3 — a `registers:` list on each `walk-around` application naming which questions that claim answers. Judging which registers a claim lands is the agent's call; the script only reads what the agent declared.

### Report and Advance

Summarize what you know and what you need.
