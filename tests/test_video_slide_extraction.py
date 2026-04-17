"""Tests for video-slide-extraction.py — frame extraction, dedup, PDF output."""

import os
import shutil
import subprocess

import pytest
from PIL import Image


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
    assert os.path.isfile(result["output_pdf"])
