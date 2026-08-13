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


class TestATypeConfusedBasisIsRejected:
    """Equality alone does not gate types.

    Python makes `True == 1` and `6.0 == 6`, so a basis carrying boolean counts
    or a float schema version compares equal to the expected object and persists
    as a type-confused record every later reader believes was verified.
    """

    def _basis(self, rv, **overrides):
        ret = _v6(rv)
        block = ret["pattern_observations"]
        basis = block["pattern_score_basis"]
        for path, value in overrides.items():
            keys = path.split(".")
            target = basis
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = value
        return ret

    def test_a_boolean_lane_count_is_rejected(self, return_validation, catalog) -> None:
        """`True == 1` — the count would compare equal and pass."""
        ret = self._basis(return_validation, **{"patterns.strong": True})

        with pytest.raises(
            return_validation.ReturnValidationError, match="nonnegative integer"
        ):
            return_validation.validate_return(ret, catalog)

    def test_a_float_schema_version_is_rejected(
        self, return_validation, catalog
    ) -> None:
        """`6.0 == 6` — the version would compare equal and pass."""
        ret = self._basis(return_validation, schema_version=6.0)

        with pytest.raises(
            return_validation.ReturnValidationError, match="schema_version"
        ):
            return_validation.validate_return(ret, catalog)

    def test_a_boolean_not_evaluable_count_is_rejected(
        self, return_validation, catalog
    ) -> None:
        ret = self._basis(return_validation, not_evaluable_count=False)

        with pytest.raises(
            return_validation.ReturnValidationError, match="not_evaluable_count"
        ):
            return_validation.validate_return(ret, catalog)

    def test_a_boolean_weight_is_rejected(self, return_validation, catalog) -> None:
        ret = self._basis(return_validation, **{"weights.weak": True})

        with pytest.raises(
            return_validation.ReturnValidationError, match="must be a number"
        ):
            return_validation.validate_return(ret, catalog)

    def test_an_extra_field_is_rejected(self, return_validation, catalog) -> None:
        ret = _v6(return_validation)
        ret["pattern_observations"]["pattern_score_basis"]["extra"] = 1

        with pytest.raises(
            return_validation.ReturnValidationError, match="must contain exactly"
        ):
            return_validation.validate_return(ret, catalog)

    def test_a_missing_confidence_level_is_rejected(
        self, return_validation, catalog
    ) -> None:
        """A lane that omits a level cannot report the composition it claims."""
        ret = _v6(return_validation)
        del ret["pattern_observations"]["pattern_score_basis"]["antipatterns"]["weak"]

        with pytest.raises(
            return_validation.ReturnValidationError, match="must name exactly"
        ):
            return_validation.validate_return(ret, catalog)

    def test_a_non_object_basis_is_rejected(self, return_validation, catalog) -> None:
        ret = _v6(return_validation)
        ret["pattern_observations"]["pattern_score_basis"] = [1, 2, 3]

        with pytest.raises(
            return_validation.ReturnValidationError, match="must be an object"
        ):
            return_validation.validate_return(ret, catalog)


class TestTheSuppliedScoreIsComparedExactly:
    """Rounding the untrusted value accepts anything near the right answer.

    `expected_weighted_score` already rounds the CANONICAL result to two places.
    Rounding the supplied value too widened the gate by half a hundredth in
    either direction, so a score no declared arithmetic produces validated and
    persisted.
    """

    def test_a_near_miss_bare_score_is_rejected(
        self, return_validation, catalog
    ) -> None:
        ret = _v6(return_validation)
        canonical = ret["pattern_observations"]["pattern_score"]["score"]
        ret["pattern_observations"]["pattern_score"] = canonical + 0.004

        with pytest.raises(
            return_validation.ReturnValidationError, match="weighted detection arrays"
        ):
            return_validation.validate_return(ret, catalog)

    def test_a_near_miss_score_object_value_is_rejected(
        self, return_validation, catalog
    ) -> None:
        ret = _v6(return_validation)
        block = ret["pattern_observations"]["pattern_score"]
        block["score"] = block["score"] + 0.004

        with pytest.raises(
            return_validation.ReturnValidationError, match="pattern_score.score"
        ):
            return_validation.validate_return(ret, catalog)

    def test_a_fractional_lane_count_is_rejected(
        self, return_validation, catalog
    ) -> None:
        """A count of 1.004 is not a count. v6 keeps v5's integer lane semantics."""
        ret = _v6(return_validation)
        ret["pattern_observations"]["pattern_score"]["patterns_used"] = 1.004

        with pytest.raises(
            return_validation.ReturnValidationError, match="must be an integer"
        ):
            return_validation.validate_return(ret, catalog)

    def test_a_float_lane_count_is_rejected_even_when_whole(
        self, return_validation, catalog
    ) -> None:
        ret = _v6(return_validation)
        ret["pattern_observations"]["pattern_score"]["antipatterns_detected"] = 0.0

        with pytest.raises(
            return_validation.ReturnValidationError, match="must be an integer"
        ):
            return_validation.validate_return(ret, catalog)

    def test_a_boolean_lane_count_is_rejected(self, return_validation, catalog) -> None:
        ret = _v6(return_validation)
        ret["pattern_observations"]["pattern_score"]["antipatterns_detected"] = False

        with pytest.raises(
            return_validation.ReturnValidationError, match="must be an integer"
        ):
            return_validation.validate_return(ret, catalog)

    def test_an_exact_whole_score_written_as_an_int_still_passes(
        self, return_validation, catalog
    ) -> None:
        """Exactness is about value, not type.

        One strong detection weighs 1.0 exactly, and an int `1` equals that — a
        legitimate JSON representation of a whole-number weighted score, not a
        near miss.
        """
        ret = _v6(return_validation)
        block = ret["pattern_observations"]
        block["patterns_detected"] = [{**_detection(), "confidence": "strong"}]
        patterns = block["patterns_detected"]
        antipatterns = block["antipatterns_detected"]
        assert return_validation.expected_weighted_score(patterns, antipatterns) == 1.0
        block["pattern_score"] = {
            "patterns_used": len(patterns),
            "antipatterns_detected": len(antipatterns),
            "score": 1,
        }
        block["pattern_score_basis"] = return_validation.pattern_score_basis(
            patterns, antipatterns, block["not_evaluable"]
        )

        return_validation.validate_return(ret, catalog)


class TestV6GetsItsOwnScoringGeneration:
    """Weighted and flat scores are not comparable, so they cannot share one.

    The opportunity identity is what files a talk into a scoring cohort. Stamping
    a v6 identity with scoring schema 5 would put a weighted score in the same
    cohort as the flat ones and let an aggregate average across two different
    arithmetics — silently, since every field would look well-formed.
    """

    def test_a_v6_return_is_stamped_with_the_weighted_generation(
        self, return_validation
    ) -> None:
        assert (
            return_validation.scoring_schema_version_for_return(
                return_validation.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION
            )
            == return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
        )

    def test_a_v5_return_keeps_the_flat_generation(self, return_validation) -> None:
        assert (
            return_validation.scoring_schema_version_for_return(
                return_validation.RETURN_SCHEMA_VERSION
            )
            == return_validation.PATTERN_SCORING_SCHEMA_VERSION
        )

    def test_the_two_generations_differ(self, return_validation) -> None:
        """If they were equal the split would be decorative."""
        assert (
            return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
            != return_validation.PATTERN_SCORING_SCHEMA_VERSION
        )

    def test_persistence_files_v5_and_v6_in_different_cohorts(
        self, return_validation, catalog, tmp_path, transcript_timing
    ) -> None:
        """The identity is the cohort key, so the two must not collide."""
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

        assert (
            v5_persisted["opportunity_coverage_identity"]
            != v6_persisted["opportunity_coverage_identity"]
        )

    def test_the_producer_and_the_validator_agree(
        self, return_validation, catalog, tmp_path, transcript_timing
    ) -> None:
        """`_persist` runs the real canonicalizer and then the real validator, so
        a disagreement between them fails here rather than at persistence."""
        persisted = _persist(
            return_validation,
            catalog,
            tmp_path,
            transcript_timing,
            _v6(return_validation),
        )

        assert persisted["opportunity_coverage_identity"]


class TestThePersistedStampAgreesWithTheIdentity:
    """One record cannot claim two generations.

    Canonicalization stamps a v6 identity with scoring generation 6. If the
    writer persisted the CURRENT generation (5) beside it, the record would carry
    contradictory authority and a later freshness replay — which rebuilds the
    identity from the talk's own stamp — would recompute with 5 and never match.
    """

    def test_the_writer_stamps_the_return_s_own_generation(
        self, return_validation
    ) -> None:
        assert return_validation.scoring_schema_version_for_return(
            return_validation.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION
        ) != return_validation.scoring_schema_version_for_return(
            return_validation.RETURN_SCHEMA_VERSION
        )

    def test_the_persisted_identity_is_the_weighted_generation_s(
        self, return_validation, catalog, tmp_path, transcript_timing
    ) -> None:
        """Rebuild the identity independently at generation 6 and at 5. The
        persisted one must be the former, or the record's stamp and its identity
        describe different cohorts."""
        import pattern_evidence

        persisted = _persist(
            return_validation,
            catalog,
            tmp_path,
            transcript_timing,
            _v6(return_validation),
        )
        outcomes = persisted["pattern_outcomes"]

        weighted = pattern_evidence.opportunity_coverage_identity(
            outcomes,
            pattern_catalog_fingerprint=catalog.fingerprint,
            pattern_scoring_schema_version=(
                return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
            ),
        )
        flat = pattern_evidence.opportunity_coverage_identity(
            outcomes,
            pattern_catalog_fingerprint=catalog.fingerprint,
            pattern_scoring_schema_version=(
                return_validation.PATTERN_SCORING_SCHEMA_VERSION
            ),
        )

        assert persisted["opportunity_coverage_identity"] == weighted
        assert persisted["opportunity_coverage_identity"] != flat


class TestAWeightedScoreSurvivesTheRealWriter:
    """Validation and persistence have to agree on what a score is.

    `validate_return` accepted a weighted 1.5 while the writer still required an
    integer and the persisted-snapshot contract knew nothing of
    `pattern_score_basis`, so a return could pass validation and then be
    unmergeable. Canonicalizing and asserting the persisted block never touched
    the writer, which is where that broke.
    """

    def _merge(
        self, return_validation, persist_results, catalog, tmp_path, timing, ret
    ):
        import pattern_evidence

        return_validation.validate_return(ret, catalog)
        vault, owner = _artifact(tmp_path, timing)
        canonical = pattern_evidence.canonicalize_return_evidence(
            copy.deepcopy(ret),
            owner,
            vault,
            catalog,
            pattern_scoring_schema_version=(
                return_validation.PATTERN_SCORING_SCHEMA_VERSION
            ),
        )
        talk = copy.deepcopy(owner)
        persist_results.merge_talk(talk, ret, catalog=catalog, canonical_ret=canonical)
        return talk

    def test_a_fractional_score_merges_and_validates(
        self,
        return_validation,
        persist_results,
        catalog,
        tmp_path,
        transcript_timing,
    ) -> None:
        ret = _v6(return_validation)
        expected = ret["pattern_observations"]["pattern_score"]["score"]
        assert expected != int(expected), "fixture must exercise a fractional score"

        talk = self._merge(
            return_validation,
            persist_results,
            catalog,
            tmp_path,
            transcript_timing,
            ret,
        )

        assert talk["pattern_score"] == expected
        assert talk["pattern_observations"]["pattern_score"] == expected

    def test_the_merged_record_carries_its_basis(
        self,
        return_validation,
        persist_results,
        catalog,
        tmp_path,
        transcript_timing,
    ) -> None:
        ret = _v6(return_validation)

        talk = self._merge(
            return_validation,
            persist_results,
            catalog,
            tmp_path,
            transcript_timing,
            ret,
        )

        assert (
            talk["pattern_observations"]["pattern_score_basis"]
            == ret["pattern_observations"]["pattern_score_basis"]
        )

    def test_the_merged_record_is_stamped_with_the_weighted_generation(
        self,
        return_validation,
        persist_results,
        catalog,
        tmp_path,
        transcript_timing,
    ) -> None:
        talk = self._merge(
            return_validation,
            persist_results,
            catalog,
            tmp_path,
            transcript_timing,
            _v6(return_validation),
        )

        assert (
            talk["pattern_scoring_schema_version"]
            == return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
        )

    def test_a_v5_record_still_merges_with_a_flat_integer_score(
        self,
        return_validation,
        persist_results,
        catalog,
        tmp_path,
        transcript_timing,
    ) -> None:
        """The weighted path must not loosen the flat contract."""
        talk = self._merge(
            return_validation,
            persist_results,
            catalog,
            tmp_path,
            transcript_timing,
            _v5(),
        )

        assert isinstance(talk["pattern_score"], int)
        assert (
            talk["pattern_scoring_schema_version"]
            == return_validation.PATTERN_SCORING_SCHEMA_VERSION
        )
