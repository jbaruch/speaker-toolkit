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

**Pattern-history authorization:** run
`python3 "{speaker_toolkit_root}/skills/presentation-creator/scripts/pattern_history_status.py"` against the loaded
profile and summary before reading any catalog-derived history. Use `-` as its profile
argument when no profile exists. Its JSON `history_enabled` value is the sole creator
classification gate; surface a disabled result's exact `warning`.
`opportunity_rows_available: true` means only that exact raw occurrence rows are
auditable; it does not authorize history tiers or labels. A valid profile source always wins;
the summary is a fallback and never merges with it. A disabled history lane does not
invalidate the whole profile. Keep using independent pacing, visual, infrastructure,
publishing, presentation-mode, instrument-catalog, and confirmed-intent fields.

Until history is enabled, do not read or repeat signature/contextual-history/
New-to-You tiers, strengths, underuse, by-mode pattern history, recurring antipattern
labels, or pattern-derived recurring issues and badges. The current pattern taxonomy
remains available for analyzing the new outline. A profile schema v1/v2/v3 is therefore
a non-pattern compatibility input, not evidence of speaker pattern history.
Schema-v4 top-level `guardrail_sources.recurring_issues[]` and `badges[]` are separate:
use an entry only when it explicitly carries `source_lane: "non_pattern"`. Catalog
warnings and reinforcement come from authorized `pattern_profile` history, never from
an unmarked duplicate in a top-level lane.

If the profile is absent, malformed, or history-disabled, Section 15 does not restore
history by implication. Use Section 15 history only when its current block carries
explicit provenance matching the bundled catalog/scoring generation and a complete
structured contract accepted by
`python3 "{speaker_toolkit_root}/skills/vault-profile/scripts/section15_pattern_history.py"`. That parser delegates the
payload to the shared profile provenance assessor, and classifications still require
`classification_fields_available: true`. A date, a recent heading, an
unlabeled count, or ordinary prose is insufficient; use taxonomy-only fallback when
the proof is absent.

When an older profile is available for comparison, compare catalog fingerprint and
pattern-scoring schema before catalog-derived values. Different identities mean a
generation reset. Report the reset, but do not describe the score, frequency, mastery,
strength, or underuse differences as improvement or regression. Even within one
generation, raw-score comparisons are unavailable across a changed or null
`opportunity_coverage_identity`.

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
2. **The speaker's own register answering for the room.** The register a speaker reaches for is the one they find convincing, which makes it invisible to them. Ask what kind of evidence *they* would want, note it, and treat it as the register most at risk of crowding out the other three (see `references/patterns/prepare/_anti_golden-rule.md`).

Record the answer in the spec. `check-rhetorical.py` enforces the declaration at Phase 4; its decision contract lives in `_check_register_coverage`'s docstring.

What this step owes that check: `talk.audience_spread`, `talk.dominant_register` when the room is homogeneous, and — during Phase 3 — a `registers:` list on each `walk-around` application naming which questions that claim answers. Judging which registers a claim lands is the agent's call; the script only reads what the agent declared.

### Step 0.5: Report and Advance

Summarize what you know and what you need.
