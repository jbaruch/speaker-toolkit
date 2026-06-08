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


def _make_outline(tmp_path):
    p = tmp_path / "presentation-outline.md"
    p.write_text(OUTLINE)
    return p


def _make_frames(builds_dir, parent, steps, ext="jpg"):
    builds_dir.mkdir(parents=True, exist_ok=True)
    for m in range(steps):
        (builds_dir / f"slide-{parent:02d}-build-{m:02d}.{ext}").write_bytes(b"img")


def test_parses_only_build_parents(build_expansion_manifest, tmp_path):
    outline = _make_outline(tmp_path)
    parents = build_expansion_manifest.parse_build_parents(outline)
    assert parents == [7, 9]  # slide 3 has no Builds block


def test_frames_sorted_ascending(build_expansion_manifest, tmp_path):
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    frames = build_expansion_manifest.frames_for(builds, 7)
    names = [f.name for f in frames]
    assert names == [
        "slide-07-build-00.jpg", "slide-07-build-01.jpg",
        "slide-07-build-02.jpg", "slide-07-build-03.jpg",
    ]


def test_manifest_full_shape(build_expansion_manifest, tmp_path):
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    _make_frames(builds, 9, 2)
    m = build_expansion_manifest.build_manifest(outline, builds)
    assert m["schema_version"] == 1
    parents = [b["parent"] for b in m["builds"]]
    assert parents == [7, 9]
    b7 = next(b for b in m["builds"] if b["parent"] == 7)
    assert len(b7["frames"]) == 4
    assert b7["frames"][0].endswith("slide-07-build-00.jpg")
    assert b7["frames"][-1].endswith("slide-07-build-03.jpg")
    assert b7["notes"] == ""


def test_missing_frames_errors(build_expansion_manifest, tmp_path):
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)  # slide 9 frames intentionally absent
    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.build_manifest(outline, builds)
    assert "slide 9" in str(exc.value)


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
