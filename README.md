# Speaker Toolkit

A two-skill system for conference speakers: analyze your existing talks to extract your rhetoric patterns, then create new presentations that match your documented style.

## What's New (0.2.0)

**PPTX as primary slide source** — Talks with `.pptx` files no longer need Google Drive
PDFs. PPTX provides richer data (exact hex colors, font names, layout names) and runs
inline during rhetoric analysis. See [CHANGELOG.md](CHANGELOG.md) for full history.

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

**Skill 1: Rhetoric Knowledge Vault** parses your recorded talks (YouTube transcripts + Google Drive slide PDFs) and extracts rhetoric patterns across 14 dimensions — opening hooks, humor style, audience interaction, slide design, pacing, transitions, verbal signatures, and more. After analyzing enough talks, it generates a structured speaker profile.

**Skill 2: Presentation Creator** reads the vault at runtime and uses your documented patterns as a constitutional style guide to build new presentations. It follows a 7-phase process from intent distillation through slide generation and publishing.

The skills never run simultaneously. You build the vault first (once, then incrementally), then use the creator whenever you need a new talk. The vault grows over time as you parse more talks, and the creator automatically picks up new patterns.

## Installation

```bash
tessl install jbaruch/speaker-toolkit
```

## Getting Started

### Phase 1: Build Your Vault

You need recorded talks with:
- YouTube videos (for transcripts)
- Google Drive slides (for PDF analysis)
- Optionally, the original .pptx source files (for exact design data)

Organize your talk metadata as `.md` shownotes files in a directory, each containing a video URL and slides URL.

Then run:
```
parse my talks
```

The vault skill will:
1. Ask where your shownotes and presentations live (once)
2. Scan for talks and .pptx files
3. Process talks in parallel batches of 5
4. Extract rhetoric patterns across 14 dimensions
5. Build a running narrative summary and slide design spec
6. Run an interactive clarification session to validate findings and capture your intent
7. Generate a structured speaker profile (after 10+ talks)

### Phase 2: Create Presentations

Once the vault exists, invoke the creator:
```
create a presentation about [topic] for [conference]
```

The creator will:
1. Load your vault (summary, design spec, profile)
2. Walk you through intent distillation (purpose, audience, constraints)
3. Jointly select rhetorical instruments (opening pattern, narrative arc, humor register, closing)
4. Write a section-by-section outline with speaker notes in your voice
5. Run guardrail checks (slide budget, Act 1 ratio, profanity, branding, data attribution)
6. Generate a .pptx deck from your template
7. Execute your publishing workflow (export, shownotes, QR codes)

Every phase requires your approval before proceeding. The skill brings the rhetoric knowledge; you bring the topic expertise.

## Architecture

### Speaker Neutrality

Both skills are generic — they work for any speaker. All personalization lives in the vault:

| Component | What it defines |
|-----------|----------------|
| **Skills** (this tile) | Process: phases, gates, output formats, guardrail structure |
| **Vault** (your data) | Content: what instruments exist, what the speaker sounds like, thresholds to enforce |

When you install this tile, the skills ask where your vault is. If you don't have one yet, the vault skill creates it from scratch.

### The Vault Directory

The vault is a directory on your filesystem containing:

```
rhetoric-knowledge-vault/
+-- tracking-database.json      # Source of truth: all talks, status, config
+-- rhetoric-style-summary.md   # Narrative analysis across all rhetoric dimensions
+-- slide-design-spec.md        # Visual design rules (fonts, colors, layout taxonomy)
+-- speaker-profile.json        # Machine-readable bridge to the creator
+-- transcripts/                # Downloaded YouTube transcripts
+-- slides/                     # Downloaded slide PDFs
+-- analyses/                   # Per-talk rhetoric analysis files
```

**rhetoric-style-summary.md** is the constitution — rich prose covering presentation modes, opening patterns, humor techniques, audience interaction styles, closing patterns, verbal signatures, persuasion techniques, and more. It grows every time you parse new talks.

**speaker-profile.json** is the specification — structured data that the creator reads at runtime: presentation modes with quantitative thresholds, instrument catalogs, guardrail rules, pacing data, design rules, and the publishing workflow.

**slide-design-spec.md** captures visual design rules extracted from both PDF inspection and programmatic .pptx analysis: background colors, typography, footer specs, shape vocabulary, and template layout catalog.

### Handoff Mechanism

The two skills communicate exclusively through the vault files. When the vault updates (new talks parsed), it automatically regenerates the speaker profile. When the creator runs, it reads the latest vault state. A freshness check warns if the profile is stale.

```
Vault Skill                          Creator Skill
===========                          =============
Parse talks                          Load vault files
     |                                    |
     v                                    v
Update summary  ------>  rhetoric-style-summary.md  ------>  Read instruments
Update spec     ------>  slide-design-spec.md       ------>  Read design rules
Regen profile   ------>  speaker-profile.json       ------>  Read thresholds
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
13. **Slide design patterns** — per-slide visual classification, typography, shapes
14. **Reflection** — critical assessment of what could be improved

### Processing Pipeline

- Talks are processed in **parallel batches of 5** subagents
- Transcripts are downloaded via `yt-dlp` (with `youtube-transcript-api` fallback)
- Slide PDFs are downloaded via `gdown`
- .pptx files are programmatically analyzed with `python-pptx` for exact design values
- Each batch updates the summary and triggers profile regeneration
- An interactive clarification session resolves ambiguities and captures confirmed intent

### Prerequisites

- Python 3 with `gdown`, `youtube-transcript-api`, and `python-pptx`
- `yt-dlp` for transcript downloading
- Talks published with YouTube video + Google Drive slides

## Creator Skill Details

### Triggers

- `create a presentation about [topic]`
- `build a talk for [conference]`
- `write a CFP for [conference]`
- `adapt my [talk name] for [new venue]`

### 7-Phase Workflow

| Phase | What happens | Gate |
|-------|-------------|------|
| 0: Intake | Load vault, gather context | Topic and context captured |
| 1: Intent Distillation | Clarifying questions, produce Presentation Spec | Author confirms spec |
| 2: Rhetorical Architecture | Joint instrument selection from vault catalog | Author approves architecture |
| 3: Content Development | Section-by-section outline with speaker notes | Draft delivered |
| 4: Revision & Guardrails | Iterate on feedback, run 9-point guardrail checks | Author declares outline done |
| 5: Slide Generation | Build .pptx from outline using speaker's template | Author declares slides done |
| 6: Publishing | Export, shownotes, QR code per speaker's workflow | Published and ready to deliver |

### Guardrail System (9 checks)

1. **Slide budget** — per-duration max from the profile
2. **Act 1 ratio** — problem section balance limits
3. **Conference branding** — footer, logos, stale names
4. **Profanity audit** — register consistency, on-slide profanity flagging
5. **Data attribution** — source visibility on data slides
6. **Time-sensitive content** — expired dates, version numbers
7. **Closing completeness** — summary + CTA + social
8. **Modular cut lines** — present for shorter/longer adaptation
9. **Anti-pattern flags** — speaker-specific recurring issues from the vault

### Special Workflows

- **Adapting existing talks** — pre-fills spec from vault analysis, auto-generates adaptation checklist
- **CFP abstract writing** — lightweight Phase 0-1, produces title + abstract + takeaways + bio
- **Co-presented talks** — role split, footer adaptation, per-speaker voice in notes

### Summary-Only Mode

If the speaker profile doesn't exist yet (fewer than 10 talks parsed), the creator runs in **summary-only mode** — drawing instruments from the rhetoric summary prose, using default guardrail thresholds, and asking for template/publishing details interactively.

## Prerequisites

### For the Vault Skill
- Python 3 environment with `gdown`, `youtube-transcript-api`, `python-pptx`
- `yt-dlp` command-line tool
- Talks with YouTube recordings and Google Drive slide exports

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
+-- skills/
    +-- rhetoric-knowledge-vault/
    |   +-- SKILL.md                          # Main vault workflow (6 steps)
    |   +-- references/
    |       +-- rhetoric-dimensions.md        # 14 analysis dimensions
    |       +-- speaker-profile-schema.md     # Profile JSON schema
    |       +-- pptx-extraction.md            # python-pptx visual extraction script
    |       +-- download-commands.md          # yt-dlp and gdown commands
    +-- presentation-creator/
        +-- SKILL.md                          # Main creator workflow (7 phases)
        +-- references/
            +-- process.md                    # Detailed phase instructions
            +-- guardrails.md                 # 9-point guardrail check structure
            +-- slide-generation.md           # MCP + python-pptx technical reference
```

## License

MIT
