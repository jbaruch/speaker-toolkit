# Speaker Toolkit

A two-skill system for conference speakers: analyze your existing talks to extract your rhetoric patterns, then create new presentations that match your documented style.

## What's New (0.11.0)

**AI-generated illustration support** — The presentation-creator now supports a full
illustration pipeline: collaboratively choose a visual style grounded in the talk's
concepts and the speaker's visual history (Phase 2), write outlines with per-slide
Format/Illustration/Image prompt fields and a Style Anchor header (Phase 3), run
illustration coverage guardrails (Phase 4), and batch-generate images via Gemini API
with a new `generate-illustrations.py` script (Phase 5). The vault ingress now
analyzes illustration style (dimension 13f) and builds a `visual_style_history` in
the speaker profile to inform future style proposals.

See [CHANGELOG.md](CHANGELOG.md) for full history.

## How It Works

The toolkit has two independent skills connected by a shared **rhetoric vault** — a directory of structured knowledge about how you present.

```
                   VAULT
                 (shared data)
                 +-----------+
  Skill 1        | summary   |        Skill 2
  Rhetoric   --> | design    | <--  Presentation
  Knowledge      | spec      |       Creator
  Vault          | profile   |
  (analysis)     +-----------+     (generation)
```

**Skill 1: Rhetoric Knowledge Vault** parses your recorded talks (YouTube transcripts + slides from PPTX files or Google Drive PDFs) and extracts rhetoric patterns across 14 dimensions — opening hooks, humor style, audience interaction, slide design, pacing, transitions, verbal signatures, and more. It also scores each talk against the Presentation Patterns taxonomy. After analyzing enough talks, it generates a structured speaker profile including a pattern profile with mastery levels and signature combinations.

**Skill 2: Presentation Creator** reads the vault at runtime and uses your documented patterns as a constitutional style guide to build new presentations. It follows a 7-phase process from intent distillation through slide generation, with a 4-tier Pattern Strategy for selecting presentation techniques, and a go-live checklist before delivery.

The skills never run simultaneously. You build the vault first (once, then incrementally), then use the creator whenever you need a new talk. The vault grows over time as you parse more talks, and the creator automatically picks up new patterns.

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
5. Score each talk against the 77 observable Presentation Patterns
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

Both skills are generic — they work for any speaker. All personalization lives in the vault:

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

The two skills communicate exclusively through the vault files. When the vault updates (new talks parsed), it automatically regenerates the speaker profile. When the creator runs, it reads the latest vault state. A freshness check warns if the profile is stale.

```
Vault Skill                          Creator Skill
===========                          =============
Parse talks                          Load vault files + pattern index
     |                                    |
     v                                    v
Update summary  ------>  rhetoric-style-summary.md  ------>  Read instruments
Update spec     ------>  slide-design-spec.md       ------>  Read design rules
Regen profile   ------>  speaker-profile.json       ------>  Read thresholds
  (incl. pattern_profile)                              +-->  Pattern Strategy
                                                       +-->  Go-live checklist
```

## Vault Skill Details

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
- Each talk is scored against 77 observable patterns from the taxonomy
- Each batch updates the summary, per-talk analysis files, and triggers profile regeneration
- An interactive clarification session resolves ambiguities and captures confirmed intent

### Prerequisites

- Python 3 with `gdown`, `youtube-transcript-api`, and `python-pptx`
- `yt-dlp` for transcript downloading
- Talks with YouTube video + slides (PPTX files and/or Google Drive PDF exports)

## Creator Skill Details

### Triggers

- `create a presentation about [topic]`
- `build a talk for [conference]`
- `write a CFP for [conference]`
- `adapt my [talk name] for [new venue]`

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

The creator includes a structured reference taxonomy of 88 presentation patterns and
antipatterns from *Presentation Patterns* (Ford, McCullough, Schutta 2013), organized
by presentation lifecycle:

- **Prepare** (21): Know Your Audience, Narrative Arc, Triad, Talklet, Brain Breaks, Takahashi, Cave Painting, and more
- **Build** (37): Foreshadowing, Bookends, Defy Defaults, Vacation Photos, Traveling Highlights, Emergence, and more
- **Deliver** (30): Carnegie Hall, Breathing Room, Echo Chamber, Seeding the First Question, and more

Of the 88 entries, **77 are observable** (detectable from transcripts and slides) and
**11 are unobservable** (pre-event logistics, physical stage behaviors, external systems
that leave no trace in recordings).

**How it integrates:**

| Integration point | Observable patterns (77) | Unobservable patterns (11) |
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

### For the Vault Skill
- Python 3 environment with `gdown`, `youtube-transcript-api`, `python-pptx`
- `yt-dlp` command-line tool
- Talks with YouTube recordings and slides (PPTX files and/or Google Drive exports)

### For the Creator Skill
- MCP PPT server (for slide generation)
- `python-pptx` (for speaker notes, structural edits)
- Microsoft PowerPoint (for PDF export via AppleScript, macOS only)
- A PowerPoint template (the vault captures the path; a generic template works too)

## File Reference

```
speaker-toolkit-tile/
+-- tile.json
+-- README.md
+-- CHANGELOG.md
+-- skills/
    +-- rhetoric-knowledge-vault/
    |   +-- SKILL.md                          # Main vault workflow (6 steps)
    |   +-- references/
    |       +-- rhetoric-dimensions.md        # 14 analysis dimensions + pattern cross-refs
    |       +-- speaker-profile-schema.md     # Profile JSON schema (incl. pattern_profile)
    |       +-- schemas.md                    # DB and subagent schemas (incl. pattern_observations)
    |       +-- pptx-extraction.md            # python-pptx visual extraction script
    |       +-- download-commands.md          # yt-dlp and gdown commands
    +-- presentation-creator/
        +-- SKILL.md                          # Main creator workflow (7 phases)
        +-- references/
            +-- process.md                    # Phase instructions + Pattern Strategy + go-live checklist
            +-- guardrails.md                 # 10-point guardrails + pattern taxonomy scan (9B)
            +-- slide-generation.md           # MCP + python-pptx technical reference
            +-- generate-illustrations.py     # Gemini API illustration generator + model comparison
            +-- patterns/                     # Presentation Patterns taxonomy (88 entries)
                +-- _index.md                 # Master index, phase mapping, dimension lookup
                +-- prepare/                  # 18 patterns + 3 antipatterns
                +-- build/                    # 27 patterns + 10 antipatterns
                +-- deliver/                  # 18 patterns + 12 antipatterns (11 unobservable)
```

## License

MIT
