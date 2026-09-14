"""run-obligations.py: the human-facing obligations of an ingress run persist.

Every scenario pins its clock through ``--now``; nothing reads the wall clock.
Fixtures are built in ``tmp_path`` from the smallest talk record the owner's
strict reader accepts, each carrying the closed claim that persisted it.
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
SEED_RUN = "seed-run"
SEED_RELEASED = "2026-09-01T00:00:00+00:00"
# The fixtures adopt the ledger after the seed claims closed, so seed facts are
# history and never reconciled; claims in recovery tests close after this.
ADOPTED = "2026-09-02T00:00:00+00:00"
ENVELOPE = {
    "schema_version": 1,
    "adopted_at": ADOPTED,
    "adopted_facts": [],
    "dismissed_runs": [],
}


def _identity(run_id, filename, released_at, *, batch_id="b1", generation=1):
    return [run_id, filename, batch_id, generation, released_at]


def _persisted_claim(
    run_id: str, released_at: str, *, result_status="processed", batch_id="b1"
):
    return {
        "schema_version": 2,
        "run_id": run_id,
        "batch_id": batch_id,
        "claimed_at": "2026-08-31T00:00:00+00:00",
        "previous_status": "pending",
        "reprocess_generation": 1,
        "state": "completed",
        "released_at": released_at,
        "release_reason": "return_persisted",
        "result_status": result_status,
        "result_payload_sha256": "0" * 64,
    }


def _talk(
    filename: str,
    *,
    status: str = "processed",
    date: str | None = "2026-09-10",
    claim: dict[str, object] | None | bool = True,
):
    talk: dict[str, object] = {
        "filename": filename,
        "schema_version": TALK_SCHEMA_VERSION,
        "status": status,
    }
    if date is not None:
        talk["date"] = date
    if claim is True:
        claim = _persisted_claim(SEED_RUN, SEED_RELEASED, result_status=status)
    if claim:
        talk["reprocess_generation"] = 1
        talk["_queue_claim"] = claim
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


def _copy_path(tmp_path: Path, run_id: str, content: bytes) -> Path:
    digest = hashlib.sha256(content).hexdigest()
    stem = "".join(c if c.isalnum() or c in "._-" else "_" for c in run_id)
    if len(stem) > 40:
        stem = stem[:31] + "-" + hashlib.sha256(run_id.encode()).hexdigest()[:8]
    return tmp_path / "ingress-reports" / f"{stem}.{digest}.md"


def _report(tmp_path: Path, text: str = "# Ingress report\n\nTwo talks processed.\n"):
    path = tmp_path / "delivered.md"
    path.write_text(text, encoding="utf-8")
    return path


def _fresh_talks():
    return [
        _talk("fresh.md", date="2026-09-10"),
        _talk("older.md", status="processed_partial", date="2026-01-01"),
        _talk("skipped.md", status="skipped_no_sources", date="2026-09-12"),
        _talk("undated.md", date=None),
        _talk("unpersisted.md", claim=None),
    ]


def _adopt(database: Path, now: str = ADOPTED):
    return _ok(database, "adopt", "--now", now)


@pytest.fixture
def fresh_db(tmp_path: Path):
    database = _write_db(tmp_path, _fresh_talks())
    _adopt(database)
    return database


@pytest.fixture
def unadopted_db(tmp_path: Path):
    return _write_db(tmp_path, _fresh_talks())


def _open(database: Path, run_id: str, *talks: str, now: str = NOW):
    arguments = ["open", "--run-id", run_id, "--now", now]
    for talk in talks:
        arguments += ["--talk", talk]
    return _ok(database, *arguments)


def _downstream(database: Path, run_id: str, now: str = NOW):
    return _ok(database, "record-downstream", "--run-id", run_id, "--now", now)


def _opened(database: Path, run_id: str = "run-x", *talks: str) -> str:
    """A run past its downstream steps, ready for the offer."""
    _open(database, run_id, *(talks or ("fresh.md",)))
    _downstream(database, run_id)
    return run_id


def _declined(database: Path, run_id: str = "run-x") -> str:
    _opened(database, run_id)
    _ok(database, "record-offer", "--run-id", run_id, "--now", NOW)
    _ok(
        database,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        NOW,
        "--disposition",
        "declined",
    )
    return run_id


def _accepted(database: Path, run_id: str = "run-x") -> str:
    _opened(database, run_id)
    _ok(database, "record-offer", "--run-id", run_id, "--now", NOW)
    _ok(
        database,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        NOW,
        "--disposition",
        "accepted",
    )
    return run_id


def _record_report(database: Path, run_id: str, report: Path, now: str = LATER):
    return _ok(
        database,
        "record-report",
        "--run-id",
        run_id,
        "--now",
        now,
        "--report-file",
        str(report),
    )


# ── open ──────────────────────────────────────────────────────────────


def test_open_records_recency_and_the_persisting_claim_and_owes_downstream(
    tmp_path, fresh_db
):
    payload = _open(fresh_db, "run-a", "fresh.md", "older.md", "skipped.md")
    run = payload["run"]
    assert payload["written"] is True
    assert payload["durability_state"] == "durable"
    assert payload["warnings"] == []
    assert payload["ledger_path"] == str(tmp_path / "ingress-obligations.json")
    assert run["schema_version"] == 1
    assert [
        (t["filename"], t["status"], t["recency_bucket"], t["claim_run_id"])
        for t in run["talks"]
    ] == [
        ("fresh.md", "processed", "same_week", SEED_RUN),
        ("older.md", "processed_partial", "older", SEED_RUN),
        ("skipped.md", "skipped_no_sources", "same_week", SEED_RUN),
    ]
    assert run["talks"][0]["days_since_delivery"] == 4
    assert run["downstream"] == {"state": "owed", "completed_at": None}
    assert run["clarification"]["state"] == "owed"
    assert run["clarification"]["offer_mode"] == "inline"
    assert run["clarification"]["recency_as_of"] == NOW
    assert run["end_report"]["state"] == "owed"
    assert run["completed_at"] is None
    assert _ledger(tmp_path)["schema_version"] == 1
    pending = _ok(fresh_db, "pending")
    assert pending["count"] == 1
    assert pending["pending"][0]["next_action"] == "complete_downstream_steps"
    assert pending["pending"][0]["downstream_state"] == "owed"


def test_the_run_links_a_talk_to_its_own_claim_when_it_has_one(tmp_path):
    talk = _talk(
        "own.md", claim=_persisted_claim("run-own", "2026-09-13T00:00:00+00:00")
    )
    talk["_queue_claim_history"] = [
        _persisted_claim("older-run", "2026-09-05T00:00:00+00:00")
    ]
    database = _write_db(tmp_path, [talk])
    _adopt(database)
    run = _open(database, "run-own", "own.md")["run"]
    assert run["talks"][0]["claim_run_id"] == "run-own"
    recovered = _open(database, "fresh-id", "own.md")["run"]
    assert recovered["talks"][0]["claim_run_id"] == "run-own"


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
    run = _open(fresh_db, "run-b", *talks)["run"]
    assert run["clarification"]["offer_mode"] == mode
    assert run["clarification"]["state"] == state


def test_a_run_with_nothing_to_clarify_still_owes_downstream_then_its_report(fresh_db):
    _open(fresh_db, "run-c", "skipped.md")
    assert _ok(fresh_db, "pending")["pending"][0]["next_action"] == (
        "complete_downstream_steps"
    )
    _downstream(fresh_db, "run-c")
    assert _ok(fresh_db, "pending")["pending"][0]["next_action"] == "deliver_end_report"


def test_open_replays_without_rewriting(tmp_path, fresh_db):
    first = _open(fresh_db, "run-d", "fresh.md")
    raw_before = (tmp_path / "ingress-obligations.json").read_bytes()
    second = _open(fresh_db, "run-d", "fresh.md")
    assert second["written"] is False
    assert second["durability_state"] == "unchanged"
    assert second["run"]["updated_at"] == first["run"]["updated_at"] == NOW
    assert (tmp_path / "ingress-obligations.json").read_bytes() == raw_before
    refreshed = _open(fresh_db, "run-d", "fresh.md", now=LATER)
    assert refreshed["written"] is True
    assert refreshed["run"]["clarification"]["recency_as_of"] == LATER
    assert refreshed["run"]["updated_at"] == LATER


def test_a_later_batch_joins_the_run_strengthens_the_offer_and_re_owes_downstream(
    fresh_db,
):
    _opened(fresh_db, "run-e", "older.md")
    before = _ok(fresh_db, "status", "--run-id", "run-e")["run"]
    assert before["downstream"]["state"] == "completed"
    run = _open(fresh_db, "run-e", "fresh.md", now=LATER)["run"]
    assert [t["filename"] for t in run["talks"]] == ["fresh.md", "older.md"]
    assert run["clarification"]["offer_mode"] == "inline"
    assert run["downstream"] == {"state": "owed", "completed_at": None}
    assert run["updated_at"] == LATER


def test_recency_moves_with_the_clock_until_the_offer_is_made(fresh_db):
    _open(fresh_db, "run-f", "fresh.md")
    resumed = _open(fresh_db, "run-f", "fresh.md", now=MUCH_LATER)["run"]
    assert resumed["talks"][0]["recency_bucket"] == "recent"
    assert resumed["clarification"]["offer_mode"] == "recommend_full"


def test_a_talk_joining_while_the_offer_stands_withdraws_it(fresh_db):
    run_id = _opened(fresh_db, "run-g")
    _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW, "--topic", "aside")
    run = _open(fresh_db, run_id, "older.md", now=MUCH_LATER)["run"]
    assert run["clarification"]["state"] == "owed"
    assert run["clarification"]["offered_at"] is None
    assert run["clarification"]["topics"] == []
    assert run["clarification"]["recency_as_of"] == MUCH_LATER
    assert [t["filename"] for t in run["talks"]] == ["fresh.md", "older.md"]
    assert run["downstream"]["state"] == "owed"
    assert _ok(fresh_db, "pending")["pending"][0]["next_action"] == (
        "complete_downstream_steps"
    )
    _downstream(fresh_db, run_id, now=MUCH_LATER)
    again = _ok(
        fresh_db,
        "record-offer",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--topic",
        "aside",
        "--topic",
        "the older talk's pacing",
    )
    assert again["offered"] is True
    assert again["run"]["clarification"]["topics"] == [
        "aside",
        "the older talk's pacing",
    ]


@pytest.mark.parametrize("disposition", ["declined", "accepted"])
def test_a_talk_cannot_join_a_run_whose_offer_was_answered(fresh_db, disposition):
    run_id = _opened(fresh_db, "run-answered")
    _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW)
    _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        NOW,
        "--disposition",
        disposition,
    )
    refused = _refused(
        fresh_db, "open", "--run-id", run_id, "--now", LATER, "--talk", "older.md"
    )
    assert refused["reason_code"] == "invalid_transition"
    assert "fresh run id" in refused["error"]
    replay = _open(fresh_db, run_id, "fresh.md", now=LATER)
    assert replay["written"] is False


def test_open_refuses_a_talk_the_database_does_not_hold(fresh_db):
    payload = _refused(
        fresh_db, "open", "--run-id", "run-h", "--now", NOW, "--talk", "ghost.md"
    )
    assert payload["reason_code"] == "talk_not_found"
    assert "persist-results.py" in payload["error"]


def test_open_refuses_a_talk_no_closed_claim_persisted(fresh_db):
    payload = _refused(
        fresh_db,
        "open",
        "--run-id",
        "run-i",
        "--now",
        NOW,
        "--talk",
        "unpersisted.md",
    )
    assert payload["reason_code"] == "talk_not_persisted"
    assert _ok(fresh_db, "pending")["pending"] == []


# ── downstream steps ──────────────────────────────────────────────────


def test_the_offer_waits_for_the_downstream_steps(fresh_db):
    _open(fresh_db, "run-j", "fresh.md")
    refused = _refused(fresh_db, "record-offer", "--run-id", "run-j", "--now", NOW)
    assert refused["reason_code"] == "invalid_transition"
    assert "record-downstream" in refused["error"]
    done = _downstream(fresh_db, "run-j", now=LATER)
    assert done["run"]["downstream"] == {"state": "completed", "completed_at": LATER}
    assert _ok(fresh_db, "pending")["pending"][0]["next_action"] == (
        "offer_clarification"
    )
    replay = _downstream(fresh_db, "run-j", now=MUCH_LATER)
    assert replay["written"] is False
    assert replay["run"]["downstream"]["completed_at"] == LATER


def test_the_report_waits_for_the_downstream_steps_even_with_nothing_to_clarify(
    tmp_path, fresh_db
):
    _open(fresh_db, "run-k", "skipped.md")
    refused = _refused(
        fresh_db,
        "record-report",
        "--run-id",
        "run-k",
        "--now",
        LATER,
        "--report-file",
        str(_report(tmp_path)),
    )
    assert refused["reason_code"] == "invalid_transition"
    assert "record-downstream" in refused["error"]


# ── offer and disposition ─────────────────────────────────────────────


def test_an_offer_is_recorded_once_with_its_topics(fresh_db):
    run_id = _opened(fresh_db)
    payload = _ok(
        fresh_db,
        "record-offer",
        "--run-id",
        run_id,
        "--now",
        NOW,
        "--topic",
        " bilingual joke at 12:40 ",
        "--topic",
        "  ",
        "--topic",
        "improvised aside",
    )
    assert payload["offered"] is True
    assert "reason" not in payload
    run = payload["run"]
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


def test_the_offer_refreshes_recency_against_the_current_database(fresh_db):
    run_id = _opened(fresh_db, "run-r")
    stale = _ok(fresh_db, "status", "--run-id", run_id)
    assert stale["summary"]["offer_mode"] == "inline"
    assert stale["summary"]["recency_as_of"] == NOW
    run = _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", MUCH_LATER)["run"]
    assert run["clarification"]["state"] == "offered"
    assert run["clarification"]["offer_mode"] == "recommend_full"
    assert run["clarification"]["recency_as_of"] == MUCH_LATER
    assert run["talks"][0]["recency_bucket"] == "recent"
    assert run["talks"][0]["days_since_delivery"] == 20


def test_the_offer_is_withdrawn_when_the_database_no_longer_has_an_analyzed_talk(
    tmp_path,
):
    database = _write_db(tmp_path, [_talk("fresh.md")])
    _adopt(database)
    _opened(database, "run-w")
    requeued = _talk("fresh.md", status="needs-reprocessing", claim=None)
    requeued["reprocess_generation"] = 1
    requeued["_queue_claim_history"] = [_persisted_claim(SEED_RUN, SEED_RELEASED)]
    _write_db(tmp_path, [requeued])
    payload = _ok(database, "record-offer", "--run-id", "run-w", "--now", LATER)
    assert payload["offered"] is False
    assert "nothing to ask" in payload["reason"]
    assert payload["run"]["clarification"]["state"] == "not_applicable"
    assert payload["run"]["clarification"]["offer_mode"] == "none"
    assert payload["run"]["talks"][0]["status"] == "needs-reprocessing"
    status = _ok(database, "status", "--run-id", "run-w")
    assert status["run"]["clarification"]["state"] == "not_applicable"
    assert status["summary"]["next_action"] == "deliver_end_report"
    delivered = _record_report(database, "run-w", _report(tmp_path), now=MUCH_LATER)
    assert delivered["run"]["completed_at"] == MUCH_LATER
    assert _ok(database, "pending")["pending"] == []


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
            ["--return-condition", "  after the next delivery  "],
            "deliver_end_report",
            None,
        ),
        (
            "accepted",
            [],
            "complete_clarification_session",
            {
                "state": "pending",
                "completed_at": None,
                "profile_inputs": None,
                "profile_refreshed": None,
            },
        ),
    ],
)
def test_each_disposition_is_explicit(
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
    other = "accepted" if disposition == "declined" else "declined"
    code, changed, _stderr = _run(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--disposition",
        other,
    )
    assert changed is not None
    if disposition == "deferred":
        # A deferred offer is the one answer that can be given again.
        assert code == 0
        assert changed["run"]["clarification"]["state"] == other
    else:
        assert code == 2
        assert changed["reason_code"] == "invalid_transition"


@pytest.mark.parametrize(
    "extra", [[], ["--return-condition", "   "]], ids=["absent", "blank"]
)
def test_a_deferral_names_when_it_returns(fresh_db, extra):
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
        *extra,
    )
    assert payload["reason_code"] == "invalid_arguments"
    assert "--return-condition" in payload["error"]
    state = _ok(fresh_db, "status", "--run-id", run_id)["run"]["clarification"]["state"]
    assert state == "offered"


# ── session ───────────────────────────────────────────────────────────


def test_the_session_completes_once_and_only_after_acceptance(fresh_db):
    run_id = _opened(fresh_db)
    early = _refused(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        NOW,
        "--profile-inputs",
        "unchanged",
    )
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
        "--profile-inputs",
        "changed",
        "--profile-refreshed",
    )["run"]
    assert run["clarification"]["session"] == {
        "state": "completed",
        "completed_at": LATER,
        "profile_inputs": "changed",
        "profile_refreshed": True,
    }
    assert _ok(fresh_db, "pending")["pending"][0]["next_action"] == "deliver_end_report"
    twice = _refused(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--profile-inputs",
        "unchanged",
    )
    assert twice["reason_code"] == "invalid_transition"


def test_changed_profile_inputs_need_a_refreshed_profile_when_one_exists(
    tmp_path, fresh_db
):
    run_id = _accepted(fresh_db)
    (tmp_path / "speaker-profile.json").write_text("{}", encoding="utf-8")
    refused = _refused(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--profile-inputs",
        "changed",
    )
    assert refused["reason_code"] == "profile_refresh_required"
    assert "Step 7" in refused["error"]
    still_pending = _ok(fresh_db, "status", "--run-id", run_id)
    assert still_pending["run"]["clarification"]["session"]["state"] == "pending"
    done = _ok(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--profile-inputs",
        "changed",
        "--profile-refreshed",
    )
    assert done["run"]["clarification"]["session"]["profile_refreshed"] is True


@pytest.mark.parametrize(
    ("profile_exists", "inputs"),
    [(True, "unchanged"), (False, "changed")],
    ids=["unchanged-inputs", "no-profile-to-refresh"],
)
def test_a_session_completes_without_a_refresh_when_none_is_owed(
    tmp_path, fresh_db, profile_exists, inputs
):
    run_id = _accepted(fresh_db)
    if profile_exists:
        (tmp_path / "speaker-profile.json").write_text("{}", encoding="utf-8")
    done = _ok(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--profile-inputs",
        inputs,
    )
    assert done["run"]["clarification"]["session"] == {
        "state": "completed",
        "completed_at": LATER,
        "profile_inputs": inputs,
        "profile_refreshed": False,
    }


# ── end report ────────────────────────────────────────────────────────


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
    run_id = _declined(fresh_db)
    report = _report(tmp_path)
    payload = _record_report(fresh_db, run_id, report)
    run = payload["run"]
    copied = _copy_path(tmp_path, run_id, report.read_bytes())
    assert copied.read_bytes() == report.read_bytes()
    assert run["end_report"] == {
        "state": "delivered",
        "delivered_at": LATER,
        "report_path": str(copied),
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "reopened_at": None,
    }
    assert run["completed_at"] == LATER
    assert _ok(fresh_db, "pending") == {
        "ok": True,
        "ledger_path": str(tmp_path / "ingress-obligations.json"),
        "ledger_present": True,
        "adopt_required": False,
        "adopted_at": ADOPTED,
        "pending": [],
        "count": 0,
        "deferred_offers": [],
        "open_required": [],
    }
    status = _ok(fresh_db, "status", "--run-id", run_id)
    assert status["summary"]["next_action"] == "none"
    replay = _record_report(fresh_db, run_id, report, now=MUCH_LATER)
    assert replay["written"] is False
    assert replay["run"]["completed_at"] == LATER
    reopened = _refused(
        fresh_db, "open", "--run-id", run_id, "--now", MUCH_LATER, "--talk", "older.md"
    )
    assert reopened["reason_code"] == "invalid_transition"


def test_a_replay_recreates_a_copy_that_went_missing(tmp_path, fresh_db):
    run_id = _declined(fresh_db)
    report = _report(tmp_path)
    _record_report(fresh_db, run_id, report)
    copied = _copy_path(tmp_path, run_id, report.read_bytes())
    copied.unlink()
    replay = _record_report(fresh_db, run_id, report, now=MUCH_LATER)
    assert replay["written"] is False
    assert copied.read_bytes() == report.read_bytes()
    assert replay["run"]["end_report"]["delivered_at"] == LATER


def test_a_placeholder_is_not_a_delivered_report(tmp_path, fresh_db):
    run_id = _declined(fresh_db)
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
    state = _ok(fresh_db, "status", "--run-id", run_id)["run"]["end_report"]["state"]
    assert state == "owed"


def test_a_report_copy_that_cannot_be_written_records_nothing(tmp_path, fresh_db):
    run_id = _declined(fresh_db)
    (tmp_path / "ingress-reports").write_text("not a directory", encoding="utf-8")
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
    assert payload["reason_code"] == "report_copy_failed"
    assert "record-report" in payload["error"]
    status = _ok(fresh_db, "status", "--run-id", run_id)
    assert status["run"]["end_report"]["state"] == "owed"
    assert status["run"]["completed_at"] is None


def test_a_symlinked_reports_directory_is_refused(tmp_path, fresh_db):
    run_id = _declined(fresh_db)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "ingress-reports").symlink_to(elsewhere)
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
    assert payload["reason_code"] == "report_copy_failed"
    assert "not a real directory" in payload["error"]
    assert list(elsewhere.iterdir()) == []
    state = _ok(fresh_db, "status", "--run-id", run_id)["run"]["end_report"]["state"]
    assert state == "owed"


def test_a_symlinked_copy_target_is_refused(tmp_path, fresh_db):
    run_id = _declined(fresh_db)
    report = _report(tmp_path)
    (tmp_path / "ingress-reports").mkdir()
    decoy = tmp_path / "decoy.md"
    decoy.write_text("decoy", encoding="utf-8")
    _copy_path(tmp_path, run_id, report.read_bytes()).symlink_to(decoy)
    payload = _refused(
        fresh_db,
        "record-report",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--report-file",
        str(report),
    )
    assert payload["reason_code"] == "report_copy_failed"
    assert decoy.read_text(encoding="utf-8") == "decoy"


def test_two_different_deliveries_keep_both_copies(tmp_path, fresh_db):
    run_id = _declined(fresh_db)
    first = _report(tmp_path, "# first\n")
    _record_report(fresh_db, run_id, first)
    second = _report(tmp_path, "# second\n")
    payload = _record_report(fresh_db, run_id, second, now=MUCH_LATER)
    assert _copy_path(tmp_path, run_id, b"# first\n").read_bytes() == b"# first\n"
    assert Path(payload["run"]["end_report"]["report_path"]).read_bytes() == (
        b"# second\n"
    )
    assert payload["run"]["end_report"]["delivered_at"] == MUCH_LATER


# ── run ids and report paths ──────────────────────────────────────────


def test_a_queue_style_run_id_with_a_slash_opens_and_reports_inside_the_vault(
    tmp_path, fresh_db
):
    run_id = "reparse/2026-09-14"
    _declined(fresh_db, run_id)
    report = _report(tmp_path)
    payload = _record_report(fresh_db, run_id, report)
    copied = Path(payload["run"]["end_report"]["report_path"])
    assert copied == _copy_path(tmp_path, run_id, report.read_bytes())
    assert copied.parent == tmp_path / "ingress-reports"
    assert copied.read_bytes() == report.read_bytes()


def test_a_ledger_edited_run_id_cannot_name_a_path_outside_the_reports_directory(
    tmp_path, fresh_db
):
    run = _valid_run(run_id="../../escape")
    run["clarification"].update(
        {"state": "declined", "offered_at": NOW, "resolved_at": NOW}
    )
    (tmp_path / "ingress-obligations.json").write_text(
        json.dumps({**ENVELOPE, "runs": [run]}), encoding="utf-8"
    )
    report = _report(tmp_path)
    payload = _record_report(fresh_db, "../../escape", report)
    copied = Path(payload["run"]["end_report"]["report_path"])
    assert copied.parent == tmp_path / "ingress-reports"
    assert copied.name.startswith(".._.._escape.")


# ── deferred offers come back ─────────────────────────────────────────


def test_a_deferred_offer_is_listed_until_it_is_answered_again(tmp_path, fresh_db):
    run_id = _opened(fresh_db)
    _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW, "--topic", "aside")
    _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        NOW,
        "--disposition",
        "deferred",
        "--return-condition",
        "after JavaZone",
    )
    _record_report(fresh_db, run_id, _report(tmp_path))
    pending = _ok(fresh_db, "pending")
    assert pending["pending"] == []
    assert pending["deferred_offers"] == [
        {
            "run_id": run_id,
            "return_condition": "after JavaZone",
            "topics": ["aside"],
            "resolved_at": NOW,
        }
    ]
    raised_again = _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--disposition",
        "accepted",
    )
    assert raised_again["run"]["clarification"]["return_condition"] is None
    assert raised_again["run"]["completed_at"] == LATER
    pending = _ok(fresh_db, "pending")
    assert pending["deferred_offers"] == []
    assert pending["pending"][0]["next_action"] == "complete_clarification_session"
    _ok(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--profile-inputs",
        "unchanged",
    )
    assert _ok(fresh_db, "pending")["pending"] == []


# ── runs that persisted but never opened ──────────────────────────────


def _db_with_claims(tmp_path: Path, claims: dict[str, tuple[str, str]]):
    """Talks whose claims closed after adoption, so reconciliation sees them."""
    if not (tmp_path / "ingress-obligations.json").exists():
        _adopt(_write_db(tmp_path, [_talk(name, claim=None) for name in claims]))
    talks = [
        _talk(filename, claim=_persisted_claim(run_id, released_at))
        for filename, (run_id, released_at) in claims.items()
    ]
    return _write_db(tmp_path, talks)


def test_a_persisted_run_with_no_ledger_record_is_reported_for_opening(tmp_path):
    database = _db_with_claims(
        tmp_path,
        {
            "a.md": ("crashed-run", "2026-09-13T10:00:00+00:00"),
            "b.md": ("crashed-run", "2026-09-13T10:05:00+00:00"),
        },
    )
    payload = _ok(database, "pending")
    assert payload["open_required"] == [
        {
            "run_id": "crashed-run",
            "talks": ["a.md", "b.md"],
            "latest_released_at": "2026-09-13T10:05:00+00:00",
            "reason": "unrecorded_run",
            "next_action": "open_obligations",
        }
    ]
    _open(database, "crashed-run", "a.md", "b.md")
    assert _ok(database, "pending")["open_required"] == []


def test_a_later_batch_of_a_recorded_run_is_reported_with_only_its_missing_talks(
    tmp_path,
):
    database = _db_with_claims(
        tmp_path,
        {
            "a.md": ("run-two-batches", "2026-09-13T10:00:00+00:00"),
            "b.md": ("run-two-batches", "2026-09-13T11:00:00+00:00"),
            "c.md": ("run-two-batches", "2026-09-13T11:00:00+00:00"),
        },
    )
    _open(database, "run-two-batches", "a.md", now="2026-09-13T10:30:00+00:00")
    payload = _ok(database, "pending")
    assert payload["open_required"] == [
        {
            "run_id": "run-two-batches",
            "talks": ["b.md", "c.md"],
            "latest_released_at": "2026-09-13T11:00:00+00:00",
            "reason": "missing_talks",
            "next_action": "open_obligations",
        }
    ]
    _open(database, "run-two-batches", "b.md", "c.md")
    assert _ok(database, "pending")["open_required"] == []
    run = _ok(database, "status", "--run-id", "run-two-batches")["run"]
    assert [talk["filename"] for talk in run["talks"]] == ["a.md", "b.md", "c.md"]


def test_talks_persisted_under_a_completed_run_are_named_for_a_fresh_run_once(
    tmp_path,
):
    database = _db_with_claims(
        tmp_path, {"a.md": ("done-run", "2026-09-13T10:00:00+00:00")}
    )
    _opened(database, "done-run", "a.md")
    _ok(database, "record-offer", "--run-id", "done-run", "--now", NOW)
    _ok(
        database,
        "record-disposition",
        "--run-id",
        "done-run",
        "--now",
        NOW,
        "--disposition",
        "declined",
    )
    _record_report(database, "done-run", _report(tmp_path))
    _db_with_claims(
        tmp_path,
        {
            "a.md": ("done-run", "2026-09-13T10:00:00+00:00"),
            "late.md": ("done-run", "2026-09-15T10:00:00+00:00"),
        },
    )
    payload = _ok(database, "pending")
    assert payload["open_required"] == [
        {
            "run_id": "done-run",
            "talks": ["late.md"],
            "latest_released_at": "2026-09-15T10:00:00+00:00",
            "reason": "talks_persisted_after_completion",
            "next_action": "open_obligations",
        }
    ]
    refused = _refused(
        database,
        "open",
        "--run-id",
        "done-run",
        "--now",
        MUCH_LATER,
        "--talk",
        "late.md",
    )
    assert refused["reason_code"] == "invalid_transition"
    # Recovering under a fresh run id links the talk to the claim that
    # persisted it, so the recovery is not reported again.
    recovered = _open(database, "done-run-recovery", "late.md", now=MUCH_LATER)
    assert recovered["run"]["talks"][0]["claim_run_id"] == "done-run"
    assert _ok(database, "pending")["open_required"] == []


def test_every_uncovered_run_after_adoption_is_listed_until_opened_or_dismissed(
    tmp_path,
):
    # ancient-run closed before adoption: history by identity, never listed.
    ancient = _talk(
        "old.md", claim=_persisted_claim("ancient-run", "2026-08-01T00:00:00+00:00")
    )
    _adopt(
        _write_db(
            tmp_path,
            [
                ancient,
                *(_talk(name, claim=None) for name in ("mid.md", "new.md", "seen.md")),
            ],
        )
    )
    database = _db_with_claims(
        tmp_path,
        {
            "old.md": ("ancient-run", "2026-08-01T00:00:00+00:00"),
            "mid.md": ("middle-run", "2026-09-10T00:00:00+00:00"),
            "new.md": ("newest-run", "2026-09-12T00:00:00+00:00"),
            "seen.md": ("recorded-run", "2026-09-05T00:00:00+00:00"),
        },
    )
    _open(database, "recorded-run", "seen.md", now="2026-09-06T00:00:00+00:00")
    listed = [entry["run_id"] for entry in _ok(database, "pending")["open_required"]]
    assert listed == ["middle-run", "newest-run"]
    # Opening the newer one never hides the older one.
    _open(database, "newest-run", "new.md", now="2026-09-13T00:00:00+00:00")
    listed = [entry["run_id"] for entry in _ok(database, "pending")["open_required"]]
    assert listed == ["middle-run"]
    dismissed = _ok(
        database,
        "dismiss",
        "--run-id",
        "middle-run",
        "--now",
        NOW,
        "--reason",
        "batch was re-run as newest-run",
    )
    assert dismissed["dismissed"] == {
        "run_id": "middle-run",
        "dismissed_at": NOW,
        "reason": "batch was re-run as newest-run",
        "facts": [_identity("middle-run", "mid.md", "2026-09-10T00:00:00+00:00")],
    }
    assert _ok(database, "pending")["open_required"] == []
    assert _ledger(tmp_path)["dismissed_runs"] == [dismissed["dismissed"]]


def test_a_dismissal_is_explicit_replay_safe_and_never_for_a_recorded_run(tmp_path):
    database = _db_with_claims(
        tmp_path,
        {
            "a.md": ("gone-run", "2026-09-10T00:00:00+00:00"),
            "b.md": ("kept-run", "2026-09-11T00:00:00+00:00"),
        },
    )
    _open(database, "kept-run", "b.md")
    blank = _refused(
        database, "dismiss", "--run-id", "gone-run", "--now", NOW, "--reason", "  "
    )
    assert blank["reason_code"] == "invalid_arguments"
    recorded = _refused(
        database, "dismiss", "--run-id", "kept-run", "--now", NOW, "--reason", "no"
    )
    assert recorded["reason_code"] == "invalid_transition"
    unlisted = _refused(
        database, "dismiss", "--run-id", "never-ran", "--now", NOW, "--reason", "typo"
    )
    assert unlisted["reason_code"] == "invalid_transition"
    assert "only a listed unrecorded_run" in unlisted["error"]
    _ok(database, "dismiss", "--run-id", "gone-run", "--now", NOW, "--reason", "dup")
    replay = _ok(
        database, "dismiss", "--run-id", "gone-run", "--now", LATER, "--reason", "dup"
    )
    assert replay["replayed"] is True
    assert replay["written"] is False
    conflict = _refused(
        database, "dismiss", "--run-id", "gone-run", "--now", LATER, "--reason", "other"
    )
    assert conflict["reason_code"] == "invalid_transition"
    assert _ok(database, "pending")["open_required"] == []


def test_a_replayed_open_of_a_completed_run_is_an_unchanged_success(tmp_path):
    database = _db_with_claims(
        tmp_path, {"a.md": ("done-run", "2026-09-13T10:00:00+00:00")}
    )
    _opened(database, "done-run", "a.md")
    _ok(database, "record-offer", "--run-id", "done-run", "--now", NOW)
    _ok(
        database,
        "record-disposition",
        "--run-id",
        "done-run",
        "--now",
        NOW,
        "--disposition",
        "declined",
    )
    done = _record_report(database, "done-run", _report(tmp_path))
    replay = _open(database, "done-run", "a.md", now=MUCH_LATER)
    assert replay["replayed"] is True
    assert replay["written"] is False
    assert replay["run"] == done["run"]


@pytest.mark.parametrize(
    ("envelope", "detail"),
    [
        ({"schema_version": 1, "dismissed_runs": [], "runs": []}, "lacks adopted_at"),
        (
            {
                "schema_version": 1,
                "adopted_at": "soon",
                "dismissed_runs": [],
                "runs": [],
            },
            "adopted_at 'soon' is malformed",
        ),
        (
            {
                "schema_version": 1,
                "adopted_at": ADOPTED,
                "adopted_facts": [],
                "runs": [],
            },
            "dismissed_runs array",
        ),
        (
            {
                "schema_version": 1,
                "adopted_at": ADOPTED,
                "dismissed_runs": [],
                "runs": [],
            },
            "lacks adopted_facts",
        ),
        (
            {**ENVELOPE, "adopted_facts": [["r", "a.md", "b1", 1]], "runs": []},
            "adopted_facts[0] must be [run_id, filename, batch_id, generation, released_at]",
        ),
        (
            {**ENVELOPE, "adopted_facts": [["r", "a.md", "b1", "1", NOW]], "runs": []},
            "generation must be a non-negative integer",
        ),
        (
            {**ENVELOPE, "dismissed_runs": [{"run_id": "x"}], "runs": []},
            "dismissed_runs[0] lacks dismissed_at",
        ),
        (
            {
                **ENVELOPE,
                "dismissed_runs": [
                    {"run_id": "x", "dismissed_at": NOW, "reason": " ", "facts": []}
                ],
                "runs": [],
            },
            "dismissed_runs[0].reason must say why",
        ),
        (
            {
                **ENVELOPE,
                "dismissed_runs": [
                    {
                        "run_id": "x",
                        "dismissed_at": NOW,
                        "reason": "a",
                        "facts": [["y", "a.md", "b1", 1, NOW]],
                    }
                ],
                "runs": [],
            },
            "dismissed_runs[0].facts name another run",
        ),
        (
            {
                **ENVELOPE,
                "dismissed_runs": [
                    {"run_id": "x", "dismissed_at": NOW, "reason": "a", "facts": []},
                    {"run_id": "x", "dismissed_at": NOW, "reason": "b", "facts": []},
                ],
                "runs": [],
            },
            "dismissed_runs[1] duplicates 'x'",
        ),
    ],
    ids=[
        "no-adopted-at",
        "adopted-at-malformed",
        "no-dismissed-runs",
        "no-adopted-facts",
        "adopted-fact-shape",
        "adopted-fact-generation",
        "dismissal-keys",
        "dismissal-reason",
        "dismissal-foreign-fact",
        "dismissal-duplicate",
    ],
)
def test_a_malformed_envelope_fails_structured(tmp_path, fresh_db, envelope, detail):
    (tmp_path / "ingress-obligations.json").write_text(
        json.dumps(envelope), encoding="utf-8"
    )
    payload = _refused(fresh_db, "pending")
    assert payload["reason_code"] == "ledger_invalid"
    assert detail in payload["error"]


def test_history_claims_count_and_other_release_reasons_do_not(tmp_path):
    _adopt(_write_db(tmp_path, [_talk("h.md", claim=None)]))
    talk = _talk(
        "h.md",
        claim={
            **_persisted_claim("recovered-run", "2026-09-13T00:00:00+00:00"),
            "state": "stale_recovered",
            "release_reason": "lease_expired",
        },
    )
    talk["_queue_claim_history"] = [
        _persisted_claim("history-run", "2026-09-11T00:00:00+00:00")
    ]
    database = _write_db(tmp_path, [talk])
    payload = _ok(database, "pending")
    assert [entry["run_id"] for entry in payload["open_required"]] == ["history-run"]


# ── inputs, ledger, and database gates ────────────────────────────────


def test_nothing_is_reconciled_before_the_ledger_is_adopted(tmp_path, unadopted_db):
    payload = _ok(unadopted_db, "pending")
    assert payload["ledger_present"] is False
    assert payload["adopt_required"] is True
    assert payload["adopted_at"] is None
    assert payload["pending"] == []
    assert payload["open_required"] == []
    assert not (tmp_path / "ingress-obligations.json").exists()
    refused = _refused(
        unadopted_db, "open", "--run-id", "run-0", "--now", NOW, "--talk", "fresh.md"
    )
    assert refused["reason_code"] == "ledger_not_adopted"
    assert "adopt --now" in refused["error"]


def test_adoption_stamps_the_boundary_once(tmp_path, unadopted_db):
    first = _adopt(unadopted_db, now=NOW)
    assert first["written"] is True
    assert first["adopted_at"] == NOW
    assert first["adopted_fact_count"] == 4
    history = [
        _identity(SEED_RUN, name, SEED_RELEASED)
        for name in ("fresh.md", "older.md", "skipped.md", "undated.md")
    ]
    assert _ledger(tmp_path) == {
        **ENVELOPE,
        "adopted_at": NOW,
        "adopted_facts": history,
        "runs": [],
    }
    replay = _adopt(unadopted_db, now=LATER)
    assert replay["replayed"] is True
    assert replay["written"] is False
    assert replay["adopted_at"] == NOW
    payload = _ok(unadopted_db, "pending")
    assert payload["adopt_required"] is False
    assert payload["adopted_at"] == NOW


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
            ["open", "--run-id", "run 2026", "--now", NOW, "--talk", "fresh.md"],
            "invalid_arguments",
        ),
        (["record-offer", "--run-id", "run-z"], "invalid_arguments"),
        (["record-session", "--run-id", "run-z", "--now", NOW], "invalid_arguments"),
        (
            [
                "open",
                "--run-id",
                "run-z",
                "--now",
                "0001-01-01T00:00:00+01:00",
                "--talk",
                "fresh.md",
            ],
            "invalid_timestamp",
        ),
        ([], "invalid_arguments"),
    ],
    ids=[
        "date-only",
        "naive",
        "no-talk",
        "bad-run-id",
        "missing-now",
        "missing-profile-inputs",
        "overflow",
        "no-action",
    ],
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
        json.dumps({**ENVELOPE, "runs": [{"run_id": "r"}]}), encoding="utf-8"
    )
    payload = _refused(fresh_db, "pending")
    assert payload["reason_code"] == "ledger_invalid"
    assert "lacks schema_version" in payload["error"]


def _valid_run(run_id: str = "r", **overrides):
    run = {
        "schema_version": 1,
        "run_id": run_id,
        "opened_at": NOW,
        "updated_at": NOW,
        "talks": [
            {
                "filename": "fresh.md",
                "status": "processed",
                "delivery_date": "2026-09-10",
                "days_since_delivery": 4,
                "recency_bucket": "same_week",
                "claim_run_id": SEED_RUN,
                "claim_batch_id": "b1",
                "claim_generation": 1,
                "claim_released_at": SEED_RELEASED,
            }
        ],
        "downstream": {"state": "completed", "completed_at": NOW},
        "clarification": {
            "state": "owed",
            "offer_mode": "inline",
            "topics": [],
            "recency_as_of": NOW,
            "offered_at": None,
            "resolved_at": None,
            "return_condition": None,
            "session": None,
        },
        "end_report": {
            "state": "owed",
            "delivered_at": None,
            "report_path": None,
            "report_sha256": None,
            "reopened_at": None,
        },
        "completed_at": None,
    }
    _apply_overrides(run, overrides)
    return run


def _apply_overrides(run, overrides):
    for path, value in overrides.items():
        target = run
        *parents, leaf = path.split(".")
        for parent in parents:
            target = target[int(parent)] if isinstance(target, list) else target[parent]
        target[leaf] = value


_DELIVERED = {
    "state": "delivered",
    "delivered_at": LATER,
    "report_path": "/vault/ingress-reports/r." + "a" * 64 + ".md",
    "report_sha256": "a" * 64,
    "reopened_at": None,
}
_SESSION_DONE = {
    "state": "completed",
    "completed_at": LATER,
    "profile_inputs": "changed",
    "profile_refreshed": True,
}
_ACCEPTED = {
    "clarification.state": "accepted",
    "clarification.offered_at": NOW,
    "clarification.resolved_at": NOW,
}


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"clarification": None}, "clarification must be an object"),
        ({"clarification.session": {}}, "session must be null in this state"),
        (_ACCEPTED, "clarification.session must be an object"),
        (
            {**_ACCEPTED, "clarification.session": {**_SESSION_DONE, "state": "done"}},
            "session.state 'done' is not one of the known values",
        ),
        (
            {**_ACCEPTED, "clarification.session": {**_SESSION_DONE, "state": []}},
            "session.state must be a string",
        ),
        (
            {
                **_ACCEPTED,
                "clarification.session": {**_SESSION_DONE, "profile_refreshed": 1},
            },
            "session.profile_refreshed must be a boolean",
        ),
        (
            {
                **_ACCEPTED,
                "clarification.session": {**_SESSION_DONE, "profile_inputs": None},
            },
            "session.profile_inputs must be a string",
        ),
        ({"clarification.state": {}}, "clarification.state must be a string"),
        ({"clarification.offer_mode": []}, "clarification.offer_mode must be a string"),
        ({"clarification.state": "offered"}, "offered_at must be set in this state"),
        ({"clarification.offered_at": NOW}, "offered_at must be null in this state"),
        (
            {"clarification.state": "declined", "clarification.offered_at": NOW},
            "resolved_at must be set in this state",
        ),
        (
            {
                "clarification.state": "deferred",
                "clarification.offered_at": NOW,
                "clarification.resolved_at": NOW,
            },
            "return_condition must name when to raise",
        ),
        (
            {
                "clarification.state": "deferred",
                "clarification.offered_at": NOW,
                "clarification.resolved_at": NOW,
                "clarification.return_condition": "  ",
            },
            "return_condition must name when to raise",
        ),
        ({"clarification.return_condition": "soon"}, "return_condition must be null"),
        ({"clarification.offered_at": "2026-09-14"}, "must be null in this state"),
        (
            {"clarification.recency_as_of": "yesterday"},
            "recency_as_of 'yesterday' is malformed",
        ),
        ({"end_report.state": ["delivered"]}, "end_report.state must be a string"),
        ({"end_report.state": "delivered"}, "delivered_at must be set in this state"),
        (
            {"end_report": {**_DELIVERED, "report_sha256": "nope"}},
            "report_sha256 must be a hex SHA-256",
        ),
        ({"end_report": _DELIVERED}, "completed_at must be set in this state"),
        (
            {"end_report": _DELIVERED, "completed_at": LATER},
            "delivered while the offer has no answer",
        ),
        (
            {
                "end_report": _DELIVERED,
                "completed_at": LATER,
                "clarification.state": "declined",
                "clarification.offered_at": NOW,
                "clarification.resolved_at": NOW,
                "downstream": {"state": "owed", "completed_at": None},
            },
            "delivered while downstream is owed",
        ),
        (
            {
                "end_report": _DELIVERED,
                "completed_at": MUCH_LATER,
                "clarification.state": "declined",
                "clarification.offered_at": NOW,
                "clarification.resolved_at": NOW,
            },
            "completed_at must equal end_report.delivered_at",
        ),
        ({"talks.0.claim_batch_id": ""}, "claim_batch_id must be a non-empty string"),
        ({"talks.0.claim_generation": -1}, "claim_generation must be a non-negative"),
        ({"talks.0.claim_generation": "1"}, "claim_generation must be a non-negative"),
        ({"completed_at": LATER}, "completed_at must be null in this state"),
        (
            {"schema_version": 2},
            "run-record schema_version 2; this script reads 1 only",
        ),
        ({"schema_version": "1"}, "run-record schema_version '1'"),
        ({"run_id": "r 1"}, "contains whitespace"),
        ({"run_id": ""}, "must be a non-empty string"),
        ({"opened_at": "Monday"}, "opened_at 'Monday' is malformed"),
        ({"opened_at": "0001-01-01T00:00:00+01:00"}, "is out of range once normalized"),
        ({"updated_at": 5}, "updated_at must be a non-empty ISO-8601 timestamp"),
        (
            {"downstream": {"state": "done", "completed_at": None}},
            "downstream.state 'done'",
        ),
        (
            {"downstream": {"state": "owed", "completed_at": NOW}},
            "downstream.completed_at must be null",
        ),
        (
            {"downstream": {"state": "completed", "completed_at": None}},
            "downstream.completed_at must be set",
        ),
        ({"clarification.topics": "bilingual"}, "topics must be an array of strings"),
        (
            {"clarification.offer_mode": "loud"},
            "offer_mode 'loud' is not one of the known values",
        ),
        ({"end_report": {"state": "sent"}}, "end_report lacks delivered_at"),
        ({"talks": [{"filename": "a.md"}]}, "talks[0] lacks status"),
        ({"talks.0.status": []}, "talks[0] status must be a non-empty string"),
        (
            {"talks.0.recency_bucket": "soon"},
            "recency_bucket 'soon' is not one of the known values",
        ),
        ({"talks.0.recency_bucket": []}, "recency_bucket must be a string"),
        (
            {"talks.0.days_since_delivery": True},
            "days_since_delivery must be an integer or null",
        ),
        (
            {"talks.0.delivery_date": "last week"},
            "delivery_date must be a YYYY-MM-DD string or null",
        ),
        ({"talks.0.claim_run_id": "run 1"}, "claim_run_id 'run 1' contains whitespace"),
        (
            {"talks.0.delivery_date": 123},
            "delivery_date must be a YYYY-MM-DD string or null",
        ),
        ({"completed_at": 1}, "completed_at must be null in this state"),
        ({"talks.0.claim_run_id": None}, "claim_run_id must be a non-empty string"),
        (
            {"talks.0.claim_released_at": "2026-09-01T02:00:00+02:00"},
            "must be the canonical UTC form '2026-09-01T00:00:00+00:00'",
        ),
        (
            {"opened_at": "2026-09-14T13:00:00+01:00"},
            "opened_at '2026-09-14T13:00:00+01:00' must be the canonical UTC form",
        ),
        ({"end_report.reopened_at": "later"}, "reopened_at 'later' is malformed"),
    ],
    ids=[
        "clarification-null",
        "session-on-unaccepted",
        "session-missing",
        "session-state",
        "session-state-list",
        "session-refreshed-int",
        "session-inputs-null-when-done",
        "state-object",
        "offer-mode-list",
        "offered-needs-stamp",
        "owed-stamp-must-be-null",
        "declined-needs-resolved",
        "deferred-needs-condition",
        "deferred-blank-condition",
        "condition-on-owed",
        "stamp-on-owed",
        "recency-malformed",
        "report-state-list",
        "delivered-needs-stamp",
        "report-digest",
        "delivered-needs-completed",
        "delivered-without-answer",
        "delivered-without-downstream",
        "completed-differs-from-delivered",
        "claim-batch-empty",
        "claim-generation-negative",
        "claim-generation-string",
        "completed-on-owed",
        "run-version-newer",
        "run-version-string",
        "run-id-whitespace",
        "run-id-empty",
        "opened-malformed",
        "opened-overflow",
        "updated-type",
        "downstream-state",
        "downstream-stamp-on-owed",
        "downstream-needs-stamp",
        "topics-type",
        "offer-mode",
        "report-keys",
        "talk-keys",
        "talk-status-list",
        "talk-bucket",
        "talk-bucket-list",
        "talk-days-bool",
        "talk-date",
        "talk-claim-id",
        "talk-date-number",
        "completed-type",
        "talk-claim-id-null",
        "talk-claim-released-noncanonical",
        "opened-noncanonical",
        "reopened-malformed",
    ],
)
def test_every_malformed_ledger_field_fails_structured(
    tmp_path, fresh_db, overrides, detail
):
    run = _valid_run()
    _apply_overrides(run, overrides)
    (tmp_path / "ingress-obligations.json").write_text(
        json.dumps({**ENVELOPE, "runs": [run]}), encoding="utf-8"
    )
    for command in (
        ["pending"],
        ["status", "--run-id", "r"],
        ["record-offer", "--run-id", "r", "--now", NOW],
    ):
        payload = _refused(fresh_db, *command)
        assert payload["reason_code"] == "ledger_invalid"
        assert detail in payload["error"]


@pytest.mark.parametrize(
    "run",
    [
        _valid_run(),
        _valid_run(
            **{
                "clarification.state": "deferred",
                "clarification.offered_at": NOW,
                "clarification.resolved_at": NOW,
                "clarification.return_condition": "after JavaZone",
                "end_report": _DELIVERED,
                "completed_at": LATER,
            }
        ),
        _valid_run(**{**_ACCEPTED, "clarification.session": _SESSION_DONE}),
        _valid_run(downstream={"state": "owed", "completed_at": None}),
    ],
    ids=["owed", "deferred-delivered", "accepted-completed", "downstream-owed"],
)
def test_a_well_formed_hand_written_ledger_is_accepted(tmp_path, fresh_db, run):
    (tmp_path / "ingress-obligations.json").write_text(
        json.dumps({**ENVELOPE, "runs": [run]}), encoding="utf-8"
    )
    assert _ok(fresh_db, "pending")["ok"] is True
    assert _ok(fresh_db, "status", "--run-id", "r")["run"] == run


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
    assert run_obligations.RUN_RECORD_SCHEMA_VERSION == 1


# ── replays are unchanged successes ───────────────────────────────────


def test_a_replayed_offer_is_an_unchanged_success_and_a_changed_one_a_conflict(
    fresh_db,
):
    run_id = _opened(fresh_db)
    first = _ok(
        fresh_db, "record-offer", "--run-id", run_id, "--now", NOW, "--topic", "aside"
    )
    replay = _ok(
        fresh_db, "record-offer", "--run-id", run_id, "--now", LATER, "--topic", "aside"
    )
    assert replay["offered"] is True
    assert replay["replayed"] is True
    assert replay["written"] is False
    assert replay["run"] == first["run"]
    conflict = _refused(
        fresh_db, "record-offer", "--run-id", run_id, "--now", LATER, "--topic", "other"
    )
    assert conflict["reason_code"] == "invalid_transition"
    assert "different offer" in conflict["error"]


def test_a_replayed_withdrawn_offer_stays_withdrawn(tmp_path):
    database = _write_db(tmp_path, [_talk("fresh.md")])
    _adopt(database)
    _opened(database, "run-w")
    requeued = _talk("fresh.md", status="needs-reprocessing", claim=None)
    requeued["reprocess_generation"] = 1
    requeued["_queue_claim_history"] = [_persisted_claim(SEED_RUN, SEED_RELEASED)]
    _write_db(tmp_path, [requeued])
    _ok(database, "record-offer", "--run-id", "run-w", "--now", LATER)
    replay = _ok(database, "record-offer", "--run-id", "run-w", "--now", MUCH_LATER)
    assert replay["offered"] is False
    assert replay["replayed"] is True
    assert replay["written"] is False


@pytest.mark.parametrize(
    ("disposition", "extra"),
    [
        ("declined", []),
        ("accepted", []),
        ("deferred", ["--return-condition", "after JavaZone"]),
    ],
)
def test_a_replayed_disposition_changes_nothing(fresh_db, disposition, extra):
    run_id = _opened(fresh_db)
    _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW)
    first = _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--disposition",
        disposition,
        *extra,
    )
    replay = _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--disposition",
        disposition,
        *extra,
    )
    assert replay["replayed"] is True
    assert replay["written"] is False
    assert replay["run"] == first["run"]


def test_a_replayed_acceptance_never_resets_a_completed_session(fresh_db):
    run_id = _accepted(fresh_db)
    _ok(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--profile-inputs",
        "unchanged",
    )
    replay = _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--disposition",
        "accepted",
    )
    assert replay["replayed"] is True
    assert replay["run"]["clarification"]["session"]["state"] == "completed"
    conflict = _refused(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--disposition",
        "declined",
    )
    assert conflict["reason_code"] == "invalid_transition"
    assert "different disposition" in conflict["error"]


def test_a_replayed_session_completion_keeps_its_first_timestamp(fresh_db):
    run_id = _accepted(fresh_db)
    first = _ok(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--profile-inputs",
        "unchanged",
    )
    replay = _ok(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--profile-inputs",
        "unchanged",
    )
    assert replay["replayed"] is True
    assert replay["written"] is False
    assert replay["run"] == first["run"]
    assert replay["run"]["clarification"]["session"]["completed_at"] == LATER
    conflict = _refused(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--profile-inputs",
        "changed",
        "--profile-refreshed",
    )
    assert conflict["reason_code"] == "invalid_transition"
    assert "different session completion" in conflict["error"]


def test_a_replayed_open_never_touches_a_frozen_snapshot(fresh_db):
    run_id = _opened(fresh_db, "run-frozen")
    offered = _ok(fresh_db, "record-offer", "--run-id", run_id, "--now", NOW)["run"]
    replay = _open(fresh_db, run_id, "fresh.md", now=MUCH_LATER)
    assert replay["written"] is False
    assert replay["run"] == offered


# ── a session after the report reopens it ─────────────────────────────


def test_a_session_accepted_after_delivery_that_changed_inputs_reopens_the_report(
    tmp_path, fresh_db
):
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
        "deferred",
        "--return-condition",
        "after JavaZone",
    )
    first = _record_report(fresh_db, run_id, _report(tmp_path))
    assert first["run"]["completed_at"] == LATER
    _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--disposition",
        "accepted",
    )
    done = _ok(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--profile-inputs",
        "changed",
    )
    assert done["report_reopened"] is True
    assert done["run"]["end_report"] == {
        "state": "owed",
        "delivered_at": None,
        "report_path": None,
        "report_sha256": None,
        "reopened_at": MUCH_LATER,
    }
    assert done["run"]["completed_at"] is None
    assert _ok(fresh_db, "pending")["pending"][0]["next_action"] == "deliver_end_report"
    again = _record_report(
        fresh_db, run_id, _report(tmp_path, "# after the session\n"), now=MUCH_LATER
    )
    assert again["run"]["completed_at"] == MUCH_LATER
    assert again["run"]["end_report"]["reopened_at"] == MUCH_LATER
    assert _ok(fresh_db, "pending")["pending"] == []


def test_a_late_session_with_unchanged_inputs_leaves_the_report_delivered(
    tmp_path, fresh_db
):
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
        "deferred",
        "--return-condition",
        "after JavaZone",
    )
    _record_report(fresh_db, run_id, _report(tmp_path))
    _ok(
        fresh_db,
        "record-disposition",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--disposition",
        "accepted",
    )
    done = _ok(
        fresh_db,
        "record-session",
        "--run-id",
        run_id,
        "--now",
        MUCH_LATER,
        "--profile-inputs",
        "unchanged",
    )
    assert "report_reopened" not in done
    assert done["run"]["end_report"]["state"] == "delivered"
    assert done["run"]["completed_at"] == LATER


# ── a talk merged again under the same run ────────────────────────────


def test_a_talk_merged_again_under_the_same_run_is_a_new_fact(tmp_path):
    first_release = "2026-09-13T10:00:00+00:00"
    second_release = "2026-09-13T12:00:00+00:00"
    database = _db_with_claims(tmp_path, {"a.md": ("run-again", first_release)})
    _opened(database, "run-again", "a.md")
    assert _ok(database, "pending")["open_required"] == []
    talk = _talk(
        "a.md", claim=_persisted_claim("run-again", second_release, batch_id="b2")
    )
    talk["_queue_claim_history"] = [_persisted_claim("run-again", first_release)]
    _write_db(tmp_path, [talk])
    payload = _ok(database, "pending")
    assert payload["open_required"] == [
        {
            "run_id": "run-again",
            "talks": ["a.md"],
            "latest_released_at": second_release,
            "reason": "missing_talks",
            "next_action": "open_obligations",
        }
    ]
    reopened = _open(database, "run-again", "a.md", now=LATER)
    assert reopened["run"]["talks"][0]["claim_released_at"] == second_release
    assert reopened["run"]["downstream"] == {"state": "owed", "completed_at": None}
    assert _ok(database, "pending")["open_required"] == []


# ── more inputs that fail closed ──────────────────────────────────────


def test_a_directory_at_the_copy_target_is_refused(tmp_path, fresh_db):
    run_id = _declined(fresh_db)
    report = _report(tmp_path)
    _copy_path(tmp_path, run_id, report.read_bytes()).mkdir(parents=True)
    payload = _refused(
        fresh_db,
        "record-report",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--report-file",
        str(report),
    )
    assert payload["reason_code"] == "report_copy_failed"
    assert "not a regular file" in payload["error"]


def test_a_database_asserting_another_vault_root_fails_closed(tmp_path):
    database = _write_db(tmp_path, [_talk("fresh.md")])
    payload = json.loads(database.read_text(encoding="utf-8"))
    payload["config"]["vault_storage_path"] = str(tmp_path / "elsewhere")
    database.write_text(json.dumps(payload), encoding="utf-8")
    code, result, stderr = _run(database, "pending")
    assert code == 2
    assert result is not None and result["ok"] is False
    assert result["error"] in stderr
    assert isinstance(result["reason_code"], str) and result["reason_code"]


# ── recovery names the exact persisted fact ───────────────────────────


def test_recovery_after_another_run_reprocessed_the_talk_links_the_right_claim(
    tmp_path,
):
    first_release = "2026-09-13T10:00:00+00:00"
    later_release = "2026-09-14T10:00:00+00:00"
    database = _db_with_claims(tmp_path, {"a.md": ("run-a", first_release)})
    _opened(database, "run-a", "a.md")
    _ok(database, "record-offer", "--run-id", "run-a", "--now", NOW)
    _ok(
        database,
        "record-disposition",
        "--run-id",
        "run-a",
        "--now",
        NOW,
        "--disposition",
        "declined",
    )
    _record_report(database, "run-a", _report(tmp_path))
    # run-a's report is out; then run-a merges a.md once more (a late batch),
    # and run-b reprocesses the same talk afterwards.
    talk = _talk("a.md", claim=_persisted_claim("run-b", later_release, batch_id="b3"))
    talk["_queue_claim_history"] = [
        _persisted_claim("run-a", first_release),
        _persisted_claim("run-a", "2026-09-13T12:00:00+00:00", batch_id="b2"),
    ]
    _write_db(tmp_path, [talk])
    listed = _ok(database, "pending")["open_required"]
    assert [(entry["run_id"], entry["reason"]) for entry in listed] == [
        ("run-a", "talks_persisted_after_completion"),
        ("run-b", "unrecorded_run"),
    ]
    wrong = _refused(
        database,
        "open",
        "--run-id",
        "run-a-recovery",
        "--now",
        MUCH_LATER,
        "--talk",
        "a.md",
        "--from-run",
        "run-zzz",
    )
    assert wrong["reason_code"] == "talk_not_persisted"
    recovered = _ok(
        database,
        "open",
        "--run-id",
        "run-a-recovery",
        "--now",
        MUCH_LATER,
        "--talk",
        "a.md",
        "--from-run",
        "run-a",
    )["run"]
    assert recovered["talks"][0]["claim_run_id"] == "run-a"
    assert recovered["talks"][0]["claim_released_at"] == "2026-09-13T12:00:00+00:00"
    listed = _ok(database, "pending")["open_required"]
    assert [(entry["run_id"], entry["reason"]) for entry in listed] == [
        ("run-b", "unrecorded_run")
    ]
    # A recency refresh keeps the recovered link instead of re-picking run-b.
    _downstream(database, "run-a-recovery", now=MUCH_LATER)
    offered = _ok(
        database, "record-offer", "--run-id", "run-a-recovery", "--now", MUCH_LATER
    )["run"]
    assert offered["talks"][0]["claim_run_id"] == "run-a"
    assert _ok(database, "pending")["open_required"] == listed


def test_a_fifo_as_the_report_file_is_refused_not_read(tmp_path, fresh_db):
    run_id = _declined(fresh_db)
    fifo = tmp_path / "report.fifo"
    os.mkfifo(fifo)
    payload = _refused(
        fresh_db,
        "record-report",
        "--run-id",
        run_id,
        "--now",
        LATER,
        "--report-file",
        str(fifo),
    )
    assert payload["reason_code"] == "report_unreadable"
    assert "regular file" in payload["error"]


def test_a_read_failure_on_an_existing_copy_is_the_structured_failure(
    tmp_path, run_obligations, monkeypatch
):
    directory = tmp_path / "ingress-reports"
    directory.mkdir()
    content = b"# report\n"
    digest = hashlib.sha256(content).hexdigest()
    (directory / f"run-x.{digest}.md").write_bytes(content)
    real_read = os.read

    def failing_read(descriptor, size):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(run_obligations.os, "read", failing_read)
    with pytest.raises(run_obligations.RunObligationsError) as caught:
        run_obligations.write_report_copy(directory, "run-x", digest, content)
    monkeypatch.setattr(run_obligations.os, "read", real_read)
    assert caught.value.reason_code == "report_copy_failed"
    assert "could not be read" in str(caught.value)
    assert (directory / f"run-x.{digest}.md").read_bytes() == content
    assert sorted(path.name for path in directory.iterdir()) == [f"run-x.{digest}.md"]


def test_two_batches_released_in_the_same_second_are_distinct_facts(tmp_path):
    release = "2026-09-13T10:00:00+00:00"
    database = _db_with_claims(tmp_path, {"a.md": ("run-same-second", release)})
    _opened(database, "run-same-second", "a.md")
    assert _ok(database, "pending")["open_required"] == []
    # The queue gives every re-claim of a talk its own generation; only the
    # release second is shared.
    second = {
        **_persisted_claim("run-same-second", release, batch_id="b2"),
        "reprocess_generation": 2,
    }
    talk = _talk("a.md", claim=second)
    talk["reprocess_generation"] = 2
    talk["_queue_claim_history"] = [_persisted_claim("run-same-second", release)]
    _write_db(tmp_path, [talk])
    listed = _ok(database, "pending")["open_required"]
    assert [(entry["run_id"], entry["talks"], entry["reason"]) for entry in listed] == [
        ("run-same-second", ["a.md"], "missing_talks")
    ]
    reopened = _open(database, "run-same-second", "a.md", now=LATER)["run"]
    assert reopened["talks"][0]["claim_batch_id"] == "b2"
    assert reopened["talks"][0]["claim_generation"] == 2
    assert reopened["downstream"] == {"state": "owed", "completed_at": None}
    assert _ok(database, "pending")["open_required"] == []


def test_a_run_answered_but_unreported_sends_late_talks_to_a_fresh_run(tmp_path):
    database = _db_with_claims(
        tmp_path,
        {
            "a.md": ("run-answered", "2026-09-13T10:00:00+00:00"),
            "b.md": ("run-answered", "2026-09-13T11:00:00+00:00"),
        },
    )
    _opened(database, "run-answered", "a.md")
    _ok(database, "record-offer", "--run-id", "run-answered", "--now", NOW)
    _ok(
        database,
        "record-disposition",
        "--run-id",
        "run-answered",
        "--now",
        NOW,
        "--disposition",
        "declined",
    )
    listed = _ok(database, "pending")["open_required"]
    assert listed == [
        {
            "run_id": "run-answered",
            "talks": ["b.md"],
            "latest_released_at": "2026-09-13T11:00:00+00:00",
            "reason": "talks_persisted_after_answer",
            "next_action": "open_obligations",
        }
    ]
    refused = _refused(
        database, "open", "--run-id", "run-answered", "--now", LATER, "--talk", "b.md"
    )
    assert refused["reason_code"] == "invalid_transition"
    recovered = _ok(
        database,
        "open",
        "--run-id",
        "run-answered-late",
        "--now",
        LATER,
        "--talk",
        "b.md",
        "--from-run",
        "run-answered",
    )["run"]
    assert recovered["talks"][0]["claim_run_id"] == "run-answered"
    assert _ok(database, "pending")["open_required"] == []


def test_a_dismissal_covers_only_the_facts_that_existed_when_it_was_recorded(tmp_path):
    database = _db_with_claims(
        tmp_path, {"a.md": ("gone-run", "2026-09-10T00:00:00+00:00")}
    )
    _ok(
        database,
        "dismiss",
        "--run-id",
        "gone-run",
        "--now",
        NOW,
        "--reason",
        "abandoned",
    )
    assert _ok(database, "pending")["open_required"] == []
    # The next batch closes at the very second of the dismissal, with a later
    # generation: an exact identity the dismissal never named, so it is listed.
    later = {
        **_persisted_claim("gone-run", NOW, batch_id="b9"),
        "reprocess_generation": 2,
    }
    talk = _talk("a.md", claim=later)
    talk["reprocess_generation"] = 2
    talk["_queue_claim_history"] = [
        _persisted_claim("gone-run", "2026-09-10T00:00:00+00:00")
    ]
    _write_db(tmp_path, [talk])
    listed = _ok(database, "pending")["open_required"]
    assert [(entry["run_id"], entry["talks"], entry["reason"]) for entry in listed] == [
        ("gone-run", ["a.md"], "unrecorded_run")
    ]
    # Dismissing again, with the same or another reason, renews the entry to
    # cover the facts that appeared since; a replay only counts when nothing
    # new is listed.
    renewed = _ok(
        database,
        "dismiss",
        "--run-id",
        "gone-run",
        "--now",
        MUCH_LATER,
        "--reason",
        "abandoned",
    )
    assert renewed["renewed"] is True
    assert renewed["written"] is True
    assert renewed["dismissed"] == {
        "run_id": "gone-run",
        "dismissed_at": MUCH_LATER,
        "reason": "abandoned",
        "facts": [
            _identity("gone-run", "a.md", "2026-09-10T00:00:00+00:00"),
            _identity("gone-run", "a.md", NOW, batch_id="b9", generation=2),
        ],
    }
    assert _ok(database, "pending")["open_required"] == []
    assert len(_ledger(tmp_path)["dismissed_runs"]) == 1
    replay = _ok(
        database,
        "dismiss",
        "--run-id",
        "gone-run",
        "--now",
        MUCH_LATER,
        "--reason",
        "abandoned",
    )
    assert replay["replayed"] is True


def test_a_long_run_id_still_gets_its_report_copy(tmp_path, fresh_db):
    run_id = "reparse-" + "x" * 300
    _declined(fresh_db, run_id)
    report = _report(tmp_path)
    payload = _record_report(fresh_db, run_id, report)
    copied = Path(payload["run"]["end_report"]["report_path"])
    assert copied == _copy_path(tmp_path, run_id, report.read_bytes())
    assert len(copied.name) < 120
    assert copied.read_bytes() == report.read_bytes()


def test_a_batch_stamped_before_adoption_but_closed_after_it_is_still_listed(
    tmp_path,
):
    # persist-results.py --run-date stamps midnight; a batch merged after the
    # noon adoption still carries a morning release time. Identity, not time,
    # decides what is history.
    database = _write_db(tmp_path, [_talk("a.md", claim=None)])
    _adopt(database, now="2026-09-13T12:00:00+00:00")
    _write_db(
        tmp_path,
        [_talk("a.md", claim=_persisted_claim("day-run", "2026-09-13T00:00:00+00:00"))],
    )
    listed = _ok(database, "pending")["open_required"]
    assert [(entry["run_id"], entry["reason"]) for entry in listed] == [
        ("day-run", "unrecorded_run")
    ]


def test_open_reads_the_persisted_filenames_from_a_file(tmp_path, fresh_db):
    listing = tmp_path / "persisted.txt"
    listing.write_text("fresh.md\n\n  older.md  \n", encoding="utf-8")
    run = _ok(
        fresh_db,
        "open",
        "--run-id",
        "run-file",
        "--now",
        NOW,
        "--talks-from",
        str(listing),
        "--talk",
        "skipped.md",
    )["run"]
    assert [talk["filename"] for talk in run["talks"]] == [
        "fresh.md",
        "older.md",
        "skipped.md",
    ]
    missing = _refused(
        fresh_db,
        "open",
        "--run-id",
        "run-file",
        "--now",
        NOW,
        "--talks-from",
        str(tmp_path / "absent.txt"),
    )
    assert missing["reason_code"] == "invalid_arguments"
    empty = tmp_path / "empty.txt"
    empty.write_text("\n", encoding="utf-8")
    nothing = _refused(
        fresh_db,
        "open",
        "--run-id",
        "run-file",
        "--now",
        NOW,
        "--talks-from",
        str(empty),
    )
    assert nothing["reason_code"] == "invalid_arguments"
