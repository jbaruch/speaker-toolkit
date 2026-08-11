"""The persisted-observation validator's classification contract (#167).

Return validation guards what a subagent hands in; nothing guarded what was
already stored. The live vault holds every shape these tests pin: a legacy list
container, an absent one, 28 detections with `evidence` and `dimensions`
swapped, order-only and membership dimension drift, missing dimension arrays,
IDs no catalog entry claims, and detections of entries since marked
`observable: false`.

Fixtures are built from the live catalog rather than hardcoded IDs, so a catalog
edit that removes an entry fails these tests instead of quietly reclassifying
what they assert.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(scope="session")
def catalog(return_validation):
    return return_validation.load_catalog()


@pytest.fixture(scope="session")
def observable_entry(catalog):
    """One observable entry with at least two dimensions, for order drift."""
    for entry in sorted(catalog.entries.values(), key=lambda item: item.pattern_id):
        if entry.observable and len(entry.vault_dimensions) >= 2:
            return entry
    raise AssertionError("catalog has no observable entry with two dimensions")


@pytest.fixture(scope="session")
def archival_entry(catalog):
    """One entry the catalog no longer treats as observable."""
    for entry in sorted(catalog.entries.values(), key=lambda item: item.pattern_id):
        if not entry.observable:
            return entry
    raise AssertionError("catalog has no unobservable entry")


def _detection(entry, **overrides):
    detection = {
        "pattern_id": entry.pattern_id,
        "confidence": "strong",
        "evidence": "The speaker did the thing, at 12:03.",
        "dimensions": list(entry.vault_dimensions),
    }
    detection.update(overrides)
    return detection


def _collection_name(entry) -> str:
    return (
        "antipatterns_detected"
        if entry.entry_type == "antipattern"
        else "patterns_detected"
    )


def _block(**lanes) -> dict[str, Any]:
    """A current block carries every lane the canonical writer emits."""
    block: dict[str, Any] = {
        "patterns_detected": [],
        "antipatterns_detected": [],
        "not_evaluable": [],
    }
    block.update(lanes)
    return block


def _talk(entry, *detections) -> dict[str, Any]:
    return {
        "pattern_observations": _block(**{_collection_name(entry): list(detections)})
    }


def test_a_clean_block_is_usable(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    talk = _talk(observable_entry, _detection(observable_entry))

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is True
    assert assessment.findings == ()
    assert assessment.detection_count == 1
    assert assessment.archival_count == 0


def test_an_absent_block_is_not_current(
    persisted_pattern_observations, catalog
) -> None:
    """Nine live talks carry no block at all."""
    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        {"filename": "a.md"}, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (persisted_pattern_observations.CONTAINER_ABSENT,)


def test_the_legacy_list_container_is_not_current(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    """81 live talks carry the pre-#147 list shape.

    It is readable as history and never as a current block: a bare list carries
    no collection names to audit a detection against.
    """
    talk = {"pattern_observations": [_detection(observable_entry)]}

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.CONTAINER_LEGACY_LIST,
    )
    assert assessment.detection_count == 1


@pytest.mark.parametrize("container", ["a string", 7, True])
def test_a_non_container_is_refused(
    persisted_pattern_observations, catalog, container
) -> None:
    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        {"pattern_observations": container}, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.CONTAINER_INVALID,
    )


def test_a_non_list_collection_is_refused(
    persisted_pattern_observations, catalog
) -> None:
    talk = {"pattern_observations": _block(patterns_detected={"pattern_id": "x"})}

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.COLLECTION_INVALID,
    )


@pytest.mark.parametrize(
    "lane", ["patterns_detected", "antipatterns_detected", "not_evaluable"]
)
def test_an_absent_lane_is_not_an_empty_lane(
    persisted_pattern_observations, catalog, lane
) -> None:
    """A block missing a lane is one whose writer never finished.

    Reading it as empty reports coverage the record never claimed — `{}` would
    pass as a clean current block.
    """
    block = _block()
    del block[lane]
    talk = {"pattern_observations": block}

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.COLLECTION_ABSENT,
    )
    assert assessment.findings[0].location == lane


def test_an_empty_block_is_refused(persisted_pattern_observations, catalog) -> None:
    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        {"pattern_observations": {}}, catalog
    )

    assert assessment.usable is False
    assert [finding.location for finding in assessment.findings] == [
        "patterns_detected",
        "antipatterns_detected",
        "not_evaluable",
    ]


def test_a_malformed_outcome_lane_is_refused(
    persisted_pattern_observations, catalog
) -> None:
    talk = {"pattern_observations": _block(not_evaluable={"pattern_id": "x"})}

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.COLLECTION_INVALID,
    )


@pytest.mark.parametrize(
    ("record", "code"),
    [
        ("a string", "DETECTION_NOT_OBJECT"),
        ({}, "DETECTION_ID_MISSING"),
        ({"pattern_id": "cultural_map_disclaimer"}, "DETECTION_ID_UNKNOWN"),
    ],
)
def test_outcome_records_are_audited_for_identity(
    persisted_pattern_observations, catalog, record, code
) -> None:
    """Outcome records carry no evidence to check, but they do name a pattern."""
    talk = {"pattern_observations": _block(not_evaluable=[record])}

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (getattr(persisted_pattern_observations, code),)


def test_a_polarity_mismatch_is_refused(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    """The lane is the claim: a pattern filed as an antipattern inverts it."""
    wrong_lane = (
        "patterns_detected"
        if observable_entry.entry_type == "antipattern"
        else "antipatterns_detected"
    )
    talk = {
        "pattern_observations": _block(**{wrong_lane: [_detection(observable_entry)]})
    }

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.DETECTION_POLARITY_MISMATCH,
    )
    assert assessment.findings[0].pattern_id == observable_entry.pattern_id


def test_both_lanes_reject_the_other_polarity(
    persisted_pattern_observations, catalog
) -> None:
    """Neither lane is the lenient one."""
    pattern = next(
        entry
        for entry in sorted(catalog.entries.values(), key=lambda item: item.pattern_id)
        if entry.observable and entry.entry_type == "pattern"
    )
    antipattern = next(
        entry
        for entry in sorted(catalog.entries.values(), key=lambda item: item.pattern_id)
        if entry.observable and entry.entry_type == "antipattern"
    )
    talk = {
        "pattern_observations": _block(
            patterns_detected=[_detection(antipattern)],
            antipatterns_detected=[_detection(pattern)],
        )
    }

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert [finding.location for finding in assessment.findings] == [
        "patterns_detected[0]",
        "antipatterns_detected[0]",
    ]
    assert assessment.reason_codes == (
        persisted_pattern_observations.DETECTION_POLARITY_MISMATCH,
    )


def test_the_swapped_field_signature_is_reported_once_and_repairable(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    """The 28-detection signature from one live talk.

    Both fields satisfy the other's schema exactly, so the repair is a swap and
    loses nothing. It is one finding, not two: reporting each field separately
    would read as two independent defects and invite two independent guesses.
    """
    prose = "The speaker opened with the map, at 00:41."
    swapped = _detection(
        observable_entry,
        evidence=list(observable_entry.vault_dimensions),
        dimensions=prose,
    )
    talk = _talk(observable_entry, swapped)

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (persisted_pattern_observations.FIELDS_SWAPPED,)
    assert len(assessment.repairs) == 1
    repair = assessment.repairs[0]
    assert repair.evidence == prose
    assert repair.dimensions == observable_entry.vault_dimensions


def test_applying_the_repair_restores_both_values(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    prose = "The speaker opened with the map, at 00:41."
    talk = _talk(
        observable_entry,
        _detection(
            observable_entry,
            evidence=list(observable_entry.vault_dimensions),
            dimensions=prose,
        ),
    )
    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    repaired = persisted_pattern_observations.apply_swapped_field_repairs(
        talk, assessment.repairs
    )

    collection = repaired["pattern_observations"][_collection_name(observable_entry)]
    assert collection[0]["evidence"] == prose
    assert collection[0]["dimensions"] == list(observable_entry.vault_dimensions)
    # The input is untouched: a repair returns a new talk rather than mutating
    # the generation it was assessed against.
    stored: Any = talk["pattern_observations"][_collection_name(observable_entry)]
    assert stored[0]["dimensions"] == prose
    after = persisted_pattern_observations.assess_persisted_pattern_observations(
        repaired, catalog
    )
    assert after.usable is True


def test_a_repair_against_a_changed_talk_is_refused(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    """The talk moved since it was assessed, and this is not the assessment."""
    talk = _talk(
        observable_entry,
        _detection(
            observable_entry,
            evidence=list(observable_entry.vault_dimensions),
            dimensions="prose",
        ),
    )
    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )
    moved = _talk(observable_entry, _detection(observable_entry))

    with pytest.raises(ValueError, match="reassess the talk"):
        persisted_pattern_observations.apply_swapped_field_repairs(
            moved, assessment.repairs
        )


def test_a_half_swap_is_two_defects_not_a_repair(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    """Guessing at one side of an inexact swap would destroy the other."""
    talk = _talk(
        observable_entry,
        _detection(observable_entry, evidence=[99], dimensions="prose"),
    )

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.repairs == ()
    assert assessment.reason_codes == (
        persisted_pattern_observations.DETECTION_EVIDENCE_INVALID,
        persisted_pattern_observations.DIMENSIONS_INVALID,
    )


def test_order_only_drift_is_distinguished_from_membership_drift(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    """23 live detections reorder the catalog value; 38 name a different set."""
    reordered = list(reversed(observable_entry.vault_dimensions))
    talk = _talk(observable_entry, _detection(observable_entry, dimensions=reordered))

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.DIMENSIONS_ORDER_DRIFT,
    )


def test_membership_drift_is_never_auto_mapped(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    """A different set is a semantic claim; #156 owns that review."""
    foreign = [
        dimension
        for dimension in range(1, 15)
        if dimension not in observable_entry.vault_dimensions
    ][:1]
    talk = _talk(observable_entry, _detection(observable_entry, dimensions=foreign))

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.DIMENSIONS_MEMBERSHIP_DRIFT,
    )
    assert assessment.repairs == ()


def test_a_missing_dimensions_array_is_reported(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    """1,129 live detections carry legacy or missing dimension arrays."""
    detection = _detection(observable_entry)
    del detection["dimensions"]
    talk = _talk(observable_entry, detection)

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.DIMENSIONS_ABSENT,
    )


@pytest.mark.parametrize(
    "legacy_id",
    ["cultural_map_disclaimer", "plane_exercise_closing", "extended_qa_as_closing"],
)
def test_an_unknown_id_is_never_mapped_to_a_neighbour(
    persisted_pattern_observations, catalog, observable_entry, legacy_id
) -> None:
    """The three live legacy IDs. What they meant is an owner decision."""
    talk = _talk(observable_entry, _detection(observable_entry, pattern_id=legacy_id))

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.DETECTION_ID_UNKNOWN,
    )
    assert assessment.findings[0].pattern_id == legacy_id


def test_an_unobservable_entry_is_archival_not_malformed(
    persisted_pattern_observations, catalog, archival_entry
) -> None:
    """641 live detections reference entries the catalog no longer observes.

    The record is well-formed; the catalog moved. It is reported so a caller can
    exclude it from the current cohort, and it does not make the talk unusable.
    """
    talk = _talk(archival_entry, _detection(archival_entry))

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is True
    assert assessment.reason_codes == (
        persisted_pattern_observations.ENTRY_NOT_OBSERVABLE,
    )
    assert assessment.archival_count == 1


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("confidence", "very sure", "DETECTION_CONFIDENCE_INVALID"),
        ("confidence", None, "DETECTION_CONFIDENCE_INVALID"),
        ("evidence", "", "DETECTION_EVIDENCE_INVALID"),
        ("evidence", "   ", "DETECTION_EVIDENCE_INVALID"),
        ("evidence", 12, "DETECTION_EVIDENCE_INVALID"),
    ],
)
def test_malformed_detection_fields_are_typed(
    persisted_pattern_observations, catalog, observable_entry, field, value, code
) -> None:
    talk = _talk(observable_entry, _detection(observable_entry, **{field: value}))

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (getattr(persisted_pattern_observations, code),)


@pytest.mark.parametrize("detection", ["a string", 7, None, ["nested"]])
def test_a_non_object_detection_is_refused(
    persisted_pattern_observations, catalog, detection
) -> None:
    talk = {"pattern_observations": _block(patterns_detected=[detection])}

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.DETECTION_NOT_OBJECT,
    )


def test_a_detection_without_an_id_is_refused(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    detection = _detection(observable_entry)
    del detection["pattern_id"]
    talk = _talk(observable_entry, detection)

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert assessment.usable is False
    assert assessment.reason_codes == (
        persisted_pattern_observations.DETECTION_ID_MISSING,
    )


def test_every_defect_in_a_block_is_located(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    """A corrupt talk usually holds several; a caller repairs by location."""
    detection_missing_dimensions = _detection(observable_entry)
    del detection_missing_dimensions["dimensions"]
    talk = _talk(
        observable_entry,
        _detection(observable_entry),
        detection_missing_dimensions,
        _detection(observable_entry, pattern_id="cultural_map_disclaimer"),
    )
    collection = _collection_name(observable_entry)

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    assert [finding.location for finding in assessment.findings] == [
        f"{collection}[1]",
        f"{collection}[2]",
    ]
    assert assessment.detection_count == 3


def test_the_report_is_json_ready(
    persisted_pattern_observations, catalog, observable_entry
) -> None:
    """Consumers write this into reports, so it has to serialize as-is."""
    import json

    talk = _talk(
        observable_entry,
        _detection(
            observable_entry,
            evidence=list(observable_entry.vault_dimensions),
            dimensions="prose",
        ),
    )

    assessment = persisted_pattern_observations.assess_persisted_pattern_observations(
        talk, catalog
    )

    payload = json.loads(json.dumps(assessment.as_dict()))
    assert payload["usable"] is False
    assert payload["schema_version"] == (
        persisted_pattern_observations.ASSESSMENT_SCHEMA_VERSION
    )
    assert payload["repairs"][0]["dimensions"] == list(
        observable_entry.vault_dimensions
    )
