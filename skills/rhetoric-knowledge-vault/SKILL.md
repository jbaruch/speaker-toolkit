---
name: rhetoric-knowledge-vault
description: >
  This skill parses presentation talks to catalog specific rhetoric patterns: opening hooks,
  humor style, pacing, transitions, audience interaction, slide design, and verbal signatures.
  It downloads YouTube transcripts and Google Drive slide PDFs, analyzing HOW the speaker
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

## Key Files

| File | Purpose |
|------|---------|
| `tracking-database.json` | Source of truth — talks, status, config, confirmed intents |
| `rhetoric-style-summary.md` | Running rhetoric & style narrative (the constitution) |
| `slide-design-spec.md` | Visual design rules from PDF + PPTX analysis |
| `speaker-profile.json` | Machine-readable bridge to presentation-creator |
| `transcripts/{youtube_id}.txt` | Downloaded/cleaned transcripts |
| `slides/{google_drive_id}.pdf` | Downloaded slide PDFs |

For full database, subagent return, and PPTX extraction schemas, see `references/schemas.md`.

The vault has **two independent data sources**: shownotes (`.md` files with video/slide
links → rhetoric analysis) and PPTX sources (`.pptx` files → visual design extraction).
Most talks appear in both; disparity is expected. The `pptx_catalog` array tracks all
`.pptx` files and fuzzy-matches them to shownotes entries.

## Workflow

### Step 1: Load State & Sync Sources

Read `tracking-database.json` (create with empty `config`, `talks`, `pptx_catalog` if missing).

**Config bootstrapping** — ask once per field, persist in the tracking database:

| Config field | Question | Auto-detect |
|-------------|----------|-------------|
| `vault_root` | "Where should the vault live?" | — |
| `talks_source_dir` | "Where are your talk shownotes (.md files)?" | — |
| `pptx_source_dir` | "Where are your .pptx presentation files?" | — |
| `python_path` | "Path to Python 3 with gdown, youtube-transcript-api, python-pptx?" | `{vault_root}/.venv/bin/python3`, then `python3` on PATH |
| `template_skip_patterns` | — | Default: `["template"]` |

**Scan for new talks:** Glob `*.md` in `talks_source_dir`. For each file not in the
`talks` array, parse and add (extract title, conference, date, URLs, IDs, status `"pending"`).

**Scan for .pptx files:** Glob `**/*.pptx` in `pptx_source_dir`. Skip files named
`*static*`, `*(N).pptx` (conflict copies), or matching `template_skip_patterns`.
Fuzzy-match each to a `talks[]` entry by conference + title. Report counts.

Read `rhetoric-style-summary.md` and `slide-design-spec.md`. Report state:
"X processed, Y remaining. PPTX: A cataloged, B matched, C extracted."

### Step 2: Select Talks to Process

- Select all talks with status `pending` or `needs-reprocessing`.
- Talks missing `video_url` or `slides_url`: mark `"skipped_no_sources"`, skip.
- If `$ARGUMENTS` specifies a talk filename or title, process ONLY that one.

### Step 3: Process Talks — Parallel Subagents, Batches of 5

Per batch: launch 5 subagents in parallel, wait, run Step 4, then next batch.
Each subagent receives the talk's DB entry and current `rhetoric-style-summary.md`.

#### Per-Talk Subagent Instructions:

**A. Download transcript and slides:**

```bash
yt-dlp --write-auto-sub --sub-lang en --skip-download --sub-format vtt \
  -o "{vault_root}/transcripts/{youtube_id}" "https://www.youtube.com/watch?v={youtube_id}"
```
```bash
"{python_path}" -m gdown "https://drive.google.com/uc?id={google_drive_id}" \
  -O "{vault_root}/slides/{google_drive_id}.pdf"
```

For VTT cleanup and fallback commands, see `references/download-commands.md`.

**B. Analyze for Rhetoric & Style (NOT content).** Apply all 14 dimensions from
`references/rhetoric-dimensions.md` (including dimension 14: Areas for Improvement).

**C. Return JSON** per the subagent return schema in `references/schemas.md`.

### Step 3B: Extract Visual Design Data from PPTX Files

Process .pptx files with `pptx_visual_status: "pending"` or `visual_extracted: false`.
Uses `python-pptx` for exact design values. See `references/pptx-extraction.md` for the
extraction script. Output schema in `references/schemas.md`.

**After extraction:**
1. Store results in `structured_data.pptx_visual` on matching talk (or `pptx_catalog` entry)
2. Set `pptx_visual_status: "extracted"`, `visual_extracted: true`
3. After 3+ extractions: fill confirmed values in `slide-design-spec.md`
4. After 5+ extractions: analyze cross-talk patterns (color sequences, fonts, footer consistency, shape frequency)
5. Update `rhetoric-style-summary.md` Section 5 with confirmed specs

### Step 4: Collect Results & Update

After each batch:

1. **Update tracking DB** — set `status`, `processed_date`, all result fields.
   Backfill empty `structured_data` from earlier runs using `rhetoric_notes`.
2. **Update rhetoric-style-summary.md** — integrate `new_patterns` and `summary_updates`.
   Be additive; refine and consolidate but never delete. Maintain these sections:
   - Section 1: Presentation modes (→ profile `presentation_modes`)
   - Sections 2-13: Instrument catalogs (→ profile `instrument_catalog`)
   - Section 15: Areas for improvement (→ profile `guardrail_sources.recurring_issues`)
   - Section 16: Speaker-confirmed intent (→ profile `confirmed_intents` + `rhetoric_defaults`)
3. **Report:** talks processed, new patterns, current state, skipped talks.
4. **Auto-regenerate speaker profile** (Step 6) if it already exists. Report the diff.
5. Flag **structural changes** prominently (new presentation mode, new workflow pattern).

### Error Handling

| Transcript | Slides | Status | Action |
|-----------|--------|--------|--------|
| OK | OK | `processed` | Full analysis |
| FAIL | OK | `processed_partial` | Slides only |
| OK | FAIL | `processed_partial` | Transcript only |
| FAIL | FAIL | `skipped_download_failed` | Skip, move on |

### Step 5: Interactive Clarification Session

After all batches complete. Purpose: resolve ambiguities, validate findings, capture intent.

**5A. Rhetoric Clarification:**
Review all results from this run. Compile observations that are surprising, contradictory,
or ambiguous. Ask one topic at a time via `AskUserQuestion`:
- **Intentional vs accidental**: "Was X pattern deliberate?"
- **Context you can't see**: "Talk X had different energy — what was happening?"
- **Conflicting signals**: "Sometimes you do X, sometimes Y — what drives the choice?"
- **Improvement areas**: "I flagged X — do you agree?"
Update the summary and tracking DB after each answer.

**5B. Speaker Infrastructure** (first session only — ask for empty config fields):

| Config field | Question |
|-------------|----------|
| `speaker_name` | "Name as it appears on slides?" |
| `speaker_handle` | "Social handle for footers?" |
| `speaker_website` | "Website for talk resources?" |
| `shownotes_url_pattern` | "URL pattern for talk pages? (e.g., `speaking.example.com/{slug}`)" |
| `template_pptx_path` | "PowerPoint template path?" |
| `presentation_file_convention` | "File organization? (default: `{conference}/{year}/{talk-slug}/`)" |
| `publishing_process` | "Export method? Shownotes publishing? QR codes? Other distribution steps?" |

**5C. Structured Intent Capture:**
Compile confirmed intents from 5A into structured entries:
```json
{"pattern": "delayed_self_introduction", "intent": "deliberate",
 "rule": "Two-phase intro: brief bio slide 3, full re-intro mid-talk",
 "note": "Confirmed intentional rhetorical device"}
```
Store in tracking DB `confirmed_intents` array. These feed directly into the profile.

### Step 6: Generate / Update Speaker Profile

**When:** 10+ talks parsed AND one clarification session completed. Also on explicit request.

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
4. Generate `speaker-profile.json` per `references/speaker-profile-schema.md`:
   - `speaker` ← config fields
   - `infrastructure` ← config + template layouts
   - `presentation_modes` ← summary Section 1 + aggregated structured_data
   - `design_rules` ← slide-design-spec.md confirmed rules
   - `rhetoric_defaults` ← confirmed intents + summary Section 16
   - `confirmed_intents` ← tracking DB array
   - `pacing` ← aggregated duration/slide data (or summary prose)
   - `guardrail_sources` ← pacing data + summary Section 15 recurring issues
   - `instrument_catalog` ← summary Sections 2-13 (each pattern → structured entry)
   - `publishing_process` ← config publishing_process (empty object + flag if not captured)
5. **Diff against existing profile** and report changes (new instruments, revised thresholds,
   new guardrails, structural changes). Flag new presentation modes prominently.
6. Save to `{vault_root}/speaker-profile.json`.

**Auto-trigger:** Step 4 calls this after every vault update (if profile exists).

### Important Notes

- Create `transcripts/` and `slides/` dirs if missing before downloading.
- Re-read tracking DB before writing (single source of truth).
- Preserve all summary content — add/refine, never delete.
- After 10+ talks, start providing adherence assessments.
- PPTX extraction (Step 3B) can run independently of rhetoric analysis.
- PPTX files named `*static*` or `*(N).pptx` are always skipped.
