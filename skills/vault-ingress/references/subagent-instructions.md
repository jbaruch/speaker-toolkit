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
  Copy the resulting PDF to `slides/{youtube_id}.pdf`. Delete the video after
  extraction. For batch downloads, use
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
the shape walk. On those slides the extractor emits
`text_extraction_confidence: "low"`, keeps `text_content_preview` as
shape-only (often empty), and — when PICTURE blobs exist — fills `ocr_text`
via tesseract (`text_extraction_method: "shapes+ocr"`).

**An empty `text_content_preview` on a low-confidence slide is not evidence of
a wordless slide.** It means shapes could not read the text. Prefer `ocr_text`
for the word inventory; if that is also empty (engine missing, image
background with no picture blob, or genuinely blank art), still do not treat
absence as proof — look at the rendered page. Reading shape emptiness as
"wordless" inverts Dimension 8 — see
[known-issues.md](known-issues.md) § "Shape Extraction Is Blind to Text Baked
Into Images".

**Use the two channels for different jobs:**

| Job | Source |
|---|---|
| Word inventory, transcript cross-check, slide-text language policy, citational pattern evidence (`second-look` labels, buried jokes) | `ocr_text` (and shape `text_content_preview` when present) |
| Density / two-layer legibility / composition / Dim 8–13 design judgment | **Rendered page images** (OCR is not a layout oracle) |

When any slide in a deck reports `text_extraction_confidence: "low"`:

1. Read `ocr_text` and `text_extraction_method` from the extraction JSON first.
   Non-empty `ocr_text` is the citeable inventory. `shapes+ocr_unavailable`
   means install tesseract next time; do not invent words.

2. Get a PDF to render for design judgment. Which one depends on `slide_source`
   — the `pptx` path never downloads one, so it has to be produced:

   | `slide_source` | PDF |
   |---|---|
   | `pdf`, `both` | already at `{vault_root}/slides/{google_drive_id}.pdf` |
   | `video_extracted` | already at `{vault_root}/slides/{youtube_id}.pdf` |
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
object are mandatory. `transcript_source` is the sole conditional field: omit it
when the fetcher reports `existing` and the DB has no known provenance.

Use `clear_fields` when the re-analysis disproves an earlier value. Each entry is
an analysis-owned dotted path such as `verbatim_examples.jokes` or
`structured_data.slide_count`; an empty replacement alone does not clear stale
DB data because ordinary merges are additive.

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
    "evidence_sources": ["transcript", "static_slides"],
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
    "not_evaluable": [
      {
        "pattern_id": "composite-animation",
        "evidence_source": "static_slides",
        "reason": "A flattened PDF contains no animation timing."
      }
    ],
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
