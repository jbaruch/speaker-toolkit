"""Exact-generation and worker-boundary tests for PDF evidence."""

from __future__ import annotations

import hashlib
import importlib
import logging
import os
import subprocess
import sys
import types
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "vault-ingress"
    / "scripts"
    / "pdf_evidence.py"
)
SCRIPT_DIR = SCRIPT.parent
if os.fspath(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, os.fspath(SCRIPT_DIR))
pdf_evidence = importlib.import_module("pdf_evidence")


def _synthetic_pdf(page_count: int = 1, *, marker: str = "a") -> bytes:
    """Build a deterministic, strict-readable PDF without a binary fixture."""
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            b"<< /Type /Pages /Kids ["
            + b" ".join(
                f"{index} 0 R".encode("ascii") for index in range(3, 3 + page_count)
            )
            + f"] /Count {page_count} >>".encode("ascii")
        ),
    ]
    objects.extend(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"
        for _ in range(page_count)
    )
    rendered = bytearray(f"%PDF-1.4\n%{marker}\n".encode("ascii"))
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(rendered))
        rendered.extend(f"{object_number} 0 obj\n".encode("ascii"))
        rendered.extend(body)
        rendered.extend(b"\nendobj\n")
    xref_offset = len(rendered)
    rendered.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    rendered.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        rendered.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    rendered.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(rendered)


def _generation(
    *,
    size: int = 100,
    inode: int = 31,
    flags: int | None = None,
    file_attributes: int | None = None,
) -> Any:
    return pdf_evidence.FileGeneration(
        size=size,
        mtime_ns=11,
        ctime_ns=12,
        device=13,
        inode=inode,
        mode=0o100600,
        flags=flags,
        file_attributes=file_attributes,
    )


def _receipt(generation: Any, root_generation: Any | None = None) -> Any:
    return pdf_evidence.ArtifactMetadataReceipt(
        generation=generation,
        root_generation=root_generation,
        reparse_tag=None,
    )


def _worker_result(
    generation: Any,
    *,
    page_count: int = 1,
    diagnostics: Any | None = None,
) -> Any:
    return pdf_evidence.WorkerResult(
        payload={
            "schema_version": pdf_evidence.PDF_PROBE_SCHEMA_VERSION,
            "status": "available",
            "page_count": page_count,
            "source_sha256": "a" * 64,
            "source_size_bytes": generation.size,
        },
        observed_generations={"pdf": generation},
        diagnostics=diagnostics or pdf_evidence.DiagnosticReceipt.empty(),
    )


@pytest.fixture(autouse=True)
def _clear_probe_cache() -> None:
    pdf_evidence.clear_pdf_artifact_probe_cache()


def test_limits_use_dedicated_profiles_and_documented_ceilings() -> None:
    assert pdf_evidence.PDF_METADATA_OPERATION == "pdf_metadata"
    assert pdf_evidence.PDF_PROBE_OPERATION == "pdf_probe"
    assert pdf_evidence.PDF_METADATA_LIMITS.profile_id == "pdf-metadata-v1"
    assert pdf_evidence.PDF_PROBE_LIMITS.profile_id == "pdf-probe-v1"
    assert pdf_evidence.PDF_MAX_INPUT_BYTES == 512 * 1024 * 1024
    assert pdf_evidence.PDF_MAX_PAGES == 65_536
    assert pdf_evidence.PDF_METADATA_LIMITS.max_processes == 1
    assert pdf_evidence.PDF_PROBE_LIMITS.max_processes == 1


def test_public_pdf_locators_fail_before_metadata_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign_locators = (
        ["/foreign/talk.pdf"]
        if os.name == "nt"
        else [r"C:\conference\talk.pdf", r"\\server\share\talk.pdf"]
    )
    cases = [
        ("talk.pdf", None, "artifact_locator_trusted_root_required"),
        ("~/talk.pdf", None, "artifact_locator_home_expansion_unsupported"),
        (
            r"conference\talk.pdf",
            tmp_path,
            "artifact_locator_noncanonical_relative",
        ),
        (
            tmp_path / "talk.pdf",
            "relative-root",
            "artifact_root_not_native_absolute",
        ),
        (
            r"\\server.\share\talk.pdf",
            None,
            "artifact_locator_windows_trimmed_component",
        ),
        *[
            (foreign, None, "artifact_locator_foreign_absolute")
            for foreign in foreign_locators
        ],
    ]
    monkeypatch.setattr(
        pdf_evidence,
        "_invoke_metadata_worker",
        lambda *_args, **_kwargs: pytest.fail("invalid locator started metadata"),
    )

    for locator, root, expected_failure in cases:
        with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
            pdf_evidence.probe_pdf_artifact(locator, trusted_root=root)
        assert caught.value.reason_code == "pdf_evidence_invalid"
        assert caught.value.details == {"locator_failure": expected_failure}
        assert os.fspath(locator) not in str(caught.value)
        assert os.fspath(locator) not in repr(caught.value.details)


def test_pdf_metadata_worker_revalidates_locator_before_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign = "/foreign/talk.pdf" if os.name == "nt" else r"C:\conference\talk.pdf"
    monkeypatch.setattr(
        pdf_evidence,
        "inspect_metadata_generation",
        lambda *_args, **_kwargs: pytest.fail("invalid locator reached metadata"),
    )

    with pytest.raises(pdf_evidence.SupervisorError) as caught:
        pdf_evidence._metadata_child({"pdf_path": foreign, "trusted_root": None})

    assert caught.value.reason_code == "invalid_worker_request"
    assert caught.value.details == {
        "locator_failure": "artifact_locator_foreign_absolute"
    }


def test_real_worker_probes_synthetic_pdf_and_reuses_exact_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "talk.pdf"
    source = _synthetic_pdf(2)
    artifact.write_bytes(source)

    first = pdf_evidence.probe_pdf_artifact("talk.pdf", trusted_root=tmp_path)

    assert first.page_count == 2
    assert first.source_sha256 == hashlib.sha256(source).hexdigest()
    assert first.source_size_bytes == len(source)
    assert first.generation == pdf_evidence.FileGeneration.from_stat(artifact.stat())
    assert first.root_generation == (
        pdf_evidence.FileGeneration.from_directory_identity(tmp_path.stat())
    )
    assert first.availability.state == "local"
    assert first.parser_diagnostics == pdf_evidence.DiagnosticReceipt.empty()

    def unexpected_probe(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("exact-generation cache should bypass the parser worker")

    monkeypatch.setattr(pdf_evidence, "_invoke_probe_worker", unexpected_probe)
    second = pdf_evidence.probe_pdf_artifact(artifact, trusted_root=tmp_path)
    assert second == first
    assert second is not first


def test_same_size_replacement_invalidates_cached_probe(tmp_path: Path) -> None:
    """A same-size replacement is probed again, never served from the cache.

    The promise is the content binding, so that is what is asserted (#277). An
    earlier version also required the replacement's inode to differ from the
    original's — an allocation outcome this test does not control, and a claim
    about the filesystem rather than about the probe. A cache that did serve
    the stale entry still fails the digest assertion below, which is the defect
    worth catching either way.
    """
    artifact = tmp_path / "talk.pdf"
    original = _synthetic_pdf(marker="a")
    replacement_bytes = _synthetic_pdf(marker="b")
    assert len(replacement_bytes) == len(original)
    assert replacement_bytes != original
    artifact.write_bytes(original)
    first = pdf_evidence.probe_pdf_artifact(artifact, trusted_root=tmp_path)
    assert first.source_sha256 == hashlib.sha256(original).hexdigest()

    replacement = tmp_path / "replacement.pdf"
    replacement.write_bytes(replacement_bytes)
    os.replace(replacement, artifact)
    second = pdf_evidence.probe_pdf_artifact(artifact, trusted_root=tmp_path)

    assert second.source_sha256 == hashlib.sha256(replacement_bytes).hexdigest()
    assert second.source_size_bytes == first.source_size_bytes


@pytest.mark.parametrize(
    ("source", "reason_code"),
    [
        (b"this is not a PDF", "pdf_invalid_container"),
        (b"%PDF-not-a-real-document\n", "pdf_parser_rejected"),
    ],
)
def test_real_worker_maps_synthetic_invalid_artifacts_stably(
    tmp_path: Path,
    source: bytes,
    reason_code: str,
) -> None:
    artifact = tmp_path / "broken.pdf"
    artifact.write_bytes(source)

    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence.probe_pdf_artifact(artifact, trusted_root=tmp_path)

    assert caught.value.reason_code == reason_code
    assert str(artifact) not in str(caught.value)
    assert str(artifact) not in repr(caught.value.details)


@pytest.mark.parametrize(
    ("generation", "expected_flag"),
    [
        (
            _generation(flags=pdf_evidence.PDF_MACOS_DATALESS_FLAG or 0x40000000),
            "macos_dataless",
        ),
        (
            _generation(file_attributes=0x400000),
            "windows_recall_on_data_access",
        ),
    ],
)
def test_platform_offline_facts_reject_before_probe_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    generation: Any,
    expected_flag: str,
) -> None:
    if expected_flag == "macos_dataless" and not pdf_evidence.PDF_MACOS_DATALESS_FLAG:
        monkeypatch.setattr(pdf_evidence, "PDF_MACOS_DATALESS_FLAG", 0x40000000)
    receipt = _receipt(generation)
    monkeypatch.setattr(
        pdf_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: receipt,
    )

    def forbidden_open(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("offline artifacts must not reach the probe worker")

    monkeypatch.setattr(pdf_evidence, "_invoke_probe_worker", forbidden_open)
    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence.probe_pdf_artifact(tmp_path / "offline.pdf")

    assert caught.value.reason_code == "pdf_cloud_placeholder_unavailable"
    availability = caught.value.details["availability"]
    assert isinstance(availability, dict)
    assert availability["state"] == "unavailable"
    assert availability[expected_flag] is True


def test_success_with_any_parser_diagnostic_is_a_cached_repair_fact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    receipt = _receipt(generation)
    diagnostic_bytes = b"parser repaired an object"
    diagnostics = pdf_evidence.DiagnosticReceipt(
        byte_count=len(diagnostic_bytes),
        sha256=hashlib.sha256(diagnostic_bytes).hexdigest(),
        truncated=False,
    )
    monkeypatch.setattr(
        pdf_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: receipt,
    )
    calls = 0

    def diagnostic_success(*_args: object, **_kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        return _worker_result(generation, diagnostics=diagnostics)

    monkeypatch.setattr(pdf_evidence, "_invoke_probe_worker", diagnostic_success)
    for _ in range(2):
        with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
            pdf_evidence.probe_pdf_artifact(tmp_path / "repair.pdf")
        assert caught.value.reason_code == "pdf_parser_repair_required"
        assert caught.value.details == {"diagnostic_receipt": diagnostics.to_dict()}
        assert not hasattr(diagnostics, "text")
    assert calls == 2


def test_protocol_failure_is_stable_but_never_cached_as_artifact_fact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt(_generation())
    monkeypatch.setattr(
        pdf_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: receipt,
    )
    calls = 0

    def malformed_protocol(*_args: object, **_kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        raise pdf_evidence.SupervisorError("invalid_worker_response")

    monkeypatch.setattr(pdf_evidence, "_invoke_probe_worker", malformed_protocol)
    for _ in range(2):
        with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
            pdf_evidence.probe_pdf_artifact(tmp_path / "protocol.pdf")
        assert caught.value.reason_code == "pdf_probe_malformed_result"
    assert calls == 2


def test_parser_failure_requires_identical_second_bounded_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    receipt = _receipt(generation)
    monkeypatch.setattr(
        pdf_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: receipt,
    )
    outcomes = [
        pdf_evidence.WorkerResult(
            payload={
                "schema_version": 1,
                "status": "unavailable",
                "reason_code": "pdf_parser_rejected",
                "details": {"exception_type": "PdfReadError"},
            },
            observed_generations={"pdf": generation},
        ),
        _worker_result(generation),
    ]

    def changing_result(*_args: object, **_kwargs: object) -> Any:
        return outcomes.pop(0)

    monkeypatch.setattr(pdf_evidence, "_invoke_probe_worker", changing_result)
    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence.probe_pdf_artifact(tmp_path / "changing.pdf")

    assert caught.value.reason_code == "pdf_probe_materialization_changed"
    assert not pdf_evidence._PDF_ARTIFACT_PROBE_CACHE


def test_post_probe_metadata_failure_preserves_infrastructure_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    receipt = _receipt(generation)
    metadata_calls = 0

    def metadata(*_args: object, **_kwargs: object) -> Any:
        nonlocal metadata_calls
        metadata_calls += 1
        if metadata_calls == 1:
            return receipt
        raise pdf_evidence.PdfEvidenceError(
            "metadata worker crashed",
            reason_code="pdf_probe_crash",
        )

    monkeypatch.setattr(pdf_evidence, "_run_bounded_metadata_worker", metadata)
    monkeypatch.setattr(
        pdf_evidence,
        "_invoke_probe_worker",
        lambda *_args, **_kwargs: _worker_result(generation),
    )

    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence.probe_pdf_artifact(tmp_path / "talk.pdf")

    assert caught.value.reason_code == "pdf_probe_crash"
    assert not pdf_evidence._PDF_ARTIFACT_PROBE_CACHE


def test_confirmation_probe_infrastructure_failure_preserves_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    receipt = _receipt(generation)
    monkeypatch.setattr(
        pdf_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: receipt,
    )
    first = pdf_evidence.WorkerResult(
        payload={
            "schema_version": 1,
            "status": "unavailable",
            "reason_code": "pdf_parser_rejected",
            "details": {"exception_type": "PdfReadError"},
        },
        observed_generations={"pdf": generation},
    )
    calls = 0

    def probe(*_args: object, **_kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            return first
        raise pdf_evidence.SupervisorError("worker_exit")

    monkeypatch.setattr(pdf_evidence, "_invoke_probe_worker", probe)

    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence.probe_pdf_artifact(tmp_path / "talk.pdf")

    assert caught.value.reason_code == "pdf_probe_crash"
    assert calls == 2
    assert not pdf_evidence._PDF_ARTIFACT_PROBE_CACHE


def test_metadata_diagnostics_are_structured_and_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    raw = b"unexpected metadata diagnostic"
    diagnostics = pdf_evidence.DiagnosticReceipt(
        byte_count=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        truncated=False,
    )
    result = pdf_evidence.WorkerResult(
        payload={
            "schema_version": pdf_evidence.METADATA_SCHEMA_VERSION,
            "status": "available",
            "generation": generation.to_dict(),
            "root_generation": None,
            "reparse_tag": None,
        },
        observed_generations={},
        diagnostics=diagnostics,
    )
    monkeypatch.setattr(
        pdf_evidence,
        "_invoke_metadata_worker",
        lambda *_args, **_kwargs: result,
    )

    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._run_bounded_metadata_worker(
            tmp_path / "talk.pdf",
            trusted_root=None,
            deadline_monotonic=None,
        )

    assert caught.value.reason_code == "pdf_probe_malformed_result"
    assert caught.value.details == {"diagnostic_receipt": diagnostics.to_dict()}


def test_truncated_diagnostic_receipt_fails_as_bounded_resource_fault() -> None:
    generation = _generation()
    diagnostics = pdf_evidence.DiagnosticReceipt(
        byte_count=65_537,
        sha256="f" * 64,
        truncated=True,
    )
    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._decode_probe_payload(
            _worker_result(generation).payload,
            receipt=_receipt(generation),
            diagnostics=diagnostics,
        )
    assert caught.value.reason_code == "pdf_probe_resource_unavailable"
    assert caught.value.details == {"diagnostic_receipt": diagnostics.to_dict()}


@pytest.mark.parametrize(
    "diagnostics",
    [
        pdf_evidence.DiagnosticReceipt(
            byte_count=65_537,
            sha256="f" * 64,
            truncated=False,
        ),
        pdf_evidence.DiagnosticReceipt(
            byte_count=1,
            sha256="f" * 64,
            truncated=True,
        ),
    ],
)
def test_diagnostic_receipt_must_bind_truncation_to_profile_ceiling(
    diagnostics: Any,
) -> None:
    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._diagnostic_receipt_shape(
            diagnostics,
            max_diagnostic_bytes=65_536,
        )
    assert caught.value.reason_code == "pdf_probe_malformed_result"


@pytest.mark.parametrize(
    ("reason_code", "details"),
    [
        ("pdf_invalid_container", {"exception_type": "PdfReadError"}),
        ("pdf_parser_rejected", {"limit_bytes": 512 * 1024 * 1024}),
        ("pdf_page_limit", {}),
        ("pdf_probe_resource_unavailable", {"max_pages": 65_536}),
        (
            "pdf_probe_resource_unavailable",
            {"exception_type": "OSError", "limit_bytes": 512 * 1024 * 1024},
        ),
        ("pdf_parser_rejected", {"exception_type": "/private/source.pdf"}),
    ],
)
def test_unavailable_payload_details_are_closed_per_reason(
    reason_code: str,
    details: dict[str, object],
) -> None:
    generation = _generation()
    payload = {
        "schema_version": 1,
        "status": "unavailable",
        "reason_code": reason_code,
        "details": details,
    }
    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._decode_probe_payload(
            payload,
            receipt=_receipt(generation),
            diagnostics=pdf_evidence.DiagnosticReceipt.empty(),
        )
    assert caught.value.reason_code == "pdf_probe_malformed_result"


def test_metadata_admission_failure_purges_every_same_path_cache_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "talk.pdf"
    receipt = _receipt(_generation())
    key = pdf_evidence._cache_key(artifact, None, receipt)
    pdf_evidence._PDF_ARTIFACT_PROBE_CACHE[key] = pdf_evidence.PdfArtifactProbe(
        generation=receipt.generation,
        root_generation=None,
        availability=pdf_evidence._availability(receipt.generation),
        page_count=1,
        source_sha256="a" * 64,
        source_size_bytes=receipt.generation.size,
        parser_diagnostics=pdf_evidence.DiagnosticReceipt.empty(),
    )

    def unavailable(*_args: object, **_kwargs: object) -> Any:
        raise pdf_evidence.PdfEvidenceError(
            "unavailable",
            reason_code="pdf_artifact_unavailable",
        )

    monkeypatch.setattr(
        pdf_evidence,
        "_run_bounded_metadata_worker",
        unavailable,
    )
    with pytest.raises(pdf_evidence.PdfEvidenceError):
        pdf_evidence.probe_pdf_artifact(artifact)
    assert not pdf_evidence._PDF_ARTIFACT_PROBE_CACHE


def test_oversized_artifact_is_a_distinct_cached_artifact_fact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt(_generation(size=pdf_evidence.PDF_MAX_INPUT_BYTES + 1))
    monkeypatch.setattr(
        pdf_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: receipt,
    )

    def forbidden_probe(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("oversized artifacts must not reach the probe worker")

    monkeypatch.setattr(pdf_evidence, "_invoke_probe_worker", forbidden_probe)
    for _ in range(2):
        with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
            pdf_evidence.probe_pdf_artifact(tmp_path / "huge.pdf")
        assert caught.value.reason_code == "pdf_artifact_too_large"
        assert caught.value.details == {"limit_bytes": pdf_evidence.PDF_MAX_INPUT_BYTES}


def test_probe_uses_only_fixed_child_command_and_bound_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    receipt = _receipt(generation)
    monkeypatch.setattr(
        pdf_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: receipt,
    )
    artifact = tmp_path / "private name.pdf"

    def inspect_invocation(
        command: list[str],
        expected_generations: dict[str, Any],
        payload: dict[str, object],
        sensitive_values: tuple[Path, ...],
        limits: Any,
    ) -> Any:
        assert command == [
            sys.executable,
            os.fspath(SCRIPT.absolute()),
            "--supervised-worker",
        ]
        assert all(os.fspath(artifact) not in part for part in command)
        assert expected_generations == {"pdf": generation}
        assert payload == {
            "pdf_path": os.fspath(artifact),
            "trusted_root": None,
            "max_input_bytes": 512 * 1024 * 1024,
            "max_pages": 65_536,
        }
        assert sensitive_values == (artifact,)
        assert limits.profile_id == "pdf-probe-v1"
        return _worker_result(generation)

    monkeypatch.setattr(pdf_evidence, "_invoke_probe_worker", inspect_invocation)
    assert pdf_evidence.probe_pdf_artifact(artifact).page_count == 1


_SUPERVISOR_PUBLIC_MESSAGES = {
    "pdf_artifact_changed": "PDF artifact changed during bounded inspection",
    "pdf_dependency_unavailable": (
        "PDF evidence requires its declared runtime dependencies; install the "
        "speaker-toolkit project dependencies"
    ),
    "pdf_probe_containment_unavailable": (
        "Bounded PDF evidence worker could not establish or preserve "
        "process-tree containment"
    ),
    "pdf_probe_crash": "Bounded PDF evidence worker terminated unexpectedly",
    "pdf_probe_malformed_result": (
        "Bounded PDF evidence worker returned an invalid authenticated result"
    ),
    "pdf_probe_monitor_identity_changed": (
        "Bounded PDF evidence worker process identity changed during inspection"
    ),
    "pdf_probe_monitor_unavailable": (
        "Bounded PDF evidence worker could not inspect its process tree"
    ),
    "pdf_probe_request_oversized": (
        "Bounded PDF evidence worker request exceeded its input contract"
    ),
    "pdf_probe_resource_unavailable": (
        "PDF evidence exceeded a configured worker resource limit"
    ),
    "pdf_probe_result_oversized": (
        "Bounded PDF evidence worker result exceeded its output contract"
    ),
    "pdf_probe_start_failure": "Could not start the bounded PDF evidence worker",
    "pdf_probe_timeout": "Bounded PDF evidence operation exceeded its wall limit",
}

_SUPERVISOR_FAILURE_CASES = [
    ("worker_generation_changed", {}, "pdf_artifact_changed"),
    ("worker_generation_binding_mismatch", {}, "pdf_probe_malformed_result"),
    ("worker_timeout", {}, "pdf_probe_timeout"),
    ("worker_memory_limit_exceeded", {}, "pdf_probe_resource_unavailable"),
    ("worker_process_limit_exceeded", {}, "pdf_probe_resource_unavailable"),
    ("worker_diagnostic_limit_exceeded", {}, "pdf_probe_resource_unavailable"),
    (
        "worker_monitor_unavailable",
        {
            "dependency": "psutil",
            "required_version": "7.2.2",
            "actual_version": "7.2.1",
        },
        "pdf_dependency_unavailable",
    ),
    ("worker_monitor_unavailable", {}, "pdf_probe_monitor_unavailable"),
    (
        "worker_monitor_unavailable",
        {"dependency": "pypdf"},
        "pdf_probe_monitor_unavailable",
    ),
    (
        "worker_monitor_identity_changed",
        {},
        "pdf_probe_monitor_identity_changed",
    ),
    (
        "worker_containment_unavailable",
        {},
        "pdf_probe_containment_unavailable",
    ),
    ("worker_process_tree_leak", {}, "pdf_probe_containment_unavailable"),
    ("worker_cleanup_failed", {}, "pdf_probe_containment_unavailable"),
    ("worker_input_limit_exceeded", {}, "pdf_probe_request_oversized"),
    ("worker_output_limit_exceeded", {}, "pdf_probe_result_oversized"),
    ("worker_start_failed", {}, "pdf_probe_start_failure"),
    ("worker_pipe_setup_failed", {}, "pdf_probe_start_failure"),
    ("worker_exit_before_barrier", {}, "pdf_probe_start_failure"),
    ("worker_request_write_failed", {}, "pdf_probe_start_failure"),
    ("invalid_worker_command", {}, "pdf_probe_start_failure"),
    ("unsafe_worker_process_metadata", {}, "pdf_probe_start_failure"),
    ("worker_exit", {}, "pdf_probe_crash"),
    ("worker_diagnostic_read_failed", {}, "pdf_probe_crash"),
    ("worker_output_read_failed", {}, "pdf_probe_crash"),
    ("invalid_worker_response", {}, "pdf_probe_malformed_result"),
    ("worker_response_authentication_failed", {}, "pdf_probe_malformed_result"),
    ("worker_response_binding_mismatch", {}, "pdf_probe_malformed_result"),
    ("invalid_worker_response_bindings", {}, "pdf_probe_malformed_result"),
    ("worker_response_bindings_mismatch", {}, "pdf_probe_malformed_result"),
    ("worker_response_body_mismatch", {}, "pdf_probe_malformed_result"),
    ("invalid_worker_response_body", {}, "pdf_probe_malformed_result"),
    ("invalid_worker_request", {}, "pdf_probe_malformed_result"),
    ("invalid_worker_operation", {}, "pdf_probe_malformed_result"),
    ("worker_operation_failed", {}, "pdf_probe_malformed_result"),
    ("protocol_isolation_failed", {}, "pdf_probe_malformed_result"),
    ("future_supervisor_fault", {}, "pdf_probe_malformed_result"),
]


@pytest.mark.parametrize(
    ("supervisor_reason", "supervisor_details", "public_reason"),
    _SUPERVISOR_FAILURE_CASES,
)
def test_supervisor_failures_have_cause_correct_path_free_public_mapping(
    supervisor_reason: str,
    supervisor_details: dict[str, object],
    public_reason: str,
) -> None:
    leaked_values = (
        "/private/vault/source.pdf",
        "parser exploded while reading a secret document",
        "credential-value-should-never-escape",
    )
    mapped = pdf_evidence._supervisor_failure(
        pdf_evidence.SupervisorError(
            supervisor_reason,
            {
                **supervisor_details,
                "path": leaked_values[0],
                "parser_output": leaked_values[1],
                "credential": leaked_values[2],
            },
        ),
        timeout_seconds=3.5,
    )

    assert mapped.reason_code == public_reason
    assert str(mapped) == _SUPERVISOR_PUBLIC_MESSAGES[public_reason]
    if public_reason == "pdf_artifact_changed":
        assert mapped.details == {}
    elif public_reason == "pdf_probe_timeout":
        assert mapped.details == {"timeout_seconds": 3.5}
    else:
        assert mapped.details == {"supervisor_reason_code": supervisor_reason}
    rendered = str(mapped) + repr(mapped.details)
    assert all(value not in rendered for value in leaked_values)


def test_generation_failure_preserves_only_closed_path_free_names() -> None:
    mapped = pdf_evidence._supervisor_failure(
        pdf_evidence.SupervisorError(
            "worker_generation_changed",
            {"generation_names": ["pdf_root"]},
        ),
        timeout_seconds=3.5,
    )
    assert mapped.reason_code == "pdf_artifact_changed"
    assert mapped.details == {"generation_names": ["pdf_root"]}

    malformed = pdf_evidence._supervisor_failure(
        pdf_evidence.SupervisorError(
            "worker_generation_changed",
            {"generation_names": ["/private/source.pdf"]},
        ),
        timeout_seconds=3.5,
    )
    assert malformed.details == {}


def test_supervisor_failure_preserves_only_bounded_diagnostic_receipt() -> None:
    raw = b"parser stderr at /private/source.pdf"
    diagnostics = pdf_evidence.DiagnosticReceipt(
        byte_count=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        truncated=False,
    )
    mapped = pdf_evidence._supervisor_failure(
        pdf_evidence.SupervisorError(
            "worker_exit",
            diagnostics=diagnostics,
        ),
        timeout_seconds=3.5,
    )
    assert mapped.reason_code == "pdf_probe_crash"
    assert mapped.details == {
        "supervisor_reason_code": "worker_exit",
        "diagnostic_receipt": diagnostics.to_dict(),
    }
    assert "/private/source.pdf" not in repr(mapped.details)


def test_cache_key_closes_generation_root_availability_profiles_and_policy(
    tmp_path: Path,
) -> None:
    generation = _generation(
        flags=17,
        file_attributes=0x001000,
    )
    root_generation = replace(_generation(inode=50), mode=0o040700)
    receipt = pdf_evidence.ArtifactMetadataReceipt(
        generation=generation,
        root_generation=root_generation,
        reparse_tag=0x9000001A,
    )
    key = pdf_evidence._cache_key(tmp_path / "talk.pdf", tmp_path, receipt)

    assert key.generation == generation
    assert key.root_generation == root_generation
    assert key.reparse_tag == 0x9000001A
    assert key.availability_state == "unavailable"
    assert key.windows_offline is True
    assert key.metadata_profile_id == pdf_evidence.PDF_METADATA_LIMITS.profile_id
    assert key.probe_profile_id == pdf_evidence.PDF_PROBE_LIMITS.profile_id
    assert key.schema_generation == pdf_evidence.PDF_PROBE_SCHEMA_VERSION
    assert key.pipeline_generation == pdf_evidence.PDF_PROBE_PIPELINE_VERSION
    assert key.max_input_bytes == pdf_evidence.PDF_MAX_INPUT_BYTES
    assert key.max_pages == pdf_evidence.PDF_MAX_PAGES
    assert key != pdf_evidence._cache_key(
        tmp_path / "talk.pdf",
        tmp_path,
        replace(receipt, generation=replace(generation, inode=32)),
    )


def test_copy_hashes_one_source_stream_and_rejects_wrong_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _synthetic_pdf(2)
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(source)
    snapshot = tmp_path / "snapshot.pdf"
    generation = pdf_evidence.FileGeneration.from_stat(artifact.stat())
    real_open = pdf_evidence.os.open
    source_opens = 0

    def counted_open(path: Any, *args: Any, **kwargs: Any) -> int:
        nonlocal source_opens
        if Path(path) == artifact:
            source_opens += 1
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(pdf_evidence.os, "open", counted_open)
    digest, size, header = pdf_evidence._copy_and_hash_source(
        artifact,
        snapshot,
        expected_generation=generation,
        max_input_bytes=pdf_evidence.PDF_MAX_INPUT_BYTES,
    )
    assert source_opens == 1
    assert snapshot.read_bytes() == source
    assert digest == hashlib.sha256(source).hexdigest()
    assert size == len(source)
    assert header == b"%PDF-"

    with pytest.raises(pdf_evidence.SupervisorError) as caught:
        pdf_evidence._copy_and_hash_source(
            artifact,
            tmp_path / "rejected.pdf",
            expected_generation=replace(generation, inode=generation.inode + 1),
            max_input_bytes=pdf_evidence.PDF_MAX_INPUT_BYTES,
        )
    assert caught.value.reason_code == "worker_generation_changed"
    assert caught.value.details == {"generation_names": ["pdf"]}


def test_pypdf_logger_is_routed_to_stderr_and_complete_tree_is_forced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    visited: list[int] = []

    class FakePages:
        def __len__(self) -> int:
            return 2

        def __getitem__(self, index: int) -> object:
            visited.append(index)
            return object()

    class FakeReader:
        def __init__(self, _stream: object, *, strict: bool) -> None:
            assert strict is True
            logging.getLogger("pypdf").warning("synthetic repair")
            self.pages = FakePages()

    pypdf_module = types.ModuleType("pypdf")
    setattr(pypdf_module, "PdfReader", FakeReader)
    errors_module = types.ModuleType("pypdf.errors")
    setattr(errors_module, "PdfReadError", ValueError)
    monkeypatch.setitem(sys.modules, "pypdf", pypdf_module)
    monkeypatch.setitem(sys.modules, "pypdf.errors", errors_module)
    snapshot = tmp_path / "snapshot.pdf"
    snapshot.write_bytes(_synthetic_pdf(2))

    assert pdf_evidence._strict_pdf_page_count(snapshot, max_pages=65_536) == 2
    assert visited == [0, 1]
    assert "synthetic repair" in capsys.readouterr().err


def test_private_snapshot_io_failure_is_not_classified_as_parser_damage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = tmp_path / "snapshot.pdf"
    snapshot.write_bytes(_synthetic_pdf())

    def unavailable_open(*_args: object, **_kwargs: object) -> Any:
        raise OSError("synthetic private snapshot outage")

    monkeypatch.setattr(Path, "open", unavailable_open)
    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._strict_pdf_page_count(snapshot, max_pages=65_536)

    assert caught.value.reason_code == "pdf_probe_resource_unavailable"
    assert caught.value.details == {"exception_type": "OSError"}


def test_contained_pdf_inspection_rejects_repair_diagnostics_without_leaking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakePages:
        def __len__(self) -> int:
            return 1

        def __getitem__(self, _index: int) -> object:
            return object()

    class FakeReader:
        def __init__(self, _stream: object, *, strict: bool) -> None:
            assert strict is True
            logging.getLogger("pypdf").warning("synthetic contained repair")
            self.pages = FakePages()

    pypdf_module = types.ModuleType("pypdf")
    setattr(pypdf_module, "PdfReader", FakeReader)
    errors_module = types.ModuleType("pypdf.errors")
    setattr(errors_module, "PdfReadError", ValueError)
    monkeypatch.setitem(sys.modules, "pypdf", pypdf_module)
    monkeypatch.setitem(sys.modules, "pypdf.errors", errors_module)
    artifact = tmp_path / "rendered.pdf"
    artifact.write_bytes(_synthetic_pdf())

    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._inspect_pdf_in_contained_worker(
            artifact,
            expected_generation=pdf_evidence.FileGeneration.from_stat(artifact.stat()),
        )

    assert caught.value.reason_code == "pdf_parser_repair_required"
    receipt = caught.value.details["diagnostic_receipt"]
    assert isinstance(receipt, dict)
    assert receipt["byte_count"] > 0
    assert receipt["truncated"] is False
    assert "synthetic contained repair" not in capsys.readouterr().err


def test_contained_pdf_inspection_captures_descriptor_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact = tmp_path / "rendered.pdf"
    artifact.write_bytes(_synthetic_pdf())
    generation = pdf_evidence.FileGeneration.from_stat(artifact.stat())

    def descriptor_diagnostic(*_args: object, **_kwargs: object) -> dict[str, object]:
        os.write(2, b"FD_DIAGNOSTIC_BYPASS\n")
        return {
            "schema_version": pdf_evidence.PDF_PROBE_SCHEMA_VERSION,
            "status": "available",
            "page_count": 1,
            "source_sha256": "a" * 64,
            "source_size_bytes": generation.size,
        }

    monkeypatch.setattr(
        pdf_evidence,
        "_probe_pdf_snapshot_in_process",
        descriptor_diagnostic,
    )

    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._inspect_pdf_in_contained_worker(
            artifact,
            expected_generation=generation,
        )

    assert caught.value.reason_code == "pdf_parser_repair_required"
    assert caught.value.details["diagnostic_receipt"]["byte_count"] == len(
        b"FD_DIAGNOSTIC_BYPASS\n"
    )
    assert "FD_DIAGNOSTIC_BYPASS" not in capsys.readouterr().err


def test_contained_pdf_inspection_maps_memory_error_to_pdf_resource_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "rendered.pdf"
    artifact.write_bytes(_synthetic_pdf())

    def memory_failure(*_args: object, **_kwargs: object) -> Any:
        raise MemoryError

    monkeypatch.setattr(
        pdf_evidence,
        "_probe_pdf_snapshot_in_process",
        memory_failure,
    )

    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._inspect_pdf_in_contained_worker(
            artifact,
            expected_generation=pdf_evidence.FileGeneration.from_stat(artifact.stat()),
        )

    assert caught.value.reason_code == "pdf_probe_resource_unavailable"


@pytest.mark.parametrize(
    ("error", "exception_type"),
    [(OSError("synthetic pipe failure"), "OSError"), (MemoryError(), "MemoryError")],
)
def test_contained_pdf_capture_setup_failure_preserves_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    exception_type: str,
) -> None:
    artifact = tmp_path / "rendered.pdf"
    artifact.write_bytes(_synthetic_pdf())

    def pipe_failure() -> tuple[int, int]:
        raise error

    monkeypatch.setattr(pdf_evidence.os, "pipe", pipe_failure)
    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._inspect_pdf_in_contained_worker(
            artifact,
            expected_generation=pdf_evidence.FileGeneration.from_stat(artifact.stat()),
        )

    assert caught.value.reason_code == "pdf_probe_resource_unavailable"
    assert caught.value.details == {"exception_type": exception_type}


def test_contained_pdf_capture_drainer_start_failure_preserves_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "rendered.pdf"
    artifact.write_bytes(_synthetic_pdf())

    def start_failure(_drainer: object) -> None:
        raise RuntimeError("synthetic thread start failure")

    monkeypatch.setattr(pdf_evidence._PipeDrainer, "start", start_failure)
    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._inspect_pdf_in_contained_worker(
            artifact,
            expected_generation=pdf_evidence.FileGeneration.from_stat(artifact.stat()),
        )

    assert caught.value.reason_code == "pdf_probe_resource_unavailable"
    assert caught.value.details == {"exception_type": "RuntimeError"}


def test_contained_malformed_payload_preserves_descriptor_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact = tmp_path / "rendered.pdf"
    artifact.write_bytes(_synthetic_pdf())

    def malformed_payload(*_args: object, **_kwargs: object) -> dict[str, object]:
        os.write(2, b"MALFORMED_PAYLOAD_DIAGNOSTIC\n")
        return {"schema_version": pdf_evidence.PDF_PROBE_SCHEMA_VERSION}

    monkeypatch.setattr(
        pdf_evidence,
        "_probe_pdf_snapshot_in_process",
        malformed_payload,
    )
    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._inspect_pdf_in_contained_worker(
            artifact,
            expected_generation=pdf_evidence.FileGeneration.from_stat(artifact.stat()),
        )

    assert caught.value.reason_code == "pdf_probe_malformed_result"
    assert caught.value.details["diagnostic_receipt"]["byte_count"] == len(
        b"MALFORMED_PAYLOAD_DIAGNOSTIC\n"
    )
    assert "MALFORMED_PAYLOAD_DIAGNOSTIC" not in capsys.readouterr().err


@pytest.mark.parametrize("use_storage_path", [False, True])
def test_probe_accepts_documented_symlink_trusted_root(
    tmp_path: Path,
    use_storage_path: bool,
) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    artifact = storage / "artifact.pdf"
    artifact.write_bytes(_synthetic_pdf())
    locator = tmp_path / "canonical-vault"
    try:
        locator.symlink_to(storage, target_is_directory=True)
    except OSError:
        pytest.skip("directory policy does not permit symlink creation")
    requested = artifact if use_storage_path else locator / artifact.name

    probe = pdf_evidence.probe_pdf_artifact(requested, trusted_root=locator)

    assert probe.page_count == 1


def test_probe_decoder_rejects_partial_wrong_size_and_page_overflow() -> None:
    generation = _generation()
    diagnostics = pdf_evidence.DiagnosticReceipt.empty()
    invalid_payloads = [
        {"schema_version": 1, "status": "available"},
        {
            "schema_version": 1,
            "status": "available",
            "page_count": 1,
            "source_sha256": "a" * 64,
            "source_size_bytes": generation.size - 1,
        },
        {
            "schema_version": 1,
            "status": "available",
            "page_count": 65_537,
            "source_sha256": "a" * 64,
            "source_size_bytes": generation.size,
        },
    ]
    for payload in invalid_payloads:
        with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
            pdf_evidence._decode_probe_payload(
                payload,
                receipt=_receipt(generation),
                diagnostics=diagnostics,
            )
        assert caught.value.reason_code == "pdf_probe_malformed_result"


def test_child_dispatch_rejects_wrong_profile_and_policy(tmp_path: Path) -> None:
    generation = _generation()
    base = pdf_evidence.WorkerRequest(
        request_id="a" * 64,
        operation="pdf_probe",
        request_sha256="b" * 64,
        limit_profile_id=pdf_evidence.PDF_PROBE_LIMITS.profile_id,
        schema_generation=pdf_evidence.PDF_PROBE_SCHEMA_VERSION,
        pipeline_generation=pdf_evidence.PDF_PROBE_PIPELINE_VERSION,
        expected_generations={"pdf": generation},
        payload={
            "pdf_path": os.fspath(tmp_path / "artifact.pdf"),
            "trusted_root": None,
            "max_input_bytes": pdf_evidence.PDF_MAX_INPUT_BYTES,
            "max_pages": pdf_evidence.PDF_MAX_PAGES + 1,
        },
        key=b"k" * 32,
    )
    with pytest.raises(pdf_evidence.SupervisorError) as caught:
        pdf_evidence._dispatch_supervised_worker(base)
    assert caught.value.reason_code == "invalid_worker_request"

    wrong_profile = replace(base, limit_profile_id="some-other-profile")
    with pytest.raises(pdf_evidence.SupervisorError) as caught:
        pdf_evidence._dispatch_supervised_worker(wrong_profile)
    assert caught.value.reason_code == "invalid_worker_request"


def test_child_dispatch_attributes_root_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    root_identity = replace(
        _generation(inode=50),
        size=0,
        mtime_ns=0,
        ctime_ns=0,
        mode=0o040700,
    )
    monkeypatch.setattr(
        pdf_evidence,
        "_metadata_receipt_in_probe_worker",
        lambda *_args, **_kwargs: _receipt(generation, root_identity),
    )
    request = pdf_evidence.WorkerRequest(
        request_id="a" * 64,
        operation=pdf_evidence.PDF_PROBE_OPERATION,
        request_sha256="b" * 64,
        limit_profile_id=pdf_evidence.PDF_PROBE_LIMITS.profile_id,
        schema_generation=pdf_evidence.PDF_PROBE_SCHEMA_VERSION,
        pipeline_generation=pdf_evidence.PDF_PROBE_PIPELINE_VERSION,
        expected_generations={
            "pdf": generation,
            "pdf_root": replace(root_identity, inode=root_identity.inode + 1),
        },
        payload={
            "pdf_path": os.fspath(tmp_path / "artifact.pdf"),
            "trusted_root": os.fspath(tmp_path),
            "max_input_bytes": pdf_evidence.PDF_MAX_INPUT_BYTES,
            "max_pages": pdf_evidence.PDF_MAX_PAGES,
        },
        key=b"k" * 32,
    )

    with pytest.raises(pdf_evidence.SupervisorError) as caught:
        pdf_evidence._dispatch_supervised_worker(request)

    assert caught.value.reason_code == "worker_generation_changed"
    assert caught.value.details == {"generation_names": ["pdf_root"]}


@pytest.mark.parametrize(
    ("error", "expected_diagnostic"),
    [
        (
            pdf_evidence.SupervisorError("protocol_isolation_failed"),
            "pdf supervised worker failed: protocol_isolation_failed\n",
        ),
        (
            RuntimeError("failure at /private/vault/source.pdf"),
            "pdf supervised worker failed: unexpected_error\n",
        ),
    ],
)
def test_worker_main_reports_closed_outer_failures(
    error: Exception,
    expected_diagnostic: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail() -> int:
        raise error

    monkeypatch.setattr(
        pdf_evidence.sys,
        "argv",
        [os.fspath(SCRIPT), pdf_evidence.PDF_SUPERVISED_WORKER_FLAG],
    )
    monkeypatch.setattr(pdf_evidence, "_run_supervised_worker_child", fail)

    assert pdf_evidence._main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == expected_diagnostic
    assert "/private/vault/source.pdf" not in captured.err


def test_deadline_is_validated_and_clamps_worker_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pdf_evidence.time, "monotonic", lambda: 100.0)
    limited = pdf_evidence._limits_before_deadline(
        pdf_evidence.PDF_PROBE_LIMITS,
        112.0,
    )
    assert limited.wall_seconds == 10.0
    assert limited.profile_id == pdf_evidence.PDF_PROBE_LIMITS.profile_id

    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._limits_before_deadline(pdf_evidence.PDF_PROBE_LIMITS, 102.0)
    assert caught.value.reason_code == "pdf_batch_wall_limit"
    with pytest.raises(pdf_evidence.PdfEvidenceError) as caught:
        pdf_evidence._limits_before_deadline(pdf_evidence.PDF_PROBE_LIMITS, True)
    assert caught.value.reason_code == "pdf_evidence_invalid"


def _venv_root_link(root: Path) -> Path:
    """Link the running venv to a path under `root`, on either platform.

    The condition under test is that the interpreter's own path contains the
    trusted root — the live vault's `<vault>/.venv/bin/python3`. Reproducing it
    needs a link, not a copy: a copied interpreter loses the venv and fails on
    its own dependencies, which would test the fixture instead of the
    supervisor.

    POSIX gets a symlink. Windows gets a directory junction, which needs no
    privilege where `os.symlink` does. The link is deliberately UNRESOLVED —
    resolving follows through to the base installation and drops the venv's
    site-packages.
    """
    link = root / ".venv"
    if link.exists():
        return link
    source = Path(sys.executable).parent.parent
    if os.name == "nt":
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", os.fspath(link), os.fspath(source)],
            capture_output=True,
            check=False,
        )
        assert created.returncode == 0, created.stderr.decode("utf-8", errors="replace")
    else:
        link.symlink_to(source)
    return link


def _interpreter_under(root: Path) -> Path:
    """The linked venv's interpreter, named as this platform names it."""
    executable = Path(sys.executable)
    return _venv_root_link(root) / executable.parent.name / executable.name


def test_a_pdf_probe_runs_under_an_interpreter_inside_the_trusted_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same defect as the video probe, same shape, both PDF worker paths.

    With `config.python_path` inside the vault — the layout `check-runtime`
    recommends and the live vault uses — `sys.executable` contains the trusted
    root. Without an `immutable_process_identity` declaration the supervisor
    reads the worker's own interpreter as leaked metadata and refuses to start
    it, so every PDF admission failed `pdf_probe_start_failure`.

    Exercised through `probe_pdf_artifact`, which drives the metadata worker and
    the probe worker in turn, so both changed call sites are covered by the
    outcome rather than by their wiring.
    """
    source = _synthetic_pdf(3)
    (tmp_path / "talk.pdf").write_bytes(source)
    interpreter = _interpreter_under(tmp_path)
    monkeypatch.setattr(sys, "executable", os.fspath(interpreter))

    probe = pdf_evidence.probe_pdf_artifact("talk.pdf", trusted_root=tmp_path)

    assert probe.page_count == 3
    assert probe.source_sha256 == hashlib.sha256(source).hexdigest()
    assert probe.availability.state == "local"
