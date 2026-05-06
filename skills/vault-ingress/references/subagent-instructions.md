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
- **`pdf`** — download via gdown:
  ```bash
  "{python_path}" -m gdown \
    "https://drive.google.com/uc?id={google_drive_id}" \
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
