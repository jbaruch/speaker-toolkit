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
    # every occurrence is reported, so the operator can see the real windows
    assert finding["spoken"] == [[2.72, 3.56]]


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


def test_pan_findings_report_the_spatial_axis_under_its_own_key(verify_storyboard):
    s = sequence()
    s["clips"][0]["events"] = [e for e in s["clips"][0]["events"] if e["type"] != "pan"]
    finding = verify_storyboard.verify(s)["findings"][0]
    assert finding["axis"] == "motion"  # verification axis
    assert finding["pan_axis"] == "x"  # spatial axis


# --- absence of evidence is never evidence of conformance (PR #432 review) ----
#
# The first draft passed an empty sequence on every axis — the exact
# "unexamined reported as passing" failure the pixel axis was careful to avoid,
# committed everywhere else.


def test_an_empty_sequence_does_not_pass(verify_storyboard):
    v = verify_storyboard.verify({})
    assert v["ok"] is False
    assert "sequence_empty" in codes(v)


def test_an_unexercised_axis_reads_unverified_not_pass(verify_storyboard):
    """A take asserting nothing about geometry has not passed geometry."""
    v = verify_storyboard.verify({})
    for axis in ("geometry", "motion", "time"):
        assert v["axes"][axis] == "unverified", axis
        assert axis in v["unverified_axes"]


def test_a_sequence_exercising_only_time_leaves_the_others_unverified(
    verify_storyboard,
):
    s = sequence()
    s["rows"][0]["require"] = {}  # keep phrase + proof_frame_t only
    v = verify_storyboard.verify(s)
    assert v["axes"]["time"] == "pass"
    assert v["axes"]["semantic"] == "pass"  # seam check still ran
    assert v["axes"]["geometry"] == "unverified"
    assert v["axes"]["motion"] == "unverified"


@pytest.mark.parametrize(
    "strip,requirement",
    [
        ("viewport", "content_bounds"),
        ("labels", "visible_labels"),
        ("route", "route"),
        ("data_fingerprint", "data_fingerprint"),
    ],
)
def test_a_requirement_without_its_evidence_is_refused_not_passed(
    verify_storyboard, strip, requirement
):
    s = sequence()
    del s["clips"][0]["entry"][strip]
    v = verify_storyboard.verify(s)
    assert "evidence_missing" in codes(v), (strip, v["findings"])
    assert any(f.get("requirement") == requirement for f in v["findings"])


def test_a_click_without_pointer_data_is_refused_not_passed(verify_storyboard):
    s = sequence()
    del s["clips"][0]["events"][1]["pointer"]
    v = verify_storyboard.verify(s)
    assert "evidence_missing" in codes(v)
    assert v["axes"]["motion"] == "fail"


def test_a_proof_frame_without_narration_is_refused_not_passed(verify_storyboard):
    s = sequence()
    s["narration"]["words"] = []
    v = verify_storyboard.verify(s)
    assert "evidence_missing" in codes(v)
    assert v["axes"]["time"] == "fail"


# --- a phrase spoken more than once (PR #432 review) --------------------------


def _twice():
    """Narration saying "ship it" at ~1s and again at ~5s."""
    return [
        {"word": "ship", "start": 1.0, "end": 1.4},
        {"word": "it", "start": 1.4, "end": 1.8},
        {"word": "then", "start": 3.0, "end": 3.4},
        {"word": "we", "start": 3.4, "end": 3.7},
        {"word": "ship", "start": 5.0, "end": 5.4},
        {"word": "it", "start": 5.4, "end": 5.8},
    ]


@pytest.mark.parametrize("proof_t", [1.2, 5.2])
def test_a_proof_frame_during_any_occurrence_passes(verify_storyboard, proof_t):
    """Matching only the first occurrence would fail a correctly-placed proof."""
    s = sequence()
    s["narration"]["words"] = _twice()
    s["rows"][0]["phrase"] = "ship it"
    s["rows"][0]["proof_frame_t"] = proof_t
    assert verify_storyboard.verify(s)["ok"] is True, proof_t


def test_a_proof_frame_between_occurrences_still_fails(verify_storyboard):
    s = sequence()
    s["narration"]["words"] = _twice()
    s["rows"][0]["phrase"] = "ship it"
    s["rows"][0]["proof_frame_t"] = 3.2  # spoken neither time
    v = verify_storyboard.verify(s)
    assert codes(v) == {"proof_outside_phrase"}
    assert v["findings"][0]["spoken"] == [[1.0, 1.8], [5.0, 5.8]]


# --- absence compared to absence is not agreement (PR #432 round 2) -----------


def test_a_required_label_without_a_measurement_cannot_pass_readability(
    verify_storyboard,
):
    """A label carrying only its text was silently skipped while geometry
    was still marked exercised — so it reported pass having judged nothing."""
    s = sequence()
    s["clips"][0]["entry"]["labels"] = [{"text": "release_docs"}]  # no height_px
    v = verify_storyboard.verify(s)
    assert "evidence_missing" in codes(v)
    assert v["axes"]["geometry"] == "fail"
    assert any(f.get("labels") == ["release_docs"] for f in v["findings"])


def test_a_seam_missing_a_field_on_both_sides_is_refused(verify_storyboard):
    """Two manifests carrying only a route compared equal as None and passed."""
    s = sequence()
    bare = {"route": "/only"}
    s["clips"][0]["exit"] = dict(bare)
    s["clips"][1]["entry"] = dict(bare)
    v = verify_storyboard.verify(s)
    assert "evidence_missing" in codes(v)
    missing = {
        f["field"]
        for f in v["findings"]
        if f["code"] == "evidence_missing" and "field" in f
    }
    assert {"tabs", "active_tab", "zoom", "scroll", "transform"} <= missing


def test_a_seam_missing_a_field_on_one_side_is_refused(verify_storyboard):
    s = sequence()
    del s["clips"][1]["entry"]["active_tab"]
    v = verify_storyboard.verify(s)
    finding = next(f for f in v["findings"] if f.get("field") == "active_tab")
    assert finding["code"] == "evidence_missing"
    assert finding["present_on_exit"] is True
    assert finding["present_on_entry"] is False


def test_a_fully_described_seam_still_passes(verify_storyboard):
    """The evidence gate must not make a complete, conforming seam fail."""
    assert verify_storyboard.verify(sequence())["ok"] is True


# --- CLI robustness (Copilot) ------------------------------------------------


def test_main_rejects_a_directory_with_exit_two(verify_storyboard, tmp_path, capsys):
    d = tmp_path / "adir"
    d.mkdir()
    assert verify_storyboard.main([str(d)]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_main_rejects_non_utf8_bytes_with_exit_two(verify_storyboard, tmp_path, capsys):
    p = tmp_path / "seq.json"
    p.write_bytes(b"\xff\xfe\x00\x01 not text")
    assert verify_storyboard.main([str(p)]) == 2
    assert "not UTF-8" in capsys.readouterr().err


def test_main_rejects_a_json_scalar_with_exit_two(verify_storyboard, tmp_path, capsys):
    p = tmp_path / "seq.json"
    p.write_text("[]", encoding="utf-8")
    assert verify_storyboard.main([str(p)]) == 2
    assert "must be a JSON object" in capsys.readouterr().err


# --- evidence gaps must fail the axis they block (PR #432, Copilot) -----------


def test_missing_viewport_fails_geometry_not_semantic(verify_storyboard):
    """Filing it under semantic let axes.geometry read pass with no evidence."""
    s = sequence()
    del s["clips"][0]["entry"]["viewport"]
    v = verify_storyboard.verify(s)
    finding = next(f for f in v["findings"] if f.get("requirement") == "content_bounds")
    assert finding["axis"] == "geometry"
    assert v["axes"]["geometry"] == "fail"


@pytest.mark.parametrize(
    "requirement,strip,axis",
    [
        ("route", "route", "semantic"),
        ("data_fingerprint", "data_fingerprint", "semantic"),
        ("visible_labels", "labels", "semantic"),
        ("content_bounds", "viewport", "geometry"),
    ],
)
def test_each_evidence_gap_is_filed_on_the_axis_it_blocks(
    verify_storyboard, requirement, strip, axis
):
    s = sequence()
    del s["clips"][0]["entry"][strip]
    v = verify_storyboard.verify(s)
    finding = next(f for f in v["findings"] if f.get("requirement") == requirement)
    assert finding["axis"] == axis
    assert v["axes"][axis] == "fail"


# --- a malformed document is refused, never crashes --------------------------


@pytest.mark.parametrize(
    "sequence_doc,fragment",
    [
        ({"clips": "nope"}, "clips must be a list"),
        ({"rows": {"a": 1}}, "rows must be a list"),
        ({"clips": ["not-an-object"]}, "clips[0] must be an object"),
        ({"rows": [{"clip": "x"}]}, "rows[0] needs a non-empty string id"),
        ({"clips": [{"id": ""}]}, "clips[0] needs a non-empty string id"),
        ({"clips": [{"id": 7}]}, "clips[0] needs a non-empty string id"),
        ({"narration": "words"}, "narration must be an object"),
        ({"narration": {"words": "no"}}, "narration.words must be a list"),
    ],
)
def test_structural_problems_are_described_not_raised(
    verify_storyboard, sequence_doc, fragment
):
    assert verify_storyboard.structural_problem(sequence_doc) == fragment


def test_a_conforming_sequence_has_no_structural_problem(verify_storyboard):
    assert verify_storyboard.structural_problem(sequence()) is None


def test_main_exits_two_on_a_malformed_sequence(verify_storyboard, tmp_path, capsys):
    p = tmp_path / "seq.json"
    p.write_text(json.dumps({"clips": [{"no_id": True}]}), encoding="utf-8")
    assert verify_storyboard.main([str(p)]) == 2
    err = capsys.readouterr().err
    assert "sequence contract" in err
    assert "sequence-contract.md" in err
