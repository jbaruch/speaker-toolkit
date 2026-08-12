"""Migration repairs or requeues corrupt observations — never stamps them (#167).

#147 migration stamped a talk as current record schema without ever reading the
nested detection objects, so a swapped-field block became "current" on the
strength of its container's shape.
"""

from __future__ import annotations

import copy

import pytest


@pytest.fixture(scope="module")
def gate(migrate_tracking_database):
    return migrate_tracking_database


def _database(talk: dict) -> dict:
    return {
        "schema_version": 1,
        "config": {"schema_version": 2, "pptx_directory_exclusions": []},
        "talks": [talk],
        "pptx_catalog": [],
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }


def _talk(observations: object, *, status: str = "processed") -> dict:
    return {
        "schema_version": 5,
        "filename": "talk.md",
        "status": status,
        "pattern_observations": observations,
    }


class TestRequeue:
    def test_a_corrupt_block_is_requeued_not_stamped(self, gate) -> None:
        database = _database(_talk({"patterns_detected": "not a list"}))

        counts = gate.gate_persisted_observations(database)

        assert counts["requeued"] == 1
        talk = database["talks"][0]
        assert talk["status"] == "needs-reprocessing"
        assert talk["reprocess_reason"] == gate.REQUEUE_REASON

    def test_a_requeued_talk_keeps_its_original_bytes(self, gate) -> None:
        """A defect the gate cannot undo without inventing a value is one an
        owner has to see; rewriting it would destroy that evidence."""
        original = {"patterns_detected": [{"pattern_id": "not-a-real-entry"}]}
        database = _database(_talk(copy.deepcopy(original)))

        gate.gate_persisted_observations(database)

        assert database["talks"][0]["pattern_observations"] == original


class TestScope:
    def test_a_talk_not_claiming_analysis_is_untouched(self, gate) -> None:
        database = _database(
            _talk({"patterns_detected": "not a list"}, status="pending")
        )

        counts = gate.gate_persisted_observations(database)

        assert counts == {"repaired": 0, "requeued": 0}
        assert database["talks"][0]["status"] == "pending"

    def test_an_absent_block_is_incompleteness_not_corruption(self, gate) -> None:
        """Requeueing every talk that predates pattern scoring would flood a
        queue that is working — the boundary preflight already draws."""
        database = _database(_talk(None))

        counts = gate.gate_persisted_observations(database)

        assert counts == {"repaired": 0, "requeued": 0}
        assert database["talks"][0]["status"] == "processed"

    def test_a_database_without_talks_is_a_no_op(self, gate) -> None:
        assert gate.gate_persisted_observations({}) == {
            "repaired": 0,
            "requeued": 0,
        }


class TestOutcomesAreExclusive:
    def test_a_talk_is_never_both_repaired_and_requeued(self, gate) -> None:
        database = _database(_talk({"patterns_detected": "not a list"}))

        counts = gate.gate_persisted_observations(database)

        assert counts["repaired"] + counts["requeued"] == 1

    def test_the_migration_report_carries_the_counts(self, gate, tmp_path) -> None:
        """A silent repair is indistinguishable from no corruption at all, so
        the report has to carry the counts — asserted through the real CLI
        entry point, not the constant."""
        import hashlib
        import json

        database = _database(_talk({"patterns_detected": "not a list"}))
        path = tmp_path / "tracking-database.json"
        raw = (json.dumps(database, indent=2) + "\n").encode("utf-8")
        path.write_bytes(raw)

        report = gate.execute(
            path, apply=True, expected_sha256=hashlib.sha256(raw).hexdigest()
        )

        assert report["persisted_observations"] == {"repaired": 0, "requeued": 1}
        assert report["changed"] is True
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["talks"][0]["status"] == "needs-reprocessing"


class TestLosslessRepair:
    """The one signature repairable without inventing a value."""

    def _swapped_talk(self, entry) -> dict:
        prose = "The speaker opened with the map, at 00:41."
        collection = (
            "antipatterns_detected"
            if entry.entry_type == "antipattern"
            else "patterns_detected"
        )
        return _talk(
            {
                "patterns_detected": [],
                "antipatterns_detected": [],
                "not_evaluable": [],
                collection: [
                    {
                        "pattern_id": entry.pattern_id,
                        "confidence": "strong",
                        # Both fields satisfy the other's schema exactly.
                        "evidence": list(entry.vault_dimensions),
                        "dimensions": prose,
                    }
                ],
            }
        )

    def _entry(self, catalog):
        for entry in sorted(catalog.entries.values(), key=lambda i: i.pattern_id):
            if entry.observable and len(entry.vault_dimensions) >= 2:
                return entry
        raise AssertionError("catalog has no observable entry with two dimensions")

    def test_an_exact_swap_is_undone_in_place(self, gate, return_validation) -> None:
        entry = self._entry(return_validation.load_catalog())
        database = _database(self._swapped_talk(entry))

        counts = gate.gate_persisted_observations(database)

        assert counts == {"repaired": 1, "requeued": 0}

    def test_the_repaired_talk_keeps_claiming_its_analysis(
        self, gate, return_validation
    ) -> None:
        """A repair restores the record; it does not send it back to the queue."""
        entry = self._entry(return_validation.load_catalog())
        database = _database(self._swapped_talk(entry))

        gate.gate_persisted_observations(database)

        talk = database["talks"][0]
        assert talk["status"] == "processed"
        assert "reprocess_reason" not in talk

    def test_both_values_land_where_they_belong(self, gate, return_validation) -> None:
        entry = self._entry(return_validation.load_catalog())
        prose = "The speaker opened with the map, at 00:41."
        database = _database(self._swapped_talk(entry))

        gate.gate_persisted_observations(database)

        block = database["talks"][0]["pattern_observations"]
        collection = (
            block["antipatterns_detected"]
            if entry.entry_type == "antipattern"
            else block["patterns_detected"]
        )
        assert collection[0]["evidence"] == prose
        assert collection[0]["dimensions"] == list(entry.vault_dimensions)
