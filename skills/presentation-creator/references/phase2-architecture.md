# Phase 2: Rhetorical Architecture — Detail

### Plan Analog Before Going Digital

Architecture decisions in this phase happen at the conceptual level — mode, opening pattern, narrative arc, sectioning, pattern strategy. These are best worked out **away from slideware**. Reynolds is emphatic: opening a presentation tool during planning prematurely commits the author to a template, a layout, and a default font when those decisions should still be fluid.

When the author is making architecture decisions in this phase, encourage analog tools — paper sketches, whiteboard diagrams, Post-it notes — for working through the structure before any slide is created. The five-step Reynolds workflow keeps slideware out of the picture for the first four steps: brainstorm → group/identify the core → analog storyboard → sketch visuals → only then transfer into slideware. Architecture decisions in this phase belong to steps 1–3; slideware belongs to Phase 5. See `patterns/prepare/concurrent-creation.md` for the full workflow.

### The Joint Selection Process

This phase is a conversation, not a monologue. **Use `AskUserQuestion` for each
instrument selection. One decision per turn.** Never combine multiple decisions into
a single message — see the `interaction-rules` steering rule.

For each decision:

1. **Extract the options** from the vault summary (sections 2-13) and speaker profile
   (`instrument_catalog`). The vault is the living source — new instruments appear
   as more talks are parsed.
2. **Present the options** via `AskUserQuestion` with brief descriptions
3. **Recommend** based on the spec — put the recommended option first with "(Recommended)"
4. **Wait for the author's choice** before moving to the next decision

### Mode Selection Logic

Read `presentation_modes[]` from the speaker profile. Each mode has a `when_to_use`
field — use these to build a selection logic table dynamically. Present the modes
with their descriptions and match signals from the spec.

### Opening Pattern Selection Logic

Read `instrument_catalog.opening_patterns[]` from the speaker profile. Each pattern
has a `best_for` field. Match to the spec's audience warmth, venue size, and context.

### Narrative Arc Templates

Read `instrument_catalog.narrative_structures[]` from the speaker profile. Each has
acts and `time_allocation`. Present the options with their time splits and best-for
context.

### Persuasive vs. Informative Architecture — Sparkline or Narrative Arc?

Before presenting narrative-arc templates, ask one upstream question: **is this talk primarily persuasive or primarily informative?**

- **Persuasive** = the audience is being asked to do or believe something different after the talk (sales pitches, strategic-direction announcements, fundraising, organizational change, advocacy keynotes, investor pitches).
- **Informative** = the audience needs to *understand* something but is not being asked to act on it differently (tutorials, technical deep-dives, scientific explanations, status updates, postmortems).

For **persuasive talks**, present `sparkline` (per `patterns/build/sparkline.md`) as the default top-level structural option. The sparkline's two named turning points (Call to Adventure, Call to Action) and "new bliss" close are purpose-built for moving audiences to action. Stack with one of the contrast-driven sub-structures inside the middle (problem-solution, compare-contrast, cause-effect, advantage-disadvantage).

For **informative talks**, present the existing narrative-arc templates (three-act and variants) as the default. The three-act structure suits content that needs to be understood; the sparkline is overkill and can feel manipulative when there's no genuine action to take.

The two patterns can coexist: an informative talk can have a small sparkline-shaped closing argument, and a persuasive talk can have informative sections inside its middle. But the choice of *top-level* structure matters because it shapes time allocation across the three sections — sparkline allocates ≤10% to "what is" baseline and most of the time to the persuasive middle; narrative-arc typically allocates ~25-50% to the middle, with longer setup and resolution.

When the speaker profile shows historical preference (most past talks tagged narrative-arc or sparkline), surface that history but do not let it override the persuasive-vs-informative diagnostic. A speaker accustomed to narrative-arc tutorials switching to a sales pitch should switch to sparkline for that talk; the architecture should match the talk's purpose, not the speaker's habit.

### Action Typology — Pre-Plan the Call to Action

When sparkline is selected (or whenever the talk includes a call-to-action moment), pre-plan the audience's action diversity at the architecture level. Per `patterns/build/call-to-action.md`, every audience contains four action-temperament types — **Doer** (instigates activities), **Supplier** (provides resources), **Influencer** (changes perceptions), **Innovator** (generates ideas) — and the call-to-action must address at least one ask per type.

This is an architecture-phase concern (not a content-phase one) because the asks shape the entire backward-design of the talk: if you can't name a credible Doer ask, the talk lacks an actionable thesis; if you can't name an Influencer ask, you haven't accounted for audience members who can't directly execute but can spread the idea. Write the four asks before writing any other content; the rest of the talk is in service of making them feel earned.

### Decision #10: Pattern Strategy

Read [patterns/_index.md](patterns/_index.md) for the full taxonomy and
`profile → pattern_profile` for the speaker's pattern history.

Present patterns in **4 tiers:**

```
PATTERN STRATEGY for "{talk title}"
===================================
YOUR TOOLKIT (signature):
  ✓ Narrative Arc (22/24 talks) — recommended for this format
  ✓ Bookends (18/24) — strong with this audience
  ✓ Expansion Joints (20/24) — essential for 45→20 min adaptation

WORTH CONSIDERING (contextual):
  ○ Talklet (3/24) — good fit for the 20-min constraint
  ○ Foreshadowing (7/24) — pairs well with your arc style

NEW TO YOU:
  ★ [NEW] Preroll — display bio/topic on screen before you start
  ★ [NEW] Seeding the First Question — plant an easy Q for Q&A

SHAKE IT UP:
  ⚡ [WILD CARD] Red, Yellow, Green — audience voting with colored cards
  ⚡ [WILD CARD] Cave Painting — one giant canvas instead of slides

WARNINGS:
  ⚠ Shortchanged (8/24 detections) — plan cut lines for the 20-min slot
  ⚠ Dual-Headed Monster — co-presented talk, define handoff points
===================================
```

**Tier logic:**
1. **Signature** — `mastery_level: signature` patterns (80%+ usage), always shown
2. **Contextual** — patterns matching spec context that speaker uses occasionally (10-80%)
3. **New to You** — from `never_used_patterns`, filtered by spec relevance, marked `[NEW]`
4. **Shake It Up** — 1-2 random picks from `never_used_patterns`, NOT filtered by relevance.
   Provocations, not prescriptions.

**Antipattern warnings** — merge speaker's recurring antipatterns (from
`pattern_profile.antipattern_frequency`) + contextual warnings derived from the spec
(co-presented → Dual-Headed Monster, dense content → Bullet-Riddled Corpse,
new format → Shortchanged, etc.)

**Summary-only mode** (no profile yet): Pattern taxonomy still works — patterns come
from the reference files alone (no usage stats). All patterns presented as "new" (no
tier separation, just a flat relevant-patterns list). Contextual antipattern warnings
still apply.

Enhance decisions 2-9 with pattern cross-references as shared vocabulary: when recommending
an opening pattern, reference the taxonomy ID; when selecting a narrative structure, note
which Presentation Patterns it maps to (e.g., "problem-solution" = Narrative Arc + Triad).

### Decision #11: Illustration Strategy (when applicable)

Not every talk needs generated illustrations — demo-heavy, data-heavy, or
screenshot-driven talks may not. When the author wants AI-generated illustrations,
delegate to the illustrations skill for the full collaboration (style proposals
grounded in vault `visual_style_history`, format vocabulary, model choice,
visual continuity devices):

```
Skill(skill: "illustrations")
```

The skill writes the approved STYLE ANCHOR block back into the outline header,
then returns control to Phase 2. Continue with the next decision (or the
architecture gate) once the skill returns.

### Slide Budget Calculation

Read `guardrail_sources.slide_budgets[]` from the speaker profile. Match the spec's
duration to the closest budget entry. Read `pacing` for WPM and slides/min targets.
