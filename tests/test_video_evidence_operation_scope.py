"""Operation-local source-video assessment wiring regressions."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


def test_return_freshness_wrapper_forwards_the_supplied_assessment(
    return_validation,
    monkeypatch,
    tmp_path,
) -> None:
    assessment = object()
    observed: list[object] = []

    def assess_artifact(_talk, **kwargs):
        observed.append(kwargs["video_evidence_assessment"])
        return ()

    monkeypatch.setattr(
        return_validation,
        "assess_artifact_freshness",
        assess_artifact,
    )

    assert (
        return_validation.assess_current_persisted_pattern_evidence_freshness(
            {},
            vault_root=tmp_path,
            video_evidence_assessment=assessment,
        )
        == ()
    )
    assert observed == [assessment]


def test_persist_operation_reuses_one_assessment_for_every_video_consumer(
    persist_results,
    monkeypatch,
    tmp_path,
) -> None:
    assessment = object()
    created: list[object] = []
    observed: list[tuple[str, object]] = []
    talk = {"filename": "talk.md", "status": "processed"}
    database = {"config": {}, "talks": [talk]}
    returned = {
        "filename": "talk.md",
        "return_schema_version": 4,
        "status": "processed",
    }
    snapshot = object()

    def create_assessment():
        created.append(assessment)
        return assessment

    def assess_batch(*_args, **kwargs):
        observed.append(("capabilities", kwargs["video_evidence_assessment"]))
        return {"talk.md": {}}

    def admit(*_args, **kwargs):
        observed.append(("admission", kwargs["video_evidence_assessment"]))

    def canonicalize(ret, *_args, **kwargs):
        observed.append(("canonicalization", kwargs["video_evidence_assessment"]))
        return dict(ret)

    def assess_freshness(_talk, **kwargs):
        observed.append(("freshness", kwargs["video_evidence_assessment"]))
        return ()

    def build_baseline(talks, *, evidence_freshness_assessor, **_kwargs):
        assert evidence_freshness_assessor(talks[0]) == ()
        return {}

    monkeypatch.setattr(persist_results, "VideoEvidenceAssessment", create_assessment)
    monkeypatch.setattr(
        persist_results,
        "materialize_native_authority",
        lambda *_args, **_kwargs: tmp_path / "tracking-database.json",
    )
    monkeypatch.setattr(
        persist_results,
        "load_tracking_database",
        lambda _path: (database, snapshot),
    )
    monkeypatch.setattr(
        persist_results,
        "resolve_vault_root_authority",
        lambda **_kwargs: tmp_path,
    )
    monkeypatch.setattr(persist_results, "load_json", lambda *_args: [returned])
    monkeypatch.setattr(
        persist_results,
        "validate_batch",
        lambda _returns: SimpleNamespace(fingerprint="f" * 64),
    )
    monkeypatch.setattr(
        persist_results,
        "assess_batch_artifact_capabilities",
        assess_batch,
    )
    monkeypatch.setattr(
        persist_results,
        "validate_batch_claims_against_talks",
        lambda *_args, **_kwargs: {"talk.md": talk},
    )
    monkeypatch.setattr(persist_results, "admit_return_artifacts", admit)
    monkeypatch.setattr(
        persist_results,
        "canonicalize_return_evidence",
        canonicalize,
    )
    monkeypatch.setattr(persist_results, "return_evidence_claim", lambda _value: {})
    monkeypatch.setattr(
        persist_results,
        "merge_talk",
        lambda *_args, **_kwargs: ([], True, False, []),
    )
    monkeypatch.setattr(
        persist_results,
        "assess_current_persisted_pattern_evidence_freshness",
        assess_freshness,
    )
    monkeypatch.setattr(
        persist_results,
        "build_current_cohort_baseline",
        build_baseline,
    )
    monkeypatch.setattr(
        persist_results,
        "atomic_write_json",
        lambda *_args, **_kwargs: SimpleNamespace(
            input_sha256="a" * 64,
            output_sha256="b" * 64,
            installed=True,
            durability_state="durable",
            warnings=(),
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "persist-results.py",
            str(tmp_path / "tracking-database.json"),
            str(tmp_path / "returns.json"),
            "--run-date",
            "2026-08-04T12:00:00+00:00",
        ],
    )

    persist_results.main()

    assert created == [assessment]
    assert observed == [
        ("capabilities", assessment),
        ("admission", assessment),
        ("canonicalization", assessment),
        ("freshness", assessment),
    ]


def test_second_return_video_failure_blocks_the_whole_batch_before_merge(
    persist_results,
    monkeypatch,
    tmp_path,
) -> None:
    assessment = object()
    talks = [
        {"filename": "first.md", "status": "processed"},
        {"filename": "second.md", "status": "processed"},
    ]
    database = {"config": {}, "talks": talks}
    returns = [
        {
            "filename": talk["filename"],
            "return_schema_version": 4,
            "status": "processed",
        }
        for talk in talks
    ]
    admitted: list[str] = []

    monkeypatch.setattr(
        persist_results,
        "VideoEvidenceAssessment",
        lambda: assessment,
    )
    monkeypatch.setattr(
        persist_results,
        "materialize_native_authority",
        lambda *_args, **_kwargs: tmp_path / "tracking-database.json",
    )
    monkeypatch.setattr(
        persist_results,
        "load_tracking_database",
        lambda _path: (database, object()),
    )
    monkeypatch.setattr(
        persist_results,
        "resolve_vault_root_authority",
        lambda **_kwargs: tmp_path,
    )
    monkeypatch.setattr(persist_results, "load_json", lambda *_args: returns)
    monkeypatch.setattr(
        persist_results,
        "validate_batch",
        lambda _returns: SimpleNamespace(fingerprint="f" * 64),
    )
    monkeypatch.setattr(
        persist_results,
        "assess_batch_artifact_capabilities",
        lambda *_args, **_kwargs: {talk["filename"]: {} for talk in talks},
    )
    monkeypatch.setattr(
        persist_results,
        "validate_batch_claims_against_talks",
        lambda *_args, **_kwargs: {talk["filename"]: talk for talk in talks},
    )

    def admit(_root, _talk, ret, **kwargs):
        assert kwargs["video_evidence_assessment"] is assessment
        admitted.append(ret["filename"])
        if ret["filename"] == "second.md":
            raise persist_results.PatternEvidenceError(
                "second source video failed bounded inspection"
            )

    monkeypatch.setattr(persist_results, "admit_return_artifacts", admit)
    monkeypatch.setattr(
        persist_results,
        "canonicalize_return_evidence",
        lambda ret, *_args, **_kwargs: dict(ret),
    )
    monkeypatch.setattr(persist_results, "return_evidence_claim", lambda _value: {})
    monkeypatch.setattr(
        persist_results,
        "merge_talk",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("batch merged before all source videos were admitted")
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "persist-results.py",
            str(tmp_path / "tracking-database.json"),
            str(tmp_path / "returns.json"),
            "--run-date",
            "2026-08-04T12:00:00+00:00",
        ],
    )

    try:
        persist_results.main()
    except SystemExit as exc:
        assert exc.code == 1
    else:  # pragma: no cover - main must reject the batch
        raise AssertionError("persist-results accepted a bad second source video")

    assert admitted == ["first.md", "second.md"]


def test_analysis_writer_reuses_one_assessment_for_capability_and_freshness(
    write_analysis,
    monkeypatch,
    tmp_path,
) -> None:
    assessment = object()
    created: list[object] = []
    observed: list[tuple[str, object]] = []
    returned = {
        "filename": "talk.md",
        "return_schema_version": 4,
        "status": "processed",
        "pattern_observations": {},
    }
    persisted_observations = {
        "evidence_schema_version": 2,
        "source_inspection": [],
        "patterns_detected": [],
        "antipatterns_detected": [],
        "not_evaluable": [],
    }
    talk = {
        "filename": "talk.md",
        "title": "Talk",
        "status": "processed",
        "processed_date": "2026-08-04T12:00:00+00:00",
        "pattern_observations": persisted_observations,
    }

    def create_assessment():
        created.append(assessment)
        return assessment

    def assess_batch(*_args, **kwargs):
        observed.append(("capabilities", kwargs["video_evidence_assessment"]))
        return {"talk.md": {}}

    def assess_freshness(_talk, **kwargs):
        observed.append(("freshness", kwargs["video_evidence_assessment"]))
        return ()

    monkeypatch.setattr(write_analysis, "VideoEvidenceAssessment", create_assessment)
    monkeypatch.setattr(
        write_analysis,
        "materialize_native_authority",
        lambda *_args, **_kwargs: tmp_path / "tracking-database.json",
    )
    monkeypatch.setattr(
        write_analysis,
        "load_tracking_database",
        lambda _path: {"config": {}, "talks": [talk]},
    )
    monkeypatch.setattr(
        write_analysis,
        "resolve_vault_root_authority",
        lambda **_kwargs: tmp_path,
    )
    monkeypatch.setattr(write_analysis, "load_json", lambda *_args: [returned])
    monkeypatch.setattr(
        write_analysis,
        "validate_batch",
        lambda _returns: SimpleNamespace(fingerprint="f" * 64),
    )
    monkeypatch.setattr(
        write_analysis,
        "assess_batch_artifact_capabilities",
        assess_batch,
    )
    monkeypatch.setattr(
        write_analysis,
        "validate_batch_claims_against_talks",
        lambda *_args, **_kwargs: {"talk.md": talk},
    )
    monkeypatch.setattr(write_analysis, "return_evidence_claim", lambda _value: {})
    monkeypatch.setattr(
        write_analysis,
        "validate_persisted_catalog_generation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        write_analysis,
        "assess_current_persisted_pattern_evidence_freshness",
        assess_freshness,
    )
    monkeypatch.setattr(
        write_analysis,
        "persisted_processed_stamp",
        lambda *_args, **_kwargs: "2026-08-04T12:00:00+00:00",
    )
    monkeypatch.setattr(
        write_analysis,
        "effective_render_payload",
        lambda ret, _talk: ret,
    )
    monkeypatch.setattr(
        write_analysis,
        "render_analysis",
        lambda *_args, **_kwargs: "analysis\n",
    )
    monkeypatch.setattr(
        write_analysis,
        "atomic_write_batch",
        lambda _rendered: None,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "write-analysis.py",
            str(tmp_path / "returns.json"),
            str(tmp_path / "analyses"),
            "--talks",
            str(tmp_path / "tracking-database.json"),
        ],
    )

    write_analysis.main()

    assert created == [assessment]
    assert observed == [
        ("capabilities", assessment),
        ("freshness", assessment),
    ]


def test_queue_operation_creates_one_assessment_after_root_authority(
    queue_state,
    monkeypatch,
    tmp_path,
) -> None:
    assessment = object()
    events: list[object] = []
    snapshot = object()

    monkeypatch.setattr(
        queue_state,
        "materialize_native_authority",
        lambda *_args, **_kwargs: Path(tmp_path / "tracking-database.json"),
    )
    monkeypatch.setattr(
        queue_state,
        "load_database_snapshot",
        lambda *_args, **_kwargs: ({"config": {}, "talks": []}, snapshot),
    )

    def resolve_root(**_kwargs):
        events.append("root")
        return tmp_path

    def create_assessment():
        events.append(assessment)
        return assessment

    def normalize(*_args, **kwargs):
        events.append(kwargs["video_evidence_assessment"])
        return {"ok": True}

    monkeypatch.setattr(queue_state, "resolve_vault_root_authority", resolve_root)
    monkeypatch.setattr(queue_state, "VideoEvidenceAssessment", create_assessment)
    monkeypatch.setattr(queue_state, "command_normalize", normalize)

    assert (
        queue_state.main([str(tmp_path / "tracking-database.json"), "normalize"]) == 0
    )
    assert events == ["root", assessment, assessment]


def test_queue_capability_and_freshness_closures_share_the_operation_assessment(
    queue_state,
    monkeypatch,
    tmp_path,
) -> None:
    assessment = object()
    observed: list[tuple[str, object]] = []
    database = {"config": {}, "talks": []}
    talk = {"filename": "talk.md"}

    monkeypatch.setattr(
        queue_state,
        "evidence_roots",
        lambda *_args: (tmp_path, {}),
    )

    def assess_capabilities(_talk, **kwargs):
        observed.append(("capabilities", kwargs["video_evidence_assessment"]))
        return {}

    def assess_freshness(_talk, **kwargs):
        observed.append(("freshness", kwargs["video_evidence_assessment"]))
        return ()

    monkeypatch.setattr(
        queue_state,
        "assess_talk_artifact_capabilities",
        assess_capabilities,
    )
    monkeypatch.setattr(
        queue_state,
        "assess_current_persisted_pattern_evidence_freshness",
        assess_freshness,
    )

    capability = queue_state.artifact_capability_assessor(
        database,
        tmp_path / "tracking-database.json",
        video_evidence_assessment=assessment,
    )
    freshness = queue_state.evidence_freshness_assessor(
        database,
        tmp_path / "tracking-database.json",
        video_evidence_assessment=assessment,
    )

    assert capability(talk) == {}
    assert capability(talk) == {}
    assert freshness(talk) == ()
    assert freshness(talk) == ()
    assert observed == [
        ("capabilities", assessment),
        ("capabilities", assessment),
        ("freshness", assessment),
    ]
