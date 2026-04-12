#!/usr/bin/env python3
"""Extract slide images from conference talk videos.

Downloads frames via ffmpeg, auto-detects the slide region, deduplicates
using perceptual hashing, and combines unique slides into a PDF.

Usage:
    video-slide-extraction.py <video> <outdir> <youtube_id> [--fps 0.5] [--threshold 8]

    <video>       Path to downloaded MP4 video
    <outdir>      Directory for intermediate files and output PDF
    <youtube_id>  YouTube video ID (used for naming the output PDF)
    --fps         Frames per second to extract (default: 0.5 = 1 frame per 2s)
    --threshold   Perceptual hash distance threshold for dedup (default: 8)

Examples:
    video-slide-extraction.py video.mp4 output/ aBcDeFg
    video-slide-extraction.py video.mp4 output/ aBcDeFg --fps 0.5 --threshold 12
"""

import argparse
import glob
import json
import os
import sys
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


def main():
    parser = argparse.ArgumentParser(
        description="Extract slide images from conference talk videos."
    )
    parser.add_argument("video", help="Path to downloaded MP4 video")
    parser.add_argument("outdir", help="Directory for intermediate files and output PDF")
    parser.add_argument("youtube_id", help="YouTube video ID (used for naming)")
    parser.add_argument("--fps", type=float, default=0.5,
                        help="Frames per second to extract (default: 0.5)")
    parser.add_argument("--threshold", type=int, default=8,
                        help="Perceptual hash distance threshold (default: 8)")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    result = extract_slides_from_video(
        args.video, args.outdir, args.youtube_id,
        fps=args.fps, hash_threshold=args.threshold
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
