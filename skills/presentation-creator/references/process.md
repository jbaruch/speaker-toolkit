# Presentation Creator — Process Reference

Detailed workflow for each phase. The SKILL.md has the overview; this file has the
operational detail.

## Phase 0: Intake & Context Loading — Detail

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

### Step 0.3: Report and Advance

Summarize what you know and what you need.

## Phase 1: Intent Distillation — Detail

### The Art of Asking

Don't dump all questions at once. Use `AskUserQuestion` for structured choices when
the vault provides a finite set of options, and conversational questions when the
answer is open-ended.

**Batch questions logically:**
1. First batch: Purpose & thesis (the "what" and "why")
2. Second batch: Audience & venue specifics (the "who" and "where")
3. Third batch: Constraints & preferences (the "how" and "how not")

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

## Phase 2: Rhetorical Architecture — Detail

### The Joint Selection Process

This phase is a conversation, not a monologue. For each decision:

1. **Extract the options** from the vault summary (sections 2-13) and speaker profile
   (`instrument_catalog`). The vault is the living source — new instruments appear
   as more talks are parsed.
2. **Present the options** to the author with brief descriptions
3. **Recommend** based on the spec (with reasoning)
4. **Let the author choose** — they may want something the vault doesn't recommend

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

### Decision #10: Pattern Strategy

Read `references/patterns/_index.md` for the full taxonomy and
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
  multiple models for visual comparison (see Image Generation Setup below)

#### Step 4: Visual continuity devices

Define recurring elements that tie the deck together as a coherent visual artifact:
- Numbering scheme (e.g., "FIG. N" sequential numbering)
- Recurring characters or motifs across slides
- Progressive visual elements (e.g., a form that fills in across the talk)
- Annotation style (callout labels, footnotes, stamps)

**Gate:** Author approves the style anchor paragraphs, format vocabulary, and model
choice. These become the Illustration Style Anchor section in the outline header.

### Slide Budget Calculation

Read `guardrail_sources.slide_budgets[]` from the speaker profile. Match the spec's
duration to the closest budget entry. Read `pacing` for WPM and slides/min targets.

## Phase 3: Content Development — Detail

### Writing the Outline

The outline needs to be:
1. **Structurally complete** — every section, every transition, every interaction cue
2. **Voice-authentic** — speaker notes in the speaker's actual voice
3. **Visually directional** — enough detail for the author to build slides from
4. **Flexible** — marked sections that can be cut for shorter slots or expanded

### Outline Format

```markdown
# [Talk Title]

**Spec:** [mode] | [duration] | [venue] | [audience]
**Slide budget:** [N slides — from profile guardrail_sources.slide_budgets]
**Pacing target:** [from profile pacing.wpm_range]

---
```

#### Illustration Style Anchor (when illustration strategy is defined)

If Phase 2 produced an illustration strategy, add the style anchor section after
the spec/budget/pacing header:

```markdown
## Illustration Style Anchor

All generated illustrations use the **[style name]** style. Prefix every image
prompt with the appropriate anchor below.

**Model:** `[model-name]`

### STYLE ANCHOR (FULL — Landscape 1920×1080)
> [style anchor paragraph for full-bleed illustrations]

### STYLE ANCHOR (IMG+TXT — Portrait 1024×1536)
> [style anchor paragraph for image-with-text illustrations]

### Conventions
[Visual continuity rules: numbering scheme, recurring motifs,
progressive elements, annotation style — from Phase 2 Step 4]

---
```

The format names and dimensions come from the format vocabulary defined in Phase 2.
Talks without an illustration strategy omit this entire section.

#### Standard outline body

```markdown
## Opening Sequence [3 min, slides 1-5]

### Slide 1: Title Slide
- Visual: [description]
- Footer: [from profile design_rules.footer.pattern]
- Speaker: [no notes — title slide is visual-only]

### Slide 2: [Opening hook type — from Phase 2 architecture]
- Visual: [description]
- Speaker: "[opening lines in the speaker's voice]"

### Slide 3: Brief Bio
- Visual: [from profile speaker.bio_short]
- Speaker: "[brief intro]"

### Slide 4: Shownotes URL
- Visual: [from profile speaker.shownotes_url_pattern] with QR code
- Speaker: "Everything — slides, links, resources — [shownotes URL]"

### Slide 5: [First content beat]
...

## Act 1: [Title] [N min, slides X-Y]
...

## [CUT LINE: Everything below here can be dropped for short version]
...

## Closing Sequence [3 min, slides N-end]

### Slide N: Summary
### Slide N+1: CTA
### Slide N+2: Thanks / Social
```

#### Per-slide illustration fields (when illustration strategy is defined)

When the outline has an Illustration Style Anchor, each slide gains additional fields:

```markdown
### Slide N: [Title]
- Format: **FULL** | **IMG+TXT** | **EXCEPTION** — [justification if EXCEPTION]
- Illustration: [human-readable description of the visual concept]
- Text overlay: [text that goes on top of the illustration, or "none"]
- Image prompt: `[STYLE ANCHOR]. [complete prompt for the image generation model]`
- Visual: [description — for non-illustrated elements like footer, layout notes]
- Speaker: [notes]
```

Key rules:
- **Format** is required for every slide — forces the author to think about visual weight
- **EXCEPTION** slides must include a justification (why a real asset instead of generated)
- **Image prompt** uses `[STYLE ANCHOR]` as a token referencing the header — the
  generation script replaces it with the full anchor text for the matching format
- **Illustration** is the human-readable intent; **Image prompt** is the machine-readable
  generation input
- Slides with no illustration (text-only, EXCEPTION with real asset) omit the Image
  prompt field
- Talks without an illustration strategy use the standard `- Visual:` field only

### Callback Identification

Proactively identify and suggest callback opportunities. Check the vault summary for
whether the speaker uses within-talk callbacks as a structural device. Look for:

- **Recurring memes** — call back later with a twist
- **Progressive lists** — add items on later appearances
- **Running gags** — escalate across 2-3 callbacks
- **Deferred payoff** — plant early, resolve later

Flag every callback explicitly in the outline:
```
[CALLBACK: reference to {element} from slide {N} — {variation}]
[PROGRESSIVE LIST: {list name} gains Nth item from slide {N}]
[RUNNING GAG: Nth appearance of {gag}]
```

### Voice Calibration

Read verbal signatures from the vault summary (recurring phrases section) and the
profile's `instrument_catalog.verbal_signatures[]`. Place them where they fit
organically — don't force them.

General placement principles:
- **Confirmation tags** — after explaining something, not every sentence
- **Transition fillers** — into the next point, sparingly
- **Bold claim framers** — before provocative statements, max once per talk
- **Dismissal phrases** — when rejecting a concept the audience might believe in
- **Profanity** — only in the speaker's natural rhythm, calibrated to the spec's register
- **Self-deprecating humor** — most effective in openings and transitions
- **Bullet symbols** — read default from `design_rules.default_bullet_symbol` in the
  profile, but proactively suggest contextual symbols where they fit

The specific phrases come from the vault, not from this file.

### Placeholder Types

Use numbered, typed placeholders:

```
[AUTHOR 01: your specific data/story for this point]
[DEMO 01: description of what to demo]
[DATA 01: need survey stat — describe what's needed]
[SCREENSHOT 01: description of what to capture]
[IMAGE 01: description — what real asset is needed]
```

`[IMAGE NN]` is for EXCEPTION slides that need real photos, screenshots, or data
visualizations instead of generated illustrations. This replaces `[SCREENSHOT NN]`
in illustration-aware outlines. `[SCREENSHOT NN]` still works for talks without
an illustration strategy.

**Meme briefs** — structured brief for each meme:

```
[MEME 01]
Template: [meme template name]
Search query: "[search terms to find the template image]"
Overlay text: [specific text to apply]
Rhetorical function: [what argument this meme serves]
```

Each type uses independent numbering.

## Phase 4: Revision & Guardrails — Detail

### Guardrail Check Procedure

After each revision, run through `references/guardrails.md` systematically with
thresholds from the speaker profile. Present results as a checklist:

```
GUARDRAIL CHECK
===============
[PASS/FAIL] Slide budget: {actual}/{max from profile} for {duration}-min slot
[PASS/WARN/FAIL] Act 1 ratio: {%} (limit from profile)
[PASS/FAIL] Branding: footer elements from profile
[PASS/FAIL] Profanity: register from spec, on-slide rules from profile
[PASS/FAIL] Data attribution: sources visible
[PASS/FAIL] Time-sensitive: no expired content
[PASS/FAIL] Closing: summary + CTA + social present
[PASS/FAIL] Cut lines: present for adaptation
[INFO] Anti-patterns: checks from profile recurring_issues
```

### Iteration Protocol

- Apply the author's changes first, guardrail check second
- If a guardrail fails after the author's change, flag but don't block
- Track intentionally overridden vs accidentally missed guardrails
- **Keep file versions:** Before major revisions, create a timestamped copy
- The current/active outline is always `presentation-outline.md`

## Phase 5: Slide Generation & Interactive Iteration — Detail

Full technical reference: `references/slide-generation.md`

### Step 5.1: Create the Deck

Read the template path from `speaker-profile.json → infrastructure.template_pptx_path`.
Strip demo slides from template, keep layouts only (see slide-generation.md for code).
Save to the presentation file convention from the profile.

### Step 5.1b: Generate Illustrations (when illustration strategy is defined)

If the outline includes an Illustration Style Anchor section:

1. Run `generate-illustrations.py <outline.md> remaining` to batch-generate all
   missing illustrations
2. Review generated images with the author — delete and regenerate as needed
3. Once all images are approved, proceed to slide population

Images are stored in `illustrations/` alongside the outline file. See
**Image Generation Setup** below for prerequisites.

### Step 5.2: Walk the Outline

For each slide, select the layout from the profile's `infrastructure.template_layouts[]`,
add via MCP, populate placeholders. See slide-generation.md for the workflow
(including illustration-format-aware insertion for FULL, IMG+TXT, and EXCEPTION slides).

### Step 5.3: Inject Speaker Notes

Batch-inject via python-pptx (MCP doesn't support notes). Key slides only — not every slide.

### Step 5.4: Present to Author

Save and present a generation report with slide count, layouts used, and placeholders
needing author content.

### Step 5.5: Iteration Loop

Free-form conversation. The author gives feedback in whatever format is natural.
Handle content changes (MCP), structural changes (python-pptx), and note changes
(python-pptx). See slide-generation.md for patterns.

### Step 5.6: Final Save

Save the .pptx. Export and publishing happen in Phase 6.

### Image Generation Setup

Before generating illustrations, ensure:

1. **API Key** — set the `GEMINI_API_KEY` environment variable:
   ```bash
   export GEMINI_API_KEY="your-key-here"
   ```
   Get a key from https://aistudio.google.com/app/apikey

2. **Model availability** — verify the model specified in the outline header
   is accessible with your key. The script reads the model name from the
   `**Model:** \`model-name\`` line in the Illustration Style Anchor section.

3. **Python 3** — the script uses only stdlib (`urllib`, `json`, `base64`).
   No pip install needed.

4. **Run the script:**
   ```bash
   python3 generate-illustrations.py presentation-outline.md remaining
   ```
   Options: `all`, `remaining`, or specific slide numbers (`2 5 9`, `2-10`)

5. **Model comparison** (during Phase 2 model selection):
   ```bash
   python3 generate-illustrations.py presentation-outline.md --compare 2
   ```
   Generates the same prompt across multiple Gemini image models for visual
   comparison. Results go to `illustrations/model-comparison/`.

6. **Review & iterate** — check generated images in the `illustrations/`
   directory. Delete any that need regeneration and re-run with `remaining`.

## Phase 6: Publishing — Detail

The publishing workflow is speaker-specific. Read `publishing_process` from
`speaker-profile.json`. If the section is missing or empty, fall back to asking
the author interactively and document their answers for next time.

### Step 6.1: Export

Read `publishing_process.export_format` and `publishing_process.export_method`.

- If `export_script` is provided, run it (substituting the deck path)
- If `export_method` is a description, follow its instructions
- Common pattern: PowerPoint AppleScript for PDF (see `references/slide-generation.md`)
- If no export info, ask: "How do you want to export? PDF, keep .pptx only, or both?"

### Step 6.2: Shownotes

Read `publishing_process.shownotes_publishing`. If `enabled`:

- Follow the `method` description (git push, CMS, manual)
- If `shownotes_repo_path` and `shownotes_template` are provided, generate the page
- Include: title, abstract, slide embed/download link, resource links, speaker bio
- Use the `shownotes_url_pattern` from `speaker` to construct the final URL

If not enabled, skip.

### Step 6.3: QR Code

Read `publishing_process.qr_code`. If `enabled`:

- Generate QR code pointing to the shownotes URL (or `target` URL)
- If `insert_into_deck` is true, add to the deck at the specified `slide_position`
- Re-save the deck after insertion

### Step 6.4: Additional Steps

Read `publishing_process.additional_steps[]`. For each entry:

- If `automated` is true and `script` is provided, run it
- If `automated` is false, present the step to the author as a manual TODO
- Report completion status for each step

### Step 6.5: Go-Live Preparation Checklist

Before delivery, surface unobservable patterns from `references/patterns/_index.md`
(the "Unobservable Patterns — Go-Live Checklist" section) as a preparation reminder.
These are patterns the vault **cannot score retroactively** because they involve
pre-event logistics, physical stage behaviors, or external systems — but they still
matter for delivery quality.

```
GO-LIVE CHECKLIST — {talk title}
==================================
PRE-EVENT:
[ ] Preparation — backups, cables, hydration, room layout check
[ ] Carnegie Hall — completed 4 rehearsals (pace, delivery, fixes, groove)
[ ] The Stakeout — staging area identified near venue
[ ] Posse — supporter(s) confirmed for front row
[ ] Seeding Satisfaction — plan to arrive early and mingle
[ ] Shoeless — comfort ritual ready

DURING DELIVERY:
[ ] Lightsaber — if laser pointer needed, max 2-3 steady moments
[ ] Red/Yellow/Green — exit feedback cards set up (if venue supports)

AVOID:
[ ] Laser Weapons — don't wave the pointer; use built-in highlights
[ ] Bunker — step out from behind the podium
[ ] Backchannel — don't monitor social media during the talk
==================================
```

### Step 6.6: Publishing Report

```
PUBLISHING REPORT — {talk title}
==================================
[DONE/SKIP] Export: {format} → {output path}
[DONE/SKIP] Shownotes: {url or "not configured"}
[DONE/SKIP] QR code: {inserted at slide N or "not configured"}
[DONE/SKIP/TODO] {additional step name}: {status}
[INFO] Go-live checklist: {presented above}
==================================
```
