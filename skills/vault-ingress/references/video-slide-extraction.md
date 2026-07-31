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
      → write scoped PDFs + page-to-video provenance
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

## Step 5: Write Scoped Artifacts

When a region is applied, assemble the retained frames twice by default:

- `{youtube_id}.slide-region.pdf` physically crops every page to the selected region.
  It is a deck-analysis candidate, and becomes trusted authored-slide evidence only
  after a visually verified manual crop.
- `{youtube_id}.context.pdf` preserves the full broadcast frame for room, stage,
  speaker, and PiP analysis. It is never an authored slide deck.

With no region, only the context PDF is written. Review-required runs always retain
context. `--no-context-pdf` may omit the extra context derivative only after a verified
manual crop; it never deletes the source video.

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

# Inspect the JSON result and both artifacts. If review_required is true, inspect
# the candidate against the context/source and rerun with checked coordinates:
python3 skills/vault-ingress/scripts/video-slide-extraction.py \
  "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
  "{vault_root}/slides-rebuild/{youtube_id}" \
  "{youtube_id}" \
  --region LEFT,TOP,RIGHT,BOTTOM --region-verified

# Only after review_required=false and trusted_for_authored_slide_analysis=true,
# promote the slide-region artifact:
cp "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.slide-region.pdf" \
  "{vault_root}/slides/{youtube_id}.pdf"
```

For batch downloads: `skills/vault-ingress/scripts/batch-download-videos.sh <vault_root> ID1 ID2 ...`

Always store the full script result in `structured_data.video_extraction` and keep
`slide_source: "video_extracted"` to name the acquisition path. Set
`slides_local_path: "slides/{youtube_id}.pdf"` only after promoting a trusted
`slide_region` artifact. Keep the source MP4 and context artifact in
`slides-rebuild/{youtube_id}/`; they are provenance, not disposable scratch.

## What This Produces

| Output | Location | Purpose |
|--------|----------|---------|
| Slide-region PDF | `slides-rebuild/{youtube_id}/{youtube_id}.slide-region.pdf` when a region is applied | Cropped deck-analysis candidate; trusted only after verified manual crop |
| Full-frame context PDF | `slides-rebuild/{youtube_id}/{youtube_id}.context.pdf` | Room/stage/PiP analysis; never authored-slide evidence |
| Source video | `slides-rebuild/{youtube_id}/{youtube_id}.mp4` | Durable source for crop review and re-extraction |
| Extraction metadata | `structured_data.video_extraction` | Canonical paths, artifact scopes, crop trust, retained-frame/page mapping, thresholds, versions |
| Intermediate JPEG frames | Deleted after PDF generation | Reproducible cache; source video and context remain |

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

The extractor may write that unverified auto crop as a `slide_region` candidate so it
can be inspected, but it emits `review_required: true` and
`trusted_for_authored_slide_analysis: false`. Never copy that candidate into `slides/`,
set `slides_local_path` from it, or cite it as authored-slide evidence. Rerun with the
printed coordinates as a manual region plus `--region-verified` after checking it
against the full-frame context/source. If a no-region result is actually a full-frame
screencast, verify that fact and rerun with `--region 0,0,1,1 --region-verified`.

**Wide-angle room recordings are out of scope by design.** No crop is promoted as
authored-slide evidence without ground truth to validate it, because a wrong crop
silently discards real slide content while no crop merely leaves the over-count visible.
An unverified candidate may be written for review, but extracted page counts for these
recordings remain unreliable in BOTH directions.

**Therefore: never report an extracted page count as a slide count.** The result names
it `unique_frame_count`, records each artifact's `page_count`, and leaves
`authored_slide_count` null. Corroborate in-frame first — a "Slide N of M" status bar,
a visible thumbnail rail, in-deck
numbering, or the speaker stating a count. With no corroboration, record the
count as low-confidence and say why.

## Pipeline Versioning

The extractor carries a `PIPELINE_VERSION` constant (top of
`skills/vault-ingress/scripts/video-slide-extraction.py`). It is stamped into every
video-extracted artifact in two places:

- **Vault DB row** — the script's JSON output includes `pipeline_version`, which
  lands in `structured_data.video_extraction.pipeline_version` when you record
  the DB entry.
- **PDF metadata** — every slide-region and context artifact records
  `speaker-toolkit/video-slide-extraction <version>` plus its factual scope. Context
  PDFs explicitly say "not authored slides" even when separated from the JSON result.

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
    3. Store the complete artifact manifest in structured_data
    4. If review_required, inspect source + context + candidate and rerun with a
       verified manual region; do not perform authored-deck analysis yet
    5. Promote only the trusted slide_region artifact to slides/{youtube_id}.pdf
    6. Read that promoted PDF for deck analysis (dimensions 8/13); read the
       full_frame_context artifact only for room/stage/PiP observations
    7. Keep the source video and context artifact for provenance and re-extraction
```

Only a `slide_region` artifact with
`trusted_for_authored_slide_analysis: true` is analyzed like a Google Drive PDF for
slide design patterns. A context PDF may reveal delivery and co-presentation behavior,
but broadcast overlays, venue furniture, lower thirds, and PiP do not belong to the
authored deck.

## Cleanup

After extraction is complete:

- Keep the downloaded MP4 source (typically 100–500 MB) under
  `slides-rebuild/{youtube_id}/` so crop review and future pipeline versions remain
  reproducible.
- Keep the full-frame context PDF unless the operator explicitly used
  `--no-context-pdf` with a verified manual crop. Unverified candidates always retain
  context for review.
- Delete only the intermediate JPEG frame directory; the script already does this.
- Keep the trusted promoted slide-region PDF in `slides/{youtube_id}.pdf` and its
  original artifact/manifest in `slides-rebuild/{youtube_id}/`.

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
- **Approximate time mapping**: `retained_frames[].timestamp_seconds` is derived from
  the zero-based sampled-frame index and extraction FPS. It locates the source-video
  neighborhood but is not caption/transcript synchronization; use content matching
  for precise rhetoric evidence.
