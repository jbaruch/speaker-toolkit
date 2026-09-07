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
from copy import deepcopy

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
    """A take that passes every checked axis. Negative tests perturb exactly one thing.

    Deep-copied: the sweep tests mutate nested values in place, and handing out a
    reference to module-level REAL_WORDS let one test corrupt the baseline for
    every test after it — an order-dependent suite that can pass for the wrong
    reason (rules/testing-standards.md Independence).
    """
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
    return deepcopy(base)


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


# --- malformed nested evidence (PR #432 round 3) -----------------------------
#
# Presence was not enough: `viewport: {}` is present and useless, and accepting
# it let a required content_bounds report geometry pass having compared nothing.


@pytest.mark.parametrize(
    "doc,fragment",
    [
        ({"clips": [{"id": "a", "entry": "text"}]}, "clips[0].entry must be an object"),
        (
            {"clips": [{"id": "a", "entry": {"viewport": {}}}]},
            "clips[0].entry.viewport.width must be a positive number",
        ),
        (
            {"clips": [{"id": "a", "entry": {"viewport": {"width": 0, "height": 9}}}]},
            "clips[0].entry.viewport.width must be a positive number",
        ),
        (
            {"clips": [{"id": "a", "entry": {"viewport": "big"}}]},
            "clips[0].entry.viewport must be an object",
        ),
        (
            {"clips": [{"id": "a", "entry": {"labels": [{"height_px": 9}]}}]},
            "clips[0].entry.labels[0].text must be a string",
        ),
        (
            {"clips": [{"id": "a", "entry": {"labels": "none"}}]},
            "clips[0].entry.labels must be a list",
        ),
        (
            {
                "clips": [
                    {
                        "id": "a",
                        "events": [{"type": "click", "pointer": [], "target_rect": []}],
                    }
                ]
            },
            "clips[0].events[0].pointer must be 2 numbers",
        ),
        (
            {
                "clips": [
                    {
                        "id": "a",
                        "events": [
                            {"type": "click", "pointer": [1, 2], "target_rect": [1]}
                        ],
                    }
                ]
            },
            "clips[0].events[0].target_rect must be 4 finite numbers",
        ),
        ({"clips": [{"id": "a", "events": "none"}]}, "clips[0].events must be a list"),
        (
            {"rows": [{"id": "r", "require": {"content_bounds": [1, 2]}}]},
            "rows[0].require.content_bounds must be 4 finite numbers",
        ),
        (
            {"narration": {"words": [{"word": "x", "start": "0", "end": 1}]}},
            "narration.words[0].start must be a finite number",
        ),
    ],
)
def test_malformed_nested_evidence_is_refused(verify_storyboard, doc, fragment):
    assert verify_storyboard.structural_problem(doc) == fragment


def test_a_boolean_is_not_accepted_as_a_coordinate(verify_storyboard):
    """bool is an int in Python; a True pointer is not a coordinate."""
    doc = {
        "clips": [
            {
                "id": "a",
                "events": [
                    {"type": "click", "pointer": [True, 2], "target_rect": [1, 2, 3, 4]}
                ],
            }
        ]
    }
    assert (
        verify_storyboard.structural_problem(doc)
        == "clips[0].events[0].pointer must be 2 numbers"
    )


def test_a_present_but_null_manifest_does_not_crash(verify_storyboard):
    """`clip.get("entry", {})` returns None for a present null key, not {}."""
    s = sequence()
    s["clips"][0]["entry"] = None
    v = verify_storyboard.verify(s)  # must not raise
    assert v["ok"] is False
    assert "evidence_missing" in codes(v)


def test_main_exits_two_rather_than_tracebacking_on_an_unexpected_shape(
    verify_storyboard, tmp_path, capsys, monkeypatch
):
    """The contract promises exit 2 and a diagnostic, never a traceback."""

    def boom(_seq):
        raise TypeError("simulated shape the validator did not anticipate")

    monkeypatch.setattr(verify_storyboard, "verify", boom)
    p = tmp_path / "seq.json"
    p.write_text(json.dumps(sequence()), encoding="utf-8")
    assert verify_storyboard.main([str(p)]) == 2
    assert "could not be verified" in capsys.readouterr().err


# --- a refused requirement is skipped, not judged (PR #432 round 4) -----------
#
# Every finding in this round was one structure: checks ran after their evidence
# gate had already refused them, producing a verdict about nothing and two codes
# for one defect.


def test_missing_labels_yields_one_finding_not_two(verify_storyboard):
    """`required_label_absent` is a judgement; with no labels there is nothing to judge."""
    s = sequence()
    del s["clips"][0]["entry"]["labels"]
    v = verify_storyboard.verify(s)
    assert codes(v) == {"evidence_missing"}
    assert "required_label_absent" not in codes(v)


def test_missing_route_evidence_does_not_also_report_a_mismatch(verify_storyboard):
    s = sequence()
    del s["clips"][0]["entry"]["route"]
    v = verify_storyboard.verify(s)
    assert codes(v) == {"evidence_missing"}
    assert "route_mismatch" not in codes(v)


def test_missing_data_evidence_does_not_also_report_stale_data(verify_storyboard):
    s = sequence()
    del s["clips"][0]["entry"]["data_fingerprint"]
    v = verify_storyboard.verify(s)
    assert codes(v) == {"evidence_missing"}
    assert "stale_data" not in codes(v)


def test_a_click_without_evidence_does_not_also_report_cursor_off_target(
    verify_storyboard,
):
    s = sequence()
    del s["clips"][0]["events"][1]["target_rect"]
    v = verify_storyboard.verify(s)
    assert codes(v) == {"evidence_missing"}
    assert "cursor_off_target" not in codes(v)


def test_no_narration_does_not_also_report_phrase_not_spoken(verify_storyboard):
    s = sequence()
    s["narration"]["words"] = []
    v = verify_storyboard.verify(s)
    assert codes(v) == {"evidence_missing"}
    assert "phrase_not_spoken" not in codes(v)


def test_an_unmeasured_label_does_not_also_report_below_readable_size(
    verify_storyboard,
):
    s = sequence()
    s["clips"][0]["entry"]["labels"] = [{"text": "release_docs"}]
    v = verify_storyboard.verify(s)
    assert codes(v) == {"evidence_missing"}
    assert "label_below_readable_size" not in codes(v)


# --- non-finite and incomplete evidence (PR #432 round 4) --------------------


def test_a_nan_measurement_is_refused_not_passed(verify_storyboard):
    """JSON admits NaN, and every comparison with NaN is false — so a NaN
    height silently satisfies any readability threshold it is tested against."""
    doc = {
        "clips": [
            {"id": "a", "entry": {"labels": [{"text": "x", "height_px": float("nan")}]}}
        ]
    }
    assert (
        verify_storyboard.structural_problem(doc)
        == "clips[0].entry.labels[0].height_px must be a finite number"
    )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_not_numbers(verify_storyboard, bad):
    assert verify_storyboard._is_number(bad) is False
    assert verify_storyboard._numbers([bad, 1.0], 2) is False


@pytest.mark.parametrize(
    "doc,fragment",
    [
        (
            {"clips": [{"id": "a", "entry": {"scroll": {}}}]},
            "clips[0].entry.scroll must carry x",
        ),
        (
            {"clips": [{"id": "a", "entry": {"scroll": {"x": 1}}}]},
            "clips[0].entry.scroll must carry y",
        ),
        (
            {"clips": [{"id": "a", "entry": {"transform": {"pan_x": 0, "pan_y": 0}}}]},
            "clips[0].entry.transform must carry zoom",
        ),
        (
            {"clips": [{"id": "a", "entry": {"scroll": {"x": float("nan"), "y": 0}}}]},
            "clips[0].entry.scroll.x must be a finite number",
        ),
        (
            {"clips": [{"id": "a", "entry": {"zoom": float("inf")}}]},
            "clips[0].entry.zoom must be a finite number",
        ),
    ],
)
def test_incomplete_continuity_evidence_is_refused(verify_storyboard, doc, fragment):
    """Two empty scroll objects compare equal — agreement between two absences."""
    assert verify_storyboard.structural_problem(doc) == fragment


def test_seam_tolerance_does_not_default_a_missing_key_to_zero(verify_storyboard):
    """`before.get(k, 0)` read an absent key as 0 and called the gap in-tolerance."""
    s = sequence()
    s["clips"][0]["exit"]["scroll"] = {"x": 0}  # y absent on one side only
    v = verify_storyboard.verify(s)
    assert v["ok"] is False
    assert "scroll" in {f.get("field") for f in v["findings"]}


# --- every numeric in the contract must be finite (PR #432 round 5) -----------
#
# Five rounds of "this particular number was not validated". This sweeps the
# whole contract instead of naming instances: a NaN anywhere a number is read
# must be refused, because NaN satisfies every comparison it is tested against.

NUMERIC_PATHS = [
    ("delivery", "width"),
    ("delivery", "height"),
    ("delivery", "min_label_px"),
    ("delivery", "scale"),
    ("clips", 0, "entry", "viewport", "width"),
    ("clips", 0, "entry", "viewport", "height"),
    ("clips", 0, "entry", "zoom"),
    ("clips", 0, "entry", "scroll", "x"),
    ("clips", 0, "entry", "scroll", "y"),
    ("clips", 0, "entry", "transform", "pan_x"),
    ("clips", 0, "entry", "transform", "zoom"),
    ("clips", 0, "entry", "labels", 0, "height_px"),
    ("clips", 0, "events", 0, "delta"),
    ("clips", 0, "events", 0, "t"),
    ("clips", 0, "events", 1, "pointer", 0),
    ("clips", 0, "events", 1, "target_rect", 0),
    ("rows", 0, "proof_frame_t"),
    ("rows", 0, "require", "margin_px"),
    ("rows", 0, "require", "content_bounds", 0),
    ("rows", 0, "require", "pan", "min_abs_delta"),
    ("narration", "words", 0, "start"),
    ("narration", "words", 0, "end"),
    ("seam_tolerances", "scroll"),
]


def _poke(doc, path, value):
    node = doc
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return doc


@pytest.mark.parametrize("path", NUMERIC_PATHS, ids=lambda p: ".".join(map(str, p)))
def test_a_nan_anywhere_a_number_is_read_is_refused(verify_storyboard, path):
    doc = _poke(sequence(), path, float("nan"))
    assert verify_storyboard.structural_problem(doc) is not None, path


@pytest.mark.parametrize("path", NUMERIC_PATHS, ids=lambda p: ".".join(map(str, p)))
def test_the_baseline_sequence_is_finite_everywhere_it_is_poked(
    verify_storyboard, path
):
    """Guards the sweep: a path that does not exist would make the test vacuous."""
    node = sequence()
    for step in path:
        node = node[step]
    assert isinstance(node, (int, float)) and not isinstance(node, bool), path


def test_a_nan_scale_cannot_pass_readability(verify_storyboard, tmp_path, capsys):
    """scale=NaN made a 1px label meet a 14px floor: NaN < 14 is False."""
    s = sequence()
    s["delivery"]["scale"] = float("nan")
    s["clips"][0]["entry"]["labels"] = [{"text": "release_docs", "height_px": 1}]
    p = tmp_path / "seq.json"
    p.write_text(json.dumps(s), encoding="utf-8")
    assert verify_storyboard.main([str(p)]) == 2
    assert "delivery.scale must be a positive finite number" in capsys.readouterr().err


def test_a_proof_frame_without_a_phrase_is_refused(verify_storyboard):
    """Silently skipping it let a sibling row's pass carry the whole time axis."""
    s = sequence()
    del s["rows"][0]["phrase"]
    assert (
        verify_storyboard.structural_problem(s)
        == "rows[0] declares proof_frame_t but no phrase to prove it against"
    )


def test_a_blank_phrase_is_refused_like_a_missing_one(verify_storyboard):
    s = sequence()
    s["rows"][0]["phrase"] = "   "
    assert "no phrase to prove it against" in verify_storyboard.structural_problem(s)


def test_one_incomplete_row_is_not_masked_by_a_valid_sibling(verify_storyboard):
    """The reviewer's case: a good row's pass must not cover an unchecked one."""
    s = sequence()
    s["rows"].append({"id": "r2", "clip": "a0-hook", "proof_frame_t": 3.1})
    assert verify_storyboard.structural_problem(s) is not None


# --- suite independence and incomplete requirements (PR #432 round 6) ---------


def test_the_sequence_builder_shares_no_state_between_calls(verify_storyboard):
    """The sweep mutates nested values in place; a shared baseline let one test
    corrupt every test after it, so later cases could pass for the wrong reason."""
    first = sequence()
    first["narration"]["words"][0]["start"] = float("nan")
    first["clips"][0]["entry"]["viewport"]["width"] = -1
    first["rows"][0]["require"]["visible_labels"].append("injected")

    second = sequence()
    assert second["narration"]["words"][0]["start"] == 0.0
    assert second["clips"][0]["entry"]["viewport"]["width"] == 1600
    assert second["rows"][0]["require"]["visible_labels"] == ["release_docs"]
    assert verify_storyboard.structural_problem(second) is None


def test_module_level_word_data_is_never_handed_out_by_reference():
    assert sequence()["narration"]["words"] is not REAL_WORDS
    assert sequence()["narration"]["words"][0] is not REAL_WORDS[0]


@pytest.mark.parametrize(
    "pan,fragment",
    [
        ({"axis": "x"}, "rows[0].require.pan must carry min_abs_delta"),
        ({"axis": "x", "min_abs_delta": 0}, "must be a positive finite number"),
        ({"axis": "x", "min_abs_delta": -5}, "must be a positive finite number"),
        ({"axis": "x", "min_abs_delta": "200"}, "must be a positive finite number"),
    ],
)
def test_an_incomplete_pan_requirement_is_refused(verify_storyboard, pan, fragment):
    """A threshold defaulting to 0 is satisfied by a take that never panned."""
    s = sequence()
    s["rows"][0]["require"]["pan"] = pan
    problem = verify_storyboard.structural_problem(s)
    assert problem is not None and fragment in problem


def test_a_pan_requirement_with_a_real_threshold_still_works(verify_storyboard):
    s = sequence()
    s["rows"][0]["require"]["pan"] = {"axis": "x", "min_abs_delta": 200}
    assert verify_storyboard.verify(s)["ok"] is True
    s["clips"][0]["events"] = [e for e in s["clips"][0]["events"] if e["type"] != "pan"]
    assert "pan_not_performed" in codes(verify_storyboard.verify(s))


# --- exercised must mean "a check ran" (PR #432 round 7) ---------------------


@pytest.mark.parametrize(
    "doc,fragment",
    [
        ({"clips": [{"id": "a"}, {"id": "a"}]}, "clips[1] repeats the id 'a'"),
        (
            {"rows": [{"id": "r"}, {"id": "x"}, {"id": "r"}]},
            "rows[2] repeats the id 'r'",
        ),
    ],
)
def test_duplicate_ids_are_refused(verify_storyboard, doc, fragment):
    """clips are looked up by id; a duplicate silently replaced the earlier one,
    so a conforming clip could stand in for the failing one a row named."""
    assert verify_storyboard.structural_problem(doc) == fragment


def test_a_later_clip_cannot_shadow_an_earlier_failing_one(verify_storyboard):
    s = sequence()
    stale = deepcopy(s["clips"][0])
    stale["entry"]["data_fingerprint"] = "sha256:stale"
    s["clips"] = [stale, deepcopy(s["clips"][0])]  # same id twice
    assert verify_storyboard.structural_problem(s) is not None


def test_an_absent_labels_field_leaves_geometry_unverified_not_passing(
    verify_storyboard,
):
    """Readability was never measured, so geometry has not passed."""
    s = sequence()
    del s["clips"][0]["entry"]["labels"]
    del s["rows"][0]["require"]["content_bounds"]  # isolate the readability lane
    v = verify_storyboard.verify(s)
    assert v["axes"]["geometry"] == "unverified"
    assert v["axes"]["geometry"] != "pass"


def test_an_absent_delivery_scale_blocks_readability(verify_storyboard):
    """Defaulting scale to 1.0 assumed the conversion from recorded to delivered."""
    s = sequence()
    del s["delivery"]["scale"]
    v = verify_storyboard.verify(s)
    assert "evidence_missing" in codes(v)
    assert any(f.get("missing_field") == "delivery.scale" for f in v["findings"])
    assert v["axes"]["geometry"] == "fail"


def test_a_blocked_check_does_not_mark_its_axis_exercised(verify_storyboard):
    """The invariant behind every 'unverified vs pass' fix in this PR."""
    s = sequence()
    s["rows"][0]["require"] = {"click_on_target": True}
    del s["clips"][0]["events"][1]["pointer"]
    v = verify_storyboard.verify(s)
    assert v["axes"]["motion"] == "fail"  # evidence_missing fires

    s2 = sequence()
    s2["rows"][0]["require"] = {"route": "/workflows/release_docs"}
    del s2["clips"][0]["entry"]["route"]
    v2 = verify_storyboard.verify(s2)
    # semantic still fails on the evidence gap, never passes on a skipped check
    assert v2["axes"]["semantic"] == "fail"


# --- declared-but-unusable requirements (PR #432 round 8) --------------------


@pytest.mark.parametrize(
    "require,fragment",
    [
        ({"content_bounds": None}, "must be 4 finite numbers"),
        ({"content_bounds": [110, 10, -20, 20]}, "must have positive width and height"),
        ({"content_bounds": [0, 0, 10, 0]}, "must have positive width and height"),
        ({"margin_px": -5}, "must be a non-negative finite number"),
        ({"margin_px": "8"}, "must be a non-negative finite number"),
    ],
)
def test_a_declared_but_unusable_requirement_is_refused(
    verify_storyboard, require, fragment
):
    """`content_bounds: null` validated, then made the geometry check skip
    itself — a requirement that was declared and verified nothing."""
    s = sequence()
    s["rows"][0]["require"].update(require)
    problem = verify_storyboard.structural_problem(s)
    assert problem is not None and fragment in problem


@pytest.mark.parametrize("field", ["width", "height", "min_label_px", "scale"])
@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_delivery_values_are_refused(verify_storyboard, field, value):
    """min_label_px <= 0 makes readability vacuously true; scale 0 erases the
    measurement it converts."""
    s = sequence()
    s["delivery"][field] = value
    problem = verify_storyboard.structural_problem(s)
    assert problem == f"delivery.{field} must be a positive finite number"


def test_a_zero_margin_is_still_allowed(verify_storyboard):
    """Non-negative, not positive: a flush-to-edge requirement is legitimate."""
    s = sequence()
    s["rows"][0]["require"]["margin_px"] = 0
    assert verify_storyboard.structural_problem(s) is None


# --- an explicit null is not an absent key (PR #432 round 9) -----------------
#
# `content_bounds: null` was fixed last round; its sibling `pan: null` was not.
# Every validator now guards on key presence, so a declared-null cannot skip
# both its validation and the check it gates.


@pytest.mark.parametrize(
    "path,fragment",
    [
        (("rows", 0, "require", "pan"), "rows[0].require.pan must be an object"),
        (("rows", 0, "require", "content_bounds"), "must be 4 finite numbers"),
        (("rows", 0, "require", "margin_px"), "must be a non-negative finite number"),
        (("rows", 0, "proof_frame_t"), "rows[0].proof_frame_t must be a finite number"),
        (("rows", 0, "require"), "rows[0].require must be an object"),
        (("clips", 0, "events"), "clips[0].events must be a list"),
        (
            ("clips", 0, "entry", "viewport"),
            "clips[0].entry.viewport must be an object",
        ),
        (("clips", 0, "entry", "labels"), "clips[0].entry.labels must be a list"),
        (("clips", 0, "entry", "tabs"), "clips[0].entry.tabs must be a list"),
        (("clips", 0, "entry", "zoom"), "clips[0].entry.zoom must be a finite number"),
    ],
)
def test_an_explicit_null_is_refused_wherever_a_value_is_declared(
    verify_storyboard, path, fragment
):
    doc = _poke(sequence(), path, None)
    problem = verify_storyboard.structural_problem(doc)
    assert problem is not None, f"null at {path} was accepted"
    assert fragment in problem


def test_a_null_pan_cannot_pass_without_the_pan_being_performed(verify_storyboard):
    """The exact regression: null skipped validation AND the motion check."""
    s = sequence()
    s["rows"][0]["require"]["pan"] = None
    s["clips"][0]["events"] = [e for e in s["clips"][0]["events"] if e["type"] != "pan"]
    assert verify_storyboard.structural_problem(s) is not None


def test_the_click_evidence_gap_names_the_missing_field(verify_storyboard):
    """ "pointer/target_rect" read as though both were absent when one was."""
    s = sequence()
    del s["clips"][0]["events"][1]["target_rect"]
    finding = next(
        f
        for f in verify_storyboard.verify(s)["findings"]
        if f["code"] == "evidence_missing"
    )
    assert finding["missing_field"] == "events[].target_rect"
    assert "pointer" not in finding["message"]


# --- every declared requirement carries a type (PR #432 round 10) ------------


@pytest.mark.parametrize(
    "require,fragment",
    [
        ({"visible_labels": None}, "visible_labels must be a list of strings"),
        (
            {"visible_labels": "release_docs"},
            "visible_labels must be a list of strings",
        ),
        ({"visible_labels": [1, 2]}, "visible_labels must be a list of strings"),
        ({"click_on_target": None}, "click_on_target must be a boolean"),
        ({"click_on_target": "yes"}, "click_on_target must be a boolean"),
        ({"click_on_target": 1}, "click_on_target must be a boolean"),
        ({"route": 7}, "route must be a string"),
        ({"data_fingerprint": ["x"]}, "data_fingerprint must be a string"),
    ],
)
def test_every_declared_requirement_is_type_checked(
    verify_storyboard, require, fragment
):
    """visible_labels and click_on_target had no type check at all, so `null`
    passed validation and silently skipped the check it declared."""
    s = sequence()
    s["rows"][0]["require"].update(require)
    problem = verify_storyboard.structural_problem(s)
    assert problem is not None and fragment in problem


@pytest.mark.parametrize("rect", [[1, 1, 0, 0], [1, 1, 10, 0], [1, 1, -5, 5]])
def test_a_target_rect_with_no_area_is_refused(verify_storyboard, rect):
    """A rect of zero area contains no point, so no click can land on it —
    yet the containment test reported motion: pass."""
    s = sequence()
    s["clips"][0]["events"][1]["target_rect"] = rect
    problem = verify_storyboard.structural_problem(s)
    assert problem is not None and "positive width and height" in problem


def test_a_real_target_rect_still_verifies_the_click(verify_storyboard):
    s = sequence()
    assert verify_storyboard.verify(s)["ok"] is True
    s["clips"][0]["events"][1]["pointer"] = [9000, 9000]
    assert "cursor_off_target" in codes(verify_storyboard.verify(s))


# --- unrepresentable and non-numeric edges (PR #432 round 11) ----------------

HUGE_INT = 10**400  # a Python int with no float representation


def test_an_unrepresentable_integer_is_not_finite(verify_storyboard):
    """math.isfinite raises OverflowError rather than answering, and that
    escaped structural_problem() as a traceback instead of exit 2."""
    assert verify_storyboard._is_number(HUGE_INT) is False


@pytest.mark.parametrize(
    "path",
    [
        ("delivery", "width"),
        ("rows", 0, "proof_frame_t"),
        ("clips", 0, "entry", "zoom"),
    ],
)
def test_an_unrepresentable_integer_is_refused_wherever_a_number_is_read(
    verify_storyboard, path
):
    doc = _poke(sequence(), path, HUGE_INT)
    assert verify_storyboard.structural_problem(doc) is not None


def test_main_exits_two_on_an_unrepresentable_integer(
    verify_storyboard, tmp_path, capsys
):
    s = sequence()
    s["delivery"]["width"] = HUGE_INT
    p = tmp_path / "seq.json"
    p.write_text(json.dumps(s), encoding="utf-8")
    assert verify_storyboard.main([str(p)]) == 2
    assert "delivery.width must be a positive finite number" in capsys.readouterr().err


def test_a_non_numeric_extra_key_in_a_tolerated_field_does_not_crash(
    verify_storyboard,
):
    """Structural validation enforces the required keys; an extra one with a
    non-numeric value reached the tolerance subtraction and raised TypeError."""
    s = sequence()
    s["clips"][0]["exit"]["scroll"] = {"x": 0, "y": 0, "note": "annotated"}
    s["clips"][1]["entry"]["scroll"] = {"x": 0, "y": 0, "note": "annotated"}
    v = verify_storyboard.verify(s)  # must not raise
    assert isinstance(v["ok"], bool)


def test_a_non_numeric_extra_key_reports_a_mismatch_rather_than_passing(
    verify_storyboard,
):
    s = sequence()
    s["clips"][0]["exit"]["scroll"] = {"x": 0, "y": 0, "note": "a"}
    s["clips"][1]["entry"]["scroll"] = {"x": 0, "y": 0, "note": "b"}
    v = verify_storyboard.verify(s)
    assert "seam_state_mismatch" in codes(v)
