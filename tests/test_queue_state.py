"""Queue-state contract tests for vault-ingress.

All timestamps are injected and every fixture is local. The CLI never reaches a
network or reads subagent returns.
"""

import importlib.util
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


@pytest.fixture(scope="session")
def queue_state():
    spec = importlib.util.spec_from_file_location("queue_state", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["queue_state"] = module
    spec.loader.exec_module(module)
    return module


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
    }]
    assert payload["claimed"][0]["previous_status"] == "pending"


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


def test_duplicate_filenames_reject_without_rewriting(tmp_path):
    talk = _talk("eg6gqvUFh6Q")
    path = _write_db(tmp_path, [talk, dict(talk)])
    before = path.read_bytes()

    result = _run(path, "normalize")

    assert result.returncode == 2
    assert "duplicate talk filename" in json.loads(result.stdout)["error"]
    assert path.read_bytes() == before


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
