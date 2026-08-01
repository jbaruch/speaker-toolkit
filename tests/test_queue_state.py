"""Queue-state contract tests for vault-ingress.

All timestamps are injected and every fixture is local. The CLI never reaches a
network or reads subagent returns.
"""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "vault-ingress"
    / "scripts"
    / "queue-state.py"
)
NOW = "2026-07-31T18:00:00+00:00"


def _talk(video_id, *, status="pending", filename=None, video=True) -> dict[str, object]:
    filename = filename or f"playlist-{video_id}.md"
    return {
        "filename": filename,
        "title": filename,
        "status": status,
        "video_url": (
            f"https://www.youtube.com/watch?v={video_id}" if video else ""
        ),
        "youtube_id": video_id,
    }


def _write_db(tmp_path, talks):
    path = tmp_path / "tracking-database.json"
    path.write_text(
        json.dumps({"config": {}, "talks": talks}, indent=2),
        encoding="utf-8",
    )
    return path


def _read_db(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _run(path, *arguments):
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), *arguments],
        capture_output=True,
        text=True,
        env=environment,
    )


def _claim(path, *, run_id="run-1", batch_id="batch-1", limit=5, filenames=()):
    arguments = [
        "claim",
        "--run-id", run_id,
        "--batch-id", batch_id,
        "--now", NOW,
        "--limit", str(limit),
    ]
    for filename in filenames:
        arguments.extend(("--filename", filename))
    return _run(path, *arguments)


def test_claim_recovers_the_two_stranded_transcript_statuses(tmp_path):
    """The two real vault rows with videos must re-enter the processable queue."""
    talks = [
        _talk("eixm_f7Jpdc", status="skipped_no_transcript"),
        _talk("QS-_4k7o7A4", status="skipped_no_transcript"),
        _talk("abcdefghijk", status="skipped_no_video", video=False),
        _talk("lmnopqrstuv", status="skipped_duplicate"),
        _talk("wxyzABCDEF0", status="pending", video=False),
    ]
    path = _write_db(tmp_path, talks)

    result = _claim(path, limit=10)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [item["filename"] for item in payload["claimed"]] == [
        "playlist-QS-_4k7o7A4.md",
        "playlist-eixm_f7Jpdc.md",
    ]
    assert {item["previous_status"] for item in payload["claimed"]} == {"pending"}
    assert all(item["reprocess_generation"] == 1 for item in payload["claimed"])
    records = {talk["filename"]: talk for talk in _read_db(path)["talks"]}
    assert records["playlist-eixm_f7Jpdc.md"]["status"] == "reprocessing-inflight"
    assert records["playlist-QS-_4k7o7A4.md"]["status"] == "reprocessing-inflight"
    assert records["playlist-abcdefghijk.md"]["status"] == "skipped_no_sources"
    assert records["playlist-lmnopqrstuv.md"]["status"] == "skipped_duplicate"
    assert records["playlist-wxyzABCDEF0.md"]["status"] == "pending"
    assert not [item for item in tmp_path.iterdir() if item.name.endswith(".partial")]


def test_legacy_no_video_status_with_video_is_normalized_and_claimed(tmp_path):
    path = _write_db(
        tmp_path,
        [_talk("eg6gqvUFh6Q", status="skipped_no_video")],
    )

    result = _claim(path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["normalizations"] == [{
        "filename": "playlist-eg6gqvUFh6Q.md",
        "previous_status": "skipped_no_video",
        "status": "pending",
        "video_present": True,
        "source_capabilities": ["video", "transcript"],
    }]
    assert payload["claimed"][0]["previous_status"] == "pending"


@pytest.mark.parametrize("source_fields,expected_capability", [
    ({"slides_url": "https://drive.google.com/open?id=deck"}, "slides"),
    ({"pptx_path": "decks/talk.pptx"}, "slides"),
    ({"slides_local_path": "slides/talk.pdf"}, "slides"),
    ({"transcript_path": "transcripts/talk.txt"}, "transcript"),
])
def test_legacy_no_video_talk_with_nonvideo_source_is_claimable(
        tmp_path, source_fields, expected_capability):
    talk = _talk(
        "abcdefghijk", status="skipped_no_video", video=False,
        filename="source-only.md",
    )
    talk.update(source_fields)
    path = _write_db(tmp_path, [talk])

    result = _claim(path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["normalizations"] == [{
        "filename": "source-only.md",
        "previous_status": "skipped_no_video",
        "status": "pending",
        "video_present": False,
        "source_capabilities": [expected_capability],
    }]
    assert payload["claimed"][0]["filename"] == "source-only.md"
    assert payload["claimed"][0]["previous_status"] == "pending"


def test_manual_provenance_label_without_artifact_is_not_a_capability(tmp_path):
    talk = _talk(
        "abcdefghijk",
        status="skipped_no_video",
        video=False,
        filename="label-only.md",
    )
    talk["transcript_source"] = "manual"
    path = _write_db(tmp_path, [talk])

    result = _claim(path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["normalizations"] == [{
        "filename": "label-only.md",
        "previous_status": "skipped_no_video",
        "status": "skipped_no_sources",
        "video_present": False,
        "source_capabilities": [],
    }]
    assert payload["claimed"] == []


def test_legacy_true_no_source_talk_is_the_only_one_skipped(tmp_path):
    no_source = _talk(
        "abcdefghijk", status="skipped_no_transcript", video=False,
        filename="no-source.md",
    )
    slides_only = _talk(
        "lmnopqrstuv", status="skipped_no_transcript", video=False,
        filename="slides-only.md",
    )
    slides_only["google_drive_id"] = "drive-artifact"
    path = _write_db(tmp_path, [no_source, slides_only])

    result = _claim(path, limit=10)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [item["filename"] for item in payload["claimed"]] == ["slides-only.md"]
    records = {talk["filename"]: talk for talk in _read_db(path)["talks"]}
    assert records["no-source.md"]["status"] == "skipped_no_sources"
    assert records["slides-only.md"]["status"] == "reprocessing-inflight"


def test_video_bearing_download_failure_is_retryable(tmp_path):
    path = _write_db(
        tmp_path,
        [_talk("iPYc7LCH608", status="skipped_download_failed")],
    )

    result = _claim(path)

    assert result.returncode == 0, result.stderr
    claim = json.loads(result.stdout)["claimed"][0]
    assert claim["previous_status"] == "skipped_download_failed"


def test_claim_is_idempotent_for_an_existing_run_and_batch(tmp_path):
    path = _write_db(tmp_path, [_talk("eg6gqvUFh6Q")])
    first = _claim(path)
    first_bytes = path.read_bytes()

    second = _claim(path)

    assert first.returncode == second.returncode == 0
    payload = json.loads(second.stdout)
    assert payload["idempotent_replay"] is True
    assert payload["claimed"][0]["reprocess_generation"] == 1
    assert path.read_bytes() == first_bytes


def test_new_claim_is_v3_with_one_immutable_batch_baseline(tmp_path):
    talks = [_talk("eg6gqvUFh6Q"), _talk("iPYc7LCH608")]
    path = _write_db(tmp_path, talks)

    result = _claim(path, limit=2)

    assert result.returncode == 0, result.stderr
    claims = json.loads(result.stdout)["claimed"]
    assert {claim["schema_version"] for claim in claims} == {3}
    assert {claim["required_return_schema_version"] for claim in claims} == {3}
    assert claims[0]["adherence_baseline"] == claims[1]["adherence_baseline"]
    baseline = claims[0]["adherence_baseline"]
    assert baseline["as_of"] == NOW
    assert baseline["excluded_filenames"] == sorted(
        talk["filename"] for talk in talks)


def test_claim_baseline_failure_is_copy_on_write(tmp_path):
    malformed = _talk("eg6gqvUFh6Q", status="processed")
    malformed.update({
        "pattern_scoring_generation_status": "current",
        "pattern_scoring_generation_reasons": [],
        "pattern_score": 1,
        "pattern_observations": {"pattern_score": 1},
    })
    path = _write_db(tmp_path, [malformed, _talk("iPYc7LCH608")])
    before = path.read_bytes()

    result = _claim(
        path,
        filenames=("playlist-iPYc7LCH608.md",),
    )

    assert result.returncode == 2
    assert "missing required identity fields" in result.stderr
    assert path.read_bytes() == before


def test_same_run_and_batch_reclaims_a_stale_recovered_generation(tmp_path):
    path = _write_db(
        tmp_path,
        [_talk("eg6gqvUFh6Q", status="needs-reprocessing")],
    )
    first = _run(
        path,
        "claim",
        "--run-id", "reparse",
        "--batch-id", "25",
        "--now", "2026-07-31T17:00:00+00:00",
    )
    assert first.returncode == 0, first.stderr
    first_claim = json.loads(first.stdout)["claimed"][0]
    recovered = _run(
        path,
        "recover",
        "--now", "2026-07-31T18:00:00+00:00",
        "--stale-after-seconds", "3600",
    )
    assert recovered.returncode == 0, recovered.stderr

    retried = _run(
        path,
        "claim",
        "--run-id", "reparse",
        "--batch-id", "25",
        "--now", "2026-07-31T18:01:00+00:00",
    )

    assert retried.returncode == 0, retried.stderr
    payload = json.loads(retried.stdout)
    assert payload["idempotent_replay"] is False
    assert payload["claimed"][0]["reprocess_generation"] == 2
    assert payload["claimed"][0]["state"] == "claimed"
    talk = _read_db(path)["talks"][0]
    assert talk["status"] == "reprocessing-inflight"
    assert talk["reprocess_generation"] == 2
    assert talk["_queue_claim"]["reprocess_generation"] == 2
    archived = talk["_queue_claim_history"][0]
    assert archived["schema_version"] == 3
    assert archived["adherence_baseline"] == first_claim["adherence_baseline"]
    assert archived["state"] == "stale_recovered"
    assert archived["released_at"] == "2026-07-31T18:00:00+00:00"
    assert archived["release_reason"] == "lease_expired"
    assert talk["_queue_claim"]["adherence_baseline"]["as_of"] == \
        "2026-07-31T18:01:00+00:00"
    assert (talk["_queue_claim"]["adherence_baseline"] !=
            archived["adherence_baseline"])

    retried_bytes = path.read_bytes()
    replay = _run(
        path,
        "claim",
        "--run-id", "reparse",
        "--batch-id", "25",
        "--now", "2026-07-31T18:02:00+00:00",
    )
    assert replay.returncode == 0, replay.stderr
    replay_payload = json.loads(replay.stdout)
    assert replay_payload["idempotent_replay"] is True
    assert len(replay_payload["claimed"]) == 1
    assert replay_payload["claimed"][0]["reprocess_generation"] == 2
    assert path.read_bytes() == retried_bytes


def test_v3_batch_epoch_can_span_current_and_history_after_member_reclaim(
        tmp_path):
    path = _write_db(
        tmp_path,
        [_talk("eg6gqvUFh6Q"), _talk("iPYc7LCH608")],
    )
    claimed = _claim(path, run_id="old-run", batch_id="old-batch", limit=2)
    assert claimed.returncode == 0, claimed.stderr
    database = _read_db(path)
    for talk in database["talks"]:
        talk["status"] = "processed"
        talk["_queue_claim"].update({
            "state": "completed",
            "released_at": "2026-07-31T18:05:00+00:00",
            "release_reason": "return_persisted",
            "result_status": "processed",
            "result_payload_sha256": "0" * 64,
        })

    reclaimed = database["talks"][0]
    old_claim = copy.deepcopy(reclaimed["_queue_claim"])
    reclaimed["_queue_claim_history"] = [old_claim]
    new_claim = copy.deepcopy(old_claim)
    for field in (
            "released_at", "release_reason", "result_status",
            "result_payload_sha256"):
        new_claim.pop(field)
    new_claim.update({
        "run_id": "new-run",
        "batch_id": "new-batch",
        "claimed_at": "2026-07-31T19:00:00+00:00",
        "reprocess_generation": 2,
        "state": "claimed",
    })
    new_claim["adherence_baseline"]["as_of"] = new_claim["claimed_at"]
    new_claim["adherence_baseline"]["excluded_filenames"] = [
        reclaimed["filename"]]
    reclaimed["_queue_claim"] = new_claim
    reclaimed["reprocess_generation"] = 2
    reclaimed["status"] = "reprocessing-inflight"

    path.write_text(json.dumps(database))
    result = _run(path, "inspect", "--run-id", "new-run")

    assert result.returncode == 0, result.stderr


def test_v3_current_batch_cannot_split_claimed_at(tmp_path):
    path = _write_db(
        tmp_path,
        [_talk("eg6gqvUFh6Q"), _talk("iPYc7LCH608")],
    )
    claimed = _claim(path, run_id="run", batch_id="batch", limit=2)
    assert claimed.returncode == 0, claimed.stderr
    database = _read_db(path)
    second_claim = database["talks"][1]["_queue_claim"]
    second_claim["claimed_at"] = "2026-07-31T18:00:01+00:00"
    second_claim["adherence_baseline"]["as_of"] = second_claim["claimed_at"]

    path.write_text(json.dumps(database))
    before = path.read_bytes()

    result = _run(path, "inspect", "--run-id", "run")

    assert result.returncode == 2
    assert "do not share one claimed_at" in result.stderr
    assert path.read_bytes() == before


def test_claim_is_idempotent_for_a_completed_same_run_and_batch(tmp_path):
    talk = _talk("eg6gqvUFh6Q", status="processed")
    talk["reprocess_generation"] = 1
    talk["_queue_claim"] = {
        "schema_version": 2,
        "run_id": "reparse",
        "batch_id": "25",
        "claimed_at": "2026-07-31T17:00:00+00:00",
        "previous_status": "needs-reprocessing",
        "reprocess_generation": 1,
        "state": "completed",
        "released_at": "2026-07-31T17:30:00+00:00",
        "release_reason": "return_persisted",
        "result_status": "processed",
        "result_payload_sha256": "0" * 64,
    }
    path = _write_db(tmp_path, [talk])
    before = path.read_bytes()

    replay = _claim(
        path,
        run_id="reparse",
        batch_id="25",
        filenames=(talk["filename"],),
    )

    assert replay.returncode == 0, replay.stderr
    payload = json.loads(replay.stdout)
    assert payload["idempotent_replay"] is True
    assert payload["claimed"][0]["state"] == "completed"
    assert payload["claimed"][0]["result_status"] == "processed"
    assert path.read_bytes() == before


def test_completed_v1_replay_keeps_stdout_and_disk_at_v1(tmp_path):
    talk = _talk("eg6gqvUFh6Q", status="processed")
    talk["reprocess_generation"] = 1
    talk["_queue_claim"] = {
        "schema_version": 1,
        "run_id": "legacy-run",
        "batch_id": "legacy-batch",
        "claimed_at": "2026-07-31T17:00:00+00:00",
        "previous_status": "needs-reprocessing",
        "reprocess_generation": 1,
        "state": "completed",
        "released_at": "2026-07-31T17:30:00+00:00",
        "release_reason": "return_persisted",
        "result_status": "processed",
    }
    path = _write_db(tmp_path, [talk])
    before = path.read_bytes()

    result = _claim(
        path,
        run_id="legacy-run",
        batch_id="legacy-batch",
        filenames=(talk["filename"],),
    )

    assert result.returncode == 0, result.stderr
    claim = json.loads(result.stdout)["claimed"][0]
    assert claim["schema_version"] == 1
    assert "result_payload_sha256" not in claim
    assert path.read_bytes() == before


def test_recover_uses_injected_time_and_exact_stale_threshold(tmp_path):
    path = _write_db(
        tmp_path,
        [_talk("eg6gqvUFh6Q", status="needs-reprocessing")],
    )
    claimed = _run(
        path,
        "claim",
        "--run-id", "reparse",
        "--batch-id", "25",
        "--now", "2026-07-31T17:00:00+00:00",
    )
    assert claimed.returncode == 0, claimed.stderr

    fresh = _run(
        path,
        "recover",
        "--now", "2026-07-31T17:59:59+00:00",
        "--stale-after-seconds", "3600",
    )
    assert fresh.returncode == 0
    assert json.loads(fresh.stdout)["recovered"] == []

    stale = _run(
        path,
        "recover",
        "--now", "2026-07-31T18:00:00+00:00",
        "--stale-after-seconds", "3600",
    )
    assert stale.returncode == 0, stale.stderr
    assert json.loads(stale.stdout)["recovered"] == [{
        "filename": "playlist-eg6gqvUFh6Q.md",
        "run_id": "reparse",
        "batch_id": "25",
        "reprocess_generation": 1,
        "status": "needs-reprocessing",
        "age_seconds": 3600,
    }]
    talk = _read_db(path)["talks"][0]
    assert talk["status"] == "needs-reprocessing"
    assert talk["_queue_claim"]["state"] == "stale_recovered"
    assert talk["reprocess_generation"] == 1


def test_inspect_reconstructs_claims_after_stale_recovery(tmp_path):
    path = _write_db(tmp_path, [_talk("eg6gqvUFh6Q")])
    assert _claim(path, run_id="reparse", batch_id="25").returncode == 0
    assert _run(
        path,
        "recover",
        "--now", "2026-07-31T19:00:00+00:00",
        "--stale-after-seconds", "1",
    ).returncode == 0

    result = _run(path, "inspect", "--run-id", "reparse")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["batches"] == [{
        "batch_id": "25",
        "filenames": ["playlist-eg6gqvUFh6Q.md"],
    }]
    assert payload["claims"][0]["state"] == "stale_recovered"


def test_inspect_accepts_a_completed_persistence_claim(tmp_path):
    talk = _talk("eg6gqvUFh6Q", status="processed")
    talk["reprocess_generation"] = 1
    talk["_queue_claim"] = {
        "schema_version": 2,
        "run_id": "reparse",
        "batch_id": "25",
        "claimed_at": "2026-07-31T17:00:00+00:00",
        "previous_status": "needs-reprocessing",
        "reprocess_generation": 1,
        "state": "completed",
        "released_at": "2026-07-31T17:30:00+00:00",
        "release_reason": "return_persisted",
        "result_status": "processed",
        "result_payload_sha256": "0" * 64,
    }
    path = _write_db(tmp_path, [talk])

    result = _run(path, "inspect", "--run-id", "reparse")

    assert result.returncode == 0, result.stderr
    claim = json.loads(result.stdout)["claims"][0]
    assert claim["state"] == "completed"
    assert claim["result_status"] == "processed"


def test_inspect_dual_reads_legacy_completed_claim_without_mutating(tmp_path):
    talk = _talk("eg6gqvUFh6Q", status="processed")
    talk["reprocess_generation"] = 1
    talk["_queue_claim"] = {
        "schema_version": 1,
        "run_id": "legacy-run",
        "batch_id": "legacy-batch",
        "claimed_at": "2026-07-31T17:00:00+00:00",
        "previous_status": "needs-reprocessing",
        "reprocess_generation": 1,
        "state": "completed",
        "released_at": "2026-07-31T17:30:00+00:00",
        "release_reason": "return_persisted",
        "result_status": "processed",
    }
    path = _write_db(tmp_path, [talk])
    before = path.read_bytes()

    result = _run(path, "inspect", "--run-id", "legacy-run")

    assert result.returncode == 0, result.stderr
    claim = json.loads(result.stdout)["claims"][0]
    assert claim["schema_version"] == 1
    assert "result_payload_sha256" not in claim
    assert path.read_bytes() == before


def test_unknown_future_claim_schema_fails_without_rewriting(tmp_path):
    talk = _talk("eg6gqvUFh6Q", status="reprocessing-inflight")
    talk["reprocess_generation"] = 1
    talk["_queue_claim"] = {
        "schema_version": 99,
        "run_id": "future-run",
        "batch_id": "future-batch",
        "claimed_at": NOW,
        "previous_status": "pending",
        "reprocess_generation": 1,
        "state": "claimed",
    }
    path = _write_db(tmp_path, [talk])
    before = path.read_bytes()

    result = _run(path, "inspect", "--run-id", "future-run")

    assert result.returncode == 2
    assert "newer than supported" in json.loads(result.stdout)["error"]
    assert path.read_bytes() == before


def test_active_claim_with_terminal_status_rejects_every_command_but_recover(
        tmp_path):
    talk = _talk("eg6gqvUFh6Q", status="processed")
    talk["reprocess_generation"] = 1
    talk["_queue_claim"] = {
        "schema_version": 1,
        "run_id": "reparse",
        "batch_id": "25",
        "claimed_at": NOW,
        "previous_status": "needs-reprocessing",
        "reprocess_generation": 1,
        "state": "claimed",
    }
    path = _write_db(tmp_path, [talk])
    before = path.read_bytes()

    rejected = _run(path, "inspect", "--run-id", "reparse")

    assert rejected.returncode == 2
    assert "stranded lease" in json.loads(rejected.stdout)["error"]
    assert path.read_bytes() == before

    recovered = _run(
        path,
        "recover",
        "--now", NOW,
        "--stale-after-seconds", "999",
    )

    assert recovered.returncode == 0, recovered.stderr
    assert json.loads(recovered.stdout)["recovered"] == [{
        "filename": "playlist-eg6gqvUFh6Q.md",
        "run_id": "reparse",
        "batch_id": "25",
        "reprocess_generation": 1,
        "status": "needs-reprocessing",
        "age_seconds": 0,
        "status_before": "processed",
        "release_reason": "state_status_drift",
    }]
    repaired = _read_db(path)["talks"][0]
    assert repaired["status"] == "needs-reprocessing"
    assert repaired["_queue_claim"]["state"] == "stale_recovered"
    assert repaired["_queue_claim"]["release_reason"] == "state_status_drift"


def test_duplicate_filenames_reject_without_rewriting(tmp_path):
    talk = _talk("eg6gqvUFh6Q")
    path = _write_db(tmp_path, [talk, dict(talk)])
    before = path.read_bytes()

    result = _run(path, "normalize")

    assert result.returncode == 2
    assert "duplicate talk filename" in json.loads(result.stdout)["error"]
    assert path.read_bytes() == before


def test_tracking_database_symlink_is_rejected_before_read_or_write(tmp_path):
    target = _write_db(tmp_path, [_talk("eg6gqvUFh6Q")])
    before = target.read_bytes()
    link = tmp_path / "tracking-link.json"
    link.symlink_to(target.name)

    result = _claim(link)

    assert result.returncode == 2
    assert "symbolic link" in json.loads(result.stdout)["error"]
    assert link.is_symlink()
    assert target.read_bytes() == before


@pytest.mark.parametrize(
    "talk,error",
    [
        (
            _talk(
                "eg6gqvUFh6Q",
                filename="playlist-iPYc7LCH608.md",
            ),
            "filename id",
        ),
        (
            {
                **_talk("eg6gqvUFh6Q", filename="talk.md"),
                "video_url": "https://youtu.be/iPYc7LCH608",
            },
            "disagrees with video_url id",
        ),
    ],
)
def test_locally_decidable_video_identity_mismatches_reject(tmp_path, talk, error):
    path = _write_db(tmp_path, [talk])

    result = _run(path, "normalize")

    assert result.returncode == 2
    assert error in json.loads(result.stdout)["error"]


def test_malformed_claim_timestamp_rejects(tmp_path):
    talk = _talk("eg6gqvUFh6Q", status="reprocessing-inflight")
    talk["reprocess_generation"] = 1
    talk["_queue_claim"] = {
        "schema_version": 1,
        "run_id": "reparse",
        "batch_id": "25",
        "claimed_at": "yesterday",
        "previous_status": "pending",
        "reprocess_generation": 1,
        "state": "claimed",
    }
    path = _write_db(tmp_path, [talk])

    result = _run(path, "inspect", "--run-id", "reparse")

    assert result.returncode == 2
    assert "claim.claimed_at" in json.loads(result.stdout)["error"]


@pytest.mark.parametrize(
    "talk",
    [
        _talk("eg6gqvUFh6Q", status="skipped_duplicate"),
        _talk("iPYc7LCH608", status="pending", video=False),
    ],
)
def test_explicit_claim_rejects_invalid_transitions(tmp_path, talk):
    path = _write_db(tmp_path, [talk])
    before = path.read_bytes()

    result = _claim(path, filenames=(talk["filename"],))

    assert result.returncode == 2
    assert "cannot claim" in json.loads(result.stdout)["error"]
    assert path.read_bytes() == before


def test_cli_requires_timezone_aware_now(tmp_path):
    path = _write_db(tmp_path, [_talk("eg6gqvUFh6Q")])

    result = _run(
        path,
        "claim",
        "--run-id", "reparse",
        "--batch-id", "25",
        "--now", "2026-07-31T18:00:00",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "has no timezone" in payload["error"]
