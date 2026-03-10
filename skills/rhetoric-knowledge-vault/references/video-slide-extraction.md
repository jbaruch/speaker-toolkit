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

## Extraction Script

Run this for each video. It handles steps 2-5 after the video is downloaded.

```python
import os
import sys
import glob
import json
from pathlib import Path

# Check dependencies
try:
    import imagehash
    from PIL import Image
except ImportError:
    print("ERROR: Install dependencies: pip install imagehash Pillow")
    sys.exit(1)


def extract_frames(video_path, frames_dir, fps=0.5):
    """Extract frames from video at specified fps."""
    os.makedirs(frames_dir, exist_ok=True)
    cmd = (
        f'ffmpeg -i "{video_path}" -vf "fps={fps}" -q:v 2 '
        f'"{frames_dir}/frame_%05d.jpg" -y -loglevel warning'
    )
    ret = os.system(cmd)
    if ret != 0:
        raise RuntimeError(f"ffmpeg failed with code {ret}")
    frames = sorted(glob.glob(f"{frames_dir}/frame_*.jpg"))
    print(f"  Extracted {len(frames)} frames")
    return frames


def detect_slide_region(frames, sample_size=10):
    """Auto-detect the slide region by analyzing variance across sample frames.

    Conference videos typically have a static border (conference branding,
    speaker PiP in a fixed corner) and a dynamic center (the slides).
    We find the bounding box of the high-variance region.

    Returns (left, upper, right, lower) as fraction of image dimensions,
    or None if slides appear to be full-frame.
    """
    import numpy as np

    if len(frames) < sample_size * 2:
        return None  # Too few frames, assume full-frame

    # Sample evenly spaced frame pairs
    step = max(1, len(frames) // sample_size)
    diffs = []

    for i in range(0, len(frames) - step, step):
        img1 = np.array(Image.open(frames[i]).convert('L').resize((320, 180)))
        img2 = np.array(Image.open(frames[i + step]).convert('L').resize((320, 180)))
        diff = np.abs(img1.astype(float) - img2.astype(float))
        diffs.append(diff)

    # Average difference map — high values = dynamic (slide content changes)
    avg_diff = np.mean(diffs, axis=0)

    # Threshold: regions with above-median change are "slide area"
    threshold = np.percentile(avg_diff, 60)
    mask = avg_diff > threshold

    # Find bounding box of the active region
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)

    if not rows.any() or not cols.any():
        return None  # No clear region detected

    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]

    h, w = avg_diff.shape  # 180, 320

    # Convert to fractions with a small margin
    margin = 0.02
    region = (
        max(0, cmin / w - margin),
        max(0, rmin / h - margin),
        min(1, (cmax + 1) / w + margin),
        min(1, (rmax + 1) / h + margin),
    )

    # If region covers >90% of the frame, it's effectively full-frame
    area = (region[2] - region[0]) * (region[3] - region[1])
    if area > 0.9:
        return None

    print(f"  Detected slide region: {region[0]:.0%}-{region[2]:.0%} horizontal, "
          f"{region[1]:.0%}-{region[3]:.0%} vertical ({area:.0%} of frame)")
    return region


def crop_frame(img, region):
    """Crop an image to the detected slide region."""
    if region is None:
        return img
    w, h = img.size
    box = (
        int(region[0] * w),
        int(region[1] * h),
        int(region[2] * w),
        int(region[3] * h),
    )
    return img.crop(box)


def deduplicate_frames(frames, slide_region=None, hash_threshold=8):
    """Deduplicate consecutive similar frames using perceptual hashing.

    Returns list of (frame_path, frame_index) for unique slides.
    hash_threshold: lower = stricter dedup (fewer slides).
      - 4-6: aggressive, may merge progressive reveals
      - 8-12: moderate, good default for most talks
      - 14+: loose, keeps more variation (use for progressive-reveal-heavy talks)
    """
    unique_slides = []
    prev_hash = None

    for i, frame_path in enumerate(frames):
        img = Image.open(frame_path)
        # Hash the CROPPED region (slide only, not speaker PiP)
        cropped = crop_frame(img, slide_region)
        h = imagehash.phash(cropped, hash_size=16)

        if prev_hash is None or abs(h - prev_hash) > hash_threshold:
            unique_slides.append((frame_path, i))
            prev_hash = h

    print(f"  Deduplicated: {len(frames)} frames -> {len(unique_slides)} unique slides")
    return unique_slides


def combine_to_pdf(unique_slides, output_pdf, slide_region=None):
    """Combine unique slide frames into a PDF.

    Saves FULL (uncropped) frames — the crop region was only used for
    hash comparison. The full frame preserves speaker PiP context which
    can be useful for analyzing co-presentation dynamics.
    """
    images = []
    for frame_path, _ in unique_slides:
        img = Image.open(frame_path).convert('RGB')
        images.append(img)

    if not images:
        print("  WARNING: No unique slides found")
        return None

    images[0].save(output_pdf, save_all=True, append_images=images[1:])
    size_mb = os.path.getsize(output_pdf) / (1024 * 1024)
    print(f"  Saved PDF: {output_pdf} ({len(images)} pages, {size_mb:.1f} MB)")
    return output_pdf


def extract_slides_from_video(video_path, output_dir, youtube_id,
                               fps=0.5, hash_threshold=8):
    """Full pipeline: frames -> detect region -> dedup -> PDF.

    Args:
        video_path: Path to downloaded MP4
        output_dir: Directory for intermediate files and output PDF
        youtube_id: YouTube video ID (used for naming)
        fps: Frames per second to extract (0.5 = 1 frame per 2 seconds)
        hash_threshold: Perceptual hash distance threshold for dedup (8-12 recommended)

    Returns:
        dict with extraction results for structured_data
    """
    frames_dir = os.path.join(output_dir, "frames")
    output_pdf = os.path.join(output_dir, f"{youtube_id}.pdf")

    print(f"Extracting slides from {youtube_id}...")

    # Step 2: Extract frames
    frames = extract_frames(video_path, frames_dir, fps=fps)
    if not frames:
        return {"error": "No frames extracted", "slide_count": 0}

    # Step 3: Detect slide region
    slide_region = detect_slide_region(frames)

    # Step 4: Deduplicate
    unique_slides = deduplicate_frames(frames, slide_region, hash_threshold)

    # Step 5: Combine into PDF
    pdf_path = combine_to_pdf(unique_slides, output_pdf, slide_region)

    # Cleanup: remove frame JPEGs to save space (keep PDF)
    for f in frames:
        os.remove(f)
    try:
        os.rmdir(frames_dir)
    except OSError:
        pass

    result = {
        "slide_source": "video_extracted",
        "total_frames_extracted": len(frames),
        "unique_slides_count": len(unique_slides),
        "hash_threshold_used": hash_threshold,
        "slide_region_detected": slide_region is not None,
        "slide_region": slide_region,
        "output_pdf": pdf_path,
        "fps_used": fps,
    }

    print(f"  Done: {len(unique_slides)} unique slides extracted")
    return result


# Usage from the rhetoric-knowledge-vault skill:
#
# vault_root = "/path/to/rhetoric-knowledge-vault"
# youtube_id = "aUEyM59Ob2k"
# video_path = f"{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4"
# output_dir = f"{vault_root}/slides-rebuild/{youtube_id}"
#
# result = extract_slides_from_video(video_path, output_dir, youtube_id)
#
# # Copy the PDF to the slides directory for analysis
# import shutil
# slides_pdf = f"{vault_root}/slides/{youtube_id}.pdf"
# shutil.copy2(result["output_pdf"], slides_pdf)
#
# # Update the talk entry in the tracking DB:
# talk["slide_source"] = "video_extracted"
# talk["slides_local_path"] = slides_pdf
# talk["structured_data"]["video_extraction"] = result
```

## What This Produces

| Output | Location | Purpose |
|--------|----------|---------|
| Slide PDF | `slides/{youtube_id}.pdf` | Visual analysis (same as Google Drive PDFs) |
| Extraction metadata | `structured_data.video_extraction` | Frame counts, region detection, threshold |
| Intermediate frames | Deleted after PDF generation | Saves disk space |

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
variance analysis. For split-screen formats, manual `slide_region` override may
be needed — pass it as a parameter.

## Tuning the Hash Threshold

The `hash_threshold` parameter controls deduplication aggressiveness:

| Value | Behavior | Best For |
|-------|----------|----------|
| 4-6 | Aggressive: merges similar slides | Dense meme-heavy talks where each slide is visually distinct |
| 8-10 | Moderate: good default | Most conference talks |
| 12-16 | Loose: keeps more variation | Progressive-reveal-heavy talks (table rows appearing one-by-one) |

For talks in the speaker's mode (a) polemic style with progressive reveals,
use threshold 12. For demo-heavy or minimal-slide talks, use 8.

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
  slide with different speaker positions as different slides. Increase threshold.
- **Animated slides**: Animations within a single slide produce multiple frames.
  The dedup catches most of these, but fast animations at exactly the 2-second
  boundary may produce duplicates. Not a significant issue in practice.
- **Progressive reveals**: The speaker's talks frequently use progressive reveals
  (table rows appearing one-by-one). These ARE different slides rhetorically and
  SHOULD be kept as separate pages. The default threshold of 8-12 handles this
  correctly — each reveal step looks sufficiently different.
- **Low-quality uploads**: Some older conference videos are 360p or lower. Frame
  extraction still works but slide text may be unreadable. Flag these with
  `video_quality: "low"` in structured_data.
- **No audio sync**: Frame timestamps are not correlated with transcript timestamps.
  The subagent must use content matching (reading slide text and matching to
  transcript passages) rather than time alignment.
