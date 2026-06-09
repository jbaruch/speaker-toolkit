"""Tests for stage-images-into-container.py — the no-FDA image stager.

The stager copies a deck-ops manifest's images into PowerPoint's sandbox
container (so UserPicture reads them prompt-free) and rewrites the manifest paths
to the staged copies. The VBA side can't run in CI; these tests cover the
deterministic copy + path-rewrite contract.
"""

import json

import pytest


def _img(dir_, name, data=b"PNGDATA"):
    """Create a fake image file and return its absolute path string."""
    p = dir_ / name
    p.write_bytes(data)
    return str(p)


def test_backgrounds_paths_rewritten_into_stage_dir(stage_images_into_container, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    stage = tmp_path / "stage"
    a = _img(src, "slide-01.jpg", b"AAA")
    b = _img(src, "slide-03.jpg", b"BBB")
    manifest = {"backgrounds": {"1": a, "3": b}}

    out = stage_images_into_container.stage_manifest(manifest, stage)

    for key in ("1", "3"):
        staged = out["backgrounds"][key]
        assert staged.startswith(str(stage)), "path must point inside the stage dir"
    # Slide numbers preserved.
    assert set(out["backgrounds"]) == {"1", "3"}
    # Content actually copied, byte-for-byte.
    assert stage.is_dir()
    assert open(out["backgrounds"]["1"], "rb").read() == b"AAA"
    assert open(out["backgrounds"]["3"], "rb").read() == b"BBB"


def test_build_expansion_frames_rewritten_metadata_preserved(stage_images_into_container, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    stage = tmp_path / "stage"
    f0 = _img(src, "slide-07-build-00.jpg", b"F0")
    f1 = _img(src, "slide-07-build-01.jpg", b"F1")
    manifest = {
        "schema_version": 1,
        "builds": [{"parent": 7, "frames": [f0, f1], "notes": "final note"}],
    }

    out = stage_images_into_container.stage_manifest(manifest, stage)

    build = out["builds"][0]
    assert build["parent"] == 7
    assert build["notes"] == "final note"
    assert out["schema_version"] == 1
    assert all(fr.startswith(str(stage)) for fr in build["frames"])
    # Frame order preserved.
    assert open(build["frames"][0], "rb").read() == b"F0"
    assert open(build["frames"][1], "rb").read() == b"F1"


def test_same_basename_different_dirs_get_distinct_staged_names(stage_images_into_container, tmp_path):
    d1 = tmp_path / "a"
    d2 = tmp_path / "b"
    d1.mkdir()
    d2.mkdir()
    stage = tmp_path / "stage"
    p1 = _img(d1, "slide-07.jpg", b"ONE")
    p2 = _img(d2, "slide-07.jpg", b"TWO")
    manifest = {"backgrounds": {"1": p1, "2": p2}}

    out = stage_images_into_container.stage_manifest(manifest, stage)

    s1 = out["backgrounds"]["1"]
    s2 = out["backgrounds"]["2"]
    assert s1 != s2, "same basename from different dirs must not collide"
    assert open(s1, "rb").read() == b"ONE"
    assert open(s2, "rb").read() == b"TWO"


def test_idempotent_rerun_same_staged_paths(stage_images_into_container, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    stage = tmp_path / "stage"
    a = _img(src, "slide-01.jpg", b"AAA")
    manifest = {"backgrounds": {"1": a}}

    first = stage_images_into_container.stage_manifest(manifest, stage)
    second = stage_images_into_container.stage_manifest(manifest, stage)
    assert first["backgrounds"]["1"] == second["backgrounds"]["1"]


def test_missing_image_raises_actionable(stage_images_into_container, tmp_path):
    stage = tmp_path / "stage"
    manifest = {"backgrounds": {"4": str(tmp_path / "does-not-exist.jpg")}}
    with pytest.raises(SystemExit) as exc:
        stage_images_into_container.stage_manifest(manifest, stage)
    msg = str(exc.value)
    assert "slide 4" in msg
    assert "not found" in msg


def test_missing_frame_names_parent_and_index(stage_images_into_container, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    stage = tmp_path / "stage"
    f0 = _img(src, "slide-07-build-00.jpg", b"F0")
    manifest = {
        "schema_version": 1,
        "builds": [{"parent": 14, "frames": [f0, str(src / "gone.jpg")], "notes": ""}],
    }
    with pytest.raises(SystemExit) as exc:
        stage_images_into_container.stage_manifest(manifest, stage)
    assert "parent 14 frame 1" in str(exc.value)


def test_unrecognized_shape_rejected(stage_images_into_container, tmp_path):
    stage = tmp_path / "stage"
    with pytest.raises(SystemExit) as exc:
        stage_images_into_container.stage_manifest({"slides": []}, stage)
    assert "unrecognized manifest shape" in str(exc.value)


def test_non_string_path_rejected_with_actionable_error(stage_images_into_container, tmp_path):
    stage = tmp_path / "stage"
    # a malformed manifest with a non-string (int) path value must not crash with
    # a raw TypeError — it should raise SystemExit naming the offending slot
    with pytest.raises(SystemExit) as exc:
        stage_images_into_container.stage_manifest({"backgrounds": {"2": 123}}, stage)
    msg = str(exc.value)
    assert "slide 2" in msg
    assert "must be a string" in msg


def test_non_object_manifest_rejected(stage_images_into_container, tmp_path):
    stage = tmp_path / "stage"
    with pytest.raises(SystemExit) as exc:
        stage_images_into_container.stage_manifest(["not", "an", "object"], stage)
    assert "must be a JSON object" in str(exc.value)


def test_cli_writes_out_and_creates_stage_dir(stage_images_into_container, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    stage = tmp_path / "nested" / "stage"  # does not exist yet
    a = _img(src, "slide-01.jpg", b"AAA")
    manifest_path = tmp_path / "bg.json"
    manifest_path.write_text(json.dumps({"backgrounds": {"1": a}}))
    out_path = tmp_path / "rewritten.json"

    rc = stage_images_into_container.main(
        [str(manifest_path), "--stage-dir", str(stage), "--out", str(out_path)]
    )
    assert rc == 0
    assert stage.is_dir(), "stage dir created when absent"
    written = json.loads(out_path.read_text())
    assert written["backgrounds"]["1"].startswith(str(stage))
