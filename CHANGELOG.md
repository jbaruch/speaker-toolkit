# Changelog

## 0.17.0

**Talk timer, Keynote compatibility, shownotes destination** — New delivery timer
artifact, documented Keynote gotchas for slide generation, and machine-readable
shownotes publishing destination.

### Presentation Creator

- **`generate-talk-timings.py`** — new script parses `## Pacing Summary` table
  from the outline into `MM:SS Chapter` plain-text format for timemytalk.app.
  Supports `--qa` flag for Q&A chapters, sub-minute resolution, and automatic
  subdivision of acts exceeding 5 min using `## Section` headers
- **Phase 6 Step 6.4: Talk Timer Artifact** — new optional publishing step,
  gated on pacing summary presence in the outline
- **Keynote compatibility rules** — three python-pptx slide generation gotchas
  added to `slide-generation-rules.md`: use rectangles not connectors for
  decorative lines, never create-then-remove shapes in the same authoring flow,
  keep shape IDs contiguous per slide

### Resources & Publishing

- **Shownotes publishing destination** — `publishing_process.shownotes_site` added
  to speaker profile schema. Resources-gathering rules section 8 documents the
  read path: construct talk URLs from `shownotes_site` + `shownotes_url_pattern`,
  never guess or search the web
- **Vault-clarification config question** — new Step 5B question for
  `publishing_process.shownotes_site`

### Tests

- 15 new tests for `generate-talk-timings.py` (pacing parsing, cumulative times,
  Q&A insertion, sub-minute resolution, subdivision)

## 0.16.0

**Vault-clarification eval + test suite** — First dedicated eval for the interactive
clarification session, fixed volatile eval scenarios, and full pytest coverage for
every script with CI.

### New Eval

- **`clarification-interactive-session`** — first eval testing the vault-clarification
  skill's interactive session: rhetoric clarification (one question at a time), humor
  post-mortem (per-beat grading), blind spot probing, infrastructure config capture,
  intent confirmation storage, and session completion marking. Fixed test data with 1
  analyzed talk, empty config, 10-criterion weighted checklist

### Eval Fixes

- **Scenario 12** (humor post-mortem) — rewritten from "write a Python debrief tool" to
  "process these two fixed analysis files and produce structured debrief outputs." Fixed
  test data in `eval-resources/scenario-12/` (recent + old talk analyses)
- **Scenario 13** (extraction diagnostics) — rewritten from "write a diagnostics tool" to
  "analyze these 6 fixed extraction results and produce a report." Fixed test data in
  `eval-resources/scenario-13/` (6 concrete recording cases)

### Bug Fix

- **`pptx-extraction.py`** — fixed `AttributeError` crash on `_NoneColor` when extracting
  font colors from slides with unset color properties

### Tests & CI

- **119 tests across 15 test files** covering all Python scripts and the bash downloader
- **GitHub Actions workflow** (`tests.yml`) — runs on push to main + PRs, Python 3.12,
  installs ffmpeg and LibreOffice for full integration coverage
- **`pyproject.toml`** — declares all dependencies (python-pptx, lxml, qrcode, Pillow,
  imagehash, numpy) with `[test]` optional group for pytest

### Script Refactors

- **`strip-template.py`** — wrapped in `strip_slides()` + `main()` guard for importability
- **`delete-slides.py`** — wrapped in `delete_slides()` + `main()` guard
- **`reorder-slides.py`** — wrapped in `reorder_slide()` + `main()` guard (now raises
  `IndexError` on out-of-range instead of `sys.exit`)
- **`export-pdf.py`** — wrapped in `main()` guard, functions now take parameters
- **`_pptx_repair.py`** — extracted shared `clean_viewprops()` from strip-template and
  delete-slides into a single module, eliminating code duplication

## 0.15.0

**Placeholder slides, resources gathering, and post-event workflow** — New deck
adaptation tooling, Phase 6.0 resources extraction, Phase 7 post-event workflow,
and hardened QR generation.

### Presentation Creator

- **`insert-placeholder-slides.py`** — new script inserts bright-yellow placeholder
  slides at specified positions (1-indexed). Supports JSON file or `--at`/`--title`
  CLI input, `--output` flag for non-destructive saves. Processes positions in
  descending order to avoid index shifting
- **Phase 6.0: Resources gathering** — new `extract-resources.py` script parses
  presentation outlines for URLs, GitHub repos, book references, RFCs, and
  tool/library mentions. Deduplicates, tracks slide context, outputs JSON or markdown
- **Phase 7: Post-event workflow** — new phase covering post-delivery tasks
- **`generate-thumbnail.py`** — YouTube thumbnail generation via Gemini, composing
  slide images + speaker photos with style variants and YouTube spec validation
- **Shownotes slug convention** — slug generation process added to Phase 1 intent
  distillation, enforced from Presentation Spec (never agent-invented)
- **Presentation Spec persistence** — specs saved to disk as `presentation-spec.md`

### QR Generation Hardening

- **Custom Bitly domains** — `generate-qr.py` supports custom domains (e.g., `jbaru.ch`)
- **Per-slide QR colors** — different slides can have different background colors;
  script generates minimal PNG variants grouped by color scheme
- **Idempotent re-runs** — existing QR images replaced instead of stacked
- **`--png-only` mode** — generate QR PNG without opening a deck
- **Loud missing config** — missing shortener config surfaces as a warning, not silent
  degradation. Actionable `secrets.json` creation commands in error messages
- **Late-entry guard** — Phase 6 pre-flight checklist, no-raw-dogging rule

### Bug Fixes

- Fixed Bitly custom back-half silently ignored
- Fixed PPTX corruption from stale viewProps.xml after slide deletion
- Fixed multi-placeholder insertion index bugs

### Evals

- 2 new scenarios: insert-placeholder-slides, QR generation failure modes

## 0.14.0

**QR code generation** — Automated QR code generation and insertion into decks during
Phase 6 publishing, with slide background color matching and auto-contrast foreground.

**Gemini API key in secrets.json** — `generate-illustrations.py` now reads the Gemini
API key from `{vault}/secrets.json` (`gemini.api_key`) first, falling back to the
`GEMINI_API_KEY` environment variable for backward compatibility. This unifies all API
keys in one file. New `--vault` CLI argument for custom vault paths.

### Presentation Creator

- **`generate-qr.py` script** — new script generates unbranded QR codes from shownotes
  URLs (or pre-shortened URLs), matches the QR background to the target slide's color,
  and auto-selects white or black foreground based on WCAG relative luminance. Inserts
  the QR as a 2" square in the bottom-right corner of the configured slide(s)
- **Phase 6 step reordering** — QR generation now runs before PDF export (was after).
  Steps: Shownotes → QR Code → Export → Additional → Go-live → Report
- **URL shortening support** — bit.ly and rebrand.ly via direct API or MCP-preresolved
  mode. Re-running for the same talk slug updates the existing short link (keeps printed
  QR codes valid). Falls back to raw URL when shortener=none or API fails
- **Vault-based secrets** — API keys stored in `{vault}/secrets.json` (not env vars),
  documented with `chmod 600` recommendation

### Schema Changes

- **Speaker profile `qr_code`** — 5 new fields: `custom_url`, `shortener`,
  `rebrandly_domain`, `bg_color_match`, `preferred_short_path`
- **Tracking database `qr_codes[]`** — new top-level array tracking per-talk QR
  metadata: talk slug, target URL, shortener, short path/URL, link ID, PNG path
- **Vault clarification** — 3 new questions for shortener preference, Rebrandly
  domain, and API key setup

### Evals

- 1 new scenario (scenario-19): QR generation with purple background matching,
  auto-contrast white foreground, shortener=none path, tracking DB update

## 0.11.0

**Illustration pipeline** — AI-generated illustrations are now a first-class part of
the presentation creation process, with collaborative style decisions and per-slide
image prompts generated during outline creation.

### Presentation Creator

- **Phase 2: Illustration Strategy (Decision #11)** — optional collaborative workflow
  for talks that want AI-generated illustrations. Proposes 3-4 style options informed
  by the talk's concepts, the vault's visual history, and mode-specific precedent.
  Includes format vocabulary, model selection (with `--compare` mode), and visual
  continuity devices
- **Phase 3: Illustrated outline format** — new Illustration Style Anchor section in
  the outline header (model, per-format anchors, conventions). Per-slide Format,
  Illustration, Text overlay, and Image prompt fields. `[STYLE ANCHOR]` token
  referencing the header. `[IMAGE NN]` placeholder type for EXCEPTION slides
- **Phase 4: Illustration coverage guardrail (#10)** — checks format tag coverage,
  EXCEPTION justifications, style anchor references, and prompt quality. Shows
  `[SKIP]` for non-illustrated outlines
- **Phase 5: Generate illustrations step** — new Step 5.1b runs
  `generate-illustrations.py` to batch-generate images before slide population.
  Image Generation Setup docs with API key, model, and `--compare` instructions
- **Slide generation** — illustration-format-aware insertion (FULL → full-bleed,
  IMG+TXT → image + text, EXCEPTION → real asset) added to slide-generation.md

### Rhetoric Knowledge Vault

- **Dimension 13f: Illustration & Image Style** — new analysis sub-dimension for
  image source types, illustration aesthetic, visual coherence, style anchor evidence,
  visual continuity devices, and mode correlation
- **Structured data fields** — `illustration_style`, `illustration_coherence`,
  `image_source_distribution`, `visual_continuity_devices` added to extraction output
- **Speaker profile: `visual_style_history`** — new section with default style,
  style departures, mode-specific visual profiles, and confirmed visual intents
- **Schema fixes** — `transcript_source` added as required field on talk entries and
  subagent return schema. `delivery_language` and `co_presenter` added to subagent
  return schema. English-first quote rule promoted to inline in SKILL.md
- Video-as-slide-fallback reinforced in Step 3A processing instructions

### New files

- `skills/presentation-creator/references/generate-illustrations.py` — stdlib-only
  Python script for Gemini API image generation with `--compare` mode, resumable
  batch runs, rate limiting, and progress reporting

### Evals

- 2 new scenarios: illustrated outline format, illustration guardrail audit
- Updated guardrail audit scenario to check `[SKIP]` illustrations line
- 11 new instructions in instructions.json covering illustration features
- Fixed pre-existing eval gaps: task descriptions, criteria alignment, skill content

## 0.10.1

**Small print** — Sessions catalog entries now include a "Small Print" field for
Program Committee notes (talk positioning, what it is/isn't, reviewer context).

## 0.10.0

**Sessions catalog** — New `sessions-catalog.md` file in the vault for maintaining
submission-ready conference materials (title, abstract, outline) per active talk.

- Added Sessions Catalog section to presentation-creator SKILL.md with read/write
  rules: when to pull from the catalog (before writing a new CFP), when to save
  (after CFP writing or Phase 4 outline finalization), and maintenance guidelines
- CFP Abstract Writing flow now includes step 5: save to sessions catalog
- Added `sessions-catalog.md` to the vault skill's Key Files table
- Anti-pattern checking recommended on catalog entries before saving (public-facing text)

## 0.7.0

**Canonical vault path** — The vault now uses `~/.claude/rhetoric-knowledge-vault/` as
a fixed, discoverable location. No more asking "where should the vault live?" every
session. Custom locations (e.g., Google Drive) are symlinked to the canonical path.

- Vault discovery replaces config bootstrapping for `vault_root` — checks canonical
  path first, creates or symlinks on first run
- New `vault_storage_path` config field tracks the actual directory when using a custom
  location
- Updated presentation-creator to read vault from the canonical path directly
- Updated eval instructions (+2 new vault discovery instructions) and scenario-1
  criteria (canonical path check)
- README updated to reflect new vault location behavior

## 0.6.2

**Maintenance** — Version bump and CLI publish.

## 0.6.1

**Eval scenarios** — Added 5 new server-generated eval scenarios via `tessl scenario
generate`, covering both skills end-to-end. Reviewed and fixed all 15 scenarios for
quality, then ran the full eval suite (baseline avg 62% → with-skill avg 98%).

### New scenarios (5)
- Multilingual rhetoric analysis with language policy and pattern scoring
- Presentation outline with typed placeholders and callbacks
- python-pptx deck generation with template stripping and notes injection
- Guardrail check format and 4-tier pattern strategy
- Speaker profile JSON generation from vault data

### Scenario fixes
- Removed instruction leakage from python-pptx scenario (replaced numbered output
  spec with high-level ask)
- Fixed factual error in guardrail scenario (Act 1 ratio math: 51.7% → 43.3% to
  correctly test the WARN threshold)
- Fixed infeasible criteria (replaced MCP-only `optimize_slide_text` with python-pptx
  overflow handling)
- Fixed transcript pre-translating Russian phrases (defeated the English-only quote
  format test)
- Fixed ambiguous download results in status management scenario (added
  `video_extraction` field, clarified planning-time vs download-outcome for
  `slide_source`)
- Added missing `capability.txt` files to all new scenarios
- Tightened subjective criteria wording across all scenarios

## 0.5.5

**Video-extracted slides** — When no slides file exists, extract slides directly
from video: ffmpeg frame extraction → crop to slide area (exclude PiP) → perceptual
hash deduplication → combine into PDF. Marks `slide_source: "video_extracted"`.

## 0.5.4

**Non-YouTube video support** — Step 3A now supports ingesting talks from InfoQ,
Vimeo, conference platforms, and any source yt-dlp supports. Downloads audio via
`yt-dlp -f http_audio`, transcribes locally with MLX Whisper (Apple Silicon) or
OpenAI Whisper. Tags transcript source as `"whisper"` vs `"youtube_auto"`.

## 0.5.3

**Data integrity fixes:**

- **Summary status recount:** Step 4 now rewrites the summary Status block by
  counting the tracking DB every time. The DB is the source of truth; the summary
  is a derived view. Fixes stale tallies from manual incrementing.
- **Structured field extraction:** Step 4 now requires populating `co_presenter`,
  `delivery_language`, and other structured DB fields directly from analysis results,
  not burying them in `rhetoric_notes` free text.

## 0.5.2

**Blind spot clarification + language policy** — Two additions to the vault skill:

- **Step 5A-bis (Blind Spots):** After analyzing each talk, the skill identifies
  moments it knows it missed (audience reactions, costume/prop moments, room energy,
  demo engagement) and asks the speaker. Stores as `blind_spot_observations`.
- **Language policy:** The vault is English-only. Non-English talks are analyzed and
  stored in English with translated quotes, language-tagged verbal signatures, and
  `delivery_language` on the talk entry. Prevents non-English content from polluting
  the signature list or rhetoric summary.

## 0.5.1

**Robustness & conciseness** — Addressed gaps found during tile review and
tightened both skills for the review gate.

### Robustness fixes
- Made vault→creator pattern index path explicit with tile-root-relative path
- Added pattern taxonomy migration: Step 1 detects pre-v0.5.0 talks missing
  `pattern_observations` and marks them `needs-reprocessing`
- Added `clarification_sessions_completed` counter to tracking DB config
- Added LibreOffice CLI as cross-platform PDF export alternative
- Clarified Step 3B firing conditions

### Conciseness improvements
- Vault SKILL.md: 285 → 207 lines. Consolidated reference file list into Key
  Files table, collapsed config bootstrapping, tightened PPTX/PDF handling,
  moved Step 5B questions to `schemas.md`, compressed profile mapping and badges
- Creator SKILL.md: 263 → 230 lines. Merged vault loading steps, condensed
  Phase 2 decisions table, removed summary-only mode table (now inline)
- Review threshold lowered to 85 (vault conciseness 2/3 has no actionable
  feedback per the optimizer)

## 0.5.0

**Presentation Patterns integration** — Integrated the pattern taxonomy from
*Presentation Patterns* (Ford, McCullough, Schutta 2013) as a structured reference,
vault scoring system, and brainstorming vocabulary across both skills. Patterns are
classified as observable (scored by the vault) or unobservable (surfaced as a go-live
checklist before delivery).

### Pattern taxonomy (88 new files)

- 88 reference files (63 patterns + 25 antipatterns) organized by lifecycle phase
  (prepare/build/deliver) with YAML frontmatter: `id`, `name`, `type`, `part`,
  `phase_relevance`, `vault_dimensions`, `detection_signals`, `related_patterns`,
  `inverse_of`, `difficulty`, and `observable` (true by default, false for 11 entries)
- Master index (`references/patterns/_index.md`): flat catalog table, phase-grouped
  lookup, vault dimension reverse mapping, and unobservable patterns go-live checklist
- Each file includes: summary, detailed description, when to use/avoid, detection
  heuristics, 3-tier scoring criteria, vault dimension mapping, and combinatorics

### Observable vs unobservable split

- **77 observable** patterns are detectable from transcripts + slides and scored during
  vault analysis
- **11 unobservable** patterns (8 patterns + 3 antipatterns) involve pre-event logistics,
  physical stage behaviors, or external systems that leave no trace in recordings:
  - Pre-event: Preparation, Carnegie Hall, Stakeout, Posse, Seeding Satisfaction, Shoeless
  - During delivery: Lightsaber, Red/Yellow/Green
  - Antipatterns to avoid: Laser Weapons, Bunker, Backchannel
- Unobservable patterns are marked `observable: false` in their frontmatter, excluded
  from vault scoring and `pattern_profile`, and surfaced as a go-live preparation
  checklist in creator Phase 6

### Vault scoring (4 modified files)

- Subagents now tag talks against the observable pattern taxonomy during analysis
  (Step 3 B2), skipping patterns marked `observable: false`
- `pattern_observations` field added to both subagent return schema and tracking
  database talk entries (`schemas.md`)
- Per-talk analysis files now include a "Presentation Patterns Scoring" section
- Step 6 generates an aggregate `pattern_profile` in the speaker profile with mastery
  levels, usage trends, signature combinations, antipattern frequency, and never-used
  patterns (observable only)
- Pattern-based badges generated from profile data (e.g., "Narrative Arc Master",
  "Shortchanged Survivor", "Pattern Polyglot")
- `pattern_profile` section added to `speaker-profile-schema.md` with documentation
  that only observable patterns are included
- All 14 rhetoric dimensions in `rhetoric-dimensions.md` cross-referenced with their
  related patterns and antipatterns

### Creator integration (3 modified files)

- Phase 0: Loads `references/patterns/_index.md` alongside vault documents
- Phase 2 (Architecture): Decision #10 "Pattern Strategy" — 4-tier recommendation
  system using `pattern_profile`:
  - **Signature** (80%+ usage) — always shown
  - **Contextual** — matching spec context, occasional speaker usage
  - **New to You** — from never-used patterns, filtered by relevance
  - **Shake It Up** — random picks, provocations not prescriptions
  - Plus antipattern warnings merging speaker history + contextual detection
- Phase 4 (Guardrails): Section 9B adds taxonomy-based antipattern scanning with
  `[RECURRING]` flags from `pattern_profile.antipattern_frequency` and `[CONTEXTUAL]`
  flags from outline analysis
- Phase 6 (Publishing): Step 6.5 go-live preparation checklist surfaces all 11
  unobservable patterns as delivery-day reminders
- Summary-only mode (no profile) still works — patterns from reference files only,
  flat list, go-live checklist still applies

### Documentation

- `README.md` — rewritten with Presentation Patterns section, observable/unobservable
  table, updated file tree, updated vault/creator descriptions
- `tile.json` — bumped to v0.5.0, added "patterns" keyword
- `CHANGELOG.md` — this entry

## 0.4.7

**Review & consistency fixes** — Addressed consistency gaps found during tile review.

- Vault Step 4 now writes per-talk analysis files to `analyses/` (fixes broken adaptation workflow in creator)
- Added `badges` schema to `speaker-profile-schema.md`
- Broke single `publishing_process` question into targeted sub-questions matching the schema
- Clarified summary section numbering vs rhetoric dimension numbering in vault SKILL.md
- Labeled slide budget table in creator as defaults when profile is unavailable
- Added `cfp`, `abstract`, `pptx` keywords to `tile.json`
- Fixed `tessl.json` project name from scaffold placeholder
- Added python-pptx internal API risk note to `slide-generation.md`
- Backfilled CHANGELOG for versions 0.3.1-0.4.5

## 0.4.1 - 0.4.5

**CI/publish pipeline tuning** — Iterative adjustments to the GitHub Actions publish
workflow: switched to the publish action's built-in skill review gate, tested optimize
input, and settled on the default review threshold (50%).

## 0.4.0

**Evaluation scenarios** — Added 10 eval scenarios covering both skills (vault analysis
and presentation creation), plus Tessl eval infrastructure.

- 10 scenario tasks with criteria covering rhetoric analysis, profile generation,
  presentation creation, adaptation, CFP writing, and guardrail enforcement
- Tessl eval tile dependency added

## 0.3.0

**Speaker badges & profile Step 6 enhancement** — Profile regeneration now generates
personalized speaker badges as a fun summary of portfolio-wide achievements, mined from
real vault data (meme counts, employer transitions, recurring patterns, signature quirks).

- Step 6.7 added: generate speaker badges after profile regeneration
- Badges must be genuinely personalized to the speaker's quirks, not generic
- Grounded in aggregated data from all processed talks

## 0.2.0

**PPTX as primary slide source** — The vault skill no longer requires Google Drive slide
PDFs for every talk. Talks with `.pptx` files can now be processed directly, providing
richer data (exact hex colors, font names, layout names) than PDF visual inspection.

- A talk is processable with `video_url` + at least one of `slides_url` or `pptx_path`
- New `slide_source` field on each talk: `"pdf"`, `"pptx"`, or `"both"`
- When PPTX is available, extraction runs inline during rhetoric analysis (Step 3),
  merging what was previously a separate Step 3B pass
- Step 3B now only processes PPTX files not already handled as primary sources
- Schema updated: `slides_url` and `pptx_path` are both optional (at least one required)

## 0.1.0

Initial release with two skills:
- **rhetoric-knowledge-vault** — parse recorded talks to extract rhetoric patterns
- **presentation-creator** — create new presentations matching your documented style
