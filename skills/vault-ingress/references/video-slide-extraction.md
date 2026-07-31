# Video Slide Extraction — Technical Reference

Extract slide images from conference talk videos when no PPTX or PDF is available.
This is the fourth slide acquisition path — used when a talk has `video_url` but neither
`slides_url` nor `pptx_path`.

## Prerequisites

- `yt-dlp` (video download)
- `ffmpeg` (frame extraction)
- Python packages: `imagehash`, `Pillow` (perceptual deduplication)

Install Python dependencies:
```bash
"{python_path}" -m pip install imagehash Pillow
```

## When to Use

Set `slide_source: "video_extracted"` when:
- Talk has `video_url` but no `slides_url` and no `pptx_path`
- The video shows slides on screen (most conference recordings do)

Skip video extraction when:
- PPTX or PDF is available (those are higher quality sources)
- The video is audio-only, a panel/interview with no slides, or a pure live-coding demo

## Pipeline Overview

```
video → download (yt-dlp, 720p) → extract frames (ffmpeg, 1 per 2s)
      → crop to slide region → deduplicate (perceptual hash)
      → save unique slides → combine into PDF
```

## Step 1: Download Video

Download at 720p — enough resolution to read slide text, small enough to be fast.

```bash
yt-dlp -f "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]" \
  --merge-output-format mp4 \
  -o "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
  "https://www.youtube.com/watch?v={youtube_id}"
```

For talks where 720p is unavailable, yt-dlp will fall back to the best available.

## Step 2: Extract Frames

Extract one frame every 2 seconds. This captures slide transitions without
generating excessive frames (~1500 frames for a 50-min talk).

```bash
mkdir -p "{vault_root}/slides-rebuild/{youtube_id}/frames"
ffmpeg -i "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
  -vf "fps=0.5" -q:v 2 \
  "{vault_root}/slides-rebuild/{youtube_id}/frames/frame_%05d.jpg"
```

## Step 3: Detect Slide Region and Crop

Conference videos have varying layouts — slides may occupy the full frame, or
share space with a speaker camera (PiP), conference branding bars, or lower-third
titles. The script auto-detects the slide region.

## Step 4: Deduplicate by Perceptual Hash

Adjacent frames showing the same slide produce near-identical perceptual hashes.
Group consecutive similar frames and keep one representative per group.

## Step 5: Combine into PDF

Assemble unique slides into a single PDF for analysis, matching the format of
Google Drive PDFs used elsewhere in the vault.

## Usage

Run `python3 skills/vault-ingress/scripts/video-slide-extraction.py` for each video after downloading it:

```bash
# Download video at 720p
yt-dlp -f "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]" \
  --merge-output-format mp4 \
  -o "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
  "https://www.youtube.com/watch?v={youtube_id}"

# Extract slides
python3 skills/vault-ingress/scripts/video-slide-extraction.py \
  "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
  "{vault_root}/slides-rebuild/{youtube_id}" \
  "{youtube_id}"

# Copy PDF to slides dir, then delete the video
cp "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.pdf" "{vault_root}/slides/{youtube_id}.pdf"
rm "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4"
```

For batch downloads: `skills/vault-ingress/scripts/batch-download-videos.sh <vault_root> ID1 ID2 ...`

Update the talk's DB entry: `slide_source: "video_extracted"`,
`slides_local_path: "slides/{youtube_id}.pdf"`,
`structured_data.video_extraction: <script output>`.

## What This Produces

| Output | Location | Purpose |
|--------|----------|---------|
| Slide PDF | `slides/{youtube_id}.pdf` | Visual analysis (same as Google Drive PDFs) |
| Extraction metadata | `structured_data.video_extraction` | Frame counts, region detection, threshold, pipeline version |
| Intermediate frames | Deleted after PDF generation | Saves disk space |

## Slide-Region Detection — Contract and Limit

`detect_slide_region(frames)` returns either a `(left, upper, right, lower)`
crop as fractions of the frame, or `None` meaning "do not crop". Selection
criteria and constants live in `skills/vault-ingress/scripts/video-slide-extraction.py`
(`detect_slide_region` docstring and `_largest_rectangular_component`).

**A `None` is not a failure signal.** It is returned both for full-frame
screencasts, where there is nothing to crop, and for wide-angle room recordings,
where the region cannot be identified safely. The caller cannot distinguish
them, and must not treat an uncropped extraction as a verified one.

**A returned region is not a verified one either.** Detection is dependable only
for broadcast composites — a fixed slide rectangle beside static venue
furniture. On room recordings it returns the speaker about as readily as the
screen: a torso is rectangular, well-filled, and the right size and aspect. A
by-eye check of 94 corpus decks found correct screen crops and confident crops
of a presenter's chest in the same pass. Look at the crop before trusting
anything derived from it.

**Wide-angle room recordings are out of scope by design.** No crop ships without
ground truth to validate it, because a wrong crop silently discards real slide
content while no crop merely leaves the over-count visible. Extracted page
counts for those recordings stay unreliable in BOTH directions.

**Therefore: never report an extracted page count as a slide count.** Corroborate
in-frame first — a "Slide N of M" status bar, a visible thumbnail rail, in-deck
numbering, or the speaker stating a count. With no corroboration, record the
count as low-confidence and say why.

## Pipeline Versioning

The extractor carries a `PIPELINE_VERSION` constant (top of
`skills/vault-ingress/scripts/video-slide-extraction.py`). It is stamped into every
video-extracted artifact in two places:

- **Vault DB row** — the script's JSON output includes `pipeline_version`, which
  lands in `structured_data.video_extraction.pipeline_version` when you record
  the DB entry.
- **PDF metadata** — the producer/creator fields of `slides/{youtube_id}.pdf`
  read `speaker-toolkit/video-slide-extraction <version>`.

Query the running version with `video-slide-extraction.py --version`, which
prints `{"pipeline_version": "<version>"}` (JSON, queryable without the
extraction dependencies installed).

**Bump policy:** increment `PIPELINE_VERSION` in the same change that alters
extraction *behavior* — the default `--fps` or `--threshold`, the 720p download
tier, region-detection logic, the dedup hashing, or PDF assembly. A bump pairs
with the behavior change so re-ingested vaults are comparable across iterations.
Pure refactors, comments, and doc edits that don't change output do not bump.

## Layout Detection Heuristics

Common conference video layouts and how the script handles them:

| Layout | Example | Slide Region |
|--------|---------|-------------|
| Full-frame slides | Most Devoxx, JFokus | `None` (full frame) |
| Slides + speaker PiP (corner) | DevOpsDays, meetups | 70-85% left/center |
| Slides + speaker sidebar | QCon, some webinars | 60-75% left |
| Speaker + slides behind | TED-style keynotes | Variable, may fail |
| Split screen 50/50 | Co-presented live coding | 50% left or right |

The `detect_slide_region()` function handles the first three automatically via
variance analysis. For split-screen formats, provide a normalized manual crop:
`--region LEFT,TOP,RIGHT,BOTTOM`. Add `--region-verified` only after checking the
crop against rendered frames. Use `--region none` to disable cropping when the
auto-detector selects the wrong subject. An auto-detected crop remains unverified;
after checking it, rerun with its printed coordinates as a manual region plus
`--region-verified` to record that judgment.

## Tuning the Hash Threshold

The `hash_threshold` parameter is the largest perceptual-hash distance still
treated as the same slide. The implementation keeps a frame only when its
distance from the last kept frame is **greater than** the threshold. Therefore,
raising the threshold merges more aggressively and keeps fewer variants:

| Value | Behavior | Best For |
|-------|----------|----------|
| 4-6 | Conservative merge: keeps more visual variants | Progressive reveals or visually similar authored slides; expect more animation noise |
| 8-10 | Moderate merge | Most conference talks (fullscreen slide recordings) |
| 12-16 | Aggressive merge: keeps fewer variants | Moving overlays or room motion; verify that real slides were not merged |
| 14-18 | Very aggressive merge | Last-resort wide-angle cleanup after a manual crop is unavailable; high under-count risk |

For talks in the speaker's mode (a) polemic style with progressive reveals,
start at threshold 4–6 so reveal steps remain distinct. For demo-heavy or
minimal-slide talks, start at 8 and inspect the retained frames.

**Wide-angle room recordings** (meetups, DevOpsDays, early-era conference recordings)
where the camera captures the full stage — speaker walking + slides projected behind —
defeat the default dedup. Every frame looks different because the speaker moved. Options:
1. Manually specify `--region LEFT,TOP,RIGHT,BOTTOM --region-verified` to crop
   out the speaker and isolate the screen
2. Increase the threshold to 14–18 to merge more motion variants, then verify
   that distinct slides and progressive reveals were not under-counted
3. Accept the bloated PDF (800-1500 pages) and have the analysis subagent SAMPLE
   frames at intervals rather than reading every page

## Integration with the Skill Workflow

In Step 3 of the skill (per-talk subagent):

```
if slide_source == "video_extracted":
    1. Download video: yt-dlp -f "best[height<=720]" ...
    2. Run extract_slides_from_video()
    3. Copy PDF to slides/{youtube_id}.pdf
    4. Read the PDF for visual analysis (dimension 13)
    5. Delete the video file (keep only the PDF)
    6. Store extraction metadata in structured_data
```

The resulting PDF is analyzed exactly like a Google Drive PDF — the subagent
reads it for slide design patterns (backgrounds, typography, shapes, memes,
footer, etc.) using the same dimension 13 analysis.

## Cleanup

After extraction is complete and the PDF is saved:
- Delete the downloaded MP4 video (typically 100-500 MB)
- Delete the frames directory (already done by the script)
- Keep only the PDF in `slides/{youtube_id}.pdf`

For a full 83-talk batch, the video downloads would consume ~20-40 GB temporarily
but only ~1-2 GB of PDFs remain after cleanup.

## Limitations

- **Speaker overlay**: If the speaker's face overlaps slides (green-screen overlay
  style), frame extraction still works but the perceptual hash may treat the same
  slide with different speaker positions as different slides. A higher threshold
  merges more of those variants but also raises under-count risk; prefer a manual
  crop when the slide area can be isolated.
- **Animated slides**: Animations within a single slide produce multiple frames.
  The dedup catches most of these, but fast animations at exactly the 2-second
  boundary may produce duplicates. Not a significant issue in practice.
- **Progressive reveals**: The speaker's talks frequently use progressive reveals
  (table rows appearing one-by-one). These ARE different slides rhetorically and
  SHOULD be kept as separate pages. Lower thresholds keep more variants; start at
  4–6 when preserving reveal steps matters, then inspect for animation noise.
- **Low-quality uploads**: Some older conference videos are 360p or lower. Frame
  extraction still works but slide text may be unreadable. Flag these with
  `video_quality: "low"` in structured_data.
- **No audio sync**: Frame timestamps are not correlated with transcript timestamps.
  The subagent must use content matching (reading slide text and matching to
  transcript passages) rather than time alignment.
