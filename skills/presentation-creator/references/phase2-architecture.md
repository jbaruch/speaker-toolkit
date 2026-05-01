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
this sub-decision walks through the visual identity collaboratively.

#### Step 1: Propose style ideas with sample prompts

Present 3-4 style options informed by **three sources**:

1. **The talk's own concepts, metaphors, and narrative** — the style should reinforce
   the thesis, not be decorative wallpaper
2. **The vault's visual history** — read `speaker-profile.json` →
   `visual_style_history` for the structured data: `default_illustration_style`,
   `style_departures[]` (what styles the speaker has used and what triggered them),
   `mode_visual_profiles[]` (which modes tend toward which aesthetics), and
   `confirmed_visual_intents[]` (hard rules about visual design). Also read
   `rhetoric-style-summary.md` (Section 13 cross-talk visual patterns),
   `slide-design-spec.md`, and `design_rules`. Know what the speaker's default
   looks like so you can propose informed departures
3. **Historical precedent for this mode/context** — read `visual_style_history` →
   `mode_visual_profiles` for the matching mode ID. If the vault shows the speaker
   uses a particular aesthetic for this talk type, surface that as a data point
   (e.g., "your vault shows you use terminal aesthetic for agent talks"). If this
   talk's mode/context has no visual precedent in `style_departures`, say so

Each option includes: a name, **why it fits this talk's concepts**, **how it relates
to the speaker's visual history** (continuation vs. departure), and a **sample prompt
excerpt** showing a specific slide from THIS talk rendered in the style.

```
ILLUSTRATION STYLE OPTIONS for "{talk title}"
=========================================================

A. [STYLE NAME]
   CONCEPT FIT: [Why this style reinforces the talk's thesis,
   metaphors, and narrative arc — not just what it looks like]

   VAULT CONTEXT: [How this relates to the speaker's visual
   history — continuation of default, intentional departure,
   or precedent from similar talk types]

   Sample prompt (Slide N — [slide title]):
   "[Complete prompt showing this specific slide rendered
   in the proposed style]"

B. [STYLE NAME]
   CONCEPT FIT: [...]
   VAULT CONTEXT: [...]
   Sample prompt (Slide N — [slide title]):
   "[...]"

C. [STYLE NAME]
   ...

RECOMMENDATION: [Which option and why — grounded in concept
fit and vault context, not just aesthetic preference]
=========================================================
```

The key: **each style option explains WHY it fits this specific talk's concepts**,
not just what it looks like. The author picks one (or mixes elements), then they
iterate on the anchor paragraph together.

#### Step 2: Define format vocabulary & aspect ratios

Once the style is chosen, define the slide format types for this talk:

```
SLIDE FORMAT VOCABULARY
========================
FULL     — full-bleed illustration, 1-2 sentences overlaid
           → Landscape 16:9 (1920×1080)
IMG+TXT  — illustration ~60% of slide, text beside/below
           → Portrait 2:3 (1024×1536)
EXCEPTION — real photo, data table, bio, or primary source
           → No generated illustration; uses [IMAGE NN] placeholder
========================
```

Format names and ratios are talk-specific — the author may use different names or
add formats (e.g., DIAGRAM for technical slides, QUOTE for attributed quotations).

#### Step 3: Choose image generation model

Agree on the target model (affects prompt style and capabilities):
- Model name and API (e.g., `gemini-3-pro-image-preview`, `dall-e-3`, `flux`)
- Any model-specific prompt conventions to bake into the style anchor
- Use `generate-illustrations.py --compare N` to generate the same prompt across
  multiple models for visual comparison (see [phase5-slides.md](phase5-slides.md)
  Image Generation Setup)

#### Step 4: Visual continuity devices

Define recurring elements that tie the deck together as a coherent visual artifact:
- **Sequential numbering** (e.g., "FIG. N" numbering) — ties the deck together as one
  coherent document. The generation model may render numbers imperfectly; that's acceptable
- **Recurring characters/motifs** in consistent style (same uniforms, same species,
  same rendering approach across all appearances)
- **Checklist progression** — a shared base image that gets edited to add checkmarks,
  fill-ins, or stamps across the talk. Use image editing (not regeneration) to preserve
  visual consistency. Track which slide is the base image
- **Progressive visual elements** with explicit base-image tracking: document which
  slide is the "source" image for each progression, so edits chain correctly
- **Annotation style** (callout labels, footnotes, stamps) — keep labels funny/deadpan
  if that's the tone; the gags in labels ARE the point

**Gate:** Author approves the style anchor paragraphs, format vocabulary, and model
choice. These become the Illustration Style Anchor section in the outline header.

### Slide Budget Calculation

Read `guardrail_sources.slide_budgets[]` from the speaker profile. Match the spec's
duration to the closest budget entry. Read `pacing` for WPM and slides/min targets.
