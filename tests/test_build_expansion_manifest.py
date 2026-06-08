"""Tests for build-expansion-manifest.py — the deck-assembly build plan emitter."""

import json

import pytest

OUTLINE = """\
# Plan

**Model:** `gemini-3-pro-image-preview`

### Slide 3: Plain
- Format: **FULL**
- Image prompt: `[STYLE ANCHOR] a thing`

### Slide 7: The Pipeline
- Format: **FULL**
- Image prompt: `[STYLE ANCHOR] a pipeline`
- Builds: 4 steps
  - build-00: Empty track. Keep the frame.
  - build-01: Add build stage. Keep the rest.
  - build-02: Add test stage. Keep the rest.
  - build-03: [FULL] full pipeline

### Slide 9: Rollback
- Format: **FULL**
- Image prompt: `[STYLE ANCHOR] rollback`
- Builds: 2 steps
  - build-00: Empty. Keep frame.
  - build-01: [FULL] full
"""


def _make_outline(tmp_path, text=OUTLINE):
    p = tmp_path / "presentation-outline.md"
    p.write_text(text)
    return p


def _make_frames(builds_dir, parent, steps, ext="jpg"):
    """Create build-MM frames for the given step numbers (a list) or count (int)."""
    builds_dir.mkdir(parents=True, exist_ok=True)
    nums = range(steps) if isinstance(steps, int) else steps
    for m in nums:
        (builds_dir / f"slide-{parent:02d}-build-{m:02d}.{ext}").write_bytes(b"img")


def test_parses_build_specs(build_expansion_manifest, tmp_path):
    outline = _make_outline(tmp_path)
    specs = build_expansion_manifest.parse_build_specs(outline)
    parents = [s["parent"] for s in specs]
    assert parents == [7, 9]  # slide 3 has no Builds block
    s7 = next(s for s in specs if s["parent"] == 7)
    assert s7["count"] == 4
    assert s7["steps"] == [0, 1, 2, 3]


def test_frames_for_maps_step_to_path(build_expansion_manifest, tmp_path):
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    found = build_expansion_manifest.frames_for(builds, 7)
    assert sorted(found) == [0, 1, 2, 3]
    assert found[0].name == "slide-07-build-00.jpg"


def test_manifest_full_shape(build_expansion_manifest, tmp_path):
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    _make_frames(builds, 9, 2)
    m = build_expansion_manifest.build_manifest(outline, builds)
    assert m["schema_version"] == 1
    assert [b["parent"] for b in m["builds"]] == [7, 9]
    b7 = next(b for b in m["builds"] if b["parent"] == 7)
    assert len(b7["frames"]) == 4
    assert b7["frames"][0].endswith("slide-07-build-00.jpg")
    assert b7["frames"][-1].endswith("slide-07-build-03.jpg")
    assert b7["notes"] == ""


def test_missing_middle_frame_errors(build_expansion_manifest, tmp_path):
    # build-01 missing while 00/02/03 exist must fail — a partial sequence would
    # expand into a broken reveal.
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, [0, 2, 3])  # build-01 absent
    _make_frames(builds, 9, 2)
    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.build_manifest(outline, builds)
    assert "slide 7" in str(exc.value)
    assert "[1]" in str(exc.value)  # the missing step is named


def test_count_mismatch_errors(build_expansion_manifest, tmp_path):
    # Declared `Builds: 4 steps` but only 3 build-NN entries → fail.
    text = OUTLINE.replace("  - build-03: [FULL] full pipeline\n", "")
    outline = _make_outline(tmp_path, text)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, [0, 1, 2])
    _make_frames(builds, 9, 2)
    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.build_manifest(outline, builds)
    assert "slide 7" in str(exc.value)


def test_all_frames_present_passes(build_expansion_manifest, tmp_path):
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    _make_frames(builds, 9, 2)
    m = build_expansion_manifest.build_manifest(outline, builds)
    assert [b["parent"] for b in m["builds"]] == [7, 9]


def test_cli_writes_out_file(build_expansion_manifest, tmp_path, capsys):
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    _make_frames(builds, 9, 2)
    out = tmp_path / "builds.json"
    rc = build_expansion_manifest.main([str(outline), str(builds), "--out", str(out)])
    assert rc == 0
    written = json.loads(out.read_text())
    assert [b["parent"] for b in written["builds"]] == [7, 9]
    assert json.loads(capsys.readouterr().out)["schema_version"] == 1


def test_carries_parent_notes_to_final_frame(build_expansion_manifest, tmp_path):
    # The parent's notes (0-based key N-1) ride onto its build record so
    # expansion doesn't drop them.
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    _make_frames(builds, 9, 2)
    notes_map = {"6": "notes for slide 7", "8": "notes for slide 9"}  # 0-based
    m = build_expansion_manifest.build_manifest(outline, builds, notes_map)
    b7 = next(b for b in m["builds"] if b["parent"] == 7)
    assert b7["notes"] == "notes for slide 7"


def test_notes_default_empty_when_no_map(build_expansion_manifest, tmp_path):
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    _make_frames(builds, 9, 2)
    m = build_expansion_manifest.build_manifest(outline, builds)
    assert all(b["notes"] == "" for b in m["builds"])


def test_unwritable_out_returns_error(build_expansion_manifest, tmp_path, capsys):
    # --out pointing at a directory must fail cleanly (rc 1 + stderr), not raise.
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    _make_frames(builds, 9, 2)
    out_dir = tmp_path / "outdir"
    out_dir.mkdir()
    rc = build_expansion_manifest.main([str(outline), str(builds), "--out", str(out_dir)])
    assert rc == 1
    assert "cannot write manifest" in capsys.readouterr().err


def test_non_contiguous_steps_error(build_expansion_manifest, tmp_path):
    # `Builds: 2 steps` with build-00 + build-02 (count matches, but a gap) must
    # fail — expansion would silently skip the intermediate reveal.
    text = """\
# Plan

### Slide 7: Gappy
- Format: **FULL**
- Image prompt: `[STYLE ANCHOR] x`
- Builds: 2 steps
  - build-00: Empty. Keep frame.
  - build-02: [FULL] full
"""
    outline = _make_outline(tmp_path, text)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, [0, 2])
    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.build_manifest(outline, builds)
    assert "not contiguous" in str(exc.value)
