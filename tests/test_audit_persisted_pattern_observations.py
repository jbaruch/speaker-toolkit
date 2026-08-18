"""The standalone persisted-observation audit CLI (#167, last criterion).

The assessor was only ever reachable in-flow: seven consumers call it to decide
something about one talk and move on. Nothing could answer "what is wrong with
this corpus, in total, before anyone touches it", which is what the criterion
asks for and what the reparse decision needs BEFORE the migration runs.

These tests build databases from the live catalog rather than hardcoded IDs, so
a catalog edit that removes an entry fails them instead of quietly
reclassifying what they assert.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "vault-ingress" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load_script(module_name: str, filename: str):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_script(
    "audit_persisted_pattern_observations",
    "audit-persisted-pattern-observations.py",
)


@pytest.fixture(scope="session")
def catalog(return_validation):
    return return_validation.load_catalog()


@pytest.fixture(scope="session")
def observable_entry(catalog):
    for entry in sorted(catalog.entries.values(), key=lambda item: item.pattern_id):
        if entry.observable and len(entry.vault_dimensions) >= 2:
            return entry
    raise AssertionError("catalog has no observable entry with two dimensions")


def _detection(entry, **overrides) -> dict[str, Any]:
    detection = {
        "pattern_id": entry.pattern_id,
        "confidence": "strong",
        "evidence": "The speaker did the thing, at 12:03.",
        "dimensions": list(entry.vault_dimensions),
    }
    detection.update(overrides)
    return detection


def _lane(entry) -> str:
    return (
        "antipatterns_detected"
        if entry.entry_type == "antipattern"
        else "patterns_detected"
    )


def _talk(filename: str, entry, *detections) -> dict[str, Any]:
    block: dict[str, Any] = {
        "patterns_detected": [],
        "antipatterns_detected": [],
        "not_evaluable": [],
    }
    block[_lane(entry)] = list(detections)
    return {"filename": filename, "pattern_observations": block}


def _database(tmp_path: Path, talks: list[dict[str, Any]]) -> Path:
    path = tmp_path / "tracking-database.json"
    path.write_text(json.dumps({"schema_version": 1, "talks": talks}))
    return path


def _swapped(entry) -> dict[str, Any]:
    """The 28-record live signature: `evidence` and `dimensions` exchanged."""
    return _detection(
        entry,
        evidence=list(entry.vault_dimensions),
        dimensions="The speaker did the thing, at 12:03.",
    )


class TestTheReportAnswersTheCorpusQuestion:
    def test_a_clean_corpus_reports_usable(self, tmp_path, observable_entry) -> None:
        path = _database(
            tmp_path,
            [_talk("a.md", observable_entry, _detection(observable_entry))],
        )

        report = audit.audit_database(path)

        assert report["usable"] is True
        assert report["summary"] == {
            "talks_assessed": 1,
            "talks_usable": 1,
            "talks_unusable": 0,
        }
        assert report["reason_counts"] == {}

    def test_it_counts_and_names_every_defective_talk(
        self, tmp_path, observable_entry
    ) -> None:
        """A count says how bad; the filenames say where. Reporting only the
        count leaves an owner unable to act on it."""
        path = _database(
            tmp_path,
            [
                _talk("clean.md", observable_entry, _detection(observable_entry)),
                _talk("swapped.md", observable_entry, _swapped(observable_entry)),
            ],
        )

        report = audit.audit_database(path)

        assert report["usable"] is False
        assert report["summary"]["talks_assessed"] == 2
        assert report["summary"]["talks_unusable"] == 1
        assert report["unusable_filenames"] == ["swapped.md"]
        assert sum(report["reason_counts"].values()) >= 1
        for names in report["reason_filenames"].values():
            assert names == ["swapped.md"]

    def test_a_talk_with_no_observations_is_reported_not_skipped(
        self, tmp_path
    ) -> None:
        """9 of 209 live talks carried no block. Silence would have read as
        nine clean talks."""
        path = _database(tmp_path, [{"filename": "bare.md"}])

        report = audit.audit_database(path)

        assert report["summary"]["talks_unusable"] == 1
        assert report["unusable_filenames"] == ["bare.md"]

    def test_a_talk_whose_filename_is_unusable_is_still_named(
        self, tmp_path, observable_entry
    ) -> None:
        """A malformed record is the kind this audit exists to surface, so it
        must not be the one entry the report cannot identify."""
        talk = _talk("ignored.md", observable_entry, _swapped(observable_entry))
        del talk["filename"]
        path = _database(tmp_path, [talk])

        report = audit.audit_database(path)

        assert report["unusable_filenames"] == ["talks[0]"]

    def test_two_runs_over_one_database_are_byte_identical(
        self, tmp_path, observable_entry
    ) -> None:
        """The criterion says attach deterministic counts to a report. A diff
        between two runs has to be a real change, not dict ordering."""
        path = _database(
            tmp_path,
            [
                _talk("b.md", observable_entry, _swapped(observable_entry)),
                _talk("a.md", observable_entry, _swapped(observable_entry)),
            ],
        )

        first = json.dumps(audit.audit_database(path), sort_keys=True)
        second = json.dumps(audit.audit_database(path), sort_keys=True)

        assert first == second


class TestTheProcessContract:
    def test_a_clean_corpus_exits_zero(
        self, tmp_path, observable_entry, capsys
    ) -> None:
        path = _database(
            tmp_path,
            [_talk("a.md", observable_entry, _detection(observable_entry))],
        )

        status = audit.run_cli([str(path)])

        assert status == 0
        assert json.loads(capsys.readouterr().out)["usable"] is True

    def test_defects_exit_one_with_the_report_still_on_stdout(
        self, tmp_path, observable_entry, capsys
    ) -> None:
        """Exit 1 is a finding about the corpus, not a failure of the audit, so
        the report an owner needs must still be there."""
        path = _database(
            tmp_path,
            [_talk("swapped.md", observable_entry, _swapped(observable_entry))],
        )

        status = audit.run_cli([str(path)])

        captured = capsys.readouterr()
        assert status == 1
        assert json.loads(captured.out)["unusable_filenames"] == ["swapped.md"]
        assert "before migration or reparse" in captured.err

    def test_an_unreadable_database_exits_three_with_empty_stdout(
        self, tmp_path, capsys
    ) -> None:
        """Distinct from exit 1. A broken auditor must not read as a corpus
        full of defects."""
        status = audit.run_cli([str(tmp_path / "absent.json")])

        captured = capsys.readouterr()
        assert status == 3
        assert captured.out == ""
        # stderr is one closed JSON document followed by the operator recovery
        # note, so only the first line is the document.
        document = json.loads(captured.err.splitlines()[0])
        assert document["error"] == "persisted_observation_audit_unexpected_failure"
        assert "UNAUDITED" in captured.err

    def test_a_file_that_is_not_a_tracking_database_exits_three(
        self, tmp_path, capsys
    ) -> None:
        path = tmp_path / "profile.json"
        path.write_text(json.dumps({"schema_version": 1, "speaker": "someone"}))

        status = audit.run_cli([str(path)])

        assert status == 3
        assert capsys.readouterr().out == ""

    def test_it_never_writes_to_the_database(self, tmp_path, observable_entry) -> None:
        """Read-only is the reason it is safe to point at a copy of a live
        vault, so it is worth asserting rather than assuming."""
        path = _database(
            tmp_path,
            [_talk("swapped.md", observable_entry, _swapped(observable_entry))],
        )
        before = path.read_bytes()

        audit.run_cli([str(path)])

        assert path.read_bytes() == before
