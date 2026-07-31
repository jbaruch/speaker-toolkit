# Per-Talk Subagent Instructions — Detail

The Step 3 procedure each parallel subagent runs. The orchestrator passes the
talk's DB entry plus the current `rhetoric-style-summary.md`; the subagent
returns the JSON shape in [schemas-db.md](schemas-db.md).

## A. Acquire Transcript and Slides

### Transcript download

One command. Do NOT hand-roll a fetch — an inline `python3 -c` fetch here is
what wrote four Python tracebacks into `transcripts/` when the upstream library
renamed a method, and nothing noticed because nothing validated the output.

```bash
python3 skills/vault-ingress/scripts/fetch-transcript.py {youtube_id} \
  --out "{vault_root}/transcripts/{youtube_id}.txt" \
  [--duration-seconds {seconds}]
```

The script owns the whole chain — caption track first, local Whisper fallback,
validation, atomic write. It prints one JSON object and never leaves a file
behind on failure. Exit codes and the JSON shape are the script's contract; see
its module docstring.

| exit | meaning | what to do |
|---|---|---|
| 0 | a valid transcript is at `--out` | continue; read `method` to set `transcript_source` |
| 1 | no source produced a valid transcript | `processed_partial` at best — say so in `rhetoric_notes` |
| 2 | argument or tool-state error | the id or the environment is wrong, not the talk |

Map the returned `method` to `transcript_source`:

| `method` | `transcript_source` |
|---|---|
| `captions` | `youtube_auto` |
| `whisper` | `whisper` |
| `existing` | leave the talk's current `transcript_source` unchanged; when the field is absent, leave it absent |

`existing` means a valid transcript was already on disk and no fetch ran, so the
script learned nothing about where it came from — overwriting the recorded source
would replace a known value with a guess, and inventing one where the field is
absent is the same error with no prior value to lose. `manual` in particular
means a human produced the transcript; writing it on an unknown-provenance file
asserts something false, and a downstream reader weighing transcript reliability
would trust it more than the ASR it probably is.

Set `delivery_language` from the returned `language`: the caption track's own
language code, or Whisper's detected language. It is `null` on the `existing`
path — keep whatever the talk already records, and leave the field unset rather
than guessing when there is nothing to copy.

Pass `--duration-seconds` when the runtime is known — it enables the
words-per-minute check that catches a caption track returning only its opening
minute.

**A transcript already on disk is not proof of a transcript.** Ten corpus files
were empty, a traceback, or a stub. Running the script without `--force` is the
check: it validates any existing file and either keeps it or replaces it.

**Non-YouTube talks** (InfoQ, Vimeo, conference platforms): acquire the audio or
video file, then pass it to the same script with `--audio`. Do not call
`mlx_whisper.transcribe()` yourself — the validation, the atomic write and the
JSON contract all live in the script, and a hand-rolled call has none of them.

```bash
python3 skills/vault-ingress/scripts/fetch-transcript.py {talk_label} \
  --audio "{path_to_audio_or_video}" \
  --out "{vault_root}/transcripts/{talk_id}.txt"
```

Set `transcript_source: whisper` on exit 0. Fall back to `processed_partial`
when no audio is obtainable at all.

### Slide acquisition (per `slide_source`)

- **`pptx` / `both`** — run
  `python3 skills/vault-ingress/scripts/pptx-extraction.py <path.pptx>`.
- **`pdf`** — download via gdown (pass the bare Google Drive file id; gdown
  accepts a `url_or_id` argument, so no full download URL is needed):
  ```bash
  "{python_path}" -m gdown "{google_drive_id}" \
    -O "{vault_root}/slides/{google_drive_id}.pdf"
  ```
- **`video_extracted`** — download video at 720p, then extract slides:
  ```bash
  yt-dlp -f "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]" \
    --merge-output-format mp4 \
    -o "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
    "https://www.youtube.com/watch?v={youtube_id}"
  python3 skills/vault-ingress/scripts/video-slide-extraction.py \
    "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
    "{vault_root}/slides-rebuild/{youtube_id}" "{youtube_id}"
  ```
  Store the complete JSON result in `structured_data.video_extraction`, then obey its
  artifact gate:

  1. An artifact with `artifact_scope: "full_frame_context"` is evidence about the
     room, stage, speaker, and PiP only. Never treat it as the authored deck, derive
     slide design from it, or copy it to `slides/{youtube_id}.pdf`.
  2. A `slide_region` artifact from a result with top-level `review_required: true`, or
     whose own `trusted_for_authored_slide_analysis` is false, is only a crop candidate.
     Inspect it against the context PDF and source video, then rerun with the checked
     coordinates as `--region LEFT,TOP,RIGHT,BOTTOM --region-verified`. An auto crop is
     always unverified. If the source is truly a full-frame screencast, use the verified
     manual region `0,0,1,1`.
  3. Only a `slide_region` artifact with
     `trusted_for_authored_slide_analysis: true` and `review_required: false` may be
     copied to `slides/{youtube_id}.pdf`, recorded as `slides_local_path`, and analyzed
     like an authored PDF deck.

  The return validator recomputes that trust from the complete schema-v3 manifest; it
  does not trust `slide_source: "video_extracted"` or an isolated artifact boolean.
  `status: "processed"` requires both the trusted manifest and the promoted top-level
  `slides_local_path: "slides/{youtube_id}.pdf"`. A trusted artifact may still finish
  `processed_partial` when another channel fails, and its verified `slide_region` may
  supply `static_slides` evidence even before promotion. Any return without a promoted
  artifact must omit `slides_local_path` and put `slides_local_path` in `clear_fields`.
  If the manifest itself is untrusted, the result is context-only: return
  `processed_partial` and omit authored-slide structured claims such as `slide_count`,
  slide design, typography, per-slide visuals, and image counts.

  A `full_frame_context` artifact may support `delivery_video` observations about the
  room, speaker, PiP, or visible delivery phenomena when it was actually inspected. It
  never makes `static_slides` available. Apply each catalog entry's `evaluable_from`
  gate to the sources actually inspected. If none qualifies—or the source cannot
  establish that entry's evidence requirements—record the entry in `not_evaluable`.

  Keep the source MP4 and full-frame context artifact under
  `slides-rebuild/{youtube_id}/` for provenance and future re-extraction. The script
  deletes only its intermediate JPEG frames. `unique_frame_count` and artifact
  `page_count` are retained video samples, not authored `slide_count`; populate
  `structured_data.slide_count` only from corroborated deck numbering or an authored
  source. For batch downloads, use
  `skills/vault-ingress/scripts/batch-download-videos.sh <vault_root> ID1 ID2 ...`.
- **`none`** — transcript-only, status `processed_partial`.
- **Fallback** — if primary slides fail but `video_url` exists, fall back to
  video extraction. A talk can still reach `processed` status this way.

### `transcript_source` records known provenance

Set `transcript_source` on the talk entry: `youtube_auto` (caption track),
`whisper` (local transcription), or `manual`. Downstream tools use it to gauge
transcript reliability.

**One exception, and only one:** `method: "existing"` from the fetcher. No fetch
ran, so provenance is unknown — leave the recorded value alone, and leave the
field absent when it was already absent. `manual` asserts a human produced the
transcript; writing it on an unknown file is a false claim that makes a
downstream reader trust ASR more than it should. Absent is honest; invented is
not.

## B. Analyze for Rhetoric & Style (NOT content)

Apply all 14 dimensions from
[rhetoric-dimensions.md](rhetoric-dimensions.md), including dimension 14
(Areas for Improvement). Follow language policy and verbatim-quote rules in
[processing-rules.md](processing-rules.md).

**Quote rule:** verbatim quotes must be English-first —
`"English translation" (original text)`. Never quote non-English text without
an English translation preceding it.

### Slides with `text_extraction_confidence: low` — inventory + pixels

`skills/vault-ingress/scripts/pptx-extraction.py` reads text out of PPTX
*shapes*. Text rendered inside a picture — the norm for AI-generated illustration decks, where titles, callout
labels, stamps, and annotations are all baked into the image — is invisible to
native text channels. On those slides the extractor emits
`text_extraction_confidence: "low"`, keeps `text_content_preview` as
native shape/table text (often empty), and — when PICTURE or background-image
blobs exist — fills distinct provenance-bearing OCR channels plus the
backward-compatible `ocr_text` aggregate via tesseract
(`text_extraction_method: "shapes+ocr"`).

**An empty `text_content_preview` on a low-confidence slide is not evidence of
a wordless slide.** It means shapes could not read the text. Prefer `ocr_text`
for the word inventory; inspect `text_channels` to learn which source was read.
If OCR is also empty (engine missing, unavailable/corrupt image blob, unsupported
SmartArt/chart/graphic frame, or genuinely blank art), still do not treat
absence as proof — look at the rendered page. Reading shape emptiness as
"wordless" inverts Dimension 8 — see
[known-issues.md](known-issues.md) § "Shape Extraction Is Blind to Text Baked
Into Images".

**Use the source classes for different jobs:**

| Job | Source |
|---|---|
| Word inventory, transcript cross-check, slide-text language policy, citational pattern evidence (`second-look` labels, buried jokes) | `text_channels` first; `ocr_text` and `text_content_preview` are compatibility aggregates |
| Density / two-layer legibility / composition / Dim 8–13 design judgment | **Rendered page images** (OCR is not a layout oracle) |

When any slide in a deck reports `text_extraction_confidence: "low"`:

1. Read `text_channels`, `unsupported_content`, and
   `render_required_reasons` from the extraction JSON first. Each channel names
   its source, confidence, and status. `ocr_text` remains a convenient combined
   inventory. `shapes+ocr_unavailable` means install tesseract next time; an
   `unsupported` or `unavailable` channel needs rendering or a specialized
   parser. Do not invent words.

2. Get a PDF to render for design judgment. Which one depends on `slide_source`
   — the `pptx` path never downloads one, so it has to be produced:

   | `slide_source` | PDF |
   |---|---|
   | `pdf`, `both` | already at `{vault_root}/slides/{google_drive_id}.pdf` |
   | `video_extracted` | trusted `slide_region` artifact promoted to `{vault_root}/slides/{youtube_id}.pdf`; if no trusted artifact exists, deck-layout judgment is not evaluable |
   | `pptx` | none exists — export it from the deck (below) |

   For `pptx`, export first (PowerPoint via AppleScript, LibreOffice fallback).
   A `pptx`-sourced talk may have no `slides_url`, so `google_drive_id` can be
   absent — render to a temp path, which needs no id and no cleanup:

   ```bash
   python3 skills/presentation-creator/scripts/export-pdf.py \
     "{pptx_path}" "{tmp}/deck.pdf"
   ```

   If the export fails and no PDF exists for the talk, say so in the analysis
   and mark Dimensions 8 and 13 design fields low-confidence rather than
   judging layout from shape JSON alone — an unreadable deck is not a wordless
   one. Still use any `ocr_text` that the extractor produced from picture blobs.

3. Render the pages and read them for design:

   ```bash
   pdftoppm -png -r 100 -f <first> -l <last> "{pdf_path}" "{tmp}/slide"
   ```

4. Judge **Dimension 8** structure (dense vs minimal, room vs reward layer) and
   **Dimension 13** (Slide Design) from the rendered images. Cross-check the
   spoken word against `ocr_text` where the inventory exists.
5. Count `image_only_slide_count` from what the rendered slide *shows* (and
   from non-empty `ocr_text`), not from empty shape text alone. A slide
   carrying baked-in text is not image-only.

Structural fields stay authoritative for what they actually measure —
`shape_count`, `background_color_hex`, `layout_name`, fonts, and
`has_text_frame_shapes` (which reports text-frame shapes, not on-screen text).

## B2. Tag Presentation Patterns

Scan observations against the pattern taxonomy at
`skills/presentation-creator/references/patterns/_index.md`. Skip patterns
marked `observable: false`. Record confidence (strong/moderate/weak) and
evidence per pattern. Compute per-talk score:
`count(patterns) − count(antipatterns)`. Store in `pattern_observations`.
See [processing-rules.md](processing-rules.md) for full tagging rules.

## C. Return JSON

Return exactly the shape in [schemas-db.md](schemas-db.md). `status`,
`slide_source`, all five catalog-feedback lanes, and the complete pattern score
object are mandatory. `transcript_source` is conditional provenance: omit it when
the fetcher reports `existing` and the DB has no known provenance.
`slides_local_path` is optional for ordinary returns but mandatory for
`status: "processed"` with `slide_source: "video_extracted"`.
Omit `processed_date`; the persistence writer owns one normalized timestamp for
the complete queue batch and the analysis writer renders that stored value.

Use `clear_fields` when the re-analysis disproves an earlier value. Each entry is
an analysis-owned dotted path such as `verbatim_examples.jokes` or
`structured_data.slide_count`; an empty replacement alone does not clear stale
DB data because ordinary merges are additive. An untrusted or unpromoted
video-extraction result must include `slides_local_path` here so an older trusted
deck path cannot survive the corrective merge; also clear any stale authored-slide
structured fields disproved by the new evidence.

Minimal processed structure:

```json
{
  "filename": "2026-01-01-example.md",
  "queue_claim": {
    "run_id": "reparse-2026-07",
    "batch_id": "25",
    "reprocess_generation": 1
  },
  "status": "processed",
  "transcript_source": "youtube_auto",
  "slide_source": "pdf",
  "slides_local_path": "slides/example.pdf",
  "rhetoric_notes": "Dimensions 1-13 analysis...",
  "areas_for_improvement": "Dimension 14 analysis...",
  "adherence_assessment": "Compared with the current baseline...",
  "new_patterns": "",
  "summary_updates": "",
  "structured_data": {
    "delivery_language": "en",
    "co_presenter": false
  },
  "verbatim_examples": {},
  "pattern_observations": {
    "evidence_sources": ["transcript", "static_slides", "delivery_video"],
    "patterns_detected": [
      {
        "pattern_id": "narrative-arc",
        "confidence": "strong",
        "evidence_source": "transcript",
        "evidence": "Four named acts build one argument.",
        "dimensions": [2, 5]
      }
    ],
    "antipatterns_detected": [],
    "not_evaluable": [],
    "pattern_score": {
      "patterns_used": 1,
      "antipatterns_detected": 0,
      "score": 1
    }
  },
  "catalog_feedback": {
    "unmatched_observations": [],
    "confusable_pairs": [],
    "definition_problems": [],
    "scoring_problems": [],
    "tensions": []
  }
}
```

Before returning, run the deterministic gate:

```bash
python3 skills/vault-ingress/scripts/validate-returns.py batch-returns.json
```

Fix every reported error. Do not weaken a catalog ID, polarity, observability,
evidence, confidence, score, or status error into a prose caveat.
