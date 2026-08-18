#!/usr/bin/env python3
"""Extract scoped slide-region and context artifacts from conference videos.

Downloads frames via ffmpeg, resolves a slide-region crop, deduplicates using
perceptual hashing, and writes separately scoped slide-region/context PDFs.

Usage:
    video-slide-extraction.py <video> <outdir> <youtube_id> [--fps 0.5]
                              [--threshold 8]
                              [--region auto|none|LEFT,TOP,RIGHT,BOTTOM]
                              [--region-verified]
                              [--no-context-pdf]

    <video>       Path to downloaded MP4 video
    <outdir>      Directory for intermediate files and output artifacts
    <youtube_id>  YouTube video ID (used for naming the output PDF)
    --fps         Frames per second to extract (default: 0.5 = 1 frame per 2s)
    --threshold   Largest perceptual-hash distance treated as the same slide
                  (default: 8). Higher values merge more and keep fewer frames.
    --region      Crop used for hashing: auto-detect, none, or four normalized
                  coordinates (default: auto)
    --region-verified
                  Assert that a manually supplied crop was visually verified
    --no-context-pdf
                  Omit the extra full-frame context PDF after a verified manual
                  crop; review-required runs always preserve context

Examples:
    video-slide-extraction.py /vault/video.mp4 /vault/output AbCdEfGhI_1
    video-slide-extraction.py /vault/video.mp4 /vault/output AbCdEfGhI_1 --fps 0.5 --threshold 12
"""

import argparse
import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile

from artifact_locator import ArtifactLocatorError, materialize_native_root
from ingress_contract import YOUTUBE_ID_RE
from video_evidence import (
    VideoEvidenceAssessment,
    VideoEvidenceError,
    build_video_source_receipt,
    video_source_receipt_generation_drift,
)

# Pipeline version — stamped into every video-extracted vault entry (DB row +
# PDF metadata) so artifacts record which extraction iteration produced them.
# Bump this whenever extraction BEHAVIOR changes: default --fps or --threshold,
# the download tier, region-detection logic, dedup hashing, or PDF assembly.
# See skills/vault-ingress/references/video-slide-extraction.md ("Pipeline
# Versioning") for the policy.
PIPELINE_VERSION = "0.13.0"

# Shape version of the structured_data.video_extraction record (distinct from
# PIPELINE_VERSION, which tracks extractor behavior — this tracks the record's
# field shape). Bump on any field add/remove/rename. Records written before this
# field existed have no schema_version and are read as the legacy shape (0).
# See skills/vault-ingress/references/schemas-db.md ("Video Extraction Output Schema").
SCHEMA_VERSION = 4

VIDEO_DEPENDENCY_INSTALL = (
    'pip install "ImageHash==4.3.2" "numpy==2.2.6" "Pillow==12.3.0" "filelock==3.32.2"'
)

# Heavy deps are only needed for the extraction pipeline itself. Import them
# without exiting on failure so the module stays importable (and --version /
# --help stay answerable) in a minimal environment. main() enforces presence
# before any extraction runs.
try:
    import imagehash
    import numpy as _numpy_dependency
    from filelock import FileLock
    from PIL import Image

    _DEPS_ERROR = None
except ImportError as exc:
    imagehash = None
    _numpy_dependency = None
    FileLock = None
    Image = None
    _DEPS_ERROR = exc


NormalizedSlideRegion = tuple[float, float, float, float]


def validate_youtube_id(value: object) -> str:
    """Return one canonical ingress YouTube ID or fail with a closed reason."""
    if not isinstance(value, str) or YOUTUBE_ID_RE.fullmatch(value) is None:
        raise ValueError("youtube_id_invalid")
    return value


class VideoSourceLineageError(RuntimeError):
    """No derivative could be bound to one exact source-video generation.

    Raised instead of returning a manifest. A schema-4 record exists only when
    the engine-owned receipt was captured around the same extraction run, so a
    run that cannot prove that produces no record at all.
    """

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = dict(details or {})


def _capture_source_receipt(assessment, source_video_path):
    """Return the engine-owned receipt for the exact source generation."""
    try:
        probe = assessment.probe(source_video_path)
    except VideoEvidenceError as exc:
        raise VideoSourceLineageError(
            "source video did not pass bounded evidence inspection",
            reason_code=exc.reason_code,
            details=dict(exc.details),
        ) from exc
    return build_video_source_receipt(probe)


def _require_stable_source(assessment, source_video_path, source_receipt):
    """Fail the run when the source changed while derivatives were produced."""
    try:
        probe = assessment.probe(source_video_path)
    except VideoEvidenceError as exc:
        raise VideoSourceLineageError(
            "source video became uninspectable during extraction",
            reason_code=exc.reason_code,
            details=dict(exc.details),
        ) from exc
    drift = video_source_receipt_generation_drift(source_receipt, probe)
    if drift:
        raise VideoSourceLineageError(
            "source video was replaced during extraction",
            reason_code="video_source_replaced_during_extraction",
            details={"drift": list(drift)},
        )


def _discard_unbound_artifacts(staged):
    """Drop every stage this run wrote, leaving prior derivatives untouched."""
    for path in staged:
        _remove_stale_pdf_stage(path)


def _commit_bound_artifacts(staged):
    """Publish this run's staged derivatives once the binding is proven.

    Several destinations cannot be replaced in one portable atomic rename, so
    each publish moves the prior version aside first and a failure part-way
    puts every already-replaced destination back. Callers see the whole set
    published or none of it — never one run's slide-region PDF beside another
    run's context PDF.
    """
    replaced: list[tuple[str, str | None]] = []
    try:
        for path in staged:
            backup = _pdf_backup_path(path)
            _remove_regular_file(backup)
            try:
                os.replace(path, backup)
            except FileNotFoundError:
                # Nothing to put back, which is itself state worth recording.
                backup = None
                _mark_pdf_absent(path)
            # Recorded before the publish, not after: the prior version is
            # already moved aside, so a failure in the publish itself still has
            # to put it back.
            replaced.append((path, backup))
            commit_pdf_stage(path)
    except OSError:
        for path, backup in reversed(replaced):
            if backup is None:
                _remove_regular_file(path)
                _clear_pdf_absent_marker(path)
                continue
            os.replace(backup, path)
        raise
    for path, backup in replaced:
        if backup is None:
            _clear_pdf_absent_marker(path)
        else:
            _remove_regular_file(backup)


def _confined_output_path(output_root: str, filename: str) -> str:
    """Return a derived output that remains under the canonical authorized root."""
    lexical_path = os.path.join(output_root, filename)
    candidate = os.path.realpath(lexical_path)
    try:
        common = os.path.commonpath((output_root, candidate))
    except ValueError:
        common = ""
    if os.path.normcase(common) != os.path.normcase(output_root):
        raise ValueError("video_output_path_escape")
    if os.path.lexists(lexical_path) and (
        os.path.islink(lexical_path) or not os.path.isfile(lexical_path)
    ):
        raise ValueError("video_output_leaf_invalid")
    return candidate


def _require_image_dependencies():
    """Return imported image modules or fail clearly for direct callers."""
    if Image is None or imagehash is None or _numpy_dependency is None:
        raise RuntimeError(f"Install dependencies: {VIDEO_DEPENDENCY_INSTALL}") from (
            _DEPS_ERROR
        )
    return Image, imagehash


def _video_run_lock(path):
    """Return the declared cross-platform lock without burdening --version."""
    if FileLock is None:
        raise RuntimeError(f"Install dependencies: {VIDEO_DEPENDENCY_INSTALL}") from (
            _DEPS_ERROR
        )
    return FileLock(path)


def _video_run_lock_path(output_dir: str, youtube_id: str) -> str:
    """Map one local output identity to a stable OS-temporary lock file."""
    identity = (
        os.fsencode(os.path.normcase(output_dir)) + b"\0" + youtube_id.encode("ascii")
    )
    lock_name = f"{hashlib.sha256(identity).hexdigest()}.lock"
    lock_root = os.path.join(tempfile.gettempdir(), "speaker-toolkit-video-locks")
    os.makedirs(lock_root, exist_ok=True)
    return os.path.join(lock_root, lock_name)


def validate_slide_region(region) -> NormalizedSlideRegion:
    """Return a normalized manual crop or raise ValueError.

    Coordinates are fractions of the source frame in Pillow crop order:
    (left, upper, right, lower). Keeping this validation pure makes the CLI and
    direct Python entry point enforce the same geometry contract.
    """
    if not isinstance(region, (tuple, list)) or len(region) != 4:
        raise ValueError(
            "manual slide region must contain four coordinates: LEFT,TOP,RIGHT,BOTTOM"
        )
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in region
    ):
        raise ValueError("manual slide-region coordinates must be numbers")
    left, upper, right, lower = (float(value) for value in region)
    if not (0.0 <= left < right <= 1.0 and 0.0 <= upper < lower <= 1.0):
        raise ValueError(
            "manual slide region must satisfy "
            "0 <= LEFT < RIGHT <= 1 and 0 <= TOP < BOTTOM <= 1"
        )
    return left, upper, right, lower


def parse_slide_region(value: str) -> str | NormalizedSlideRegion:
    """Parse --region as auto, none, or normalized crop coordinates."""
    normalized = value.strip().lower()
    if normalized in ("auto", "none"):
        return normalized
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "--region must be auto, none, or LEFT,TOP,RIGHT,BOTTOM"
        )
    try:
        region = tuple(float(part) for part in parts)
        return validate_slide_region(region)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def extract_frames(video_path, frames_dir, fps=0.5):
    """Extract frames into one empty workspace and enumerate them literally."""
    video_path = canonical_path(video_path)
    frames_dir = canonical_path(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)
    with os.scandir(frames_dir) as entries:
        if next(entries, None) is not None:
            raise RuntimeError("frame workspace is not empty")
    output_pattern = os.path.join(frames_dir, "frame_%05d.jpg")
    completed = subprocess.run(
        [
            "ffmpeg",
            "-i",
            video_path,
            "-vf",
            f"fps={fps}",
            "-q:v",
            "2",
            output_pattern,
            "-y",
            "-loglevel",
            "warning",
        ],
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with exit status {completed.returncode}")
    numbered_frames = []
    with os.scandir(frames_dir) as entries:
        for entry in entries:
            frame_number = entry.name[len("frame_") : -len(".jpg")]
            if (
                entry.is_file(follow_symlinks=False)
                and entry.name.startswith("frame_")
                and entry.name.endswith(".jpg")
                and frame_number.isdigit()
            ):
                numbered_frames.append((int(frame_number), entry.name, entry.path))
    frames = [path for _, _, path in sorted(numbered_frames)]
    print(f"  Extracted {len(frames)} frames", file=sys.stderr)
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
                    if (
                        0 <= rr < h
                        and 0 <= cc < w
                        and mask[rr, cc]
                        and not seen[rr, cc]
                    ):
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
_MIN_REGION_AREA_FRAC = 0.15  # smaller than this is a slide element, not a slide
_MIN_REGION_ASPECT = 1.0  # 4:3 is 1.33, 16:9 is 1.78; allow margin either way
_MAX_REGION_ASPECT = 2.4


def _largest_rectangular_component(
    mask,
    min_fill=0.5,
    min_area_frac=_MIN_REGION_AREA_FRAC,
    min_aspect=_MIN_REGION_ASPECT,
    max_aspect=_MAX_REGION_ASPECT,
):
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


def detect_slide_region(frames, sample_size=10) -> NormalizedSlideRegion | None:
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
    pil_image, _ = _require_image_dependencies()

    # Sample evenly spaced frame pairs
    step = max(1, len(frames) // sample_size)
    diffs = []

    for i in range(0, len(frames) - step, step):
        with pil_image.open(frames[i]) as source1:
            with source1.convert("L") as gray1:
                with gray1.resize((320, 180)) as resized1:
                    img1 = np.array(resized1)
        with pil_image.open(frames[i + step]) as source2:
            with source2.convert("L") as gray2:
                with gray2.resize((320, 180)) as resized2:
                    img2 = np.array(resized2)
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

    print(
        f"  Detected slide region: {region[0]:.0%}-{region[2]:.0%} horizontal, "
        f"{region[1]:.0%}-{region[3]:.0%} vertical ({area:.0%} of frame)",
        file=sys.stderr,
    )
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


def canonical_path(path):
    """Return a native absolute, symlink-resolved path for durable provenance."""
    try:
        native = materialize_native_root(path)
    except ArtifactLocatorError as exc:
        raise ValueError(
            f"artifact path must be native absolute ({exc.reason_code})"
        ) from None
    return os.path.realpath(os.fspath(native))


def deduplicate_frames(frames, slide_region=None, hash_threshold=8):
    """Deduplicate consecutive similar frames using perceptual hashing.

    Returns list of (frame_path, frame_index) for retained unique frames.
    hash_threshold is the largest distance still treated as the same slide.
    Because a frame is kept only when distance > threshold, higher values merge
    more aggressively and keep fewer variants:
      - 4-6: conservative merging; preserves reveals but keeps more motion noise
      - 8-12: moderate; 8 is the default for most talks
      - 14+: aggressive merging; reduces moving-overlay duplicates but risks
        merging progressive reveals or visually similar authored slides
    """
    unique_frames = []
    prev_hash = None
    if not frames:
        print("  Deduplicated: 0 frames -> 0 unique frames", file=sys.stderr)
        return unique_frames
    pil_image, perceptual_hash = _require_image_dependencies()

    for i, frame_path in enumerate(frames):
        with pil_image.open(frame_path) as source:
            # Hash the CROPPED region (slide only, not speaker PiP).
            cropped = crop_frame(source, slide_region)
            try:
                h = perceptual_hash.phash(cropped, hash_size=16)
            finally:
                if cropped is not source:
                    cropped.close()

        if prev_hash is None or abs(h - prev_hash) > hash_threshold:
            unique_frames.append((frame_path, i))
            prev_hash = h

    print(
        f"  Deduplicated: {len(frames)} frames -> {len(unique_frames)} unique frames",
        file=sys.stderr,
    )
    return unique_frames


def select_slide_region(
    frames, requested: str | NormalizedSlideRegion = "auto", verified=False
) -> tuple[NormalizedSlideRegion | None, dict]:
    """Resolve the hashing crop and return it with explicit provenance.

    Auto-detection is always unverified: the heuristic can select a presenter's
    torso on a room recording. A manual crop is marked verified only when the
    caller explicitly says it was checked. `none` disables cropping.
    """
    if requested == "auto":
        if verified:
            raise ValueError(
                "slide_region_verified requires a manual region; an auto-detected "
                "crop is a hint until someone checks it"
            )
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
                "applies no crop"
            )
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


def review_reason_for_region(region, provenance):
    """Explain why a region result may or may not support authored-slide trust."""
    method = provenance["slide_region_method"]
    verified = provenance["slide_region_verified"]
    if region is not None and method == "manual" and verified:
        return None
    if region is None:
        return (
            "No verified slide region is available; the PDF is full-frame context "
            "only until an operator verifies a manual region."
        )
    if method == "auto":
        return (
            "The auto-detected crop is unverified; inspect it against the source "
            "and context, then rerun with a verified manual region."
        )
    return (
        "The manual crop was not marked visually verified; review it and rerun "
        "with --region-verified before promotion."
    )


_PDF_STAGE_SUFFIX = ".speaker-toolkit-stage.tmp"
_PDF_BACKUP_SUFFIX = ".speaker-toolkit-prior.tmp"
_PDF_ABSENT_SUFFIX = ".speaker-toolkit-absent.tmp"


def _pdf_stage_path(output_pdf: str) -> str:
    """Return the deterministic stage owned by one locked PDF destination."""
    return os.path.join(
        os.path.dirname(output_pdf),
        f".{os.path.basename(output_pdf)}{_PDF_STAGE_SUFFIX}",
    )


def _pdf_backup_path(output_pdf: str) -> str:
    """Return the deterministic prior-version slot for one PDF destination."""
    return os.path.join(
        os.path.dirname(output_pdf),
        f".{os.path.basename(output_pdf)}{_PDF_BACKUP_SUFFIX}",
    )


def _remove_regular_file(path: str) -> None:
    """Unlink one file this run owns, tolerating an already-absent leaf."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _pdf_absent_marker_path(output_pdf: str) -> str:
    """Return the deterministic "held nothing" marker for one destination."""
    return os.path.join(
        os.path.dirname(output_pdf),
        f".{os.path.basename(output_pdf)}{_PDF_ABSENT_SUFFIX}",
    )


def _require_regular_recovery_leaf(path: str) -> None:
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise ValueError("video_pdf_recovery_leaf_invalid")


def _mark_pdf_absent(output_pdf: str) -> None:
    """Record that this destination held nothing before the publish.

    Without it, a process killed after this destination publishes and before
    the run completes leaves a PDF the next run cannot tell from a prior
    version worth keeping.
    """
    marker = _pdf_absent_marker_path(output_pdf)
    with open(marker, "wb") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _clear_pdf_absent_marker(output_pdf: str) -> None:
    _remove_regular_file(_pdf_absent_marker_path(output_pdf))


def _remove_stale_pdf_stage(output_pdf: str) -> None:
    """Reclaim the exact stage left by an interrupted prior run."""
    try:
        os.unlink(_pdf_stage_path(output_pdf))
    except FileNotFoundError:
        pass
    except IsADirectoryError:
        raise ValueError("video_pdf_stage_invalid") from None


def _recover_stale_pdf_publish(output_pdf: str) -> None:
    """Undo a publish a killed process left half-applied at this destination.

    Both markers exist only inside one run's publish, so finding either means
    that run never completed and never wrote a manifest. The destination is
    put back to what a completed run last left there: the prior version, or
    nothing at all.
    """
    marker = _pdf_absent_marker_path(output_pdf)
    if os.path.exists(marker):
        _require_regular_recovery_leaf(marker)
        _remove_regular_file(output_pdf)
        _remove_regular_file(marker)
        return
    backup = _pdf_backup_path(output_pdf)
    if not os.path.exists(backup):
        return
    _require_regular_recovery_leaf(backup)
    os.replace(backup, output_pdf)


def _open_pdf_stage(output_pdf: str):
    """Open a fresh stage with normal umask mode or the prior PDF's mode."""
    prior_mode = None
    try:
        metadata = os.stat(output_pdf, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("video_output_leaf_invalid")
        prior_mode = stat.S_IMODE(metadata.st_mode)

    _remove_stale_pdf_stage(output_pdf)
    staged_path = _pdf_stage_path(output_pdf)
    staged = open(staged_path, "x+b")
    if prior_mode is not None:
        try:
            os.chmod(staged_path, prior_mode)
        except OSError:
            staged.close()
            _remove_stale_pdf_stage(output_pdf)
            raise
    return staged_path, staged


def commit_pdf_stage(output_pdf: str) -> None:
    """Publish one staged derivative over its destination."""
    os.replace(_pdf_stage_path(output_pdf), output_pdf)


def combine_to_pdf(
    unique_frames,
    output_pdf,
    slide_region=None,
    artifact_scope=None,
    source_video_id=None,
    crop_method="none",
    crop_verified=False,
    commit=True,
):
    """Write retained video frames as one explicitly scoped PDF artifact.

    ``slide_region`` is applied to the saved pages, not only to the hashes.
    Callers write a separate ``full_frame_context`` artifact when room or PiP
    context is useful. PDF metadata names the scope so a context artifact can
    never masquerade as an authored deck after it is separated from the JSON.

    ``commit=False`` leaves the finished pages in this destination's stage and
    returns the path they are staged for. A caller running several derivatives
    under one source binding uses it to hold every replacement until the whole
    run is proven, so a failed re-extraction cannot destroy the artifacts a
    previous run published. ``commit_pdf_stage`` publishes one such stage.
    """
    if artifact_scope is None:
        artifact_scope = (
            "slide_region" if slide_region is not None else "full_frame_context"
        )
    if artifact_scope not in ("slide_region", "full_frame_context"):
        raise ValueError(f"unknown artifact scope: {artifact_scope!r}")
    if artifact_scope == "slide_region" and slide_region is None:
        raise ValueError("slide_region artifacts require a physical crop")
    if artifact_scope == "full_frame_context" and slide_region is not None:
        raise ValueError("full_frame_context artifacts must preserve the full frame")
    if source_video_id is not None:
        source_video_id = validate_youtube_id(source_video_id)

    if not unique_frames:
        print("  WARNING: No unique frames found", file=sys.stderr)
        return None

    images = []
    pil_image, _ = _require_image_dependencies()
    staged_path = None
    try:
        for frame_path, _ in unique_frames:
            with pil_image.open(frame_path) as source:
                cropped = crop_frame(source, slide_region)
                try:
                    images.append(cropped.convert("RGB"))
                finally:
                    if cropped is not source:
                        cropped.close()

        if not images:
            print("  WARNING: No unique frames found", file=sys.stderr)
            return None

        output_pdf = canonical_path(output_pdf)
        output_parent = os.path.dirname(output_pdf)
        os.makedirs(output_parent, exist_ok=True)
        producer = f"speaker-toolkit/video-slide-extraction {PIPELINE_VERSION}"
        if artifact_scope == "full_frame_context":
            title = f"{source_video_id or 'video'} full-frame context"
            subject = "Full-frame video context; not authored slides"
        else:
            title = f"{source_video_id or 'video'} cropped slide region"
            trust = "verified" if crop_verified else "unverified; review required"
            subject = (
                f"Cropped slide-region frames from video; crop method={crop_method}; "
                f"{trust}"
            )

        staged_path, staged = _open_pdf_stage(output_pdf)
        with staged:
            images[0].save(
                staged,
                format="PDF",
                save_all=True,
                append_images=images[1:],
                producer=producer,
                creator=producer,
                title=title,
                subject=subject,
            )
            staged.flush()

        size_mb = os.path.getsize(staged_path) / (1024 * 1024)
        if commit:
            os.replace(staged_path, output_pdf)
        staged_path = None
        state = "Saved" if commit else "Staged"
        print(
            f"  {state} {artifact_scope} PDF: {output_pdf} "
            f"({len(images)} pages, {size_mb:.1f} MB)",
            file=sys.stderr,
        )
        return output_pdf
    finally:
        if staged_path is not None:
            try:
                os.unlink(staged_path)
            except FileNotFoundError:
                pass
        for image in images:
            image.close()


def retained_frame_provenance(unique_frames, fps):
    """Map PDF page order back to zero-based sampled-frame positions."""
    if fps <= 0:
        raise ValueError("fps must be greater than zero")
    return [
        {
            "page_number": page_number,
            "frame_index": frame_index,
            "timestamp_seconds": round(frame_index / fps, 3),
        }
        for page_number, (_, frame_index) in enumerate(unique_frames, start=1)
    ]


def artifact_record(
    path,
    artifact_scope,
    page_count,
    source_video_id,
    source_video_path,
    source_receipt,
    crop_method="none",
    crop_verified=False,
    trusted_for_authored_slide_analysis=False,
):
    """Build a self-describing PDF artifact record for the extraction result.

    ``source_receipt`` is the run's engine-owned source receipt. Every
    derivative carries it, so a PDF separated from the manifest still names the
    exact source bytes it came from.
    """
    if artifact_scope not in ("slide_region", "full_frame_context"):
        raise ValueError(f"unknown artifact scope: {artifact_scope!r}")
    if artifact_scope == "full_frame_context" and (
        crop_method != "none" or crop_verified or trusted_for_authored_slide_analysis
    ):
        raise ValueError("full-frame context cannot be cropped or trusted as slides")
    if artifact_scope == "slide_region" and crop_method not in ("auto", "manual"):
        raise ValueError("slide-region artifacts require an auto or manual crop")
    if trusted_for_authored_slide_analysis and not (
        crop_method == "manual" and crop_verified
    ):
        raise ValueError("authored-slide trust requires a verified manual crop")
    source_video_id = validate_youtube_id(source_video_id)
    return {
        "path": canonical_path(path),
        "artifact_scope": artifact_scope,
        "page_count": page_count,
        "source_video_id": source_video_id,
        "source_video_path": canonical_path(source_video_path),
        "source_receipt": copy.deepcopy(source_receipt),
        "crop_method": crop_method,
        "crop_verified": bool(crop_verified),
        "trusted_for_authored_slide_analysis": bool(
            trusted_for_authored_slide_analysis
        ),
    }


def _extract_slides_in_workspace(
    video_path,
    output_dir,
    youtube_id,
    frames_dir,
    source_receipt,
    published,
    fps=0.5,
    hash_threshold=8,
    slide_region: str | NormalizedSlideRegion = "auto",
    slide_region_verified=False,
    include_context_pdf=True,
):
    """Full pipeline: frames -> detect region -> dedup -> scoped PDF artifacts.

    Args:
        video_path: Path to downloaded MP4
        output_dir: Directory for intermediate files and output PDF
        youtube_id: YouTube video ID (used for naming)
        source_receipt: Engine-owned receipt for the exact source generation,
                        stamped onto the manifest and every derivative record.
        published: Caller-owned list this appends each staged PDF path to the
                   moment its pages land. The caller publishes them once the
                   source binding holds, and drops the stages otherwise, so a
                   failed run never disturbs a prior run's artifacts.
        fps: Frames per second to extract (0.5 = 1 frame per 2 seconds)
        hash_threshold: Largest hash distance treated as the same slide. Higher
                        values merge more and keep fewer frames.
        slide_region: "auto", "none", or normalized (left, upper, right, lower)
                      coordinates used for hashing.
        slide_region_verified: True only when a manual crop was visually checked.
        include_context_pdf: Preserve an additional full-frame PDF after a verified
                             crop. Review-required results always keep context even
                             when this is False.

    Returns:
        dict with extraction results for structured_data
    """
    youtube_id = validate_youtube_id(youtube_id)
    if fps <= 0:
        raise ValueError("fps must be greater than zero")
    output_dir = canonical_path(output_dir)
    source_video_path = canonical_path(video_path)
    slide_pdf = _confined_output_path(
        output_dir,
        f"{youtube_id}.slide-region.pdf",
    )
    context_pdf = _confined_output_path(output_dir, f"{youtube_id}.context.pdf")

    print(f"Extracting video artifacts from {youtube_id}...", file=sys.stderr)

    # Step 2: Extract frames
    frames = extract_frames(source_video_path, frames_dir, fps=fps)
    if not frames:
        return {
            "slide_source": "video_extracted",
            "schema_version": SCHEMA_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "source_video_id": youtube_id,
            "source_video_path": source_video_path,
            "source_receipt": copy.deepcopy(source_receipt),
            "total_frames_extracted": 0,
            "unique_frame_count": 0,
            "authored_slide_count": None,
            "retained_frames": [],
            "artifacts": [],
            "review_required": True,
            "review_reason": "No frames were extracted.",
            "error": "No frames extracted",
        }

    # Step 3: Resolve the slide region. Auto-detection is a hint, while a manual
    # crop carries explicit verification provenance.
    resolved_region, region_provenance = select_slide_region(
        frames, slide_region, slide_region_verified
    )

    # Step 4: Deduplicate
    unique_frames = deduplicate_frames(frames, resolved_region, hash_threshold)

    # Step 5: Write separately scoped artifacts. A crop is saved into the
    # slide-region PDF itself; the uncropped broadcast frame, when retained, is
    # a context artifact and is never labeled as authored slides.
    trusted_slide_evidence = bool(
        resolved_region is not None
        and region_provenance["slide_region_method"] == "manual"
        and region_provenance["slide_region_verified"]
    )
    review_reason = review_reason_for_region(resolved_region, region_provenance)
    artifacts = []
    if resolved_region is not None:
        slide_pdf_path = combine_to_pdf(
            unique_frames,
            slide_pdf,
            resolved_region,
            artifact_scope="slide_region",
            source_video_id=youtube_id,
            crop_method=region_provenance["slide_region_method"],
            crop_verified=region_provenance["slide_region_verified"],
            commit=False,
        )
        if slide_pdf_path:
            published.append(slide_pdf_path)
            artifacts.append(
                artifact_record(
                    slide_pdf_path,
                    "slide_region",
                    len(unique_frames),
                    youtube_id,
                    source_video_path,
                    source_receipt,
                    crop_method=region_provenance["slide_region_method"],
                    crop_verified=region_provenance["slide_region_verified"],
                    trusted_for_authored_slide_analysis=trusted_slide_evidence,
                )
            )

    # With no region, the full frame is the only visual evidence and must be
    # preserved as context. With a region, callers may explicitly omit this
    # additional derivative; the source video itself is never deleted here.
    if include_context_pdf or not trusted_slide_evidence:
        context_pdf_path = combine_to_pdf(
            unique_frames,
            context_pdf,
            artifact_scope="full_frame_context",
            source_video_id=youtube_id,
            commit=False,
        )
        if context_pdf_path:
            published.append(context_pdf_path)
            artifacts.append(
                artifact_record(
                    context_pdf_path,
                    "full_frame_context",
                    len(unique_frames),
                    youtube_id,
                    source_video_path,
                    source_receipt,
                )
            )

    result = {
        "slide_source": "video_extracted",
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "source_video_id": youtube_id,
        "source_video_path": source_video_path,
        "source_receipt": copy.deepcopy(source_receipt),
        "total_frames_extracted": len(frames),
        "unique_frame_count": len(unique_frames),
        # Frame/page count is not an authored slide count: animations, camera
        # motion, missed samples, and dedup thresholds make that unknowable here.
        "authored_slide_count": None,
        "hash_threshold_used": hash_threshold,
        "slide_region": resolved_region,
        "fps_used": fps,
        "retained_frames": retained_frame_provenance(unique_frames, fps),
        "artifacts": artifacts,
        "review_required": review_reason is not None,
        "review_reason": review_reason,
        **region_provenance,
    }

    print(f"  Done: {len(unique_frames)} unique frames retained", file=sys.stderr)
    return result


def extract_slides_from_video(
    video_path,
    output_dir,
    youtube_id,
    fps=0.5,
    hash_threshold=8,
    slide_region: str | NormalizedSlideRegion = "auto",
    slide_region_verified=False,
    include_context_pdf=True,
):
    """Run one extraction bound end to end to one exact source generation.

    The source is probed before any frame is sampled and again after every
    derivative is written. One assessment owns both probes, so the closing
    probe costs a stat when the generation held and a full re-probe exactly
    when it did not. Any drift discards the derivatives and fails the run —
    a manifest is never written against bytes it did not come from.

    Derivatives stay staged until the closing probe passes, so no exit path can
    leave a half-bound PDF behind and a failed re-extraction leaves the previous
    run's artifacts exactly as it found them.
    """
    youtube_id = validate_youtube_id(youtube_id)
    if fps <= 0:
        raise ValueError("fps must be greater than zero")
    output_dir = canonical_path(output_dir)
    source_video_path = canonical_path(video_path)
    os.makedirs(output_dir, exist_ok=True)
    run_lock = _video_run_lock_path(output_dir, youtube_id)

    with _video_run_lock(run_lock):
        assessment = VideoEvidenceAssessment()
        source_receipt = _capture_source_receipt(assessment, source_video_path)
        for filename in (
            f"{youtube_id}.slide-region.pdf",
            f"{youtube_id}.context.pdf",
        ):
            destination = _confined_output_path(output_dir, filename)
            _recover_stale_pdf_publish(destination)
            _remove_stale_pdf_stage(destination)
        published: list[str] = []
        bound = False
        try:
            with tempfile.TemporaryDirectory(
                prefix="speaker-toolkit-video-frames-"
            ) as frames_dir:
                result = _extract_slides_in_workspace(
                    source_video_path,
                    output_dir,
                    youtube_id,
                    frames_dir,
                    source_receipt,
                    published,
                    fps=fps,
                    hash_threshold=hash_threshold,
                    slide_region=slide_region,
                    slide_region_verified=slide_region_verified,
                    include_context_pdf=include_context_pdf,
                )
            _require_stable_source(assessment, source_video_path, source_receipt)
            _commit_bound_artifacts(published)
            bound = True
        finally:
            if not bound:
                _discard_unbound_artifacts(published)
        return result


def main():
    parser = argparse.ArgumentParser(
        description="Extract slide images from conference talk videos."
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the pipeline version as JSON and exit",
    )
    parser.add_argument("video", nargs="?", help="Path to downloaded MP4 video")
    parser.add_argument(
        "outdir", nargs="?", help="Directory for intermediate files and output PDF"
    )
    parser.add_argument(
        "youtube_id", nargs="?", help="YouTube video ID (used for naming)"
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=0.5,
        help="Frames per second to extract (default: 0.5)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=8,
        help="largest hash distance treated as the same slide; "
        "higher merges more and keeps fewer frames (default: 8)",
    )
    parser.add_argument(
        "--region",
        type=parse_slide_region,
        default="auto",
        metavar="auto|none|LEFT,TOP,RIGHT,BOTTOM",
        help="crop used for hashing: auto-detect, none, or normalized coordinates",
    )
    parser.add_argument(
        "--region-verified",
        action="store_true",
        help="mark a manually supplied --region as visually verified",
    )
    parser.add_argument(
        "--no-context-pdf",
        action="store_false",
        dest="include_context_pdf",
        help="omit extra full-frame context after a verified manual crop",
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
        parser.error(
            "--region-verified requires manual LEFT,TOP,RIGHT,BOTTOM coordinates"
        )
    try:
        youtube_id = validate_youtube_id(args.youtube_id)
    except ValueError as exc:
        parser.error(str(exc))

    if _DEPS_ERROR is not None:
        print(
            json.dumps({"error": f"Install dependencies: {VIDEO_DEPENDENCY_INSTALL}"}),
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        result = extract_slides_from_video(
            args.video,
            args.outdir,
            youtube_id,
            fps=args.fps,
            hash_threshold=args.threshold,
            slide_region=args.region,
            slide_region_verified=args.region_verified,
            include_context_pdf=args.include_context_pdf,
        )
    except VideoSourceLineageError as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "reason_code": exc.reason_code,
                    "details": exc.details,
                }
            ),
            file=sys.stderr,
        )
        sys.exit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
