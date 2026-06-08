# Speaker Toolkit

[![tessl](https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.tessl.io%2Fv1%2Fbadges%2Fjbaruch%2Fspeaker-toolkit)](https://tessl.io/registry/jbaruch/speaker-toolkit)

A six-skill presentation system for conference speakers: analyze your existing talks to extract your rhetoric patterns, create new presentations that match your documented style, produce the deck illustrations + thumbnail visual layer, and publish talk pages to a Jekyll shownotes site.

## What's New (Unreleased)

**Progressive-reveal build expansion** — the toolkit now assembles generated
build frames into the deck: a new `ExpandBuilds` PowerPoint pass replaces each
progressive-reveal parent slide with its frames as full-bleed slides (notes on
the final frame), so a build sequence becomes the sequential slides you advance
through. Pairs with poster-theatrical for pure full-bleed, builds-and-all decks.

**Poster-theatrical composition** — a style-wizard option where every slide is
full-bleed and the title + footer are rendered *into* the image (stylized,
blended), with only the QR code added afterward. No overlaid titles, no safe
zones — an "all art, no chrome" look. Chosen in the wizard and baked into the
STYLE ANCHOR header.

**Idea-sourcing wizard + render-before-bake gate** — illustration style strategy
is now an explicit multi-select wizard: pick where the visual ideas come from
(your usual, mode/series match, new, wild, what's trending, or bring your own),
with a Quick-default fast path that still renders and shows. The strategy steps
are individually gated, and a new `--check-style-explore` verdict plus a guard in
`generate-illustrations.py` refuse to generate from any model that wasn't rendered
in the exploration grid the speaker reviewed — you can no longer bake a model into
the STYLE ANCHOR by reasoning alone.

**Explicit engine & theme sourcing** — deck tooling (PowerPoint/pptx vs presenterm
terminal-markdown) is now a first-class Phase 2 decision sourced through the same
wizard, recorded on the outline (`talk.engine`) instead of inferred at build time.
A live-coding talk that should run in a terminal tool no longer silently becomes a
slide deck.

**Structured style selection + model registry** — Phase 2 style strategy now
runs as an ordered process: elicit what the speaker optimizes for (cost, speed,
quality, build-editability), narrow the model roster to a priority-driven
shortlist with `model_registry.py --shortlist`, propose styles, then render a
`style × model × format` grid into a structured `style-explore/` directory with
an `index.md` contact sheet (`generate-illustrations.py --style-explore`) for a
visual pick. The model roster moved into a single source of truth,
`model_registry.py` — a structured registry with vendor aliases (so "nano-banana"
resolves to the canonical Gemini id instead of being dropped on refresh),
per-model attributes, and a deterministic `--check-freshness` precheck that
SKILL.md Step 2 now runs first and reports, closing the "freshness check never
ran" gap. The roster is a seed cache, not an allowlist: rendering accepts any id
from a supported vendor family, and a web-discovered model can be injected into
the shortlist for one talk via `--add` without a code edit.

## What's New (0.18.0)

**Cross-vendor image generation + model-freshness check** — `generate-illustrations.py`
now dispatches by model-name prefix to three vendor families: Google's
`gemini-*` / `nano-banana-*` (`generateContent`), Google's `imagen-*` (`:predict`),
and OpenAI's `gpt-image-*` (`/images/generations` and multipart `/images/edits`).
`COMPARE_MODELS` refreshed to current flagships including `gpt-image-2`,
`imagen-4.0-ultra-generate-001`, `gemini-3.1-flash-image-preview`, and
`nano-banana-pro-preview`. New SKILL.md Step 2 web-searches the model
landscape before any image generation runs and proposes re-running
`--compare` if a newer flagship has shipped since the outline's `**Model:**`
was last set — closes the months-long gap between picking a model in
Phase 2 and actually generating images in Phase 5.

**Talk timer for timemytalk.app** — New `generate-talk-timings.py` parses the
outline's pacing summary into `MM:SS Chapter` format for the timemytalk.app
delivery timer. Supports `--qa` flag, sub-minute resolution, and automatic
subdivision of long acts. Phase 6 publishing docs updated.

**Keynote compatibility rules** — Slide generation rules now document three
python-pptx gotchas that cause Keynote to reject generated `.pptx` files: use
rectangles not connectors for decorative lines, avoid create-then-remove shape
patterns, keep shape IDs contiguous.

**Shownotes publishing destination** — Agents can now resolve published shownotes
from `publishing_process.shownotes_site` in the speaker profile instead of
searching the web. Resources-gathering rules document the read path.
Fixed eval scenarios 12 and 13 with deterministic test data.

**Test suite and CI** — 119 pytest tests across 15 files cover every script, running
on every push and PR via GitHub Actions with ffmpeg and LibreOffice.

See [CHANGELOG.md](CHANGELOG.md) for full history.

## How It Works

The toolkit is built on six skills connected by a shared **rhetoric vault** — a directory of structured knowledge about how you present.

```
                   VAULT
                 (shared data)
                 +-----------+
  Vault skills   | summary   |        Creator skills
  (analysis) --> | design    | <--  (generation)
                 | spec      |
                 | profile   |
                 +-----------+
```

**Vault skills (analysis):**
- **vault-ingress** parses your recorded talks (YouTube transcripts + slides from PPTX files or Google Drive PDFs) and extracts rhetoric patterns across 14 dimensions — opening hooks, humor style, audience interaction, slide design, pacing, transitions, verbal signatures, and more. It also scores each talk against the Presentation Patterns taxonomy.
- **vault-clarification** runs interactive sessions to validate findings and capture deliberate intent.
- **vault-profile** generates a structured speaker profile, including a pattern profile with mastery levels and signature combinations, after enough talks are analyzed.

**Creator skills (generation):**
- **presentation-creator** reads the vault at runtime and uses your documented patterns as a constitutional style guide to build new presentations. It follows a 7-phase process from intent distillation through slide generation, with a 4-tier Pattern Strategy for selecting presentation techniques, and a go-live checklist before delivery. Delegates the visual layer to the illustrations skill.
- **illustrations** owns the deck illustration strategy, generation, build chains, and YouTube thumbnails. Invoked by presentation-creator at the relevant phases (Phase 2 strategy, Phase 5 application, Phase 7 thumbnail).
- **shownotes-publisher** writes talk pages into a Jekyll-based shownotes site (e.g., `speaking.jbaru.ch`). Encodes the custom parser's format contract so authored content actually renders: abstract is one paragraph, video field absent = "coming soon" badge, slides/video URLs must be markdown links, no frontmatter title, etc. Invoked after the talk is delivered (or pre-talk for slides-only publish).

The vault skills never run simultaneously with the creator skills. You build the vault first (once, then incrementally), then use the creator whenever you need a new talk. The vault grows over time as you parse more talks, and the creator automatically picks up new patterns.

## Installation

```bash
tessl install jbaruch/speaker-toolkit
```

## Getting Started

### Phase 1: Build Your Vault

You need recorded talks with:
- YouTube videos (for transcripts)
- Slides in at least one of: `.pptx` source files (preferred — exact design data) or Google Drive PDF exports

Organize your talk metadata as `.md` shownotes files in a directory, each containing a video URL and optionally a slides URL or PPTX path (or both).

Then run:
```
parse my talks
```

The vault skill will:
1. Check `~/.claude/rhetoric-knowledge-vault/` (or ask for a custom location on first run)
2. Scan for talks and .pptx files
3. Process talks in parallel batches of 5
4. Extract rhetoric patterns across 14 dimensions
5. Score each talk against the 86 observable Presentation Patterns
6. Build a running narrative summary and slide design spec
7. Run an interactive clarification session to validate findings and capture your intent
8. Generate a structured speaker profile with pattern mastery data (after 10+ talks)

### Phase 2: Create Presentations

Once the vault exists, invoke the creator:
```
create a presentation about [topic] for [conference]
```

The creator will:
1. Load your vault (summary, design spec, profile) and the pattern taxonomy
2. Walk you through intent distillation (purpose, audience, constraints)
3. Jointly select rhetorical instruments, including a 4-tier Pattern Strategy
4. Write a section-by-section outline with speaker notes in your voice
5. Run guardrail checks (slide budget, Act 1 ratio, profanity, branding, pattern-based antipattern scan)
6. Generate a .pptx deck from your template
7. Execute your publishing workflow and present a go-live preparation checklist

Every phase requires your approval before proceeding. The skill brings the rhetoric knowledge; you bring the topic expertise.

## Architecture

### Speaker Neutrality

All skills are generic — they work for any speaker. All personalization lives in the vault:

| Component | What it defines |
|-----------|----------------|
| **Skills** (this tile) | Process: phases, gates, output formats, guardrail structure |
| **Vault** (your data) | Content: what instruments exist, what the speaker sounds like, thresholds to enforce |

The vault lives at `~/.claude/rhetoric-knowledge-vault/` by default. If you prefer a different location (e.g., Google Drive for backup), the skill creates a symlink from the canonical path to your chosen directory. If you don't have a vault yet, the skill creates it from scratch on first run.

### The Vault Directory

The vault lives at `~/.claude/rhetoric-knowledge-vault/` (or a symlink to a custom location). It contains:

```
rhetoric-knowledge-vault/
+-- tracking-database.json      # Source of truth: all talks, status, config
+-- rhetoric-style-summary.md   # Narrative analysis across all rhetoric dimensions
+-- slide-design-spec.md        # Visual design rules (fonts, colors, layout taxonomy)
+-- speaker-profile.json        # Machine-readable bridge to the creator
+-- sessions-catalog.md         # Submission-ready titles, abstracts, outlines
+-- analyses/                   # Per-talk rhetoric analysis + pattern scoring
+-- transcripts/                # Downloaded YouTube transcripts
+-- slides/                     # Downloaded slide PDFs
```

**rhetoric-style-summary.md** is the constitution — rich prose covering presentation modes, opening patterns, humor techniques, audience interaction styles, closing patterns, verbal signatures, persuasion techniques, and more. It grows every time you parse new talks.

**speaker-profile.json** is the specification — structured data that the creator reads at runtime: presentation modes with quantitative thresholds, instrument catalogs, guardrail rules, pacing data, design rules, the publishing workflow, and a `pattern_profile` with per-pattern mastery levels, antipattern frequency, signature combinations, and never-used patterns.

**slide-design-spec.md** captures visual design rules extracted from both PDF inspection and programmatic .pptx analysis: background colors, typography, footer specs, shape vocabulary, and template layout catalog.

### Handoff Mechanism

The skills communicate exclusively through the vault files plus
per-talk artifacts (`outline.yaml`, `_talks/*.md`). When the vault
updates (new talks parsed), it regenerates the speaker profile. When
a downstream skill runs, it reads the latest vault state and the
talk's spec. A freshness check warns if the profile is stale.

```
Vault skills (analysis)            Downstream skills (generation + publish)
=======================            =======================================
vault-ingress      ----+
vault-clarification    +-->  rhetoric-style-summary.md  -->  presentation-creator
vault-profile      ----+      slide-design-spec.md           illustrations
                              speaker-profile.json            (via outline.yaml)
                              (incl. pattern_profile)

                                                              presentation-creator
                                                              produces outline.yaml
                                                                      |
                                                                      v
                                                              shownotes-publisher
                                                              reads outline.yaml +
                                                              resources.json, writes
                                                              _talks/<file>.md
```

### Steering Rules

The tile ships persistent steering rules (auto-loaded by the agent at runtime via `tile.json` → `steering`). Keep this table in sync with the manifest:

| Rule | Scope |
|------|-------|
| [`vault-language-policy`](rules/vault-language-policy.md) | Vault analysis prose conventions and forbidden phrasings. |
| [`slide-generation-rules`](rules/slide-generation-rules.md) | `.pptx` generation gotchas and Keynote compatibility constraints. |
| [`deck-editing-rules`](rules/deck-editing-rules.md) | Structural edits (delete/reorder/import) to illustrated decks via real PowerPoint (macOS), not python-pptx. |
| [`guardrail-rules`](rules/guardrail-rules.md) | Creator guardrail checks (slide budget, Act 1 ratio, profanity, branding, antipattern scan). |
| [`illustration-rules`](rules/illustration-rules.md) | Edit vs regenerate asymmetry, build chains, iteration hygiene. |
| [`title-overlay-rules`](rules/title-overlay-rules.md) | Title-safe-zone composition policy for FULL illustrations. |
| [`thumbnail-generation-rules`](rules/thumbnail-generation-rules.md) | Phase 7 thumbnail composition specifics. |
| [`resources-gathering-rules`](rules/resources-gathering-rules.md) | Phase 6 shownotes / resources read paths. |
| [`interaction-rules`](rules/interaction-rules.md) | Conversational stance and gate behavior across phases. |
| [`tessl-version-floating`](rules/tessl-version-floating.md) | Authority-of-record for the `tessl.json` floating-spec carve-out (paired with `scripts/check-tessl-pins.sh`). |
| [`shownotes-content-publish`](rules/shownotes-content-publish.md) | Authority-of-record for the shownotes content direct-push carve-out (paired with `skills/shownotes-publisher/scripts/content-only-gate.sh`). |

## Vault Skills Details

The vault skills (`vault-ingress`, `vault-clarification`,
`vault-profile`) share the analysis triggers and processing pipeline
below.

### Triggers

- `parse my talks` / `run the rhetoric analyzer`
- `analyze my presentation style`
- `how many talks have been processed`
- `update the rhetoric knowledge base` / `check rhetoric vault status`
- `process remaining talks for style patterns`
- `generate my speaker profile` / `update speaker profile`

### 14 Rhetoric Dimensions

Each talk is analyzed across:

1. **Opening pattern** — hook type, first impression strategy
2. **Narrative structure** — arc, throughline, act breakdown
3. **Humor & wit** — technique, register, frequency, placement
4. **Audience interaction** — polls, questions, direct address
5. **Transition techniques** — verbal bridges, visual transitions
6. **Closing pattern** — callback, CTA, summary, emotional note
7. **Verbal signatures** — recurring phrases, characteristic expressions
8. **Slide-to-speech relationship** — density, reading vs. springboarding
9. **Persuasion techniques** — argument structure, credibility building
10. **Cultural & pop-culture references** — what's referenced and how
11. **Technical content delivery** — simplification, progressive revelation
12. **Pacing clues** — section lengths, density, speed variation
13. **Slide design patterns** — per-slide visual classification, typography, shapes, illustration style
14. **Reflection** — critical assessment of what could be improved

Each dimension is cross-referenced with the Presentation Patterns taxonomy — the analysis
notes which named patterns and antipatterns are detected per talk.

### Processing Pipeline

- Talks are processed in **parallel batches of 5** subagents
- Transcripts are downloaded via `yt-dlp` (with `youtube-transcript-api` fallback)
- Slides are acquired from PPTX files (preferred, richer data) or downloaded as PDFs via `gdown`
- Each talk is scored against 91 observable patterns from the taxonomy
- Each batch updates the summary, per-talk analysis files, and triggers profile regeneration
- An interactive clarification session resolves ambiguities and captures confirmed intent

### Prerequisites

- Python 3 with `gdown`, `youtube-transcript-api`, and `python-pptx`
- `yt-dlp` for transcript downloading
- Talks with YouTube video + slides (PPTX files and/or Google Drive PDF exports)

## Generation & Publishing Skills Details

The downstream skills (`presentation-creator`, `illustrations`,
`shownotes-publisher`) build new talks from vault data + per-talk
intent, generate the visual layer, and publish the talk page to the
shownotes site. `presentation-creator` is the entry point; the other
two are invoked via typed `Skill(...)` handoffs.

### Triggers (presentation-creator)

- `create a presentation about [topic]`
- `build a talk for [conference]`
- `write a CFP for [conference]`
- `adapt my [talk name] for [new venue]`

### Triggers (shownotes-publisher)

- `publish shownotes` / `add talk to shownotes` / `shownotes for [talk]`
- `update shownotes with the recording` (once the video URL lands)
- Fires automatically after `presentation-creator` Phase 6 when the
  speaker says "now publish to shownotes"

### 7-Phase Workflow

| Phase | What happens | Gate |
|-------|-------------|------|
| 0: Intake | Load vault + pattern index, gather context | Topic and context captured |
| 1: Intent Distillation | Clarifying questions, produce Presentation Spec | Author confirms spec |
| 2: Rhetorical Architecture | Joint instrument selection + Pattern Strategy | Author approves architecture |
| 3: Content Development | Section-by-section outline with speaker notes | Draft delivered |
| 4: Revision & Guardrails | Iterate on feedback, run guardrail checks + antipattern scan | Author declares outline done |
| 5: Slide Generation | Build .pptx from outline using speaker's template | Author declares slides done |
| 6: Publishing | Export, shownotes, QR code, go-live checklist | Published and ready to deliver |

### Guardrail System (10 checks + pattern taxonomy scan)

1. **Slide budget** — per-duration max from the profile
2. **Act 1 ratio** — problem section balance limits
3. **Conference branding** — footer, logos, stale names
4. **Profanity audit** — register consistency, on-slide profanity flagging
5. **Data attribution** — source visibility on data slides
6. **Time-sensitive content** — expired dates, version numbers
7. **Closing completeness** — summary + CTA + social
8. **Modular cut lines** — present for shorter/longer adaptation
9. **Anti-pattern flags** — speaker-specific recurring issues from the vault
   - **9A:** Profile-based recurring issues
   - **9B:** Taxonomy-based antipattern scan — `[RECURRING]` from speaker history, `[CONTEXTUAL]` from outline analysis
10. **Illustration coverage** — format tags, EXCEPTION justifications, style anchor references, prompt quality (when illustration strategy is defined; `[SKIP]` otherwise)

### Presentation Patterns Taxonomy

The creator includes a structured reference taxonomy of 102 presentation patterns and
antipatterns from *Presentation Patterns* (Ford, McCullough, Schutta 2013) supplemented
by *Presentation Zen* (Reynolds, 2nd ed. 2012), *Resonate* (Duarte 2010), and a small
set of vault-derived patterns observed across the corpus (`delayed-self-introduction`,
`three-part-close`, `progressive-reveal`, `anti-sell`, `meme-as-argument`), organized
by presentation lifecycle:

- **Prepare** (22): Know Your Audience, Narrative Arc, Triad, Talklet, Brain Breaks, Takahashi, Cave Painting, Opening PUNCH, and more
- **Build** (47): Foreshadowing, Bookends, Defy Defaults, Vacation Photos, Traveling Highlights, Emergence, Sparkline, Call to Adventure, Call to Action, New Bliss, S.T.A.R. Moment, Three-Part Close, Progressive Reveal, Meme as Argument, and more
- **Deliver** (33): Carnegie Hall, Breathing Room, Echo Chamber, Seeding the First Question, Screen Blackout, Delayed Self-Introduction, Anti-Sell, and more

Of the 102 entries, **91 are observable** (detectable from transcripts and slides) and
**11 are unobservable** (pre-event logistics, physical stage behaviors, external systems
that leave no trace in recordings).

**How it integrates:**

| Integration point | Observable patterns (91) | Unobservable patterns (11) |
|---|---|---|
| **Vault scoring** (Step 3 B2) | Scored per talk, aggregated into `pattern_profile` | Excluded from scoring |
| **Creator Phase 2** | 4-tier Pattern Strategy (Signature / Contextual / New to You / Shake It Up) | Included in recommendations |
| **Creator Phase 4** | `[RECURRING]` + `[CONTEXTUAL]` antipattern flags | Excluded from scan |
| **Creator Phase 6** | — | Go-live preparation checklist |
| **Speaker profile** | `pattern_profile` with mastery levels, trends, combos | Not in profile |
| **Summary-only mode** | Flat relevant-patterns list from reference files | Go-live checklist still applies |

### Special Workflows

- **Adapting existing talks** — pre-fills spec from vault analysis, auto-generates adaptation checklist
- **CFP abstract writing** — lightweight Phase 0-1, produces title + abstract + takeaways + bio
- **Co-presented talks** — role split, footer adaptation, per-speaker voice in notes

### Summary-Only Mode

If the speaker profile doesn't exist yet (fewer than 10 talks parsed), the creator runs in **summary-only mode** — drawing instruments from the rhetoric summary prose, using default guardrail thresholds, and asking for template/publishing details interactively. The pattern taxonomy still works (all patterns shown as "new"), and the go-live checklist still applies.

## Prerequisites

### For the Vault Skills (vault-ingress, vault-clarification, vault-profile)
- Python 3 environment with `gdown`, `youtube-transcript-api`, `python-pptx`
- `yt-dlp` command-line tool
- Talks with YouTube recordings and slides (PPTX files and/or Google Drive exports)

### For the Presentation Creator & Illustrations Skills
- Microsoft PowerPoint with VBA macros — the deck engine: slide generation, structural edits, speaker notes, backgrounds, and QR all drive the real app (macOS only). One-time `DeckOps.pptm` macro setup: `skills/presentation-creator/references/deck-editing-setup.md`
- `python-pptx` (extraction reads + the illustration scrim/title apply pass)
- A PowerPoint template (the vault captures the path; a generic template works too)

### For the Shownotes Publisher Skill
- A Jekyll-based shownotes site cloned locally (`~/Projects/shownotes`
  by default). The site must use the custom markdown parser plugin
  this skill targets; see
  [`skills/shownotes-publisher/references/parser-contract.md`](skills/shownotes-publisher/references/parser-contract.md)
- `bundle exec jekyll build` available locally for the Step 8 validation
- `gh` CLI for the branch + PR publish flow (and for direct push under
  the `ci-safety` Content-Only Direct-Push Carve-Out when the target
  repo has it wired)

## File Reference

```
speaker-toolkit-tile/
+-- tile.json
+-- README.md
+-- CHANGELOG.md
+-- pyproject.toml                            # Dependencies + pytest config
+-- tests/                                    # 119 tests across 15 files
|   +-- conftest.py                           # Script import helpers + PPTX fixtures
|   +-- test_*.py                             # One test file per script
+-- .github/workflows/
|   +-- tests.yml                             # pytest on push/PR (ffmpeg + LibreOffice)
|   +-- publish-tile.yml                      # Tessl skill review + publish
+-- skills/
    +-- vault-ingress/
    |   +-- SKILL.md                          # Main vault workflow (6 steps)
    |   +-- scripts/
    |   |   +-- pptx-extraction.py            # python-pptx visual extraction
    |   |   +-- video-slide-extraction.py     # Video-to-slides via ffmpeg + perceptual dedup
    |   |   +-- vtt-cleanup.py                # WebVTT to plain text
    |   |   +-- batch-download-videos.sh      # Parallel video download for batch processing
    |   +-- references/
    |       +-- rhetoric-dimensions.md        # 14 analysis dimensions + pattern cross-refs
    |       +-- schemas-db.md                 # DB, subagent, and extraction output schemas
    |       +-- video-slide-extraction.md     # Layout heuristics, tuning tables, limitations
    |       +-- processing-rules.md           # Language policy, pattern migration logic
    +-- presentation-creator/
    |   +-- SKILL.md                          # Main creator workflow (7 phases)
    |   +-- scripts/
    |   |   +-- generate-qr.py                # QR generation + bg-color match (insert via InsertQR)
    |   |   +-- extract-resources.py          # Resource link extraction from outlines
    |   |   +-- guardrail-check.py            # Outline guardrail validation
    |   |   +-- export-pdf.py                 # Export deck to PDF (PowerPoint or LibreOffice)
    |   |   +-- validate-deckops.py           # Validate a deck op sequence before BuildDeck (tested)
    |   |   +-- build-deck.sh                  # Wrapper for BuildDeck (whole-deck creation via real PowerPoint)
    |   |   +-- build-deck.applescript         # AppleScript driver for BuildDeck (reads ops as UTF-8)
    |   |   +-- RunDeckOps.bas                 # VBA: BuildDeck + trim/reorder/import/notes/bg/placeholder/QR via real PowerPoint
    |   |   +-- run-deck-ops.sh                # Wrapper for RunDeckOps (staging + move into place)
    |   |   +-- run-deck-ops.applescript       # AppleScript driver for RunDeckOps
    |   |   +-- make-bg-slide.sh               # Wrapper for MakeBgImageSlide (illustration -> bg slide)
    |   |   +-- make-bg-slide.applescript      # AppleScript driver for MakeBgImageSlide
    |   |   +-- make-placeholder-slide.sh       # Wrapper for MakePlaceholderSlide (yellow [PLACEHOLDER] slide)
    |   |   +-- make-placeholder-slide.applescript # AppleScript driver for MakePlaceholderSlide
    |   |   +-- apply-backgrounds.sh           # Wrapper for ApplyBackgrounds (bulk FULL-slide bg fills)
    |   |   +-- apply-backgrounds.applescript  # AppleScript driver for ApplyBackgrounds
    |   |   +-- backgrounds-manifest-to-spec.py # Manifest JSON -> ApplyBackgrounds spec (tested)
    |   |   +-- inject-notes.sh                # Wrapper for SetSpeakerNotes (notes via real PowerPoint)
    |   |   +-- inject-notes.applescript       # AppleScript driver for SetSpeakerNotes (reads notes as UTF-8)
    |   |   +-- notes-to-packed.py             # Notes JSON -> SetSpeakerNotes wire format (tested)
    |   |   +-- insert-qr.sh                    # Wrapper for InsertQR (QR PNG bottom-right via real PowerPoint)
    |   |   +-- insert-qr.applescript           # AppleScript driver for InsertQR
    |   +-- references/
    |       +-- phase0-intake.md through phase7-post-event.md  # Phase detail docs
    |       +-- patterns/                     # Presentation Patterns taxonomy (102 entries)
    |           +-- _index.md                 # Master index, phase mapping, dimension lookup
    |           +-- prepare/                  # 19 patterns + 3 antipatterns
    |           +-- build/                    # 37 patterns + 10 antipatterns
    |           +-- deliver/                  # 21 patterns + 12 antipatterns (11 unobservable)
    +-- illustrations/
    |   +-- SKILL.md                          # Visual layer workflow (7 mode-routed steps)
    |   +-- scripts/
    |   |   +-- model_registry.py             # Model roster, aliases, attributes; --check-freshness + --shortlist
    |   |   +-- generate-illustrations.py     # Illustration generator + model comparison + style exploration + builds
    |   |   +-- apply-illustrations-to-deck.py # Swap into deck, reposition title, position IMG+TXT
    |   |   +-- suggest-scrim-color.py        # Sample deck-tuned scrim color from illustrations
    |   |   +-- generate-thumbnail.py         # YouTube thumbnail via Gemini composition
    |   +-- references/
    |       +-- strategy.md                   # Phase 2 D#11 — priorities, model shortlist, style proposals, exploration render
    |       +-- generation.md                 # Setup, edit/fix workflow, format vocabulary, apply-to-deck
    |       +-- builds.md                     # Backwards-chained build generation + deck insertion
    |       +-- thumbnails.md                 # Phase 7 thumbnail composition + slide selection
    |       +-- style-explore-candidates-schema.md # candidates.json contract for --style-explore
    |       +-- title-placement.md            # Outline schema + scripts for Safe-zone title placement
    +-- shownotes-publisher/
        +-- SKILL.md                          # Jekyll shownotes publish workflow (9 steps)
        +-- references/
            +-- parser-contract.md            # `_plugins/markdown_parser.rb` capture rules per extracted_* field
            +-- template-conditionals.md      # `talk.html` conditional rendering per extracted field
            +-- common-mistakes.md            # 13 failure modes (1, 1b, 1c, 2-11) with right-way fixes
```

## License

MIT
