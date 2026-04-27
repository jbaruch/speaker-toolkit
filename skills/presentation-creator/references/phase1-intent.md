# Phase 1: Intent Distillation — Detail

### The Art of Asking

**Ask each question individually. Wait for the answer before asking the next.**
Never present multiple questions in a single message — see the `interaction-rules` steering rule.

Use `AskUserQuestion` for structured choices when the vault provides a finite set
of options (mode, profanity register, commercial intent, yes/no confirmations).
Use conversational text for open-ended questions ("Tell me about the audience") —
but still one at a time.

**Question order** (ask about what's missing, skip what's already known):
1. Purpose & thesis (the "what" and "why")
2. Audience & venue specifics (the "who" and "where")
3. Constraints & preferences (the "how" and "how not")

**Concrete examples:**

```
AskUserQuestion(
  question: "Which presentation mode fits this talk?",
  options: [
    {label: "Slide-driven polemic (Recommended)", description: "Your default — opinionated thesis with visual evidence"},
    {label: "Live-coding with slides", description: "Demo-heavy with supporting slides"},
    {label: "Panel / fireside chat", description: "Conversational, minimal slides"}
  ])
→ wait for answer →

AskUserQuestion(
  question: "What profanity register for JCON Europe?",
  options: [
    {label: "Moderate — damn/hell (Recommended)", description: "Your vault default"},
    {label: "Clean — no profanity", description: "Corporate or family audience"},
    {label: "Unrestricted", description: "Anything goes"}
  ])
→ wait for answer →

"Any venue-specific context I should know about JCON Europe?"
→ wait for answer →

AskUserQuestion(
  question: "Any commercial intent for this talk?",
  options: [
    {label: "None (Recommended)", description: "Pure thought leadership"},
    {label: "Subtle", description: "Product woven into narrative"},
    {label: "Direct", description: "Explicit product pitch"}
  ])
→ wait for answer →

AskUserQuestion(
  question: "Generated slug: 2026-06-23-jcon-robocoders — confirm?",
  options: [
    {label: "Looks good (Recommended)", description: "Use this slug for shownotes and QR"},
    {label: "I want to adjust", description: "Let me edit the slug"}
  ])
```

**Use the vault to inform questions.** If the topic overlaps with existing talks in
the vault, reference them: "This overlaps with your [talk name] territory. Should
we build on that argument or take a different angle?"

### Co-Presented Talks

If the spec has a co-presenter:
- Identify who owns which expertise domain
- Determine the role split: provocateur/depth, alternating sections, or parallel tracks
- Clarify whose deck/template to use (default: the vault speaker's template)
- Determine how handoffs work (verbal cue, slide type change, both)
- Use `[SPEAKER A]:` / `[SPEAKER B]:` prefixes in all speaker notes throughout the outline

### Shownotes Slug Generation

The slug is NOT free-form. Conventions drift over time (older analyses often
encode retired naming patterns), so derive from CURRENT shownotes entries, not
whatever examples happen to be loaded in context.

**Step 1 — Observe the current convention.** List the most recent entries in
the speaker's live shownotes directory (source location comes from the vault's
shownotes config — see `vault_root/speaker-profile.json`). Examples:

```
ls {shownotes_talks_dir} | sort -r | head -20
```

Extract the actual pattern from the latest 5–10 entries. Note that the current
convention may differ from older convention examples that appear in archived
analyses. Trust the live directory, not the analyses.

**Step 2 — Read the declared convention.** Check
`publishing_process.shownotes.slug_convention.template` in the speaker
profile. If it matches what you observed in Step 1, use it. If it disagrees
with recent entries, the profile is stale — treat the observed convention as
authoritative and offer to update the profile (via vault-clarification) at
the end of the phase.

**Step 3 — Derive the slug mechanically.** Apply the convention to this talk's
metadata (date, venue, title). Example convention:

```
Convention: {venue-compact}{yy}-{short-talk-id}
Input:      DevNexus 2026-04-16, "Robocoders: Judgment Day"
Result:     devnexus26-robocoders
```

**Step 4 — Confirm once, not as a menu.** Present a SINGLE generated slug for
confirmation, not 2–3 options. If the convention is genuinely ambiguous (e.g.,
the last 10 entries show two different patterns), show 2–3 examples from the
live directory and ask the speaker which pattern applies — don't freestyle.

**Step 5 — Backfill if needed.** If
`publishing_process.shownotes.slug_convention.template` was `null` or missing,
hand off to vault-clarification at end-of-phase to persist the observed
convention in the profile (and populate
`slug_convention.examples` with the recent live slugs). Next run shouldn't
need Step 1 again.

Rules:
- Kebab-case, lowercase, no special characters.
- NEVER invent a slug from convention-like patterns you saw in analyses —
  those are snapshots of whatever was current when the analysis was written.
- The confirmed slug goes into the Presentation Spec as `Shownotes slug:` and
  is persisted in `presentation-spec.md`. All downstream uses (Phase 6
  shownotes URL, QR code `--talk-slug`, directory name) must use this exact
  slug.

### Spec Validation

Before presenting the spec, cross-check:
- Does the thesis pass the "one sentence" test?
- Does the time slot match the content ambition?
- Is the mode selection consistent with the audience?
- Are there contradictions? (e.g., "zero profanity" + "heavy meme density" — flag it)
- If co-presented: is the role split clear? Does each presenter have enough airtime?

### When Adapting Existing Talks

Pre-fill the spec from the vault's analysis of the original talk:
1. Read the original talk's entry in the tracking database
2. Read its analysis file from `{vault_root}/analyses/`
3. Pre-populate: mode, opening type, narrative arc, humor register, closing pattern
4. Present to author: "Here's the original spec. What changes for the new venue?"
