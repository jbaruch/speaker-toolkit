#!/usr/bin/env python3
"""Extract slide images from conference talk videos.

Downloads frames via ffmpeg, auto-detects the slide region, deduplicates
using perceptual hashing, and combines unique slides into a PDF.

Usage:
    video-slide-extraction.py <video> <outdir> <youtube_id> [--fps 0.5]
                              [--threshold 8]
                              [--region auto|none|LEFT,TOP,RIGHT,BOTTOM]
                              [--region-verified]

    <video>       Path to downloaded MP4 video
    <outdir>      Directory for intermediate files and output PDF
    <youtube_id>  YouTube video ID (used for naming the output PDF)
    --fps         Frames per second to extract (default: 0.5 = 1 frame per 2s)
    --threshold   Largest perceptual-hash distance treated as the same slide
                  (default: 8). Higher values merge more and keep fewer frames.
    --region      Crop used for hashing: auto-detect, none, or four normalized
                  coordinates (default: auto)
    --region-verified
                  Assert that a manually supplied crop was visually verified

Examples:
    video-slide-extraction.py video.mp4 output/ aBcDeFg
    video-slide-extraction.py video.mp4 output/ aBcDeFg --fps 0.5 --threshold 12
"""

import argparse
import glob
import json
import os
import sys

# Pipeline version — stamped into every video-extracted vault entry (DB row +
# PDF metadata) so artifacts record which extraction iteration produced them.
# Bump this whenever extraction BEHAVIOR changes: default --fps or --threshold,
# the download tier, region-detection logic, dedup hashing, or PDF assembly.
# See skills/vault-ingress/references/video-slide-extraction.md ("Pipeline
# Versioning") for the policy.
PIPELINE_VERSION = "0.9.0"

# Shape version of the structured_data.video_extraction record (distinct from
# PIPELINE_VERSION, which tracks extractor behavior — this tracks the record's
# field shape). Bump on any field add/remove/rename. Records written before this
# field existed have no schema_version and are read as the legacy shape (0).
# See skills/vault-ingress/references/schemas-db.md ("Video Extraction Output Schema").
SCHEMA_VERSION = 2

# Heavy deps are only needed for the extraction pipeline itself. Import them
# without exiting on failure so the module stays importable (and --version /
# --help stay answerable) in a minimal environment. main() enforces presence
# before any extraction runs.
try:
    import imagehash
    from PIL import Image
    _DEPS_ERROR = None
except ImportError as exc:
    imagehash = None
    Image = None
    _DEPS_ERROR = exc


def validate_slide_region(region):
    """Return a normalized manual crop or raise ValueError.

    Coordinates are fractions of the source frame in Pillow crop order:
    (left, upper, right, lower). Keeping this validation pure makes the CLI and
    direct Python entry point enforce the same geometry contract.
    """
    if not isinstance(region, (tuple, list)) or len(region) != 4:
        raise ValueError(
            "manual slide region must contain four coordinates: "
            "LEFT,TOP,RIGHT,BOTTOM")
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           for value in region):
        raise ValueError("manual slide-region coordinates must be numbers")
    left, upper, right, lower = (float(value) for value in region)
    if not (0.0 <= left < right <= 1.0 and 0.0 <= upper < lower <= 1.0):
        raise ValueError(
            "manual slide region must satisfy "
            "0 <= LEFT < RIGHT <= 1 and 0 <= TOP < BOTTOM <= 1")
    return left, upper, right, lower


def parse_slide_region(value):
    """Parse --region as auto, none, or normalized crop coordinates."""
    normalized = value.strip().lower()
    if normalized in ("auto", "none"):
        return normalized
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "--region must be auto, none, or LEFT,TOP,RIGHT,BOTTOM")
    try:
        region = tuple(float(part) for part in parts)
        return validate_slide_region(region)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


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


def _label_components(mask):
    """Label 4-connected True regions in a boolean mask.

    Implemented with an explicit stack rather than scipy.ndimage.label so the
    extractor keeps its declared dependency set (numpy/Pillow/imagehash); the
    mask is 180x320, so the cost is irrelevant.

    Yields (row_indices, col_indices) arrays per component.
    """
    import numpy as np

    seen = np.zeros(mask.shape, dtype=bool)
    h, w = mask.shape
    for r0 in range(h):
        for c0 in range(w):
            if not mask[r0, c0] or seen[r0, c0]:
                continue
            rows, cols, stack = [], [], [(r0, c0)]
            seen[r0, c0] = True
            while stack:
                r, c = stack.pop()
                rows.append(r)
                cols.append(c)
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < h and 0 <= cc < w and mask[rr, cc] and not seen[rr, cc]:
                        seen[rr, cc] = True
                        stack.append((rr, cc))
            yield np.array(rows), np.array(cols)


# A crop is only taken when the chosen component actually looks like a projected
# display. These bounds exist because component selection alone will happily
# return a text block inside a FULL-FRAME slide — cropping a deck into a fragment
# of itself and silently discarding the rest. Measured over 94 corpus decks,
# unconstrained selection produced boxes with aspect ratios from 0.32 to 9.45;
# the gate leaves 26. A missed crop leaves an over-count visible; a
# wrong crop destroys content, so these are deliberately strict.
_MIN_REGION_AREA_FRAC = 0.15   # smaller than this is a slide element, not a slide
_MIN_REGION_ASPECT = 1.0       # 4:3 is 1.33, 16:9 is 1.78; allow margin either way
_MAX_REGION_ASPECT = 2.4


def _largest_rectangular_component(mask, min_fill=0.5,
                                   min_area_frac=_MIN_REGION_AREA_FRAC,
                                   min_aspect=_MIN_REGION_ASPECT,
                                   max_aspect=_MAX_REGION_ASPECT):
    """Pick the component most likely to be the projected slide.

    A slide region is a solid rectangle that changes wholesale between slides, so
    its component nearly fills its own bounding box; a speaker picture-in-picture
    is an irregular blob of moving person and fills much less. Fill ratio
    separates those two. Area and aspect then reject the other failure mode —
    a localized text block inside a full-frame deck, which is rectangular and
    well-filled but is not the display.

    The mask is 320x180, so its pixel aspect equals the source frame's aspect for
    16:9 recordings and box_w/box_h is directly comparable to a display ratio.

    Returns (rmin, rmax, cmin, cmax) or None when nothing qualifies.
    """
    import numpy as np

    total = mask.size
    best, best_area = None, 0
    for rows, cols in _label_components(mask):
        rmin, rmax = int(rows.min()), int(rows.max())
        cmin, cmax = int(cols.min()), int(cols.max())
        box_h, box_w = rmax - rmin + 1, cmax - cmin + 1
        box_area = box_h * box_w
        if box_area / total < min_area_frac:
            continue
        # Fill ratio separates a solid slide rectangle from a person-shaped blob.
        if len(rows) / box_area < min_fill:
            continue
        # Aspect rejects strips and columns — neither is a projected display.
        if not (min_aspect <= box_w / box_h <= max_aspect):
            continue
        if box_area > best_area:
            best, best_area = (rmin, rmax, cmin, cmax), box_area
    return best


def detect_slide_region(frames, sample_size=10):
    """Auto-detect the slide region by analyzing variance across sample frames.

    Conference videos typically have a static border (conference branding,
    speaker PiP in a fixed corner) and a dynamic center (the slides).
    We find the bounding box of the high-variance region.

    Returns (left, upper, right, lower) as fraction of image dimensions,
    or None if slides appear to be full-frame.

    A RETURNED REGION IS NOT A VERIFIED ONE. Detection is reliable only for the
    extreme case it was built for: a broadcast composite where a fixed slide
    rectangle sits beside static venue furniture. On room recordings it can and
    does return the speaker — a torso is rectangular, well-filled, and passes
    every size and aspect gate a screen passes. Spot-checking 94 corpus decks by
    eye found correct screen crops and confident crops of a presenter's chest in
    the same pass. Treat the output as a hint to verify, never as ground truth,
    and never derive a slide count from a crop nobody looked at.

    KNOWN LIMIT — wide-angle room recordings are NOT reliably handled. Ambient
    motion clears the threshold across the frame and the largest plausible
    component is as often a person as a screen. Separating them needs a signal
    this function does not have (screen-edge geometry, projector luminance, or
    boundary stability across frames) plus ground truth to validate against.
    See references/video-slide-extraction.md.
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

    if not mask.any():
        return None  # No clear region detected

    # A broadcast composite has MORE than one moving thing: the slide rectangle
    # and a live speaker picture-in-picture, which are disjoint. Taking the
    # bounding box of every above-threshold pixel merges them into one box that
    # spans the frame, trips the >90% guard below, and returns None — so the
    # deck is never cropped and the deduper hashes the moving presenter. That is
    # how one 43-slide talk extracted to 963 pages. Pick the best single
    # component instead of boxing them all.
    component = _largest_rectangular_component(mask)
    if component is None:
        return None
    rmin, rmax, cmin, cmax = component

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
    hash_threshold is the largest distance still treated as the same slide.
    Because a frame is kept only when distance > threshold, higher values merge
    more aggressively and keep fewer variants:
      - 4-6: conservative merging; preserves reveals but keeps more motion noise
      - 8-12: moderate; 8 is the default for most talks
      - 14+: aggressive merging; reduces moving-overlay duplicates but risks
        merging progressive reveals or visually similar authored slides
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


def select_slide_region(frames, requested="auto", verified=False):
    """Resolve the hashing crop and return it with explicit provenance.

    Auto-detection is always unverified: the heuristic can select a presenter's
    torso on a room recording. A manual crop is marked verified only when the
    caller explicitly says it was checked. `none` disables cropping.
    """
    if requested == "auto":
        if verified:
            raise ValueError(
                "slide_region_verified requires a manual region; an auto-detected "
                "crop is a hint until someone checks it")
        region = detect_slide_region(frames)
        return region, {
            "slide_region_method": "auto",
            "slide_region_detected": region is not None,
            "slide_region_applied": region is not None,
            "slide_region_verified": False,
        }
    if requested == "none":
        if verified:
            raise ValueError(
                "slide_region_verified requires a manual region; --region none "
                "applies no crop")
        return None, {
            "slide_region_method": "none",
            "slide_region_detected": False,
            "slide_region_applied": False,
            "slide_region_verified": False,
        }

    region = validate_slide_region(requested)
    return region, {
        "slide_region_method": "manual",
        "slide_region_detected": False,
        "slide_region_applied": True,
        "slide_region_verified": bool(verified),
    }


def combine_to_pdf(unique_slides, output_pdf, slide_region=None):
    """Combine unique slide frames into a PDF.

    Saves FULL (uncropped) frames — the crop region was only used for
    hash comparison. The full frame preserves speaker PiP context which
    can be useful for analyzing co-presentation dynamics.

    Stamps PIPELINE_VERSION into the PDF's producer/creator metadata so the
    durable artifact itself records which extraction iteration produced it.
    """
    images = []
    for frame_path, _ in unique_slides:
        img = Image.open(frame_path).convert('RGB')
        images.append(img)

    if not images:
        print("  WARNING: No unique slides found")
        return None

    producer = f"speaker-toolkit/video-slide-extraction {PIPELINE_VERSION}"
    images[0].save(
        output_pdf, save_all=True, append_images=images[1:],
        producer=producer, creator=producer,
    )
    size_mb = os.path.getsize(output_pdf) / (1024 * 1024)
    print(f"  Saved PDF: {output_pdf} ({len(images)} pages, {size_mb:.1f} MB)")
    return output_pdf


def extract_slides_from_video(video_path, output_dir, youtube_id,
                               fps=0.5, hash_threshold=8,
                               slide_region="auto", slide_region_verified=False):
    """Full pipeline: frames -> detect region -> dedup -> PDF.

    Args:
        video_path: Path to downloaded MP4
        output_dir: Directory for intermediate files and output PDF
        youtube_id: YouTube video ID (used for naming)
        fps: Frames per second to extract (0.5 = 1 frame per 2 seconds)
        hash_threshold: Largest hash distance treated as the same slide. Higher
                        values merge more and keep fewer frames.
        slide_region: "auto", "none", or normalized (left, upper, right, lower)
                      coordinates used for hashing.
        slide_region_verified: True only when a manual crop was visually checked.

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

    # Step 3: Resolve the slide region. Auto-detection is a hint, while a manual
    # crop carries explicit verification provenance.
    slide_region, region_provenance = select_slide_region(
        frames, slide_region, slide_region_verified)

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
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "total_frames_extracted": len(frames),
        "unique_slides_count": len(unique_slides),
        "hash_threshold_used": hash_threshold,
        "slide_region": slide_region,
        "output_pdf": pdf_path,
        "fps_used": fps,
        **region_provenance,
    }

    print(f"  Done: {len(unique_slides)} unique slides extracted")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Extract slide images from conference talk videos."
    )
    parser.add_argument("--version", action="store_true",
                        help="Print the pipeline version as JSON and exit")
    parser.add_argument("video", nargs="?", help="Path to downloaded MP4 video")
    parser.add_argument("outdir", nargs="?",
                        help="Directory for intermediate files and output PDF")
    parser.add_argument("youtube_id", nargs="?",
                        help="YouTube video ID (used for naming)")
    parser.add_argument("--fps", type=float, default=0.5,
                        help="Frames per second to extract (default: 0.5)")
    parser.add_argument("--threshold", type=int, default=8,
                        help="largest hash distance treated as the same slide; "
                             "higher merges more and keeps fewer frames (default: 8)")
    parser.add_argument(
        "--region", type=parse_slide_region, default="auto",
        metavar="auto|none|LEFT,TOP,RIGHT,BOTTOM",
        help="crop used for hashing: auto-detect, none, or normalized coordinates",
    )
    parser.add_argument(
        "--region-verified", action="store_true",
        help="mark a manually supplied --region as visually verified",
    )
    args = parser.parse_args()

    # Structured version query — JSON, not prose, per script-delegation. Handled
    # before the dependency guard so the version stays queryable in a minimal env.
    if args.version:
        print(json.dumps({"pipeline_version": PIPELINE_VERSION}))
        return

    if None in (args.video, args.outdir, args.youtube_id):
        parser.error("video, outdir, and youtube_id are required")
    if args.region_verified and not isinstance(args.region, tuple):
        parser.error("--region-verified requires manual LEFT,TOP,RIGHT,BOTTOM coordinates")

    if _DEPS_ERROR is not None:
        print(json.dumps(
            {"error": "Install dependencies: pip install imagehash Pillow"}),
            file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.outdir, exist_ok=True)
    result = extract_slides_from_video(
        args.video, args.outdir, args.youtube_id,
        fps=args.fps, hash_threshold=args.threshold,
        slide_region=args.region, slide_region_verified=args.region_verified,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
