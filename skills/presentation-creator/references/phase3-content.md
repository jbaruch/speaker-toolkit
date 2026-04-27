# Phase 3: Content Development — Detail

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
- Visual: [shownotes URL composed from profile `publishing_process.shownotes.url.base` + `url.template` with the Presentation Spec slug] with QR code
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

#### Build specifications (progressive reveals)

When a slide needs progressive-reveal builds, add a Builds section after the Image
prompt field:

```markdown
### Slide 5: The Five Pillars
- Format: **FULL**
- Illustration: Five pillars of AI governance, labeled
- Image prompt: `[STYLE ANCHOR]. Five classical pillars...`
- Builds: 5 steps
  - build-00: Empty frame — title and borders only, no pillars
  - build-01: First pillar only (Transparency)
  - build-02: Add second pillar (Accountability)
  - build-03: Add third pillar (Fairness)
  - build-04: Add fourth pillar (Safety)
  - build-05: [FULL] — all five pillars (= slide-05.jpg)
```

Key conventions:
- `build-00` is always the empty frame (title/borders only, no content)
- The final build step is tagged `[FULL]` — it's a copy of the full slide image
- Build descriptions are edit instructions for the image model (they describe what to
  show at that step, working backwards from the full image)
- Build slides count toward the slide budget (they are separate slides, not animations)

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
