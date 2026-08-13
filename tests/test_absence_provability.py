"""The provable-set denominator behind never-used claims (#160, #153).

`absence_evaluable_from: null` means absence is not provable for that pattern
and never falls back to the presence gate. Never-used and underused are computed
over the populated-gate entries only, so the denominator has to travel with them
— otherwise a short never-used list reads as a statement about the speaker when
it is mostly a statement about coverage.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _no_policy_override(runtime):
    """The bundled default policy — no on-disk override for this test run."""
    return runtime.resolve_classification_policy(
        Path(__file__).resolve().parent / "__no_policy_override__"
    )


@pytest.fixture(scope="module")
def classification_runtime(profile_pattern_provenance):
    # Depends on profile_pattern_provenance for its import side effect: that
    # fixture puts the vault-profile scripts directory on the path, which is what
    # makes this plain module import resolve.
    del profile_pattern_provenance
    return importlib.import_module("pattern_classification_runtime")


@pytest.fixture(scope="module")
def pattern_catalog(return_validation):
    return return_validation.load_catalog()


@pytest.fixture(scope="module")
def provability(profile_pattern_provenance, pattern_catalog):
    return profile_pattern_provenance.absence_provability(pattern_catalog)


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
    """An unused helper is not a contract — the reason this was rejected once.

    Asserted against the writer's emitted payload, not its source text. Matching
    a call expression in `inspect.getsource` passes for code that is never
    reached and fails for a correct refactor, so it measures the spelling rather
    than the behaviour.
    """

    def test_the_profile_writer_emits_the_denominator(
        self, classification_runtime, pattern_catalog
    ) -> None:
        emitted = classification_runtime.classify_pattern_profile(
            [], _no_policy_override(classification_runtime), catalog=pattern_catalog
        )

        assert "absence_provability" in emitted
        assert set(emitted["absence_provability"]) == {
            "schema_version",
            "absence_provable_count",
            "absence_unknowable_count",
            "observable_count",
        }

    def test_the_emitted_counts_match_the_live_catalog(
        self, classification_runtime, pattern_catalog, provability
    ) -> None:
        """The writer reports the catalog it actually ran against."""
        emitted = classification_runtime.classify_pattern_profile(
            [], _no_policy_override(classification_runtime), catalog=pattern_catalog
        )

        assert emitted["absence_provability"] == provability

    def test_the_writer_stamps_the_generation_that_carries_it(
        self, classification_runtime, pattern_catalog, profile_pattern_provenance
    ) -> None:
        """The field and its version stamp are emitted together or not at all."""
        emitted = classification_runtime.classify_pattern_profile(
            [], _no_policy_override(classification_runtime), catalog=pattern_catalog
        )

        assert (
            emitted["classification_schema_version"]
            == profile_pattern_provenance.CLASSIFICATION_SCHEMA_VERSION
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
