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
| [references/video-slide-extraction.md](references/video-slide-extraction.md) | Video-to-slides pipeline — layout heuristics, tuning, limitations |
| [references/processing-rules.md](references/processing-rules.md) | Language policy, pattern migration logic, structured field rules |
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
database. Core fields: `talks_source_dir`, `pptx_source_dir`, `python_path`,
`template_skip_patterns`. See [references/schemas-db.md](references/schemas-db.md) for the full schema.

**Scan for new talks:** Glob `*.md` in `talks_source_dir`; parse and add any file not
yet in `talks[]` (title, conference, date, URLs, status `"pending"`). Extract
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

Per batch: launch 5 subagents in parallel, wait, run Step 4 (Apply Subagent Results), then next batch. When all batches have finished, proceed to Step 5.
Each subagent receives the talk's DB entry and current `rhetoric-style-summary.md`.

#### Per-Talk Subagent Instructions:

**A. Download transcript and acquire slides.**

**Transcript download:**
- **YouTube talks:** use yt-dlp with auto-subtitles across likely languages:
  ```bash
  yt-dlp --write-auto-sub --sub-lang "en,ru,he,fr,de,es,ja" --skip-download --sub-format vtt \
    -o "{vault_root}/transcripts/{youtube_id}" "https://www.youtube.com/watch?v={youtube_id}"
  ```
  The VTT filename includes the language code (e.g., `{youtube_id}.ru.vtt`). Record
  the detected language as `delivery_language`. After download, clean the VTT:
  ```bash
  python3 scripts/vtt-cleanup.py "{vault_root}/transcripts/{youtube_id}.{lang}.vtt"
  ```
  This strips timestamps, cue markers, and deduplicates lines. Output: `transcripts/{youtube_id}.txt`.
- **Fallback 1 — youtube-transcript-api** (if yt-dlp has no auto-captions):
  ```bash
  "{python_path}" -c "
  from youtube_transcript_api import YouTubeTranscriptApi
  transcript = YouTubeTranscriptApi.get_transcript('{youtube_id}', languages=['en','ru','he','fr','de'])
  for entry in transcript:
      print(entry['text'])
  " > "{vault_root}/transcripts/{youtube_id}.txt"
  ```
- **Fallback 2 — Whisper** (no captions at all, requires downloaded video/audio):
  ```bash
  ffmpeg -i "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
    -vn -acodec libmp3lame "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp3"
  ```
  Then transcribe with MLX Whisper (`mlx_whisper.transcribe()`) or OpenAI Whisper.
  Set `transcript_source: "whisper"`.
- **Non-YouTube talks** (InfoQ, Vimeo, conference platforms): attempt audio download
  via yt-dlp, then transcribe locally with Whisper. Falls back to `processed_partial`
  if audio fails.

**Slide acquisition** per `slide_source`:
- `pptx`/`both`: run `scripts/pptx-extraction.py <path.pptx>`.
- `pdf`: download via gdown:
  ```bash
  "{python_path}" -m gdown "https://drive.google.com/uc?id={google_drive_id}" \
    -O "{vault_root}/slides/{google_drive_id}.pdf"
  ```
- `video_extracted`: download video at 720p then run `scripts/video-slide-extraction.py`:
  ```bash
  yt-dlp -f "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]" \
    --merge-output-format mp4 \
    -o "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
    "https://www.youtube.com/watch?v={youtube_id}"
  python3 scripts/video-slide-extraction.py \
    "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
    "{vault_root}/slides-rebuild/{youtube_id}" "{youtube_id}"
  ```
  Copy PDF to `slides/{youtube_id}.pdf`. Delete video after extraction.
  For batch downloads, use `scripts/batch-download-videos.sh <vault_root> ID1 ID2 ...`.
- `none`: transcript-only, `processed_partial`.
- **Fallback:** if primary slides fail but `video_url` exists, fall back to video
  extraction. A talk can still reach `"processed"` status this way.

**Set `transcript_source`** on the talk entry: `youtube_auto` (yt-dlp captions),
`whisper` (local transcription), or `manual`. This field is required — downstream
tools use it to gauge transcript reliability.

**B. Analyze for Rhetoric & Style (NOT content).** Apply all 14 dimensions from
[references/rhetoric-dimensions.md](references/rhetoric-dimensions.md) (including dimension 14: Areas for Improvement).
Follow language policy and verbatim-quote rules in [references/processing-rules.md](references/processing-rules.md).
**Key rule:** all verbatim quotes must be English-first — `"English translation"
(original text)`. Never quote non-English text without an English translation preceding it.

**B2. Tag Presentation Patterns.** Scan observations against the pattern taxonomy
at `skills/presentation-creator/references/patterns/_index.md`. Skip patterns
marked `observable: false`. Record confidence (strong/moderate/weak) and evidence per
pattern. Compute per-talk score: count(patterns) − count(antipatterns). Store in
`pattern_observations`. See [references/processing-rules.md](references/processing-rules.md) for full tagging rules.

**C. Return JSON** per the subagent return schema in [references/schemas-db.md](references/schemas-db.md).
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

## Step 4 — Apply Subagent Results

Runs after each batch inside Step 3's loop (not as a separate post-loop
phase). One action: take the subagent JSON returns from the batch and
fold them into the tracking DB, per-talk analysis files, and the running
rhetoric summary in a single atomic update.

1. **Update tracking DB** — set `status`, `processed_date`, all result fields.
   Persist `pattern_observations` IDs + score. Populate structured fields
   (`co_presenter`, `delivery_language`, etc.) — do not leave structured data buried
   in free-text prose. See [references/processing-rules.md](references/processing-rules.md) for field extraction rules.
2. **Write per-talk analysis files** — write
   `{vault_root}/analyses/{talk_filename}.md` for each processed talk: all 14
   dimensions, structured data, verbatim examples, and a "Presentation Patterns
   Scoring" section. Create `analyses/` directory if missing.
3. **Update rhetoric-style-summary.md** — integrate `new_patterns` and
   `summary_updates`. Sections 1–14 map to the 14 dimensions; Section 15 aggregates
   improvement areas; Section 16 captures speaker-confirmed intent. **Recount status
   from the DB every time** — never increment manually.
   **Speaker-review gate:** before applying any `summary_updates` or `new_patterns`
   from a subagent, present the proposed changes (section-by-section diff) and wait
   for explicit speaker confirmation. Silent application erodes the speaker's sense
   of ownership of their own style summary; pattern taxonomy additions in particular
   can drift if applied unreviewed. Only bypass the gate if the speaker has pre-
   authorized this batch ("just apply everything, don't ask").
4. **Report:** talks processed, new patterns, current state, skipped talks.
5. Flag **structural changes** prominently (new presentation mode, new workflow pattern).

When Step 3's batch loop finishes, proceed to Step 5.

## Step 5 — Extract Remaining PPTX Visual Data

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

Proceed immediately to Step 6.

## Step 6 — Regenerate Speaker Profile

If `{vault_root}/speaker-profile.json` exists, invoke `Skill(skill: "vault-profile")`
with the updated tracking database. Report the diff of changes (added fields,
changed values) so the speaker can verify.

If the profile doesn't exist, skip this step silently.

Proceed immediately to Step 7.

## Step 7 — Same-Week Clarification Trigger

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
- **Wide-angle room recordings** defeat perceptual hash dedup — when the camera
  captures the full stage (speaker moving + slides on screen behind), every frame
  looks different. Mitigate by: increasing `--threshold` to 14-16, manually specifying
  `slide_region` crop coordinates, or accepting the bloated PDF and having the analysis
  subagent sample frames at intervals. Best results with fullscreen slide recordings
  (Devoxx, JFokus); worst with meetup/DevOpsDays audience-camera recordings.
- **Whisper hallucination on bad audio:** Whisper large-v3-turbo recovers ~60% of
  speech on poor recordings but hallucinates through silent/noisy sections. Always set
  `transcript_source: "whisper"`, cross-reference against visible slide text, and note
  quality issues (e.g., `transcript_quality: "partial"`).
- **Non-speaker talks slip into playlists.** Verify speaker identity early — check
  video frames and transcript for self-identification. Flag `is_baruch_talk: false`
  and set status to `skipped` if the speaker doesn't match.
