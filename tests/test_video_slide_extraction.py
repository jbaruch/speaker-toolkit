"""Tests for video-slide-extraction.py — frame extraction, dedup, PDF output."""

import argparse
import json
import os
import shutil
import subprocess
import sys

import pytest
from PIL import Image

SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), os.pardir,
    "skills", "vault-ingress", "scripts", "video-slide-extraction.py",
)
SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), os.pardir,
    "skills", "vault-ingress", "references", "schemas-db.md",
)


def _artifact(result, scope):
    matches = [artifact for artifact in result["artifacts"]
               if artifact["artifact_scope"] == scope]
    assert len(matches) == 1, f"expected one {scope!r} artifact"
    return matches[0]


def _pdf_contains(raw, text):
    return text.encode() in raw or text.encode("utf-16-be") in raw


def test_crop_frame_none_region(video_slide_extraction):
    """No region → return original image unchanged."""
    img = Image.new("RGB", (1920, 1080), (128, 128, 128))
    result = video_slide_extraction.crop_frame(img, None)
    assert result.size == (1920, 1080)


def test_crop_frame_with_region(video_slide_extraction):
    """Crop to center 50% of the frame."""
    img = Image.new("RGB", (1000, 500), (128, 128, 128))
    region = (0.25, 0.25, 0.75, 0.75)
    result = video_slide_extraction.crop_frame(img, region)
    assert result.size == (500, 250)


def test_region_argument_accepts_modes_and_normalized_coordinates(
        video_slide_extraction):
    assert video_slide_extraction.parse_slide_region("auto") == "auto"
    assert video_slide_extraction.parse_slide_region("NONE") == "none"
    assert video_slide_extraction.parse_slide_region(
        "0.1,0.2,0.9,0.8") == (0.1, 0.2, 0.9, 0.8)


@pytest.mark.parametrize("value", [
    "0.1,0.2,0.9",
    "left,0.2,0.9,0.8",
    "0.9,0.2,0.1,0.8",
    "-0.1,0.2,0.9,0.8",
])
def test_region_argument_rejects_invalid_geometry(video_slide_extraction, value):
    with pytest.raises(argparse.ArgumentTypeError):
        video_slide_extraction.parse_slide_region(value)


def test_deduplicate_identical_frames(video_slide_extraction, tmp_path):
    """Identical frames should collapse to one."""
    frames = []
    for i in range(5):
        img = Image.new("RGB", (320, 180), (100, 100, 100))
        path = str(tmp_path / f"frame_{i:05d}.jpg")
        img.save(path)
        frames.append(path)
    unique = video_slide_extraction.deduplicate_frames(frames, hash_threshold=8)
    assert len(unique) == 1


def test_deduplicate_distinct_frames(video_slide_extraction, tmp_path):
    """Visually distinct frames should all be kept."""
    import numpy as np
    # Use patterned images (not solid) so JPEG compression preserves distinctness
    rng = np.random.RandomState(42)
    frames = []
    for i in range(3):
        arr = rng.randint(0, 256, (180, 320, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        path = str(tmp_path / f"frame_{i:05d}.png")
        img.save(path)  # PNG to avoid JPEG lossy compression
        frames.append(path)
    unique = video_slide_extraction.deduplicate_frames(frames, hash_threshold=8)
    assert len(unique) == 3


def test_higher_hash_threshold_monotonically_keeps_fewer_variants(
        video_slide_extraction, tmp_path, monkeypatch):
    """A frame is kept only when distance > threshold.

    Fixed distances make the direction deterministic: raising the threshold must
    merge more aggressively, never keep more visual variants. This guards the
    contract that the old docstring and reference described backwards.
    """
    frames = []
    for i in range(3):
        path = tmp_path / f"fixed_{i}.png"
        Image.new("RGB", (32, 18), (i * 40, 0, 0)).save(path)
        frames.append(str(path))

    class FakeHash:
        def __init__(self, value):
            self.value = value

        def __sub__(self, other):
            return self.value - other.value

    def retained(threshold):
        values = iter((0, 6, 12))
        monkeypatch.setattr(
            video_slide_extraction.imagehash, "phash",
            lambda image, hash_size: FakeHash(next(values)),
        )
        return len(video_slide_extraction.deduplicate_frames(
            frames, hash_threshold=threshold))

    assert [retained(4), retained(8), retained(16)] == [3, 2, 1]


def test_combine_to_pdf(video_slide_extraction, tmp_path):
    """Combine frames into a valid multi-page PDF."""
    frames = []
    for i in range(3):
        img = Image.new("RGB", (320, 180), (i * 80, 0, 0))
        path = str(tmp_path / f"frame_{i:05d}.jpg")
        img.save(path)
        frames.append((path, i))

    output = str(tmp_path / "slides.pdf")
    result = video_slide_extraction.combine_to_pdf(frames, output)
    assert result == output
    assert os.path.isfile(output)
    assert os.path.getsize(output) > 100


def test_combine_to_pdf_applies_crop_to_saved_pages(
        video_slide_extraction, tmp_path):
    """The slide crop must affect the durable PDF, not only the dedup hash."""
    frame = tmp_path / "broadcast-frame.png"
    Image.new("RGB", (1000, 500), (80, 40, 20)).save(frame)
    output = tmp_path / "slide-region.pdf"

    video_slide_extraction.combine_to_pdf(
        [(str(frame), 0)], str(output),
        slide_region=(0.25, 0.25, 0.75, 0.75),
        artifact_scope="slide_region",
        source_video_id="video-id",
        crop_method="manual",
        crop_verified=True,
    )

    raw = output.read_bytes()
    assert b"/MediaBox [ 0 0 500.0 250.0 ]" in raw


def test_combine_to_pdf_empty(video_slide_extraction, tmp_path):
    """Empty slide list returns None."""
    output = str(tmp_path / "empty.pdf")
    result = video_slide_extraction.combine_to_pdf([], output)
    assert result is None


def test_pdf_scope_cannot_mislabel_full_frames_as_slide_region(
        video_slide_extraction, tmp_path):
    frame = tmp_path / "frame.png"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    with pytest.raises(ValueError, match="physical crop"):
        video_slide_extraction.combine_to_pdf(
            [(str(frame), 0)], str(tmp_path / "wrong.pdf"),
            artifact_scope="slide_region",
        )


def test_artifact_manifest_rejects_unverified_authored_slide_trust(
        video_slide_extraction, tmp_path):
    with pytest.raises(ValueError, match="verified manual crop"):
        video_slide_extraction.artifact_record(
            tmp_path / "candidate.pdf", "slide_region", 1, "video-id",
            tmp_path / "source.mp4", crop_method="auto", crop_verified=False,
            trusted_for_authored_slide_analysis=True,
        )


def test_pipeline_version_is_semver(video_slide_extraction):
    """PIPELINE_VERSION is a defined dotted version string."""
    version = video_slide_extraction.PIPELINE_VERSION
    parts = version.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_schema_version_is_positive_int(video_slide_extraction):
    """SCHEMA_VERSION is a positive integer record-shape version."""
    sv = video_slide_extraction.SCHEMA_VERSION
    assert isinstance(sv, int)
    assert sv >= 1


def test_schema_reference_tracks_extractor_versions(video_slide_extraction):
    with open(SCHEMA_PATH, encoding="utf-8") as schema_file:
        schema = schema_file.read()
    assert f'"schema_version": {video_slide_extraction.SCHEMA_VERSION}' in schema
    assert f'"pipeline_version": "{video_slide_extraction.PIPELINE_VERSION}"' in schema


def test_version_flag_emits_json(video_slide_extraction):
    """`--version` prints structured JSON (not prose) per script-delegation."""
    proc = subprocess.run(
        [sys.executable, SCRIPT_PATH, "--version"],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload == {"pipeline_version": video_slide_extraction.PIPELINE_VERSION}


def test_combine_to_pdf_stamps_version_metadata(video_slide_extraction, tmp_path):
    """The output PDF records PIPELINE_VERSION in its producer/creator metadata."""
    frames = []
    for i in range(2):
        img = Image.new("RGB", (320, 180), (i * 80, 0, 0))
        path = str(tmp_path / f"frame_{i:05d}.jpg")
        img.save(path)
        frames.append((path, i))

    output = str(tmp_path / "slides.pdf")
    video_slide_extraction.combine_to_pdf(frames, output)

    with open(output, "rb") as f:
        raw = f.read()
    version = video_slide_extraction.PIPELINE_VERSION
    # Pillow serializes PDF metadata strings as UTF-16BE; match either encoding.
    assert _pdf_contains(raw, "video-slide-extraction")
    assert _pdf_contains(raw, version)
    assert _pdf_contains(raw, "not authored slides")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_extract_frames_from_synthetic_video(video_slide_extraction, tmp_path):
    """Generate a tiny video with ffmpeg and verify frame extraction."""
    video = str(tmp_path / "test.mp4")
    # Create a 2-second solid-color video
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        "color=c=red:s=320x180:d=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        video,
    ], capture_output=True, check=True)

    frames_dir = str(tmp_path / "frames")
    frames = video_slide_extraction.extract_frames(video, frames_dir, fps=1)
    assert len(frames) >= 1
    # Each frame should be a JPEG
    for f in frames:
        assert f.endswith(".jpg")
        assert os.path.isfile(f)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_full_pipeline(video_slide_extraction, tmp_path):
    """End-to-end: synthetic video → frames → dedup → PDF."""
    video = str(tmp_path / "test.mp4")
    # 3-second video: red for 1s, green for 1s, blue for 1s
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=320x180:d=1",
        "-f", "lavfi", "-i", "color=c=green:s=320x180:d=1",
        "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=1",
        "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        video,
    ], capture_output=True, check=True)

    outdir = str(tmp_path / "output")
    result = video_slide_extraction.extract_slides_from_video(
        video, outdir, "test_id", fps=1, hash_threshold=8
    )
    assert result["unique_frame_count"] >= 1
    assert result["authored_slide_count"] is None
    assert "unique_slides_count" not in result
    assert "slide_count" not in result
    assert "output_pdf" not in result
    assert result["slide_source"] == "video_extracted"
    assert result["pipeline_version"] == video_slide_extraction.PIPELINE_VERSION
    assert result["schema_version"] == video_slide_extraction.SCHEMA_VERSION
    assert result["slide_region_method"] == "auto"
    assert result["slide_region_applied"] is False
    assert result["slide_region_verified"] is False
    assert result["review_required"] is True
    assert not any(artifact["artifact_scope"] == "slide_region"
                   for artifact in result["artifacts"])
    context = _artifact(result, "full_frame_context")
    assert context["trusted_for_authored_slide_analysis"] is False
    assert os.path.isfile(context["path"])
    assert context["path"].endswith("test_id.context.pdf")
    assert result["source_video_path"] == os.path.realpath(video)
    assert os.path.isfile(video), "the extractor must preserve its source video"


def test_no_region_emits_context_only_even_when_extra_context_is_disabled(
        video_slide_extraction, tmp_path, monkeypatch):
    frame = tmp_path / "full-frame.png"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    video = tmp_path / "source.mp4"
    video.write_bytes(b"source-video")
    outdir = tmp_path / "output" / ".." / "output"
    monkeypatch.setattr(
        video_slide_extraction, "extract_frames",
        lambda video_path, frames_dir, fps: [str(frame)],
    )

    result = video_slide_extraction.extract_slides_from_video(
        str(video), str(outdir), "no_region",
        slide_region="none", include_context_pdf=False,
    )

    assert result["review_required"] is True
    assert result["artifacts"] == [_artifact(result, "full_frame_context")]
    context = result["artifacts"][0]
    assert context["path"] == os.path.realpath(
        tmp_path / "output" / "no_region.context.pdf")
    assert context["source_video_id"] == "no_region"
    assert context["source_video_path"] == os.path.realpath(video)
    assert context["crop_method"] == "none"
    assert context["crop_verified"] is False
    assert context["trusted_for_authored_slide_analysis"] is False
    assert video.exists()


def test_unverified_auto_crop_is_a_review_required_candidate(
        video_slide_extraction, tmp_path, monkeypatch):
    frame = tmp_path / "broadcast-frame.png"
    Image.new("RGB", (1000, 500), (80, 40, 20)).save(frame)
    video = tmp_path / "source.mp4"
    video.write_bytes(b"source-video")
    outdir = tmp_path / "output"
    region = (0.25, 0.25, 0.75, 0.75)
    monkeypatch.setattr(
        video_slide_extraction, "extract_frames",
        lambda video_path, frames_dir, fps: [str(frame)],
    )
    monkeypatch.setattr(
        video_slide_extraction, "detect_slide_region",
        lambda frames: region,
    )

    result = video_slide_extraction.extract_slides_from_video(
        str(video), str(outdir), "auto_id", fps=0.5,
        include_context_pdf=False,
    )

    slide = _artifact(result, "slide_region")
    context = _artifact(result, "full_frame_context")
    assert result["review_required"] is True
    assert "auto-detected crop is unverified" in result["review_reason"]
    assert slide["crop_method"] == "auto"
    assert slide["crop_verified"] is False
    assert slide["trusted_for_authored_slide_analysis"] is False
    assert context["trusted_for_authored_slide_analysis"] is False
    assert slide["path"] == os.path.realpath(
        outdir / "auto_id.slide-region.pdf")
    assert context["path"] == os.path.realpath(
        outdir / "auto_id.context.pdf")
    with open(slide["path"], "rb") as slide_file:
        assert b"/MediaBox [ 0 0 500.0 250.0 ]" in slide_file.read()
    assert result["retained_frames"] == [
        {"page_number": 1, "frame_index": 0, "timestamp_seconds": 0.0}]
    assert video.exists()


def test_manual_region_bypasses_detection_and_records_verified_provenance(
        video_slide_extraction, tmp_path, monkeypatch):
    frame = tmp_path / "manual-region-frame.png"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    outdir = tmp_path / "output"
    outdir.mkdir()

    monkeypatch.setattr(
        video_slide_extraction, "extract_frames",
        lambda video, frames_dir, fps: [str(frame)],
    )
    monkeypatch.setattr(
        video_slide_extraction, "detect_slide_region",
        lambda frames: pytest.fail("manual region must bypass auto-detection"),
    )

    region = (0.2, 0.1, 0.9, 0.8)
    result = video_slide_extraction.extract_slides_from_video(
        "video.mp4", str(outdir), "manual_id",
        slide_region=region, slide_region_verified=True,
    )

    assert result["slide_region"] == region
    assert result["slide_region_method"] == "manual"
    assert result["slide_region_detected"] is False
    assert result["slide_region_applied"] is True
    assert result["slide_region_verified"] is True
    assert result["review_required"] is False
    assert result["review_reason"] is None
    slide = _artifact(result, "slide_region")
    context = _artifact(result, "full_frame_context")
    assert slide["crop_method"] == "manual"
    assert slide["crop_verified"] is True
    assert slide["trusted_for_authored_slide_analysis"] is True
    assert context["trusted_for_authored_slide_analysis"] is False
    assert os.path.isfile(slide["path"])
    assert os.path.isfile(context["path"])


def test_verified_crop_can_omit_extra_context_without_deleting_source(
        video_slide_extraction, tmp_path, monkeypatch):
    frame = tmp_path / "manual-region-frame.png"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    video = tmp_path / "source.mp4"
    video.write_bytes(b"source-video")
    outdir = tmp_path / "output"
    monkeypatch.setattr(
        video_slide_extraction, "extract_frames",
        lambda video_path, frames_dir, fps: [str(frame)],
    )

    result = video_slide_extraction.extract_slides_from_video(
        str(video), str(outdir), "manual_no_context",
        slide_region=(0.2, 0.1, 0.9, 0.8),
        slide_region_verified=True,
        include_context_pdf=False,
    )

    assert result["review_required"] is False
    assert [artifact["artifact_scope"] for artifact in result["artifacts"]] == [
        "slide_region"]
    assert _artifact(result, "slide_region")["path"].endswith(
        "manual_no_context.slide-region.pdf")
    assert not (outdir / "manual_no_context.context.pdf").exists()
    assert video.exists()


def test_retained_frame_provenance_records_page_indices_and_timestamps(
        video_slide_extraction):
    assert video_slide_extraction.retained_frame_provenance(
        [("first.jpg", 0), ("later.jpg", 3)], fps=0.5,
    ) == [
        {"page_number": 1, "frame_index": 0, "timestamp_seconds": 0.0},
        {"page_number": 2, "frame_index": 3, "timestamp_seconds": 6.0},
    ]


def test_only_a_manual_region_can_be_marked_verified(video_slide_extraction):
    with pytest.raises(ValueError, match="manual region"):
        video_slide_extraction.select_slide_region([], "auto", verified=True)
    with pytest.raises(ValueError, match="manual region"):
        video_slide_extraction.select_slide_region([], "none", verified=True)


def _composite_frames(tmp_path, n=24, with_pip=True):
    """Synthesize a broadcast composite: a slide rectangle that changes wholesale,
    optional moving speaker PiP on the left, and static venue furniture around
    both. Returns frame paths.

    Geometry is fixed, so the expected crop is known without a fixture file.
    """
    import numpy as np
    rows, cols = np.mgrid[0:360, 0:640]
    frames = []
    for i in range(n):
        arr = np.full((360, 640), 60, dtype=np.uint8)      # static venue furniture
        # Slide content must vary SPATIALLY, not only per frame: a uniform fill
        # gives every slide pixel an identical diff, the percentile lands exactly
        # on that value, and the strict `>` then drops the whole region.
        slide = (rows[40:320, 200:620] * 7
                 + cols[40:320, 200:620] * 13
                 + i * 61) % 256
        arr[40:320, 200:620] = slide.astype(np.uint8)
        if with_pip:
            top = 100 + (i % 5) * 8                        # speaker PiP: moves, small
            pip = (rows[top:top + 40, 20:90] * 11 + i * 97) % 256
            arr[top:top + 40, 20:90] = pip.astype(np.uint8)
        p = tmp_path / f"f{i:03d}.png"
        Image.fromarray(arr).save(p)
        frames.append(str(p))
    return frames


def test_detects_the_slide_and_excludes_the_speaker_pip(video_slide_extraction, tmp_path):
    """The regression, asserted on the public entry point.

    A broadcast composite has two disjoint moving regions — the slide and a live
    speaker PiP. Boxing every above-threshold pixel merges them: on this scene
    the old logic yields x[0.011, 0.989], a crop reaching into the PiP; on the
    real Devoxx 2016 artifact it exceeded the area>0.9 guard and returned None,
    so the deck was never cropped and a 43-slide talk extracted to 963 pages.
    Either way the crop is wrong, so assert the property that matters: the
    returned region excludes the PiP and still covers the slide.
    """
    frames = _composite_frames(tmp_path)
    region = video_slide_extraction.detect_slide_region(frames, sample_size=8)
    assert region is not None, "composite went undetected — the 963-page failure"
    left, upper, right, lower = region
    # The slide occupies x[0.3125, 0.969], y[0.111, 0.889] by construction; the
    # PiP sits entirely left of x=0.15 and must not be inside the crop.
    assert left > 0.15, f"crop reaches into the speaker PiP: left={left:.3f}"
    assert right > 0.9 and lower > 0.8, "crop lost part of the slide"
    assert (right - left) * (lower - upper) < 0.9, "crop is effectively full-frame"


def test_same_scene_without_a_pip_still_detects_the_slide(video_slide_extraction, tmp_path):
    """Control: the detection must not depend on a PiP being present."""
    frames = _composite_frames(tmp_path, with_pip=False)
    region = video_slide_extraction.detect_slide_region(frames, sample_size=8)
    assert region is not None
    assert region[0] > 0.15


def test_full_frame_slides_return_none(video_slide_extraction, tmp_path):
    """A full-frame screencast has no border to crop; detection must decline
    rather than shave the edges."""
    import numpy as np
    frames = []
    for i in range(24):
        arr = np.full((180, 320), 20 * (i % 8), dtype=np.uint8)
        p = tmp_path / f"g{i:03d}.png"
        Image.fromarray(arr).save(p)
        frames.append(str(p))
    assert video_slide_extraction.detect_slide_region(frames, sample_size=8) is None


def test_too_few_frames_declines_to_guess(video_slide_extraction, tmp_path):
    frames = _composite_frames(tmp_path, n=4)
    assert video_slide_extraction.detect_slide_region(frames, sample_size=8) is None


def _fullframe_slide_frames(tmp_path, n=24):
    """A FULL-FRAME deck: the whole frame is the slide, and only a text block
    changes between slides. There is no border to crop."""
    import numpy as np
    rows, cols = np.mgrid[0:360, 0:640]
    frames = []
    for i in range(n):
        arr = np.full((360, 640), 245, dtype=np.uint8)     # slide background
        block = (rows[120:200, 180:460] * 3 + i * 83) % 256  # the changing text
        arr[120:200, 180:460] = block.astype(np.uint8)
        p = tmp_path / f"s{i:03d}.png"
        Image.fromarray(arr).save(p)
        frames.append(str(p))
    return frames


def test_full_frame_deck_is_not_cropped_into_its_own_text_block(
        video_slide_extraction, tmp_path):
    """Regression on the plausibility gate.

    Component selection alone returns the changing text block inside a
    full-frame slide — a well-filled rectangle that is NOT the display. Cropping
    to it discards the rest of the deck. Observed on a real corpus talk whose
    'HELLO My name is Baruch' title slide was cropped to a 9% fragment with the
    name cut off.
    """
    frames = _fullframe_slide_frames(tmp_path)
    assert video_slide_extraction.detect_slide_region(frames, sample_size=8) is None


def test_region_smaller_than_the_area_floor_is_rejected(video_slide_extraction):
    import numpy as np
    m = np.zeros((180, 320), dtype=bool)
    m[60:90, 100:180] = True                 # solid, 4:3-ish, but only ~4% of frame
    assert video_slide_extraction._largest_rectangular_component(m) is None


def test_strip_and_column_shapes_are_rejected(video_slide_extraction):
    """Aspect gate: a wide strip or a tall column is never a projected display.

    Both shapes are sized ABOVE the 15% area floor on purpose. A strip that also
    fails on area would pass this test while the aspect gate silently regressed.
    """
    import numpy as np
    total = 180 * 320

    strip = np.zeros((180, 320), dtype=bool)
    strip[60:110, 5:315] = True              # 50x310 -> aspect 6.2, 27% of frame
    assert (50 * 310) / total > 0.15, "strip must clear the area floor to test aspect"
    assert video_slide_extraction._largest_rectangular_component(strip) is None

    column = np.zeros((180, 320), dtype=bool)
    column[5:175, 100:220] = True            # 170x120 -> aspect 0.71, 35% of frame
    assert (170 * 120) / total > 0.15, "column must clear the area floor to test aspect"
    assert video_slide_extraction._largest_rectangular_component(column) is None


def test_a_plausible_screen_of_the_same_area_is_accepted(video_slide_extraction):
    """Control for the two shape tests: same size band, display-like aspect, so
    the rejections above are attributable to aspect and nothing else."""
    import numpy as np
    m = np.zeros((180, 320), dtype=bool)
    m[40:150, 60:260] = True                 # 110x200 -> aspect 1.82, 38% of frame
    got = video_slide_extraction._largest_rectangular_component(m)
    assert got == (40, 149, 60, 259)
