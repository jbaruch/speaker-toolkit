"""shorts-producer: plan checks, caption fidelity, speaker tracking, a full render.

Recordings and deck pages are synthesized in ``tmp_path`` with ffmpeg and
Pillow. Apple Vision and the word transcriber are the platform-bound layer
(``rules/shorts-vision-validation-authority.md``,
``rules/transcript-fetch-authority.md``); tests feed their outputs directly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import subprocess
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont
import pytest

from conftest import _import_script

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "shorts-producer" / "scripts"
plan_mod = _import_script(str(SCRIPTS / "shorts_plan.py"), "shorts_plan")
render_mod = _import_script(str(SCRIPTS / "render-short.py"), "render_short")
verify_mod = _import_script(str(SCRIPTS / "verify-short.py"), "verify_short")
prepare_mod = _import_script(str(SCRIPTS / "prepare-clip.py"), "prepare_clip")

WORDS = "this is a short test of the caption highlight in the render".split()


@pytest.fixture(autouse=True)
def portable_fonts(monkeypatch):
    """The renderer's macOS fonts stand in for Pillow's bundled one on CI."""
    monkeypatch.setattr(
        render_mod, "_font", lambda kind, size: ImageFont.load_default(size=size)
    )


def _spoken(texts, start=0.0, step=0.4):
    return [
        {
            "text": t,
            "start": round(start + i * step, 3),
            "end": round(start + (i + 1) * step, 3),
        }
        for i, t in enumerate(texts)
    ]


def _plan_dict(tmp_path, **clip_overrides):
    clip = {
        "id": "01-test",
        "title": "A test",
        "hook": ["A SHORT", "TEST."],
        "start": 0.5,
        "end": 5.5,
        "rationale": "fixture",
        "speaker_region": [0.3, 0.1, 0.4, 0.8],
        "slides": [[0, 1], [2.5, 2]],
        "captions": " ".join(WORDS),
    }
    clip.update(clip_overrides)
    return {
        "schema_version": 1,
        "talk": "test.md",
        "source": "source.mp4",
        "deck_pdf": "deck.pdf",
        "work_dir": "work",
        "out_dir": "out",
        "handle": "@speaker",
        "event": "Test Conf",
        "website": "example.com",
        "qr_url": None,
        "clips": [clip],
    }


def _write_plan(tmp_path, plan):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    return path


def _face_rows(start=0.0, end=6.0, x=0.45):
    rows = []
    t = start
    while t <= end:
        rows.append(
            {
                "t": round(t, 2),
                "faces": [
                    {"x": x, "y": 0.25, "w": 0.1, "h": 0.15, "confidence": 0.9},
                    # A face on the projected slide, outside the speaker region.
                    {"x": 0.02, "y": 0.05, "w": 0.08, "h": 0.12, "confidence": 0.95},
                ],
            }
        )
        t += 0.5
    return rows


def _prepared(tmp_path, plan):
    """What prepare-clip.py leaves behind, synthesized."""
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30:duration=6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(tmp_path / "source.mp4"),
        ],
        check=True,
        timeout=120,
    )
    deck = tmp_path / "work" / "deck"
    deck.mkdir(parents=True)
    for page, color in ((1, "#2a6fdb"), (2, "#db6f2a")):
        image = Image.new("RGB", (1080, 608), color)
        ImageDraw.Draw(image).rectangle((200, 150, 880, 450), fill="white")
        image.save(deck / f"page-{page:03d}.png")
    folder = tmp_path / "work" / "01-test"
    folder.mkdir()
    words = _spoken(WORDS, start=0.6)
    (folder / "words.json").write_text(
        json.dumps({"schema_version": 1, "window": [0, 6], "words": words})
    )
    (folder / "faces.json").write_text(
        json.dumps({"schema_version": 1, "rows": _face_rows()})
    )
    return _write_plan(tmp_path, plan)


# ── plan ─────────────────────────────────────────────────────────────


def test_a_plan_resolves_its_paths_against_its_own_folder(tmp_path):
    plan = plan_mod.load(_write_plan(tmp_path, _plan_dict(tmp_path)))
    assert plan["source"] == (tmp_path / "source.mp4").resolve()
    assert plan["work_dir"] == (tmp_path / "work").resolve()
    assert plan_mod.clip(plan, "01-test")["start"] == 0.5


@pytest.mark.parametrize(
    "change,complaint",
    [
        (lambda p: p.pop("deck_pdf"), "missing"),
        (lambda p: p.update(schema_version=2), "schema_version"),
        (lambda p: p["clips"][0].update(id="Bad Id"), "lowercase"),
        (lambda p: p["clips"].append(dict(p["clips"][0])), "twice"),
        (lambda p: p["clips"][0].update(end=0.2), "start < end"),
        (lambda p: p.update(qr_url="http://example.com"), "https"),
    ],
    ids=[
        "missing-field",
        "schema",
        "bad-id",
        "duplicate-id",
        "backwards",
        "insecure-qr",
    ],
)
def test_a_broken_plan_is_refused_with_its_fix(tmp_path, change, complaint):
    plan = _plan_dict(tmp_path)
    change(plan)
    with pytest.raises(plan_mod.PlanError, match=complaint):
        plan_mod.load(_write_plan(tmp_path, plan))


@pytest.mark.parametrize(
    "overrides,complaint",
    [
        ({"speaker_region": [0.8, 0.1, 0.4, 0.8]}, "speaker_region"),
        ({"slides": [[1, 1]]}, "start at 0"),
        ({"slides": [[0, 1], [9, 2]]}, "inside the clip"),
        ({"slides": [[0, 0]]}, "offset, page"),
        ({"captions": "  "}, "captions"),
        ({"hook": ["ONE", "TWO", "THREE"]}, "hook"),
    ],
    ids=[
        "region-outside",
        "slides-late",
        "slides-past-end",
        "page-zero",
        "empty-captions",
        "long-hook",
    ],
)
def test_an_unfinished_clip_cannot_render(tmp_path, overrides, complaint):
    plan = plan_mod.load(_write_plan(tmp_path, _plan_dict(tmp_path, **overrides)))
    with pytest.raises(plan_mod.PlanError, match=complaint):
        plan_mod.require_render_fields(plan["clips"][0])


# ── captions ─────────────────────────────────────────────────────────


def test_captions_that_match_the_speech_take_its_timing_and_list_no_edits():
    spoken = _spoken(["We", "ship", "it."])
    words, edits = render_mod.align_captions(spoken, "We ship it.")
    assert edits == []
    assert [(w["start"], w["end"]) for w in words] == [
        (0.0, 0.4),
        (0.4, 0.8),
        (0.8, 1.2),
    ]


def test_a_grammar_fix_keeps_the_spoken_words_timing():
    spoken = _spoken("she have the ability to say stop now and talk to me".split())
    words, edits = render_mod.align_captions(
        spoken, "She has the ability to say stop now and talk to me"
    )
    assert edits == [{"op": "replace", "spoken": "have", "caption": "has"}]
    assert (words[1]["text"], words[1]["start"], words[1]["end"]) == ("has", 0.4, 0.8)


def test_a_stutter_is_dropped_from_the_captions_and_listed():
    spoken = _spoken("it's it's going to be all done in two weeks they said".split())
    words, edits = render_mod.align_captions(
        spoken, "It's going to be all done in two weeks, they said."
    )
    assert edits == [{"op": "delete", "spoken": "it's", "caption": ""}]
    assert [w["text"] for w in words][:2] == ["It's", "going"]


def test_an_inserted_word_is_timed_between_its_neighbours():
    spoken = _spoken(
        "I will give you more but explain what happened to the budget".split()
    )
    words, edits = render_mod.align_captions(
        spoken, "I will give you more, but explain what happened to the budget"
    )
    assert edits == []
    spoken = _spoken(
        "the amazing development and also everybody else here today".split()
    )
    words, edits = render_mod.align_captions(
        spoken, "the amazing development and also of everybody else here today"
    )
    assert edits == [{"op": "insert", "spoken": "", "caption": "of"}]
    inserted = words[5]
    assert words[4]["start"] <= inserted["start"] <= words[6]["start"]


def test_a_correction_that_puts_in_too_many_words_is_refused():
    said = "he built a signal system that tells him what is going on inside the factory every day"
    spoken = _spoken(said.split())
    with pytest.raises(render_mod.RenderError, match="puts in 4 words"):
        render_mod.align_captions(
            spoken, said.replace("a signal", "a really very very clever signal")
        )


def test_captions_that_drop_too_much_of_the_speech_are_refused():
    spoken = _spoken(
        "we will decide together how we move forward from here on out".split()
    )
    with pytest.raises(render_mod.RenderError, match="keep"):
        render_mod.align_captions(spoken, "we will decide how")


def test_caption_blocks_break_at_four_words_sentence_ends_and_pauses():
    words = _spoken(["One", "two", "three", "four", "five", "Done.", "Next"])
    words[-1] = {"text": "Next", "start": 4.0, "end": 4.4}
    blocks = render_mod.caption_blocks(words)
    assert [[w["text"] for w in b] for b in blocks] == [
        ["One", "two", "three", "four"],
        ["five", "Done."],
        ["Next"],
    ]


def test_the_highlight_runs_from_each_word_to_the_next_then_holds():
    blocks = render_mod.caption_blocks(_spoken(["We", "ship", "it."]))
    states = render_mod.caption_timeline(blocks, 5.0)
    active = [s for s in states if s[1] >= 0]
    for earlier, later in zip(active, active[1:]):
        assert later[3] == pytest.approx(earlier[4])
    assert states[-1][1] == -1
    assert states[-1][4] == pytest.approx(1.2 + render_mod.BLOCK_HOLD_SECONDS)


# ── speaker crop ─────────────────────────────────────────────────────


def test_the_crop_follows_the_face_inside_the_region_and_ignores_the_slide():
    crop, keyframes = render_mod.crop_track(
        _face_rows(), [0.3, 0.1, 0.4, 0.8], 0.5, 5.5, (1920, 1080)
    )
    face_h = 0.15 * 1080
    assert crop[1] == pytest.approx(face_h * render_mod.FACE_TO_CROP, abs=2)
    assert crop[0] % 2 == 0 and crop[1] % 2 == 0
    t, x, y = keyframes[0]
    assert x + crop[0] / 2 == pytest.approx(0.5 * 1920, abs=1)
    assert len(keyframes) == 1


def test_a_region_with_too_few_faces_is_refused():
    with pytest.raises(render_mod.RenderError, match="speaker_region"):
        render_mod.crop_track(
            _face_rows(), [0.8, 0.8, 0.1, 0.1], 0.5, 5.5, (1920, 1080)
        )


def test_the_crop_expression_passes_through_its_keyframes():
    keyframes = [(0.0, 100.0, 50.0), (2.0, 300.0, 50.0), (4.0, 200.0, 80.0)]
    for axis in (1, 2):
        expression = render_mod.crop_expression(keyframes, axis)
        for t, *values in keyframes:
            value = eval(
                expression, {"clip": lambda v, lo, hi: min(max(v, lo), hi), "t": t}
            )
            assert value == pytest.approx(values[axis - 1], abs=0.1)


# ── layout ───────────────────────────────────────────────────────────


def test_the_qr_card_holds_the_code_and_its_call_to_action(tmp_path):
    render_mod.qr_card("https://example.com/talk", tmp_path / "card.png")
    with Image.open(tmp_path / "card.png") as card:
        assert card.size == render_mod.QR_CARD[2:]
        margin = (render_mod.QR_CARD[2] - render_mod.QR_SIZE) // 2
        code = card.convert("RGB").crop(
            (margin, margin, margin + render_mod.QR_SIZE, margin + render_mod.QR_SIZE)
        )
        assert {(0, 0, 0), (255, 255, 255)} <= {
            c for _, c in code.getcolors(65536) or []
        }


def _overlaps(box, other):
    x, y, w, h = box
    ox, oy, ow, oh = other
    return x < ox + ow and ox < x + w and y < oy + oh and oy < y + h


@pytest.mark.parametrize("name", ["HOOK_BOX", "QR_CARD", "CAPTION_BOX"])
def test_what_carries_meaning_stays_clear_of_the_platform_overlays(name):
    x, y, w, h = getattr(render_mod, name)
    assert render_mod.SAFE_TOP <= y and y + h <= render_mod.SAFE_BOTTOM
    assert not _overlaps((x, y, w, h), render_mod.RAIL)
    assert 0 <= x and x + w <= render_mod.CANVAS[0]


def test_the_slide_and_speaker_fill_the_frame_below_the_hook():
    slide, bar, speaker = (
        render_mod.SLIDE_BOX,
        render_mod.BAR_BOX,
        render_mod.PRESENTER_BOX,
    )
    assert (
        render_mod.SAFE_TOP <= slide[1]
        and slide[1] + slide[3] <= render_mod.SAFE_BOTTOM
    )
    assert slide[1] + slide[3] == bar[1] and bar[1] + bar[3] == speaker[1]
    assert speaker[1] + speaker[3] == render_mod.CANVAS[1]


# ── end to end ───────────────────────────────────────────────────────


def test_a_prepared_clip_renders_and_passes_verification(tmp_path):
    plan_path = _prepared(tmp_path, _plan_dict(tmp_path))

    result = render_mod.render(plan_path, "01-test")

    assert result["caption_edits"] == []
    video = Path(result["video"])
    assert video.exists() and Path(result["txt"]).read_text().strip() == " ".join(WORDS)
    assert Path(result["srt"]).read_text().startswith("1\n00:00:00,100 --> ")
    checked = verify_mod.verify(plan_path, "01-test")
    assert checked["failures"] == []
    assert checked["ok"] is True
    assert Path(checked["review"]).exists()


@pytest.mark.parametrize(
    "payloads,failures",
    [(["https://example.com/talk"], 0), (["https://other.example"], 1), ([], 1)],
    ids=["matches", "other-link", "unreadable"],
)
def test_the_qr_card_must_decode_to_the_planned_link(
    tmp_path, monkeypatch, payloads, failures
):
    plan_path = _prepared(
        tmp_path, {**_plan_dict(tmp_path), "qr_url": "https://example.com/talk"}
    )
    render_mod.render(plan_path, "01-test")
    scanned = []

    def scan(plan, image):
        with Image.open(image) as card:
            scanned.append(card.size)
        return payloads

    monkeypatch.setattr(verify_mod, "_scan_qr", scan)
    checked = verify_mod.verify(plan_path, "01-test")
    assert scanned == [tuple(render_mod.QR_CARD[2:])]
    assert len(checked["failures"]) == failures
    assert checked["ok"] is (failures == 0)


def test_a_clip_moved_outside_its_prepared_window_must_be_prepared_again(tmp_path):
    plan_path = _prepared(tmp_path, _plan_dict(tmp_path, start=0.5, end=7.5))
    with pytest.raises(render_mod.RenderError, match="re-run prepare-clip.py"):
        render_mod.render(plan_path, "01-test")


def test_an_unprepared_clip_is_refused(tmp_path):
    plan_path = _write_plan(tmp_path, _plan_dict(tmp_path))
    with pytest.raises(render_mod.RenderError, match="not prepared"):
        render_mod.render(plan_path, "01-test")


# ── prepare ──────────────────────────────────────────────────────────


def test_prepare_writes_word_timings_frames_and_both_contact_sheets(
    tmp_path, monkeypatch
):
    plan_path = _prepared(tmp_path, _plan_dict(tmp_path, start=1.0, end=4.0))
    folder = tmp_path / "work" / "01-test"
    for name in ("words.json", "faces.json"):
        (folder / name).unlink()
    deck = tmp_path / "work" / "deck"
    for page in deck.glob("*.png"):
        page.rename(deck / f"source-{page.name}")
    real_run = prepare_mod._run

    def run(command, what):
        if command[0] == "pdftoppm":
            # pdftoppm pads page numbers to the page count's width.
            for number, source in enumerate(sorted(deck.glob("source-*.png")), start=1):
                source.rename(deck / f"raw-{number}.png")
            return ""
        return real_run(command, what)

    monkeypatch.setattr(prepare_mod, "_run", run)
    monkeypatch.setattr(
        prepare_mod,
        "probe_local_media",
        lambda path, trusted_root: SimpleNamespace(duration_seconds=6.0),
    )
    monkeypatch.setattr(
        prepare_mod,
        "transcribe_local_words",
        lambda *a, **k: (
            None,
            {
                "words": [
                    {"text": " hello", "start_seconds": 1.2, "end_seconds": 1.6},
                    {"text": " ", "start_seconds": 1.6, "end_seconds": 1.7},
                    {"text": " world", "start_seconds": 1.7, "end_seconds": 2.1},
                ]
            },
        ),
    )
    monkeypatch.setattr(
        prepare_mod,
        "detect_faces",
        lambda plan, frames: [
            {"t": prepare_mod.frame_time(p), "faces": []}
            for p in sorted(frames.glob("*.jpg"))
        ],
    )

    result = prepare_mod.prepare(plan_path, "01-test")

    assert result["window"] == [0.0, 6.0]
    words = json.loads((folder / "words.json").read_text())["words"]
    assert words == [
        {"text": "hello", "start": 1.2, "end": 1.6},
        {"text": "world", "start": 1.7, "end": 2.1},
    ]
    frames = sorted((folder / "frames").glob("*.jpg"))
    assert frames[0].name == "000000.00.jpg" and frames[1].name == "000000.50.jpg"
    assert (folder / "contact.jpg").exists() and (deck / "contact.jpg").exists()
    assert sorted(p.name for p in deck.glob("page-*.png")) == [
        "page-001.png",
        "page-002.png",
    ]


def test_a_clip_past_the_end_of_the_recording_is_refused(tmp_path):
    plan_path = _prepared(tmp_path, _plan_dict(tmp_path, start=5.0, end=9.0))
    with pytest.raises(prepare_mod.PrepareError, match="recording is"):
        prepare_mod.prepare(plan_path, "01-test")


def test_the_vision_helper_is_copied_to_a_runnable_name_once(tmp_path):
    plan = {"work_dir": tmp_path / "work"}
    script = plan_mod.vision_script(plan)
    assert script.name == "vision.swift"
    assert script.read_text() == (SCRIPTS / "vision.swift.txt").read_text()
    before = script.stat().st_mtime_ns
    assert (
        plan_mod.vision_script(plan) == script and script.stat().st_mtime_ns == before
    )


def test_the_scripts_refuse_with_json_and_exit_1(tmp_path):
    plan_path = _write_plan(tmp_path, _plan_dict(tmp_path))
    for script in ("render-short.py", "verify-short.py"):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / script),
                "--plan",
                str(plan_path),
                "--clip",
                "nope",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 1
        assert json.loads(completed.stdout)["ok"] is False
        assert "no clip 'nope'" in completed.stderr
