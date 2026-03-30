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
| `rhetoric-style-summary.md` | Running rhetoric & style narrative |
| `slide-design-spec.md` | Visual design rules from PDF + PPTX analysis |
| `speaker-profile.json` | Machine-readable bridge to presentation-creator |
| `sessions-catalog.md` | Submission-ready titles, abstracts, and outlines for active talks |
| `analyses/{talk_filename}.md` | Per-talk rhetoric analysis (one file per processed talk) |
| `transcripts/{youtube_id}.txt` | Downloaded/cleaned transcripts |
| `slides/{id}.pdf` | Slide PDFs (from Google Drive, PPTX export, or video extraction) |
| `references/schemas.md` | DB + subagent schemas; full config field list |
| `references/rhetoric-dimensions.md` | 14 analysis dimensions |
| `references/pptx-extraction.md` | Visual extraction script |
| `references/speaker-profile-schema.md` | Profile JSON schema |
| `references/download-commands.md` | yt-dlp + gdown commands |
| `references/video-slide-extraction.md` | Extract slides from video when no PDF/PPTX exists |
| `references/blind-spot-moments.md` | Protocol for capturing audience/room data invisible to transcripts |
| `references/humor-post-mortem.md` | Protocol for grading humor effectiveness with speaker |
| `references/known-pitfalls.md` | Common failure modes and mitigations |
| `references/processing-rules.md` | Language policy, pattern migration logic, structured field rules |

A talk is processable when it has `video_url`. Slide sources, in order of preference:
1. `pptx_path` → richest data (exact colors, fonts, shapes via python-pptx)
2. `slides_url` → download PDF from Google Drive
3. `video_url` → extract slides from the video using ffmpeg + perceptual dedup
4. none → transcript-only analysis (`processed_partial`)

The `slide_source` field tracks which path: `"pptx"`, `"pdf"`, `"both"`,
`"video_extracted"`, or `"none"`. The `pptx_catalog` array fuzzy-matches `.pptx`
files to shownotes entries.

## Workflow

### Step 1: Load State & Sync Sources

**Vault discovery** — canonical path is always `~/.claude/rhetoric-knowledge-vault/`.

1. **Path exists** → use as `vault_root`, read `tracking-database.json`.
2. **Path missing** → first-time setup: ask preferred location via `AskUserQuestion`,
   create directory (and symlink if custom path chosen), initialize empty
   `tracking-database.json` with empty `config`, `talks`, `pptx_catalog`.

**Config bootstrapping** — ask once per missing field and persist to the tracking
database. Core fields: `talks_source_dir`, `pptx_source_dir`, `python_path`,
`template_skip_patterns`. See `references/schemas.md` for the full field list.

**Scan for new talks:** Glob `*.md` in `talks_source_dir`; parse and add any file not
yet in `talks[]` (title, conference, date, URLs, status `"pending"`).

**Scan for .pptx files:** Glob `**/*.pptx` in `pptx_source_dir`; fuzzy-match to
`talks[]` entries. Report counts.

**Pattern taxonomy migration:** See `references/processing-rules.md` for migration
logic. In brief: talks with `status` `"processed"` or `"processed_partial"` that
lack `pattern_observations` are marked `"needs-reprocessing"`.

Read `rhetoric-style-summary.md` and `slide-design-spec.md`. Report:
"X processed, Y remaining. PPTX: A cataloged, B matched, C extracted."

### Step 2: Select Talks to Process

- Select talks with status `pending` or `needs-reprocessing`.
- Set `slide_source` per the hierarchy above. Mark `"skipped_no_sources"` only if
  `video_url` is entirely absent.
- If `$ARGUMENTS` specifies a talk filename or title, process ONLY that one.

### Step 3: Process Talks — Parallel Subagents, Batches of 5

Per batch: launch 5 subagents in parallel, wait, run Step 4, then next batch.
Each subagent receives the talk's DB entry and current `rhetoric-style-summary.md`.

#### Per-Talk Subagent Instructions:

**A. Download transcript and acquire slides.**

- **YouTube talks:** use yt-dlp with auto-subtitles across likely languages. Example:
  ```bash
  yt-dlp --write-auto-sub --skip-download \
    --sub-langs "en,es,fr,de,pt" \
    -o "transcripts/%(id)s.%(ext)s" <video_url>
  ```
  See `references/download-commands.md` for additional options and post-processing.
- **Non-YouTube talks** (InfoQ, Vimeo, conference platforms): attempt audio download
  via yt-dlp, then transcribe locally with MLX Whisper or OpenAI Whisper. Set
  `transcript_source: "whisper"`. Falls back to `processed_partial` if audio fails.
  See `references/download-commands.md` for commands.
- **Slide acquisition** per `slide_source`:
  - `pptx`/`both`: run script in `references/pptx-extraction.md`.
  - `pdf`: download via gdown or use locally provided PDF.
  - `video_extracted`: run pipeline in `references/video-slide-extraction.md`
    (download 720p → ffmpeg frames → perceptual dedup → PDF). Delete video after.
  - `none`: transcript-only, `processed_partial`.

**B. Analyze for Rhetoric & Style (NOT content).** Apply all 14 dimensions from
`references/rhetoric-dimensions.md` (including dimension 14: Areas for Improvement).
Follow language policy and verbatim-quote rules in `references/processing-rules.md`.

**B2. Tag Presentation Patterns.** Scan observations against the pattern taxonomy
at `skills/presentation-creator/references/patterns/_index.md`. Skip patterns
marked `observable: false`. Record confidence (strong/moderate/weak) and evidence per
pattern. Compute per-talk score: count(patterns) − count(antipatterns). Store in
`pattern_observations`. See `references/processing-rules.md` for full tagging rules.

**C. Return JSON** per the subagent return schema in `references/schemas.md`.
Minimal structure:
```json
{
  "talk_id": "...",
  "status": "processed",
  "transcript_source": "youtube",
  "slide_source": "pdf",
  "pattern_observations": [
    {"pattern_id": "...", "confidence": "strong", "evidence": "..."}
  ],
  "new_patterns": ["..."],
  "summary_updates": [{"section": 1, "content": "..."}],
  "structured_data": {"delivery_language": "en", "co_presenter": false}
}
```

### Step 3B: Extract Remaining PPTX Visual Data

Process PPTX files not yet extracted during Step 3: unmatched catalog entries, talks
that used PDF as primary but have a PPTX available, or entries with
`pptx_visual_status: "pending"`. Skip if already `"extracted"`.

After 3+ extractions, populate `slide-design-spec.md`; after 5+, analyze cross-talk
patterns (colors, fonts, footers).

### Step 4: Collect Results & Update

After each batch:

1. **Update tracking DB** — set `status`, `processed_date`, all result fields.
   Persist `pattern_observations` IDs + score. Populate structured fields
   (`co_presenter`, `delivery_language`, etc.) — do not leave structured data buried
   in free-text prose. See `references/processing-rules.md` for field extraction rules.
2. **Write per-talk analysis files** — write
   `{vault_root}/analyses/{talk_filename}.md` for each processed talk: all 14
   dimensions, structured data, verbatim examples, and a "Presentation Patterns
   Scoring" section. Create `analyses/` directory if missing.
3. **Update rhetoric-style-summary.md** — integrate `new_patterns` and
   `summary_updates`. Sections 1–14 map to the 14 dimensions; Section 15 aggregates
   improvement areas; Section 16 captures speaker-confirmed intent. **Recount status
   from the DB every time** — never increment manually.
4. **Report:** talks processed, new patterns, current state, skipped talks.
5. **Auto-regenerate speaker profile** (Step 6) if it already exists. Report the diff.
6. Flag **structural changes** prominently (new presentation mode, new workflow pattern).

### Error Handling

| Transcript | Slides (PPTX/PDF) | Video | Status | Action |
|-----------|-------------------|-------|--------|--------|
| OK | OK | — | `processed` | Full analysis |
| OK | FAIL | OK | `processed` | Extract slides from video, then full analysis |
| OK | FAIL | FAIL | `processed_partial` | Transcript only (no visual analysis) |
| FAIL | OK | — | `processed_partial` | Slides only |
| FAIL | FAIL | OK | `processed_partial` | Extract slides from video, visual only |
| FAIL | FAIL | FAIL | `skipped_download_failed` | Skip, move on |

### Step 5: Interactive Clarification Session

After all batches complete. Purpose: resolve ambiguities, validate findings, capture intent.

**5A. Rhetoric Clarification:** For each surprising, contradictory, or ambiguous
observation ask one topic at a time via `AskUserQuestion`:
intentional vs accidental patterns, invisible context, conflicting signals, and
flagged improvement areas. Update summary and DB after each answer.

**5A-bis. Blind Spot Moments:** Follow `references/blind-spot-moments.md` — ask about
audience reactions, physical performance, and room context transcripts cannot capture.

**5A-ter. Humor Post-Mortem:** Follow `references/humor-post-mortem.md` — walk through
detected humor beats, grade effectiveness, capture spontaneous material.

**5B. Speaker Infrastructure** (first session only): ask for any empty config fields
(`speaker_name` through `publishing_process.*`). See `references/schemas.md`.

**5C. Structured Intent Capture:** Store confirmed intents in the `confirmed_intents`
array of the tracking DB. Schema: `{"pattern", "intent", "rule", "note"}`.
See `references/schemas.md` for the full schema.

**5D. Mark session complete:** Increment `config.clarification_sessions_completed` in
the tracking DB. This counter gates profile generation (Step 6).

### Step 6: Generate / Update Speaker Profile

**When:** 10+ talks parsed AND `config.clarification_sessions_completed >= 1`.
Also on explicit request.

**Process:**
1. Read `rhetoric-style-summary.md`, `slide-design-spec.md`, and `confirmed_intents`.
2. Aggregate `structured_data` from processed talks (skip empty, fall back to prose).
3. If `template_pptx_path` is set, extract slide layouts via python-pptx.
   See `references/pptx-extraction.md` for the script.
4. Generate `speaker-profile.json` per `references/speaker-profile-schema.md`.
   Map config → `speaker`/`infrastructure`, summary sections →
   `instrument_catalog`/`presentation_modes`, confirmed intents →
   `rhetoric_defaults`, aggregated data → `pacing`/`guardrail_sources`,
   pattern observations → `pattern_profile`.
5. Diff against existing profile; report changes (new instruments, revised thresholds,
   new guardrails). Flag new presentation modes prominently.
6. Save to `{vault_root}/speaker-profile.json`.
7. **Generate speaker badges** — fun, self-deprecating achievements grounded in real
   vault data (e.g., "Narrative Arc Master 22/24", "Pattern Polyglot 12+ patterns").

**Auto-trigger:** Step 4 calls this after every vault update (if profile exists).

### Important Notes

- Create `transcripts/`, `slides/`, `analyses/` dirs if missing.
- Re-read tracking DB before writing (single source of truth).
- Preserve all summary content — add/refine, never delete.
- After 10+ talks, start providing adherence assessments.
- See `references/known-pitfalls.md` for wide-angle recording dedup issues, Whisper
  hallucination handling, non-speaker talk detection, and Step 5 timing guidance.
