# Download Commands Reference

## A. Download Transcript

### Primary: yt-dlp

```bash
yt-dlp --write-auto-sub --sub-lang en --skip-download --sub-format vtt \
  -o "{vault_root}/transcripts/{youtube_id}" "https://www.youtube.com/watch?v={youtube_id}"
```

### VTT Cleanup (required after yt-dlp download)

The .vtt file contains timestamps, cue position markers, and duplicate lines. Clean it before analysis:

1. Strip all timestamp lines (lines matching `\d{2}:\d{2}.*-->`)
2. Strip cue position markers (lines like `align:start position:0%`)
3. Remove blank lines
4. Deduplicate consecutive identical lines
5. Save the cleaned text as `{vault_root}/transcripts/{youtube_id}.txt`

### Fallback: youtube-transcript-api

Use if yt-dlp fails (e.g., no auto-captions available):

```bash
"{python_path}" -c "
from youtube_transcript_api import YouTubeTranscriptApi
transcript = YouTubeTranscriptApi.get_transcript('{youtube_id}', languages=['en'])
for entry in transcript:
    print(entry['text'])
" > "{vault_root}/transcripts/{youtube_id}.txt"
```

Where `{python_path}` is `config.python_path` from the tracking database.

This produces clean text directly — no VTT cleanup needed.

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
