"""The v5/weighted scoring boundary, asserted through the public validator.

These drive `validate_return`, the entry point that owns schema resolution — a
test calling the private score helper proves the arithmetic but not that any
real return can reach it.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from test_schema5_pattern_outcomes import (
    _assessment,
    _catalog,
    _detection,
    _entry,
    _raw_return,
    _scored_talk,
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


def _v6(rv, *, score=None, basis=None, drop_basis=False, bare=False) -> dict[str, Any]:
    """A v6 return: the v5 shape with weighted arithmetic and its basis.

    `bare` emits the score as a plain number instead of the declared score
    object. Both shapes are legal, and the basis is required by the SCORE rather
    than by the shape it was written in.
    """
    ret = copy.deepcopy(_v5())
    ret["return_schema_version"] = rv.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION
    block = ret["pattern_observations"]
    patterns = block["patterns_detected"]
    antipatterns = block["antipatterns_detected"]
    not_evaluable = block["not_evaluable"]
    weighted = rv.expected_weighted_score(patterns, antipatterns)
    resolved = weighted if score is None else score
    block["pattern_score"] = (
        resolved
        if bare
        else {
            "patterns_used": len(patterns),
            "antipatterns_detected": len(antipatterns),
            "score": resolved,
        }
    )
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


class TestV7AddsProviderAutoProvenance:
    def test_provider_auto_validates_at_the_new_generation(
        self, return_validation, catalog
    ) -> None:
        ret = _v6(return_validation)
        ret["return_schema_version"] = return_validation.RETURN_SCHEMA_VERSION
        ret["transcript_source"] = "provider_auto"

        return_validation.validate_return(ret, catalog)

    def test_provider_auto_is_not_backported_to_v6(
        self, return_validation, catalog
    ) -> None:
        ret = _v6(return_validation)
        ret["transcript_source"] = "provider_auto"

        with pytest.raises(
            return_validation.ReturnValidationError,
            match="snapshot return transcript_source",
        ):
            return_validation.validate_return(ret, catalog)


class TestTheBasisIsRequiredByTheScoreNotItsShape:
    """Gating the basis inside the score-object branch would let a bare weighted
    number ship with no record of the evidence behind it."""

    def test_a_bare_weighted_number_with_its_basis_passes(
        self, return_validation, catalog
    ) -> None:
        return_validation.validate_return(_v6(return_validation, bare=True), catalog)

    def test_a_bare_weighted_number_without_a_basis_is_rejected(
        self, return_validation, catalog
    ) -> None:
        """The shape carries no counts of its own, so an unaccompanied bare
        number says nothing at all about the evidence behind it."""
        with pytest.raises(
            return_validation.ReturnValidationError, match="pattern_score_basis"
        ):
            return_validation.validate_return(
                _v6(return_validation, bare=True, drop_basis=True), catalog
            )

    def test_a_bare_number_ignoring_the_weights_is_rejected(
        self, return_validation, catalog
    ) -> None:
        with pytest.raises(
            return_validation.ReturnValidationError, match="weighted detection arrays"
        ):
            return_validation.validate_return(
                _v6(return_validation, bare=True, score=99), catalog
            )

    def test_a_bare_basis_contradicting_the_arrays_is_rejected(
        self, return_validation, catalog
    ) -> None:
        basis = return_validation.pattern_score_basis([], [], [])
        basis["patterns"] = {"strong": 9, "moderate": 0, "weak": 0}

        with pytest.raises(
            return_validation.ReturnValidationError, match="does not match"
        ):
            return_validation.validate_return(
                _v6(return_validation, bare=True, basis=basis), catalog
            )


class TestAWeightedScoreCanBeCompared:
    """The adherence comparison restates the block's own score.

    It therefore takes that generation's type. Requiring an integer of both
    generations rejects every valid weighted return that reports a comparison —
    which would mean v6 does not actually retain the v5 adherence contract it
    claims to inherit.
    """

    def _with_comparison(self, rv, ret, score):
        import adherence_baseline

        baseline = adherence_baseline.build_adherence_baseline(
            [_scored_talk(f"talk-{index}.md", "1" * 64) for index in range(10)],
            selected_filenames=[],
            as_of="2026-07-31T12:00:00+00:00",
            pattern_catalog_fingerprint="a" * 64,
            pattern_scoring_schema_version=rv.PATTERN_SCORING_SCHEMA_VERSION,
            evidence_freshness_assessor=lambda _talk: (),
            persisted_observation_assessor=lambda _talk: (),
        )
        ret["adherence_assessment"] = "It rose against the baseline. Clearly so."
        ret["adherence_comparison"] = {
            "schema_version": 1,
            "baseline": baseline,
            "talk_pattern_score": score,
        }
        return ret

    def test_a_fractional_comparison_score_validates(
        self, return_validation, catalog
    ) -> None:
        """The whole return completes — not merely "fails for another reason"."""
        ret = _v6(return_validation)
        score = ret["pattern_observations"]["pattern_score"]["score"]
        assert score != int(score), "fixture must exercise a fractional score"

        self._with_comparison(return_validation, ret, score)

        return_validation.validate_return(ret, catalog)

    def test_the_flat_contract_still_validates_its_own_comparison(
        self, return_validation, catalog
    ) -> None:
        """The weighted allowance is an addition, not a loosening."""
        ret = _v5()
        raw = ret["pattern_observations"]["pattern_score"]
        score = raw["score"] if isinstance(raw, dict) else raw
        self._with_comparison(return_validation, ret, score)

        return_validation.validate_return(ret, catalog)

    def test_a_non_finite_comparison_score_is_rejected(
        self, return_validation, catalog
    ) -> None:
        """`inf` is numeric and is not a score."""
        ret = _v6(return_validation)
        self._with_comparison(return_validation, ret, float("inf"))

        with pytest.raises(
            return_validation.ReturnValidationError, match="finite number"
        ):
            return_validation.validate_return(ret, catalog)

    def test_a_v5_comparison_still_refuses_a_float(
        self, return_validation, catalog
    ) -> None:
        """The weighted allowance must not loosen the flat contract."""
        ret = _v5()
        self._with_comparison(return_validation, ret, 1.5)

        with pytest.raises(
            return_validation.ReturnValidationError, match="must be an integer"
        ):
            return_validation.validate_return(ret, catalog)


class TestAWeightedBlockSurvivesTheReadGate:
    """The activation's point: a weighted block persists AND reads back.

    The gate keys the weighted shape off the field SET, so a canonical block
    that omits `pattern_score_basis` is a v5 block — and the fractional score
    it carries is then rejected at that shape. v6 that cannot be stored.
    """

    def _talk(self, rv, block: dict[str, Any]) -> dict[str, Any]:
        return {
            "structured_data": {},
            "verbatim_examples": {},
            "pattern_observations": block,
            "pattern_score": block["pattern_score"],
        }

    def _weighted_block(self, rv) -> dict[str, Any]:
        patterns = [
            {
                "pattern_id": "one",
                "confidence": "moderate",
                "evidence": "text",
                "evidence_citations": [],
                "dimensions": [1],
            }
        ]
        block = {
            "patterns_detected": patterns,
            "pattern_ids": ["one"],
            "antipatterns_detected": [],
            "antipattern_ids": [],
            "not_evaluable": [],
            "not_evaluable_ids": [],
            "evidence_sources": ["transcript"],
            "pattern_score": rv.expected_weighted_score(patterns, []),
            "applicability_assessments": [],
            "pattern_outcomes": [],
            "opportunity_coverage_identity": None,
            "pattern_score_basis": rv.pattern_score_basis(patterns, [], []),
        }
        return block

    def test_the_weighted_field_set_is_v5_plus_the_basis(self, return_validation):
        assert set(return_validation.V6_PERSISTED_PATTERN_OBSERVATION_FIELDS) == (
            set(return_validation.V5_PERSISTED_PATTERN_OBSERVATION_FIELDS)
            | {"pattern_score_basis"}
        )

    def test_a_fractional_score_is_accepted_at_the_weighted_shape(
        self, return_validation
    ):
        block = self._weighted_block(return_validation)
        assert block["pattern_score"] != int(block["pattern_score"])

        return_validation.validate_persisted_pattern_score_basis(
            block, block["pattern_score"]
        )

    def test_the_basis_is_checked_against_the_persisted_lanes(self, return_validation):
        """A stored basis agreeing with a stored score proves only that whoever
        wrote them agreed with themselves."""
        block = self._weighted_block(return_validation)
        block["patterns_detected"].append(
            {
                "pattern_id": "two",
                "confidence": "strong",
                "evidence": "text",
                "evidence_citations": [],
                "dimensions": [1],
            }
        )

        with pytest.raises(return_validation.ReturnValidationError):
            return_validation.validate_persisted_pattern_score_basis(
                block, block["pattern_score"]
            )

    def test_a_score_the_lanes_do_not_produce_is_refused(self, return_validation):
        block = self._weighted_block(return_validation)

        with pytest.raises(return_validation.ReturnValidationError):
            return_validation.validate_persisted_pattern_score_basis(block, 99.0)
