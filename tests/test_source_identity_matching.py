"""Focused tests for the shared source-identity matching contracts."""

from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO_ROOT / "skills" / "vault-ingress" / "scripts" / "source_identity_matching.py"
)
SPEC = importlib.util.spec_from_file_location("source_identity_matching", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
source_identity_matching = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source_identity_matching)


@pytest.mark.parametrize(
    ("authored_title", "shownotes_title", "expected"),
    [
        ("Kahneman\u2019s Shortcut", "Kahneman's Shortcut", True),
        ("Case Matters", "case matters", False),
        ("Quoted: Title", "Quoted Title", False),
    ],
)
def test_shownotes_title_presentation_rules_remain_narrow(
    authored_title: str,
    shownotes_title: str,
    expected: bool,
) -> None:
    assert (
        source_identity_matching.shownotes_titles_agree(
            authored_title,
            shownotes_title,
            conference=None,
            talk_date=None,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("shownotes_title", "conference", "talk_date", "expected"),
    [
        (
            "Never Trust a Monkey at Voxxed Luxembourg 2026",
            "Voxxed Days Luxembourg 2026",
            "2026-06-18",
            True,
        ),
        (
            "Never Trust a Monkey at Voxxed Days Luxembourg",
            "Voxxed Days Luxembourg 2026",
            "2026-06-18",
            True,
        ),
        (
            "Never Trust a Monkey at Java Meetup 2026",
            "Java Conference 2026",
            "2026-06-18",
            False,
        ),
        (
            "Never Trust a Monkey at DevOps Conference 2026",
            "DevOps Days 2026",
            "2026-06-18",
            False,
        ),
        (
            "Never Trust a Monkey at Source Conference 2026",
            "Open Source Summit 2026",
            "2026-06-18",
            False,
        ),
        (
            "Never Trust a Monkey at Luxembourg 2026",
            "Voxxed Days Luxembourg 2026",
            "2026-06-18",
            False,
        ),
        (
            "Never Trust a Monkey at Voxxed Days Luxembourg 2025",
            "Voxxed Days Luxembourg 2026",
            "2026-06-18",
            False,
        ),
        (
            "Never Trust a Monkey at Voxxed Days Luxembourg 2026",
            "Voxxed Days Luxembourg 2025",
            "2026-06-18",
            False,
        ),
        (
            "Never Trust a Monkey at Voxxed Days Luxembourg 2026",
            "Voxxed Days Luxembourg 2026",
            "20260618",
            False,
        ),
        (
            "Never Trust a Monkey at Voxxed Days Luxembourg 2",
            "Voxxed Days Luxembourg 2026",
            "2026-06-18",
            False,
        ),
        (
            "Never Trust a Monkey at Voxxed Days Luxembourg 99999",
            "Voxxed Days Luxembourg 2026",
            "2026-06-18",
            False,
        ),
        (
            "Never Trust a Monkey at Caf\u00e9Conf 2026",
            "Cafe\u0301Conf 2026",
            "2026-06-18",
            True,
        ),
        (
            "Never Trust a Monkey at Cafe\u0301Conf 2026",
            "Caf\u00e9Conf 2026",
            "2026-06-18",
            True,
        ),
        (
            "Never Trust a Monkey — Voxxed Days Luxembourg 2026",
            "Voxxed Days Luxembourg 2026",
            "2026-06-18",
            False,
        ),
        (
            "Never Trust a Monkey Returns at Voxxed Days Luxembourg 2026",
            "Voxxed Days Luxembourg 2026",
            "2026-06-18",
            False,
        ),
    ],
)
def test_shownotes_event_qualifier_requires_exact_base_event_and_year(
    shownotes_title: str,
    conference: str,
    talk_date: str,
    expected: bool,
) -> None:
    assert (
        source_identity_matching.shownotes_titles_agree(
            "Never Trust a Monkey",
            shownotes_title,
            conference=conference,
            talk_date=talk_date,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2014", (None, 2014)),
        (" 2014 ", (None, 2014)),
        ("2013-11-28", (date(2013, 11, 28), 2013)),
        ("November 2014", None),
        ("", None),
        (2014, None),
        (None, None),
    ],
)
def test_parse_catalog_date_keeps_a_bare_year_comparable(
    value: object,
    expected: tuple[date | None, int] | None,
) -> None:
    """A bare `YYYY` is a coarse delivery date, never an absent one."""
    assert source_identity_matching.parse_catalog_date(value) == expected


@pytest.mark.parametrize(
    ("upload", "catalog", "expected"),
    [
        # A bare-year catalog record still gates on the year it names.
        (date(2013, 11, 28), (None, 2014), True),
        (date(2014, 11, 28), (None, 2014), False),
        (date(2015, 1, 1), (None, 2014), False),
        # An exact catalog day gates at day precision.
        (date(2025, 11, 1), (date(2025, 11, 2), 2025), True),
        (date(2025, 11, 2), (date(2025, 11, 2), 2025), False),
        # An uncomparable side is unknown, never "does not predate".
        (None, (None, 2014), None),
        (date(2013, 11, 28), None, None),
    ],
)
def test_upload_predates_catalog_compares_at_the_records_own_precision(
    upload: date | None,
    catalog: tuple[date | None, int] | None,
    expected: bool | None,
) -> None:
    assert source_identity_matching.upload_predates_catalog(upload, catalog) is expected


@pytest.mark.parametrize(
    ("talk", "expected"),
    [
        ({"duration_seconds": 2700}, 2700.0),
        ({"video_duration_seconds": 1800}, 1800.0),
        ({"structured_data": {"recording_duration_seconds": 900}}, 900.0),
        # A later positive value is read past an unusable earlier one.
        ({"duration_seconds": 0, "video_duration_seconds": 1800}, 1800.0),
        ({"duration_seconds": -5, "talk_duration_seconds": 60}, 60.0),
        # `bool` is an `int`; `True` must not read as a one-second talk.
        ({"duration_seconds": True}, None),
        ({"duration_seconds": float("inf")}, None),
        ({"duration_seconds": "2700"}, None),
        ({"structured_data": "not-a-mapping"}, None),
        ({}, None),
    ],
)
def test_expected_duration_seconds_reads_the_first_usable_catalog_duration(
    talk: dict[str, object],
    expected: float | None,
) -> None:
    assert source_identity_matching.expected_duration_seconds(talk) == expected


EQUIVALENCE = [
    {
        "schema_version": 1,
        "video_id": "QS-_4k7o7A4",
        "provider_title": "JavaDay Kiev 2014: Spring - битва конфигураций",
        "reason": "cross_language_title",
        "evidence": "owner-reviewed translation",
        "verified_at": "2026-08-18T12:00:00Z",
    }
]


@pytest.mark.parametrize(
    ("video_id", "provider_title", "expected"),
    [
        # The reviewed pair, exactly as recorded.
        ("QS-_4k7o7A4", EQUIVALENCE[0]["provider_title"], True),
        # Whitespace and Unicode composition vary without changing what was read.
        ("QS-_4k7o7A4", f"  {EQUIVALENCE[0]['provider_title']}  ", True),
        # A different video must never ride another talk's approval.
        ("wd-mXqXdfk0", EQUIVALENCE[0]["provider_title"], False),
        # A provider that retitles again re-gates instead of staying approved.
        ("QS-_4k7o7A4", "JavaDay Kiev 2014: Spring config showdown", False),
        ("QS-_4k7o7A4", "", False),
    ],
)
def test_title_equivalence_matches_only_the_reviewed_video_and_title(
    video_id: str,
    provider_title: str,
    expected: bool,
) -> None:
    assert (
        source_identity_matching.title_equivalence_recorded(
            EQUIVALENCE,
            video_id=video_id,
            provider_title=provider_title,
        )
        is expected
    )


@pytest.mark.parametrize(
    "ledger",
    [None, [], "not-a-list", [None], [{"video_id": "QS-_4k7o7A4"}]],
)
def test_title_equivalence_treats_an_unusable_ledger_as_no_approval(
    ledger: object,
) -> None:
    assert (
        source_identity_matching.title_equivalence_recorded(
            ledger,
            video_id="QS-_4k7o7A4",
            provider_title=EQUIVALENCE[0]["provider_title"],
        )
        is False
    )


@pytest.mark.parametrize("version", [2, 0, None, True, "1", 1.0])
def test_an_unrecognized_equivalence_generation_never_suppresses_the_gate(
    version: object,
) -> None:
    """Unusable state is not an approval — what it would suppress is the gate."""
    record = dict(EQUIVALENCE[0])
    if version is None:
        del record["schema_version"]
    else:
        record["schema_version"] = version

    assert (
        source_identity_matching.title_equivalence_recorded(
            [record],
            video_id="QS-_4k7o7A4",
            provider_title=EQUIVALENCE[0]["provider_title"],
        )
        is False
    )


def test_pinned_provider_title_is_the_one_canonicalizer() -> None:
    """Reader and writer must agree on which titles are the same approval."""
    assert source_identity_matching.pinned_provider_title(
        "  Spring -  битва   конфигураций \n"
    ) == source_identity_matching.pinned_provider_title("Spring - битва конфигураций")
