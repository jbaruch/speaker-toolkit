"""Offline tests for the ceiling establisher (#430).

Every database is built in-test from fixed literals, and `established_at` is
always passed explicitly, so a run today and a run next year agree.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from conftest import CURRENT_ROOT_SCHEMA_VERSION as CURRENT_ROOT
from conftest import current_tracking_config
import pytest


# Two fixed past stamps. A later run only needs a different stamp, and a
# future literal would rot as the run date advances.
AS_OF = "2026-01-05T00:00:00Z"
SECOND_RUN = "2026-02-09T00:00:00Z"


def _talk(
    filename: str,
    *,
    date: object = "",
    upload_date: str | None = "2016-01-21",
    **updates: object,
):
    talk = {
        "filename": filename,
        "title": "A Talk",
        "conference": "ExampleConf",
        "date": date,
        "status": "processed",
        "schema_version": 8,
        "youtube_id": "AbCdEfGhI_1",
    }
    if upload_date is not None:
        talk["source_identity"] = {
            "schema_version": 1,
            "provider": "youtube",
            "video_id": "AbCdEfGhI_1",
            "upload_date": upload_date,
            "captured_at": "2026-08-18T19:55:38Z",
        }
    talk.update(updates)
    return talk


def _database(talks, provenance=None):
    database = {
        "schema_version": CURRENT_ROOT,
        "config": current_tracking_config(),
        "talks": talks,
        "pptx_catalog": [],
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }
    if provenance is not None:
        database["date_provenance"] = provenance
    return database


def _write(tmp_path: Path, database) -> tuple[Path, str]:
    path = tmp_path / "tracking-database.json"
    raw = json.dumps(database, indent=2, ensure_ascii=False).encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def test_a_dateless_talk_with_a_stored_upload_gets_a_ceiling(
    establish_date_provenance,
):
    plan = establish_date_provenance.plan_ceilings(
        _database([_talk("dateless.md")]), established_at=AS_OF
    )

    assert [record["talk_filename"] for record in plan["proposals"]] == ["dateless.md"]
    record = plan["proposals"][0]
    assert record["method"] == "provider_upload_ceiling"
    assert record["not_later_than"] == "2016-01-21"
    assert record["established_at"] == AS_OF
    assert "2016-01-21" in record["evidence"]
    assert plan["blocked"] == []


@pytest.mark.parametrize(
    "talk,reason",
    [
        (_talk("dated.md", date="2016-03-04"), "date_already_comparable"),
        (_talk("year.md", date="2016"), "date_already_comparable"),
        (_talk("month.md", date="2016-03"), "date_present_but_uncomparable"),
        (_talk("junk.md", date="spring 2016"), "date_present_but_uncomparable"),
        (_talk("nosource.md", upload_date=None), "no_provider_upload_date"),
        (_talk("badupload.md", upload_date="20160121"), "no_provider_upload_date"),
    ],
)
def test_every_refusal_is_named_rather_than_silently_skipped(
    establish_date_provenance, talk, reason
):
    plan = establish_date_provenance.plan_ceilings(
        _database([talk]), established_at=AS_OF
    )

    assert plan["proposals"] == []
    assert plan["blocked"] == [{"talk_filename": talk["filename"], "reason": reason}]
    assert plan["coverage"]["blocked_by_reason"][reason] == 1


def test_a_talk_that_already_has_provenance_is_left_alone(establish_date_provenance):
    """One record per talk: a second run must not displace the first account."""
    existing = {
        "schema_version": 1,
        "talk_filename": "dateless.md",
        "method": "organizer_program",
        "evidence": "published schedule",
        "established_at": AS_OF,
    }
    plan = establish_date_provenance.plan_ceilings(
        _database([_talk("dateless.md")], [existing]), established_at=AS_OF
    )

    assert plan["proposals"] == []
    assert plan["blocked"] == [
        {"talk_filename": "dateless.md", "reason": "provenance_already_recorded"}
    ]


def test_coverage_makes_backlog_progress_measurable(establish_date_provenance):
    database = _database(
        [
            _talk("a.md", date="2016-03-04"),
            _talk("b.md", date="2016"),
            _talk("c.md"),
            _talk("d.md"),
            _talk("e.md", date="2016-03"),
            _talk("f.md", upload_date=None),
        ]
    )

    plan = establish_date_provenance.plan_ceilings(database, established_at=AS_OF)

    assert plan["coverage"] == {
        "talks": 6,
        "with_comparable_date": 2,
        "with_provenance_before": 0,
        "with_provenance_after": 2,
        "blocked_by_reason": {
            "date_already_comparable": 2,
            "date_present_but_uncomparable": 1,
            "provenance_already_recorded": 0,
            "no_provider_upload_date": 1,
        },
    }


def test_a_dry_run_writes_nothing_and_an_apply_writes_once(
    establish_date_provenance, tmp_path
):
    database = _database([_talk("dateless.md"), _talk("dated.md", date="2016-03-04")])
    path, digest = _write(tmp_path, database)

    preview = establish_date_provenance.execute(
        path, apply=False, expected_sha256=None, as_of=AS_OF
    )

    assert preview["mode"] == "dry-run"
    assert preview["changed"] is True
    assert preview["database_written"] is False
    assert json.loads(path.read_bytes()) == database

    applied = establish_date_provenance.execute(
        path, apply=True, expected_sha256=digest, as_of=AS_OF
    )

    assert applied["database_written"] is True
    assert applied["output_sha256"] == preview["output_sha256"]
    written = json.loads(path.read_bytes())
    assert [r["talk_filename"] for r in written["date_provenance"]] == ["dateless.md"]
    assert written["talks"] == database["talks"], "a ceiling never edits a talk"


def test_a_second_apply_is_a_no_op(establish_date_provenance, tmp_path):
    """Repeatable: progress accumulates instead of restarting each run."""
    path, digest = _write(tmp_path, _database([_talk("dateless.md")]))
    establish_date_provenance.execute(
        path, apply=True, expected_sha256=digest, as_of=AS_OF
    )
    after_first = path.read_bytes()

    again = establish_date_provenance.execute(
        path,
        apply=True,
        expected_sha256=hashlib.sha256(after_first).hexdigest(),
        as_of=SECOND_RUN,
    )

    assert again["changed"] is False
    assert again["proposals"] == []
    assert path.read_bytes() == after_first


def test_apply_requires_the_digest_from_a_dry_run(establish_date_provenance, tmp_path):
    path, digest = _write(tmp_path, _database([_talk("dateless.md")]))

    with pytest.raises(establish_date_provenance.DateProvenanceError, match="requires"):
        establish_date_provenance.execute(
            path, apply=True, expected_sha256=None, as_of=AS_OF
        )

    stale = hashlib.sha256(b"something else").hexdigest()
    with pytest.raises(
        establish_date_provenance.DateProvenanceError, match="precondition failed"
    ):
        establish_date_provenance.execute(
            path, apply=True, expected_sha256=stale, as_of=AS_OF
        )
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_legacy_root_refuses_with_the_repair_named(
    establish_date_provenance, tmp_path
):
    database = _database([_talk("dateless.md")])
    database["schema_version"] = 1
    path, _digest = _write(tmp_path, database)

    with pytest.raises(
        establish_date_provenance.DateProvenanceError, match="migrate the tracking"
    ):
        establish_date_provenance.execute(
            path, apply=False, expected_sha256=None, as_of=AS_OF
        )


def test_the_written_records_survive_the_readers_own_validation(
    establish_date_provenance, tracking_database, tmp_path
):
    path, digest = _write(tmp_path, _database([_talk("dateless.md")]))
    establish_date_provenance.execute(
        path, apply=True, expected_sha256=digest, as_of=AS_OF
    )

    written = json.loads(path.read_bytes())

    assert tracking_database.assess_tracking_database(written).state == "current"


def test_a_malformed_talk_refuses_rather_than_being_skipped(
    establish_date_provenance,
):
    database = _database([_talk("ok.md")])
    database["talks"].append({"title": "no filename"})

    with pytest.raises(
        establish_date_provenance.DateProvenanceError, match="no usable filename"
    ):
        establish_date_provenance.plan_ceilings(database, established_at=AS_OF)


@pytest.mark.parametrize("value", ["not-a-time", "2026-09-08T00:00:00", "2026-09-08"])
def test_a_naive_or_malformed_as_of_refuses(establish_date_provenance, value):
    with pytest.raises(
        establish_date_provenance.DateProvenanceError, match="timezone-aware"
    ):
        establish_date_provenance._validate_as_of(value)


def test_the_cli_reports_a_refusal_as_json_and_exits_one(
    establish_date_provenance, tmp_path, capsys
):
    database = _database([_talk("dateless.md")])
    database["schema_version"] = 1
    path, _digest = _write(tmp_path, database)

    with pytest.raises(SystemExit) as exc:
        establish_date_provenance.main([str(path)])

    assert exc.value.code == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["ok"] is False
    assert "migrate the tracking" in report["error"]
    # stdout stays the report; the diagnostic also has to reach stderr.
    assert "establish-date-provenance failed" in captured.err
    assert "migrate the tracking" in captured.err


def test_the_cli_prints_a_plan_and_exits_zero(
    establish_date_provenance, tmp_path, capsys
):
    path, _digest = _write(tmp_path, _database([_talk("dateless.md")]))

    assert establish_date_provenance.main([str(path), "--as-of", AS_OF]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    assert report["mode"] == "dry-run"
    assert len(report["proposals"]) == 1
    assert report["established_at"] == AS_OF


def test_the_plan_never_mutates_the_database_it_reads(establish_date_provenance):
    database = _database([_talk("dateless.md")])
    before = copy.deepcopy(database)

    establish_date_provenance.plan_ceilings(database, established_at=AS_OF)

    assert database == before
