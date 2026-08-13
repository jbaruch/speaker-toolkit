"""The prose-scan guardrail's status mapping (#287).

The scan belongs to `blog-writer`. This script owns only what happens to its
counts, which is a total function of two integers — so it is a script rather than
a threshold sentence in skill prose that drifts from the one anybody applies.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "presentation-creator"
    / "scripts"
    / "classify-prose-scan.py"
)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


class TestTheBoundaries:
    """Every threshold, from both sides."""

    @pytest.mark.parametrize(
        ("high", "medium", "expected"),
        [
            (0, 0, "PASS"),
            (0, 2, "PASS"),
            (0, 3, "WARN"),
            (1, 0, "WARN"),
            (3, 0, "WARN"),
            (3, 99, "WARN"),
            (4, 0, "FAIL"),
            (9, 9, "FAIL"),
        ],
    )
    def test_counts_map_to_a_status(
        self, classify_prose_scan, high, medium, expected
    ) -> None:
        assert classify_prose_scan.classify(high, medium) == expected

    def test_a_single_high_finding_ends_pass(self, classify_prose_scan) -> None:
        """One confident finding is worth reading, whatever the mediums say."""
        assert classify_prose_scan.classify(0, 0) == "PASS"
        assert classify_prose_scan.classify(1, 0) != "PASS"

    def test_mediums_escalate_only_in_a_cluster(self, classify_prose_scan) -> None:
        """Any long passage collects a couple; three is a pattern."""
        assert classify_prose_scan.classify(0, 2) == "PASS"
        assert classify_prose_scan.classify(0, 3) == "WARN"


class TestAnAbsentScannerIsNeverAPass:
    def test_unavailable_reports_skip(self, classify_prose_scan) -> None:
        report = classify_prose_scan.unavailable_report()

        assert report["status"] == "SKIP"
        assert report["scanner_available"] is False
        assert report["high"] is None and report["medium"] is None

    def test_it_says_how_to_get_the_scanner(self, classify_prose_scan) -> None:
        """A skip the author cannot act on is just a silent gap."""
        assert "tessl install" in classify_prose_scan.unavailable_report()["remedy"]

    def test_a_zero_count_scan_is_a_pass_not_a_skip(self, classify_prose_scan) -> None:
        """Clean prose and an absent scanner are different outcomes."""
        assert classify_prose_scan.report(high=0, medium=0)["status"] == "PASS"
        assert classify_prose_scan.unavailable_report()["status"] == "SKIP"


class TestTheCommandLineContract:
    def test_counts_emit_one_json_object_and_exit_zero(self) -> None:
        result = _run("--high", "1", "--medium", "0")

        assert result.returncode == 0
        assert json.loads(result.stdout)["status"] == "WARN"

    def test_a_fail_still_exits_zero(self) -> None:
        """FAIL is a finding, not a run failure."""
        result = _run("--high", "4", "--medium", "0")

        assert result.returncode == 0
        assert json.loads(result.stdout)["status"] == "FAIL"

    def test_unavailable_emits_the_skip_report(self) -> None:
        result = _run("--unavailable")

        assert result.returncode == 0
        assert json.loads(result.stdout)["status"] == "SKIP"

    def test_missing_counts_exit_non_zero_with_a_diagnostic(self) -> None:
        result = _run("--high", "1")

        assert result.returncode != 0
        assert result.stdout == ""
        assert "blog-writer" in result.stderr

    def test_counts_beside_unavailable_are_refused(self) -> None:
        """An absent scanner produced no counts, so supplying them is a lie."""
        result = _run("--unavailable", "--high", "1", "--medium", "0")

        assert result.returncode != 0
        assert result.stderr.strip()

    def test_a_negative_count_is_refused(self) -> None:
        result = _run("--high", "-1", "--medium", "0")

        assert result.returncode != 0

    def test_the_script_is_importable_without_running(
        self, classify_prose_scan
    ) -> None:
        """file-hygiene -> Standalone Scripts: the entry-point guard makes it so."""
        assert classify_prose_scan.REPORT_SCHEMA_VERSION == 1
