# Phase 3: Content Development — Detail

`outline.yaml` is the source of truth for the talk's content. The schema is
defined in `scripts/outline_schema.py` (pydantic v2 model); validate any draft
with `python3 skills/presentation-creator/scripts/outline_schema.py outline.yaml`. The four derived
artifacts (`narrative.md`, `script.md`, `slides.md`, `rhetorical-review.md`)
regenerate deterministically — never hand-edit them.

A complete worked example lives at `tests/fixtures/outline-example.yaml`.

## Writing the Outline

The outline needs to be:

1. **Structurally complete** — every chapter, every slide, every transition, every interaction cue
2. **Voice-authentic** — `script:` items in the speaker's actual voice (multi-speaker talks attribute every line)
3. **Visually directional** — `visual:` / `text_overlay:` / `image_prompt:` rich enough to build slides from
4. **Flexible** — `cuttable: true` on chapters or slides that drop for short slots

## The `talk:` block

Authored in Phase 1; never re-edited carelessly. Field reference (see
`outline_schema.py:TalkMetadata` for the authoritative list):

| Field | Required | Notes |
|-------|----------|-------|
| `title` | yes | Talk title — appears in extracted artifact headers |
| `slug` | yes | Kebab-case (`venue-year-topic`) — names the deck file and shownotes path |
| `speakers` | yes | List of speaker names; multi-speaker talks force `speaker:` on every script line |
| `duration_min` | yes | Slot length in minutes |
| `audience`, `mode`, `venue` | yes | Short prose |
| `slide_budget` | yes | Integer; expanded build count is validated against this |
| `pacing_wpm` | yes | `[low, high]` integer tuple |
| `architecture` | yes | One of: `narrative-arc`, `sparkline`, `fourthought`, `triad`, `talklet`, `expansion-joints`, `lightning-talk`, `takahashi`, `cave-painting` |
| `applied_patterns` | optional | Talk-level patterns (e.g., `bookends`, `mentor`, `anti-sell`) |
| `thesis` | optional | Elaborated paragraph; the slide-ready single sentence lives on the call-to-adventure slide via `big_idea_text` |
| `shownotes_url_base` | optional | e.g., `https://speaking.example.com/` — used by Phase 6 |
| `commercial_intent`, `profanity_register` | optional | Free prose |
| `must_include`, `must_avoid` | optional | Lists of strings |
| `catalog_reference` | optional | Pointer to sessions-catalog entry |
| `delivery_count`, `delivery_date` | optional | First delivery = 1; date in ISO YYYY-MM-DD |

## The `chapters:` block

Authored in Phase 2; section-level scaffolding for `narrative.md`. Each chapter:

```yaml
- id: ch1                   # stable kebab id, referenced by slides[].chapter
  title: "Cold Open"
  target_min: 6             # rough time allocation; sum is checked against duration
  accent: red               # optional — visual theme tag (e.g., color code per section)
  cuttable: false           # set true on sections that drop for short slots
  argument_beats:
    - text: "Beat as a paragraph. Slide refs natural in the prose."
      slide_refs: [1, 2]    # validated against slides[].n at load time
      tags: [hook]          # free-form authoring tags
```

`argument_beats[].text` is the *prose argument* — what `narrative.md` will
render. Keep it dense and one-paragraph per beat. The `slide_refs` field is a
structured cross-reference: the schema validator rejects any ref that doesn't
match a real slide number in `slides[]`, and `narrative.md` renders each beat
with a `*[slide N, slide M]*` marker so readers can trace beats back to the
deck. Slide numbers also tend to appear inline in the prose naturally.

## The `slides:` and `interludes:` blocks

Slides are the deck-facing units; interludes are between-slide events
(live demos, terminal switches) anchored by `after_slide:`.

### Slide field reference

```yaml
- n: 17                     # slide number; unique and ascending; n=0 allowed for title cards
  chapter: ch3              # must reference a valid chapter id
  title: "Five Pillars"
  format: FULL              # FULL | IMG+TXT | EXCEPTION | TITLE | DEMO
  format_justification: ""  # required when format == EXCEPTION
  cuttable: false
  visual: "Five classical pillars, labeled."
  text_overlay: "Five pillars. Most teams have one."   # what's literally on screen; "none" for image-only
  image_prompt: |           # only when style_anchor is set + format != EXCEPTION
    [STYLE ANCHOR]. Five classical pillars, all labeled, soft morning light.
  builds:                   # progressive reveals; each step expands to one deck slide
    - { step: 0, desc: "Empty frame" }
    - { step: 1, desc: "First pillar reveal" }
  script:                   # screenplay form — see Script section below
    - cue: "SLIDE 17 UP"
    - parenthetical: "(beat)"
    - line: "Five pillars. Most teams have one."        # single-speaker
    - { speaker: "Patrick", line: "..." }               # multi-speaker
  applied_patterns:
    - { id: star-moment, subtype: shocking-statistic }
  callbacks:
    - { kind: plant, id: receipt-motif }
    - { kind: pay,   id: same-model-same-task, variation: "Same model. Same question." }
  progressive_lists:
    - { id: cheat-sheet, item_index: 2 }
  running_gags:
    - { id: mod-7, appearance_index: 3 }
  placeholders: ["AUTHOR-04", "DATA-02"]
  big_idea: true            # exactly ONE slide in the talk has this true
  thesis: preview           # "preview" or "payoff" — preview must come before payoff
```

### Interlude field reference

```yaml
- id: demo-04
  after_slide: 13           # plays between slide 13 and slide 14
  chapter: ch-wrong-tool
  title: "DEMO 04 — The Wrong Tool (RIGHT)"
  cuttable: false
  script: [...]             # same shape as slide.script
  callbacks: [...]
  applied_patterns: [...]
```

Interludes have no `n`, no `visual`, no `image_prompt` — they're production
events. They appear in `script.md` (rehearsal), not in `slides.md` (deck build).

## The `style_anchor:` block (optional)

Only present when Phase 2 produced an illustration strategy. Talks without
this block use `visual:` + `text_overlay:` only; `image_prompt:` is omitted.

```yaml
style_anchor:
  model: "imagen-4"
  full: |
    Full-bleed style anchor paragraph — describes the FULL (1920×1080) format.
  imgtxt: |
    IMG+TXT style anchor paragraph — describes the portrait (1024×1536) format.
  conventions: |
    Visual continuity rules (numbering scheme, recurring motifs, annotation style).
```

The `[STYLE ANCHOR]` token in each slide's `image_prompt` is replaced by the
illustrations pipeline with the format-appropriate anchor text at generation
time. Slides with no illustration (text-only or EXCEPTION) omit `image_prompt`.

## Script (`script:` items)

A slide's or interlude's `script:` is a flat list of three item shapes; exactly
one of `{cue, parenthetical, line}` is set on each:

| Item shape | Meaning | Speaker attribution |
|------------|---------|---------------------|
| `{ cue: "..." }` | Production direction (slide change, terminal up, build advance) | Never — cues are scene-level |
| `{ parenthetical: "(beat)" }` | Delivery direction (pause, tone, gesture, audience interaction) | Optional in multi-speaker mode; forbidden in single-speaker mode |
| `{ line: "..." }` | Spoken dialogue | Required in multi-speaker; forbidden in single-speaker |
| `{ speaker: "Name", parenthetical: "(to Baruch)" }` | Speaker-attributed stage direction | Common in screenplay form |
| `{ speaker: "Name", line: "..." }` | Multi-speaker dialogue line | The speaker must be in `talk.speakers` |

Consecutive items with the same `speaker:` group as one block in `script.md`.
Floating parentheticals (no speaker) describe the room ("many hands go up");
attributed parentheticals describe a specific speaker's action.

## Pattern Application — Closed Taxonomy

Patterns are declared via `applied_patterns:` on slides, interludes, or the
talk itself. Pattern IDs come from the closed enum discovered at runtime from
`references/patterns/{prepare,build,deliver}/*.md` (77 patterns / 25
antipatterns matching the index). Antipatterns are never declared in
`outline.yaml` — they surface as detections in `rhetorical-review.md`.

### Opening PUNCH (slide-level)

```yaml
applied_patterns:
  - id: opening-punch
    flavors: [personal, unexpected, challenging]   # ≥1 from: personal, unexpected, novel, challenging, humorous
```

Strong openings stack 2–3 PUNCH flavors. The first ~10% of the deck must
declare `opening-punch` with at least one flavor or the rhetorical-review
flags a missing-hook gap.

### Big Idea + Thesis (slide-level)

```yaml
- n: 17
  big_idea: true                    # exactly one slide in the talk has this
  thesis: preview                   # this slide previews the thesis; a later slide pays it off
  applied_patterns:
    - id: call-to-adventure
      big_idea_text: "Treat context as an engineering artifact."
```

The single-sentence form lives on `big_idea_text:`. The elaborated thesis
lives on `talk.thesis`. Preview must come before payoff.

### Sparkline Structural Elements (when architecture is `sparkline`)

```yaml
# Call to Adventure — turning point 1, 10–25% into the talk
applied_patterns:
  - { id: call-to-adventure, big_idea_text: "..." }

# Call to Action — turning point 2, last 15–25%
applied_patterns:
  - id: call-to-action
    asks:
      doer: "specific immediately-executable ask"
      supplier: "..."
      influencer: "..."
      innovator: "..."

# New Bliss — immediately after Call to Action
applied_patterns:
  - { id: new-bliss }

# S.T.A.R. moments — at peaks in the persuasive middle (≥1 required for sparkline)
applied_patterns:
  - { id: star-moment, subtype: shocking-statistic }
  # subtype values: memorable-dramatization | repeatable-sound-bite | evocative-visual
  #                 | emotive-storytelling | shocking-statistic
```

### Master Story (talks 30+ min)

```yaml
# First telling
- n: 8
  applied_patterns:
    - { id: master-story, story_id: pandy, beat: introduce }

# Subsequent recalls — each beat: recall-1, recall-2, recall-3
- n: 22
  applied_patterns:
    - { id: master-story, story_id: pandy, beat: recall-1 }
```

`introduce` must be the first beat for any `story_id`; recalls are ordered.

### Inoculation Beats (persuasive talks; ≤3 per talk)

```yaml
applied_patterns:
  - id: inoculation
    resistance_vector: politics         # one of: comfort-zone | fear | vulnerabilities
                                        # | misunderstanding | obstacles | politics
```

Reserve for objections that would derail the room. The rhetorical-review
flags >3 inoculations as a defensive-feeling talk.

### Callbacks (slide-level ledger)

```yaml
# Plant a callback
callbacks:
  - { kind: plant, id: receipt-motif }

# Pay it off later
callbacks:
  - { kind: pay, id: receipt-motif, variation: "Revealed in full" }
```

Every plant must have at least one pay; every pay must reference a planted id.
The schema rejects unpaired ledger entries before the rhetorical-review even
runs.

### Progressive Lists & Running Gags

```yaml
# A list that grows across slides
progressive_lists:
  - { id: cheat-sheet, item_index: 1 }   # later slides increment item_index

# A gag that escalates across appearances
running_gags:
  - { id: mod-7, appearance_index: 1 }
```

Indexes must be contiguous starting at 1. Running gags need ≥2 appearances
(otherwise it's a one-shot meme, not a gag).

### Talk-level patterns

`applied_patterns:` on the talk itself for patterns that span the whole talk
(`bookends`, `mentor`, `anti-sell`, `delayed-self-introduction`,
`unifying-visual-theme`, `master-story`, `meme-as-argument`,
`a-la-carte-content`, `greek-chorus`, `live-demo`, etc.). These don't carry
slide-level instance metadata.

## Builds (Progressive Reveals)

When a slide needs progressive-reveal builds:

```yaml
- n: 5
  format: FULL
  visual: "Five pillars, labeled."
  image_prompt: |
    [STYLE ANCHOR]. Five classical pillars, all labeled.
  builds:
    - { step: 0, desc: "Empty frame — title and borders only, no pillars" }
    - { step: 1, desc: "First pillar (Transparency)" }
    - { step: 2, desc: "Add second pillar (Accountability)" }
    - { step: 3, desc: "Add third pillar (Fairness)" }
    - { step: 4, desc: "Add fourth pillar (Safety)" }
    - { step: 5, desc: "All five pillars" }
```

Conventions:

- `step: 0` is the empty frame (title/borders only, no content)
- The final step matches the full slide image
- Build descriptions are edit instructions for the image model (what to show at that step)
- Each build counts toward `slide_budget` (the validator expands `max(len(builds), 1)`)
- Script cues mid-slide reference the build steps: `cue: "BUILD 01"`

## Voice Calibration

Read verbal signatures from the vault summary (recurring phrases section) and
the profile's `instrument_catalog.verbal_signatures[]`. Place them where they
fit organically in `script:` items — don't force them.

General placement principles:

- **Confirmation tags** — after explaining something, not every sentence
- **Transition fillers** — into the next point, sparingly
- **Bold claim framers** — before provocative statements, max once per talk
- **Dismissal phrases** — when rejecting a concept the audience might believe in
- **Profanity** — only in the speaker's natural rhythm, calibrated to `profanity_register`
- **Self-deprecating humor** — most effective in openings and transitions
- **Bullet symbols** — read default from `design_rules.default_bullet_symbol`

The specific phrases come from the vault, not from this file.

## Opening PUNCH — framework reminder

The first 1–2 minutes of the talk are the highest-stakes real estate. Audiences
grant a roughly two-minute "honeymoon period" before forming a verdict on whether
the talk is worth their attention. The opening section must contain at least one
of five hook flavors, per Reynolds's PUNCH framework:

- **P**ersonal — a relevant story (not a credentials parade)
- **U**nexpected — a counterintuitive fact, surprising statistic, or claim that violates received wisdom
- **N**ovel — fresh data, never-published image, or working demo of something new
- **C**hallenging — a provocative question or assumption-reframing
- **H**umorous — observational humor, a wry aside, or anecdote with a relevant payoff (not a joke)

Strong openings stack 2–3 PUNCH elements. Tag every opening slide that contains
a flavor (see `applied_patterns` example above). If the opening contains none of
the PUNCH flavors — agenda slide, "let me introduce myself," "thanks for having me"
filler — the rhetorical-review will flag it.

See `patterns/prepare/opening-punch.md` for the full pattern.

## Contrast as a Structural Device

Reynolds: "Contrast is about differences, and we are hardwired to notice
differences." When choosing how to frame a chapter or transition, look for the
inherent contrast pair:

- before / after
- past / future
- problem / solution
- received wisdom / actual finding
- naive expectation / messy reality
- competitor approach / your approach
- pessimism / optimism
- decline / growth

Contrast structures naturally produce dramatic tension and make the resolution
feel earned. If a chapter feels flat, ask: *what is the contrast pair here?*
If you can't name one, the chapter is not yet sharpened. (Contrast is rhetorical
guidance, not a tagged pattern — it shapes how you write `argument_beats[].text`.)

## Placeholder Types

Every placeholder requiring author input MUST use a typed tag — never
generic `TODO` or `TBD`. Independent numbering per type (each starts at 01):

| Tag | Use |
|-----|-----|
| `AUTHOR-NN` | Speaker's specific data or story for this point |
| `DEMO-NN` | Description of what to demo |
| `DATA-NN` | Survey stat needed — describe what's needed |
| `SCREENSHOT-NN` | Description of what to capture (no illustration strategy) |
| `IMAGE-NN` | Real photo/screenshot/data viz needed (for EXCEPTION slides) |
| `MEME-NN` | Meme placeholder — see brief format below |

`IMAGE-NN` replaces `SCREENSHOT-NN` in illustration-aware outlines. `SCREENSHOT-NN`
still works for talks without an illustration strategy.

Placeholders go in the slide's `placeholders:` list. For memes, include a
structured brief in the surrounding context (free prose in `visual:` or a
separate notes block):

```
MEME-01
Template: [meme template name]
Search query: "[search terms to find the template image]"
Overlay text: [specific text to apply]
Rhetorical function: [what argument this meme serves]
```
