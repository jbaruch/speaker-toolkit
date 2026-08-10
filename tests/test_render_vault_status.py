"""Owner-generated vault status block in rhetoric-style-summary.md (#168).

The summary's status line was hand-maintained and drifted: a verified snapshot
claimed `199 / 208` with 195 processed while the tracking database held 209
talks, 116 of them `needs-reprocessing`. Queue normalization moves statuses
without touching prose, so the stale cohort reads as live.

Every count here comes from one strict snapshot. These tests pin that, plus the
hash-preconditioned apply that keeps the renderer from overwriting a human edit
it never read.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

GENERATED_AT = "2026-08-10T12:00:00Z"


def _claim(state: str = "claimed") -> dict:
    """A queue claim the owner contract accepts.

    Schema 2 keeps the fixture to the fields this test is about; the adherence
    baseline that schema 3+ requires says nothing about counting.
    """
    claim = {
        "schema_version": 2,
        "run_id": "status-render-test",
        "batch_id": "batch-1",
        "claimed_at": "2026-07-31T12:00:00+00:00",
        "previous_status": "needs-reprocessing",
        # Positive, and equal to the talk's own reprocess_generation: the owner
        # contract refuses a claim that disagrees with the record it is on.
        "reprocess_generation": 1,
        "state": state,
    }
    if state != "claimed":
        # A terminal claim is a finished writer, never an active one.
        claim.update(
            {
                "released_at": "2026-07-31T13:00:00+00:00",
                "release_reason": "status_render_test",
                "result_status": "processed",
            }
        )
    return claim


ANALYSED = {"pattern_observations": {"patterns_detected": [{"pattern_id": "hook"}]}}


def _talk(filename: str, status: str, **extra) -> dict:
    talk = {"schema_version": 5, "filename": filename, "status": status}
    if "_queue_claim" in extra:
        talk["reprocess_generation"] = extra["_queue_claim"]["reprocess_generation"]
    talk.update(extra)
    return talk


def _database(talks: list[dict], **config_extra) -> dict:
    config = {"schema_version": 2, "pptx_directory_exclusions": []}
    config.update(config_extra)
    return {
        "schema_version": 1,
        "config": config,
        "talks": talks,
        "pptx_catalog": [],
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }


def _vault(tmp_path: Path, database: dict, summary: str = "# Rhetoric\n\nNarrative.\n"):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "tracking-database.json").write_text(json.dumps(database), encoding="utf-8")
    (root / "rhetoric-style-summary.md").write_text(summary, encoding="utf-8")
    return root


def _block_payload(report: dict) -> dict:
    body = report["block"].split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    return json.loads(body)


def test_the_verified_209_talk_mismatch_is_derived_not_transcribed(
    render_vault_status, tmp_path: Path
) -> None:
    """The live snapshot from the issue: prose said 199/208, the database said this."""
    talks = (
        # 100 of the requeued talks were analysed before normalization moved
        # them back; 16 never were.
        [_talk(f"reproc-{i}.md", "needs-reprocessing", **ANALYSED) for i in range(100)]
        + [_talk(f"fresh-{i}.md", "needs-reprocessing") for i in range(16)]
        + [_talk(f"pending-{i}.md", "pending") for i in range(9)]
        + [_talk(f"done-{i}.md", "processed", **ANALYSED) for i in range(78)]
        + [_talk(f"partial-{i}.md", "processed_partial", **ANALYSED) for i in range(2)]
        + [
            _talk(f"inflight-{i}.md", "reprocessing-inflight", _queue_claim=_claim())
            for i in range(3)
        ]
        + [_talk("dupe.md", "skipped_duplicate")]
    )
    root = _vault(tmp_path, _database(talks))

    report = render_vault_status.execute(root, generated_at=GENERATED_AT)

    status = report["status"]
    assert status["total_talks"] == 209
    assert status["status_counts"] == {
        "needs-reprocessing": 116,
        "pending": 9,
        "processed": 78,
        "processed_partial": 2,
        "reprocessing-inflight": 3,
        "skipped_duplicate": 1,
    }
    # The two counts must differ: 100 requeued talks keep their analysis
    # evidence, so they are historically analysed while out of the current
    # cohort. Reading history off `status` would erase all 100.
    assert status["current_cohort_count"] == 80
    assert status["historically_analysed_count"] == 180
    assert status["active_claim_count"] == 3


def test_in_flight_talks_are_counted_as_active(
    render_vault_status, tmp_path: Path
) -> None:
    talks = [
        _talk("inflight-a.md", "reprocessing-inflight", _queue_claim=_claim()),
        _talk("inflight-b.md", "reprocessing-inflight", _queue_claim=_claim()),
        _talk("idle.md", "processed"),
    ]
    root = _vault(tmp_path, _database(talks))

    report = render_vault_status.execute(root, generated_at=GENERATED_AT)

    assert report["status"]["active_claim_count"] == 2


@pytest.mark.parametrize(
    ("talk", "expected"),
    [
        ({"status": "reprocessing-inflight"}, 1),
        ({"status": "processed", "_queue_claim": {"state": "claimed"}}, 1),
        ({"status": "processed", "_queue_claim": {"state": "completed"}}, 0),
        ({"status": "processed", "_queue_claim": {"state": "stale_recovered"}}, 0),
        ({"status": "processed", "_queue_claim": "not an object"}, 0),
        ({"status": "processed"}, 0),
        ("not a talk", 0),
    ],
)
def test_active_claim_counting_reads_both_signals(
    render_vault_status, talk, expected
) -> None:
    """The counting rule itself, apart from the queue contract's own validity.

    A recovered or completed claim is a finished writer; only an in-flight
    status or a still-`claimed` record means someone holds the talk now.
    """
    assert render_vault_status._active_claims([talk]) == expected


def test_the_block_binds_the_exact_database_generation(
    render_vault_status, tmp_path: Path
) -> None:
    database = _database(
        [_talk("one.md", "processed")],
        pattern_scoring_schema_version=5,
        pattern_catalog_fingerprint="a" * 64,
    )
    root = _vault(tmp_path, database)
    raw = (root / "tracking-database.json").read_bytes()

    report = render_vault_status.execute(root, generated_at=GENERATED_AT)

    status = report["status"]
    assert status["database_sha256"] == hashlib.sha256(raw).hexdigest()
    assert status["database_schema_version"] == 1
    assert status["scoring_generation"] == {
        "pattern_scoring_schema_version": 5,
        "pattern_catalog_fingerprint": "a" * 64,
    }


def test_an_absent_generation_is_reported_absent_not_defaulted(
    render_vault_status, tmp_path: Path
) -> None:
    """A default would let a database with no recorded generation claim one."""
    root = _vault(tmp_path, _database([_talk("one.md", "processed")]))

    report = render_vault_status.execute(root, generated_at=GENERATED_AT)

    assert report["status"]["scoring_generation"] == {
        "pattern_scoring_schema_version": None,
        "pattern_catalog_fingerprint": None,
    }


def test_a_dry_run_writes_nothing(render_vault_status, tmp_path: Path) -> None:
    root = _vault(tmp_path, _database([_talk("one.md", "processed")]))
    summary = root / "rhetoric-style-summary.md"
    before = summary.read_bytes()

    report = render_vault_status.execute(root, generated_at=GENERATED_AT)

    assert report["mode"] == "dry-run"
    assert report["changed"] is True
    assert report["summary_written"] is False
    assert summary.read_bytes() == before


def test_apply_installs_the_block_and_preserves_the_narrative(
    render_vault_status, tmp_path: Path
) -> None:
    root = _vault(
        tmp_path,
        _database([_talk("one.md", "processed")]),
        summary="# Rhetoric\n\nSection 1 narrative.\n",
    )
    summary = root / "rhetoric-style-summary.md"
    dry = render_vault_status.execute(root, generated_at=GENERATED_AT)

    applied = render_vault_status.execute(
        root,
        generated_at=GENERATED_AT,
        apply_requested=True,
        expected_sha256=dry["summary_sha256"],
    )

    text = summary.read_text(encoding="utf-8")
    assert applied["summary_written"] is True
    assert "Section 1 narrative." in text
    assert render_vault_status.BLOCK_BEGIN in text
    assert render_vault_status.BLOCK_END in text


def test_a_second_apply_is_a_byte_stable_no_op(
    render_vault_status, tmp_path: Path
) -> None:
    """Rewriting identical bytes would churn the file for consumers watching it."""
    root = _vault(tmp_path, _database([_talk("one.md", "processed")]))
    summary = root / "rhetoric-style-summary.md"
    first = render_vault_status.execute(root, generated_at=GENERATED_AT)
    render_vault_status.execute(
        root,
        generated_at=GENERATED_AT,
        apply_requested=True,
        expected_sha256=first["summary_sha256"],
    )
    installed = summary.read_bytes()

    second = render_vault_status.execute(
        root,
        generated_at=GENERATED_AT,
        apply_requested=True,
        expected_sha256=hashlib.sha256(installed).hexdigest(),
    )

    assert second["changed"] is False
    assert second["summary_written"] is False
    assert summary.read_bytes() == installed


def test_apply_refuses_a_stale_precondition(
    render_vault_status, tmp_path: Path
) -> None:
    """The summary is a file a human also edits."""
    root = _vault(tmp_path, _database([_talk("one.md", "processed")]))
    summary = root / "rhetoric-style-summary.md"
    dry = render_vault_status.execute(root, generated_at=GENERATED_AT)
    summary.write_text("# Rhetoric\n\nEdited by a human meanwhile.\n", encoding="utf-8")
    before = summary.read_bytes()

    with pytest.raises(render_vault_status.SummaryRenderError) as caught:
        render_vault_status.execute(
            root,
            generated_at=GENERATED_AT,
            apply_requested=True,
            expected_sha256=dry["summary_sha256"],
        )

    assert caught.value.reason_code == "summary_precondition_failed"
    assert summary.read_bytes() == before


def test_apply_without_a_precondition_is_refused(
    render_vault_status, tmp_path: Path
) -> None:
    root = _vault(tmp_path, _database([_talk("one.md", "processed")]))

    with pytest.raises(render_vault_status.SummaryRenderError) as caught:
        render_vault_status.execute(
            root, generated_at=GENERATED_AT, apply_requested=True
        )

    assert caught.value.reason_code == "summary_precondition_missing"


def test_only_the_delimited_block_is_replaced(
    render_vault_status, tmp_path: Path
) -> None:
    root = _vault(tmp_path, _database([_talk("one.md", "processed")]))
    summary = root / "rhetoric-style-summary.md"
    summary.write_text(
        "# Rhetoric\n\nBefore.\n\n"
        f"{render_vault_status.BLOCK_BEGIN}\nstale garbage\n"
        f"{render_vault_status.BLOCK_END}\n\nAfter.\n",
        encoding="utf-8",
    )
    dry = render_vault_status.execute(root, generated_at=GENERATED_AT)

    render_vault_status.execute(
        root,
        generated_at=GENERATED_AT,
        apply_requested=True,
        expected_sha256=dry["summary_sha256"],
    )

    text = summary.read_text(encoding="utf-8")
    assert "Before." in text and "After." in text
    assert "stale garbage" not in text
    assert text.count(render_vault_status.BLOCK_BEGIN) == 1


def test_a_malformed_delimiter_pair_installs_nothing(
    render_vault_status, tmp_path: Path
) -> None:
    root = _vault(tmp_path, _database([_talk("one.md", "processed")]))
    summary = root / "rhetoric-style-summary.md"
    summary.write_text(
        f"# Rhetoric\n\n{render_vault_status.BLOCK_END}\nout of order\n"
        f"{render_vault_status.BLOCK_BEGIN}\n",
        encoding="utf-8",
    )
    before = summary.read_bytes()

    with pytest.raises(render_vault_status.SummaryRenderError) as caught:
        render_vault_status.execute(root, generated_at=GENERATED_AT)

    assert caught.value.reason_code == "summary_block_malformed"
    assert summary.read_bytes() == before


def test_a_legacy_database_generation_still_renders(
    render_vault_status, tmp_path: Path
) -> None:
    """Legacy owner state is readable, so its cohort must be reportable too."""
    root = _vault(tmp_path, {"config": {}, "talks": [_talk("one.md", "processed")]})

    report = render_vault_status.execute(root, generated_at=GENERATED_AT)

    assert report["status"]["database_schema_version"] == 0
    assert report["status"]["total_talks"] == 1


def test_an_unusable_database_renders_nothing(
    render_vault_status, tmp_path: Path, capsys
) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "tracking-database.json").write_text(json.dumps({"schema_version": 99}))
    (root / "rhetoric-style-summary.md").write_text("# Rhetoric\n")

    exit_code = render_vault_status.main([str(root), "--generated-at", GENERATED_AT])

    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    # Path-neutral: the vault path must not ride out on the failure.
    assert str(root) not in captured.out + captured.err


def test_the_block_payload_is_machine_readable(
    render_vault_status, tmp_path: Path
) -> None:
    """A consumer diagnosing staleness reads the block, not the prose."""
    root = _vault(tmp_path, _database([_talk("one.md", "processed")]))

    report = render_vault_status.execute(root, generated_at=GENERATED_AT)

    payload = _block_payload(report)
    assert payload["schema_version"] == render_vault_status.STATUS_BLOCK_SCHEMA_VERSION
    assert payload["generated_at"] == GENERATED_AT
    assert payload["database_sha256"] == report["status"]["database_sha256"]


def test_a_requeued_talk_stays_historically_analysed(
    render_vault_status, tmp_path: Path
) -> None:
    """The distinction the block exists for, in isolation.

    Normalization flips `status` and leaves the analysis evidence in place.
    Deriving history from `status` would report the work as never done.
    """
    talks = [
        _talk("requeued.md", "needs-reprocessing", **ANALYSED),
        _talk("current.md", "processed", **ANALYSED),
        _talk("never.md", "needs-reprocessing"),
    ]
    root = _vault(tmp_path, _database(talks))

    status = render_vault_status.execute(root, generated_at=GENERATED_AT)["status"]

    assert status["current_cohort_count"] == 1
    assert status["historically_analysed_count"] == 2


def test_duplicate_delimiters_are_malformed(
    render_vault_status, tmp_path: Path
) -> None:
    """A second pair would make the splice target a range never inspected."""
    root = _vault(tmp_path, _database([_talk("one.md", "processed")]))
    summary = root / "rhetoric-style-summary.md"
    block = f"{render_vault_status.BLOCK_BEGIN}\nx\n{render_vault_status.BLOCK_END}"
    summary.write_text(f"# Rhetoric\n\n{block}\n\n{block}\n", encoding="utf-8")
    before = summary.read_bytes()

    with pytest.raises(render_vault_status.SummaryRenderError) as caught:
        render_vault_status.execute(root, generated_at=GENERATED_AT)

    assert caught.value.reason_code == "summary_block_malformed"
    assert summary.read_bytes() == before


def test_an_edit_during_the_stage_window_abandons_the_swap(
    render_vault_status, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compare-and-swap must bind the install, not just the earlier read."""
    root = _vault(tmp_path, _database([_talk("one.md", "processed")]))
    summary = root / "rhetoric-style-summary.md"
    dry = render_vault_status.execute(root, generated_at=GENERATED_AT)

    real_open_stage = render_vault_status.open_retained_stage

    def edit_then_stage(*args, **kwargs):
        # A human saves the file after the digest was read and while the
        # replacement is being staged.
        summary.write_text("# Rhetoric\n\nSaved mid-flight.\n", encoding="utf-8")
        return real_open_stage(*args, **kwargs)

    monkeypatch.setattr(render_vault_status, "open_retained_stage", edit_then_stage)

    with pytest.raises(render_vault_status.SummaryRenderError) as caught:
        render_vault_status.execute(
            root,
            generated_at=GENERATED_AT,
            apply_requested=True,
            expected_sha256=dry["summary_sha256"],
        )

    assert caught.value.reason_code == "summary_precondition_failed"
    assert summary.read_text(encoding="utf-8") == "# Rhetoric\n\nSaved mid-flight.\n"
