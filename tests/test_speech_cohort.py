"""Metadata-only cohort fixtures; no media, provider, or live vault access."""

import copy
from pathlib import Path

import pytest

from conftest import SCRIPTS_VP, _import_script


@pytest.fixture
def cohort():
    return _import_script(Path(SCRIPTS_VP) / "speech_cohort.py", "speech_cohort")


def talk(name, family="family-a", year="2020", mode="lecture", **extra):
    return {
        "filename": name,
        "date": year,
        "video_path": f"recordings/{name}.mp4",
        "structured_data": {
            "talk_family": family,
            "mode": mode,
            "delivery_language": "en",
            "co_presenter": False,
        },
        **extra,
    }


def database(*talks):
    return {"config": {"speaker_name": "Fixture Speaker"}, "talks": list(talks)}


def test_plan_balances_families_and_preserves_every_decision(cohort):
    source = database(talk("a"), talk("b"), talk("c", "family-b", "2021"))
    before = copy.deepcopy(source)
    plan = cohort.plan_cohort(
        source, "Fixture Speaker", language="en", maximum_recordings=2
    )
    assert plan["selected_recording_ids"] == ["a", "c"]
    assert plan["recordings"][1]["reasons"] == ["cohort_budget"]
    assert source == before
    source["talks"].reverse()
    assert (
        cohort.plan_cohort(
            source, "Fixture Speaker", language="en", maximum_recordings=2
        )
        == plan
    )


def test_explicit_duplicate_recording_is_counted_once(cohort):
    source = database(
        talk("a", youtube_id="abcdefghijk"),
        talk(
            "b",
            youtube_id="abcdefghijk",
            source_relation={"type": "duplicate", "target_filename": "a"},
        ),
    )
    plan = cohort.plan_cohort(source, "Fixture Speaker", language="en")
    assert plan["selected_recording_ids"] == ["a"]
    assert plan["recordings"][1]["reasons"] == ["duplicate_recording"]


def test_conflicting_duplicate_identity_is_not_guessed(cohort):
    source = database(
        talk("a", youtube_id="abcdefghijk"),
        talk("b", "different", youtube_id="abcdefghijk"),
    )
    plan = cohort.plan_cohort(source, "Fixture Speaker", language="en")
    assert plan["selected_recording_ids"] == []
    assert all(
        row["reasons"] == ["duplicate_recording_identity_unresolved"]
        for row in plan["recordings"]
    )


def test_excluded_duplicate_cannot_hide_a_multiple_speaker_declaration(cohort):
    canonical = talk("a", youtube_id="abcdefghijk")
    duplicate = talk(
        "b",
        youtube_id="abcdefghijk",
        source_relation={"type": "duplicate", "target_filename": "a"},
    )
    duplicate["structured_data"]["co_presenter"] = True
    plan = cohort.plan_cohort(
        database(canonical, duplicate), "Fixture Speaker", language="en"
    )
    assert plan["selected_recording_ids"] == []
    assert plan["recordings"][0]["reasons"] == [
        "duplicate_recording_identity_unresolved"
    ]
    assert plan["recordings"][1]["reasons"] == ["multiple_speakers"]


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("talk_family", None, "presentation_family_missing"),
        ("mode", None, "delivery_mode_missing"),
        ("delivery_language", None, "delivery_language_missing"),
        ("delivery_language", "fr", "different_delivery_language"),
        ("co_presenter", True, "multiple_speakers"),
        ("co_presenter", None, "solo_speaker_scope_unverified"),
        ("co_presenters", ["Second speaker"], "co_presenters_declared"),
    ],
)
def test_unverified_or_out_of_scope_metadata_is_not_inferred(
    cohort, field, value, reason
):
    row = talk("a")
    row["structured_data"][field] = value
    plan = cohort.plan_cohort(database(row), "Fixture Speaker", language="en")
    assert plan["selected_recording_ids"] == []
    assert reason in plan["recordings"][0]["reasons"]


def test_download_requires_explicit_option_and_never_runs_in_plan(cohort):
    source = database(talk("a", video_path=None, youtube_id="abcdefghijk"))
    refused = cohort.plan_cohort(source, "Fixture Speaker", language="en")
    assert refused["recordings"][0]["reasons"] == ["recording_download_not_enabled"]
    selected = cohort.plan_cohort(
        source, "Fixture Speaker", language="en", allow_download=True
    )
    assert selected["recordings"][0]["source"] == {
        "kind": "youtube",
        "video_id": "abcdefghijk",
    }


def test_conflicting_local_sources_are_not_silently_selected(cohort):
    source = database(talk("a", video_local_path="other.mp4"))
    plan = cohort.plan_cohort(source, "Fixture Speaker", language="en")
    assert plan["selected_recording_ids"] == []
    assert "local_recording_locator_conflict" in plan["recordings"][0]["reasons"]


def test_unknown_speaker_and_duplicate_talk_id_fail_closed(cohort):
    with pytest.raises(cohort.SpeechRateError, match="speaker explicitly named"):
        cohort.plan_cohort(database(talk("a")), "Another Speaker", language="en")
    with pytest.raises(cohort.SpeechRateError, match="duplicate talk identities"):
        cohort.plan_cohort(
            database(talk("a"), talk("a")), "Fixture Speaker", language="en"
        )


@pytest.mark.parametrize(
    "row", [{}, {"filename": None}, {"filename": 7}, {"filename": " padded "}]
)
def test_malformed_talk_identity_is_a_closed_error(cohort, row):
    with pytest.raises(cohort.SpeechRateError):
        cohort.plan_cohort(database(row), "Fixture Speaker", language="en")


@pytest.mark.parametrize("modes", [(None,), (["demo"],), ("demo", "demo")])
def test_invalid_demo_mode_declarations_fail_closed(cohort, modes):
    with pytest.raises(cohort.SpeechRateError):
        cohort.plan_cohort(
            database(talk("a")), "Fixture Speaker", language="en", demo_modes=modes
        )


@pytest.mark.parametrize(
    "duration,expected", [(3600, (1500, 600)), (300, (30, 240)), (240, (30, 180))]
)
def test_sample_window_uses_actual_source_duration(cohort, duration, expected):
    assert cohort.sample_window(duration) == expected


@pytest.mark.parametrize(
    "duration", [True, "600", float("nan"), float("inf"), -1, 239, 10**1000, 14401]
)
def test_inadequate_or_invalid_duration_refuses(cohort, duration):
    with pytest.raises(cohort.SpeechRateError):
        cohort.sample_window(duration)
