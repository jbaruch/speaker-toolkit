"""Tests for build-expansion-to-packed.py — the ExpandBuilds wire packer."""

import pytest

RS, US, GS = chr(30), chr(31), chr(29)


def _manifest(builds):
    return {"schema_version": 1, "builds": builds}


def test_packs_descending_by_parent(build_expansion_to_packed):
    m = _manifest([
        {"parent": 7, "frames": ["/b/s7-00.jpg", "/b/s7-01.jpg"], "notes": ""},
        {"parent": 9, "frames": ["/b/s9-00.jpg", "/b/s9-01.jpg"], "notes": "final"},
    ])
    packed = build_expansion_to_packed.manifest_to_packed(m)
    records = packed.split(RS)
    # Descending: parent 9 first so its insertion can't shift parent 7's index.
    assert records[0].split(US)[0] == "9"
    assert records[1].split(US)[0] == "7"


def test_record_fields_and_frame_order(build_expansion_to_packed):
    m = _manifest([{"parent": 7, "frames": ["/b/00.jpg", "/b/01.jpg", "/b/02.jpg"], "notes": "spk"}])
    packed = build_expansion_to_packed.manifest_to_packed(m)
    parent, notes, frames = packed.split(US)
    assert parent == "7"
    assert notes == "spk"
    assert frames.split(GS) == ["/b/00.jpg", "/b/01.jpg", "/b/02.jpg"]


def test_empty_builds_errors(build_expansion_to_packed):
    with pytest.raises(ValueError, match="no 'builds'"):
        build_expansion_to_packed.manifest_to_packed(_manifest([]))


def test_build_without_frames_errors(build_expansion_to_packed):
    with pytest.raises(ValueError, match="no frames"):
        build_expansion_to_packed.manifest_to_packed(
            _manifest([{"parent": 7, "frames": [], "notes": ""}])
        )


def test_reserved_control_char_in_path_errors(build_expansion_to_packed):
    with pytest.raises(ValueError, match="reserved control char"):
        build_expansion_to_packed.manifest_to_packed(
            _manifest([{"parent": 7, "frames": [f"/b/00{US}.jpg"], "notes": ""}])
        )


def test_cli_writes_packed_file(build_expansion_to_packed, tmp_path):
    import json
    manifest = tmp_path / "builds.json"
    manifest.write_text(json.dumps(_manifest(
        [{"parent": 4, "frames": ["/b/00.jpg", "/b/01.jpg"], "notes": ""}]
    )))
    out = tmp_path / "packed.txt"
    rc = build_expansion_to_packed.main([str(manifest), str(out)])
    assert rc == 0
    packed = out.read_text()
    assert packed.split(US)[0] == "4"
    assert packed.split(US)[2].split(GS) == ["/b/00.jpg", "/b/01.jpg"]
