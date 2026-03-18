# Download Commands Reference

## A. Download Transcript

**The vault ingests transcripts in ANY language.** The vault is English-only for
analysis output, but transcripts are stored in the original delivery language.
The analysis subagent translates as needed per the language policy in SKILL.md.

### Primary: yt-dlp

Try all likely languages — the speaker delivers in English, Russian, and Hebrew:

```bash
yt-dlp --write-auto-sub --sub-lang "en,ru,he,fr,de,es,ja" --skip-download --sub-format vtt \
  -o "{vault_root}/transcripts/{youtube_id}" "https://www.youtube.com/watch?v={youtube_id}"
```

The VTT filename includes the language code (e.g., `{youtube_id}.ru.vtt`). Record
the detected language as `delivery_language` on the talk's DB entry.

### VTT Cleanup (required after yt-dlp download)

The .vtt file contains timestamps, cue position markers, and duplicate lines. Clean it before analysis:

1. Strip all timestamp lines (lines matching `\d{2}:\d{2}.*-->`)
2. Strip cue position markers (lines like `align:start position:0%`)
3. Remove blank lines
4. Deduplicate consecutive identical lines
5. Save the cleaned text as `{vault_root}/transcripts/{youtube_id}.txt`

### Fallback 1: youtube-transcript-api

Use if yt-dlp fails (e.g., no auto-captions available):

```bash
"{python_path}" -c "
from youtube_transcript_api import YouTubeTranscriptApi
transcript = YouTubeTranscriptApi.get_transcript('{youtube_id}', languages=['en','ru','he','fr','de'])
for entry in transcript:
    print(entry['text'])
" > "{vault_root}/transcripts/{youtube_id}.txt"
```

Where `{python_path}` is `config.python_path` from the tracking database.

This produces clean text directly — no VTT cleanup needed.

### Fallback 2: Whisper (local transcription)

Use when no YouTube captions exist at all. Requires a downloaded video or audio file:

```bash
# Extract audio from video
ffmpeg -i "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
  -vn -acodec libmp3lame "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp3"
```

Then transcribe with MLX Whisper (Apple Silicon) or OpenAI Whisper:

```python
import mlx_whisper
result = mlx_whisper.transcribe(
    "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp3",
    path_or_hf_repo='mlx-community/whisper-large-v3-turbo',
    language=None)  # auto-detect language
with open("{vault_root}/transcripts/{youtube_id}.txt", "w") as f:
    f.write(result["text"])
```

Set `transcript_source: "whisper"` on the talk entry (vs `"youtube_auto"`).

## B. Download Slides PDF

```bash
"{python_path}" -m gdown "https://drive.google.com/uc?id={google_drive_id}" \
  -O "{vault_root}/slides/{google_drive_id}.pdf"
```

Where `{python_path}` is `config.python_path` from the tracking database.

Then read the PDF to understand slide content and visual structure.

## C. Download Video (for slide extraction)

When no PDF or PPTX is available, download the video to extract slides from frames.

```bash
mkdir -p "{vault_root}/slides-rebuild/{youtube_id}"
yt-dlp -f "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]" \
  --merge-output-format mp4 \
  -o "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
  "https://www.youtube.com/watch?v={youtube_id}"
```

After download, run the extraction script from `references/video-slide-extraction.md`.
The script extracts frames, detects the slide region, deduplicates, and produces a
PDF at `slides/{youtube_id}.pdf`. Delete the video after extraction to save space.

## D. Batch Video Download

For processing many playlist talks at once, download videos in parallel:

```bash
# Download up to 3 videos concurrently
for yt_id in ID1 ID2 ID3 ...; do
  (
    yt-dlp -f "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]" \
      --merge-output-format mp4 \
      -o "{vault_root}/slides-rebuild/${yt_id}/${yt_id}.mp4" \
      "https://www.youtube.com/watch?v=${yt_id}" 2>/dev/null
    echo "Downloaded: ${yt_id}"
  ) &
  # Limit concurrency
  [ $(jobs -r -p | wc -l) -ge 3 ] && wait -n
done
wait
```

Then run the extraction script on each downloaded video sequentially.
