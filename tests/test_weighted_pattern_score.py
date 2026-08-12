"""Weighted aggregate scoring and its evidence basis (#153).

Weighting is a v6 return contract. A v5 return was PRODUCED by a worker counting
+1/-1, so these tests pin both arithmetics — rescoring a v5 return under the
weight table would restate what its worker meant rather than validate it.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def rv(return_validation):
    return return_validation


def _det(pattern_id: str, confidence: str) -> dict:
    return {"pattern_id": pattern_id, "confidence": confidence}


class TestWeights:
    def test_the_owner_approved_table(self, rv) -> None:
        assert rv.DETECTION_WEIGHTS == {"strong": 1.0, "moderate": 0.5, "weak": 0.25}

    def test_every_confidence_level_has_a_weight(self, rv) -> None:
        """A partial table would make some detection unscoreable."""
        assert set(rv.DETECTION_WEIGHTS) == set(rv.CONFIDENCE_LEVELS)


class TestWeightedTotal:
    @pytest.mark.parametrize(
        ("patterns", "antipatterns", "expected"),
        [
            ([("a", "strong")], [], 1.0),
            ([("a", "moderate")], [], 0.5),
            ([("a", "weak")], [], 0.25),
            ([("a", "strong")], [("b", "weak")], 0.75),
            ([], [("b", "strong")], -1.0),
            ([("a", "moderate"), ("b", "moderate")], [("c", "moderate")], 0.5),
            ([], [], 0.0),
        ],
    )
    def test_polarity_aware_arithmetic(
        self, rv, patterns, antipatterns, expected
    ) -> None:
        assert (
            rv.expected_weighted_score(
                [_det(*p) for p in patterns], [_det(*a) for a in antipatterns]
            )
            == expected
        )

    def test_a_strong_detection_outweighs_a_moderate_one(self, rv) -> None:
        """The whole point: flat counting made these read as equivalent."""
        strong = rv.expected_weighted_score([_det("a", "strong")], [])
        moderate = rv.expected_weighted_score([_det("a", "moderate")], [])
        assert strong > moderate

    def test_the_sum_carries_no_float_dust(self, rv) -> None:
        """0.1+0.2 arithmetic would fail an equality check that is logically
        true, so the total rounds deterministically."""
        score = rv.expected_weighted_score(
            [_det("a", "moderate"), _det("b", "weak"), _det("c", "weak")], []
        )
        assert score == 1.0


class TestBasis:
    def test_it_counts_each_lane_by_confidence(self, rv) -> None:
        basis = rv.pattern_score_basis(
            [_det("a", "strong"), _det("b", "moderate")],
            [_det("c", "weak")],
            [{"pattern_id": "d"}],
        )
        assert basis["patterns"] == {"strong": 1, "moderate": 1, "weak": 0}
        assert basis["antipatterns"] == {"strong": 0, "moderate": 0, "weak": 1}
        assert basis["not_evaluable_count"] == 1

    def test_it_carries_the_weights_it_was_computed_under(self, rv) -> None:
        """A score without its weights cannot be compared across generations."""
        basis = rv.pattern_score_basis([], [], [])
        assert basis["weights"] == rv.DETECTION_WEIGHTS
        assert basis["schema_version"] == rv.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION


class TestSchemaBoundary:
    def test_the_scoring_generation_holds_until_a_return_emits_a_weighted_score(
        self, rv
    ) -> None:
        """Bumping it early would strand every persisted talk on a generation
        nothing has produced."""
        assert rv.PATTERN_SCORING_SCHEMA_VERSION == 5
        assert rv.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION == 6

    def test_weighting_starts_above_the_current_return_schema(self, rv) -> None:
        assert rv.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION > rv.RETURN_SCHEMA_VERSION


class TestBasisIsRequiredByTheScoreNotItsShape:
    """Gating the basis inside the score-object branch would let a bare
    weighted number ship with no record of the evidence behind it."""

    def _observations(self, score: object, **extra) -> dict:
        block = {"pattern_score": score}
        block.update(extra)
        return block

    def _detections(self):
        return [_det("a", "strong")], [], []

    def test_a_bare_weighted_number_without_a_basis_is_rejected(self, rv) -> None:
        patterns, antipatterns, not_evaluable = self._detections()

        with pytest.raises(rv.ReturnValidationError, match="pattern_score_basis"):
            rv._validate_score(
                self._observations(1.0),
                patterns,
                antipatterns,
                not_evaluable,
                rv.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION,
            )

    def test_a_score_object_without_a_basis_is_rejected(self, rv) -> None:
        patterns, antipatterns, not_evaluable = self._detections()
        score = {"patterns_used": 1, "antipatterns_detected": 0, "score": 1.0}

        with pytest.raises(rv.ReturnValidationError, match="pattern_score_basis"):
            rv._validate_score(
                self._observations(score),
                patterns,
                antipatterns,
                not_evaluable,
                rv.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION,
            )

    def test_a_bare_weighted_number_with_its_basis_passes(self, rv) -> None:
        patterns, antipatterns, not_evaluable = self._detections()
        basis = rv.pattern_score_basis(patterns, antipatterns, not_evaluable)

        rv._validate_score(
            self._observations(1.0, pattern_score_basis=basis),
            patterns,
            antipatterns,
            not_evaluable,
            rv.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION,
        )

    def test_a_basis_that_contradicts_the_arrays_is_rejected(self, rv) -> None:
        patterns, antipatterns, not_evaluable = self._detections()
        basis = rv.pattern_score_basis(patterns, antipatterns, not_evaluable)
        basis["patterns"] = {"strong": 9, "moderate": 0, "weak": 0}

        with pytest.raises(rv.ReturnValidationError, match="does not match"):
            rv._validate_score(
                self._observations(1.0, pattern_score_basis=basis),
                patterns,
                antipatterns,
                not_evaluable,
                rv.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION,
            )

    def test_a_pre_v6_return_keeps_flat_arithmetic(self, rv) -> None:
        """A v5 return was produced by a worker counting +1/-1."""
        patterns, antipatterns, not_evaluable = self._detections()

        rv._validate_score(
            self._observations(1),
            patterns,
            antipatterns,
            not_evaluable,
            rv.RETURN_SCHEMA_VERSION,
        )

    def test_a_pre_v6_return_cannot_carry_a_basis(self, rv) -> None:
        patterns, antipatterns, not_evaluable = self._detections()
        basis = rv.pattern_score_basis(patterns, antipatterns, not_evaluable)

        with pytest.raises(rv.ReturnValidationError, match="cannot carry one"):
            rv._validate_score(
                self._observations(1, pattern_score_basis=basis),
                patterns,
                antipatterns,
                not_evaluable,
                rv.RETURN_SCHEMA_VERSION,
            )


class TestV6IsReachable:
    """The contract has to be reachable through the public validator, or it is
    code nothing can invoke."""

    def test_v6_is_a_supported_return_schema(self, rv) -> None:
        assert (
            rv.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION
            in rv.SUPPORTED_RETURN_SCHEMA_VERSIONS
        )

    @pytest.mark.parametrize(
        "field_set",
        [
            "SNAPSHOT_RETURN_SCHEMA_VERSIONS",
            "OUTCOME_GATE_RETURN_SCHEMA_VERSIONS",
            "SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS",
            "EXHAUSTIVE_OUTCOME_RETURN_SCHEMA_VERSIONS",
        ],
    )
    def test_v6_inherits_every_v5_semantic(self, rv, field_set) -> None:
        """v6 adds weighting to v5; it does not drop anything, so every set v5
        belongs to must contain it."""
        versions = getattr(rv, field_set)
        assert rv.RETURN_SCHEMA_VERSION in versions
        assert rv.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION in versions

    def test_a_v6_return_resolves_through_the_public_entry_point(self, rv) -> None:
        ret = {"return_schema_version": rv.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION}

        assert (
            rv.resolve_return_schema_version(ret)
            == rv.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION
        )
