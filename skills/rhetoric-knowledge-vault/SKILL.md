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
running summary. All paths are relative to **vault root** (`config.vault_root`).

## Key Files & References

| File / Reference | Purpose |
|------------------|---------|
| `tracking-database.json` | Source of truth — talks, status, config, confirmed intents |
| `rhetoric-style-summary.md` | Running rhetoric & style narrative (the constitution) |
| `slide-design-spec.md` | Visual design rules from PDF + PPTX analysis |
| `speaker-profile.json` | Machine-readable bridge to presentation-creator |
| `analyses/{talk_filename}.md` | Per-talk rhetoric analysis (one file per processed talk) |
| `transcripts/{youtube_id}.txt` | Downloaded/cleaned transcripts |
| `slides/{google_drive_id}.pdf` | Downloaded slide PDFs |
| `references/schemas.md` | DB + subagent schemas; full config field list |
| `references/rhetoric-dimensions.md` | 14 analysis dimensions |
| `references/pptx-extraction.md` | Visual extraction script |
| `references/speaker-profile-schema.md` | Profile JSON schema |
| `references/download-commands.md` | yt-dlp + gdown commands |

A talk is processable when it has `video_url` AND at least one of `slides_url` or
`pptx_path`. The `slide_source` field tracks which path applies: `"pptx"` (preferred —
richer data), `"pdf"`, or `"both"`. The `pptx_catalog` array fuzzy-matches `.pptx`
files to shownotes entries.

## Workflow

### Step 1: Load State & Sync Sources

Read `tracking-database.json` (create with empty `config`, `talks`, `pptx_catalog` if missing).

**Config bootstrapping** — ask once per missing field and persist to the tracking database.
Core fields: `vault_root`, `talks_source_dir`, `pptx_source_dir`, `python_path`
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

- Select talks with status `pending` or `needs-reprocessing`. Set `slide_source` per above.
- Mark `"skipped_no_sources"` if missing `video_url` or missing both slide sources.
- If `$ARGUMENTS` specifies a talk filename or title, process ONLY that one.

### Step 3: Process Talks — Parallel Subagents, Batches of 5

Per batch: launch 5 subagents in parallel, wait, run Step 4, then next batch.
Each subagent receives the talk's DB entry and current `rhetoric-style-summary.md`.

#### Per-Talk Subagent Instructions:

**A. Download transcript and acquire slides:**

```bash
yt-dlp --write-auto-sub --sub-lang en --skip-download --sub-format vtt \
  -o "{vault_root}/transcripts/{youtube_id}" "https://www.youtube.com/watch?v={youtube_id}"
```

**Slide acquisition** per `slide_source`: if PPTX available, run the extraction script
(store in `structured_data.pptx_visual`); if PDF only, download via gdown.

**B. Analyze for Rhetoric & Style (NOT content).** Apply all 14 dimensions
(including dimension 14: Areas for Improvement).

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
4. **Report:** talks processed, new patterns, current state, skipped talks.
5. **Auto-regenerate speaker profile** (Step 6) if it already exists. Report the diff.
6. Flag **structural changes** prominently (new presentation mode, new workflow pattern).

### Error Handling

| Transcript | Slides | Status | Action |
|-----------|--------|--------|--------|
| OK | OK | `processed` | Full analysis |
| FAIL | OK | `processed_partial` | Slides only |
| OK | FAIL | `processed_partial` | Transcript only |
| FAIL | FAIL | `skipped_download_failed` | Skip, move on |

### Step 5: Interactive Clarification Session

After all batches complete. Purpose: resolve ambiguities, validate findings, capture intent.

**5A. Rhetoric Clarification:** For each surprising, contradictory, or ambiguous observation from this run, ask one topic at a time via `AskUserQuestion`:
- **Intentional vs accidental**: "Was X pattern deliberate?"
- **Context you can't see**: "Talk X had different energy — what was happening?"
- **Conflicting signals**: "Sometimes you do X, sometimes Y — what drives the choice?"
- **Improvement areas**: "I flagged X — do you agree?"

Update the summary and tracking DB after each answer.

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
