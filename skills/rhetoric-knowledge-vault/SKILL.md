---
name: rhetoric-knowledge-vault
description: >
  This skill parses presentation talks to catalog specific rhetoric patterns: opening hooks,
  humor style, pacing, transitions, audience interaction, slide design, and verbal signatures.
  It downloads YouTube transcripts and analyzes slides (from PPTX files or Google Drive PDFs), examining HOW the speaker
  presents. After enough talks are analyzed, it generates a structured speaker profile and
  can create a personalized presentation-creator skill tailored to the speaker's style.
  Triggers: "parse my talks", "run the rhetoric analyzer", "analyze my presentation style",
  "how many talks have been processed", "update the rhetoric knowledge base",
  "check rhetoric vault status", "process remaining talks for style patterns",
  "generate my speaker profile", "update speaker profile".
user_invocable: true
---

# Rhetoric Knowledge Vault — Incremental Talk Parser

Build a rhetoric and style knowledge base by analyzing presentation talks. Each run
processes **unprocessed** talks, extracts rhetoric/style observations, and updates the
running summary. The vault lives at `~/.claude/rhetoric-knowledge-vault/` (may be a
symlink to a custom location). All paths are relative to this **vault root**.

## Key Files & References

| File / Reference | Purpose |
|------------------|---------|
| `tracking-database.json` | Source of truth — talks, status, config, confirmed intents |
| `rhetoric-style-summary.md` | Running rhetoric & style narrative (the constitution) |
| `slide-design-spec.md` | Visual design rules from PDF + PPTX analysis |
| `speaker-profile.json` | Machine-readable bridge to presentation-creator |
| `analyses/{talk_filename}.md` | Per-talk rhetoric analysis (one file per processed talk) |
| `transcripts/{youtube_id}.txt` | Downloaded/cleaned transcripts |
| `slides/{id}.pdf` | Slide PDFs (from Google Drive, PPTX export, or video extraction) |
| `references/schemas.md` | DB + subagent schemas; full config field list |
| `references/rhetoric-dimensions.md` | 14 analysis dimensions |
| `references/pptx-extraction.md` | Visual extraction script |
| `references/speaker-profile-schema.md` | Profile JSON schema |
| `references/download-commands.md` | yt-dlp + gdown commands |
| `references/video-slide-extraction.md` | Extract slides from video when no PDF/PPTX exists |

A talk is processable when it has `video_url`. Slide sources, in order of preference:
1. `pptx_path` → richest data (exact colors, fonts, shapes via python-pptx)
2. `slides_url` → download PDF from Google Drive
3. `video_url` → extract slides from the video using ffmpeg + perceptual dedup
4. none → transcript-only analysis (last resort, `processed_partial`)

The `slide_source` field tracks which path: `"pptx"`, `"pdf"`, `"both"`,
`"video_extracted"`, or `"none"`. The `pptx_catalog` array fuzzy-matches `.pptx`
files to shownotes entries.

## Workflow

### Step 1: Load State & Sync Sources

**Vault discovery** — the canonical vault path is always `~/.claude/rhetoric-knowledge-vault/`.
On every run, check this path first:

1. **Path exists** (directory or symlink) → use it as `vault_root`, read `tracking-database.json`.
2. **Path does not exist** → first-time setup:
   a. Tell the user: "The vault will live at `~/.claude/rhetoric-knowledge-vault/` by default."
   b. Ask via `AskUserQuestion`: "Want a different location? (e.g., Google Drive for backup)
      Enter a custom path, or press Enter / say 'default' to use the default."
   c. **Default chosen:** `mkdir -p ~/.claude/rhetoric-knowledge-vault`
   d. **Custom path chosen:** `mkdir -p {custom_path}` then
      `ln -s {custom_path} ~/.claude/rhetoric-knowledge-vault` — the symlink makes the
      canonical path always work. Store `vault_storage_path` as the custom path in config
      (for display/debugging).
   e. Create empty `tracking-database.json` with empty `config`, `talks`, `pptx_catalog`.

Set `vault_root` to `~/.claude/rhetoric-knowledge-vault` in config (always the canonical path).

**Config bootstrapping** — ask once per missing field and persist to the tracking database.
Remaining core fields: `talks_source_dir`, `pptx_source_dir`, `python_path`
(auto-detect: `{vault_root}/.venv/bin/python3`, then `python3` on PATH),
`template_skip_patterns` (default: `["template"]`).
See `references/schemas.md` for the full config field list (including speaker infrastructure fields).

**Scan for new talks:** Glob `*.md` in `talks_source_dir`. For each file not in the
`talks` array, parse and add (extract title, conference, date, URLs, IDs, status `"pending"`).

**Scan for .pptx files:** Glob `**/*.pptx` in `pptx_source_dir` (skip `*static*`,
conflict copies, template matches). Fuzzy-match to `talks[]` entries. Report counts.

**Pattern taxonomy migration:** If the pattern taxonomy exists
(`skills/presentation-creator/references/patterns/_index.md`) but any talks with
status `"processed"` or `"processed_partial"` have no `pattern_observations` (or
`pattern_observations.pattern_ids` is empty), mark them `"needs-reprocessing"` with
`reprocess_reason: "pattern_scoring_added"`. Report: "N talks need reprocessing for
pattern scoring."

Read `rhetoric-style-summary.md` and `slide-design-spec.md`. Report state:
"X processed, Y remaining. PPTX: A cataloged, B matched, C extracted."

### Step 2: Select Talks to Process

- Select talks with status `pending` or `needs-reprocessing`.
- Set `slide_source` per the hierarchy above. Mark `"skipped_no_sources"` only if
  missing `video_url` entirely.
- If `$ARGUMENTS` specifies a talk filename or title, process ONLY that one.

### Step 3: Process Talks — Parallel Subagents, Batches of 5

Per batch: launch 5 subagents in parallel, wait, run Step 4, then next batch.
Each subagent receives the talk's DB entry and current `rhetoric-style-summary.md`.

#### Per-Talk Subagent Instructions:

**A. Download transcript and acquire slides:**

**YouTube talks** (default — try ALL likely languages, not just English):
```bash
yt-dlp --write-auto-sub --sub-lang "en,ru,he,fr,de,es,ja" --skip-download --sub-format vtt \
  -o "{vault_root}/transcripts/{youtube_id}" "https://www.youtube.com/watch?v={youtube_id}"
```

**Non-YouTube talks** (InfoQ, conference platforms, etc.): `yt-dlp` supports many
sites beyond YouTube. When `video_url` is not a YouTube link:
1. Try `yt-dlp -f http_audio` to download audio (MP3/M4A)
2. Transcribe locally using MLX Whisper (Apple Silicon) or OpenAI Whisper:
   ```python
   import mlx_whisper
   result = mlx_whisper.transcribe(audio_path,
       path_or_hf_repo='mlx-community/whisper-large-v3-turbo',
       language='en')  # or 'ru', etc.
   ```
3. Save transcript text to `{vault_root}/transcripts/{talk_id}.txt`
4. Set `transcript_source: "whisper"` on the talk entry (vs `"youtube_auto"` for YouTube)

This enables ingestion from InfoQ, Vimeo, conference-hosted video, or any source
yt-dlp supports. Falls back to `processed_partial` (slides only) if audio extraction fails.

**Slide acquisition** per `slide_source` (see hierarchy above):
- **`pptx`/`both`**: Run `references/pptx-extraction.md` script. Store in `structured_data.pptx_visual`.
- **`pdf`**: Download via gdown or use locally provided PDF.
- **`video_extracted`**: Run `references/video-slide-extraction.md` pipeline (download
  720p video → ffmpeg frames → auto-detect slide region → perceptual dedup → PDF).
  Delete video after extraction; keep only the PDF. Analyze like any other slide PDF.
- **`none`**: Transcript-only analysis, `processed_partial`.

**B. Analyze for Rhetoric & Style (NOT content).** Apply all 14 dimensions
(including dimension 14: Areas for Improvement).

**Language policy — the vault is English-only.** All analysis output, rhetoric summary
updates, tracking DB entries, and profile data MUST be written in English regardless
of the talk's delivery language. For non-English talks:
- **Verbatim quotes**: ALWAYS write English translation FIRST, then the original in
  parentheses. Never the reverse. Format: `"English text" (оригинальный текст)`.
  Example: `"That's the whole point" (В этом весь смысл)` — NOT
  `"В этом весь смысл" (That's the whole point)`
- **Verbal signatures**: store separately tagged with language code (e.g.,
  `[ru] "получается что"`) — do NOT merge into the main English signature list
- **Slide text**: translate in the analysis, note original language
- **Humor/wordplay**: note when a joke is language-dependent and untranslatable
- Tag the talk entry with `delivery_language` in the tracking DB

**B2. Tag Presentation Patterns.** Scan observations against the pattern taxonomy
index at `skills/presentation-creator/references/patterns/_index.md` (path relative
to tile root). Skip patterns marked `observable: false` — these are pre-event logistics
and physical stage behaviors that cannot be detected from transcripts or slides. For each
observable pattern/antipattern, determine if the talk exhibits it (strong/moderate/weak
confidence), record evidence, and compute per-talk pattern score:
count(patterns) - count(antipatterns). Return in the `pattern_observations` field.

**C. Return JSON** per the subagent return schema (see `references/schemas.md`).

### Step 3B: Extract Remaining PPTX Visual Data

Process PPTX files **not** already extracted during Step 3: unmatched catalog entries,
talks that used PDF as primary source but have a PPTX available, or any entry with
`pptx_visual_status: "pending"`. Skip if already `"extracted"`.

**After extraction:** Store in `structured_data.pptx_visual`, set status to
`"extracted"`. After 3+ extractions, fill `slide-design-spec.md`; after 5+, analyze
cross-talk patterns (colors, fonts, footers).

### Step 4: Collect Results & Update

After each batch:

1. **Update tracking DB** — set `status`, `processed_date`, all result fields.
   Backfill empty `structured_data` from earlier runs using `rhetoric_notes`.
   Persist `pattern_observations` IDs + score to each talk entry.
   **Structured field extraction:** When the analysis identifies co-presenters,
   delivery language, or other structured metadata, populate the corresponding
   DB fields (`co_presenter`, `delivery_language`, etc.) — do NOT leave
   structured data buried only in `rhetoric_notes` free text.
2. **Write per-talk analysis files** — for each processed talk, write a standalone
   analysis file to `{vault_root}/analyses/{talk_filename}.md` containing the full
   rhetoric analysis (all 14 dimensions, structured data, verbatim examples, and
   a "Presentation Patterns Scoring" section listing detected patterns/antipatterns
   with confidence levels, evidence, and the per-talk pattern score).
   These files are read by the presentation-creator when adapting existing talks.
   Create the `analyses/` directory if it doesn't exist.
3. **Update rhetoric-style-summary.md** — integrate `new_patterns` and `summary_updates`.
   Be additive; never delete. Sections 1-14 map to the 14 rhetoric dimensions; Section 15
   aggregates areas for improvement; Section 16 captures speaker-confirmed intent.
   **Recount status from DB every time.** The summary's `## Status` block must be
   rewritten by counting the tracking DB — never increment manually, never trust the
   existing status line. Count: total talks, processed, skipped (by reason), languages,
   co-presenters. The DB is the source of truth; the summary is a derived view.
4. **Report:** talks processed, new patterns, current state, skipped talks.
5. **Auto-regenerate speaker profile** (Step 6) if it already exists. Report the diff.
6. Flag **structural changes** prominently (new presentation mode, new workflow pattern).

### Error Handling

| Transcript | Slides (PPTX/PDF) | Video | Status | Action |
|-----------|-------------------|-------|--------|--------|
| OK | OK | — | `processed` | Full analysis (best quality) |
| OK | FAIL | OK | `processed` | Extract slides from video, then full analysis |
| OK | FAIL | FAIL | `processed_partial` | Transcript only (no visual analysis) |
| FAIL | OK | — | `processed_partial` | Slides only |
| FAIL | FAIL | OK | `processed_partial` | Extract slides from video, visual only |
| FAIL | FAIL | FAIL | `skipped_download_failed` | Skip, move on |

### Step 5: Interactive Clarification Session

After all batches complete. Purpose: resolve ambiguities, validate findings, capture intent.

**5A. Rhetoric Clarification:** For each surprising, contradictory, or ambiguous observation from this run, ask one topic at a time via `AskUserQuestion`:
- **Intentional vs accidental**: "Was X pattern deliberate?"
- **Context you can't see**: "Talk X had different energy — what was happening?"
- **Conflicting signals**: "Sometimes you do X, sometimes Y — what drives the choice?"
- **Improvement areas**: "I flagged X — do you agree?"

Update the summary and tracking DB after each answer.

**5A-bis. Blind Spot Moments:** The skill can only analyze transcripts (speech) and
slides (visuals). It CANNOT observe audience reactions, physical performance, stage
movement, costume/prop moments, room energy, or laughter/applause. During analysis,
flag moments where the transcript or slides suggest something happened that the skill
cannot measure — then ask the speaker about each one. Examples:
- **Costume/prop moments**: Slides show a theatrical transition but transcript has no
  audience reaction — "The BTTF transition slide suggests a costume change. How did the
  audience react?"
- **Physical comedy/stage business**: Transcript shows a pause or laughter cue but no
  verbal content — "There's a gap here. Were you doing something physical on stage?"
- **Audience energy shifts**: Show-of-hands results are mentioned but enthusiasm level
  is invisible — "You asked for a show of hands on TDD. Was it enthusiastic or reluctant?"
- **Demo reactions**: Live demos create visible reactions not captured in speech —
  "The demo section has minimal dialogue. Was the audience engaged or checking phones?"
- **Room context**: Packed/empty, post-lunch slot, competing sessions, technical failures —
  "Anything about the room or timing that affected delivery?"

These blind spots are inherent to transcript+slides analysis. Asking about them captures
data that no amount of parsing can recover. Store responses as `blind_spot_observations`
in the talk's tracking DB entry and integrate into the rhetoric summary.

**5A-ter. Humor Post-Mortem:** The skill can identify jokes from transcripts and
slides but CANNOT hear laughter. For every talk processed in this run, compile the
humor beats detected in dimension 3 and walk through them with the speaker:

1. **List every joke/humor beat** identified in the analysis (verbatim quote or slide
   reference). For each one, ask: "Did this land? Big laugh, knowing nods, or flat?"
2. **Meme slides**: For meme-only or meme-with-text slides, ask if the audience
   visibly reacted or if the meme was more of a visual punchline the speaker talked over.
3. **Spontaneous humor**: Ask if there were jokes NOT on the slides that happened
   in the moment — audience riffs, improvised callbacks, heckler interactions, recovery
   humor from demo failures. These are invisible to the skill but often the best material.
4. **Humor grading**: For each confirmed-landed joke, tag it in the DB with
   `humor_grade: "hit"|"nod"|"flat"|"spontaneous_hit"`. Over time this builds a
   corpus-wide humor effectiveness map — which joke TYPES land (self-deprecating,
   industry snark, meme-as-punchline, callback) and which fall flat.
5. **Promote to portfolio**: If a spontaneous joke landed well, ask the speaker if
   it should be promoted to a planned beat in future deliveries (like the therapy
   analogy from QCon London 2026).

This is particularly important for recent talks where memory is fresh. For older talks
(2+ years), compress to: "Any jokes you remember landing particularly well or badly?"

Store results in `humor_postmortem` on the talk's DB entry and update the rhetoric
summary Section 3 (Humor & Wit) with confirmed effectiveness data.

**5B. Speaker Infrastructure** (first session only): Ask for any empty config fields
(`speaker_name` through `publishing_process.*`). See `references/schemas.md` for the full field list.

**5C. Structured Intent Capture:** Compile confirmed intents from 5A into structured entries and store in `confirmed_intents` array in the tracking DB:
```json
{"pattern": "delayed_self_introduction", "intent": "deliberate",
 "rule": "Two-phase intro: brief bio slide 3, full re-intro mid-talk",
 "note": "Confirmed intentional rhetorical device"}
```

**5D. Mark session complete:** Increment `config.clarification_sessions_completed` in
the tracking DB. This counter gates profile generation (Step 6).

### Step 6: Generate / Update Speaker Profile

**When:** 10+ talks parsed AND `config.clarification_sessions_completed >= 1`. Also on explicit request.

**Process:**
1. Read `rhetoric-style-summary.md`, `slide-design-spec.md`, and `confirmed_intents`.
2. Aggregate `structured_data` from processed talks (skip empty entries, fall back to prose).
3. If `template_pptx_path` is set, extract layouts via python-pptx:
   ```python
   from pptx import Presentation
   prs = Presentation(template_path)
   for i, layout in enumerate(prs.slide_layouts):
       print(f"{i}: {layout.name} — {[p.placeholder_format.type for p in layout.placeholders]}")
   ```
4. Generate `speaker-profile.json` per `references/speaker-profile-schema.md`. Map config →
   `speaker`/`infrastructure`, summary sections → `instrument_catalog`/`presentation_modes`,
   confirmed intents → `rhetoric_defaults`, aggregated data → `pacing`/`guardrail_sources`,
   pattern observations → `pattern_profile`.
5. **Diff against existing profile** and report changes (new instruments, revised thresholds,
   new guardrails, structural changes). Flag new presentation modes prominently.
6. Save to `{vault_root}/speaker-profile.json`.
7. **Generate speaker badges** — fun, self-deprecating achievements grounded in real
   vault data (e.g., "Narrative Arc Master 22/24", "Pattern Polyglot 12+ patterns").
   Mine both general stats and `pattern_profile` data. Personalize to THIS speaker.

**Auto-trigger:** Step 4 calls this after every vault update (if profile exists).

### Important Notes

- Create `transcripts/`, `slides/`, `analyses/` dirs if missing.
- Re-read tracking DB before writing (single source of truth).
- Preserve all summary content — add/refine, never delete.
- After 10+ talks, start providing adherence assessments.

### Known Pitfalls

**Wide-angle room recordings defeat perceptual hash dedup.** When the camera captures
the full stage (speaker moving + slides projected on a screen behind them), every frame
looks different because speaker position changes. The pipeline produces 800-1500
"unique" frames instead of 40-80 actual slides. Mitigation options:
1. Increase `hash_threshold` to 14-16 (loose dedup tolerates speaker movement)
2. Manually specify `slide_region` crop coordinates to isolate the projected screen
3. Accept the bloated PDF — the analysis subagent should visually SAMPLE representative
   frames at intervals rather than reading every page of a 1000+ page PDF

The pipeline works best for recordings that show slides fullscreen (Devoxx, JFokus,
most modern conference recordings). Wide-angle audience-camera recordings from meetups
and DevOpsDays are the worst case.

**Whisper hallucination on bad audio.** When conference recordings have poor audio
(distant mics, room echo, music tags), Whisper large-v3-turbo recovers ~60% of speech
but hallucinates through silent/noisy sections — generating plausible-sounding but
fabricated text. Always:
1. Set `transcript_source: "whisper"` so the analysis knows the source
2. Cross-reference Whisper output against visible slide text to catch hallucination
3. Note quality issues in the talk's DB entry (e.g., `transcript_quality: "partial"`)

**Non-speaker talks slip into playlists.** Conference playlists include ALL speakers,
not just the vault's target speaker. The subagent should verify speaker identity early
in analysis — check video frames for the expected speaker, check transcript for
self-identification. Flag `is_baruch_talk: false` and set status to `skipped` if the
speaker doesn't match.

**Step 5 timing matters.** Run the full clarification session (especially the humor
post-mortem and blind spot moments) IMMEDIATELY for talks delivered within the past
week. Memory is freshest right after delivery — room energy, audience reactions, and
spontaneous moments fade fast. For older talks (2+ years), use the compressed version:
"Any jokes you remember landing well or badly? Anything about the room context?"
