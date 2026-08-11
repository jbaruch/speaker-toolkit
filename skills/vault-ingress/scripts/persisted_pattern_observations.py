#!/usr/bin/env python3
"""Structural audit of pattern detections already stored in the database (#167).

Return validation guards what a subagent hands in. Nothing guarded what is
already persisted, and the live vault shows why that matters: across 209 talks
and 5,222 detection objects, `pattern_observations` is a dict on 119 talks, a
legacy list on 81, and absent on 9; 28 detections in one talk have `evidence`
and `dimensions` swapped; 1,129 carry legacy or missing dimension arrays; 3 name
IDs no catalog entry claims; and 641 reference entries since marked
`observable: false`.

A record-schema migration can stamp any of those as current without ever
looking inside the nested block, so the corruption survives into rendered
analyses and derived profile state.

This module is the read-only classifier the migration, preflight, rendering,
profile, and queue paths share. It decides nothing about remediation: it says
what is wrong, in stable reason codes, and says which single defect — the exact
inverse-schema field swap — is losslessly repairable. Everything else is an
owner decision, and semantic dimension mappings belong to the catalog review in
#156, never here.

Pure function of (talk, catalog): no filesystem, no clock, no network.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable

from return_validation import CONFIDENCE_LEVELS, PatternCatalog

ASSESSMENT_SCHEMA_VERSION = 1

# The detection collections a persisted block carries, each bound to the catalog
# polarity its members must have: a `pattern` entry filed under
# `antipatterns_detected` inverts what the record claims the speaker did.
DETECTION_COLLECTIONS = {
    "patterns_detected": "pattern",
    "antipatterns_detected": "antipattern",
}

# `not_evaluable` holds outcome records rather than detections, so it is audited
# for container shape and catalog identity alone.
OUTCOME_COLLECTION = "not_evaluable"

# Every lane the canonical writer emits. A current block missing one is not a
# leaner current block: it is a block whose writer never finished, and treating
# an absent lane as an empty one reports invented completeness.
REQUIRED_COLLECTIONS = (*DETECTION_COLLECTIONS, OUTCOME_COLLECTION)

# Catalog dimensions are integers 1-14 (`vault_dimensions` in every entry's
# frontmatter). The bound is the catalog's, restated here only as the swap
# signature's type test.
MINIMUM_DIMENSION = 1
MAXIMUM_DIMENSION = 14

# Stable reason codes. Consumers route on these; the messages are prose and may
# be reworded. Grouped by what the owner has to do about them.

# The block itself, before any detection is read.
CONTAINER_ABSENT = "observations_absent"
CONTAINER_LEGACY_LIST = "observations_legacy_list"
CONTAINER_INVALID = "observations_invalid"
COLLECTION_ABSENT = "detection_collection_absent"
COLLECTION_INVALID = "detection_collection_invalid"

# One detection object's own shape.
DETECTION_NOT_OBJECT = "detection_not_object"
DETECTION_ID_MISSING = "detection_pattern_id_missing"
DETECTION_ID_UNKNOWN = "detection_pattern_id_unknown"
DETECTION_CONFIDENCE_INVALID = "detection_confidence_invalid"
DETECTION_EVIDENCE_INVALID = "detection_evidence_invalid"
DETECTION_POLARITY_MISMATCH = "detection_polarity_mismatch"

# The dimensions array, in increasing order of ambiguity.
DIMENSIONS_ABSENT = "dimensions_absent"
DIMENSIONS_INVALID = "dimensions_invalid"
DIMENSIONS_ORDER_DRIFT = "dimensions_order_drift"
DIMENSIONS_MEMBERSHIP_DRIFT = "dimensions_membership_drift"

# The one signature that is unambiguous enough to repair without losing data.
FIELDS_SWAPPED = "detection_fields_swapped"

# Not a defect in the record: the catalog moved. Archival evidence, never
# current observable scoring evidence.
ENTRY_NOT_OBSERVABLE = "detection_entry_not_observable"

# Findings that leave the talk unusable as current scoring evidence. A swapped
# pair is repairable but still not current until the repair lands, and an
# unobservable entry is archival rather than malformed — neither is silently
# tolerated, and only the archival case leaves the record itself valid.
BLOCKING_REASONS = frozenset(
    {
        CONTAINER_ABSENT,
        CONTAINER_LEGACY_LIST,
        CONTAINER_INVALID,
        COLLECTION_ABSENT,
        COLLECTION_INVALID,
        DETECTION_NOT_OBJECT,
        DETECTION_ID_MISSING,
        DETECTION_ID_UNKNOWN,
        DETECTION_CONFIDENCE_INVALID,
        DETECTION_EVIDENCE_INVALID,
        DETECTION_POLARITY_MISMATCH,
        DIMENSIONS_ABSENT,
        DIMENSIONS_INVALID,
        DIMENSIONS_ORDER_DRIFT,
        DIMENSIONS_MEMBERSHIP_DRIFT,
        FIELDS_SWAPPED,
    }
)


@dataclass(frozen=True)
class ObservationFinding:
    """One defect, located precisely enough to repair or review by hand."""

    reason_code: str
    location: str
    pattern_id: str | None
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "location": self.location,
            "pattern_id": self.pattern_id,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SwappedFieldRepair:
    """One detection whose `evidence` and `dimensions` are exact inverses.

    Carries both original values, so applying the repair is a swap and never a
    reconstruction: a repair that cannot restore what it replaced is a rewrite.
    """

    location: str
    pattern_id: str
    evidence: str
    dimensions: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "pattern_id": self.pattern_id,
            "evidence": self.evidence,
            "dimensions": list(self.dimensions),
        }


@dataclass(frozen=True)
class PersistedObservationAssessment:
    """What one talk's persisted observations are, in stable terms."""

    schema_version: int
    usable: bool
    findings: tuple[ObservationFinding, ...]
    repairs: tuple[SwappedFieldRepair, ...]
    detection_count: int
    archival_count: int

    @property
    def reason_codes(self) -> tuple[str, ...]:
        """Every distinct code, sorted, for a caller that routes on shape."""
        return tuple(sorted({finding.reason_code for finding in self.findings}))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "usable": self.usable,
            "findings": [finding.as_dict() for finding in self.findings],
            "repairs": [repair.as_dict() for repair in self.repairs],
            "detection_count": self.detection_count,
            "archival_count": self.archival_count,
            "reason_codes": list(self.reason_codes),
        }


def _is_dimension_list(value: Any) -> bool:
    """A non-empty list of in-range dimension integers, booleans excluded."""
    if not isinstance(value, list) or not value:
        return False
    return all(
        not isinstance(item, bool)
        and isinstance(item, int)
        and MINIMUM_DIMENSION <= item <= MAXIMUM_DIMENSION
        for item in value
    )


def _is_evidence_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _swapped_repair(
    detection: dict[str, Any],
    location: str,
    pattern_id: str,
) -> SwappedFieldRepair | None:
    """The repair for an exact inverse-schema swap, or nothing.

    Both sides must satisfy the other's schema exactly. A `dimensions` value
    that is prose and an `evidence` value that is a half-valid list is not a
    swap — it is two separate defects, and guessing at one would destroy the
    other.
    """
    evidence = detection.get("evidence")
    dimensions = detection.get("dimensions")
    if not _is_dimension_list(evidence) or not _is_evidence_text(dimensions):
        return None
    assert isinstance(dimensions, str)  # _is_evidence_text postcondition
    assert isinstance(evidence, list)  # _is_dimension_list postcondition
    return SwappedFieldRepair(
        location=location,
        pattern_id=pattern_id,
        evidence=dimensions,
        dimensions=tuple(evidence),
    )


def _audit_dimensions(
    detection: dict[str, Any],
    location: str,
    pattern_id: str,
    expected: tuple[int, ...],
) -> ObservationFinding | None:
    """Classify the dimensions array against the catalog's ordered value."""
    dimensions = detection.get("dimensions")
    if dimensions is None:
        return ObservationFinding(
            DIMENSIONS_ABSENT,
            location,
            pattern_id,
            "detection carries no dimensions array",
        )
    if not _is_dimension_list(dimensions):
        return ObservationFinding(
            DIMENSIONS_INVALID,
            location,
            pattern_id,
            "dimensions must be a non-empty array of integers 1 through 14",
        )
    stored = tuple(dimensions)
    if stored == expected:
        return None
    if sorted(stored) == sorted(expected):
        # Same membership, different order. Mechanical to fix, but the catalog
        # owns the order, so it is still reported rather than silently sorted.
        return ObservationFinding(
            DIMENSIONS_ORDER_DRIFT,
            location,
            pattern_id,
            f"dimensions {list(stored)} reorder the catalog value {list(expected)}",
        )
    # Different membership is a semantic claim about what the pattern measures.
    # #156 owns that review; auto-mapping it here would invent evidence.
    return ObservationFinding(
        DIMENSIONS_MEMBERSHIP_DRIFT,
        location,
        pattern_id,
        f"dimensions {list(stored)} differ from the catalog value {list(expected)}",
    )


def _audit_detection(
    detection: Any,
    location: str,
    catalog: PatternCatalog,
    expected_type: str,
) -> tuple[list[ObservationFinding], SwappedFieldRepair | None, bool]:
    """Audit one detection object. Returns (findings, repair, archival)."""
    if not isinstance(detection, dict):
        return (
            [
                ObservationFinding(
                    DETECTION_NOT_OBJECT,
                    location,
                    None,
                    "detection must be an object",
                )
            ],
            None,
            False,
        )
    pattern_id = detection.get("pattern_id")
    if not isinstance(pattern_id, str) or not pattern_id:
        return (
            [
                ObservationFinding(
                    DETECTION_ID_MISSING,
                    location,
                    None,
                    "detection carries no pattern_id",
                )
            ],
            None,
            False,
        )
    entry = catalog.entries.get(pattern_id)
    if entry is None:
        # Never mapped to a near neighbour: a legacy ID is an owner decision
        # about what the observation meant, not a spelling correction.
        return (
            [
                ObservationFinding(
                    DETECTION_ID_UNKNOWN,
                    location,
                    pattern_id,
                    "no catalog entry claims this pattern_id",
                )
            ],
            None,
            False,
        )

    findings: list[ObservationFinding] = []
    if entry.entry_type != expected_type:
        # The lane is the claim: a pattern filed as an antipattern inverts what
        # the record says the speaker did, and no field inside the detection
        # says otherwise.
        findings.append(
            ObservationFinding(
                DETECTION_POLARITY_MISMATCH,
                location,
                pattern_id,
                f"catalog entry is a {entry.entry_type} and cannot be filed here",
            )
        )
    archival = not entry.observable
    if archival:
        findings.append(
            ObservationFinding(
                ENTRY_NOT_OBSERVABLE,
                location,
                pattern_id,
                "catalog entry is no longer observable; evidence is archival",
            )
        )

    repair = _swapped_repair(detection, location, pattern_id)
    if repair is not None:
        # One finding for the pair. Reporting the two fields separately would
        # read as two independent defects and invite two independent guesses.
        findings.append(
            ObservationFinding(
                FIELDS_SWAPPED,
                location,
                pattern_id,
                "evidence holds the dimensions array and dimensions holds the "
                "evidence text",
            )
        )
        return findings, repair, archival

    confidence = detection.get("confidence")
    if confidence not in CONFIDENCE_LEVELS:
        findings.append(
            ObservationFinding(
                DETECTION_CONFIDENCE_INVALID,
                location,
                pattern_id,
                f"confidence must be one of {sorted(CONFIDENCE_LEVELS)}",
            )
        )
    if not _is_evidence_text(detection.get("evidence")):
        findings.append(
            ObservationFinding(
                DETECTION_EVIDENCE_INVALID,
                location,
                pattern_id,
                "evidence must be non-empty text",
            )
        )
    dimension_finding = _audit_dimensions(
        detection,
        location,
        pattern_id,
        entry.vault_dimensions,
    )
    if dimension_finding is not None:
        findings.append(dimension_finding)
    return findings, repair, archival


def _audit_collection(
    observations: dict[str, Any],
    name: str,
    catalog: PatternCatalog,
    expected_type: str,
) -> tuple[list[ObservationFinding], list[SwappedFieldRepair], int, int]:
    """Audit one detection collection. Returns (findings, repairs, count, archival)."""
    if name not in observations:
        return (
            [
                ObservationFinding(
                    COLLECTION_ABSENT,
                    name,
                    None,
                    f"a current block carries {name}; an absent lane is not an "
                    "empty one",
                )
            ],
            [],
            0,
            0,
        )
    raw = observations.get(name)
    if not isinstance(raw, list):
        return (
            [
                ObservationFinding(
                    COLLECTION_INVALID,
                    name,
                    None,
                    f"{name} must be an array of detection objects",
                )
            ],
            [],
            0,
            0,
        )
    findings: list[ObservationFinding] = []
    repairs: list[SwappedFieldRepair] = []
    archival = 0
    for index, detection in enumerate(raw):
        found, repair, is_archival = _audit_detection(
            detection,
            f"{name}[{index}]",
            catalog,
            expected_type,
        )
        findings.extend(found)
        if repair is not None:
            repairs.append(repair)
        if is_archival:
            archival += 1
    return findings, repairs, len(raw), archival


def _audit_outcomes(
    observations: dict[str, Any],
    catalog: PatternCatalog,
) -> list[ObservationFinding]:
    """Audit the `not_evaluable` lane's shape and catalog identity.

    These are outcome records, not detections: they carry no evidence or
    dimensions to check. What they must be is present, listed, and named by an
    ID the catalog claims — an unreadable lane leaves the block's coverage
    unknown, which is not the same as complete.
    """
    if OUTCOME_COLLECTION not in observations:
        return [
            ObservationFinding(
                COLLECTION_ABSENT,
                OUTCOME_COLLECTION,
                None,
                f"a current block carries {OUTCOME_COLLECTION}; an absent lane "
                "is not an empty one",
            )
        ]
    raw = observations.get(OUTCOME_COLLECTION)
    if not isinstance(raw, list):
        return [
            ObservationFinding(
                COLLECTION_INVALID,
                OUTCOME_COLLECTION,
                None,
                f"{OUTCOME_COLLECTION} must be an array of outcome records",
            )
        ]
    findings: list[ObservationFinding] = []
    for index, record in enumerate(raw):
        location = f"{OUTCOME_COLLECTION}[{index}]"
        if not isinstance(record, dict):
            findings.append(
                ObservationFinding(
                    DETECTION_NOT_OBJECT,
                    location,
                    None,
                    "outcome record must be an object",
                )
            )
            continue
        pattern_id = record.get("pattern_id")
        if not isinstance(pattern_id, str) or not pattern_id:
            findings.append(
                ObservationFinding(
                    DETECTION_ID_MISSING,
                    location,
                    None,
                    "outcome record carries no pattern_id",
                )
            )
            continue
        if pattern_id not in catalog.entries:
            findings.append(
                ObservationFinding(
                    DETECTION_ID_UNKNOWN,
                    location,
                    pattern_id,
                    "no catalog entry claims this pattern_id",
                )
            )
    return findings


def _blocking(findings: Iterable[ObservationFinding]) -> bool:
    return any(finding.reason_code in BLOCKING_REASONS for finding in findings)


def assess_persisted_pattern_observations(
    talk: Any,
    catalog: PatternCatalog,
) -> PersistedObservationAssessment:
    """Classify one talk's persisted pattern observations.

    ``usable`` means the block can be read as current scoring evidence. It is
    false for every structural defect, the repairable swap included: the repair
    has to land before the record is current, and reporting it as usable would
    let the corruption through the gate that found it.
    """
    observations = talk.get("pattern_observations") if isinstance(talk, dict) else None
    if observations is None:
        return PersistedObservationAssessment(
            schema_version=ASSESSMENT_SCHEMA_VERSION,
            usable=False,
            findings=(
                ObservationFinding(
                    CONTAINER_ABSENT,
                    "pattern_observations",
                    None,
                    "talk carries no persisted pattern observations",
                ),
            ),
            repairs=(),
            detection_count=0,
            archival_count=0,
        )
    if isinstance(observations, list):
        # The pre-#147 shape. Readable as history, never as a current block:
        # it carries no collection names to audit against.
        return PersistedObservationAssessment(
            schema_version=ASSESSMENT_SCHEMA_VERSION,
            usable=False,
            findings=(
                ObservationFinding(
                    CONTAINER_LEGACY_LIST,
                    "pattern_observations",
                    None,
                    "pattern_observations is the legacy list shape",
                ),
            ),
            repairs=(),
            detection_count=len(observations),
            archival_count=0,
        )
    if not isinstance(observations, dict):
        return PersistedObservationAssessment(
            schema_version=ASSESSMENT_SCHEMA_VERSION,
            usable=False,
            findings=(
                ObservationFinding(
                    CONTAINER_INVALID,
                    "pattern_observations",
                    None,
                    "pattern_observations must be an object",
                ),
            ),
            repairs=(),
            detection_count=0,
            archival_count=0,
        )

    findings: list[ObservationFinding] = []
    repairs: list[SwappedFieldRepair] = []
    detections = 0
    archival = 0
    for name, expected_type in DETECTION_COLLECTIONS.items():
        found, repaired, count, archived = _audit_collection(
            observations,
            name,
            catalog,
            expected_type,
        )
        findings.extend(found)
        repairs.extend(repaired)
        detections += count
        archival += archived
    findings.extend(_audit_outcomes(observations, catalog))
    return PersistedObservationAssessment(
        schema_version=ASSESSMENT_SCHEMA_VERSION,
        usable=not _blocking(findings),
        findings=tuple(findings),
        repairs=tuple(repairs),
        detection_count=detections,
        archival_count=archival,
    )


def apply_swapped_field_repairs(
    talk: dict[str, Any],
    repairs: Iterable[SwappedFieldRepair],
) -> dict[str, Any]:
    """Return a copy of ``talk`` with each exact inverse swap undone.

    Only the two swapped values move, and both come from the repair record, so
    the operation is reversible and loses nothing. A repair whose location no
    longer holds the swapped shape is refused rather than forced: the talk
    changed since it was assessed, and this is not the assessment.
    """
    repaired = copy.deepcopy(talk)
    observations = repaired.get("pattern_observations")
    if not isinstance(observations, dict):
        raise ValueError(
            "cannot repair a talk whose pattern_observations is not an object; "
            "reassess the talk and apply the repairs it reports"
        )
    for repair in repairs:
        name, _, index_text = repair.location.partition("[")
        index = int(index_text.rstrip("]"))
        collection = observations.get(name)
        if not isinstance(collection, list) or index >= len(collection):
            raise ValueError(
                f"repair target {repair.location} is absent; reassess the talk "
                "and apply the repairs it reports"
            )
        detection = collection[index]
        # The identity is checked against the record, never supplied to it:
        # passing the repair's own pattern_id into the shape check would let a
        # detection that became a different pattern — same swapped fields, new
        # id — compare equal and be rewritten.
        if (
            not isinstance(detection, dict)
            or detection.get("pattern_id") != repair.pattern_id
            or _swapped_repair(detection, repair.location, repair.pattern_id) != repair
        ):
            raise ValueError(
                f"repair target {repair.location} no longer holds the swapped "
                "shape it was assessed with; reassess the talk and apply the "
                "repairs it reports"
            )
        detection["evidence"] = repair.evidence
        detection["dimensions"] = list(repair.dimensions)
    return repaired
