---
name: vault-ingress
description: >
  Parses presentation talks to catalog rhetoric patterns: opening hooks, humor style,
  pacing, transitions, audience interaction, slide design, and verbal signatures.
  Downloads YouTube transcripts and analyzes slides (from PPTX, Google Drive PDFs, or
  video extraction), examining HOW the speaker presents. Processes talks in parallel
  batches and updates the running rhetoric summary.
  Triggers: "parse my talks", "run the rhetoric analyzer", "analyze my presentation style",
  "how many talks have been processed", "update the rhetoric knowledge base",
  "check rhetoric vault status", "process remaining talks for style patterns".
user_invocable: true
---

# Vault Ingress — Incremental Talk Parser

Process the steps below in order; each step's output (tracking DB state, batch results, per-talk artifacts) feeds the next. Do not skip ahead.

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
| `analyses/{talk_filename}.md` | Per-talk rhetoric analysis (one file per processed talk) |
| `transcripts/{youtube_id}.txt` | Downloaded/cleaned transcripts |
| `slides/{id}.pdf` | Slide PDFs (from Google Drive, PPTX export, or video extraction) |
| [references/schemas-db.md](references/schemas-db.md) | DB + subagent schemas; extraction output schemas |
| [references/rhetoric-dimensions.md](references/rhetoric-dimensions.md) | 14 analysis dimensions |
| [references/subagent-instructions.md](references/subagent-instructions.md) | Step 3 per-talk procedure — transcript download, slide acquisition, fallback chains, return-JSON shape |
| [references/video-slide-extraction.md](references/video-slide-extraction.md) | Video-to-slides pipeline — layout heuristics, tuning, limitations |
| [references/processing-rules.md](references/processing-rules.md) | Language policy, pattern migration logic, structured field rules |
| [references/known-issues.md](references/known-issues.md) | Edge cases — wide-angle recordings, Whisper hallucination, non-speaker talks |
| `scripts/pptx-extraction.py` | Extract visual design data from .pptx files |
| `scripts/video-slide-extraction.py` | Extract slides from video via ffmpeg + perceptual dedup |
| `scripts/batch-download-videos.sh` | Parallel video download for batch processing |
| `scripts/vtt-cleanup.py` | Clean VTT subtitles into plain transcript text |

A talk is processable when it has `video_url`. Slide sources, in order of preference:
1. `pptx_path` — richest data (exact colors, fonts, shapes via python-pptx)
2. `slides_url` — download PDF from Google Drive
3. `video_url` — extract slides from the video using ffmpeg + perceptual dedup
4. none — transcript-only analysis (`processed_partial`)

The `slide_source` field tracks which path: `"pptx"`, `"pdf"`, `"both"`,
`"video_extracted"`, or `"none"`. The `pptx_catalog` array fuzzy-matches `.pptx`
files to shownotes entries.

## Step 1 — Bootstrap Vault State

**Vault discovery** — canonical path is always `~/.claude/rhetoric-knowledge-vault/`.

1. **Path exists** — use as `vault_root`, read `tracking-database.json`.
2. **Path missing** — first-time setup: ask preferred location via `AskUserQuestion`,
   create directory (and symlink if custom path chosen), initialize empty
   `tracking-database.json` with empty `config`, `talks`, `pptx_catalog`.

**Config bootstrapping** — ask once per missing field and persist to the tracking
database. Core fields: `shownotes` (enabled, source.type, source.path_or_url,
source.talks_subdir, url.base, url.template, thumbnail_path_template,
slug_convention), `pptx_source_dir`, `python_path`, `template_skip_patterns`.
See [references/schemas-db.md](references/schemas-db.md) for the full schema
and [../vault-profile/references/schemas-config.md](../vault-profile/references/schemas-config.md)
for field-by-field semantics and migration notes.

**Scan for new talks:** Build the talks directory path as
`{shownotes.source.path_or_url}/{shownotes.source.talks_subdir}`; glob `*.md`
there; parse and add any file not yet in `talks[]` (title, conference, date,
URLs, status `"pending"`). For `remote_url` or `none` source types, skip the
scan — the vault ingests only the talks the speaker has already registered
elsewhere. Extract
`video_url`, `slides_url` from frontmatter/links. Parse IDs from URLs:
- `youtube_id`: extract the `v=` parameter from YouTube URLs
  (e.g., `https://www.youtube.com/watch?v=aBcDeFg` → `youtube_id: "aBcDeFg"`)
- `google_drive_id`: extract the file ID from Google Drive URLs
  (e.g., `https://drive.google.com/file/d/1AbCdEfGhIjK/view` → `google_drive_id: "1AbCdEfGhIjK"`)

Default status is always `"pending"` for new entries.

**Scan for .pptx files:** Recursively glob `**/*.pptx` in `pptx_source_dir`; fuzzy-match
to `talks[]` entries. Report counts. See [references/schemas-db.md](references/schemas-db.md)
for the PPTX extraction output schema (per-slide visual data, shape types, global design stats).
Run `scripts/pptx-extraction.py` for extraction.

**Pattern taxonomy migration:** See [references/processing-rules.md](references/processing-rules.md) for migration
logic. In brief: talks with `status` `"processed"` or `"processed_partial"` that
lack `pattern_observations` are marked `"needs-reprocessing"`.

Read `rhetoric-style-summary.md` and `slide-design-spec.md`. Report:
"X processed, Y remaining. PPTX: A cataloged, B matched, C extracted."

## Step 2 — Select Talks to Process

- Select talks with status `pending` or `needs-reprocessing`.
- Set `slide_source` per the hierarchy above. Mark `"skipped_no_sources"` only if
  `video_url` is entirely absent — a talk with no `video_url` is **not processable**
  regardless of whether slides exist.
- If `$ARGUMENTS` specifies a talk filename or title, process ONLY that one.

## Step 3 — Process Talks via Parallel Subagents (Batches of 5)

Per batch: launch 5 subagents in parallel, wait, run Step 4 (Persist Subagent
Results), then run Step 5 (Update Rhetoric Summary), then move to the next
batch. When all batches have finished, proceed to Step 6.

Each subagent receives the talk's DB entry and current
`rhetoric-style-summary.md`, runs A → B → B2 → C, and returns a JSON payload.
Full procedure — transcript download (YouTube auto-subs → youtube-transcript-api
→ Whisper fallback chain), slide acquisition per `slide_source`, rhetoric/style
analysis, pattern-taxonomy tagging, and the return-JSON shape — lives in
[references/subagent-instructions.md](references/subagent-instructions.md).

## Step 4 — Persist Subagent Results

Runs after each batch inside Step 3's loop (not as a separate post-loop
phase). Mechanical persistence of the batch's subagent JSON returns:

- **Update tracking DB** — set `status`, `processed_date`, all result fields.
  Persist `pattern_observations` IDs + score. Populate structured fields
  (`co_presenter`, `delivery_language`, etc.) — do not leave structured data
  buried in free-text prose. See
  [references/processing-rules.md](references/processing-rules.md) for field
  extraction rules.
- **Write per-talk analysis files** — write
  `{vault_root}/analyses/{talk_filename}.md` for each processed talk: all 14
  dimensions, structured data, verbatim examples, and a "Presentation Patterns
  Scoring" section. Create `analyses/` directory if missing.

Proceed immediately to Step 5.

## Step 5 — Update Rhetoric Summary

Still per-batch (continues Step 3's loop). The summary update is a separate
step from Step 4's persistence because it requires a speaker-review gate —
unlike DB writes, edits to `rhetoric-style-summary.md` change the speaker's
ground-truth narrative and must not be applied silently.

1. **Speaker-review gate.** Present the subagent's proposed `summary_updates`
   and `new_patterns` as a section-by-section diff and wait for explicit
   speaker confirmation. Silent application erodes the speaker's sense of
   ownership of their own style summary; pattern-taxonomy additions in
   particular drift if applied unreviewed. Only bypass the gate if the
   speaker pre-authorized this batch ("just apply everything, don't ask").
2. **Apply approved changes.** Integrate confirmed `new_patterns` and
   `summary_updates` into `rhetoric-style-summary.md`. Sections 1–14 map to
   the 14 dimensions; Section 15 aggregates improvement areas; Section 16
   captures speaker-confirmed intent. **Recount status from the DB every
   time** — never increment manually.
3. **Report.** Output: talks processed, new patterns, current state, skipped
   talks. Flag structural changes prominently (new presentation mode, new
   workflow pattern).

When Step 3's batch loop finishes, proceed to Step 6.

## Step 6 — Extract Remaining PPTX Visual Data

Runs once after all Step 3 batches have completed.

Process PPTX files not yet extracted during Step 3: unmatched catalog entries, talks
that used PDF as primary but have a PPTX available, or entries with
`pptx_visual_status: "pending"`. Skip if already `"extracted"`.
Run `scripts/pptx-extraction.py <path.pptx>` for each file.

**PPTX matching rules:** The .pptx files are in `Conference/Year/TalkName.pptx` and
shownotes entries have `conference` and `title` fields. Fuzzy-match by: normalize
conference names (strip year, "Days", "Conference"), match by date proximity and title
substring. Skip files with "static" in name, conflict copies matching `(N).pptx`, and
files matching `config.template_skip_patterns`. Some talks have multiple .pptx files
(one per delivery) — match to the closest date.

After 3+ extractions, populate `slide-design-spec.md`; after 5+, analyze cross-talk
patterns (colors, fonts, footers).

Proceed immediately to Step 7.

## Step 7 — Regenerate Speaker Profile

If `{vault_root}/speaker-profile.json` exists, invoke `Skill(skill: "vault-profile")`
with the updated tracking database. Report the diff of changes (added fields,
changed values) so the speaker can verify.

If the profile doesn't exist, skip this step silently.

Proceed immediately to Step 8.

## Step 8 — Same-Week Clarification Trigger

If no talks were newly processed in this run, finish here without further action.

Otherwise, scan the newly-processed talks for delivery date. For any talk whose
`date` is within the past 7 days, explicitly recommend running
`Skill(skill: "vault-clarification")` NOW — memory of the delivery is freshest
right after the talk, and verbal beats that didn't appear in auto-captions
(bilingual jokes rendered in a non-primary language, improvised asides, fly-bys
that weren't in the deck) need speaker confirmation while they're still
recoverable.

Surface these as candidate clarification topics in the recommendation:
- Each per-talk `areas_for_improvement` entry.
- Any `pattern_observations` the subagent flagged as **unverifiable from
  transcript alone** (low confidence, heavy reliance on visual cues, non-English
  dialogue without captions).

For older talks (30+ days), recommend the compressed clarification session
instead of the full one — memory has decayed and detailed recall is unreliable.
For talks in the 7–30 day window, recommend the full session but note that some
verbatim details may be lost.

## Error Handling

| Transcript | Slides (PPTX/PDF) | Video | Status | Action |
|-----------|-------------------|-------|--------|--------|
| OK | OK | — | `processed` | Full analysis |
| OK | FAIL | OK | `processed` | Extract slides from video, then full analysis |
| OK | FAIL | FAIL | `processed_partial` | Transcript only (no visual analysis) |
| FAIL | OK | — | `processed_partial` | Slides only |
| FAIL | FAIL | OK | `processed_partial` | Extract slides from video, visual only |
| FAIL | FAIL | FAIL | `skipped_download_failed` | Skip, move on |

## Important Notes

- Create `transcripts/`, `slides/`, `analyses/` dirs if missing.
- Re-read tracking DB before writing (single source of truth).
- Preserve all summary content — add/refine, never delete.
- After 10+ talks, start providing adherence assessments.

For input-quality edge cases that require non-default handling — wide-angle
room recordings, Whisper hallucination on bad audio, non-speaker talks
slipping into playlists — see
[references/known-issues.md](references/known-issues.md).
