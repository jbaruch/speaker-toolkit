"""The v5/v6 scoring boundary, asserted through the public validator (#153).

These drive `validate_return`, the entry point that owns schema resolution — a
test calling the private score helper proves the arithmetic but not that any
real return can reach it.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from test_schema5_pattern_outcomes import (  # noqa: E402
    _artifact,
    _assessment,
    _catalog,
    _detection,
    _entry,
    _raw_return,
)


@pytest.fixture(scope="module")
def catalog(return_validation):
    return _catalog(
        return_validation,
        _entry(return_validation, "detected"),
        _entry(return_validation, "undetected"),
        _entry(return_validation, "conditional", applicability=True),
    )


def _v5(**kwargs) -> dict[str, Any]:
    return _raw_return(detections=[_detection()], assessments=[_assessment()], **kwargs)


def _v6(rv, *, score=None, basis=None, drop_basis=False) -> dict[str, Any]:
    """A v6 return: the v5 shape with weighted arithmetic and its basis."""
    ret = copy.deepcopy(_v5())
    ret["return_schema_version"] = rv.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION
    block = ret["pattern_observations"]
    patterns = block["patterns_detected"]
    antipatterns = block["antipatterns_detected"]
    not_evaluable = block["not_evaluable"]
    weighted = rv.expected_weighted_score(patterns, antipatterns)
    block["pattern_score"] = {
        "patterns_used": len(patterns),
        "antipatterns_detected": len(antipatterns),
        "score": weighted if score is None else score,
    }
    if not drop_basis:
        block["pattern_score_basis"] = basis or rv.pattern_score_basis(
            patterns, antipatterns, not_evaluable
        )
    return ret


class TestV5KeepsFlatArithmetic:
    def test_a_flat_v5_return_validates(self, return_validation, catalog) -> None:
        """Its worker counted +1/-1; rescoring it would restate its meaning."""
        return_validation.validate_return(_v5(), catalog)

    def test_a_v5_return_cannot_carry_a_basis(self, return_validation, catalog) -> None:
        ret = _v5()
        ret["pattern_observations"]["pattern_score_basis"] = {"schema_version": 1}

        with pytest.raises(return_validation.ReturnValidationError):
            return_validation.validate_return(ret, catalog)


class TestV6IsAcceptedEndToEnd:
    def test_a_well_formed_v6_return_validates(
        self, return_validation, catalog
    ) -> None:
        """The contract is reachable: a real return resolves to v6 and passes."""
        return_validation.validate_return(_v6(return_validation), catalog)

    def test_a_v6_return_without_a_basis_is_rejected(
        self, return_validation, catalog
    ) -> None:
        with pytest.raises(
            return_validation.ReturnValidationError, match="pattern_score_basis"
        ):
            return_validation.validate_return(
                _v6(return_validation, drop_basis=True), catalog
            )

    def test_a_v6_score_that_ignores_the_weights_is_rejected(
        self, return_validation, catalog
    ) -> None:
        """A flat count in a v6 return is the defect the schema exists to stop."""
        with pytest.raises(
            return_validation.ReturnValidationError, match="detection arrays require"
        ):
            return_validation.validate_return(_v6(return_validation, score=99), catalog)

    def test_a_basis_contradicting_the_arrays_is_rejected(
        self, return_validation, catalog
    ) -> None:
        basis = return_validation.pattern_score_basis([], [], [])
        basis["patterns"] = {"strong": 9, "moderate": 0, "weak": 0}

        with pytest.raises(
            return_validation.ReturnValidationError, match="does not match"
        ):
            return_validation.validate_return(
                _v6(return_validation, basis=basis), catalog
            )


def _persist(return_validation, catalog, tmp_path, transcript_timing, ret):
    """Drive a raw return through the real canonicalization/persistence path.

    Not `canonical_persisted_pattern_observations(raw, ...)` — the raw return
    omits the engine-owned evidence fields on purpose, so calling persistence on
    it would test a shape no worker ever produces.
    """
    import pattern_evidence

    return_validation.validate_return(ret, catalog)
    vault, owner = _artifact(tmp_path, transcript_timing)
    canonical = pattern_evidence.canonicalize_return_evidence(
        copy.deepcopy(ret),
        owner,
        vault,
        catalog,
        pattern_scoring_schema_version=return_validation.PATTERN_SCORING_SCHEMA_VERSION,
    )
    generation = return_validation.assess_scoring_generation(canonical, catalog)
    return return_validation.canonical_persisted_pattern_observations(
        canonical, catalog, generation
    )


class TestV6IsRepresentableAsPersistedState:
    """An accepted return that persistence cannot represent is a broken contract.

    Accepting v6 at the validator while the persistence path still tested
    `== RETURN_SCHEMA_VERSION` meant a v6 return would have been stored with a
    legacy evidence stamp and no exhaustive outcomes at all — silently, since
    every check that would have caught it was gated on the same equality.
    """

    def test_the_basis_is_persisted_beside_the_score(
        self, return_validation, catalog, tmp_path, transcript_timing
    ) -> None:
        ret = _v6(return_validation)

        persisted = _persist(
            return_validation, catalog, tmp_path, transcript_timing, ret
        )

        assert (
            persisted["pattern_score_basis"]
            == (ret["pattern_observations"]["pattern_score_basis"])
        )
        assert (
            persisted["pattern_score"]
            == (ret["pattern_observations"]["pattern_score"]["score"])
        )

    def test_a_v5_return_persists_no_basis(
        self, return_validation, catalog, tmp_path, transcript_timing
    ) -> None:
        """The field cannot exist under the v5 contract, persisted or otherwise."""
        persisted = _persist(
            return_validation, catalog, tmp_path, transcript_timing, _v5()
        )

        assert "pattern_score_basis" not in persisted

    def test_v6_keeps_the_current_evidence_stamp(
        self, return_validation, catalog, tmp_path, transcript_timing
    ) -> None:
        """v6 is source-located and exhaustive, exactly as v5 is."""
        persisted = _persist(
            return_validation,
            catalog,
            tmp_path,
            transcript_timing,
            _v6(return_validation),
        )

        assert (
            persisted["evidence_schema_version"]
            == return_validation.PATTERN_EVIDENCE_SCHEMA_VERSION
        )

    def test_v6_persists_the_exhaustive_outcome_lanes(
        self, return_validation, catalog, tmp_path, transcript_timing
    ) -> None:
        """Gated on equality with v5, these three vanished from a v6 talk."""
        persisted = _persist(
            return_validation,
            catalog,
            tmp_path,
            transcript_timing,
            _v6(return_validation),
        )

        assert "pattern_outcomes" in persisted
        assert "applicability_assessments" in persisted
        assert "opportunity_coverage_identity" in persisted

    def test_v6_persists_the_same_lanes_as_v5(
        self, return_validation, catalog, tmp_path, transcript_timing
    ) -> None:
        """The two generations differ by the basis alone — nothing else moves."""
        v5_persisted = _persist(
            return_validation,
            catalog,
            tmp_path / "v5",
            transcript_timing,
            _v5(),
        )
        v6_persisted = _persist(
            return_validation,
            catalog,
            tmp_path / "v6",
            transcript_timing,
            _v6(return_validation),
        )

        assert set(v6_persisted) - set(v5_persisted) == {"pattern_score_basis"}
        assert not set(v5_persisted) - set(v6_persisted)

    def test_the_documented_basis_shape_is_what_persistence_stores(
        self, return_validation, catalog, tmp_path, transcript_timing
    ) -> None:
        """schemas-db.md prints this object; a reader recomputes the score from it."""
        persisted = _persist(
            return_validation,
            catalog,
            tmp_path,
            transcript_timing,
            _v6(return_validation),
        )

        basis = persisted["pattern_score_basis"]
        assert set(basis) == {
            "schema_version",
            "weights",
            "patterns",
            "antipatterns",
            "not_evaluable_count",
        }
        assert basis["weights"] == return_validation.DETECTION_WEIGHTS
        assert set(basis["patterns"]) == set(return_validation.DETECTION_WEIGHTS)
        assert set(basis["antipatterns"]) == set(return_validation.DETECTION_WEIGHTS)
