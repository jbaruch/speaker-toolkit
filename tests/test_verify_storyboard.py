"""Tests for verify-storyboard.py — the manifest lane of the #369 visual oracle.

The proposal's value rests on one claim: a verifier must FAIL each way a take can
look correct while being wrong. So the core of this file is #369's negative-test
list, each asserted to fail INDEPENDENTLY — a fixture that trips two checks at
once would let a broken predicate hide behind a working one.

Word timings in the fixture are the real measured values from the port-demo
narration take (`output/feasibility-voice-sync-2026-08-27.json`), copied as
literals so the suite stays deterministic and needs no media.
"""

import json

import pytest

# Real transcribed narration: " Hi, I'm Barok from Port and I'm going to show you
# something cool." Timings as measured, not invented.
REAL_WORDS = [
    {"word": " Hi,", "start": 0.0, "end": 0.62},
    {"word": " I'm", "start": 0.88, "end": 1.06},
    {"word": " Barok", "start": 1.06, "end": 1.38},
    {"word": " from", "start": 1.38, "end": 1.58},
    {"word": " Port", "start": 1.58, "end": 1.84},
    {"word": " and", "start": 1.84, "end": 2.14},
    {"word": " I'm", "start": 2.14, "end": 2.36},
    {"word": " going", "start": 2.36, "end": 2.56},
    {"word": " to", "start": 2.56, "end": 2.72},
    {"word": " show", "start": 2.72, "end": 2.88},
    {"word": " you", "start": 2.88, "end": 3.02},
    {"word": " something", "start": 3.02, "end": 3.26},
    {"word": " cool.", "start": 3.26, "end": 3.56},
]

VIEWPORT = {"width": 1600, "height": 900}


def manifest(**over):
    base = {
        "route": "/workflows/release_docs",
        "data_fingerprint": "sha256:rev-42",
        "viewport": dict(VIEWPORT),
        "zoom": 1.0,
        "scroll": {"x": 0, "y": 0},
        "transform": {"pan_x": 0, "pan_y": 0, "zoom": 1.0},
        "tabs": ["port/workflows", "github/order-api"],
        "active_tab": "port/workflows",
        "cursor": [800, 500],
        "labels": [{"text": "release_docs", "height_px": 28}],
    }
    base.update(over)
    return base


def sequence(**over):
    """A take that passes every checked axis. Negative tests perturb exactly one thing."""
    base = {
        "delivery": {"width": 1920, "height": 1080, "min_label_px": 14, "scale": 1.0},
        "narration": {"source": "actual_word_timestamps", "words": REAL_WORDS},
        "clips": [
            {
                "id": "a0-hook",
                "entry": manifest(),
                "exit": manifest(),
                "events": [
                    {"type": "pan", "axis": "x", "delta": -640, "t": 2.0},
                    {
                        "type": "click",
                        "t": 3.1,
                        "pointer": [420, 310],
                        "target_rect": [400, 300, 120, 40],
                    },
                ],
            },
            {"id": "a1-logic", "entry": manifest(), "exit": manifest(), "events": []},
        ],
        "rows": [
            {
                "id": "a0-hook-r1",
                "clip": "a0-hook",
                "phrase": "show you something cool",
                "proof_frame_t": 3.1,
                "require": {
                    "route": "/workflows/release_docs",
                    "data_fingerprint": "sha256:rev-42",
                    "visible_labels": ["release_docs"],
                    "content_bounds": [100, 100, 1200, 600],
                    "margin_px": 24,
                    "pan": {"axis": "x", "min_abs_delta": 200},
                    "click_on_target": True,
                },
            }
        ],
        "seam_tolerances": {"scroll": 2, "transform": 2},
    }
    base.update(over)
    return base


def codes(verdict):
    return {f["code"] for f in verdict["findings"]}


# --- the take that should pass -----------------------------------------------


def test_a_conforming_take_passes_every_checked_axis(verify_storyboard):
    v = verify_storyboard.verify(sequence())
    assert v["ok"] is True, v["findings"]
    assert v["axes"]["semantic"] == "pass"
    assert v["axes"]["geometry"] == "pass"
    assert v["axes"]["motion"] == "pass"
    assert v["axes"]["time"] == "pass"


def test_the_pixel_axis_is_never_reported_as_passing(verify_storyboard):
    """The whole point: an unchecked axis must read `unverified`, not `pass`.

    Reporting pass for something never examined converts an unknown into a false
    assurance — the exact failure #364 paid twenty-four hours for.
    """
    v = verify_storyboard.verify(sequence())
    assert v["ok"] is True
    assert v["axes"]["pixels"] == "unverified"
    assert "pixels" in v["unverified_axes"]


# --- #369's negative tests, each failing on its own --------------------------


def test_negative_1_correct_route_but_stale_data(verify_storyboard):
    s = sequence()
    s["clips"][0]["entry"]["data_fingerprint"] = "sha256:rev-41"
    v = verify_storyboard.verify(s)
    assert codes(v) == {"stale_data"}
    assert v["axes"]["semantic"] == "fail"


def test_negative_2_workflow_present_but_partly_clipped(verify_storyboard):
    s = sequence()
    s["rows"][0]["require"]["content_bounds"] = [100, 100, 1550, 600]  # exceeds width
    v = verify_storyboard.verify(s)
    assert codes(v) == {"content_clipped"}
    assert v["axes"]["geometry"] == "fail"


def test_negative_3_missing_horizontal_pan(verify_storyboard):
    s = sequence()
    s["clips"][0]["events"] = [e for e in s["clips"][0]["events"] if e["type"] != "pan"]
    v = verify_storyboard.verify(s)
    assert codes(v) == {"pan_not_performed"}
    assert v["axes"]["motion"] == "fail"


def test_negative_4_labels_below_readable_size_at_delivery(verify_storyboard):
    """Readable in the browser is not readable at delivery resolution."""
    s = sequence()
    s["clips"][0]["entry"]["labels"] = [{"text": "release_docs", "height_px": 20}]
    s["delivery"]["scale"] = 0.5  # 20px browser -> 10px delivered, under the 14 floor
    v = verify_storyboard.verify(s)
    assert codes(v) == {"label_below_readable_size"}
    assert v["axes"]["geometry"] == "fail"


def test_negative_5_cursor_off_the_clicked_target(verify_storyboard):
    s = sequence()
    s["clips"][0]["events"][1]["pointer"] = [900, 700]  # outside target_rect
    v = verify_storyboard.verify(s)
    assert codes(v) == {"cursor_off_target"}
    assert v["axes"]["motion"] == "fail"


def test_negative_7_scroll_pan_zoom_mismatch_across_a_seam(verify_storyboard):
    s = sequence()
    s["clips"][0]["exit"]["scroll"] = {"x": 0, "y": 400}
    v = verify_storyboard.verify(s)
    assert codes(v) == {"seam_state_mismatch"}
    assert {f["field"] for f in v["findings"]} == {"scroll"}


def test_negative_8_different_tab_set_across_a_seam(verify_storyboard):
    s = sequence()
    s["clips"][1]["entry"]["tabs"] = ["port/workflows"]
    v = verify_storyboard.verify(s)
    assert codes(v) == {"seam_tab_mismatch"}


def test_negative_8_different_active_tab_across_a_seam(verify_storyboard):
    s = sequence()
    s["clips"][1]["entry"]["active_tab"] = "github/order-api"
    v = verify_storyboard.verify(s)
    assert codes(v) == {"seam_tab_mismatch"}


def test_negative_10_timing_from_predicted_wpm_only(verify_storyboard):
    """WPM predicts feasibility; it never establishes synchronisation."""
    s = sequence()
    s["narration"]["source"] = "predicted_wpm"
    v = verify_storyboard.verify(s)
    assert codes(v) == {"timing_not_from_actual_words"}
    assert v["axes"]["time"] == "fail"


# --- the time axis against real measured narration ---------------------------


def test_proof_frame_outside_the_spoken_phrase_fails(verify_storyboard):
    """ "show you something cool" really spans 2.72-3.56s in the measured take."""
    s = sequence()
    s["rows"][0]["proof_frame_t"] = 4.5
    v = verify_storyboard.verify(s)
    assert codes(v) == {"proof_outside_phrase"}
    finding = v["findings"][0]
    assert finding["spoken"] == [2.72, 3.56]


def test_proof_frame_at_each_edge_of_the_real_span_passes(verify_storyboard):
    for t in (2.72, 3.56):
        s = sequence()
        s["rows"][0]["proof_frame_t"] = t
        assert verify_storyboard.verify(s)["ok"] is True, t


def test_a_phrase_never_spoken_is_reported(verify_storyboard):
    s = sequence()
    s["rows"][0]["phrase"] = "and then we deploy to production"
    v = verify_storyboard.verify(s)
    assert codes(v) == {"phrase_not_spoken"}


def test_phrase_matching_ignores_transcriber_punctuation_and_spacing(verify_storyboard):
    """Real words arrive as " Hi," and " cool." — punctuation must not decide this."""
    s = sequence()
    s["rows"][0]["phrase"] = "Hi I'm Barok"
    s["rows"][0]["proof_frame_t"] = 1.0
    assert verify_storyboard.verify(s)["ok"] is True


# --- structural -------------------------------------------------------------


def test_seam_tolerance_admits_sub_threshold_drift(verify_storyboard):
    s = sequence()
    s["clips"][0]["exit"]["scroll"] = {"x": 0, "y": 1}  # within tolerance of 2
    assert verify_storyboard.verify(s)["ok"] is True


def test_a_row_naming_an_absent_clip_is_reported(verify_storyboard):
    s = sequence()
    s["rows"][0]["clip"] = "does-not-exist"
    v = verify_storyboard.verify(s)
    assert codes(v) == {"clip_missing"}


def test_a_required_label_absent_from_the_frame_is_reported(verify_storyboard):
    s = sequence()
    s["clips"][0]["entry"]["labels"] = []
    v = verify_storyboard.verify(s)
    assert codes(v) == {"required_label_absent"}


def test_a_required_click_the_take_never_made_is_reported(verify_storyboard):
    s = sequence()
    s["clips"][0]["events"] = [
        e for e in s["clips"][0]["events"] if e["type"] != "click"
    ]
    v = verify_storyboard.verify(s)
    assert codes(v) == {"click_absent"}


def test_counts_report_rows_clips_and_seams(verify_storyboard):
    v = verify_storyboard.verify(sequence())
    assert v["counts"] == {"rows": 1, "clips": 2, "seams": 1}


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (
            lambda s: s["clips"][0]["entry"].update({"route": "/elsewhere"}),
            "route_mismatch",
        ),
        (lambda s: s["clips"][0]["exit"].update({"zoom": 1.25}), "seam_state_mismatch"),
    ],
)
def test_additional_single_defect_cases_stay_isolated(
    verify_storyboard, mutate, expected
):
    s = sequence()
    mutate(s)
    assert codes(verify_storyboard.verify(s)) == {expected}


# --- CLI --------------------------------------------------------------------


def test_main_exits_zero_and_emits_json_for_a_good_take(
    verify_storyboard, tmp_path, capsys
):
    p = tmp_path / "seq.json"
    p.write_text(json.dumps(sequence()), encoding="utf-8")
    rc = verify_storyboard.main([str(p)])
    out = capsys.readouterr()
    assert rc == 0
    assert json.loads(out.out)["ok"] is True
    assert "UNVERIFIED" in out.err  # the pixel caveat must reach the operator


def test_main_exits_one_on_a_failing_take(verify_storyboard, tmp_path, capsys):
    s = sequence()
    s["clips"][0]["entry"]["data_fingerprint"] = "sha256:wrong"
    p = tmp_path / "seq.json"
    p.write_text(json.dumps(s), encoding="utf-8")
    rc = verify_storyboard.main([str(p)])
    out = capsys.readouterr()
    assert rc == 1
    assert json.loads(out.out)["ok"] is False


def test_main_rejects_a_missing_file_with_an_actionable_message(
    verify_storyboard, tmp_path, capsys
):
    rc = verify_storyboard.main([str(tmp_path / "nope.json")])
    assert rc == 2
    assert "sequence-contract.md" in capsys.readouterr().err


def test_main_rejects_malformed_json(verify_storyboard, tmp_path, capsys):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    rc = verify_storyboard.main([str(p)])
    assert rc == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_finding_payload_cannot_shadow_a_reserved_field(verify_storyboard):
    """A pan axis and a verification axis are different things sharing a word.

    The first draft passed `axis="x"` as finding metadata, colliding with the
    verification axis — caught by these tests, not in review. All four reserved
    fields are named parameters, so Python itself rejects the shadowing.
    """
    for reserved in ("axis", "code", "subject", "message"):
        with pytest.raises(TypeError, match="multiple values"):
            verify_storyboard._finding("c", "motion", "s", "m", **{reserved: "x"})


def test_pan_findings_report_the_spatial_axis_under_its_own_key(verify_storyboard):
    s = sequence()
    s["clips"][0]["events"] = [e for e in s["clips"][0]["events"] if e["type"] != "pan"]
    finding = verify_storyboard.verify(s)["findings"][0]
    assert finding["axis"] == "motion"  # verification axis
    assert finding["pan_axis"] == "x"  # spatial axis
