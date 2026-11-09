"""Tests for build-expansion-manifest.py — the deck-assembly build plan emitter.

parse_build_specs reads outline.yaml; the schema guarantees build steps are
contiguous from 0, so this emitter no longer re-validates count/contiguity
(those failure modes are caught at load and covered by test_outline_schema.py).
"""

import copy
import json
from pathlib import Path

import pytest
import yaml

from conftest import CURRENT_OUTLINE_SCHEMA_VERSION

FIXTURE = Path(__file__).parent / "fixtures" / "outline-example.yaml"
_TALK = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))["talk"]

DEFAULT_SLIDES = [
    {
        "n": 3,
        "chapter": "c",
        "title": "Plain",
        "format": "FULL",
        "image_prompt": "[STYLE ANCHOR] a thing",
    },
    {
        "n": 7,
        "chapter": "c",
        "title": "The Pipeline",
        "format": "FULL",
        "image_prompt": "[STYLE ANCHOR] a pipeline",
        "builds": [
            {"step": 0, "desc": "Empty track"},
            {"step": 1, "desc": "Build stage revealed"},
            {"step": 2, "desc": "Test stage revealed"},
            {"step": 3, "desc": "Full pipeline"},
        ],
    },
    {
        "n": 9,
        "chapter": "c",
        "title": "Rollback",
        "format": "FULL",
        "image_prompt": "[STYLE ANCHOR] rollback",
        "builds": [
            {"step": 0, "desc": "Empty"},
            {"step": 1, "desc": "Full"},
        ],
    },
]


def _fill_numbering(slides):
    """Pad 1..max(n) with plain slides: a built deck has one per outline slide."""
    present = {slide["n"] for slide in slides}
    filler = [
        {"n": k, "chapter": "c", "title": f"Filler {k}", "format": "FULL"}
        for k in range(1, max(present, default=0) + 1)
        if k not in present
    ]
    return sorted([*slides, *filler], key=lambda slide: slide["n"])


def _make_outline(tmp_path, slides=None):
    data = {
        "schema_version": CURRENT_OUTLINE_SCHEMA_VERSION,
        "talk": copy.deepcopy(_TALK),
        "slides": _fill_numbering(slides or DEFAULT_SLIDES),
    }
    p = tmp_path / "outline.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return p


def _make_frames(builds_dir, parent, steps, ext="jpg"):
    """Create decodable build-MM frames for the step numbers (a list) or count (int)."""
    from PIL import Image

    builds_dir.mkdir(parents=True, exist_ok=True)
    nums = range(steps) if isinstance(steps, int) else steps
    for m in nums:
        Image.new("RGB", (16, 9), (10, 20, 30)).save(
            builds_dir / f"slide-{parent:02d}-build-{m:02d}.{ext}"
        )


def test_parses_build_specs(build_expansion_manifest, tmp_path):
    outline = _make_outline(tmp_path)
    specs = build_expansion_manifest.parse_build_specs(outline)
    parents = [s["parent"] for s in specs]
    assert parents == [7, 9]  # slide 3 has no Builds block
    s7 = next(s for s in specs if s["parent"] == 7)
    assert s7["count"] == 4
    assert s7["steps"] == [0, 1, 2, 3]


def test_null_note_becomes_empty_not_literal_none(build_expansion_manifest, tmp_path):
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    _make_frames(builds, 9, 2)
    # slide 9 -> 0-based key "8" carries an explicit JSON null
    m = build_expansion_manifest.build_manifest(outline, builds, {"8": None})
    notes_by_parent = {b["parent"]: b["notes"] for b in m["builds"]}
    assert notes_by_parent[9] == "", "JSON null must be empty, never the literal 'None'"


def test_non_string_note_is_rejected(build_expansion_manifest, tmp_path):
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    _make_frames(builds, 9, 2)
    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.build_manifest(
            outline, builds, {"6": 123}
        )  # slide 7 -> key 6
    assert "must be a string" in str(exc.value)


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


def test_a_cueless_parent_note_lands_on_frame_00_with_a_warning(
    build_expansion_manifest, tmp_path, capsys
):
    # The parent's note (0-based key N-1) has no [BUILD NN] cue, so the speaker
    # says all of it over the first frame shown, never the last.
    outline = _make_outline(tmp_path)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    _make_frames(builds, 9, 2)
    notes_map = {"6": "notes for slide 7", "8": "notes for slide 9"}  # 0-based
    m = build_expansion_manifest.build_manifest(outline, builds, notes_map)
    b7 = next(b for b in m["builds"] if b["parent"] == 7)
    assert b7["frame_notes"] == ["notes for slide 7", "", "", ""]
    assert b7["notes"] == ""
    err = capsys.readouterr().err
    assert "WARN: slide 7" in err and "frame 00" in err


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
    rc = build_expansion_manifest.main(
        [str(outline), str(builds), "--out", str(out_dir)]
    )
    assert rc == 1
    assert "cannot write manifest" in capsys.readouterr().err


# ── #474: a stamping poster deck stamps its build frames too ─────────


FOOTER = "@jbaruch    speaking.jbaru.ch"


def _stamping_outline(tmp_path, slides):
    data = {
        "schema_version": CURRENT_OUTLINE_SCHEMA_VERSION,
        "talk": copy.deepcopy(_TALK),
        "style_anchor": {
            "model": "imagen-4",
            "full": "F",
            "imgtxt": "I",
            "conventions": "C",
            "composition": "poster-theatrical",
            "embedded_footer": FOOTER,
            "footer_style": {},
        },
        "slides": _fill_numbering(slides),
    }
    p = tmp_path / "outline.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return p


def _image_frames(builds_dir, parent, count):
    from PIL import Image

    builds_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for m in range(count):
        frame = builds_dir / f"slide-{parent:02d}-build-{m:02d}.jpg"
        Image.new("RGB", (1536, 864), (20 * m, 40, 60)).save(frame, quality=95)
        frames.append(frame)
    return frames


def test_a_poster_parents_frames_are_stamped_copies(build_expansion_manifest, tmp_path):
    from PIL import Image

    import footer_stamp

    slides = [s for s in DEFAULT_SLIDES if s["n"] == 7]
    outline = _stamping_outline(tmp_path, slides)
    builds = tmp_path / "builds"
    raw = _image_frames(builds, 7, 4)
    raw_bytes = [frame.read_bytes() for frame in raw]

    manifest = build_expansion_manifest.build_manifest(outline, builds)

    frames = manifest["builds"][0]["frames"]
    assert frames == [
        str((builds / "footer-stamped" / f"slide-07-build-{m:02d}.png").resolve())
        for m in range(4)
    ]
    spec = footer_stamp.stamp_spec(
        build_expansion_manifest.outline_schema.load_outline_partial(
            outline
        ).style_anchor
    )
    assert spec is not None
    style = spec[1]
    for frame in frames:
        with Image.open(frame) as image:
            assert footer_stamp.verify_footer(image, FOOTER, style) == (True, 1.0)
    assert [frame.read_bytes() for frame in raw] == raw_bytes


@pytest.mark.parametrize(
    "change,refusal",
    [
        (
            {"safe_zone": {"zone": "upper_third", "surface": "sky"}},
            "slide 7 is a build parent in a poster deck",
        ),
        # The outline schema refuses an illustrated non-FULL poster slide first.
        ({"format": "IMG+TXT"}, "poster-theatrical decks illustrate FULL slides"),
    ],
    ids=["safe-zone", "img-txt"],
)
def test_a_poster_build_parent_off_the_poster_contract_is_refused(
    build_expansion_manifest, tmp_path, change, refusal
):
    from pydantic import ValidationError

    slide = next(s for s in DEFAULT_SLIDES if s["n"] == 7)
    outline = _stamping_outline(tmp_path, [{**slide, **change}])
    builds = tmp_path / "builds"
    _image_frames(builds, 7, 4)

    with pytest.raises((SystemExit, ValidationError)) as exc:
        build_expansion_manifest.build_manifest(outline, builds)

    assert refusal in str(exc.value)
    assert not (builds / "footer-stamped").exists()


@pytest.mark.parametrize("stamped", [True, False], ids=["stamped", "unstamped"])
def test_a_frame_that_does_not_decode_stops_the_manifest(
    build_expansion_manifest, tmp_path, stamped
):
    """Unstamped frames are never opened by stamping; the preflight decodes them."""
    slides = [s for s in DEFAULT_SLIDES if s["n"] == 7]
    outline = (
        _stamping_outline(tmp_path, slides)
        if stamped
        else _make_outline(tmp_path, slides)
    )
    builds = tmp_path / "builds"
    _make_frames(builds, 7, 4)
    (builds / "slide-07-build-02.jpg").write_bytes(b"placeholder bytes")
    out = tmp_path / "manifest.json"

    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.main([str(outline), str(builds), "--out", str(out)])

    # The unusable frame is named, with what to do about it; nothing is written.
    assert "slide 7's build frames cannot be placed" in str(exc.value)
    assert "slide-07-build-02.jpg cannot be decoded" in str(exc.value)
    assert "--build 7" in str(exc.value)
    assert not out.exists()
    assert not (builds / "footer-stamped").exists()


def test_a_directory_named_like_a_frame_stops_the_manifest(
    build_expansion_manifest, tmp_path
):
    slides = [s for s in DEFAULT_SLIDES if s["n"] == 7]
    outline = _make_outline(tmp_path, slides)
    builds = tmp_path / "builds"
    _make_frames(builds, 7, [0, 1, 3])
    (builds / "slide-07-build-02.jpg").mkdir()

    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.build_manifest(outline, builds)

    assert "slide-07-build-02.jpg is not a file" in str(exc.value)


def test_frames_of_mixed_size_are_refused_before_any_stamp(
    build_expansion_manifest, tmp_path
):
    """Glyphs fitted to different frames would differ; nothing is stamped."""
    from PIL import Image

    slides = [s for s in DEFAULT_SLIDES if s["n"] == 7]
    outline = _stamping_outline(tmp_path, slides)
    builds = tmp_path / "builds"
    frames = _image_frames(builds, 7, 4)
    Image.new("RGB", (1024, 1024), (10, 20, 30)).save(frames[2], quality=95)

    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.build_manifest(outline, builds)

    assert "must share one size" in str(exc.value)
    assert frames[2].name in str(exc.value)
    assert not (builds / "footer-stamped").exists()


def test_a_stale_frame_outside_the_declared_steps_is_ignored(
    build_expansion_manifest, tmp_path
):
    """An earlier build's extra frame is never stamped, so it cannot block."""
    from PIL import Image

    slides = [s for s in DEFAULT_SLIDES if s["n"] == 7]
    outline = _stamping_outline(tmp_path, slides)
    builds = tmp_path / "builds"
    _image_frames(builds, 7, 4)
    stale = builds / "slide-07-build-04.jpg"
    Image.new("RGB", (1024, 1024), (10, 20, 30)).save(stale, quality=95)

    manifest = build_expansion_manifest.build_manifest(outline, builds)

    assert len(manifest["builds"][0]["frames"]) == 4
    assert not (builds / "footer-stamped" / "slide-07-build-04.png").exists()


def test_a_poster_slide_of_another_size_stops_the_manifest_before_any_stamp(
    build_expansion_manifest, tmp_path
):
    """The manifest checks the same deck-wide set the apply step does."""
    from PIL import Image

    parent = next(s for s in DEFAULT_SLIDES if s["n"] == 7)
    other = {
        "n": 9,
        "chapter": "c",
        "title": "Other",
        "format": "FULL",
        "text_overlay": "Other",
        "image_prompt": "P",
    }
    outline = _stamping_outline(tmp_path, [parent, other])
    builds = tmp_path / "builds"
    _image_frames(builds, 7, 4)
    Image.new("RGB", (1024, 1024), (10, 20, 30)).save(tmp_path / "slide-09.jpg")

    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.build_manifest(outline, builds)

    assert "must share one size" in str(exc.value)
    assert "slide-09.jpg" in str(exc.value)
    assert not (builds / "footer-stamped").exists()


def test_a_zero_based_outline_keys_the_deck_by_position(
    build_expansion_manifest, tmp_path
):
    """Slide 0 is the deck's first slide; ExpandBuilds indexes positions."""
    slides = [
        {"n": 0, "chapter": "c", "title": "Cold open", "format": "FULL"},
        {
            "n": 1,
            "chapter": "c",
            "title": "Reveal",
            "format": "FULL",
            "image_prompt": "[STYLE ANCHOR] a reveal",
            "builds": [{"step": 0, "desc": "Empty"}, {"step": 1, "desc": "Full"}],
        },
    ]
    outline = _make_outline(tmp_path, slides)
    builds = tmp_path / "builds"
    _make_frames(builds, 1, [0, 1])

    manifest = build_expansion_manifest.build_manifest(
        outline, builds, {"1": "notes for the reveal"}
    )

    assert manifest["builds"][0]["parent"] == 2
    assert manifest["builds"][0]["frame_notes"] == ["notes for the reveal", ""]


def test_the_manifest_refuses_an_outline_its_owner_has_not_migrated(
    build_expansion_manifest, tmp_path
):
    outline = _make_outline(tmp_path)
    data = yaml.safe_load(outline.read_text(encoding="utf-8"))
    data["schema_version"] = 1
    outline.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    builds = tmp_path / "builds"
    builds.mkdir()
    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.main([str(outline), str(builds)])
    assert "Hand off to presentation-creator" in str(exc.value)


def test_a_missing_outline_is_named_not_a_traceback(build_expansion_manifest, tmp_path):
    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.main(
            [str(tmp_path / "absent.yaml"), str(tmp_path / "builds")]
        )
    assert "outline not found" in str(exc.value)


# The owner's slide 6, as outline script items and as the rendered notes line
# per item; the cue item renders as [BUILD 01].
MONKEY_SCRIPT = [
    {"line": "Now those two differences start to matter."},
    {"parenthetical": "(beat)"},
    {"line": "This one I WILL explain. Infinite monkeys ... Shakespeare."},
    {"line": "What we have with LLMs are monkeys."},
    {"cue": "BUILD 01"},
    {
        "line": "We just gave them GPUs, and the randomness is skewed towards Shakespeare."
    },
]
MONKEY_NOTE = "\n".join(
    f"[{text}]" if kind == "cue" else text
    for item in MONKEY_SCRIPT
    for kind, text in item.items()
)
MONKEY_SLIDES = [
    {
        "n": 6,
        "chapter": "c",
        "title": "The Infinite Monkey Theorem",
        "format": "FULL",
        "image_prompt": "[STYLE ANCHOR] monkeys at typewriters",
        "builds": [{"step": 0, "desc": "No GPUs"}, {"step": 1, "desc": "GPUs"}],
        "script": MONKEY_SCRIPT,
    },
    {"n": 7, "chapter": "c", "title": "Simia Developeris", "format": "FULL"},
]


def _monkey_run(build_expansion_manifest, tmp_path, notes):
    outline = _make_outline(tmp_path, MONKEY_SLIDES)
    builds = tmp_path / "builds"
    _make_frames(builds, 6, 2)
    notes_path = tmp_path / "notes.json"
    notes_path.write_text(json.dumps(notes), encoding="utf-8")
    manifest_out = tmp_path / "builds-manifest.json"
    notes_out = tmp_path / "notes-expanded.json"
    rc = build_expansion_manifest.main(
        [
            str(outline),
            str(builds),
            "--out",
            str(manifest_out),
            "--notes",
            str(notes_path),
            "--notes-out",
            str(notes_out),
        ]
    )
    return rc, manifest_out, notes_out


def test_the_monkey_note_is_split_across_its_frames(build_expansion_manifest, tmp_path):
    notes = {"4": "Judgment was free.", "5": MONKEY_NOTE, "6": "Never hire this."}
    rc, manifest_out, notes_out = _monkey_run(build_expansion_manifest, tmp_path, notes)
    assert rc == 0
    (build,) = json.loads(manifest_out.read_text(encoding="utf-8"))["builds"]
    frame_00, frame_01 = build["frame_notes"]
    assert frame_00.startswith("Now those two differences")
    assert frame_00.endswith("What we have with LLMs are monkeys.")
    assert frame_01 == MONKEY_SCRIPT[-1]["line"]
    # ExpandBuilds writes `notes` onto the final frame: only the GPU line now.
    assert build["notes"] == frame_01
    assert json.loads(notes_out.read_text(encoding="utf-8")) == {
        "4": "Judgment was free.",
        "5": frame_00,
        "6": frame_01,
        "7": "Never hire this.",
    }


def test_a_monkey_note_that_lost_its_cue_line_is_refused(
    build_expansion_manifest, tmp_path
):
    notes = {"5": MONKEY_NOTE.replace("[BUILD 01]\n", "")}
    with pytest.raises(SystemExit) as exc:
        _monkey_run(build_expansion_manifest, tmp_path, notes)
    assert "slide 6" in str(exc.value)
    assert "outline script cues [BUILD 01]" in str(exc.value)


def test_a_cue_past_the_last_frame_stops_the_manifest(
    build_expansion_manifest, tmp_path
):
    notes = {"5": MONKEY_NOTE + "\n[BUILD 02]\nOne frame too many."}
    with pytest.raises(SystemExit) as exc:
        _monkey_run(build_expansion_manifest, tmp_path, notes)
    assert "slide 6" in str(exc.value) and "[BUILD 02]" in str(exc.value)


@pytest.mark.parametrize("given", ["--notes", "--notes-out"])
def test_notes_and_notes_out_go_together(
    build_expansion_manifest, tmp_path, capsys, given
):
    outline = _make_outline(tmp_path, MONKEY_SLIDES)
    builds = tmp_path / "builds"
    _make_frames(builds, 6, 2)
    with pytest.raises(SystemExit) as exc:
        build_expansion_manifest.main(
            [str(outline), str(builds), given, str(tmp_path / "notes.json")]
        )
    assert exc.value.code == 2
    assert "--notes and --notes-out go together" in capsys.readouterr().err


def test_the_split_manifest_still_packs_for_expand_builds(
    build_expansion_manifest, build_expansion_to_packed, tmp_path
):
    notes = {"5": MONKEY_NOTE}
    rc, manifest_out, _ = _monkey_run(build_expansion_manifest, tmp_path, notes)
    assert rc == 0
    packed = build_expansion_to_packed.manifest_to_packed(
        json.loads(manifest_out.read_text(encoding="utf-8"))
    )
    parent, note, _frames = packed.split(chr(31))
    assert parent == "6"
    assert note == MONKEY_SCRIPT[-1]["line"]
