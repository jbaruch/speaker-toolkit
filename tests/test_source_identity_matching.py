"""Focused tests for the shared source-identity matching contracts."""

from __future__ import annotations

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
