"""The persistence half of weighted scoring (#299).

#293 defined the weighted return; #308 got a v6 return through canonicalization.
Neither could store the number it produced: both writers that read a persisted
`pattern_score` demanded an integer, and a weighted aggregate is a sum of
1.0/0.5/0.25 terms.

These pin the two contracts that had to split by generation — `resolve_pattern_score`
on the way into the database, and the adherence cohort on the way back out. The
weighted allowance is an addition, so every test that admits a fraction at the
weighted generation has a sibling proving the flat generation still refuses one.
"""

from __future__ import annotations

import copy
import importlib
import math
from typing import Any

import pytest

from test_schema5_pattern_outcomes import (
    _artifact,
    _assessment,
    _catalog,
    _detection,
    _entry,
    _raw_return,
)

CATALOG = "a" * 64
OPPORTUNITY_IDENTITY = "c" * 64


def _arrays() -> tuple[list[dict], list[dict]]:
    """One strong pattern against one weak antipattern: 1.0 - 0.25 = 0.75.

    Deliberately not a whole number. A fixture scoring 1.0 passes the weighted
    contract and the flat one alike, so it cannot tell them apart.
    """
    return (
        [{"pattern_id": "a", "confidence": "strong"}],
        [{"pattern_id": "b", "confidence": "weak"}],
    )


class TestResolveAWeightedScore:
    """`resolve_pattern_score` — the single writer-side authority on the number."""

    def test_a_bare_fraction_the_arrays_require_is_accepted(self, persist_results):
        patterns, antipatterns = _arrays()

        score, coerced = persist_results.resolve_pattern_score(
            {"pattern_score": 0.75}, patterns, antipatterns, weighted=True
        )

        assert (score, coerced) == (0.75, True)

    def test_a_bare_fraction_the_arrays_contradict_is_refused(self, persist_results):
        """The cross-check moves to weighted arithmetic, it does not switch off."""
        patterns, antipatterns = _arrays()

        with pytest.raises(ValueError, match="weighted detection arrays require 0.75"):
            persist_results.resolve_pattern_score(
                {"pattern_score": 0.5}, patterns, antipatterns, weighted=True
            )

    def test_a_bare_count_difference_no_longer_satisfies_it(self, persist_results):
        """count(1) - count(1) = 0 was the old answer; the weighted one is 0.75."""
        patterns, antipatterns = _arrays()

        with pytest.raises(ValueError, match="weighted detection arrays require"):
            persist_results.resolve_pattern_score(
                {"pattern_score": 0}, patterns, antipatterns, weighted=True
            )

    def test_a_bool_is_not_a_weighted_score(self, persist_results):
        """`True` satisfies `isinstance(x, int)` in Python; a score does not."""
        patterns, antipatterns = _arrays()

        with pytest.raises(ValueError, match="A weighted score is a number"):
            persist_results.resolve_pattern_score(
                {"pattern_score": True}, patterns, antipatterns, weighted=True
            )

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_a_non_finite_score_is_refused_before_any_comparison(
        self, persist_results, value
    ):
        """NaN defeats the equality cross-check by never equalling anything."""
        patterns, antipatterns = _arrays()

        with pytest.raises(ValueError, match="finite"):
            persist_results.resolve_pattern_score(
                {"pattern_score": value}, patterns, antipatterns, weighted=True
            )

    def test_a_score_object_carries_its_own_counts_and_is_not_cross_checked(
        self, persist_results
    ):
        """Only the bare form arrived without the counts that vouch for it."""
        patterns, antipatterns = _arrays()

        score, coerced = persist_results.resolve_pattern_score(
            {
                "pattern_score": {
                    "patterns_used": 1,
                    "antipatterns_detected": 1,
                    "score": 0.75,
                }
            },
            patterns,
            antipatterns,
            weighted=True,
        )

        assert (score, coerced) == (0.75, False)

    def test_a_whole_weighted_score_stays_valid(self, persist_results):
        """Two strong patterns against one: 2.0 - 1.0 = 1.0, weighted and integral."""
        patterns = [
            {"pattern_id": "a", "confidence": "strong"},
            {"pattern_id": "b", "confidence": "strong"},
        ]
        antipatterns = [{"pattern_id": "c", "confidence": "strong"}]

        score, _ = persist_results.resolve_pattern_score(
            {"pattern_score": 1.0}, patterns, antipatterns, weighted=True
        )

        assert score == 1.0


class TestTheFlatContractIsUnchanged:
    """The weighted allowance is an addition, never a loosening."""

    def test_a_float_is_still_refused_at_the_flat_generation(self, persist_results):
        patterns, antipatterns = _arrays()

        with pytest.raises(ValueError, match="must be an\n?\\s*integer"):
            persist_results.resolve_pattern_score(
                {"pattern_score": 0.75}, patterns, antipatterns
            )

    def test_the_count_difference_is_still_the_flat_cross_check(self, persist_results):
        patterns, antipatterns = _arrays()

        with pytest.raises(ValueError, match="minus antipatterns_detected"):
            persist_results.resolve_pattern_score(
                {"pattern_score": 5}, patterns, antipatterns
            )

    def test_the_flat_count_difference_still_persists(self, persist_results):
        patterns, antipatterns = _arrays()

        score, coerced = persist_results.resolve_pattern_score(
            {"pattern_score": 0}, patterns, antipatterns
        )

        assert (score, coerced) == (0, True)

    def test_weighted_defaults_off(self, persist_results):
        """Callers that predate the split keep the flat contract by omission."""
        patterns, antipatterns = _arrays()

        with pytest.raises(ValueError, match="must be an\n?\\s*integer"):
            persist_results.resolve_pattern_score(
                {"pattern_score": 0.75},
                patterns,
                antipatterns,
                weighted=False,
            )


def _cohort_talk(filename: str, score: Any, *, scoring_schema: int) -> dict[str, Any]:
    return {
        "filename": filename,
        "status": "processed",
        "pattern_catalog_fingerprint": CATALOG,
        "pattern_scoring_schema_version": scoring_schema,
        "pattern_scoring_generation_status": "current",
        "pattern_scoring_generation_reasons": [],
        "pattern_score": score,
        "pattern_observations": {
            "pattern_score": score,
            "opportunity_coverage_identity": OPPORTUNITY_IDENTITY,
            "pattern_outcomes": [{"pattern_id": "p1", "outcome": "detected"}],
        },
    }


def _baseline(adherence_baseline, talks, *, scoring_schema: int):
    return adherence_baseline.build_adherence_baseline(
        talks,
        selected_filenames=[],
        as_of="2026-07-31T12:00:00+00:00",
        pattern_catalog_fingerprint=CATALOG,
        pattern_scoring_schema_version=scoring_schema,
        evidence_freshness_assessor=lambda _: (),
        persisted_observation_assessor=lambda _: (),
    )


def _partition(adherence_baseline, talks, *, scoring_schema: int):
    return adherence_baseline.partition_pattern_scoring_cohort(
        talks,
        excluded_filenames=(),
        pattern_catalog_fingerprint=CATALOG,
        pattern_scoring_schema_version=scoring_schema,
        evidence_freshness_assessor=lambda _: (),
        persisted_observation_assessor=lambda _: (),
    )


@pytest.fixture(scope="module")
def adherence_baseline():
    import adherence_baseline as module

    return module


class TestTheWeightedCohortReadsItBack:
    """A score the writer stored must not be unreadable to the cohort selector.

    The baseline is what a talk is compared against. A weighted generation whose
    own scores raise here has no baseline at all — every talk falls out, which
    reads downstream as a population too small rather than a contract mismatch.
    """

    def test_a_fractional_score_stays_in_the_weighted_cohort(
        self, adherence_baseline, return_validation
    ):
        talk = _cohort_talk(
            "weighted.md",
            0.75,
            scoring_schema=return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION,
        )

        current, excluded, details = _partition(
            adherence_baseline,
            [talk],
            scoring_schema=(return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION),
        )

        assert (current, excluded, details) == ([talk], [], [])

    def test_the_flat_cohort_still_refuses_a_fraction(
        self, adherence_baseline, return_validation
    ):
        flat = return_validation.FLAT_PATTERN_SCORING_SCHEMA_VERSION
        talk = _cohort_talk("flat.md", 0.75, scoring_schema=flat)

        with pytest.raises(
            adherence_baseline.AdherenceBaselineError,
            match="pattern_score must be an integer",
        ):
            _partition(adherence_baseline, [talk], scoring_schema=flat)

    @pytest.mark.parametrize("score", [True, False, "1", None])
    def test_a_non_number_is_still_refused_at_the_weighted_generation(
        self, adherence_baseline, return_validation, score
    ):
        weighted = return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
        talk = _cohort_talk("bad.md", score, scoring_schema=weighted)

        with pytest.raises(
            adherence_baseline.AdherenceBaselineError,
            match="pattern_score must be a number",
        ):
            _partition(adherence_baseline, [talk], scoring_schema=weighted)

    @pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
    def test_a_non_finite_score_is_refused_at_the_weighted_generation(
        self, adherence_baseline, return_validation, score
    ):
        """A NaN that reached the sum would make the whole average NaN."""
        weighted = return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
        talk = _cohort_talk("nonfinite.md", score, scoring_schema=weighted)

        with pytest.raises(
            adherence_baseline.AdherenceBaselineError,
            match="pattern_score must be finite",
        ):
            _partition(adherence_baseline, [talk], scoring_schema=weighted)

    def test_divergent_score_lanes_are_still_caught_when_both_are_fractional(
        self, adherence_baseline, return_validation
    ):
        """Loosening the type must not loosen the agreement between the lanes."""
        weighted = return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
        talk = _cohort_talk("divergent.md", 0.75, scoring_schema=weighted)
        talk["pattern_observations"]["pattern_score"] = 0.5

        with pytest.raises(
            adherence_baseline.AdherenceBaselineError,
            match="promoted pattern_score 0.75 diverges",
        ):
            _partition(adherence_baseline, [talk], scoring_schema=weighted)


class TestTheWeightedBaselineCanBeBuilt:
    """The cohort and the sum must take the same generation's arithmetic.

    Splitting only the cohort selector left `build_adherence_baseline` summing
    on the flat contract: it admitted a fractional score into the cohort on one
    line and raised on it a few lines later. Every weighted baseline would have
    been unbuildable, which reads downstream as an empty population rather than
    a contract mismatch — the same half-converted path as #308.
    """

    @staticmethod
    def _population(score, scoring_schema):
        """Above `MIN_ADHERENCE_BASELINE_TALKS`, so the cohort is comparable."""
        return [
            _cohort_talk(f"t{index}.md", score, scoring_schema=scoring_schema)
            for index in range(12)
        ]

    def test_a_weighted_baseline_sums_and_averages_its_fractions(
        self, adherence_baseline, return_validation
    ):
        weighted = return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION

        snapshot = _baseline(
            adherence_baseline,
            self._population(0.75, weighted),
            scoring_schema=weighted,
        )

        assert snapshot["scored_talk_count"] == 12
        assert snapshot["pattern_score_sum"] == 9.0
        assert snapshot["average_pattern_score"] == 0.75

    def test_the_weighted_sum_is_canonical_to_two_places(
        self, adherence_baseline, return_validation
    ):
        """A sum carrying float dust would fail an exact comparison downstream."""
        weighted = return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION

        snapshot = _baseline(
            adherence_baseline,
            self._population(0.25, weighted),
            scoring_schema=weighted,
        )

        score_sum = snapshot["pattern_score_sum"]
        assert isinstance(score_sum, float)
        assert score_sum == round(score_sum, 2)
        assert score_sum == 3.0

    def test_the_flat_baseline_keeps_an_integer_sum(
        self, adherence_baseline, return_validation
    ):
        """The flat generation's sum must not become a float by association."""
        flat = return_validation.FLAT_PATTERN_SCORING_SCHEMA_VERSION

        snapshot = _baseline(
            adherence_baseline, self._population(1, flat), scoring_schema=flat
        )

        assert snapshot["pattern_score_sum"] == 12
        assert isinstance(snapshot["pattern_score_sum"], int)

    def test_the_flat_baseline_still_refuses_a_fractional_score(
        self, adherence_baseline, return_validation
    ):
        flat = return_validation.FLAT_PATTERN_SCORING_SCHEMA_VERSION

        with pytest.raises(
            adherence_baseline.AdherenceBaselineError,
            match="pattern_score must be an integer",
        ):
            _baseline(
                adherence_baseline,
                self._population(0.75, flat),
                scoring_schema=flat,
            )

    def test_the_validator_accepts_the_weighted_snapshot_it_built(
        self, adherence_baseline, return_validation
    ):
        """`build` validates on the way out, so a rejected sum would raise there."""
        weighted = return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
        snapshot = _baseline(
            adherence_baseline,
            self._population(0.5, weighted),
            scoring_schema=weighted,
        )

        assert adherence_baseline.validate_adherence_baseline(snapshot) == snapshot

    def test_the_validator_still_refuses_a_fractional_sum_at_the_flat_generation(
        self, adherence_baseline, return_validation
    ):
        """The split is keyed on the generation, not on what the number looks like."""
        flat = return_validation.FLAT_PATTERN_SCORING_SCHEMA_VERSION
        snapshot = _baseline(
            adherence_baseline, self._population(1, flat), scoring_schema=flat
        )
        snapshot["pattern_score_sum"] = 11.5

        with pytest.raises(
            adherence_baseline.AdherenceBaselineError,
            match="pattern_score_sum must be an integer",
        ):
            adherence_baseline.validate_adherence_baseline(snapshot)


def _weighted_catalog(return_validation):
    return _catalog(
        return_validation,
        _entry(return_validation, "detected"),
        _entry(return_validation, "conditional", applicability=True),
        _entry(return_validation, "undetected"),
        _entry(return_validation, "positive-only", absence_gate=None),
    )


def _v6_return(return_validation, catalog, *, bare: bool):
    raw = _raw_return(
        detections=[_detection()],
        assessments=[_assessment()],
        not_evaluable=[
            {
                "pattern_id": "positive-only",
                "reason_code": "absence_not_authorized_by_catalog",
            }
        ],
    )
    raw["return_schema_version"] = (
        return_validation.WEIGHTED_SCORE_RETURN_SCHEMA_VERSION
    )
    block = raw["pattern_observations"]
    patterns = block["patterns_detected"]
    antipatterns = block["antipatterns_detected"]
    expected = return_validation.expected_weighted_score(patterns, antipatterns)
    assert not float(expected).is_integer(), (
        "fixture must exercise a fractional score, or it proves nothing"
    )
    block["pattern_score"] = (
        expected
        if bare
        else {
            "patterns_used": len(patterns),
            "antipatterns_detected": len(antipatterns),
            "score": expected,
        }
    )
    block["pattern_score_basis"] = return_validation.pattern_score_basis(
        patterns, antipatterns, block["not_evaluable"]
    )
    return_validation.validate_return(raw, catalog)
    return raw, expected


def _merge_v6(
    persist_results,
    return_validation,
    transcript_timing,
    tmp_path,
    catalog,
    raw,
):
    """Merge a validated v6 return, returning the stored talk and its vault."""
    import pattern_evidence

    vault, owner = _artifact(tmp_path, transcript_timing)
    canonical: dict[str, Any] = pattern_evidence.canonicalize_return_evidence(
        raw,
        owner,
        vault,
        catalog,
        pattern_scoring_schema_version=(
            return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
        ),
    )
    talk = copy.deepcopy(owner)
    talk["schema_version"] = persist_results.TALK_SCHEMA_VERSION
    talk["status"] = "reprocessing-inflight"
    persist_results.merge_talk(talk, raw, catalog=catalog, canonical_ret=canonical)
    return talk, vault


class TestAWeightedReturnReachesTheDatabase:
    """End to end: validate, canonicalize, merge — the path #308 died on.

    The unit tests above prove the contract. This proves a return that a worker
    actually emits reaches `resolve_pattern_score` with `weighted` set, which is
    the wiring the previous two fixes each got wrong in a different place.
    """

    @pytest.fixture
    def catalog(self, return_validation):
        return _weighted_catalog(return_validation)

    def _v6(self, return_validation, catalog, *, bare: bool):
        return _v6_return(return_validation, catalog, bare=bare)

    def _merge(
        self,
        persist_results,
        return_validation,
        transcript_timing,
        tmp_path,
        catalog,
        raw,
    ):
        talk, _ = _merge_v6(
            persist_results,
            return_validation,
            transcript_timing,
            tmp_path,
            catalog,
            raw,
        )
        return talk

    @pytest.mark.parametrize("bare", [True, False])
    def test_a_v6_return_persists_the_fraction_it_computed(
        self,
        persist_results,
        return_validation,
        transcript_timing,
        tmp_path,
        catalog,
        bare,
    ):
        """Both score shapes are legal on a v6 return, so both must persist."""
        raw, expected = self._v6(return_validation, catalog, bare=bare)

        talk = self._merge(
            persist_results,
            return_validation,
            transcript_timing,
            tmp_path,
            catalog,
            raw,
        )

        assert talk["pattern_score"] == expected
        assert math.isfinite(talk["pattern_score"])

    def test_the_persisted_score_is_stamped_at_the_weighted_generation(
        self,
        persist_results,
        return_validation,
        transcript_timing,
        tmp_path,
        catalog,
    ):
        """A weighted number filed under the flat generation joins the wrong cohort."""
        raw, _ = self._v6(return_validation, catalog, bare=True)

        talk = self._merge(
            persist_results,
            return_validation,
            transcript_timing,
            tmp_path,
            catalog,
            raw,
        )

        assert talk["pattern_scoring_schema_version"] == (
            return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
        )

    def test_a_v6_return_whose_score_contradicts_its_arrays_never_merges(
        self,
        persist_results,
        return_validation,
        transcript_timing,
        tmp_path,
        catalog,
    ):
        """The writer-side cross-check survives the trip through canonicalization.

        Matched on the weighted message, not on any `ValueError`: the flat
        contract also rejects this score, for the wrong reason (it is a float),
        so a bare `pytest.raises` here would pass with the split reverted.
        """
        raw, expected = self._v6(return_validation, catalog, bare=True)
        raw["pattern_observations"]["pattern_score"] = expected + 0.25

        with pytest.raises(ValueError, match="weighted detection arrays require"):
            self._merge(
                persist_results,
                return_validation,
                transcript_timing,
                tmp_path,
                catalog,
                raw,
            )


class TestTheMergedWeightedRecordValidatesAsPersistedState:
    """#299's last bullet: the chain runs to `validate_persisted_v2_analysis_state`.

    `TestAWeightedReturnReachesTheDatabase` stops at `merge_talk`, so the
    weighted shape was never put to the validator that gates publication —
    `persist-results.validate_effective_v2_state` and `write-analysis` both
    call it, and it accepts a snapshot only when the observation field set is
    one of four exact sets. A v6 record reaching it while only the v5 branch
    was wired would read as "noncanonical fields" at the first real persist.
    """

    @pytest.fixture
    def catalog(self, return_validation):
        return _weighted_catalog(return_validation)

    @pytest.fixture
    def stored(
        self,
        persist_results,
        return_validation,
        transcript_timing,
        tmp_path,
        catalog,
    ):
        raw, _ = _v6_return(return_validation, catalog, bare=True)
        talk, _ = _merge_v6(
            persist_results,
            return_validation,
            transcript_timing,
            tmp_path,
            catalog,
            raw,
        )
        return talk

    def test_a_merged_weighted_record_validates_as_persisted_state(
        self, return_validation, stored
    ):
        return_validation.validate_persisted_v2_analysis_state(stored)

    def test_it_validated_on_the_weighted_branch_and_not_a_laxer_one(
        self, return_validation, stored
    ):
        """Four field sets are accepted, so "it validated" names no branch.

        The v6 set is v5 plus the basis, so a record that lost its basis
        validates cleanly as a v5 one. Pinning the set is what distinguishes
        the weighted shape reaching its own branch from it falling through.
        """
        assert set(stored["pattern_observations"]) == set(
            return_validation.V6_PERSISTED_PATTERN_OBSERVATION_FIELDS
        )

    def test_the_weighted_shape_is_a_closed_set_at_this_validator(
        self, return_validation, stored
    ):
        """Otherwise the v6 branch reads as "v5 plus whatever else you sent"."""
        stored["pattern_observations"]["pattern_score_provenance"] = "worker"

        with pytest.raises(
            return_validation.ReturnValidationError, match="noncanonical fields"
        ):
            return_validation.validate_persisted_v2_analysis_state(stored)

    def test_the_production_gate_accepts_it_through_the_same_call(
        self, persist_results, return_validation, stored
    ):
        """`validate_effective_v2_state` is what persist-results actually runs."""
        persist_results.validate_effective_v2_state(
            stored,
            stored["structured_data"],
            pattern_snapshot_replaced=True,
        )


class TestTheWeightedRecordReadsBackFresh:
    """#317: the record persisted, and then every consumer refused it.

    Freshness is the gate on the renderer, the scoring cohort, the queue
    normalizer and the post-batch baseline. Its projection replay cross-checked
    every persisted score against the count difference, so a correct weighted
    score — fractional by construction — read as drift on a record the writer
    had just merged. Nothing was corrupt and nothing could converge: the queue
    requeued the talks it had just processed.

    This is the step that passes in isolation and failed in sequence, so it runs
    the real merge first rather than hand-building a persisted block.
    """

    @pytest.fixture
    def catalog(self, return_validation):
        return _weighted_catalog(return_validation)

    @pytest.fixture
    def stored(
        self,
        persist_results,
        return_validation,
        transcript_timing,
        tmp_path,
        catalog,
    ):
        raw, expected = _v6_return(return_validation, catalog, bare=True)
        talk, vault = _merge_v6(
            persist_results,
            return_validation,
            transcript_timing,
            tmp_path,
            catalog,
            raw,
        )
        return talk, vault, expected

    @staticmethod
    def _reasons(return_validation, talk, vault, catalog):
        return return_validation.assess_current_persisted_pattern_evidence_freshness(
            talk,
            vault_root=vault,
            catalog=catalog,
        )

    def test_a_merged_weighted_record_is_fresh(
        self, return_validation, catalog, stored
    ):
        talk, vault, expected = stored

        assert not float(expected).is_integer()
        assert talk["pattern_score"] == expected
        assert self._reasons(return_validation, talk, vault, catalog) == ()

    def test_a_weighted_score_its_own_lanes_contradict_is_drift(
        self, return_validation, catalog, stored
    ):
        """The replay still checks the arithmetic; it checks the right one."""
        talk, vault, expected = stored
        talk["pattern_score"] = expected + 0.25
        talk["pattern_observations"]["pattern_score"] = expected + 0.25

        assert self._reasons(return_validation, talk, vault, catalog) == (
            "pattern_score_projection_drift",
            "promoted_pattern_score_drift",
        )

    def test_the_count_difference_is_no_longer_the_weighted_cross_check(
        self, return_validation, catalog, stored
    ):
        """The exact #317 shape, inverted: the count difference is now the drift."""
        talk, vault, _ = stored
        observations = talk["pattern_observations"]
        flat = len(observations["patterns_detected"]) - len(
            observations["antipatterns_detected"]
        )
        talk["pattern_score"] = flat
        observations["pattern_score"] = flat

        assert "pattern_score_projection_drift" in self._reasons(
            return_validation, talk, vault, catalog
        )

    def test_a_weighted_record_without_its_basis_is_drift(
        self, return_validation, catalog, stored
    ):
        """A fractional number with no evidence composition behind it."""
        talk, vault, _ = stored
        talk["pattern_observations"].pop("pattern_score_basis")

        assert self._reasons(return_validation, talk, vault, catalog) == (
            "pattern_score_basis_projection_drift",
        )

    def test_a_basis_its_lanes_do_not_produce_is_drift(
        self, return_validation, catalog, stored
    ):
        """The basis is recomputed from the lanes, never trusted as stored."""
        talk, vault, _ = stored
        basis = talk["pattern_observations"]["pattern_score_basis"]
        basis["not_evaluable_count"] += 1

        assert self._reasons(return_validation, talk, vault, catalog) == (
            "pattern_score_basis_projection_drift",
        )

    def test_a_boolean_count_does_not_pass_as_the_one_it_equals(
        self, return_validation, catalog, stored
    ):
        """`True == 1` in Python, so value equality alone verifies nothing."""
        talk, vault, _ = stored
        counts = talk["pattern_observations"]["pattern_score_basis"]["patterns"]
        level = next(level for level, count in counts.items() if count == 1)
        counts[level] = True

        assert self._reasons(return_validation, talk, vault, catalog) == (
            "pattern_score_basis_projection_drift",
        )

    def test_a_boolean_weight_does_not_pass_as_the_one_it_equals(
        self, return_validation, catalog, stored
    ):
        """`True == 1.0`, so the weight table needs the same type gate as the counts.

        #322: the counts and the schema version were type-checked on the way
        back out; the weights got value equality alone, so a basis claiming
        `strong: true` replayed as the table the lanes require.
        """
        talk, vault, _ = stored
        weights = talk["pattern_observations"]["pattern_score_basis"]["weights"]
        level = next(level for level, weight in weights.items() if weight == 1.0)
        weights[level] = True

        assert self._reasons(return_validation, talk, vault, catalog) == (
            "pattern_score_basis_projection_drift",
        )

    def test_an_unstamped_record_is_replayed_under_no_arithmetic_at_all(
        self, return_validation, catalog, stored
    ):
        """Guessing the generation lets a record match by coincidence."""
        talk, vault, _ = stored
        talk.pop("pattern_scoring_schema_version")

        assert "pattern_scoring_schema_version_unusable" in self._reasons(
            return_validation, talk, vault, catalog
        )

    def test_a_detection_with_no_usable_confidence_names_that_defect(
        self, return_validation, catalog, stored
    ):
        """No confidence, no weight, no aggregate to compare the score against."""
        talk, vault, _ = stored
        talk["pattern_observations"]["patterns_detected"][0]["confidence"] = "certain"

        reasons = self._reasons(return_validation, talk, vault, catalog)
        assert "pattern_detection_confidence_invalid" in reasons
        assert "pattern_score_projection_drift" not in reasons


class TestTheFlatGenerationKeepsItsArithmetic:
    """The weighted allowance is an addition, not a replacement.

    A record stamped at the flat generation was written by a worker counting
    +1/-1. Replaying it under the weight table would restate what that worker
    meant, which is the reinterpretation the migration refuses to do — and it is
    why the v5→v6 migration restamps the record shape while leaving
    `pattern_scoring_schema_version: 5` on the score.
    """

    @pytest.fixture
    def catalog(self, return_validation):
        return _weighted_catalog(return_validation)

    @pytest.fixture
    def flat(
        self,
        persist_results,
        return_validation,
        transcript_timing,
        tmp_path,
        catalog,
    ):
        raw, _ = _v6_return(return_validation, catalog, bare=True)
        talk, vault = _merge_v6(
            persist_results,
            return_validation,
            transcript_timing,
            tmp_path,
            catalog,
            raw,
        )
        observations = talk["pattern_observations"]
        flat_score = len(observations["patterns_detected"]) - len(
            observations["antipatterns_detected"]
        )
        talk["pattern_scoring_schema_version"] = (
            return_validation.FLAT_PATTERN_SCORING_SCHEMA_VERSION
        )
        talk["pattern_score"] = flat_score
        observations["pattern_score"] = flat_score
        observations["opportunity_coverage_identity"] = importlib.import_module(
            "pattern_evidence"
        ).opportunity_coverage_identity(
            observations["pattern_outcomes"],
            pattern_catalog_fingerprint=talk["pattern_catalog_fingerprint"],
            pattern_scoring_schema_version=(
                return_validation.FLAT_PATTERN_SCORING_SCHEMA_VERSION
            ),
        )
        return talk, vault

    @staticmethod
    def _reasons(return_validation, talk, vault, catalog):
        return return_validation.assess_current_persisted_pattern_evidence_freshness(
            talk,
            vault_root=vault,
            catalog=catalog,
        )

    def test_a_flat_record_carrying_a_weighted_basis_is_drift(
        self, return_validation, catalog, flat
    ):
        """The basis is a weighted-generation field; a flat record cannot hold one."""
        talk, vault = flat

        assert "pattern_score_basis_projection_drift" in self._reasons(
            return_validation, talk, vault, catalog
        )

    def test_a_flat_record_is_still_checked_against_the_count_difference(
        self, return_validation, catalog, flat
    ):
        talk, vault = flat
        talk["pattern_observations"].pop("pattern_score_basis")

        assert self._reasons(return_validation, talk, vault, catalog) == ()

    def test_a_fraction_at_the_flat_generation_is_still_drift(
        self, return_validation, catalog, flat
    ):
        """A float there means some other arithmetic produced the number."""
        talk, vault = flat
        talk["pattern_observations"].pop("pattern_score_basis")
        talk["pattern_score"] = 0.75
        talk["pattern_observations"]["pattern_score"] = 0.75

        assert self._reasons(return_validation, talk, vault, catalog) == (
            "pattern_score_projection_drift",
            "promoted_pattern_score_drift",
        )


def test_the_mirrored_weight_table_matches_its_source(return_validation):
    """`pattern_evidence` restates the table because it sits below its consumer.

    A weight change that lands in one file and not the other splits the
    arithmetic in half: the writer stores one number and the freshness replay
    demands another, which is #317 with a different root cause.
    """
    pattern_evidence = importlib.import_module("pattern_evidence")

    assert pattern_evidence.DETECTION_WEIGHTS == return_validation.DETECTION_WEIGHTS
    assert pattern_evidence.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION == (
        return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
    )
