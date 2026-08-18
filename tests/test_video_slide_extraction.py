"""Tests for video-slide-extraction.py — frame extraction, dedup, PDF output."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import shutil
import stat
import subprocess
import sys
import threading

import pytest
from conftest import synthetic_video_source_receipt, write_tiny_video
from filelock import FileLock, Timeout
from PIL import Image
from pypdf import PdfReader

SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__),
    os.pardir,
    "skills",
    "vault-ingress",
    "scripts",
    "video-slide-extraction.py",
)
SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__),
    os.pardir,
    "skills",
    "vault-ingress",
    "references",
    "schemas-db.md",
)
YOUTUBE_ID = "AbCdEfGhI_1"
SECOND_YOUTUBE_ID = "ZyXwVuTsR_2"


def _artifact(result, scope):
    matches = [
        artifact
        for artifact in result["artifacts"]
        if artifact["artifact_scope"] == scope
    ]
    assert len(matches) == 1, f"expected one {scope!r} artifact"
    return matches[0]


def _pdf_contains(raw, text):
    return text.encode() in raw or text.encode("utf-16-be") in raw


@pytest.fixture(autouse=True)
def _isolate_video_temporary_storage(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        video_slide_extraction.tempfile,
        "gettempdir",
        lambda: str(tmp_path),
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


def test_region_argument_accepts_modes_and_normalized_coordinates(
    video_slide_extraction,
):
    assert video_slide_extraction.parse_slide_region("auto") == "auto"
    assert video_slide_extraction.parse_slide_region("NONE") == "none"
    assert video_slide_extraction.parse_slide_region("0.1,0.2,0.9,0.8") == (
        0.1,
        0.2,
        0.9,
        0.8,
    )


@pytest.mark.parametrize(
    "value",
    [
        "0.1,0.2,0.9",
        "left,0.2,0.9,0.8",
        "0.9,0.2,0.1,0.8",
        "-0.1,0.2,0.9,0.8",
    ],
)
def test_region_argument_rejects_invalid_geometry(video_slide_extraction, value):
    with pytest.raises(argparse.ArgumentTypeError):
        video_slide_extraction.parse_slide_region(value)


@pytest.mark.parametrize(
    ("locator", "reason_code"),
    [
        ("relative/video.mp4", "artifact_root_not_native_absolute"),
        ("~/video.mp4", "artifact_locator_home_expansion_unsupported"),
        (r"C:video.mp4", "artifact_locator_windows_drive_relative"),
        (r"\video.mp4", "artifact_locator_windows_current_drive_rooted"),
        (r"\\?\C:\video.mp4", "artifact_locator_windows_device_namespace"),
        ("//server/share/video.mp4", "artifact_locator_ambiguous_double_slash"),
        ("/vault/../video.mp4", "artifact_locator_dot_segment"),
        (r"relative\video.mp4", "artifact_locator_noncanonical_relative"),
    ],
)
def test_canonical_path_rejects_ambient_or_noncanonical_locators_before_realpath(
    video_slide_extraction,
    monkeypatch,
    locator,
    reason_code,
):
    monkeypatch.setattr(
        video_slide_extraction.os.path,
        "realpath",
        lambda *_args, **_kwargs: pytest.fail("invalid locator reached realpath"),
    )

    with pytest.raises(ValueError, match=reason_code) as caught:
        video_slide_extraction.canonical_path(locator)

    assert locator not in str(caught.value)


def test_video_pipeline_rejects_relative_output_before_filesystem_or_ffmpeg(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    video = tmp_path / "source.mp4"
    monkeypatch.setattr(
        video_slide_extraction.os,
        "makedirs",
        lambda *_args, **_kwargs: pytest.fail("invalid output reached filesystem"),
    )
    monkeypatch.setattr(
        video_slide_extraction,
        "extract_frames",
        lambda *_args, **_kwargs: pytest.fail("invalid output reached ffmpeg"),
    )

    with pytest.raises(ValueError, match="artifact_root_not_native_absolute"):
        video_slide_extraction.extract_slides_from_video(
            str(video),
            "relative-output",
            "abcdefghijk",
        )


def test_extract_frames_rejects_foreign_source_before_creating_frame_directory(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    foreign = "/vault/source.mp4" if os.name == "nt" else r"C:\vault\source.mp4"
    monkeypatch.setattr(
        video_slide_extraction.os,
        "makedirs",
        lambda *_args, **_kwargs: pytest.fail("foreign source reached filesystem"),
    )

    with pytest.raises(ValueError, match="artifact_locator_foreign_absolute"):
        video_slide_extraction.extract_frames(
            foreign,
            str(tmp_path / "frames"),
        )


@pytest.mark.skipif(os.name == "nt", reason="characters are not valid Win32 names")
@pytest.mark.parametrize(
    "component",
    [
        "path with spaces",
        'path-with-"quote',
        "path;with;semicolons",
        "path-$(command-substitution)",
        "path>with-redirection",
    ],
)
def test_extract_frames_passes_adversarial_paths_as_argv_data(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
    component,
):
    video = os.path.realpath(tmp_path / f"{component}.mp4")
    frames_dir = os.path.realpath(tmp_path / f"frames-{component}")
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(video_slide_extraction.subprocess, "run", run)
    assert video_slide_extraction.extract_frames(video, frames_dir, fps=0.25) == []

    assert calls == [
        (
            [
                "ffmpeg",
                "-i",
                video,
                "-vf",
                "fps=0.25",
                "-q:v",
                "2",
                os.path.join(frames_dir, "frame_%05d.jpg"),
                "-y",
                "-loglevel",
                "warning",
            ],
            {"check": False, "shell": False},
        )
    ]


@pytest.mark.skipif(
    os.name == "nt", reason="shell quoting regression is POSIX-specific"
)
def test_extract_frames_cannot_create_a_shell_side_effect_sentinel(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)
    sentinel = tmp_path / "shell-side-effect"
    video = tmp_path / 'source"; touch shell-side-effect; #.mp4'
    frames_dir = tmp_path / "frames"

    monkeypatch.setattr(
        video_slide_extraction.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0),
    )
    video_slide_extraction.extract_frames(str(video), str(frames_dir))

    assert not sentinel.exists()


def test_extract_frames_reports_closed_process_exit_status(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    video = tmp_path / "private-source.mp4"
    frames_dir = tmp_path / "frames"
    monkeypatch.setattr(
        video_slide_extraction.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 17),
    )

    with pytest.raises(RuntimeError) as caught:
        video_slide_extraction.extract_frames(str(video), str(frames_dir))

    assert str(caught.value) == "ffmpeg failed with exit status 17"
    assert str(video) not in str(caught.value)


def test_extract_frames_refuses_a_nonempty_workspace_before_ffmpeg(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    stale = frames_dir / "frame_99999.jpg"
    stale.write_bytes(b"older extraction")
    monkeypatch.setattr(
        video_slide_extraction.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("nonempty workspace reached ffmpeg"),
    )

    with pytest.raises(RuntimeError, match="frame workspace is not empty"):
        video_slide_extraction.extract_frames(
            str(tmp_path / "source.mp4"),
            str(frames_dir),
        )

    assert stale.read_bytes() == b"older extraction"


def test_extract_frames_enumerates_only_literal_numbered_jpegs(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    frames_dir = tmp_path / "frames[literal]"

    def run(argv, **_kwargs):
        workspace = os.path.dirname(argv[7])
        for name in (
            "frame_00002.jpg",
            "frame_00001.jpg",
            "frame_100000.jpg",
            "frame_99999.jpg",
            "frame_not-a-number.jpg",
            "frame_00003.png",
            "other.jpg",
        ):
            with open(os.path.join(workspace, name), "wb") as output:
                output.write(b"frame")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(video_slide_extraction.subprocess, "run", run)

    frames = video_slide_extraction.extract_frames(
        str(tmp_path / "source.mp4"),
        str(frames_dir),
    )

    assert [os.path.basename(frame) for frame in frames] == [
        "frame_00001.jpg",
        "frame_00002.jpg",
        "frame_99999.jpg",
        "frame_100000.jpg",
    ]


@pytest.mark.parametrize(
    "youtube_id",
    [
        None,
        "",
        " ",
        "../escape-id",
        "abc/defghij",
        r"abc\defghij",
        "/absolute-id",
        r"C:\escape-id",
        r"\\?\C:\escape",
        "short-id",
        "twelve_chars",
        YOUTUBE_ID + "\x00",
        "ＡbCdEfGhI_1",
    ],
)
def test_video_pipeline_rejects_noncanonical_youtube_id_before_io(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
    youtube_id,
):
    monkeypatch.setattr(
        video_slide_extraction,
        "canonical_path",
        lambda *_args, **_kwargs: pytest.fail("invalid ID reached path resolution"),
    )
    monkeypatch.setattr(
        video_slide_extraction,
        "extract_frames",
        lambda *_args, **_kwargs: pytest.fail("invalid ID reached ffmpeg"),
    )

    with pytest.raises(ValueError) as caught:
        video_slide_extraction.extract_slides_from_video(
            tmp_path / "source.mp4",
            tmp_path / "output",
            youtube_id,
        )

    assert str(caught.value) == "youtube_id_invalid"
    if isinstance(youtube_id, str) and youtube_id:
        assert youtube_id not in str(caught.value)


@pytest.mark.parametrize(
    "derived_name",
    [
        f"{YOUTUBE_ID}.slide-region.pdf",
        f"{YOUTUBE_ID}.context.pdf",
    ],
)
def test_video_pipeline_rejects_existing_output_symlink_escape_before_ffmpeg(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
    derived_name,
):
    output = tmp_path / "output"
    output.mkdir()
    target = tmp_path / "outside"
    try:
        (output / derived_name).symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks are not available to this test process")
    monkeypatch.setattr(
        video_slide_extraction,
        "extract_frames",
        lambda *_args, **_kwargs: pytest.fail("escaping output reached ffmpeg"),
    )

    with pytest.raises(ValueError, match="video_output_path_escape"):
        video_slide_extraction.extract_slides_from_video(
            write_tiny_video(tmp_path / "source.mp4"),
            output,
            YOUTUBE_ID,
        )


def test_video_pipeline_rejects_a_directory_at_a_pdf_destination_before_ffmpeg(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    output.mkdir()
    (output / f"{YOUTUBE_ID}.context.pdf").mkdir()
    monkeypatch.setattr(
        video_slide_extraction,
        "extract_frames",
        lambda *_args, **_kwargs: pytest.fail("invalid PDF leaf reached ffmpeg"),
    )

    with pytest.raises(ValueError, match="video_output_leaf_invalid"):
        video_slide_extraction.extract_slides_from_video(
            write_tiny_video(tmp_path / "source.mp4"),
            output,
            YOUTUBE_ID,
        )


def test_pipeline_ignores_and_preserves_legacy_stale_frames(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output[literal]"
    legacy_workspace = output / "frames"
    legacy_workspace.mkdir(parents=True)
    stale = legacy_workspace / "frame_99999.jpg"
    Image.new("RGB", (320, 180), (255, 0, 0)).save(stale)
    stale_pdf_stage = video_slide_extraction._pdf_stage_path(
        str(output / f"{YOUTUBE_ID}.slide-region.pdf")
    )
    with open(stale_pdf_stage, "wb") as staged:
        staged.write(b"partial prior PDF")
    video = write_tiny_video(tmp_path / "source.mp4")
    workspaces = []
    consumed = []

    def extract(_video_path, frames_dir, fps):
        del fps
        assert os.path.realpath(frames_dir) != os.path.realpath(legacy_workspace)
        workspaces.append(frames_dir)
        current = os.path.join(frames_dir, "frame_00001.jpg")
        Image.new("RGB", (320, 180), (0, 0, 255)).save(current)
        return [current]

    def deduplicate(frames, _region, _threshold):
        consumed.extend(frames)
        return [(frames[0], 0)]

    monkeypatch.setattr(video_slide_extraction, "extract_frames", extract)
    monkeypatch.setattr(video_slide_extraction, "deduplicate_frames", deduplicate)

    result = video_slide_extraction.extract_slides_from_video(
        str(video),
        str(output),
        YOUTUBE_ID,
        slide_region="none",
    )

    assert len(workspaces) == 1
    assert consumed == [os.path.join(workspaces[0], "frame_00001.jpg")]
    assert not os.path.exists(workspaces[0])
    assert stale.is_file()
    assert result["total_frames_extracted"] == 1
    assert result["unique_frame_count"] == 1
    assert result["retained_frames"] == [
        {"page_number": 1, "frame_index": 0, "timestamp_seconds": 0.0}
    ]
    context = _artifact(result, "full_frame_context")
    assert context["page_count"] == 1
    assert len(PdfReader(context["path"], strict=True).pages) == 1
    assert list(output.glob("*.video-extraction.lock")) == []
    assert not os.path.exists(stale_pdf_stage)


def test_pipeline_removes_its_private_workspace_after_failure(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    legacy_workspace = output / "frames"
    legacy_workspace.mkdir(parents=True)
    stale = legacy_workspace / "frame_99999.jpg"
    stale.write_bytes(b"older extraction")
    video = write_tiny_video(tmp_path / "source.mp4")
    workspaces = []

    def extract(_video_path, frames_dir, fps):
        del fps
        workspaces.append(frames_dir)
        current = os.path.join(frames_dir, "frame_00001.jpg")
        Image.new("RGB", (320, 180), (0, 0, 255)).save(current)
        return [current]

    def fail_deduplication(*_args):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(video_slide_extraction, "extract_frames", extract)
    monkeypatch.setattr(
        video_slide_extraction,
        "deduplicate_frames",
        fail_deduplication,
    )

    with pytest.raises(RuntimeError, match="synthetic failure"):
        video_slide_extraction.extract_slides_from_video(
            str(video),
            str(output),
            YOUTUBE_ID,
            slide_region="none",
        )

    assert len(workspaces) == 1
    assert not os.path.exists(workspaces[0])
    assert stale.read_bytes() == b"older extraction"


def test_pipeline_closes_an_open_frame_before_failure_cleanup(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    video = write_tiny_video(tmp_path / "source.mp4")
    workspaces = []

    def extract(_video_path, frames_dir, fps):
        del fps
        workspaces.append(frames_dir)
        frame = os.path.join(frames_dir, "frame_00001.jpg")
        Image.new("RGB", (320, 180), (0, 0, 255)).save(frame)
        return [frame]

    def fail_hashing(*_args, **_kwargs):
        raise RuntimeError("synthetic hash failure")

    monkeypatch.setattr(video_slide_extraction, "extract_frames", extract)
    monkeypatch.setattr(video_slide_extraction.imagehash, "phash", fail_hashing)

    with pytest.raises(RuntimeError, match="synthetic hash failure"):
        video_slide_extraction.extract_slides_from_video(
            str(video),
            str(output),
            YOUTUBE_ID,
            slide_region="none",
        )

    assert len(workspaces) == 1
    assert not os.path.exists(workspaces[0])


def test_existing_unlocked_run_lock_file_does_not_block_a_rerun(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    output.mkdir()
    run_lock = video_slide_extraction._video_run_lock_path(
        os.path.realpath(output),
        YOUTUBE_ID,
    )
    with open(run_lock, "wb") as lock_file:
        lock_file.write(b"left by an interrupted process")
    video = write_tiny_video(tmp_path / "source.mp4")

    def extract(_video_path, frames_dir, fps):
        del fps
        frame = os.path.join(frames_dir, "frame_00001.jpg")
        Image.new("RGB", (320, 180), (0, 0, 255)).save(frame)
        return [frame]

    monkeypatch.setattr(video_slide_extraction, "extract_frames", extract)

    result = video_slide_extraction.extract_slides_from_video(
        str(video),
        str(output),
        YOUTUBE_ID,
        slide_region="none",
    )

    assert result["unique_frame_count"] == 1
    assert (output / f"{YOUTUBE_ID}.context.pdf").read_bytes().startswith(b"%PDF")


def test_same_video_run_waits_for_the_existing_cooperative_lock(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    output.mkdir()
    run_lock = video_slide_extraction._video_run_lock_path(
        os.path.realpath(output),
        YOUTUBE_ID,
    )
    monkeypatch.setattr(
        video_slide_extraction,
        "_video_run_lock",
        lambda path: FileLock(path, timeout=0),
    )
    monkeypatch.setattr(
        video_slide_extraction,
        "extract_frames",
        lambda *_args, **_kwargs: pytest.fail("locked rerun reached ffmpeg"),
    )

    with FileLock(run_lock):
        with pytest.raises(Timeout):
            video_slide_extraction.extract_slides_from_video(
                str(tmp_path / "source.mp4"),
                str(output),
                YOUTUBE_ID,
                slide_region="none",
            )


def test_parallel_pipeline_runs_use_distinct_workspaces_and_publish_complete_pdf(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "output"
    video = write_tiny_video(tmp_path / "source.mp4")
    barrier = threading.Barrier(2)
    workspaces = []
    workspaces_lock = threading.Lock()

    def extract(_video_path, frames_dir, fps):
        del fps
        with workspaces_lock:
            color = 60 + len(workspaces) * 120
            workspaces.append(frames_dir)
        frame = os.path.join(frames_dir, "frame_00001.jpg")
        Image.new("RGB", (320, 180), (color, 0, 0)).save(frame)
        barrier.wait(timeout=10)
        return [frame]

    monkeypatch.setattr(video_slide_extraction, "extract_frames", extract)

    def run(youtube_id):
        return video_slide_extraction.extract_slides_from_video(
            str(video),
            str(output),
            youtube_id,
            slide_region="none",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result()
            for future in (
                executor.submit(run, YOUTUBE_ID),
                executor.submit(run, SECOND_YOUTUBE_ID),
            )
        ]

    assert len(set(workspaces)) == 2
    assert all(not os.path.exists(workspace) for workspace in workspaces)
    assert [result["unique_frame_count"] for result in results] == [1, 1]
    for youtube_id in (YOUTUBE_ID, SECOND_YOUTUBE_ID):
        published = output / f"{youtube_id}.context.pdf"
        assert published.read_bytes().startswith(b"%PDF")
        assert len(PdfReader(published, strict=True).pages) == 1


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


# Three patterns built from index arithmetic, not RNG. Their pairwise phash
# distances are 31, 31, and 38 — comfortably past the threshold 8 the test uses,
# so the assertion does not sit on the edge of the comparison. Solid colors
# would not work: phash reads structure, and three flat fills hash alike.
# `testing-standards` Determinism bans runtime randomness from shaping inputs,
# and its seeded carve-out covers property-based generators, not a numpy RNG
# building a fixture.
DISTINCT_FRAME_PATTERNS = (
    # vertical stripes, 4px period
    lambda rows, cols: ((cols // 4) % 2) * 255,
    # diagonal sawtooth
    lambda rows, cols: ((rows + cols) % 64) * 4,
    # concentric rings about the center, derived from the frame's own extent so
    # the pattern stays centered at any size
    lambda rows, cols: (
        (((rows - rows.size // 2) ** 2 + (cols - cols.size // 2) ** 2) // 400 % 2) * 255
    ),
)


def _patterned_frame(pattern, height=180, width=320):
    """One deterministic RGB frame from an index-arithmetic pattern."""
    import numpy as np

    rows = np.arange(height).reshape(height, 1)
    cols = np.arange(width).reshape(1, width)
    plane = np.broadcast_to(pattern(rows, cols), (height, width))
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, :] = plane.astype(np.uint8)[:, :, None]
    return Image.fromarray(frame)


def test_deduplicate_distinct_frames(video_slide_extraction, tmp_path):
    """Visually distinct frames should all be kept."""
    frames = []
    for i, pattern in enumerate(DISTINCT_FRAME_PATTERNS):
        path = str(tmp_path / f"frame_{i:05d}.png")
        # PNG, not JPEG: lossy compression would blur the patterns together.
        _patterned_frame(pattern).save(path)
        frames.append(path)
    unique = video_slide_extraction.deduplicate_frames(frames, hash_threshold=8)
    assert len(unique) == 3


def test_the_distinct_frame_patterns_really_are_distinct(
    video_slide_extraction, tmp_path
):
    """Guard the fixture itself: solid or near-identical patterns would make
    `test_deduplicate_distinct_frames` pass for the wrong reason."""
    import imagehash

    hashes = [
        imagehash.phash(_patterned_frame(pattern), hash_size=8)
        for pattern in DISTINCT_FRAME_PATTERNS
    ]
    distances = [
        hashes[i] - hashes[j]
        for i in range(len(hashes))
        for j in range(i + 1, len(hashes))
    ]
    assert all(distance > 8 for distance in distances), distances


def test_higher_hash_threshold_monotonically_keeps_fewer_variants(
    video_slide_extraction, tmp_path, monkeypatch
):
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
            video_slide_extraction.imagehash,
            "phash",
            lambda image, hash_size: FakeHash(next(values)),
        )
        return len(
            video_slide_extraction.deduplicate_frames(frames, hash_threshold=threshold)
        )

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
    assert list(tmp_path.glob(".slides.pdf.*.tmp")) == []


def test_combine_to_pdf_preserves_prior_pdf_when_staging_fails(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    output = tmp_path / "slides.pdf"
    prior = b"prior completed derivative"
    output.write_bytes(prior)

    def fail_after_partial_write(_image, stream, **_kwargs):
        stream.write(b"%PDF-partial")
        raise OSError("synthetic staging failure")

    monkeypatch.setattr(
        video_slide_extraction.Image.Image, "save", fail_after_partial_write
    )

    with pytest.raises(OSError, match="synthetic staging failure"):
        video_slide_extraction.combine_to_pdf([(str(frame), 0)], str(output))

    assert output.read_bytes() == prior
    assert list(tmp_path.glob(".slides.pdf.*.tmp")) == []


def test_combine_to_pdf_preserves_prior_pdf_when_atomic_replace_fails(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    output = tmp_path / "slides.pdf"
    prior = b"prior completed derivative"
    output.write_bytes(prior)

    def fail_replace(*_args):
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(
        video_slide_extraction.os,
        "replace",
        fail_replace,
    )

    with pytest.raises(OSError, match="synthetic replace failure"):
        video_slide_extraction.combine_to_pdf([(str(frame), 0)], str(output))

    assert output.read_bytes() == prior
    assert list(tmp_path.glob(".slides.pdf.*.tmp")) == []


def test_combine_to_pdf_cleans_stage_when_mode_preservation_fails(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    output = tmp_path / "slides.pdf"
    prior = b"prior completed derivative"
    output.write_bytes(prior)
    stage = video_slide_extraction._pdf_stage_path(str(output))

    def fail_chmod(*_args):
        raise OSError("synthetic chmod failure")

    monkeypatch.setattr(video_slide_extraction.os, "chmod", fail_chmod)

    with pytest.raises(OSError, match="synthetic chmod failure"):
        video_slide_extraction.combine_to_pdf([(str(frame), 0)], str(output))

    assert output.read_bytes() == prior
    assert not os.path.exists(stage)


def test_combine_to_pdf_reclaims_an_interrupted_deterministic_stage(
    video_slide_extraction,
    tmp_path,
):
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    output = tmp_path / "slides.pdf"
    stage = video_slide_extraction._pdf_stage_path(str(output))
    with open(stage, "wb") as staged:
        staged.write(b"%PDF-left-by-interrupted-run")

    video_slide_extraction.combine_to_pdf([(str(frame), 0)], str(output))

    assert not os.path.exists(stage)
    assert len(PdfReader(output, strict=True).pages) == 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission contract")
def test_combine_to_pdf_preserves_an_existing_destination_mode(
    video_slide_extraction,
    tmp_path,
):
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    output = tmp_path / "slides.pdf"
    output.write_bytes(b"prior")
    os.chmod(output, 0o640)

    video_slide_extraction.combine_to_pdf([(str(frame), 0)], str(output))

    assert stat.S_IMODE(os.stat(output).st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission contract")
def test_new_pdf_uses_the_process_umask_creation_mode(
    video_slide_extraction,
    tmp_path,
):
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    reference = tmp_path / "reference"
    with open(reference, "xb"):
        pass
    output = tmp_path / "slides.pdf"

    video_slide_extraction.combine_to_pdf([(str(frame), 0)], str(output))

    assert stat.S_IMODE(os.stat(output).st_mode) == stat.S_IMODE(
        os.stat(reference).st_mode
    )


def test_combine_to_pdf_applies_crop_to_saved_pages(video_slide_extraction, tmp_path):
    """The slide crop must affect the durable PDF, not only the dedup hash."""
    frame = tmp_path / "broadcast-frame.png"
    Image.new("RGB", (1000, 500), (80, 40, 20)).save(frame)
    output = tmp_path / "slide-region.pdf"

    video_slide_extraction.combine_to_pdf(
        [(str(frame), 0)],
        str(output),
        slide_region=(0.25, 0.25, 0.75, 0.75),
        artifact_scope="slide_region",
        source_video_id=YOUTUBE_ID,
        crop_method="manual",
        crop_verified=True,
    )

    raw = output.read_bytes()
    assert b"/MediaBox [ 0 0 500.0 250.0 ]" in raw


def test_combine_to_pdf_closes_cropped_intermediate_images(
    video_slide_extraction,
    monkeypatch,
    tmp_path,
):
    frame = tmp_path / "broadcast-frame.png"
    Image.new("RGB", (1000, 500), (80, 40, 20)).save(frame)
    output = tmp_path / "slide-region.pdf"
    cropped_images = []
    closed_image_ids = set()
    original_crop = video_slide_extraction.crop_frame
    original_close = video_slide_extraction.Image.Image.close

    def track_crop(source, region):
        cropped = original_crop(source, region)
        cropped_images.append(cropped)
        return cropped

    def track_close(image):
        closed_image_ids.add(id(image))
        return original_close(image)

    monkeypatch.setattr(video_slide_extraction, "crop_frame", track_crop)
    monkeypatch.setattr(video_slide_extraction.Image.Image, "close", track_close)

    video_slide_extraction.combine_to_pdf(
        [(str(frame), 0)],
        str(output),
        slide_region=(0.25, 0.25, 0.75, 0.75),
        artifact_scope="slide_region",
    )

    assert len(cropped_images) == 1
    assert id(cropped_images[0]) in closed_image_ids


def test_combine_to_pdf_empty(video_slide_extraction, tmp_path, capsys):
    """Empty slide list returns None."""
    output = str(tmp_path / "empty.pdf")
    result = video_slide_extraction.combine_to_pdf([], output)
    captured = capsys.readouterr()
    assert result is None
    assert captured.out == ""
    assert "WARNING: No unique frames found" in captured.err


def test_pdf_scope_cannot_mislabel_full_frames_as_slide_region(
    video_slide_extraction, tmp_path
):
    frame = tmp_path / "frame.png"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    with pytest.raises(ValueError, match="physical crop"):
        video_slide_extraction.combine_to_pdf(
            [(str(frame), 0)],
            str(tmp_path / "wrong.pdf"),
            artifact_scope="slide_region",
        )


def test_artifact_manifest_rejects_unverified_authored_slide_trust(
    video_slide_extraction, tmp_path
):
    with pytest.raises(ValueError, match="verified manual crop"):
        video_slide_extraction.artifact_record(
            tmp_path / "candidate.pdf",
            "slide_region",
            1,
            YOUTUBE_ID,
            tmp_path / "source.mp4",
            synthetic_video_source_receipt(),
            crop_method="auto",
            crop_verified=False,
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
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload == {"pipeline_version": video_slide_extraction.PIPELINE_VERSION}


def test_success_cli_emits_only_result_json_on_stdout(
    video_slide_extraction, tmp_path, monkeypatch, capsys
):
    """Progress stays on stderr so stdout remains one parseable payload."""
    frame = tmp_path / "frame.png"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    video = write_tiny_video(tmp_path / "source.mp4")
    outdir = tmp_path / "output"
    monkeypatch.setattr(
        video_slide_extraction,
        "extract_frames",
        lambda video_path, frames_dir, fps: [str(frame)],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            video_slide_extraction.__file__,
            str(video),
            str(outdir),
            YOUTUBE_ID,
            "--region",
            "none",
        ],
    )

    video_slide_extraction.main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["source_video_id"] == YOUTUBE_ID
    assert payload["artifacts"][0]["artifact_scope"] == "full_frame_context"
    assert "Extracting video artifacts" in captured.err
    assert "Deduplicated: 1 frames -> 1 unique frames" in captured.err
    assert "Saved full_frame_context PDF" in captured.err
    assert "Done: 1 unique frames retained" in captured.err


@pytest.mark.parametrize(
    "youtube_id",
    ["../escape-id", r"abc\defghij", YOUTUBE_ID + "\x00"],
)
def test_cli_rejects_noncanonical_youtube_id_before_pipeline_io(
    video_slide_extraction,
    monkeypatch,
    capsys,
    youtube_id,
):
    monkeypatch.setattr(
        video_slide_extraction,
        "extract_slides_from_video",
        lambda *_args, **_kwargs: pytest.fail("invalid CLI ID reached the pipeline"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            video_slide_extraction.__file__,
            "/native/source.mp4",
            "/native/output",
            youtube_id,
        ],
    )

    with pytest.raises(SystemExit) as caught:
        video_slide_extraction.main()

    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert "youtube_id_invalid" in captured.err
    assert youtube_id not in captured.err


def test_cli_reports_missing_video_dependencies_as_one_json_error(
    video_slide_extraction,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        video_slide_extraction,
        "_DEPS_ERROR",
        ImportError("synthetic missing dependency"),
    )
    monkeypatch.setattr(
        video_slide_extraction,
        "extract_slides_from_video",
        lambda *_args, **_kwargs: pytest.fail("missing dependency reached pipeline"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            video_slide_extraction.__file__,
            "/native/source.mp4",
            "/native/output",
            YOUTUBE_ID,
        ],
    )

    with pytest.raises(SystemExit) as caught:
        video_slide_extraction.main()

    assert caught.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": (
            'Install dependencies: pip install "ImageHash==4.3.2" '
            '"numpy==2.2.6" "Pillow==12.3.0" "filelock==3.32.2"'
        )
    }


def test_ingress_scripts_have_no_shell_artifact_process_boundary():
    scripts = os.path.dirname(SCRIPT_PATH)
    for name in os.listdir(scripts):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(scripts, name), encoding="utf-8") as source_file:
            source = source_file.read()
        assert "os.system(" not in source, name
        assert "shell=True" not in source.replace(" ", ""), name


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
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:d=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            video,
        ],
        capture_output=True,
        check=True,
    )

    frames_dir = str(tmp_path / "frames")
    frames = video_slide_extraction.extract_frames(video, frames_dir, fps=1)
    assert len(frames) >= 1
    # Each frame should be a JPEG
    for f in frames:
        assert f.endswith(".jpg")
        assert os.path.isfile(f)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_full_pipeline(video_slide_extraction, tmp_path, capsys):
    """End-to-end: synthetic video → frames → dedup → PDF."""
    video = str(tmp_path / "test.mp4")
    # 3-second video: red for 1s, green for 1s, blue for 1s
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:d=1",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=320x180:d=1",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:d=1",
            "-filter_complex",
            "[0][1][2]concat=n=3:v=1:a=0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            video,
        ],
        capture_output=True,
        check=True,
    )

    outdir = str(tmp_path / "output")
    result = video_slide_extraction.extract_slides_from_video(
        video, outdir, YOUTUBE_ID, fps=1, hash_threshold=8
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Extracted" in captured.err
    assert "Deduplicated" in captured.err
    assert "Done:" in captured.err
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
    assert not any(
        artifact["artifact_scope"] == "slide_region" for artifact in result["artifacts"]
    )
    context = _artifact(result, "full_frame_context")
    assert context["trusted_for_authored_slide_analysis"] is False
    assert os.path.isfile(context["path"])
    assert context["path"].endswith(f"{YOUTUBE_ID}.context.pdf")
    assert result["source_video_path"] == os.path.realpath(video)
    assert os.path.isfile(video), "the extractor must preserve its source video"


def test_no_region_emits_context_only_even_when_extra_context_is_disabled(
    video_slide_extraction, tmp_path, monkeypatch
):
    frame = tmp_path / "full-frame.png"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    video = write_tiny_video(tmp_path / "source.mp4")
    outdir = tmp_path / "output"
    monkeypatch.setattr(
        video_slide_extraction,
        "extract_frames",
        lambda video_path, frames_dir, fps: [str(frame)],
    )

    result = video_slide_extraction.extract_slides_from_video(
        str(video),
        str(outdir),
        YOUTUBE_ID,
        slide_region="none",
        include_context_pdf=False,
    )

    assert result["review_required"] is True
    assert result["artifacts"] == [_artifact(result, "full_frame_context")]
    context = result["artifacts"][0]
    assert context["path"] == os.path.realpath(
        tmp_path / "output" / f"{YOUTUBE_ID}.context.pdf"
    )
    assert context["source_video_id"] == YOUTUBE_ID
    assert context["source_video_path"] == os.path.realpath(video)
    assert context["crop_method"] == "none"
    assert context["crop_verified"] is False
    assert context["trusted_for_authored_slide_analysis"] is False
    assert video.exists()


def test_unverified_auto_crop_is_a_review_required_candidate(
    video_slide_extraction, tmp_path, monkeypatch
):
    frame = tmp_path / "broadcast-frame.png"
    Image.new("RGB", (1000, 500), (80, 40, 20)).save(frame)
    video = write_tiny_video(tmp_path / "source.mp4")
    outdir = tmp_path / "output"
    region = (0.25, 0.25, 0.75, 0.75)
    monkeypatch.setattr(
        video_slide_extraction,
        "extract_frames",
        lambda video_path, frames_dir, fps: [str(frame)],
    )
    monkeypatch.setattr(
        video_slide_extraction,
        "detect_slide_region",
        lambda frames: region,
    )

    result = video_slide_extraction.extract_slides_from_video(
        str(video),
        str(outdir),
        YOUTUBE_ID,
        fps=0.5,
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
    assert slide["path"] == os.path.realpath(outdir / f"{YOUTUBE_ID}.slide-region.pdf")
    assert context["path"] == os.path.realpath(outdir / f"{YOUTUBE_ID}.context.pdf")
    with open(slide["path"], "rb") as slide_file:
        assert b"/MediaBox [ 0 0 500.0 250.0 ]" in slide_file.read()
    assert result["retained_frames"] == [
        {"page_number": 1, "frame_index": 0, "timestamp_seconds": 0.0}
    ]
    assert video.exists()


def test_manual_region_bypasses_detection_and_records_verified_provenance(
    video_slide_extraction, tmp_path, monkeypatch
):
    frame = tmp_path / "manual-region-frame.png"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    video = write_tiny_video(tmp_path / "source.mp4")
    outdir = tmp_path / "output"
    outdir.mkdir()

    monkeypatch.setattr(
        video_slide_extraction,
        "extract_frames",
        lambda video, frames_dir, fps: [str(frame)],
    )
    monkeypatch.setattr(
        video_slide_extraction,
        "detect_slide_region",
        lambda frames: pytest.fail("manual region must bypass auto-detection"),
    )

    region = (0.2, 0.1, 0.9, 0.8)
    result = video_slide_extraction.extract_slides_from_video(
        str(video),
        str(outdir),
        YOUTUBE_ID,
        slide_region=region,
        slide_region_verified=True,
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
    video_slide_extraction, tmp_path, monkeypatch
):
    frame = tmp_path / "manual-region-frame.png"
    Image.new("RGB", (320, 180), (80, 40, 20)).save(frame)
    video = write_tiny_video(tmp_path / "source.mp4")
    outdir = tmp_path / "output"
    monkeypatch.setattr(
        video_slide_extraction,
        "extract_frames",
        lambda video_path, frames_dir, fps: [str(frame)],
    )

    result = video_slide_extraction.extract_slides_from_video(
        str(video),
        str(outdir),
        YOUTUBE_ID,
        slide_region=(0.2, 0.1, 0.9, 0.8),
        slide_region_verified=True,
        include_context_pdf=False,
    )

    assert result["review_required"] is False
    assert [artifact["artifact_scope"] for artifact in result["artifacts"]] == [
        "slide_region"
    ]
    assert _artifact(result, "slide_region")["path"].endswith(
        f"{YOUTUBE_ID}.slide-region.pdf"
    )
    assert not (outdir / f"{YOUTUBE_ID}.context.pdf").exists()
    assert video.exists()


def test_retained_frame_provenance_records_page_indices_and_timestamps(
    video_slide_extraction,
):
    assert video_slide_extraction.retained_frame_provenance(
        [("first.jpg", 0), ("later.jpg", 3)],
        fps=0.5,
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
        arr = np.full((360, 640), 60, dtype=np.uint8)  # static venue furniture
        # Slide content must vary SPATIALLY, not only per frame: a uniform fill
        # gives every slide pixel an identical diff, the percentile lands exactly
        # on that value, and the strict `>` then drops the whole region.
        slide = (rows[40:320, 200:620] * 7 + cols[40:320, 200:620] * 13 + i * 61) % 256
        arr[40:320, 200:620] = slide.astype(np.uint8)
        if with_pip:
            top = 100 + (i % 5) * 8  # speaker PiP: moves, small
            pip = (rows[top : top + 40, 20:90] * 11 + i * 97) % 256
            arr[top : top + 40, 20:90] = pip.astype(np.uint8)
        p = tmp_path / f"f{i:03d}.png"
        Image.fromarray(arr).save(p)
        frames.append(str(p))
    return frames


def test_detects_the_slide_and_excludes_the_speaker_pip(
    video_slide_extraction, tmp_path, capsys
):
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
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Detected slide region" in captured.err
    assert region is not None, "composite went undetected — the 963-page failure"
    left, upper, right, lower = region
    # The slide occupies x[0.3125, 0.969], y[0.111, 0.889] by construction; the
    # PiP sits entirely left of x=0.15 and must not be inside the crop.
    assert left > 0.15, f"crop reaches into the speaker PiP: left={left:.3f}"
    assert right > 0.9 and lower > 0.8, "crop lost part of the slide"
    assert (right - left) * (lower - upper) < 0.9, "crop is effectively full-frame"


def test_same_scene_without_a_pip_still_detects_the_slide(
    video_slide_extraction, tmp_path
):
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
        arr = np.full((360, 640), 245, dtype=np.uint8)  # slide background
        block = (rows[120:200, 180:460] * 3 + i * 83) % 256  # the changing text
        arr[120:200, 180:460] = block.astype(np.uint8)
        p = tmp_path / f"s{i:03d}.png"
        Image.fromarray(arr).save(p)
        frames.append(str(p))
    return frames


def test_full_frame_deck_is_not_cropped_into_its_own_text_block(
    video_slide_extraction, tmp_path
):
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
    m[60:90, 100:180] = True  # solid, 4:3-ish, but only ~4% of frame
    assert video_slide_extraction._largest_rectangular_component(m) is None


def test_strip_and_column_shapes_are_rejected(video_slide_extraction):
    """Aspect gate: a wide strip or a tall column is never a projected display.

    Both shapes are sized ABOVE the 15% area floor on purpose. A strip that also
    fails on area would pass this test while the aspect gate silently regressed.
    """
    import numpy as np

    total = 180 * 320

    strip = np.zeros((180, 320), dtype=bool)
    strip[60:110, 5:315] = True  # 50x310 -> aspect 6.2, 27% of frame
    assert (50 * 310) / total > 0.15, "strip must clear the area floor to test aspect"
    assert video_slide_extraction._largest_rectangular_component(strip) is None

    column = np.zeros((180, 320), dtype=bool)
    column[5:175, 100:220] = True  # 170x120 -> aspect 0.71, 35% of frame
    assert (170 * 120) / total > 0.15, "column must clear the area floor to test aspect"
    assert video_slide_extraction._largest_rectangular_component(column) is None


def test_a_plausible_screen_of_the_same_area_is_accepted(video_slide_extraction):
    """Control for the two shape tests: same size band, display-like aspect, so
    the rejections above are attributable to aspect and nothing else."""
    import numpy as np

    m = np.zeros((180, 320), dtype=bool)
    m[40:150, 60:260] = True  # 110x200 -> aspect 1.82, 38% of frame
    got = video_slide_extraction._largest_rectangular_component(m)
    assert got == (40, 149, 60, 259)
