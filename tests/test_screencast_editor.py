"""Tests for skills/screencast-editor/scripts — Camtasia screencast editing.

Fixtures are synthetic but shaped from a real Camtasia 2025 project and .trec:
the default screen + camera track layout, the transcript keyframes the
dynamic-caption feature writes, and the TSCM records that carry the pointer.
Each behaviour below is one that failed, or would have failed, on a real edit.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills" / "screencast-editor" / "scripts"
)
RATE = 705600000
sys.path.insert(0, str(SCRIPTS))

# The sibling module resolves only after the sys.path insert above.
import camtasia_model as model  # noqa: E402


def load(name: str):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), SCRIPTS / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_project = load("build-project")
apply_captions = load("apply-captions")
audit_framing = load("audit-framing")
chapters = load("chapters")
transcript = load("transcript")
trec_pointer = load("trec-pointer")
framing_stills = load("framing-stills")
screen_changes = load("screen-changes")


# ------------------------------------------------------------------ fixtures


def keyframes(words: list[tuple[float, str]]) -> list[dict]:
    return [
        {"endTime": round(t * RATE), "time": round(t * RATE), "value": w, "duration": 0}
        for t, w in words
    ]


def template(
    duration: float = 60.0, words: list[tuple[float, str]] | None = None
) -> dict:
    """Camtasia's project for a fresh 4K screen + camera + mic recording."""
    ticks = round(duration * RATE)
    audio = {"range": [0, 1], "type": 2, "trackRect": [0, 0, 0, 0], "parameters": {}}
    if words is not None:
        audio["parameters"]["transcription"] = {
            "type": "string",
            "keyframes": keyframes([(0.0, "%GAP"), *words]),
        }
    return {
        "title": "",
        "editRate": RATE,
        "width": 1920.0,
        "height": 1080.0,
        "sourceBin": [
            {
                "id": 1,
                "src": "take.trec",
                "rect": [0, 0, 3840, 2160],
                "sourceTracks": [
                    {"type": 0, "trackRect": [0, 0, 3840, 2160]},
                    {"type": 0, "trackRect": [0, 0, 3840, 2160]},
                    audio,
                ],
            }
        ],
        "timeline": {
            "sceneTrack": {
                "scenes": [
                    {
                        "csml": {
                            "tracks": [
                                {
                                    "trackIndex": 0,
                                    "medias": [
                                        {
                                            "id": 3,
                                            "_type": "ScreenVMFile",
                                            "src": 1,
                                            "trackNumber": 0,
                                            "attributes": {"ident": "take"},
                                            "parameters": {
                                                "scale0": 0.5,
                                                "scale1": 0.5,
                                                "cursorScale": 1.0,
                                            },
                                            "effects": [],
                                            "start": 0,
                                            "duration": ticks,
                                            "mediaStart": 0,
                                            "mediaDuration": ticks,
                                            "scalar": 1,
                                            "animationTracks": {},
                                        }
                                    ],
                                    "parameters": {},
                                },
                                {
                                    "trackIndex": 1,
                                    "medias": [
                                        {
                                            "id": 4,
                                            "_type": "UnifiedMedia",
                                            "video": {
                                                "id": 5,
                                                "_type": "VMFile",
                                                "src": 1,
                                                "trackNumber": 1,
                                                "attributes": {"ident": "take"},
                                                "parameters": {
                                                    "scale0": 1 / 6,
                                                    "scale1": 1 / 6,
                                                    "translation0": 640.0,
                                                    "translation1": -360.0,
                                                },
                                                "effects": [],
                                                "start": 0,
                                                "duration": ticks,
                                                "mediaStart": 0,
                                                "mediaDuration": ticks,
                                                "scalar": 1,
                                            },
                                            "audio": {
                                                "id": 6,
                                                "_type": "AMFile",
                                                "src": 1,
                                                "trackNumber": 2,
                                                "attributes": {},
                                                "parameters": {},
                                                "effects": [],
                                                "start": 0,
                                                "duration": ticks,
                                                "mediaStart": 0,
                                                "mediaDuration": ticks,
                                                "scalar": 1,
                                            },
                                            "effects": [],
                                            "start": 0,
                                            "duration": ticks,
                                            "mediaStart": 0,
                                            "mediaDuration": ticks,
                                            "scalar": 1,
                                        }
                                    ],
                                    "parameters": {},
                                },
                            ]
                        }
                    }
                ]
            },
            "trackAttributes": [
                {"ident": "", "audioMuted": False},
                {"ident": "", "audioMuted": False},
            ],
        },
    }


def plan(**over) -> dict:
    base = {
        "shots": [
            {"start": 1.0, "end": 10.0, "kind": "speaker", "label": "Intro"},
            {
                "start": 10.0,
                "end": 20.0,
                "kind": "screen",
                "label": "Roles",
                "cues": [[10.0, 1.06, 0.5, 0.5], [12.0, 1.7, 0.14, 0.72]],
            },
            {"start": 20.0, "end": 30.0, "kind": "speaker", "label": "Close"},
        ]
    }
    base.update(over)
    return base


def write(path: Path, data) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def trec_bytes(
    pointer: list[tuple[float, int, int]],
    rect=(-1920, 0, 1920, 1080),
    wide: bool = True,
) -> bytes:
    def record(guid: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", 1)
            + b"DATA"
            + struct.pack(">Q", 4 + 4 + 8 + 16 + len(payload))
            + guid
            + payload
        )

    pointer_body = struct.pack("<II", 1, 16) + b"".join(
        struct.pack("<dii", *s) for s in pointer
    )
    rect_body = struct.pack("<II", 1, 24) + struct.pack("<diiii", 0.0, *rect)
    body = record(bytes.fromhex("2b7b6afc7a1f11e283d00017f200be7f"), b"\x01" * 12)
    body += record(model.CAPTURE_RECT_GUID, rect_body) + record(
        model.POINTER_PATH_GUID, pointer_body
    )
    ftyp = struct.pack(">I4s", 16, b"ftyp") + b"qt  \x00\x00\x00\x00"
    if wide:
        return ftyp + struct.pack(">I4sQ", 1, b"TSCM", 16 + len(body)) + body
    return ftyp + struct.pack(">I4s", 8 + len(body), b"TSCM") + body


# ------------------------------------------------------------------ model


def test_tick_snaps_to_frames():
    assert model.tick(1.0, RATE) == RATE
    assert model.tick(1.01, RATE) == model.tick(1.0, RATE)
    assert model.tick(1.02, RATE) == 31 * RATE // 30


@pytest.mark.parametrize("zoom", [1.06, 1.4, 1.7, 2.0, 3.0])
@pytest.mark.parametrize(
    "x,y", [(0.0, 0.0), (1.0, 1.0), (0.5, 0.5), (0.14, 0.22), (0.9, 0.05)]
)
def test_framing_never_exposes_an_edge_or_the_menu_bar(zoom, x, y):
    canvas = model.Canvas()
    x0, y0, x1, y1 = model.visible_rect(zoom, x, y, canvas)
    assert x0 >= -1e-9 and x1 <= 1 + 1e-9 and y1 <= 1 + 1e-9
    assert y0 >= canvas.menubar / canvas.height - 1e-9


def test_wide_framing_hides_exactly_the_menu_bar():
    # A 6% push is enough to hide 28 of 1080 points while staying centered.
    assert model.frame(1.06, 0.5, 0.5)["translation1"] == 0


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda p: p["shots"][0].update(end=9.5), "gap or overlap"),
        (
            lambda p: p["shots"].insert(
                0, {"start": 0.5, "end": 1.0, "kind": "speaker"}
            ),
            "shorter than",
        ),
        (lambda p: p["shots"][1]["cues"][0].__setitem__(0, 11.0), "first cue"),
        (lambda p: p["shots"][1]["cues"][1].__setitem__(1, 0.9), "zoom below 1.0"),
        (
            lambda p: p["shots"][1]["cues"].append([25.0, 1.2, 0.5, 0.5]),
            "outside the shot",
        ),
        (lambda p: p["shots"][0].update(kind="camera"), "kind must be"),
    ],
)
def test_plan_validation(tmp_path, mutate, message):
    bad = plan()
    mutate(bad)
    with pytest.raises(ValueError, match=message):
        model.load_plan(write(tmp_path / "plan.json", bad))


@pytest.mark.parametrize("wide", [True, False])
def test_pointer_and_capture_rect_come_out_of_the_tscm_atom(tmp_path, wide):
    data = trec_bytes([(0.5, -960, 540), (1.0, -1900, 30)], wide=wide)
    take = tmp_path / "take.trec"
    take.write_bytes(data)
    assert model.read_top_level_atom(take, b"TSCM") == model.top_level_atom(
        data, b"TSCM"
    )
    records = model.tscm_records(model.read_top_level_atom(take, b"TSCM"))
    assert model.capture_rect(records) == (-1920, 0, 1920, 1080)
    assert model.pointer_path(records) == [(0.5, -960, 540), (1.0, -1900, 30)]


def test_a_file_without_tscm_is_not_a_camtasia_recording():
    with pytest.raises(ValueError, match="not a Camtasia recording"):
        model.top_level_atom(struct.pack(">I4s", 16, b"ftyp") + b"\x00" * 8, b"TSCM")


def test_trec_pointer_normalizes_to_the_captured_display(tmp_path):
    take = tmp_path / "take.trec"
    take.write_bytes(trec_bytes([(0.5, -960, 540)]))
    result = trec_pointer.extract(take)
    assert result["capture"] == {"x": -1920, "y": 0, "width": 1920, "height": 1080}
    assert result["samples"] == [[0.5, 0.5, 0.5]]


# ------------------------------------------------------------------ audit


def samples_resting_on(x, y, arrive=13.0):
    """Pointer idle mid-screen, moved during the shot, then rests on (x, y)."""
    return [[0.0, 0.5, 0.5], [arrive - 1, 0.3, 0.6], [arrive, x, y]]


def test_audit_flags_a_pan_away_from_where_the_pointer_rests():
    # The pointer settles on a row at y=0.62, then a pan to the top cuts it off.
    bad = plan()
    bad["shots"][1]["cues"].append([15.0, 1.7, 0.14, 0.22])
    report = audit_framing.audit(bad, samples_resting_on(0.04, 0.62))
    assert report[0]["pointing"], report


def test_audit_passes_when_the_framing_holds_the_pointer():
    report = audit_framing.audit(plan(), samples_resting_on(0.04, 0.62))
    assert report[0]["pointing"] == []


def test_a_pointer_left_by_an_earlier_shot_is_resting_not_pointing():
    samples = [[0.0, 0.9, 0.1]]  # never moves; zoomed view excludes it
    report = audit_framing.audit(plan(), samples)
    assert report[0]["pointing"] == [] and report[0]["resting_samples"] > 0


def test_a_pointer_travelling_into_frame_is_not_a_miss():
    samples = [[0.0, 0.9, 0.1]] + [
        [14.0 + i * 0.05, 0.9 - i * 0.04, 0.1 + i * 0.03] for i in range(20)
    ]
    report = audit_framing.audit(plan(), samples)
    assert report[0]["pointing"] == []


# ------------------------------------------------------------------ build


def test_build_tiles_the_edit_speaker_first():
    project = build_project.build(template(), plan())
    tracks = model.tracks(project)
    screen, inset, speaker = (t["medias"] for t in tracks)
    assert [m["attributes"]["ident"] for m in speaker] == ["Intro", "Close"]
    assert speaker[0]["start"] == 0 and speaker[0]["mediaStart"] == model.tick(
        1.0, RATE
    )
    assert screen[0]["start"] == model.tick(10.0, RATE) - model.tick(1.0, RATE)
    assert inset[0]["duration"] == sum(m["duration"] for m in screen + speaker)
    assert project["timeline"]["trackAttributes"][2]["audioMuted"] is True


def test_build_keyframes_each_cue_as_a_move_that_ends_on_it():
    project = build_project.build(template(), plan())
    clip = model.tracks(project)[0]["medias"][0]
    move = clip["animationTracks"]["visual"][0]
    assert move["endTime"] == model.tick(12.0, RATE) - model.tick(10.0, RATE)
    assert move["duration"] == model.tick(0.8, RATE)
    assert clip["parameters"]["scale0"]["defaultValue"] == pytest.approx(0.5 * 1.06)
    assert clip["parameters"]["scale0"]["keyframes"][0]["value"] == pytest.approx(
        0.5 * 1.7
    )


def test_build_sizes_the_inset_in_canvas_pixels_and_adds_noise_removal():
    project = build_project.build(template(), plan(inset={"height": 270}))
    unified = model.tracks(project)[1]["medias"][0]
    assert unified["video"]["parameters"]["scale0"] == pytest.approx(270 / 2160)
    assert [e["effectName"] for e in unified["video"]["effects"]] == [
        "RoundCorners",
        "Border",
    ]
    assert unified["audio"]["effects"][0]["effectName"] == "VSTEffect-DFN3NoiseRemoval"


def test_build_rejects_a_plan_past_the_end_of_the_take():
    with pytest.raises(ValueError, match="past the end"):
        build_project.build(template(duration=25.0), plan())


def test_build_cli_clones_the_take_and_refuses_to_overwrite(tmp_path):
    raw = tmp_path / "raw.cmproj"
    raw.mkdir()
    (raw / "take.trec").write_bytes(b"not really a movie")
    write(raw / "project.tscproj", template())
    out = tmp_path / "edit.cmproj"
    args = [str(raw), str(write(tmp_path / "plan.json", plan())), "--out", str(out)]
    assert build_project.main(args) == 0
    saved = json.loads((out / "project.tscproj").read_text())
    assert saved["sourceBin"][0]["src"] == "./media/take.trec"
    assert (out / "media" / "take.trec").read_bytes() == b"not really a movie"
    for companion in ("bookmarks.plist", "docPrefs", "shot-plan.json"):
        assert (out / companion).is_file()


# ------------------------------------------------------------------ captions

HEARD = [
    (1.0, "Hey,"),
    (1.3, "I'm"),
    (1.5, "Marc"),
    (1.8, "from"),
    (2.0, "Port."),
    (3.0, "I"),
    (3.2, "downloaded"),
    (4.0, "downgraded"),
    (4.5, "the"),
    (4.7, "lead."),
    (6.0, "I"),
    (6.2, "show"),
    (6.4, "you"),
    (6.6, "something"),
    (6.8, "cool."),
]


def heard_keyframes(gaps=(2.4, 5.2)):
    rows = [(0.0, "%GAP"), *HEARD, *[(g, "%GAP") for g in gaps]]
    return keyframes(sorted(rows))


def corrected(text: str) -> list[str]:
    return text.split()


def test_captions_keep_camtasias_onsets_and_fix_the_words():
    out, stats = apply_captions.rebuild(
        heard_keyframes(),
        corrected(
            "Hey, I'm Baruch from Port. I downgraded the lead. I showed you something cool."
        ),
        {},
    )
    words = [(k["time"] / RATE, k["value"]) for k in out if k["value"] != "%GAP"]
    assert words[2] == (1.5, "Baruch")
    assert dict((w, t) for t, w in words)["showed"] == 6.2
    assert stats["words"] == 14


def test_a_dropped_false_start_takes_the_timing_of_the_last_word_spoken():
    out, _ = apply_captions.rebuild(
        heard_keyframes(),
        corrected(
            "Hey, I'm Baruch from Port. I downgraded the lead. I show you something cool."
        ),
        {},
    )
    times = {k["value"]: k["time"] / RATE for k in out}
    assert times["downgraded"] == 4.0  # not 3.2, where "downloaded" was said


def test_pauses_survive_only_at_sentence_ends():
    out, stats = apply_captions.rebuild(
        heard_keyframes(gaps=(2.4, 3.1)),
        corrected(
            "Hey, I'm Baruch from Port. I downgraded the lead. I show you something cool."
        ),
        {},
    )
    values = [k["value"] for k in out]
    assert values[values.index("Port.") + 1] == "%GAP"
    assert "%GAP" not in values[values.index("Port.") + 2 : values.index("lead.")]
    assert stats["pauses"] == 1


def test_words_sharing_an_onset_keep_their_order():
    heard = keyframes([(0.0, "%GAP"), (1.0, "go"), (2.0, "build")])
    out, _ = apply_captions.rebuild(
        heard, corrected("Now go build something cool."), {}
    )
    assert [k["value"] for k in out if k["value"] != "%GAP"] == corrected(
        "Now go build something cool."
    )


TEXT = "Hey, I'm Baruch from Port. I downgraded the lead. I show you something cool."


def test_override_moves_a_word_to_its_measured_onset():
    text = corrected(TEXT)
    overrides = apply_captions.parse_overrides(["downgraded=4.2"], text, RATE)
    out, _ = apply_captions.rebuild(heard_keyframes(), text, overrides)
    assert {k["value"]: k["time"] for k in out}["downgraded"] == round(4.2 * RATE)


def test_a_repeated_word_needs_its_occurrence():
    text = corrected(TEXT)
    with pytest.raises(ValueError, match="occurs 2 times; name one as I#N"):
        apply_captions.parse_overrides(["I=3.0"], text, RATE)
    overrides = apply_captions.parse_overrides(["I#2=6.1"], text, RATE)
    assert overrides == {text.index("I", text.index("I") + 1): round(6.1 * RATE)}


@pytest.mark.parametrize(
    "value,message",
    [
        ("banana=1", "not in the captions"),
        ("I#3=1", "#1 to #2"),
        ("nope", "WORD=SECONDS"),
    ],
)
def test_bad_overrides_say_how_to_fix_them(value, message):
    with pytest.raises(ValueError, match=message):
        apply_captions.parse_overrides([value], corrected(TEXT), RATE)


def test_an_override_that_breaks_the_order_is_refused():
    text = corrected("Hey, I'm Baruch from Port.")
    overrides = apply_captions.parse_overrides(["hey=9"], text, RATE)
    with pytest.raises(ValueError, match="before 'Hey,'|give it an onset between"):
        apply_captions.rebuild(heard_keyframes(), text, overrides)


def caption_project(words=True, callout=True) -> dict:
    p = template(words=HEARD if words else None)
    if callout:
        model.tracks(p).append(
            {
                "trackIndex": 3,
                "medias": [
                    {
                        "_type": "Callout",
                        "parameters": {"translation1": -384.0},
                        "def": {
                            "modifier": "dynamicCaption",
                            "width": 1920.0,
                            "height": 400.0,
                            "font": {"size": 128.0},
                            "textAttributes": {
                                "keyframes": [
                                    {"value": [{"name": "fontSize", "value": 96.0}]}
                                ]
                            },
                        },
                    }
                ],
            }
        )
    return p


@pytest.fixture
def closed_projects(monkeypatch):
    """Camtasia holds nothing open; the open-file probe is platform-bound."""
    monkeypatch.setattr(model, "camtasia_open_files", lambda: [])


def test_apply_captions_cli_restyles_and_keeps_a_backup(tmp_path, closed_projects):
    bundle = tmp_path / "edit.cmproj"
    bundle.mkdir()
    write(bundle / "project.tscproj", caption_project())
    text = tmp_path / "captions.txt"
    text.write_text(
        "Hey, I'm Baruch from Port. I downgraded the lead. I showed you something cool.\n"
    )
    assert apply_captions.main([str(bundle), str(text)]) == 0
    saved = json.loads((bundle / "project.tscproj").read_text())
    callout = model.tracks(saved)[2]["medias"][0]
    assert (
        callout["def"]["width"],
        callout["def"]["height"],
        callout["def"]["font"]["size"],
    ) == (700.0, 170.0, 64.0)
    assert callout["def"]["textAttributes"]["keyframes"][0]["value"][0]["value"] == 64.0
    assert callout["parameters"]["translation1"] == -430.0
    assert len(list(bundle.glob("before-captions-*.tscproj"))) == 1


@pytest.mark.parametrize(
    "words,callout,message",
    [
        (False, True, "no Camtasia transcript"),
        (True, False, "no dynamic-caption callout"),
    ],
)
def test_apply_captions_needs_camtasias_captions_first(
    tmp_path, capsys, closed_projects, words, callout, message
):
    bundle = tmp_path / "edit.cmproj"
    bundle.mkdir()
    write(bundle / "project.tscproj", caption_project(words, callout))
    text = tmp_path / "captions.txt"
    text.write_text("Hey.\n")
    assert apply_captions.main([str(bundle), str(text)]) == 1
    assert message in capsys.readouterr().err


# ------------------------------------------------------------------ transcript and chapters

WORDS = [
    (1.0 + i, w)
    for i, w in enumerate(
        "Hey, I'm Baruch. Now, the judge rules. So we need to stop. With that, bye.".split()
    )
]


def test_transcript_groups_words_into_sentences():
    sentences = transcript.sentences(WORDS)
    assert [s["text"] for s in sentences][:2] == [
        "Hey, I'm Baruch.",
        "Now, the judge rules.",
    ]
    assert sentences[0]["end"] == sentences[1]["start"]


def test_chapters_are_timed_from_caption_words_minus_the_head_trim():
    words = [(t * 10, w) for t, w in WORDS]
    placed = chapters.place(
        words,
        [
            {"title": "Intro", "phrase": None},
            {"title": "The judge", "phrase": "Now, the judge"},
            {"title": "Stopping", "phrase": "So we need"},
        ],
        trim=5.0,
        end=200.0,
    )
    assert [(chapters.clock(t), title) for t, title in placed] == [
        ("0:00", "Intro"),
        ("0:35", "The judge"),
        ("1:15", "Stopping"),
    ]


def test_a_chapter_under_ten_seconds_is_refused():
    with pytest.raises(ValueError, match="shorter than 10s"):
        chapters.place(
            WORDS,
            [
                {"title": "Intro", "phrase": None},
                {"title": "Judge", "phrase": "Now, the judge"},
                {"title": "Stop", "phrase": "So we need"},
            ],
            0.0,
            100.0,
        )


def test_the_first_chapter_must_start_at_zero():
    with pytest.raises(ValueError, match="0:00"):
        chapters.place(
            WORDS, [{"title": "Judge", "phrase": "Now, the judge"}], 0.0, 100.0
        )


def test_a_missing_phrase_is_named():
    with pytest.raises(ValueError, match="not found"):
        chapters.place(
            WORDS,
            [
                {"title": "Intro", "phrase": None},
                {"title": "X", "phrase": "never said"},
            ],
            0.0,
            100.0,
        )


# ------------------------------------------------------------------ ffmpeg-backed


@pytest.fixture
def two_page_video(tmp_path) -> Path:
    """A 2-second 'screen': red for a second, then blue."""
    assert shutil.which("ffmpeg"), "ffmpeg is a declared system dependency"
    out = tmp_path / "screen.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=384x216:d=1:r=30",
            "-f",
            "lavfi",
            "-i",
            "color=blue:s=384x216:d=1:r=30",
            "-filter_complex",
            "[0][1]concat=n=2:v=1",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ],
        check=True,
    )
    return out


def test_screen_changes_finds_the_page_switch(two_page_video):
    found = screen_changes.changes(two_page_video, "0:0", 0.01, 10)
    assert found and abs(found[0] - 1.0) <= 0.1


def test_crop_matches_the_planned_view():
    w, h, x, y = framing_stills.crop_for(2.0, 0.5, 0.5, 3840, 2160, model.Canvas())
    assert (w, h, x, y) == (1920, 1080, 960, 540)


def test_framing_stills_renders_one_still_per_cue_and_a_sheet(tmp_path, two_page_video):
    short = {
        "shots": [
            {
                "start": 0.0,
                "end": 1.6,
                "kind": "screen",
                "cues": [[0.0, 1.06, 0.5, 0.5], [1.0, 1.5, 0.3, 0.6]],
            }
        ],
        "inset": {"height": 54, "x": 100, "y": -60},
        "canvas": {"width": 384, "height": 216, "menubar": 6},
    }
    stills = framing_stills.render(two_page_video, short, tmp_path / "stills", "0:0")
    assert [s.name for s in stills] == ["still-01.png", "still-02.png"]
    assert (tmp_path / "stills" / "sheet.png").is_file()
    assert not list((tmp_path / "stills").glob("raw-*.png"))


# ------------------------------------------------------------------ review hardening


def test_zoom_below_the_menu_bar_floor_is_refused():
    canvas = model.Canvas()
    with pytest.raises(ValueError, match="cannot hide the menu bar"):
        model.frame(1.0, 0.5, 0.5, canvas)
    floor = model.min_zoom(canvas)
    x0, y0, x1, y1 = model.visible_rect(floor, 0.5, 0.9, canvas)
    assert y1 <= 1 + 1e-9 and y0 >= canvas.menubar / canvas.height - 1e-9


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda p: p["shots"].__setitem__(0, 1), "must be an object"),
        (lambda p: p["shots"][1]["cues"].__setitem__(1, 1), "every cue must be"),
        (
            lambda p: p["shots"][1]["cues"][1].__setitem__(1, 1.0),
            "exposes the canvas edge",
        ),
    ],
)
def test_malformed_plans_are_reported_not_crashed(tmp_path, mutate, message):
    bad = plan()
    mutate(bad)
    with pytest.raises(ValueError, match=message):
        model.load_plan(write(tmp_path / "plan.json", bad))


def test_audit_refuses_a_step_that_would_never_advance(tmp_path):
    with pytest.raises(SystemExit):
        audit_framing.main(
            [str(tmp_path / "p.json"), str(tmp_path / "q.json"), "--step", "0"]
        )


def test_build_keeps_user_effects_and_drops_only_its_own():
    t = template()
    unified = model.tracks(t)[1]["medias"][0]
    unified["video"]["effects"] = [
        {"effectName": "ColorAdjustment"},
        {"effectName": "Border"},
    ]
    unified["audio"]["effects"] = [
        {"effectName": "Compressor"},
        {"effectName": "VSTEffect-DFN3NoiseRemoval"},
    ]
    project = build_project.build(t, plan(noise_removal=0))
    built = model.tracks(project)[1]["medias"][0]
    assert [e["effectName"] for e in built["video"]["effects"]] == [
        "ColorAdjustment",
        "RoundCorners",
        "Border",
    ]
    assert [e["effectName"] for e in built["audio"]["effects"]] == ["Compressor"]
    speaker = model.tracks(project)[2]["medias"][0]
    assert [e["effectName"] for e in speaker["effects"]] == ["ColorAdjustment"]


def raw_bundle(tmp_path: Path) -> Path:
    raw = tmp_path / "raw.cmproj"
    raw.mkdir()
    (raw / "take.trec").write_bytes(b"movie")
    write(raw / "project.tscproj", template())
    return raw


def test_build_rerun_is_a_noop_and_a_different_edit_is_refused(tmp_path, capsys):
    raw = raw_bundle(tmp_path)
    out = tmp_path / "edit.cmproj"
    args = [str(raw), str(write(tmp_path / "plan.json", plan())), "--out", str(out)]
    assert build_project.main(args) == 0
    assert build_project.main(args) == 0
    assert '"unchanged": true' in capsys.readouterr().out
    other = [
        str(raw),
        str(write(tmp_path / "other.json", plan(title="Other"))),
        "--out",
        str(out),
    ]
    assert build_project.main(other) == 2


def test_a_failed_build_leaves_nothing_behind(tmp_path, monkeypatch):
    raw = raw_bundle(tmp_path)
    out = tmp_path / "edit.cmproj"

    def broken_clone(source, target):
        raise OSError("disk full")

    monkeypatch.setattr(build_project, "clone", broken_clone)
    args = [str(raw), str(write(tmp_path / "plan.json", plan())), "--out", str(out)]
    assert build_project.main(args) == 1
    assert not out.exists()
    assert not list(tmp_path.glob(".edit.cmproj*"))


def test_an_open_project_is_refused(tmp_path):
    bundle = tmp_path / "edit.cmproj"
    bundle.mkdir()
    (bundle / model.OPEN_PROJECT_FILE).write_text("")
    model.ensure_closed(bundle, open_files=[])  # an empty marker is a closed project
    held = [str(bundle.resolve() / "media" / "take.trec")]
    with pytest.raises(ValueError, match="open in Camtasia"):
        model.ensure_closed(bundle, open_files=held)
    (bundle / model.OPEN_PROJECT_FILE).write_text("{}")
    with pytest.raises(ValueError, match="open in Camtasia"):
        model.ensure_closed(bundle, open_files=[])


def test_two_caption_passes_keep_two_backups(tmp_path, closed_projects):
    bundle = tmp_path / "edit.cmproj"
    bundle.mkdir()
    write(bundle / "project.tscproj", caption_project())
    text = tmp_path / "captions.txt"
    text.write_text(
        "Hey, I'm Baruch from Port. I downgraded the lead. I showed you something cool.\n"
    )
    assert apply_captions.main([str(bundle), str(text)]) == 0
    assert apply_captions.main([str(bundle), str(text)]) == 0
    assert len(list(bundle.glob("before-captions-*.tscproj"))) == 2
    assert not list(bundle.glob(".project.tscproj.writing"))


def test_fewer_than_three_chapters_is_refused():
    words = [(t * 10, w) for t, w in WORDS]
    with pytest.raises(ValueError, match="at least 3"):
        chapters.place(
            words,
            [
                {"title": "Intro", "phrase": None},
                {"title": "Judge", "phrase": "Now, the judge"},
            ],
            5.0,
            200.0,
        )


def test_chapters_cli_emits_json(tmp_path, capsys):
    bundle = tmp_path / "edit.cmproj"
    bundle.mkdir()
    write(bundle / "project.tscproj", template(words=[(t * 10, w) for t, w in WORDS]))
    spec = write(
        tmp_path / "chapters.json",
        [
            {"title": "Intro", "phrase": None},
            {"title": "The judge", "phrase": "Now, the judge"},
            {"title": "Stopping", "phrase": "So we need"},
        ],
    )
    assert chapters.main([str(bundle), str(spec), "--trim-start", "5"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert [c["clock"] for c in result["chapters"]] == ["0:00", "0:35", "1:15"]
    assert result["lines"].splitlines()[1] == "0:35 The judge"


def test_missing_ffmpeg_is_an_actionable_error(monkeypatch, tmp_path):
    def absent(*args, **kwargs):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(screen_changes.subprocess, "run", absent)
    with pytest.raises(ValueError, match="install it"):
        screen_changes.changes(tmp_path / "x.trec", "0:0", 0.01, 4)
    monkeypatch.setattr(framing_stills.subprocess, "run", absent)
    with pytest.raises(ValueError, match="install ffmpeg"):
        framing_stills.render(tmp_path / "x.trec", plan(), tmp_path / "stills", "0:0")


def test_rerendering_clears_stale_stills(tmp_path, two_page_video):
    out = tmp_path / "stills"
    out.mkdir()
    (out / "still-09.png").write_bytes(b"stale")
    short = {
        "shots": [
            {
                "start": 0.0,
                "end": 1.6,
                "kind": "screen",
                "cues": [[0.0, 1.06, 0.5, 0.5]],
            }
        ],
        "canvas": {"width": 384, "height": 216, "menubar": 6},
    }
    framing_stills.render(two_page_video, short, out, "0:0")
    assert sorted(p.name for p in out.glob("still-*.png")) == ["still-01.png"]


def test_a_missing_stream_is_reported(tmp_path, two_page_video):
    with pytest.raises(ValueError, match="no video stream"):
        framing_stills.render(two_page_video, plan(), tmp_path / "stills", "0:5")


def test_backups_never_collide_under_a_frozen_clock(tmp_path):
    from datetime import datetime, timezone

    project = tmp_path / "project.tscproj"
    project.write_text("{}")
    frozen = datetime(2026, 9, 28, 17, 32, tzinfo=timezone.utc)
    first = apply_captions.backup_project(project, now=frozen)
    second = apply_captions.backup_project(project, now=frozen)
    assert first.name == "before-captions-20260928T173200Z.tscproj"
    assert second.name == "before-captions-20260928T173200Z-1.tscproj"


def test_a_failed_open_file_check_is_an_error_not_closed(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command[0])
        code = 0 if command[0] == "pgrep" else 1
        return subprocess.CompletedProcess(
            command, code, stdout="", stderr="permission denied"
        )

    monkeypatch.setattr(model.sys, "platform", "darwin")
    monkeypatch.setattr(model.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(model.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="permission denied"):
        model.camtasia_open_files()
    assert calls == ["pgrep", "lsof"]


def test_camtasia_not_running_means_nothing_open(monkeypatch):
    monkeypatch.setattr(model.sys, "platform", "darwin")
    monkeypatch.setattr(model.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(
        model.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, stdout="", stderr=""
        ),
    )
    assert model.camtasia_open_files() == []


def test_the_first_chapter_must_have_a_null_phrase():
    words = [(t * 10, w) for t, w in WORDS]
    with pytest.raises(ValueError, match="null phrase"):
        chapters.place(
            words,
            [
                {"title": "Hey", "phrase": "Hey,"},
                {"title": "Judge", "phrase": "Now, the judge"},
                {"title": "Stop", "phrase": "So we need"},
            ],
            20.0,
            200.0,
        )


def test_the_last_sentence_has_no_invented_end():
    sentences = transcript.sentences(WORDS)
    assert "end" not in sentences[-1]


def test_a_recording_without_pointer_movement_is_refused(tmp_path):
    take = tmp_path / "take.trec"
    take.write_bytes(trec_bytes([]))
    with pytest.raises(ValueError, match="no pointer movement"):
        trec_pointer.extract(take)


@pytest.mark.parametrize(
    "content", ['{"samples": []}', '{"samples": [[1, 2]]}', "[]", "not json"]
)
def test_audit_refuses_empty_or_malformed_pointer_data(tmp_path, content):
    pointer = tmp_path / "pointer.json"
    pointer.write_text(content)
    with pytest.raises(ValueError):
        audit_framing.load_samples(pointer)


def test_a_failed_clone_falls_back_to_a_copy(tmp_path, monkeypatch):
    source = tmp_path / "take.trec"
    source.write_bytes(b"movie")
    target = tmp_path / "copy.trec"
    monkeypatch.setattr(build_project.sys, "platform", "darwin")
    monkeypatch.setattr(
        build_project.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, stdout="", stderr="clone unsupported"
        ),
    )
    build_project.clone(source, target)
    assert target.read_bytes() == b"movie"


@pytest.mark.parametrize("damage", ["media/take.trec", "shot-plan.json", "docPrefs"])
def test_a_damaged_bundle_is_not_reported_unchanged(tmp_path, capsys, damage):
    raw = raw_bundle(tmp_path)
    out = tmp_path / "edit.cmproj"
    args = [str(raw), str(write(tmp_path / "plan.json", plan())), "--out", str(out)]
    assert build_project.main(args) == 0
    (out / damage).unlink()
    assert build_project.main(args) == 2
    assert damage in capsys.readouterr().err


@pytest.mark.parametrize(
    "member,content",
    [
        ("media/take.trec", b"MOVIE"),  # same size, different recording
        ("docPrefs", b"not a plist"),
        ("shot-plan.json", b"{broken"),
    ],
)
def test_a_changed_bundle_member_is_named_not_crashed(
    tmp_path, capsys, member, content
):
    raw = raw_bundle(tmp_path)
    out = tmp_path / "edit.cmproj"
    args = [str(raw), str(write(tmp_path / "plan.json", plan())), "--out", str(out)]
    assert build_project.main(args) == 0
    (out / member).write_bytes(content)
    assert build_project.main(args) == 2
    assert member in capsys.readouterr().err


def test_a_failed_rerender_keeps_the_previous_stills(tmp_path, two_page_video):
    out = tmp_path / "stills"
    good = {
        "shots": [
            {
                "start": 0.0,
                "end": 1.6,
                "kind": "screen",
                "cues": [[0.0, 1.06, 0.5, 0.5]],
            }
        ],
        "canvas": {"width": 384, "height": 216, "menubar": 6},
    }
    framing_stills.render(two_page_video, good, out, "0:0")
    before = (out / "still-01.png").read_bytes()
    with pytest.raises(ValueError):
        framing_stills.render(two_page_video, good, out, "0:5")
    assert (out / "still-01.png").read_bytes() == before
    assert (out / "sheet.png").is_file()
    assert not (tmp_path / ".stills.staging").exists()


def test_cues_out_of_order_are_refused(tmp_path):
    bad = plan()
    bad["shots"][1]["cues"] = [
        [10.0, 1.06, 0.5, 0.5],
        [15.0, 1.7, 0.1, 0.2],
        [12.0, 1.5, 0.5, 0.5],
    ]
    with pytest.raises(ValueError, match="strictly increase"):
        model.load_plan(write(tmp_path / "plan.json", bad))


def test_an_all_speaker_plan_renders_no_stills(tmp_path, two_page_video, capsys):
    speaker_only = {"shots": [{"start": 0.0, "end": 1.6, "kind": "speaker"}]}
    plan_path = write(tmp_path / "plan.json", speaker_only)
    assert (
        framing_stills.main(
            [str(two_page_video), str(plan_path), "--out", str(tmp_path / "stills")]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"stills": [], "sheet": None}


def test_an_unwritable_stills_directory_is_reported(tmp_path, two_page_video, capsys):
    blocker = tmp_path / "stills"
    blocker.write_text("a file where the directory should be")
    good = {
        "shots": [
            {
                "start": 0.0,
                "end": 1.6,
                "kind": "screen",
                "cues": [[0.0, 1.06, 0.5, 0.5]],
            }
        ],
        "canvas": {"width": 384, "height": 216, "menubar": 6},
    }
    plan_path = write(tmp_path / "plan.json", good)
    assert (
        framing_stills.main(
            [str(two_page_video), str(plan_path), "--out", str(blocker)]
        )
        == 1
    )
    assert "choose a writable --out" in capsys.readouterr().err


def test_an_unwritable_pointer_output_is_reported(tmp_path, capsys):
    take = tmp_path / "take.trec"
    take.write_bytes(trec_bytes([(0.5, -960, 540)]))
    target = tmp_path / "missing-dir" / "pointer.json"
    assert trec_pointer.main([str(take), "--out", str(target)]) == 1
    assert "choose a writable --out" in capsys.readouterr().err


def test_an_all_speaker_plan_builds_from_a_screen_and_camera_take():
    speaker_only = {
        "shots": [
            {"start": 1.0, "end": 30.0, "kind": "speaker", "label": "All presenter"}
        ]
    }
    project = build_project.build(template(), speaker_only)
    screen, inset, speaker = (t["medias"] for t in model.tracks(project))
    assert screen == [] and [m["attributes"]["ident"] for m in speaker] == [
        "All presenter"
    ]
    assert inset[0]["duration"] == speaker[0]["duration"]


def test_a_camera_only_recording_is_refused():
    t = template()
    model.tracks(t)[0]["medias"] = []
    with pytest.raises(ValueError, match="screen on track 0"):
        build_project.build(t, plan())


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda p: p["shots"][0].update(start=-1.0), "negative time"),
        (lambda p: p["shots"][2].update(end=float("inf")), "must be numbers"),
        (lambda p: p["shots"][1]["cues"][1].__setitem__(2, 1.4), "within the screen"),
        (lambda p: p.update(canvas={"height": 20, "menubar": 28}), "menu bar shorter"),
    ],
)
def test_impossible_plan_values_are_refused(tmp_path, mutate, message):
    bad = plan()
    mutate(bad)
    with pytest.raises(ValueError, match=message):
        model.load_plan(write(tmp_path / "plan.json", bad))


def test_extract_frames_picks_exact_frames(tmp_path, two_page_video):
    extract_frames = load("extract-frames")
    frames = extract_frames.extract(
        two_page_video, "0:0", [0.2, 1.5], tmp_path / "thumb", "screen"
    )
    assert [f.name for f in frames] == ["screen-0.2.png", "screen-1.5.png"]
    assert not list(tmp_path.glob(".thumb*"))


def test_extract_frames_refuses_a_time_past_the_end(tmp_path, two_page_video):
    extract_frames = load("extract-frames")
    with pytest.raises(ValueError, match="inside the recording"):
        extract_frames.extract(
            two_page_video, "0:0", [0.2, 9.0], tmp_path / "thumb", "screen"
        )
    assert not (tmp_path / "thumb").exists()


def test_an_unrelated_transcript_is_refused():
    with pytest.raises(ValueError, match="shares no words"):
        apply_captions.rebuild(
            heard_keyframes(),
            corrected("Completely different sentences about gardening."),
            {},
        )


def test_other_platforms_are_refused_not_assumed_closed(monkeypatch):
    monkeypatch.setattr(model.sys, "platform", "win32")
    with pytest.raises(ValueError, match="Camtasia for Mac only"):
        model.camtasia_open_files()


def test_a_malformed_template_is_diagnosed_not_crashed(tmp_path, capsys):
    raw = tmp_path / "raw.cmproj"
    raw.mkdir()
    broken = template()
    del broken["timeline"]["sceneTrack"]
    write(raw / "project.tscproj", broken)
    args = [
        str(raw),
        str(write(tmp_path / "plan.json", plan())),
        "--out",
        str(tmp_path / "edit.cmproj"),
    ]
    assert build_project.main(args) == 1
    assert "not a Camtasia screen + camera recording project" in capsys.readouterr().err


@pytest.mark.parametrize(
    "spec,message",
    [
        (["Intro"], "chapter 1 needs"),
        ({"title": "Intro"}, "must be a list"),
        ([{"title": "Intro", "phrase": 3}], "must be null or"),
        ([{"phrase": None}], "chapter 1 needs"),
    ],
)
def test_malformed_chapter_files_are_explained(tmp_path, capsys, spec, message):
    bundle = tmp_path / "edit.cmproj"
    bundle.mkdir()
    write(bundle / "project.tscproj", template(words=[(t * 10, w) for t, w in WORDS]))
    assert (
        chapters.main(
            [str(bundle), str(write(tmp_path / "c.json", spec)), "--trim-start", "5"]
        )
        == 1
    )
    assert message in capsys.readouterr().err


def test_an_all_speaker_rerun_clears_earlier_stills(tmp_path, two_page_video):
    out = tmp_path / "stills"
    good = {
        "shots": [
            {
                "start": 0.0,
                "end": 1.6,
                "kind": "screen",
                "cues": [[0.0, 1.06, 0.5, 0.5]],
            }
        ],
        "canvas": {"width": 384, "height": 216, "menubar": 6},
    }
    framing_stills.render(two_page_video, good, out, "0:0")
    speaker_only = {"shots": [{"start": 0.0, "end": 1.6, "kind": "speaker"}]}
    assert framing_stills.render(two_page_video, speaker_only, out, "0:0") == []
    assert not list(out.glob("still-*.png")) and not (out / "sheet.png").exists()


@pytest.mark.parametrize(
    "value", ["downgraded=-1", "downgraded=inf", "downgraded=nan", "downgraded=soon"]
)
def test_override_seconds_must_be_a_real_onset(value):
    with pytest.raises(ValueError, match="non-negative number"):
        apply_captions.parse_overrides([value], corrected(TEXT), RATE)


@pytest.mark.parametrize(
    "content,message",
    [
        ('{"samples": [[1, "a", 0.5]]}', "finite numbers"),
        ('{"samples": [[1, 0.5, Infinity]]}', "finite numbers"),
        ('{"samples": [[2, 0.5, 0.5], [1, 0.5, 0.5]]}', "time order"),
    ],
)
def test_audit_rejects_bad_pointer_samples(tmp_path, content, message):
    pointer = tmp_path / "pointer.json"
    pointer.write_text(content)
    with pytest.raises(ValueError, match=message):
        audit_framing.load_samples(pointer)
