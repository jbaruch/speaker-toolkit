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
