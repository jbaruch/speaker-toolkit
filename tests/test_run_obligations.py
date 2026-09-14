"""run-obligations.py: the human-facing obligations of an ingress run persist.

Every scenario pins its clock through ``--now``; nothing reads the wall clock.
Fixtures are built in ``tmp_path`` from the smallest talk record the owner's
strict reader accepts.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from conftest import CURRENT_ROOT_SCHEMA_VERSION, SCRIPTS_VI, current_tracking_config

SCRIPT = os.path.join(SCRIPTS_VI, "run-obligations.py")
TALK_SCHEMA_VERSION = 8
NOW = "2026-09-14T12:00:00+00:00"
LATER = "2026-09-14T12:30:00+00:00"
MUCH_LATER = "2026-09-30T09:00:00+00:00"


def _talk(filename: str, *, status: str = "processed", date: str | None = "2026-09-10"):
    talk: dict[str, object] = {
        "filename": filename,
        "schema_version": TALK_SCHEMA_VERSION,
        "status": status,
    }
    if date is not None:
        talk["date"] = date
    return talk


def _write_db(tmp_path: Path, talks: list[dict[str, object]], *, root_version=None):
    database = {
        "schema_version": CURRENT_ROOT_SCHEMA_VERSION
        if root_version is None
        else root_version,
        "config": current_tracking_config(),
        "talks": talks,
        "pptx_catalog": [],
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }
    path = tmp_path / "tracking-database.json"
    path.write_text(json.dumps(database), encoding="utf-8")
    return path


def _run(database: Path, *arguments: str):
    completed = subprocess.run(
        [sys.executable, SCRIPT, str(database), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout) if completed.stdout.strip() else None
    return completed.returncode, payload, completed.stderr


def _ok(database: Path, *arguments: str):
    code, payload, stderr = _run(database, *arguments)
    assert code == 0, stderr
    assert payload is not None and payload["ok"] is True
    return payload


def _refused(database: Path, *arguments: str):
    code, payload, stderr = _run(database, *arguments)
    assert code == 2
    assert payload is not None and payload["ok"] is False
    assert payload["error"] in stderr
    return payload


def _ledger(tmp_path: Path):
    return json.loads((tmp_path / "ingress-obligations.json").read_text("utf-8"))


@pytest.fixture
def fresh_db(tmp_path: Path):
    return _write_db(
        tmp_path,
        [
            _talk("fresh.md", date="2026-09-10"),
            _talk("older.md", status="processed_partial", date="2026-01-01"),
            _talk("skipped.md", status="skipped_no_sources", date="2026-09-12"),
            _talk("undated.md", date=None),
        ],
    )


# ── open ──────────────────────────────────────────────────────────────


def test_open_records_recency_from_the_database_and_owes_an_inline_offer(
    tmp_path, fresh_db
):
    payload = _ok(
        fresh_db,
        "open",
        "--run-id",
        "run-a",
        "--now",
        NOW,
        "--talk",
        "fresh.md",
        "--talk",
        "older.md",
        "--talk",
        "skipped.md",
    )
    run = payload["run"]
    assert payload["written"] is True
    assert payload["ledger_path"] == str(tmp_path / "ingress-obligations.json")
    assert [
        (t["filename"], t["status"], t["recency_bucket"]) for t in run["talks"]
    ] == [
        ("fresh.md", "processed", "same_week"),
        ("older.md", "processed_partial", "older"),
        ("skipped.md", "skipped_no_sources", "same_week"),
    ]
    assert run["talks"][0]["days_since_delivery"] == 4
    assert run["clarification"]["state"] == "owed"
    assert run["clarification"]["offer_mode"] == "inline"
    assert run["end_report"]["state"] == "owed"
    assert run["completed_at"] is None
    assert _ledger(tmp_path)["schema_version"] == 1
    pending = _ok(fresh_db, "pending")
    assert pending["count"] == 1
    assert pending["pending"][0]["next_action"] == "offer_clarification"


@pytest.mark.parametrize(
    ("talks", "mode", "state"),
    [
        (["older.md"], "recommend_compressed", "owed"),
        (["undated.md"], "recommend_full", "owed"),
        (["undated.md", "older.md"], "recommend_full", "owed"),
        (["skipped.md"], "none", "not_applicable"),
    ],
    ids=["older", "undated", "undated-beats-older", "nothing-analyzed"],
)
def test_open_picks_the_strongest_offer_among_analyzed_talks(
    fresh_db, talks, mode, state
):
    arguments = ["open", "--run-id", "run-b", "--now", NOW]
    for talk in talks:
        arguments += ["--talk", talk]
    run = _ok(fresh_db, *arguments)["run"]
    assert run["clarification"]["offer_mode"] == mode
    assert run["clarification"]["state"] == state


def test_a_run_with_nothing_to_clarify_still_owes_its_report(fresh_db):
    _ok(fresh_db, "open", "--run-id", "run-c", "--now", NOW, "--talk", "skipped.md")
    pending = _ok(fresh_db, "pending")
    assert pending["pending"][0]["next_action"] == "deliver_end_report"


def test_open_replays_without_rewriting(tmp_path, fresh_db):
    first = _ok(
        fresh_db, "open", "--run-id", "run-d", "--now", NOW, "--talk", "fresh.md"
    )
    raw_before = (tmp_path / "ingress-obligations.json").read_bytes()
    second = _ok(
        fresh_db, "open", "--run-id", "run-d", "--now", LATER, "--talk", "fresh.md"
    )
    assert second["written"] is False
    assert second["run"]["updated_at"] == first["run"]["updated_at"] == NOW
    assert (tmp_path / "ingress-obligations.json").read_bytes() == raw_before


def test_a_later_batch_joins_the_run_and_strengthens_the_offer(fresh_db):
    _ok(fresh_db, "open", "--run-id", "run-e", "--now", NOW, "--talk", "older.md")
    run = _ok(
        fresh_db, "open", "--run-id", "run-e", "--now", LATER, "--talk", "fresh.md"
    )["run"]
    assert [t["filename"] for t in run["talks"]] == ["fresh.md", "older.md"]
    assert run["clarification"]["offer_mode"] == "inline"
    assert run["updated_at"] == LATER


def test_recency_moves_with_the_clock_until_the_offer_is_made(fresh_db):
    _ok(fresh_db, "open", "--run-id", "run-f", "--now", NOW, "--talk", "fresh.md")
    resumed = _ok(
        fresh_db, "open", "--run-id", "run-f", "--now", MUCH_LATER, "--talk", "fresh.md"
    )["run"]
    assert resumed["talks"][0]["recency_bucket"] == "recent"
    assert resumed["clarification"]["offer_mode"] == "recommend_full"


def test_recency_freezes_once_the_offer_is_recorded(fresh_db):
    _ok(fresh_db, "open", "--run-id", "run-g", "--now", NOW, "--talk", "fresh.md")
    _ok(fresh_db, "record-offer", "--run-id", "run-g", "--now", NOW)
    run = _ok(
        fresh_db, "open", "--run-id", "run-g", "--now", MUCH_LATER, "--talk", "older.md"
    )["run"]
    assert run["clarification"]["state"] == "offered"
    assert run["clarification"]["offer_mode"] == "inline"
    assert [t["filename"] for t in run["talks"]] == ["fresh.md", "older.md"]
    assert run["talks"][0]["recency_bucket"] == "same_week"


def test_open_refuses_a_talk_the_database_does_not_hold(fresh_db):
    payload = _refused(
        fresh_db, "open", "--run-id", "run-h", "--now", NOW, "--talk", "ghost.md"
    )
    assert payload["reason_code"] == "talk_not_found"
    assert "persist-results.py" in payload["error"]


# ── offer and disposition ─────────────────────────────────────────────


def _opened(database: Path, run_id: str = "run-x"):
    _ok(database, "open", "--run-id", run_id, "--now", NOW, "--talk", "fresh.md")
    return run_id


def test_an_offer_is_recorded_once_with_its_topics(fresh_db):
    run_id = _opened(fresh_db)
    run = _ok(
        fresh_db,
        "record-offer",
        "--run-id",
        run_id,
        "--now",
        NOW,
        "--topic",
        "bilingual joke at 12:40",
        "--topic",
        "  ",
        "--topic",
        "improvised aside",
    )["run"]
    assert run["clarification"]["state"] == "offered"
    assert run["clarification"]["offered_at"] == NOW
    assert run["clarification"]["topics"] == [
        "bilingual joke at 12:40",
        "improvised aside",
    ]
    again = _refused(fresh_db, "record-offer", "--run-id", run_id, "--now", LATER)
    assert again["reason_code"] == "invalid_transition"


def test_silence_leaves_the_offer_pending_across_a_fresh_read(fresh_db):
    run_id = _opened(fresh_db)
    _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW)
    pending = _ok(fresh_db, "pending")
    assert pending["pending"][0]["next_action"] == "await_disposition"
    assert pending["pending"][0]["clarification_state"] == "offered"


def test_a_disposition_needs_a_recorded_offer(fresh_db):
    run_id = _opened(fresh_db)
    payload = _refused(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        NOW,
        "--disposition",
        "declined",
    )
    assert payload["reason_code"] == "invalid_transition"


@pytest.mark.parametrize(
    ("disposition", "extra", "next_action", "session"),
    [
        ("declined", [], "deliver_end_report", None),
        (
            "deferred",
            ["--return-condition", "after the next delivery"],
            "deliver_end_report",
            None,
        ),
        (
            "accepted",
            [],
            "complete_clarification_session",
            {"state": "pending", "completed_at": None, "profile_refreshed": None},
        ),
    ],
)
def test_each_disposition_is_explicit_and_answered_once(
    fresh_db, disposition, extra, next_action, session
):
    run_id = _opened(fresh_db)
    _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW)
    run = _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--disposition",
        disposition,
        *extra,
    )["run"]
    assert run["clarification"]["state"] == disposition
    assert run["clarification"]["resolved_at"] == LATER
    assert run["clarification"]["session"] == session
    if disposition == "deferred":
        assert run["clarification"]["return_condition"] == "after the next delivery"
    else:
        assert run["clarification"]["return_condition"] is None
    assert _ok(fresh_db, "pending")["pending"][0]["next_action"] == next_action
    repeat = _refused(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--disposition",
        "declined",
    )
    assert repeat["reason_code"] == "invalid_transition"


def test_a_deferral_names_when_it_returns(fresh_db):
    run_id = _opened(fresh_db)
    _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW)
    payload = _refused(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--disposition",
        "deferred",
    )
    assert payload["reason_code"] == "invalid_arguments"
    assert "--return-condition" in payload["error"]


def test_the_session_completes_once_and_only_after_acceptance(fresh_db):
    run_id = _opened(fresh_db)
    early = _refused(fresh_db, "record-session", "--run-id", run_id, "--now", NOW)
    assert early["reason_code"] == "invalid_transition"
    _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW)
    _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        NOW,
        "--disposition",
        "accepted",
    )
    run = _ok(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--profile-refreshed",
    )["run"]
    assert run["clarification"]["session"] == {
        "state": "completed",
        "completed_at": LATER,
        "profile_refreshed": True,
    }
    assert _ok(fresh_db, "pending")["pending"][0]["next_action"] == "deliver_end_report"
    twice = _refused(
        fresh_db, "record-session", "--run-id", run_id, "--now", MUCH_LATER
    )
    assert twice["reason_code"] == "invalid_transition"


# ── end report ────────────────────────────────────────────────────────


def _report(tmp_path: Path, text: str = "# Ingress report\n\nTwo talks processed.\n"):
    path = tmp_path / "delivered.md"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("stage", ["owed", "offered", "accepted"])
def test_the_report_waits_for_the_clarification_disposition(tmp_path, fresh_db, stage):
    run_id = _opened(fresh_db)
    if stage in {"offered", "accepted"}:
        _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW)
    if stage == "accepted":
        _ok(
            fresh_db,
            "record-disposition",
            "--run-id",
            run_id,
            "--now",
            NOW,
            "--disposition",
            "accepted",
        )
    payload = _refused(
        fresh_db,
        "record-report",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--report-file",
        str(_report(tmp_path)),
    )
    assert payload["reason_code"] == "invalid_transition"
    assert not (tmp_path / "ingress-reports").exists()


def test_a_delivered_report_is_copied_bound_and_completes_the_run(tmp_path, fresh_db):
    run_id = _opened(fresh_db)
    _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW)
    _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        NOW,
        "--disposition",
        "declined",
    )
    report = _report(tmp_path)
    payload = _ok(
        fresh_db,
        "record-report",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--report-file",
        str(report),
    )
    run = payload["run"]
    copied = tmp_path / "ingress-reports" / f"{run_id}.md"
    assert copied.read_bytes() == report.read_bytes()
    assert run["end_report"] == {
        "state": "delivered",
        "delivered_at": LATER,
        "report_path": str(copied),
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    }
    assert run["completed_at"] == LATER
    assert _ok(fresh_db, "pending") == {
        "ok": True,
        "ledger_path": str(tmp_path / "ingress-obligations.json"),
        "ledger_present": True,
        "pending": [],
        "count": 0,
    }
    status = _ok(fresh_db, "status", "--run-id", run_id)
    assert status["summary"]["next_action"] == "none"
    replay = _ok(
        fresh_db,
        "record-report",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--report-file",
        str(report),
    )
    assert replay["written"] is False
    assert replay["run"]["completed_at"] == LATER
    reopened = _refused(
        fresh_db, "open", "--run-id", run_id, "--now", MUCH_LATER, "--talk", "older.md"
    )
    assert reopened["reason_code"] == "invalid_transition"


def test_a_placeholder_is_not_a_delivered_report(tmp_path, fresh_db):
    run_id = _opened(fresh_db)
    _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW)
    _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        NOW,
        "--disposition",
        "declined",
    )
    empty = _refused(
        fresh_db,
        "record-report",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--report-file",
        str(_report(tmp_path, "  \n")),
    )
    assert empty["reason_code"] == "report_empty"
    missing = _refused(
        fresh_db,
        "record-report",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--report-file",
        str(tmp_path / "absent.md"),
    )
    assert missing["reason_code"] == "report_unreadable"
    assert _ok(fresh_db, "status", "--run-id", run_id)["run"]["end_report"][
        "state"
    ] == ("owed")


# ── inputs, ledger, and database gates ────────────────────────────────


def test_pending_is_empty_before_any_run_opened(tmp_path, fresh_db):
    payload = _ok(fresh_db, "pending")
    assert payload["ledger_present"] is False
    assert payload["pending"] == []
    assert not (tmp_path / "ingress-obligations.json").exists()


def test_status_names_an_unknown_run(fresh_db):
    payload = _refused(fresh_db, "status", "--run-id", "never-opened")
    assert payload["reason_code"] == "run_not_found"
    assert "open" in payload["error"]


@pytest.mark.parametrize(
    ("arguments", "reason_code"),
    [
        (
            ["open", "--run-id", "run-z", "--now", "2026-09-14", "--talk", "fresh.md"],
            "invalid_timestamp",
        ),
        (
            [
                "open",
                "--run-id",
                "run-z",
                "--now",
                "2026-09-14T12:00:00",
                "--talk",
                "fresh.md",
            ],
            "invalid_timestamp",
        ),
        (["open", "--run-id", "run-z", "--now", NOW], "invalid_arguments"),
        (
            ["open", "--run-id", "../escape", "--now", NOW, "--talk", "fresh.md"],
            "invalid_arguments",
        ),
        (["record-offer", "--run-id", "run-z"], "invalid_arguments"),
        ([], "invalid_arguments"),
    ],
    ids=["date-only", "naive", "no-talk", "bad-run-id", "missing-now", "no-action"],
)
def test_bad_arguments_fail_closed_with_json(fresh_db, arguments, reason_code):
    payload = _refused(fresh_db, *arguments)
    assert payload["reason_code"] == reason_code


def test_a_legacy_database_is_refused_before_the_ledger_is_touched(tmp_path):
    database = _write_db(tmp_path, [_talk("fresh.md")], root_version=3)
    payload = _refused(database, "pending")
    assert payload["reason_code"] == "database_unusable"
    assert not (tmp_path / "ingress-obligations.json").exists()


def test_a_ledger_from_another_generation_is_not_read(tmp_path, fresh_db):
    (tmp_path / "ingress-obligations.json").write_text(
        json.dumps({"schema_version": 2, "runs": []}), encoding="utf-8"
    )
    payload = _refused(fresh_db, "pending")
    assert payload["reason_code"] == "ledger_schema_unsupported"


def test_a_malformed_ledger_is_named_not_repaired(tmp_path, fresh_db):
    (tmp_path / "ingress-obligations.json").write_text(
        json.dumps({"schema_version": 1, "runs": [{"run_id": "r"}]}), encoding="utf-8"
    )
    payload = _refused(fresh_db, "pending")
    assert payload["reason_code"] == "ledger_invalid"
    assert "lacks talks" in payload["error"]


# ── module surface ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("days", "bucket"),
    [
        (0, "same_week"),
        (7, "same_week"),
        (8, "recent"),
        (30, "recent"),
        (31, "older"),
        (None, "unknown"),
        (-1, "unknown"),
    ],
)
def test_recency_buckets_are_inclusive_at_their_edges(run_obligations, days, bucket):
    assert run_obligations.recency_bucket(days) == bucket


def test_the_strongest_bucket_decides_the_offer(run_obligations):
    def talk(bucket, status="processed"):
        return {"filename": f"{bucket}.md", "status": status, "recency_bucket": bucket}

    assert run_obligations.offer_mode_for([]) == "none"
    assert (
        run_obligations.offer_mode_for([talk("older"), talk("same_week")]) == "inline"
    )
    assert run_obligations.offer_mode_for([talk("older"), talk("unknown")]) == (
        "recommend_full"
    )
    assert run_obligations.offer_mode_for([talk("older")]) == "recommend_compressed"
    assert (
        run_obligations.offer_mode_for(
            [talk("same_week", status="skipped_download_failed")]
        )
        == "none"
    )


def test_the_entry_point_is_guarded(run_obligations):
    assert callable(run_obligations.main)
    assert run_obligations.LEDGER_SCHEMA_VERSION == 1
