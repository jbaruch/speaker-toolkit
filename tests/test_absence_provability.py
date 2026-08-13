"""The provable-set denominator behind never-used claims (#160, #153).

`absence_evaluable_from: null` means absence is not provable for that pattern
and never falls back to the presence gate. Never-used and underused are computed
over the populated-gate entries only, so the denominator has to travel with them
— otherwise a short never-used list reads as a statement about the speaker when
it is mostly a statement about coverage.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def provability(profile_pattern_provenance, return_validation):
    return profile_pattern_provenance.absence_provability(
        return_validation.load_catalog()
    )


class _Entry:
    def __init__(self, observable: bool, gate: object) -> None:
        self.observable = observable
        self.absence_evaluable_from = gate


class _Catalog:
    def __init__(self, entries: dict) -> None:
        self.entries = entries


class TestLiveCatalog:
    def test_the_counts_partition_the_observable_catalog(self, provability) -> None:
        assert (
            provability["absence_provable_count"]
            + provability["absence_unknowable_count"]
            == provability["observable_count"]
        )

    def test_absence_is_unprovable_for_most_of_the_catalog(self, provability) -> None:
        """The fact that makes the denominator load-bearing rather than trivia."""
        assert (
            provability["absence_unknowable_count"]
            > provability["absence_provable_count"]
        )

    def test_it_is_computed_not_hardcoded(
        self, profile_pattern_provenance, return_validation
    ) -> None:
        """A catalog edit that populates a gate must move these counts."""
        catalog = return_validation.load_catalog()
        observable = [entry for entry in catalog.entries.values() if entry.observable]
        computed = profile_pattern_provenance.absence_provability(catalog)
        assert computed["observable_count"] == len(observable)


class TestPartition:
    def test_a_null_gate_is_unknowable(self, profile_pattern_provenance) -> None:
        catalog = _Catalog({"a": _Entry(True, None)})

        result = profile_pattern_provenance.absence_provability(catalog)

        assert result["absence_unknowable_count"] == 1
        assert result["absence_provable_count"] == 0

    def test_a_populated_gate_is_provable(self, profile_pattern_provenance) -> None:
        catalog = _Catalog({"a": _Entry(True, ("static_slides",))})

        result = profile_pattern_provenance.absence_provability(catalog)

        assert result["absence_provable_count"] == 1
        assert result["absence_unknowable_count"] == 0

    def test_an_unobservable_entry_is_in_neither_count(
        self, profile_pattern_provenance
    ) -> None:
        """It is not scored at all, so it belongs to no denominator."""
        catalog = _Catalog(
            {"a": _Entry(False, None), "b": _Entry(False, ("transcript",))}
        )

        result = profile_pattern_provenance.absence_provability(catalog)

        assert result["observable_count"] == 0

    def test_an_empty_catalog_reports_zeroes(self, profile_pattern_provenance) -> None:
        result = profile_pattern_provenance.absence_provability(_Catalog({}))

        assert result["observable_count"] == 0
        assert result["absence_provable_count"] == 0


class TestTheWriterEmitsIt:
    """An unused helper is not a contract — the reason this was rejected once."""

    def test_the_profile_writer_emits_the_denominator(
        self, classify_pattern_profile
    ) -> None:
        import inspect

        source = inspect.getsource(classify_pattern_profile)
        assert '"absence_provability": absence_provability(' in source

    def test_the_validator_accepts_a_profile_carrying_it(
        self, profile_pattern_provenance
    ) -> None:
        assert (
            "absence_provability"
            in profile_pattern_provenance._OPTIONAL_PATTERN_PROFILE_FIELDS
        )

    def test_it_is_not_required_of_profiles_written_before_it(
        self, profile_pattern_provenance
    ) -> None:
        """Requiring it would refuse to read every profile already on disk — a
        bigger break than the gap it closes."""
        assert (
            "absence_provability"
            not in profile_pattern_provenance._V5_PATTERN_PROFILE_FIELDS
        )


class TestSchemaVersioning:
    """A shape change to a persisted artifact bumps its governing version."""

    def test_the_classification_contract_bumped(
        self, profile_pattern_provenance
    ) -> None:
        assert profile_pattern_provenance.CLASSIFICATION_SCHEMA_VERSION == 2

    def test_the_writer_stamps_the_new_version(
        self, classify_pattern_profile, profile_pattern_provenance
    ) -> None:
        """Writer and reader share one constant, not two copies."""
        assert (
            classify_pattern_profile.CLASSIFICATION_SCHEMA_VERSION
            == profile_pattern_provenance.CLASSIFICATION_SCHEMA_VERSION
        )

    def test_a_v1_block_stays_readable(self, profile_pattern_provenance) -> None:
        """The counts are a fact about the catalog, not a claim the older block
        got something wrong — refusing v1 would strand every profile on disk."""
        readable = profile_pattern_provenance.READABLE_CLASSIFICATION_SCHEMA_VERSIONS
        assert 1 in readable
        assert profile_pattern_provenance.CLASSIFICATION_SCHEMA_VERSION in readable


class TestTheEmittedObjectValidates:
    """The writer's own output has to satisfy the reader's contract.

    Shape and version rejection are exercised through `assess_pattern_profile` in
    `test_profile_pattern_provenance.py` — a malformed object matters only insofar
    as it reaches a reader, and the version gate is only observable on the real
    call path.
    """

    def test_the_computed_object_is_a_valid_persisted_shape(
        self, profile_pattern_provenance
    ) -> None:
        computed = profile_pattern_provenance.absence_provability(_Catalog({}))

        assert set(computed) == {
            "schema_version",
            "absence_provable_count",
            "absence_unknowable_count",
            "observable_count",
        }
        assert (
            computed["schema_version"]
            == profile_pattern_provenance.ABSENCE_PROVABILITY_SCHEMA_VERSION
        )

    def test_the_version_floor_is_the_generation_that_introduced_it(
        self, profile_pattern_provenance
    ) -> None:
        """Pinned to the introducing generation, not the current one — a later
        classification bump must not start rejecting version 2."""
        assert (
            profile_pattern_provenance.ABSENCE_PROVABILITY_MIN_CLASSIFICATION_SCHEMA_VERSION
            == 2
        )
