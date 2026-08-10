"""Offline tests for the networked, read-only source identity audit helper."""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest


VIDEO_ID = "AbCdEfGhI_1"
OTHER_VIDEO_ID = "ZyXwVuTsR_2"
CAPTURED_AT = "2026-07-31T19:00:00Z"


def talk(filename="talk.md", title="Perfect Vault Ingress", **updates):
    value = {
        "filename": filename,
        "title": title,
        "conference": "ExampleConf",
        "date": "2026-07-30",
        "video_url": f"https://www.youtube.com/watch?v={VIDEO_ID}",
        "youtube_id": VIDEO_ID,
        "duration_seconds": 2700,
        "status": "processed",
    }
    value.update(updates)
    return value


def metadata(video_id=VIDEO_ID, **updates):
    value = {
        "id": video_id,
        "title": "Perfect Vault Ingress — ExampleConf",
        "uploader": "ExampleConf",
        "uploader_id": "@exampleconf",
        "upload_date": "20260731",
        "duration": 2700,
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
    }
    value.update(updates)
    return value


def finding_codes(report):
    return [item["code"] for item in report["findings"]]


def test_fetches_once_per_youtube_id_and_flags_cross_talk_collision(
    audit_source_identities,
):
    database = {
        "talks": [
            talk("first.md", "Perfect Vault Ingress"),
            talk("second.md", "Unrelated Platform Keynote", date="2025-04-10"),
        ]
    }
    original = deepcopy(database)
    calls = []

    def fetcher(video_id):
        calls.append(video_id)
        return metadata(video_id)

    report = audit_source_identities.audit_database(
        database,
        database_path="/vault/tracking-database.json",
        metadata_fetcher=fetcher,
        captured_at=CAPTURED_AT,
    )

    assert calls == [VIDEO_ID]
    assert report["active_talk_count"] == 2
    assert report["unique_youtube_id_count"] == 1
    assert report["metadata_fetch_count"] == 1
    assert "same_id_cross_talk_collision" in finding_codes(report)
    assert database == original, "audit_database must not mutate its input"


def test_captures_provider_facts_without_inventing_speakers_or_recorded_date(
    audit_source_identities,
):
    report = audit_source_identities.audit_database(
        {"talks": [talk()]},
        database_path="/vault/tracking-database.json",
        metadata_fetcher=lambda video_id: metadata(video_id),
        captured_at=CAPTURED_AT,
    )

    source = report["sources"][0]["provider_evidence"]
    assert source == {
        "schema_version": 1,
        "provider": "youtube",
        "video_id": VIDEO_ID,
        "title": "Perfect Vault Ingress — ExampleConf",
        "uploader": "ExampleConf",
        "uploader_id": "@exampleconf",
        "upload_date": "2026-07-31",
        "duration_seconds": 2700,
        "webpage_url": f"https://www.youtube.com/watch?v={VIDEO_ID}",
        "webpage_video_id": VIDEO_ID,
        "captured_at": CAPTURED_AT,
    }
    proposal = report["talks"][0]["proposed_evidence"]["source_identity"]
    assert proposal == source
    assert "speakers" not in proposal
    assert "recorded_date" not in proposal
    assert "video_url" not in proposal
    assert "repairs" not in report


def test_likely_non_delivery_clip_uses_title_and_duration_evidence(
    audit_source_identities,
):
    report = audit_source_identities.audit_database(
        {"talks": [talk()]},
        database_path="/vault/tracking-database.json",
        metadata_fetcher=lambda video_id: metadata(
            video_id,
            title="Two-minute product demo clip",
            duration=180,
        ),
        captured_at=CAPTURED_AT,
    )

    finding = next(
        item
        for item in report["findings"]
        if item["code"] == "likely_non_delivery_clip"
    )
    assert finding["review_priority"] == "high"
    assert "provider_title_mismatch" in finding_codes(report)
    assert (
        "provider_duration_under_55_percent_of_catalog"
        in (finding["evidence"]["signals"])
    )


@pytest.mark.parametrize(
    ("catalog_title", "conference", "provider_title"),
    [
        (
            'Influencing DevOps without Authority - how "DevOps engineer" can '
            "advance real DevOps",
            "DevOps Vision 2023",
            "Influencing DevOps without Authority at DevOps Vision 2023",
        ),
        (
            "The Epic Groovy Puzzlers: As Usual — Traps, Pitfalls and End Cases",
            "DevNexus 2015",
            "Devnexus 2015 - The Epic Groovy Puzzlers - Baruch and Leonid",
        ),
        (
            "Coding Fast and Slow: Applying Kahneman's Insights to Improve "
            "Development Practices and Efficiency",
            "Dev2Next 2024",
            "Coding Fast and Slow at Dev2Next 2024",
        ),
        (
            "Technical Enshittification: Why Everything in IT is Horrible Right "
            "Now and How to Fix It",
            "JCON 2025",
            "Technical Enshittification at JCON 2025",
        ),
        (
            "Back to the Future of Software: How to Survive AI with Intent "
            "Integrity Chain",
            "DevNexus 2026",
            "Back to the Future of Software at DevNexus 2026",
        ),
        (
            "DevOps Reframed: Embracing the Path to Developer Productivity Engineering",
            "Dev2Next 2024",
            "DevOps Reframed at Dev2Next 2024",
        ),
        (
            "Runtime Rumble: Tool Alpha vs. Tool Beta at ExampleConf 2025",
            "ExampleConf 2025",
            "Runtime Rumble Tool Alpha vs Tool Beta",
        ),
        (
            "DevOps for developers (or maybe against them?!)",
            "Devoxx Belgium 2024",
            "DevOps for Developers at Devoxx Belgium 2024",
        ),
        (
            "Data-Driven DevOps",
            "DevOpsDays Indianapolis 2024",
            "#DataDrivenDevOps as presented at #DevOpsDaysIndy",
        ),
    ],
)
def test_explicit_base_title_accepts_real_provider_subtitle_omissions(
    audit_source_identities, catalog_title, conference, provider_title
):
    report = audit_source_identities.audit_database(
        {"talks": [talk(title=catalog_title, conference=conference)]},
        database_path="/vault/tracking-database.json",
        metadata_fetcher=lambda video_id: metadata(
            video_id,
            title=provider_title,
        ),
        captured_at=CAPTURED_AT,
    )

    assert report["talks"][0]["comparison"]["catalog_title_agrees"] is True
    assert "provider_title_mismatch" not in finding_codes(report)
    assert "provider_event_mismatch" not in finding_codes(report)


@pytest.mark.parametrize(
    ("catalog_conference", "provider_conference", "provider_title"),
    [
        (
            "Conference Alpha 2024",
            "Devoxx Poland 2024",
            "Coding Fast and Slow at Devoxx Poland 2024",
        ),
        (
            "Conference Beta 2024",
            "Dev2Next 2024",
            "Coding Fast and Slow at Dev2Next 2024",
        ),
    ],
)
def test_shared_base_title_does_not_hide_wrong_delivery_event(
    audit_source_identities, catalog_conference, provider_conference, provider_title
):
    catalog_title = (
        "Coding Fast and Slow: Applying Kahneman's Insights to Improve "
        "Development Practices and Efficiency"
    )
    active = talk(title=catalog_title, conference=catalog_conference)
    known_other_event = talk(
        "other-event.md",
        catalog_title,
        conference=provider_conference,
        video_url=None,
        youtube_id=None,
    )
    report = audit_source_identities.audit_database(
        {"talks": [active, known_other_event]},
        database_path="/vault/tracking-database.json",
        metadata_fetcher=lambda video_id: metadata(
            video_id,
            title=provider_title,
        ),
        captured_at=CAPTURED_AT,
    )

    assert "provider_title_mismatch" not in finding_codes(report)
    finding = next(
        item for item in report["findings"] if item["code"] == "provider_event_mismatch"
    )
    assert finding["review_priority"] == "high"
    assert finding["evidence"]["catalog_conference"] == catalog_conference
    assert finding["evidence"]["provider_event_aliases"] == [
        " ".join(provider_conference.casefold().split()[:-1])
    ]
    assert report["talks"][0]["comparison"]["catalog_event_agrees"] is False


@pytest.mark.parametrize(
    ("catalog_conference", "provider_title", "other_conferences"),
    [
        (
            "DevIgnition 2024",
            'Baruch Sadogursky — "DevOps Reframed: Embracing the Path"',
            ["DevOps"],
        ),
        (
            "JetConf 2016",
            "Synthetic Speaker - Java Puzzlers. The greatest hits",
            ["Java"],
        ),
        (
            "NFJS Webinar September 2023",
            "DevOps Reframed: Embracing the Path - NFJS Webinar",
            ["DevOps"],
        ),
        (
            "Vaadin Cruise Meetup 2026",
            "Back to the Future of Software at Vaadin JFokus Cruise 2026",
            ["JFokus 2026"],
        ),
        (
            "DevoxxFR",
            "Runtime Rumble: Tool Alpha vs. Java APIs | Devoxx France 2025",
            ["Devoxx", "Java"],
        ),
        (
            "AI Native DevCon 2026, London",
            "A Synthetic Talk at AIDevCon Java 2026",
            ["Java"],
        ),
        (
            "DevOpsDays Nashville 2019",
            "DevOps Theory vs. Practice at DevOps Days Nashville 2019",
            ["DevOps Nashville 2024"],
        ),
    ],
)
def test_event_matcher_ignores_live_generic_and_cobrand_false_positives(
    audit_source_identities, catalog_conference, provider_title, other_conferences
):
    active = talk(conference=catalog_conference)
    catalog_only = [
        talk(
            f"known-event-{index}.md",
            conference=conference,
            video_url=None,
            youtube_id=None,
        )
        for index, conference in enumerate(other_conferences)
    ]
    report = audit_source_identities.audit_database(
        {"talks": [active, *catalog_only]},
        database_path="/vault/tracking-database.json",
        metadata_fetcher=lambda video_id: metadata(
            video_id,
            title=provider_title,
        ),
        captured_at=CAPTURED_AT,
    )

    assert "provider_event_mismatch" not in finding_codes(report)


def test_short_matching_lightning_talk_is_not_automatically_called_a_clip(
    audit_source_identities,
):
    lightning = talk(
        title="Fast Lightning",
        duration_seconds=300,
    )
    report = audit_source_identities.audit_database(
        {"talks": [lightning]},
        database_path="/vault/tracking-database.json",
        metadata_fetcher=lambda video_id: metadata(
            video_id,
            title="Fast Lightning",
            duration=240,
        ),
        captured_at=CAPTURED_AT,
    )
    assert "likely_non_delivery_clip" not in finding_codes(report)


def test_fetch_order_and_report_are_deterministic(audit_source_identities):
    database = {
        "talks": [
            talk(
                "other.md",
                "Other Talk",
                video_url=f"https://youtu.be/{OTHER_VIDEO_ID}",
                youtube_id=OTHER_VIDEO_ID,
            ),
            talk("first.md"),
            talk("same-id.md", video_url=f"https://youtu.be/{VIDEO_ID}"),
        ]
    }
    calls = []

    def fetcher(video_id):
        calls.append(video_id)
        return metadata(
            video_id,
            title=(
                "Other Talk" if video_id == OTHER_VIDEO_ID else "Perfect Vault Ingress"
            ),
        )

    first = audit_source_identities.audit_database(
        deepcopy(database),
        database_path="/vault/tracking-database.json",
        metadata_fetcher=fetcher,
        captured_at=CAPTURED_AT,
    )
    second = audit_source_identities.audit_database(
        deepcopy(database),
        database_path="/vault/tracking-database.json",
        metadata_fetcher=fetcher,
        captured_at=CAPTURED_AT,
    )

    expected_order = sorted({VIDEO_ID, OTHER_VIDEO_ID})
    assert calls == expected_order + expected_order
    assert first == second
    assert [source["video_id"] for source in first["sources"]] == expected_order
    assert list(first["summary"]["by_code"]) == sorted(first["summary"]["by_code"])


def test_provider_identity_mismatch_blocks_evidence_proposal(audit_source_identities):
    report = audit_source_identities.audit_database(
        {"talks": [talk()]},
        database_path="/vault/tracking-database.json",
        metadata_fetcher=lambda video_id: metadata(OTHER_VIDEO_ID),
        captured_at=CAPTURED_AT,
    )

    assert report["complete"] is False
    assert "provider_video_id_mismatch" in finding_codes(report)
    assert "provider_webpage_identity_mismatch" in finding_codes(report)
    assert report["talks"][0]["proposed_evidence"] is None


def test_audit_path_leaves_database_bytes_unchanged(audit_source_identities, tmp_path):
    database_path = tmp_path / "tracking-database.json"
    database_path.write_text(
        json.dumps({"talks": [talk()]}, indent=2) + "\n",
        encoding="utf-8",
    )
    before = database_path.read_bytes()

    report = audit_source_identities.audit_path(
        database_path,
        metadata_fetcher=lambda video_id: metadata(video_id),
        captured_at=CAPTURED_AT,
    )

    assert report["complete"] is True
    assert database_path.read_bytes() == before


def test_inactive_stored_id_is_not_fetched_or_resurrected(audit_source_identities):
    database = {"talks": [talk(video_url=None)]}
    calls = []

    report = audit_source_identities.audit_database(
        database,
        database_path="/vault/tracking-database.json",
        metadata_fetcher=lambda video_id: calls.append(video_id),
        captured_at=CAPTURED_AT,
    )

    assert calls == []
    assert report["active_talk_count"] == 0
    assert report["metadata_fetch_count"] == 0
    assert report["talks"] == []


def test_future_tracking_database_is_not_fetched_or_rewritten(audit_source_identities):
    database = {
        "schema_version": 99,
        "future_inventory": {"records": "not-an-old-talks-array"},
    }
    before = json.dumps(database, sort_keys=True)
    calls = []

    report = audit_source_identities.audit_database(
        database,
        database_path="/vault/tracking-database.json",
        metadata_fetcher=lambda video_id: calls.append(video_id),
        captured_at=CAPTURED_AT,
    )

    assert calls == []
    assert "tracking_database_schema_unsupported" in finding_codes(report)
    assert "talks_shape_invalid" not in finding_codes(report)
    assert json.dumps(database, sort_keys=True) == before


def test_incomplete_provider_metadata_is_proposed_without_invented_values(
    audit_source_identities,
):
    report = audit_source_identities.audit_database(
        {"talks": [talk()]},
        database_path="/vault/tracking-database.json",
        metadata_fetcher=lambda video_id: metadata(
            video_id,
            uploader=None,
            uploader_id=None,
            upload_date=None,
        ),
        captured_at=CAPTURED_AT,
    )

    proposal = report["talks"][0]["proposed_evidence"]["source_identity"]
    assert report["complete"] is False
    assert "provider_metadata_incomplete" in finding_codes(report)
    assert "uploader" not in proposal
    assert "uploader_id" not in proposal
    assert "upload_date" not in proposal
    assert "speakers" not in proposal
    assert "recorded_date" not in proposal


def test_yt_dlp_fetch_is_dependency_injected_and_download_free(audit_source_identities):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(metadata()),
            stderr="",
        )

    result = audit_source_identities.fetch_youtube_metadata(
        VIDEO_ID,
        runner=runner,
    )

    assert result["id"] == VIDEO_ID
    command, kwargs = calls[0]
    assert command[0] == "yt-dlp"
    assert "--skip-download" in command
    assert "--no-playlist" in command
    assert command[-1].endswith(VIDEO_ID)
    assert kwargs == {
        "capture_output": True,
        "text": True,
        "check": False,
        "timeout": audit_source_identities.YT_DLP_TIMEOUT_SECONDS,
    }


def test_capture_timestamp_requires_explicit_timezone(audit_source_identities):
    with pytest.raises(ValueError, match="timezone"):
        audit_source_identities.normalize_captured_at("2026-07-31T12:00:00")
    assert (
        audit_source_identities.normalize_captured_at("2026-07-31T14:00:00-05:00")
        == CAPTURED_AT
    )


def test_cli_failure_emits_json_and_actionable_stderr(
    audit_source_identities, monkeypatch, capsys
):
    report = {
        "complete": False,
        "findings": [{"code": "metadata_fetch_failed"}],
    }
    monkeypatch.setattr(
        audit_source_identities,
        "audit_path",
        lambda *args, **kwargs: report,
    )

    exit_code = audit_source_identities.main(["/vault"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert json.loads(captured.out) == report
    assert "review report findings" in captured.err
    assert "rerun" in captured.err


# Candidate mode (#230). A shownotes conflict names a competing source; the
# auditor compares it against the active one through the same bounded fetching,
# evidence shape, and no-write guarantee, and never promotes it.

CANDIDATE_ID = "QqWwEeRrT_3"


def scan_report(*entries):
    return {"schema_version": 1, "ok": True, "entries": list(entries)}


def conflict_entry(filename="talk.md", candidate_id=CANDIDATE_ID, lane="video_url"):
    url = (
        f"https://www.youtube.com/watch?v={candidate_id}"
        if lane == "video_url"
        else "https://drive.google.com/file/d/abc/view"
    )
    return {
        "filename": filename,
        "disposition": "review_required",
        "proposal": {lane: url},
        "changes": {},
        "issues": [
            {
                "code": f"existing_{lane}_conflict",
                "field": lane,
                "message": "tracking DB conflicts with shownotes",
            }
        ],
        "applied": False,
    }


def _audit(audit_source_identities, database, report, fetcher=None):
    calls = []

    def default_fetcher(video_id):
        calls.append(video_id)
        return metadata(video_id)

    result = audit_source_identities.audit_database(
        database,
        database_path="/vault/tracking-database.json",
        metadata_fetcher=fetcher or default_fetcher,
        captured_at=CAPTURED_AT,
        candidate_report=report,
    )
    return result, calls


def test_active_and_candidate_both_get_comparable_provider_evidence(
    audit_source_identities,
):
    """Acceptance 1: both sides of the conflict carry the same evidence shape."""
    database = {"talks": [talk()]}

    report, calls = _audit(
        audit_source_identities, database, scan_report(conflict_entry())
    )

    assert sorted(calls) == sorted([VIDEO_ID, CANDIDATE_ID])
    entry = report["candidates"][0]
    assert entry["filename"] == "talk.md"
    assert entry["candidate_youtube_id"] == CANDIDATE_ID
    assert entry["same_source_as_active"] is False
    assert entry["provider_evidence"]["video_id"] == CANDIDATE_ID
    assert entry["active_provider_evidence"]["video_id"] == VIDEO_ID
    # Same keys on both sides: comparison is field-for-field, not shape-guessing.
    assert set(entry["provider_evidence"]) == set(entry["active_provider_evidence"])


def test_a_candidate_repeated_across_conflicts_is_fetched_once(
    audit_source_identities,
):
    """Acceptance 2: dedupe spans talks and both lanes."""
    database = {"talks": [talk("first.md"), talk("second.md", date="2025-04-10")]}

    report, calls = _audit(
        audit_source_identities,
        database,
        scan_report(conflict_entry("first.md"), conflict_entry("second.md")),
    )

    assert calls.count(CANDIDATE_ID) == 1
    assert [item["filename"] for item in report["candidates"]] == [
        "first.md",
        "second.md",
    ]
    assert {item["provider_evidence"]["video_id"] for item in report["candidates"]} == {
        CANDIDATE_ID
    }


def test_an_unsupported_candidate_lane_is_a_lane_local_finding(
    audit_source_identities,
):
    """Acceptance 3: a slides candidate has no provider identity to audit."""
    database = {"talks": [talk()]}

    report, calls = _audit(
        audit_source_identities,
        database,
        scan_report(conflict_entry(lane="slides_url")),
    )

    assert calls == [VIDEO_ID]
    assert "candidate_provider_unsupported" in finding_codes(report)
    assert report["candidates"] == []


def test_a_malformed_candidate_url_is_a_lane_local_finding(audit_source_identities):
    database = {"talks": [talk()]}
    entry = conflict_entry()
    entry["proposal"]["video_url"] = "https://www.youtube.com/watch?v=nope"

    report, calls = _audit(audit_source_identities, database, scan_report(entry))

    assert calls == [VIDEO_ID]
    assert "candidate_youtube_url_invalid" in finding_codes(report)
    assert report["candidates"][0]["provider_evidence"] is None


def test_an_unavailable_candidate_stays_a_structured_finding(audit_source_identities):
    """A provider failure on the candidate must not sink the whole audit."""
    database = {"talks": [talk()]}

    def fetcher(video_id):
        if video_id == CANDIDATE_ID:
            raise audit_source_identities.MetadataFetchError("HTTP 429 rate limited")
        return metadata(video_id)

    report, _calls = _audit(
        audit_source_identities, database, scan_report(conflict_entry()), fetcher
    )

    assert "metadata_fetch_failed" in finding_codes(report)
    failed = [item for item in report["sources"] if item["video_id"] == CANDIDATE_ID]
    assert failed[0]["fetch_status"] == "error"
    assert report["candidates"][0]["provider_evidence"] is None
    assert report["candidates"][0]["active_provider_evidence"]["video_id"] == VIDEO_ID


@pytest.mark.parametrize(
    ("report_value", "code"),
    [
        ("not an object", "candidate_report_invalid"),
        ({"schema_version": 1}, "candidate_report_invalid"),
        ({"entries": [{"disposition": "review_required"}]}, "candidate_report_invalid"),
    ],
)
def test_an_invalid_report_fails_before_any_provider_request(
    audit_source_identities, report_value, code
):
    """Acceptance 4: a bad binding must not cost a fetch."""
    database = {"talks": [talk()]}
    calls = []

    def fetcher(video_id):
        calls.append(video_id)
        return metadata(video_id)

    report = audit_source_identities.audit_database(
        database,
        database_path="/vault/tracking-database.json",
        metadata_fetcher=fetcher,
        captured_at=CAPTURED_AT,
        candidate_report=report_value,
    )

    assert code in finding_codes(report)
    # The active lane still audits; only the candidate binding was refused.
    assert calls == [VIDEO_ID]
    assert report["candidates"] == []


def test_a_candidate_naming_no_unique_talk_is_refused(audit_source_identities):
    database = {"talks": [talk("first.md"), talk("first.md", date="2025-04-10")]}

    report, _calls = _audit(
        audit_source_identities, database, scan_report(conflict_entry("first.md"))
    )

    assert "candidate_binding_invalid" in finding_codes(report)
    assert report["candidates"] == []


def test_candidate_mode_never_mutates_the_database(audit_source_identities):
    """Acceptance 5: read-only, candidates included."""
    database = {"talks": [talk()]}
    original = deepcopy(database)

    _audit(audit_source_identities, database, scan_report(conflict_entry()))

    assert database == original


def test_a_candidate_equal_to_the_active_source_is_reported_as_the_same_source(
    audit_source_identities,
):
    database = {"talks": [talk()]}

    report, calls = _audit(
        audit_source_identities,
        database,
        scan_report(conflict_entry(candidate_id=VIDEO_ID)),
    )

    assert calls == [VIDEO_ID]
    assert report["candidates"][0]["same_source_as_active"] is True


def test_a_repeated_candidate_does_not_fabricate_an_active_collision(
    audit_source_identities,
):
    """The outcome the fetch-count assertion missed.

    `groups` is the ACTIVE-source assignment the cross-talk collision analysis
    reads. A candidate shared by two talks must not enter it, or the audit
    would claim one active identity is attached to both records.
    """
    database = {
        "talks": [
            talk("first.md", video_url=f"https://www.youtube.com/watch?v={VIDEO_ID}"),
            talk(
                "second.md",
                date="2025-04-10",
                video_url=f"https://www.youtube.com/watch?v={OTHER_VIDEO_ID}",
                youtube_id=OTHER_VIDEO_ID,
            ),
        ]
    }

    report, _calls = _audit(
        audit_source_identities,
        database,
        scan_report(conflict_entry("first.md"), conflict_entry("second.md")),
    )

    assert "same_id_cross_talk_collision" not in finding_codes(report)
    assert report["unique_youtube_id_count"] == 2
    assert report["metadata_fetch_count"] == 3
    shared = [item for item in report["sources"] if item["video_id"] == CANDIDATE_ID]
    assert shared[0]["lanes"] == ["candidate"]
    assert shared[0]["filenames"] == ["first.md", "second.md"]


def test_a_repeated_conflict_code_does_not_duplicate_a_candidate_row(
    audit_source_identities,
):
    database = {"talks": [talk()]}
    entry = conflict_entry()
    entry["issues"] = entry["issues"] * 2

    report, _calls = _audit(audit_source_identities, database, scan_report(entry))

    assert len(report["candidates"]) == 1


def test_a_candidate_matching_another_talks_active_source_names_both_lanes(
    audit_source_identities,
):
    database = {
        "talks": [
            talk("first.md"),
            talk(
                "second.md",
                date="2025-04-10",
                video_url=f"https://www.youtube.com/watch?v={OTHER_VIDEO_ID}",
                youtube_id=OTHER_VIDEO_ID,
            ),
        ]
    }

    report, calls = _audit(
        audit_source_identities,
        database,
        scan_report(conflict_entry("second.md", candidate_id=VIDEO_ID)),
    )

    assert calls.count(VIDEO_ID) == 1
    shared = [item for item in report["sources"] if item["video_id"] == VIDEO_ID]
    assert shared[0]["lanes"] == ["active", "candidate"]
