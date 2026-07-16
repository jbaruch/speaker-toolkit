# Per-Talk Subagent Instructions — Detail

The Step 3 procedure each parallel subagent runs. The orchestrator passes the
talk's DB entry plus the current `rhetoric-style-summary.md`; the subagent
returns the JSON shape in [schemas-db.md](schemas-db.md).

## A. Acquire Transcript and Slides

### Transcript download

**YouTube talks** — `yt-dlp` with auto-subtitles across likely languages:

```bash
yt-dlp --write-auto-sub --sub-lang "en,ru,he,fr,de,es,ja" --skip-download \
  --sub-format vtt \
  -o "{vault_root}/transcripts/{youtube_id}" \
  "https://www.youtube.com/watch?v={youtube_id}"
```

The VTT filename includes the language code (e.g., `{youtube_id}.ru.vtt`).
Record the detected language as `delivery_language`. After download, clean the
VTT:

```bash
python3 skills/vault-ingress/scripts/vtt-cleanup.py \
  "{vault_root}/transcripts/{youtube_id}.{lang}.vtt"
```

This strips timestamps, cue markers, and deduplicates lines. Output:
`transcripts/{youtube_id}.txt`.

**Fallback 1 — `youtube-transcript-api`** (when yt-dlp has no auto-captions):

```bash
"{python_path}" -c "
from youtube_transcript_api import YouTubeTranscriptApi
transcript = YouTubeTranscriptApi.get_transcript('{youtube_id}', languages=['en','ru','he','fr','de'])
for entry in transcript:
    print(entry['text'])
" > "{vault_root}/transcripts/{youtube_id}.txt"
```

**Fallback 2 — Whisper** (no captions at all; requires downloaded video/audio):

```bash
ffmpeg -i "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
  -vn -acodec libmp3lame \
  "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp3"
```

Then transcribe with MLX Whisper (`mlx_whisper.transcribe()`) or OpenAI
Whisper. Set `transcript_source: "whisper"`.

**Non-YouTube talks** (InfoQ, Vimeo, conference platforms): attempt audio
download via yt-dlp, then transcribe locally with Whisper. Falls back to
`processed_partial` if audio fails.

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

### `transcript_source` is required

Set `transcript_source` on the talk entry: `youtube_auto` (yt-dlp captions),
`whisper` (local transcription), or `manual`. Downstream tools use it to gauge
transcript reliability.

## B. Analyze for Rhetoric & Style (NOT content)

Apply all 14 dimensions from
[rhetoric-dimensions.md](rhetoric-dimensions.md), including dimension 14
(Areas for Improvement). Follow language policy and verbatim-quote rules in
[processing-rules.md](processing-rules.md).

**Quote rule:** verbatim quotes must be English-first —
`"English translation" (original text)`. Never quote non-English text without
an English translation preceding it.

### Slides with `text_extraction_confidence: low` — look at the pixels

`skills/vault-ingress/scripts/pptx-extraction.py` reads text out of PPTX
*shapes*. Text rendered inside a picture — the norm for AI-generated illustration decks, where titles, callout
labels, stamps, and annotations are all baked into the image — is invisible to
it. On those slides the extractor emits `text_extraction_confidence: "low"`
and its `text_content_preview` is empty or partial.

**An empty `text_content_preview` on a low-confidence slide is not evidence of
a wordless slide.** It means the extractor could not read the slide at all.
Reading it as absence inverts Dimension 8 — see
[known-issues.md](known-issues.md) § "Shape Extraction Is Blind to Text Baked
Into Images".

When any slide in a deck reports `text_extraction_confidence: "low"`:

1. Get a PDF to render. Which one depends on `slide_source` — the `pptx` path
   never downloads one, so it has to be produced:

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
   and mark Dimensions 8 and 13 low-confidence rather than judging them from
   the extraction JSON — an unreadable deck is not a wordless one.

2. Render the pages and read them:

   ```bash
   pdftoppm -png -r 100 -f <first> -l <last> "{pdf_path}" "{tmp}/slide"
   ```

3. Judge **Dimension 8** (Slide-to-Speech Relationship) and **Dimension 13**
   (Slide Design) from the rendered images, never from the extraction JSON.
   The question Dimension 8 asks — dense or minimal, image-heavy or
   text-heavy — is the one the JSON cannot answer for these slides.
4. Count `image_only_slide_count` from what the rendered slide *shows*, not
   from what the extractor could reach. A slide carrying baked-in text is not
   image-only, whatever the JSON says.

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

Per the subagent return schema in [schemas-db.md](schemas-db.md). Minimal
structure:

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
