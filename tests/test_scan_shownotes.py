"""Tests for deterministic shownotes discovery and guarded DB import."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from conftest import CURRENT_ROOT_SCHEMA_VERSION, current_tracking_config


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "vault-ingress" / "scripts" / "scan-shownotes.py"
SCRIPT_DIRECTORY = SCRIPT.parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

# Talk-record fixtures track the current schema rather than pinning a literal:
# a pin makes every fixture in this module unmutatable the moment the talk
# record shape advances, which surfaces as "must be exact current talk schema"
# on tests that are about something else entirely.
CURRENT_TALK_SCHEMA = importlib.import_module(
    "tracking_database"
).TALK_RECORD_SCHEMA_VERSION

SPEC = importlib.util.spec_from_file_location("scan_shownotes", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
scan_shownotes = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scan_shownotes
SPEC.loader.exec_module(scan_shownotes)


YOUTUBE_ID = "AbCdEfGhI_1"
DRIVE_ID = "1AbCdEfGhIjKlMn"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _local_config(site_root: Path, **source_overrides: object) -> dict[str, object]:
    source: dict[str, object] = {
        "type": "local_jekyll",
        "path_or_url": str(site_root),
        "talks_subdir": "_talks",
    }
    source.update(source_overrides)
    return {"shownotes": {"enabled": True, "source": source}}


def _database_path(
    tmp_path: Path,
    config: dict[str, object],
    *,
    talks: list[dict[str, object]] | None = None,
    legacy: bool = False,
) -> Path:
    path = tmp_path / "tracking-database.json"
    if legacy:
        database = {"config": config, "talks": talks or []}
    else:
        current_talks = []
        for talk in talks or []:
            current_talk = {**talk, "schema_version": CURRENT_TALK_SCHEMA}
            current_talk["source_rejections"] = [
                {**rejection, "schema_version": 1}
                for rejection in current_talk.get("source_rejections", [])
            ]
            current_talks.append(current_talk)
        database = {
            "schema_version": CURRENT_ROOT_SCHEMA_VERSION,
            "config": current_tracking_config(**config),
            "talks": current_talks,
            "pptx_catalog": [],
            "qr_codes": [],
            "resources": [],
            "thumbnails": [],
            "confirmed_intents": [],
            "improvement_goals": [],
        }
    _write_json(path, database)
    return path


def _shownotes_site(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "shownotes"
    talks = root / "_talks"
    talks.mkdir(parents=True)
    return root, talks


def _write_jekyll_talk(
    directory: Path,
    *,
    filename: str = "2026-08-01-deterministic-ingress.md",
    title: str = "Deterministic Ingress",
    conference: str | None = "TestConf",
    date: str = "2026-08-01",
    video_url: str | None = None,
    slides_url: str | None = None,
) -> Path:
    lines = ["---", "layout: talk", "---", f"# {title}"]
    if conference is not None:
        lines.append(f"**Conference:** {conference}")
    lines.append(f"**Date:** {date}")
    if slides_url is not None:
        lines.append(f"**Slides:** [View Slides]({slides_url})")
    if video_url is not None:
        lines.append(f"**Video:** [Watch Video]({video_url})")
    path = directory / filename
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_dry_run_parses_jekyll_links_and_derives_exact_source_ids(
    tmp_path: Path,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    video_url = f"https://www.youtube.com/watch?v={YOUTUBE_ID}"
    slides_url = f"https://drive.google.com/file/d/{DRIVE_ID}/view"
    _write_jekyll_talk(
        talks_directory,
        video_url=video_url,
        slides_url=slides_url,
    )
    database_path = _database_path(tmp_path, _local_config(site))
    before = database_path.read_bytes()

    report = scan_shownotes.execute(database_path, apply_requested=False)

    assert report["schema_version"] == scan_shownotes.REPORT_SCHEMA_VERSION
    assert report["ok"] is True
    assert report["mode"] == "dry-run"
    assert report["database_written"] is False
    assert report["input_sha256"] == hashlib.sha256(before).hexdigest()
    assert report["output_sha256"] == report["input_sha256"]
    assert report["durability_state"] == "dry_run"
    assert report["warnings"] == []
    assert report["mutation_count"] == 1
    assert report["counts"] == {
        "add": 1,
        "update": 0,
        "unchanged": 0,
        "review_required": 0,
    }
    entry = report["entries"][0]
    assert entry["disposition"] == "add"
    assert entry["proposal"] == {
        "filename": "2026-08-01-deterministic-ingress.md",
        "title": "Deterministic Ingress",
        "conference": "TestConf",
        "date": "2026-08-01",
        "video_url": video_url,
        "slides_url": slides_url,
        "youtube_id": YOUTUBE_ID,
        "google_drive_id": DRIVE_ID,
    }
    assert database_path.read_bytes() == before


def test_legacy_database_is_dry_run_only(tmp_path: Path) -> None:
    site, _ = _shownotes_site(tmp_path)
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        legacy=True,
    )
    before = database_path.read_bytes()

    scan_shownotes.execute(database_path, apply_requested=False)

    assert database_path.read_bytes() == before
    with pytest.raises(
        scan_shownotes.ShownotesScanError,
        match="migrate-tracking-database.py",
    ):
        scan_shownotes.execute(database_path, apply_requested=True)
    assert database_path.read_bytes() == before


def test_apply_adds_only_complete_proposal_and_preserves_file_mode(
    tmp_path: Path,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    _write_jekyll_talk(talks_directory)
    database_path = _database_path(tmp_path, _local_config(site))
    os.chmod(database_path, 0o640)

    report = scan_shownotes.execute(database_path, apply_requested=True)

    database = json.loads(database_path.read_text(encoding="utf-8"))
    assert database["talks"] == [
        {
            "filename": "2026-08-01-deterministic-ingress.md",
            "title": "Deterministic Ingress",
            "conference": "TestConf",
            "date": "2026-08-01",
            "schema_version": CURRENT_TALK_SCHEMA,
            "status": "pending",
        }
    ]
    assert report["database_written"] is True
    assert report["schema_version"] == scan_shownotes.REPORT_SCHEMA_VERSION
    assert report["input_sha256"] != report["output_sha256"]
    assert (
        report["output_sha256"]
        == hashlib.sha256(database_path.read_bytes()).hexdigest()
    )
    assert report["durability_state"] == "durable"
    assert report["entries"][0]["applied"] is True
    assert database_path.stat().st_mode & 0o777 == 0o640
    assert not list(tmp_path.glob(".*.shownotes.tmp"))


def test_exact_filename_update_fills_only_empty_fields(tmp_path: Path) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    video_url = f"https://youtu.be/{YOUTUBE_ID}"
    _write_jekyll_talk(talks_directory, video_url=video_url)
    existing = {
        "filename": "2026-08-01-deterministic-ingress.md",
        "title": "Deterministic Ingress",
        "conference": "TestConf",
        "date": "2026-08-01",
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "processed",
    }
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )

    report = scan_shownotes.execute(database_path, apply_requested=True)

    talk = json.loads(database_path.read_text(encoding="utf-8"))["talks"][0]
    assert talk["video_url"] == video_url
    assert talk["youtube_id"] == YOUTUBE_ID
    assert talk["schema_version"] == CURRENT_TALK_SCHEMA
    assert talk["status"] == "processed"
    assert report["entries"][0]["changes"] == {
        "video_url": video_url,
        "youtube_id": YOUTUBE_ID,
    }


def test_existing_metadata_conflict_stays_a_non_mutating_review_proposal(
    tmp_path: Path,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    _write_jekyll_talk(talks_directory, title="Changed Title")
    existing = {
        "filename": "2026-08-01-deterministic-ingress.md",
        "title": "Authoritative Title",
        "conference": "TestConf",
        "date": "2026-08-01",
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "processed",
    }
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )
    before = database_path.read_bytes()

    report = scan_shownotes.execute(database_path, apply_requested=True)

    entry = report["entries"][0]
    assert entry["disposition"] == "review_required"
    assert entry["changes"] == {}
    assert entry["issues"][0]["code"] == "existing_title_conflict"
    assert report["database_written"] is False
    assert database_path.read_bytes() == before


def test_event_qualified_shownotes_title_preserves_authored_title(
    tmp_path: Path,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    filename = "voxxed-lu-2026-monkey.md"
    authored_title = (
        "Never Trust a Monkey: The Chasm, the Craft, and the Chain of AI-Assisted Code"
    )
    conference = "Voxxed Days Luxembourg 2026"
    talk_date = "2026-06-18"
    _write_jekyll_talk(
        talks_directory,
        filename=filename,
        title=f"{authored_title} at Voxxed Luxembourg 2026",
        conference=conference,
        date=talk_date,
    )
    existing = {
        "filename": filename,
        "title": authored_title,
        "conference": conference,
        "date": talk_date,
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "processed",
    }
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )
    before = database_path.read_bytes()

    report = scan_shownotes.execute(database_path, apply_requested=True)

    entry = report["entries"][0]
    assert entry["disposition"] == "unchanged"
    assert entry["changes"] == {}
    assert entry["issues"] == []
    assert report["database_written"] is False
    assert database_path.read_bytes() == before
    assert json.loads(before)["talks"][0]["title"] == authored_title


@pytest.mark.parametrize(
    "stored_context",
    [
        {},
        {"date": "2026-06-18"},
        {"conference": "Voxxed Days Luxembourg 2026"},
    ],
)
def test_event_qualified_title_requires_stored_conference_and_date(
    tmp_path: Path,
    stored_context: dict[str, str],
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    filename = "voxxed-lu-2026-monkey.md"
    authored_title = "Never Trust a Monkey"
    conference = "Voxxed Days Luxembourg 2026"
    talk_date = "2026-06-18"
    _write_jekyll_talk(
        talks_directory,
        filename=filename,
        title=f"{authored_title} at Voxxed Luxembourg 2026",
        conference=conference,
        date=talk_date,
    )
    existing = {
        "filename": filename,
        "title": authored_title,
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "processed",
        **stored_context,
    }
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )
    before = database_path.read_bytes()

    report = scan_shownotes.execute(database_path, apply_requested=True)

    entry = report["entries"][0]
    assert entry["disposition"] == "review_required"
    assert entry["changes"] == {}
    assert [issue["code"] for issue in entry["issues"]] == ["existing_title_conflict"]
    assert report["database_written"] is False
    assert database_path.read_bytes() == before


def test_exact_title_still_fills_missing_stored_conference_and_date(
    tmp_path: Path,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    filename = "voxxed-lu-2026-monkey.md"
    authored_title = "Never Trust a Monkey"
    conference = "Voxxed Days Luxembourg 2026"
    talk_date = "2026-06-18"
    _write_jekyll_talk(
        talks_directory,
        filename=filename,
        title=authored_title,
        conference=conference,
        date=talk_date,
    )
    existing = {
        "filename": filename,
        "title": authored_title,
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "processed",
    }
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )

    report = scan_shownotes.execute(database_path, apply_requested=True)

    entry = report["entries"][0]
    assert entry["disposition"] == "update"
    assert entry["changes"] == {
        "conference": conference,
        "date": talk_date,
    }
    assert entry["issues"] == []
    assert report["database_written"] is True
    talk = json.loads(database_path.read_text(encoding="utf-8"))["talks"][0]
    assert talk["title"] == authored_title
    assert talk["conference"] == conference
    assert talk["date"] == talk_date


@pytest.mark.parametrize(
    ("catalog_conference", "shownotes_qualifier"),
    [
        ("Java Conference 2026", "Java Meetup 2026"),
        ("DevOps Days 2026", "DevOps Conference 2026"),
        ("Open Source Summit 2026", "Source Conference 2026"),
    ],
)
def test_event_qualified_title_preserves_event_type_identity(
    tmp_path: Path,
    catalog_conference: str,
    shownotes_qualifier: str,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    filename = "2026-06-18-event-identity.md"
    authored_title = "Identity-Bound Title"
    talk_date = "2026-06-18"
    _write_jekyll_talk(
        talks_directory,
        filename=filename,
        title=f"{authored_title} at {shownotes_qualifier}",
        conference=catalog_conference,
        date=talk_date,
    )
    existing = {
        "filename": filename,
        "title": authored_title,
        "conference": catalog_conference,
        "date": talk_date,
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "processed",
    }
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )
    before = database_path.read_bytes()

    report = scan_shownotes.execute(database_path, apply_requested=True)

    entry = report["entries"][0]
    assert entry["disposition"] == "review_required"
    assert entry["changes"] == {}
    assert [issue["code"] for issue in entry["issues"]] == ["existing_title_conflict"]
    assert report["database_written"] is False
    assert database_path.read_bytes() == before


@pytest.mark.parametrize(
    "shownotes_title",
    [
        (
            "Never Trust a Monkey: The Chasm, the Craft, and the Chain of "
            "AI-Assisted Code at Devoxx Belgium 2026"
        ),
        (
            "Never Trust a Monkey: The Chasm, the Craft, and the Chain of "
            "AI-Assisted Code at Voxxed Days Luxembourg 2025"
        ),
        ("Never Trust a Monkey: A Different Subtitle at Voxxed Days Luxembourg 2026"),
        "Never Trust a Monkey Returns at Voxxed Days Luxembourg 2026",
    ],
)
def test_event_qualified_title_rejects_wrong_identity_and_shared_prefixes(
    tmp_path: Path,
    shownotes_title: str,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    filename = "voxxed-lu-2026-monkey.md"
    authored_title = (
        "Never Trust a Monkey: The Chasm, the Craft, and the Chain of AI-Assisted Code"
    )
    conference = "Voxxed Days Luxembourg 2026"
    talk_date = "2026-06-18"
    _write_jekyll_talk(
        talks_directory,
        filename=filename,
        title=shownotes_title,
        conference=conference,
        date=talk_date,
    )
    existing = {
        "filename": filename,
        "title": authored_title,
        "conference": conference,
        "date": talk_date,
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "processed",
    }
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )
    before = database_path.read_bytes()

    report = scan_shownotes.execute(database_path, apply_requested=True)

    entry = report["entries"][0]
    assert entry["disposition"] == "review_required"
    assert entry["changes"] == {}
    assert [issue["code"] for issue in entry["issues"]] == ["existing_title_conflict"]
    assert report["database_written"] is False
    assert database_path.read_bytes() == before


@pytest.mark.parametrize(
    ("field", "stored_value", "shownotes_value"),
    [
        ("title", "Kahneman\u2019s Shortcut", "Kahneman's Shortcut"),
        (
            "title",
            'The "DevOps engineer" Test',
            "The \u201cDevOps engineer\u201d Test",
        ),
        ("conference", "TESTCONF", "testconf"),
        ("title", "Caf\u00e9", "Cafe\u0301"),
        ("conference", "Caf\u00e9Conf", "Cafe\u0301Conf"),
    ],
)
def test_presentation_only_metadata_differences_are_comparison_only(
    tmp_path: Path,
    field: str,
    stored_value: str,
    shownotes_value: str,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    shownotes_arguments = {field: shownotes_value}
    _write_jekyll_talk(talks_directory, **shownotes_arguments)
    existing = {
        "filename": "2026-08-01-deterministic-ingress.md",
        "title": "Deterministic Ingress",
        "conference": "TestConf",
        "date": "2026-08-01",
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "processed",
    }
    existing[field] = stored_value
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )
    before = database_path.read_bytes()

    report = scan_shownotes.execute(database_path, apply_requested=True)

    entry = report["entries"][0]
    assert entry["disposition"] == "unchanged"
    assert entry["proposal"][field] == shownotes_value
    assert entry["changes"] == {}
    assert entry["issues"] == []
    assert report["counts"] == {
        "add": 0,
        "update": 0,
        "unchanged": 1,
        "review_required": 0,
    }
    assert report["database_written"] is False
    assert database_path.read_bytes() == before
    assert json.loads(before)["talks"][0][field] == stored_value


def test_comparison_equivalence_does_not_rewrite_during_an_unrelated_update(
    tmp_path: Path,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    video_url = f"https://youtu.be/{YOUTUBE_ID}"
    stored_title = "Kahneman\u2019s Shortcut"
    _write_jekyll_talk(
        talks_directory,
        title="Kahneman's Shortcut",
        video_url=video_url,
    )
    existing = {
        "filename": "2026-08-01-deterministic-ingress.md",
        "title": stored_title,
        "conference": "TestConf",
        "date": "2026-08-01",
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "processed",
    }
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )

    report = scan_shownotes.execute(database_path, apply_requested=True)

    talk = json.loads(database_path.read_text(encoding="utf-8"))["talks"][0]
    assert report["entries"][0]["disposition"] == "update"
    assert report["entries"][0]["changes"] == {
        "video_url": video_url,
        "youtube_id": YOUTUBE_ID,
    }
    assert talk["title"] == stored_title
    assert talk["video_url"] == video_url


@pytest.mark.parametrize(
    ("field", "stored_value", "shownotes_value"),
    [
        ("title", "Case Matters", "case matters"),
        ("title", "Quoted: Title", "Quoted Title"),
        ("conference", "Test Conf", "Test  Conf"),
        ("conference", "TestConf", "TestConf Global"),
    ],
)
def test_presentation_comparison_stays_narrow(
    tmp_path: Path,
    field: str,
    stored_value: str,
    shownotes_value: str,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    shownotes_arguments = {field: shownotes_value}
    _write_jekyll_talk(talks_directory, **shownotes_arguments)
    existing = {
        "filename": "2026-08-01-deterministic-ingress.md",
        "title": "Deterministic Ingress",
        "conference": "TestConf",
        "date": "2026-08-01",
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "processed",
    }
    existing[field] = stored_value
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )
    before = database_path.read_bytes()

    report = scan_shownotes.execute(database_path, apply_requested=True)

    entry = report["entries"][0]
    assert entry["disposition"] == "review_required"
    assert entry["changes"] == {}
    assert entry["issues"] == [
        {
            "code": f"existing_{field}_conflict",
            "field": field,
            "message": (
                f"tracking DB {field} {stored_value!r} conflicts with shownotes "
                f"{shownotes_value!r}; choose the authoritative value"
            ),
        }
    ]
    assert report["database_written"] is False
    assert database_path.read_bytes() == before


@pytest.mark.parametrize(
    ("source_type", "field", "rejected_url", "proposed_url"),
    [
        (
            "video",
            "video_url",
            f"https://youtu.be/{YOUTUBE_ID}",
            f"https://www.youtube.com/watch?v={YOUTUBE_ID}",
        ),
        (
            "slides",
            "slides_url",
            f"https://drive.google.com/open?id={DRIVE_ID}",
            f"https://docs.google.com/presentation/d/{DRIVE_ID}/edit",
        ),
        # Byte-identical URL: the match method must say exact_url, not provider_id.
        (
            "video",
            "video_url",
            f"https://www.youtube.com/watch?v={YOUTUBE_ID}",
            f"https://www.youtube.com/watch?v={YOUTUBE_ID}",
        ),
    ],
)
def test_rejected_source_identity_cannot_reappear_in_another_url_form(
    tmp_path: Path,
    source_type: str,
    field: str,
    rejected_url: str,
    proposed_url: str,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    write_arguments = {field: proposed_url}
    _write_jekyll_talk(talks_directory, **write_arguments)
    existing = {
        "filename": "2026-08-01-deterministic-ingress.md",
        "title": "Deterministic Ingress",
        "conference": "TestConf",
        "date": "2026-08-01",
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "pending",
        "source_rejections": [
            {
                "source_type": source_type,
                "url": rejected_url,
                "reason": "wrong_delivery",
                "evidence": "provider page identifies another delivery",
                "verified_at": "2026-08-01T12:00:00+00:00",
            }
        ],
    }
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )
    before = database_path.read_bytes()

    report = scan_shownotes.execute(database_path, apply_requested=True)

    entry = report["entries"][0]
    assert entry["disposition"] == "review_required"
    matched = [
        issue
        for issue in entry["issues"]
        if issue["code"] == "rejected_source_reappeared" and issue["field"] == field
    ]
    assert len(matched) == 1
    # The report is self-contained: the reviewer decides from this item alone,
    # without reopening the tracking database for the ledger entry.
    assert matched[0]["matched_rejection"] == {
        "source_type": source_type,
        "url": rejected_url,
        "provider_id": YOUTUBE_ID if source_type == "video" else DRIVE_ID,
        "reason": "wrong_delivery",
        "evidence": "provider page identifies another delivery",
        "verified_at": "2026-08-01T12:00:00+00:00",
    }
    assert matched[0]["match"]["method"] == (
        "exact_url" if proposed_url == rejected_url else "provider_id"
    )
    assert matched[0]["match"]["candidate_url"] == proposed_url
    assert database_path.read_bytes() == before


def test_incomplete_new_file_stays_a_review_proposal(tmp_path: Path) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    _write_jekyll_talk(talks_directory, conference=None)
    database_path = _database_path(tmp_path, _local_config(site))
    before = database_path.read_bytes()

    report = scan_shownotes.execute(database_path, apply_requested=True)

    entry = report["entries"][0]
    assert entry["disposition"] == "review_required"
    assert entry["issues"][-1]["code"] == "conference_missing"
    assert report["mutation_count"] == 0
    assert database_path.read_bytes() == before


def test_normalized_filename_collision_stays_a_review_proposal(
    tmp_path: Path,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    _write_jekyll_talk(
        talks_directory,
        filename="talk.md",
    )
    existing = {
        "filename": "Talk.md",
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "pending",
    }
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[existing],
    )

    report = scan_shownotes.execute(database_path, apply_requested=False)

    entry = report["entries"][0]
    assert entry["disposition"] == "review_required"
    assert entry["issues"][-1]["code"] == "filename_identity_ambiguous"


@pytest.mark.parametrize(
    ("shownotes", "expected_operation"),
    [
        (
            {"enabled": False, "source": {"type": "local_jekyll"}},
            "skipped_disabled",
        ),
        (
            {"enabled": True, "source": {"type": "remote_url"}},
            "skipped_nonlocal",
        ),
        (
            {"enabled": True, "source": {"type": "none"}},
            "skipped_nonlocal",
        ),
    ],
)
def test_nonlocal_or_disabled_apply_is_a_structured_non_mutating_noop(
    tmp_path: Path,
    shownotes: dict[str, object],
    expected_operation: str,
) -> None:
    database_path = _database_path(tmp_path, {"shownotes": shownotes})
    before = database_path.read_bytes()

    report = scan_shownotes.execute(database_path, apply_requested=True)

    assert report["operation"] == expected_operation
    assert report["mutation_count"] == 0
    assert report["scanned_file_count"] == 0
    assert report["entries"] == []
    assert report["database_written"] is False
    assert database_path.read_bytes() == before


def test_null_shownotes_config_uses_legacy_talks_source_directory(
    tmp_path: Path,
) -> None:
    _, talks_directory = _shownotes_site(tmp_path)
    _write_jekyll_talk(talks_directory)
    config = {
        "shownotes": None,
        "talks_source_dir": str(talks_directory),
    }
    database_path = _database_path(tmp_path, config)

    report = scan_shownotes.execute(database_path, apply_requested=False)

    assert report["shownotes"]["config_origin"] == "talks_source_dir"
    assert report["shownotes"]["talks_directory"] == str(talks_directory.resolve())
    assert report["counts"]["add"] == 1


def test_json_and_toml_frontmatter_are_supported(tmp_path: Path) -> None:
    json_path = tmp_path / "json.md"
    json_path.write_text(
        json.dumps(
            {
                "title": "JSON Talk",
                "conference": "JSONConf",
                "date": "2026-08-01",
                "video": f"https://youtu.be/{YOUTUBE_ID}",
            }
        )
        + "\nBody\n",
        encoding="utf-8",
    )
    toml_path = tmp_path / "toml.md"
    toml_path.write_text(
        "+++\n"
        'title = "TOML Talk"\n'
        'conference = "TOMLConf"\n'
        'date = "2026-08-01"\n'
        f'slides = "https://drive.google.com/file/d/{DRIVE_ID}/view"\n'
        "+++\nBody\n",
        encoding="utf-8",
    )

    json_proposal, json_issues = scan_shownotes.parse_shownotes_file(json_path)
    toml_proposal, toml_issues = scan_shownotes.parse_shownotes_file(toml_path)

    assert json_issues == []
    assert json_proposal["youtube_id"] == YOUTUBE_ID
    if scan_shownotes.tomllib is None:
        assert toml_issues[0]["code"] == "toml_parser_unavailable"
    else:
        assert toml_issues == []
        assert toml_proposal["google_drive_id"] == DRIVE_ID


def test_unsafe_talks_subdir_is_rejected_with_recovery(tmp_path: Path) -> None:
    site, _ = _shownotes_site(tmp_path)
    config = _local_config(site, talks_subdir="../outside")
    database_path = _database_path(tmp_path, config)

    with pytest.raises(
        scan_shownotes.ShownotesScanError,
        match="must be a safe relative path",
    ):
        scan_shownotes.execute(database_path, apply_requested=False)


def test_database_symlink_is_rejected_before_read(tmp_path: Path) -> None:
    target = tmp_path / "canonical.json"
    _write_json(target, {"config": {}, "talks": []})
    link = tmp_path / "tracking-database.json"
    link.symlink_to(target)

    with pytest.raises(
        scan_shownotes.ShownotesScanError,
        match="symbolic link",
    ):
        scan_shownotes.execute(link, apply_requested=False)


def test_future_root_is_classified_before_old_shownotes_shapes(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "tracking-database.json"
    raw = b'{"schema_version":99,"future_inventory":{"records":[]}}\n'
    database_path.write_bytes(raw)

    with pytest.raises(
        scan_shownotes.ShownotesScanError,
        match="tracking_database_schema_version_unsupported",
    ) as stopped:
        scan_shownotes.execute(database_path, apply_requested=False)

    assert "config must be" not in str(stopped.value)
    assert "talk records are invalid" not in str(stopped.value)
    assert database_path.read_bytes() == raw


def test_shownotes_directory_symlink_is_rejected_before_glob(
    tmp_path: Path,
) -> None:
    site = tmp_path / "shownotes"
    site.mkdir()
    external_talks = tmp_path / "external-talks"
    external_talks.mkdir()
    (site / "_talks").symlink_to(external_talks, target_is_directory=True)
    database_path = _database_path(tmp_path, _local_config(site))

    with pytest.raises(
        scan_shownotes.ShownotesScanError,
        match="shownotes talks directory.*symbolic link",
    ):
        scan_shownotes.execute(database_path, apply_requested=False)


def test_markdown_symlink_stays_an_unread_review_proposal(tmp_path: Path) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    external = tmp_path / "external.md"
    _write_jekyll_talk(tmp_path, filename=external.name)
    (talks_directory / "linked.md").symlink_to(external)
    database_path = _database_path(tmp_path, _local_config(site))

    report = scan_shownotes.execute(database_path, apply_requested=False)

    entry = report["entries"][0]
    assert entry["filename"] == "linked.md"
    assert entry["disposition"] == "review_required"
    assert entry["issues"][0]["code"] == "shownotes_file_unreadable"
    assert "non-symlink Markdown file" in entry["issues"][0]["message"]


def test_same_bytes_database_replacement_after_scan_aborts_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    _write_jekyll_talk(talks_directory)
    database_path = _database_path(tmp_path, _local_config(site))
    before = database_path.read_bytes()
    original_builder = scan_shownotes.build_scan_report

    def replace_after_scan(*args: object, **kwargs: object):
        result = original_builder(*args, **kwargs)
        replacement = tmp_path / "same-bytes-replacement.json"
        replacement.write_bytes(before)
        os.replace(replacement, database_path)
        return result

    monkeypatch.setattr(
        scan_shownotes,
        "build_scan_report",
        replace_after_scan,
    )

    with pytest.raises(
        scan_shownotes.ShownotesScanError,
        match="content or generation changed after the scan",
    ):
        scan_shownotes.execute(database_path, apply_requested=True)

    assert database_path.read_bytes() == before
    assert not list(tmp_path.glob(".*.shownotes.tmp"))


def test_atomic_replace_failure_leaves_database_and_cleans_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site, talks_directory = _shownotes_site(tmp_path)
    _write_jekyll_talk(talks_directory)
    database_path = _database_path(tmp_path, _local_config(site))
    before = database_path.read_bytes()

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("simulated replacement failure")

    tracking_database_os = getattr(sys.modules["tracking_database_io"], "os")
    monkeypatch.setattr(tracking_database_os, "replace", fail_replace)

    with pytest.raises(
        scan_shownotes.ShownotesScanError,
        match="cannot atomically update",
    ):
        scan_shownotes.execute(database_path, apply_requested=True)

    assert database_path.read_bytes() == before
    assert not list(tmp_path.glob(".*.shownotes.tmp"))


def test_main_emits_one_json_error_and_actionable_stderr(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing.json"

    assert scan_shownotes.main([str(missing)]) == 2

    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert "tracking database is missing" in payload["error"]
    assert "pass its canonical file path" in captured.err


def _talk_with_rejections(rejections: list[object]) -> dict[str, object]:
    return {
        "filename": "2026-08-01-deterministic-ingress.md",
        "title": "Deterministic Ingress",
        "conference": "TestConf",
        "date": "2026-08-01",
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "pending",
        "source_rejections": rejections,
    }


def _valid_rejection(url: str, **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "source_type": "video",
        "url": url,
        "reason": "wrong_delivery",
        "evidence": "provider page identifies another delivery",
        "verified_at": "2026-08-01T12:00:00+00:00",
    }
    record.update(overrides)
    return record


def test_only_the_matched_rejection_is_reported(tmp_path: Path) -> None:
    """Unrelated ledger entries stay private to the talk record."""
    site, talks_directory = _shownotes_site(tmp_path)
    proposed = f"https://www.youtube.com/watch?v={YOUTUBE_ID}"
    _write_jekyll_talk(talks_directory, video_url=proposed)
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[
            _talk_with_rejections(
                [
                    _valid_rejection(
                        "https://youtu.be/zzzzzzzzzzz",
                        reason="non_delivery_clip",
                        evidence="unrelated earlier upload",
                    ),
                    _valid_rejection(f"https://youtu.be/{YOUTUBE_ID}"),
                    _valid_rejection(
                        "https://youtu.be/qqqqqqqqqqq",
                        reason="unrelated_recording",
                        evidence="different speaker entirely",
                    ),
                ]
            )
        ],
    )

    report = scan_shownotes.execute(database_path, apply_requested=True)

    issues = report["entries"][0]["issues"]
    matched = [
        issue for issue in issues if issue["code"] == "rejected_source_reappeared"
    ]
    assert len(matched) == 1
    assert matched[0]["matched_rejection"]["url"] == f"https://youtu.be/{YOUTUBE_ID}"
    assert matched[0]["matched_rejection"]["reason"] == "wrong_delivery"
    serialized = json.dumps(report)
    assert "zzzzzzzzzzz" not in serialized
    assert "qqqqqqqqqqq" not in serialized


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"reason": ""}, id="blank-reason"),
        pytest.param({"evidence": None}, id="missing-evidence"),
        pytest.param({"verified_at": "2026-08-01T12:00:00"}, id="naive-timestamp"),
        pytest.param({"verified_at": "not-a-timestamp"}, id="unparseable-timestamp"),
    ],
)
def test_malformed_rejection_blocks_the_scan_before_any_match(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    """A record that would be reported as evidence is repaired, never half-trusted.

    The guarantee is stronger than a per-entry issue: the loader rejects the
    whole scan, so no report can carry an unverifiable ledger record. See
    tracking_database._validate_source_rejection.
    """
    site, talks_directory = _shownotes_site(tmp_path)
    proposed = f"https://www.youtube.com/watch?v={YOUTUBE_ID}"
    _write_jekyll_talk(talks_directory, video_url=proposed)
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[
            _talk_with_rejections(
                [_valid_rejection(f"https://youtu.be/{YOUTUBE_ID}", **overrides)]
            )
        ],
    )
    before = database_path.read_bytes()

    with pytest.raises(scan_shownotes.ShownotesScanError, match="source_rejections"):
        scan_shownotes.execute(database_path, apply_requested=True)

    assert database_path.read_bytes() == before


def test_matched_rejection_report_is_byte_stable(tmp_path: Path) -> None:
    """Two scans of unchanged state serialize identically."""
    site, talks_directory = _shownotes_site(tmp_path)
    proposed = f"https://www.youtube.com/watch?v={YOUTUBE_ID}"
    _write_jekyll_talk(talks_directory, video_url=proposed)
    database_path = _database_path(
        tmp_path,
        _local_config(site),
        talks=[
            _talk_with_rejections([_valid_rejection(f"https://youtu.be/{YOUTUBE_ID}")])
        ],
    )

    first = scan_shownotes.execute(database_path, apply_requested=False)
    second = scan_shownotes.execute(database_path, apply_requested=False)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["schema_version"] == scan_shownotes.REPORT_SCHEMA_VERSION


def test_an_approved_repair_makes_the_scan_report_the_entry_unchanged(
    tmp_path: Path,
    mutate_tracking_database,
) -> None:
    """#236 acceptance 5: the loop closes.

    A review-required conflict is refused by `--apply`, repaired through the
    owner writer, and the next scan sees no conflict left to review.
    """
    site, talks_directory = _shownotes_site(tmp_path)
    _write_jekyll_talk(talks_directory, title="Changed Title")
    existing = {
        "filename": "2026-08-01-deterministic-ingress.md",
        "title": "Authoritative Title",
        "conference": "TestConf",
        "date": "2026-08-01",
        "schema_version": CURRENT_TALK_SCHEMA,
        "status": "processed",
    }
    database_path = _database_path(tmp_path, _local_config(site), talks=[existing])

    first = scan_shownotes.execute(database_path, apply_requested=True)
    assert first["entries"][0]["disposition"] == "review_required"
    assert first["database_written"] is False

    database = json.loads(database_path.read_text(encoding="utf-8"))
    candidate, _changes = mutate_tracking_database.build_candidate(
        database,
        [
            {
                "kind": "apply_reviewed_metadata",
                "filename": "2026-08-01-deterministic-ingress.md",
                "expect": {"title": "Authoritative Title"},
                "set": {"title": "Changed Title"},
            }
        ],
    )
    database_path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")

    second = scan_shownotes.execute(database_path, apply_requested=False)

    entry = second["entries"][0]
    assert entry["disposition"] == "unchanged"
    assert entry["issues"] == []


# --- which tree of a site checkout gets scanned -------------------------------


def _git(cwd: Path, *arguments: str) -> str:
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.test",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.test",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 0, (arguments, result.stderr)
    return result.stdout.strip()


PUBLISHED_TALK = "2026-08-01-published.md"
LATER_TALK = "2026-09-01-published-later.md"
DRAFT_TALK = "2026-10-01-branch-only-draft.md"


def _published_site(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A site checkout cloned from an origin whose main holds one talk.

    Returns (checkout, a second clone that publishes to origin, origin).
    """
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "--initial-branch=main")
    publisher = tmp_path / "publisher"
    _git(tmp_path, "clone", str(origin), str(publisher))
    _git(publisher, "checkout", "-b", "main")
    (publisher / "_talks").mkdir()
    _write_jekyll_talk(publisher / "_talks", filename=PUBLISHED_TALK)
    _git(publisher, "add", ".")
    _git(publisher, "commit", "-m", "Publish a talk")
    _git(publisher, "push", "origin", "main")
    checkout = tmp_path / "shownotes"
    _git(tmp_path, "clone", str(origin), str(checkout))
    return checkout, publisher, origin


def _publish_later_talk(publisher: Path) -> None:
    _write_jekyll_talk(publisher / "_talks", filename=LATER_TALK)
    _git(publisher, "add", ".")
    _git(publisher, "commit", "-m", "Publish another talk")
    _git(publisher, "push", "origin", "main")


def _scanned_filenames(report: dict[str, Any]) -> list[str]:
    return [entry["filename"] for entry in report["entries"]]


def _scan(tmp_path: Path, site: Path, *, apply_requested: bool = False):
    database_path = _database_path(tmp_path, _local_config(site))
    return scan_shownotes.execute(database_path, apply_requested=apply_requested)


def test_a_feature_branch_checkout_still_sees_what_main_published(tmp_path):
    """The reported failure: a talk live on main scanned as absent."""
    checkout, publisher, _origin = _published_site(tmp_path)
    _git(checkout, "checkout", "-b", "feature")
    _write_jekyll_talk(checkout / "_talks", filename=DRAFT_TALK)
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-m", "Draft on a branch")
    _publish_later_talk(publisher)

    report = _scan(tmp_path, checkout)

    assert _scanned_filenames(report) == [PUBLISHED_TALK, LATER_TALK]
    assert report["scanned_file_count"] == 2
    assert report["source_checkout"] == {
        "state": "published_snapshot",
        "branch": "feature",
        "default_branch": "main",
        "scanned_commit": _git(publisher, "rev-parse", "HEAD"),
        "fetch": "ok",
    }
    assert report["warnings"] == []


def test_the_snapshot_leaves_the_speakers_checkout_alone(tmp_path):
    checkout, _publisher, _origin = _published_site(tmp_path)
    _git(checkout, "checkout", "-b", "feature")
    edited = checkout / "_talks" / PUBLISHED_TALK
    edited.write_text("uncommitted edit\n", encoding="utf-8")
    untracked = checkout / "_talks" / DRAFT_TALK
    untracked.write_text("untracked draft\n", encoding="utf-8")
    head = _git(checkout, "rev-parse", "HEAD")
    status = _git(checkout, "status", "--porcelain")

    report = _scan(tmp_path, checkout)

    assert _scanned_filenames(report) == [PUBLISHED_TALK]
    assert report["entries"][0]["proposal"]["title"] == "Deterministic Ingress"
    assert _git(checkout, "rev-parse", "HEAD") == head
    assert _git(checkout, "rev-parse", "--abbrev-ref", "HEAD") == "feature"
    assert _git(checkout, "status", "--porcelain") == status
    assert edited.read_text(encoding="utf-8") == "uncommitted edit\n"


def test_the_report_still_names_the_configured_location(tmp_path):
    checkout, _publisher, _origin = _published_site(tmp_path)
    _git(checkout, "checkout", "-b", "feature")

    shownotes = _scan(tmp_path, checkout)["shownotes"]

    assert shownotes["root"] == str(checkout.resolve())
    assert shownotes["talks_directory"] == str((checkout / "_talks").resolve())


def test_a_detached_checkout_reads_the_snapshot(tmp_path):
    checkout, publisher, _origin = _published_site(tmp_path)
    _git(checkout, "checkout", "--detach")
    _publish_later_talk(publisher)

    report = _scan(tmp_path, checkout)

    assert _scanned_filenames(report) == [PUBLISHED_TALK, LATER_TALK]
    assert report["source_checkout"]["state"] == "published_snapshot"
    assert report["source_checkout"]["branch"] is None


def test_a_default_branch_checkout_that_hasnt_pulled_reads_the_snapshot(tmp_path):
    checkout, publisher, _origin = _published_site(tmp_path)
    _publish_later_talk(publisher)

    report = _scan(tmp_path, checkout)

    assert _scanned_filenames(report) == [PUBLISHED_TALK, LATER_TALK]
    assert report["source_checkout"]["state"] == "published_snapshot"
    assert report["source_checkout"]["branch"] == "main"
    assert not (checkout / "_talks" / LATER_TALK).exists()


def test_a_current_default_branch_keeps_reading_its_working_tree(tmp_path):
    checkout, _publisher, _origin = _published_site(tmp_path)
    _write_jekyll_talk(checkout / "_talks", filename=DRAFT_TALK)

    report = _scan(tmp_path, checkout)

    assert _scanned_filenames(report) == [PUBLISHED_TALK, DRAFT_TALK]
    assert report["source_checkout"] == {
        "state": "default_branch",
        "branch": "main",
        "default_branch": "main",
        "scanned_commit": None,
        "fetch": "ok",
    }


def test_a_default_branch_ahead_of_origin_keeps_reading_its_working_tree(tmp_path):
    checkout, _publisher, _origin = _published_site(tmp_path)
    _write_jekyll_talk(checkout / "_talks", filename=DRAFT_TALK)
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-m", "Local commit")

    report = _scan(tmp_path, checkout)

    assert report["source_checkout"]["state"] == "default_branch"
    assert _scanned_filenames(report) == [PUBLISHED_TALK, DRAFT_TALK]


def test_apply_adds_what_main_published_and_not_the_branch_draft(tmp_path):
    checkout, _publisher, _origin = _published_site(tmp_path)
    _git(checkout, "checkout", "-b", "feature")
    _write_jekyll_talk(checkout / "_talks", filename=DRAFT_TALK)

    database_path = _database_path(tmp_path, _local_config(checkout))
    report = scan_shownotes.execute(database_path, apply_requested=True)

    assert report["database_written"] is True
    stored = json.loads(database_path.read_text(encoding="utf-8"))
    assert [talk["filename"] for talk in stored["talks"]] == [PUBLISHED_TALK]


def test_a_failed_fetch_warns_and_scans_the_last_fetched_commit(tmp_path, capsys):
    checkout, _publisher, origin = _published_site(tmp_path)
    _git(checkout, "checkout", "-b", "feature")
    origin.rename(tmp_path / "origin-moved.git")
    database_path = _database_path(tmp_path, _local_config(checkout))

    assert scan_shownotes.main([str(database_path)]) == 0

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert _scanned_filenames(report) == [PUBLISHED_TALK]
    assert report["source_checkout"]["fetch"] == "failed"
    assert len(report["warnings"]) == 1
    assert "could not fetch origin/main" in report["warnings"][0]
    assert "could not fetch origin/main" in captured.err


def test_no_remote_head_warns_and_reads_the_working_tree(tmp_path, capsys):
    checkout, _publisher, _origin = _published_site(tmp_path)
    _git(checkout, "remote", "set-head", "origin", "--delete")
    database_path = _database_path(tmp_path, _local_config(checkout))

    assert scan_shownotes.main([str(database_path)]) == 0

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["source_checkout"]["state"] == "no_default_branch"
    assert _scanned_filenames(report) == [PUBLISHED_TALK]
    assert "git remote set-head origin --auto" in report["warnings"][0]
    assert "git remote set-head origin --auto" in captured.err


def test_a_site_that_isnt_a_git_checkout_reads_its_files(tmp_path):
    site, talks_directory = _shownotes_site(tmp_path)
    _write_jekyll_talk(talks_directory, filename=PUBLISHED_TALK)

    report = _scan(tmp_path, site)

    assert report["source_checkout"]["state"] == "not_git"
    assert report["warnings"] == []
    assert _scanned_filenames(report) == [PUBLISHED_TALK]


def test_git_being_absent_reads_the_files_as_not_git(tmp_path, monkeypatch):
    site, talks_directory = _shownotes_site(tmp_path)
    _write_jekyll_talk(talks_directory, filename=PUBLISHED_TALK)
    monkeypatch.setenv("PATH", str(tmp_path / "no-tools-here"))

    report = _scan(tmp_path, site)

    assert report["source_checkout"]["state"] == "not_git"
    assert _scanned_filenames(report) == [PUBLISHED_TALK]


def test_a_talks_directory_missing_from_main_is_an_error_not_an_empty_scan(tmp_path):
    checkout, _publisher, _origin = _published_site(tmp_path)
    _git(checkout, "checkout", "-b", "feature")
    (checkout / "_branch_talks").mkdir()
    database_path = _database_path(
        tmp_path, _local_config(checkout, talks_subdir="_branch_talks")
    )

    with pytest.raises(scan_shownotes.ShownotesScanError, match="doesn't exist"):
        scan_shownotes.execute(database_path, apply_requested=False)


def test_a_symlinked_talk_on_main_is_refused_like_one_in_a_working_tree(tmp_path):
    checkout, publisher, _origin = _published_site(tmp_path)
    (publisher / "_talks" / LATER_TALK).symlink_to(PUBLISHED_TALK)
    _git(publisher, "add", ".")
    _git(publisher, "commit", "-m", "Symlink a talk")
    _git(publisher, "push", "origin", "main")
    _git(checkout, "checkout", "-b", "feature")

    report = _scan(tmp_path, checkout)

    entry = {item["filename"]: item for item in report["entries"]}[LATER_TALK]
    assert entry["disposition"] == "review_required"
    assert any("non-symlink" in issue["message"] for issue in entry["issues"])


def test_a_subdirectory_site_root_reads_the_right_tree_path(tmp_path):
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "--initial-branch=main")
    publisher = tmp_path / "publisher"
    _git(tmp_path, "clone", str(origin), str(publisher))
    _git(publisher, "checkout", "-b", "main")
    (publisher / "site" / "_talks").mkdir(parents=True)
    _write_jekyll_talk(publisher / "site" / "_talks", filename=PUBLISHED_TALK)
    _git(publisher, "add", ".")
    _git(publisher, "commit", "-m", "Publish")
    _git(publisher, "push", "origin", "main")
    checkout = tmp_path / "shownotes"
    _git(tmp_path, "clone", str(origin), str(checkout))
    _git(checkout, "checkout", "-b", "feature")

    report = _scan(tmp_path, checkout / "site")

    assert report["source_checkout"]["state"] == "published_snapshot"
    assert _scanned_filenames(report) == [PUBLISHED_TALK]


def test_a_nonlocal_source_records_no_checkout(tmp_path):
    database_path = _database_path(
        tmp_path,
        {"shownotes": {"enabled": True, "source": {"type": "none"}}},
    )

    report = scan_shownotes.execute(database_path, apply_requested=False)

    assert report["operation"] == "skipped_nonlocal"
    assert report["source_checkout"] is None
