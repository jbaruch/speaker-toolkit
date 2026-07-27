"""Tests for video-slide-extraction.py — frame extraction, dedup, PDF output."""

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


def test_combine_to_pdf_empty(video_slide_extraction, tmp_path):
    """Empty slide list returns None."""
    output = str(tmp_path / "empty.pdf")
    result = video_slide_extraction.combine_to_pdf([], output)
    assert result is None


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
    def present(s):
        return s.encode() in raw or s.encode("utf-16-be") in raw
    assert present("video-slide-extraction")
    assert present(version)


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
    assert result["unique_slides_count"] >= 1
    assert result["slide_source"] == "video_extracted"
    assert result["pipeline_version"] == video_slide_extraction.PIPELINE_VERSION
    assert result["schema_version"] == video_slide_extraction.SCHEMA_VERSION
    assert os.path.isfile(result["output_pdf"])


def _mask(spec):
    """Build a boolean mask from a list of (r0, r1, c0, c1) filled boxes."""
    import numpy as np
    m = np.zeros((180, 320), dtype=bool)
    for r0, r1, c0, c1 in spec:
        m[r0:r1, c0:c1] = True
    return m


def test_component_labelling_separates_disjoint_regions(video_slide_extraction):
    m = _mask([(10, 40, 10, 40), (100, 150, 200, 300)])
    comps = list(video_slide_extraction._label_components(m))
    assert len(comps) == 2


def test_picks_the_slide_rectangle_over_a_speaker_blob(video_slide_extraction):
    """The regression: a broadcast composite has a solid slide rectangle AND a
    moving-speaker region. Boxing every above-threshold pixel merged them into
    one frame-spanning box, tripped the >90% guard, and returned None — so a
    43-slide talk extracted to 963 pages."""
    import numpy as np
    m = np.zeros((180, 320), dtype=bool)
    m[30:150, 110:310] = True           # solid slide rectangle, right side
    rng_rows = [(40, 60), (60, 90), (90, 120)]
    for i, (a, b) in enumerate(rng_rows):  # ragged low-fill speaker blob, left
        m[a:b, 10:10 + 8 * (i + 1)] = True
    got = video_slide_extraction._largest_rectangular_component(m)
    assert got is not None
    rmin, rmax, cmin, cmax = got
    assert cmin >= 100, "picked the speaker blob instead of the slide"
    assert (rmin, rmax, cmin, cmax) == (30, 149, 110, 309)


def test_low_fill_blob_alone_is_rejected(video_slide_extraction):
    """A ragged moving-person region with no slide present must not be cropped
    to — a wrong crop silently discards real content, so None is correct."""
    import numpy as np
    m = np.zeros((180, 320), dtype=bool)
    for i in range(0, 120, 4):          # sparse comb: large box, tiny fill
        m[30 + i, 40:280] = True
    assert video_slide_extraction._largest_rectangular_component(m) is None


def test_tiny_rectangle_is_rejected_as_too_small(video_slide_extraction):
    m = _mask([(10, 16, 10, 16)])
    assert video_slide_extraction._largest_rectangular_component(m) is None


def test_full_frame_slides_still_return_none(video_slide_extraction, tmp_path):
    """A full-frame screencast has no border to crop; region detection must
    decline rather than shave the edges."""
    import numpy as np
    frames = []
    for i in range(24):
        arr = np.full((180, 320), 20 * (i % 8), dtype=np.uint8)
        p = tmp_path / f"f{i:03d}.png"
        Image.fromarray(arr).save(p)
        frames.append(str(p))
    assert video_slide_extraction.detect_slide_region(frames, sample_size=8) is None
