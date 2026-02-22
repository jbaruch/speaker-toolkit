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
