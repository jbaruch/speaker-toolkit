"""Focused regressions for PPTX recovery and exact audit receipts."""

from __future__ import annotations

import ast
import json
import struct
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from pptx import Presentation
from pptx.util import Inches
from pypdf import PdfWriter


def _write_deck(path: Path, *, with_image: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    if with_image:
        image_path = path.with_suffix(".png")
        Image.new("RGB", (64, 64), "navy").save(image_path)
        slide.shapes.add_picture(str(image_path), Inches(1), Inches(1))
    deck.save(path)


def _damage_member(path: Path, predicate) -> str:
    with zipfile.ZipFile(path) as archive:
        member = next(
            item for item in archive.infolist() if predicate(item.filename)
        )
    package = bytearray(path.read_bytes())
    name_size, extra_size = struct.unpack_from(
        "<HH", package, member.header_offset + 26
    )
    payload_offset = member.header_offset + 30 + name_size + extra_size
    package[payload_offset + max(member.compress_size // 2, 0)] ^= 0xFF
    path.write_bytes(package)
    return member.filename


def _damage_member_crc(path: Path, predicate) -> str:
    """Alter only the central-directory CRC so reading raises BadZipFile."""
    with zipfile.ZipFile(path) as archive:
        member = next(
            item for item in archive.infolist() if predicate(item.filename)
        )
    package = bytearray(path.read_bytes())
    cursor = 0
    while True:
        header = package.find(b"PK\x01\x02", cursor)
        if header < 0:
            raise AssertionError(f"central directory entry not found: {member.filename}")
        name_size, extra_size, comment_size = struct.unpack_from(
            "<HHH", package, header + 28
        )
        name_start = header + 46
        name_end = name_start + name_size
        if package[name_start:name_end].decode("utf-8") == member.filename:
            recorded_crc = struct.unpack_from("<I", package, header + 16)[0]
            struct.pack_into("<I", package, header + 16, recorded_crc ^ 0xFFFFFFFF)
            path.write_bytes(package)
            return member.filename
        cursor = name_end + extra_size + comment_size


def _write_pdf(path: Path, *, page_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for _index in range(page_count):
        writer.add_blank_page(width=640, height=480)
    with path.open("wb") as stream:
        writer.write(stream)


def test_live_badzipfile_media_path_recovers_with_structured_loss(
    pptx_evidence,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "damaged-media.pptx"
    _write_deck(deck, with_image=True)
    damaged_part = _damage_member_crc(
        deck, lambda name: name.startswith("ppt/media/")
    )

    with pytest.raises(zipfile.BadZipFile):
        Presentation(deck)

    probe = pptx_evidence.probe_pptx_artifact(deck)

    assert probe.slide_count == 1
    assert len(probe.source_sha256) == 64
    assert probe.archive_recovery == (
        {
            "schema_version": 1,
            "part_name": damaged_part,
            "member_kind": "embedded_media",
            "error_type": "crc_mismatch",
            "status": "recovered_with_placeholder_asset",
            "content_replaced": True,
            "replacement_sha256": (
                "431ced6916a2a21a156e38701afe55bbd7f88969fbbfc56d7fe099d47f265460"
            ),
        },
    )


def test_bounded_probe_timeout_is_structured_and_cached(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "slow.pptx"
    _write_deck(deck, with_image=False)
    pptx_evidence.clear_pptx_artifact_probe_cache()
    calls = 0

    def timeout_runner(command, **kwargs):
        nonlocal calls
        calls += 1
        raise subprocess.TimeoutExpired(
            command,
            pptx_evidence.PPTX_ARTIFACT_PROBE_TIMEOUT_SECONDS,
        )

    monkeypatch.setattr(pptx_evidence.subprocess, "run", timeout_runner)
    for _index in range(2):
        with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
            pptx_evidence.probe_pptx_artifact(deck)
        assert caught.value.reason_code == "pptx_probe_timeout"
    assert calls == 1


def test_bounded_probe_resource_failure_is_structured(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "memory-heavy.pptx"
    _write_deck(deck, with_image=False)
    pptx_evidence.clear_pptx_artifact_probe_cache()

    def resource_runner(command, **_kwargs):
        Path(command[-1]).write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "unavailable",
                    "reason_code": "pptx_probe_resource_unavailable",
                    "details": {},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(pptx_evidence.subprocess, "run", resource_runner)
    with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
        pptx_evidence.probe_pptx_artifact(deck)
    assert caught.value.reason_code == "pptx_probe_resource_unavailable"


def test_successful_probe_is_cached_by_exact_file_generation(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "cached.pptx"
    _write_deck(deck, with_image=False)
    pptx_evidence.clear_pptx_artifact_probe_cache()
    calls = 0

    def successful_runner(command, **_kwargs):
        nonlocal calls
        calls += 1
        Path(command[-1]).write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "available",
                    "slide_count": 1,
                    "source_sha256": "a" * 64,
                    "source_size_bytes": deck.stat().st_size,
                    "archive_recovery": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(pptx_evidence.subprocess, "run", successful_runner)
    assert pptx_evidence.probe_pptx_artifact(deck).slide_count == 1
    assert pptx_evidence.probe_pptx_artifact(deck).source_sha256 == "a" * 64
    assert calls == 1


def test_single_recovery_read_is_transient_and_not_cached(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "materializing.pptx"
    _write_deck(deck, with_image=False)
    pptx_evidence.clear_pptx_artifact_probe_cache()
    calls = 0
    recovery = [{
        "schema_version": 1,
        "part_name": "ppt/media/image1.png",
        "member_kind": "embedded_media",
        "error_type": "crc_mismatch",
        "status": "recovered_with_placeholder_asset",
        "content_replaced": True,
        "replacement_sha256": (
            "431ced6916a2a21a156e38701afe55bbd7f88969fbbfc56d7fe099d47f265460"
        ),
    }]

    def materializing_runner(command, **_kwargs):
        nonlocal calls
        calls += 1
        Path(command[-1]).write_text(
            json.dumps({
                "schema_version": 1,
                "status": "available",
                "slide_count": 1,
                "source_sha256": "a" * 64,
                "source_size_bytes": deck.stat().st_size,
                "archive_recovery": recovery if calls == 1 else [],
            })
            + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(pptx_evidence.subprocess, "run", materializing_runner)
    with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
        pptx_evidence.probe_pptx_artifact(deck)
    assert caught.value.reason_code == "pptx_probe_materialization_changed"
    assert calls == 2

    assert pptx_evidence.probe_pptx_artifact(deck).archive_recovery == ()
    assert calls == 3


def test_single_structural_crc_failure_is_not_cached_when_confirmation_is_clean(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "materializing-structure.pptx"
    _write_deck(deck, with_image=False)
    pptx_evidence.clear_pptx_artifact_probe_cache()
    calls = 0

    def materializing_runner(command, **_kwargs):
        nonlocal calls
        calls += 1
        payload = (
            {
                "schema_version": 1,
                "status": "unavailable",
                "reason_code": "pptx_structural_damage",
                "details": {"part_names": ["ppt/slides/slide1.xml"]},
            }
            if calls == 1
            else {
                "schema_version": 1,
                "status": "available",
                "slide_count": 1,
                "source_sha256": "a" * 64,
                "source_size_bytes": deck.stat().st_size,
                "archive_recovery": [],
            }
        )
        Path(command[-1]).write_text(
            json.dumps(payload) + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(pptx_evidence.subprocess, "run", materializing_runner)
    with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
        pptx_evidence.probe_pptx_artifact(deck)
    assert caught.value.reason_code == "pptx_probe_materialization_changed"
    assert calls == 2

    assert pptx_evidence.probe_pptx_artifact(deck).slide_count == 1
    assert calls == 3


def test_single_child_io_failure_is_not_cached_when_confirmation_is_clean(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "hydrating.pptx"
    _write_deck(deck, with_image=False)
    pptx_evidence.clear_pptx_artifact_probe_cache()
    calls = 0

    def hydrating_runner(command, **_kwargs):
        nonlocal calls
        calls += 1
        payload = (
            {
                "schema_version": 1,
                "status": "unavailable",
                "reason_code": "pptx_artifact_unavailable",
                "details": {"exception_type": "OSError"},
            }
            if calls == 1
            else {
                "schema_version": 1,
                "status": "available",
                "slide_count": 1,
                "source_sha256": "a" * 64,
                "source_size_bytes": deck.stat().st_size,
                "archive_recovery": [],
            }
        )
        Path(command[-1]).write_text(
            json.dumps(payload) + "\n", encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(pptx_evidence.subprocess, "run", hydrating_runner)
    with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
        pptx_evidence.probe_pptx_artifact(deck)
    assert caught.value.reason_code == "pptx_probe_materialization_changed"
    assert calls == 2

    assert pptx_evidence.probe_pptx_artifact(deck).slide_count == 1
    assert calls == 3


def test_snapshot_open_io_failure_has_portable_unavailable_code(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "open-failure.pptx"
    _write_deck(deck, with_image=False)
    original_open = Path.open

    def failing_open(path: Path, *args, **kwargs):
        if path == deck:
            raise OSError("synthetic hydration failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
        pptx_evidence._probe_pptx_artifact_in_process(deck)
    assert caught.value.reason_code == "pptx_artifact_unavailable"
    assert caught.value.details == {"exception_type": "OSError"}


def test_snapshot_generation_change_has_nonsticky_changed_code(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "generation-change.pptx"
    _write_deck(deck, with_image=False)
    actual = deck.lstat()
    original_lstat = Path.lstat
    calls = 0

    def changing_lstat(path: Path):
        nonlocal calls
        if path != deck:
            return original_lstat(path)
        calls += 1
        if calls == 1:
            return actual
        return SimpleNamespace(
            st_mode=actual.st_mode,
            st_dev=actual.st_dev,
            st_ino=actual.st_ino,
            st_size=actual.st_size,
            st_mtime_ns=actual.st_mtime_ns + 1,
            st_ctime_ns=actual.st_ctime_ns,
            st_flags=getattr(actual, "st_flags", 0),
        )

    monkeypatch.setattr(Path, "lstat", changing_lstat)
    with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
        pptx_evidence.snapshot_regular_file(deck, label="PPTX artifact")
    assert caught.value.reason_code == "pptx_artifact_changed"


def test_rendered_pdf_same_size_generation_replacement_fails_closed(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rendered = tmp_path / "rendered.pdf"
    _write_pdf(rendered, page_count=1)
    actual = rendered.lstat()
    original_lstat = Path.lstat
    calls = 0

    def replaced_lstat(path: Path):
        nonlocal calls
        if path != rendered:
            return original_lstat(path)
        calls += 1
        if calls == 1:
            return actual
        return SimpleNamespace(
            st_mode=actual.st_mode,
            st_dev=actual.st_dev,
            st_ino=actual.st_ino,
            st_size=actual.st_size,
            st_mtime_ns=actual.st_mtime_ns + 1,
            st_ctime_ns=actual.st_ctime_ns,
            st_flags=getattr(actual, "st_flags", 0),
        )

    monkeypatch.setattr(Path, "lstat", replaced_lstat)
    with pytest.raises(pptx_evidence.PptxEvidenceError, match="changed"):
        pptx_evidence.snapshot_rendered_pdf(rendered)


def test_native_audit_recomputation_timeout_is_structured(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "slow-audit.pptx"
    _write_deck(deck, with_image=False)
    pptx_evidence.clear_pptx_artifact_probe_cache()

    def timeout_runner(command, **_kwargs):
        raise subprocess.TimeoutExpired(
            command,
            pptx_evidence.PPTX_ARTIFACT_PROBE_TIMEOUT_SECONDS,
        )

    monkeypatch.setattr(pptx_evidence.subprocess, "run", timeout_runner)
    with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
        pptx_evidence.recompute_native_deck_audit(deck)
    assert caught.value.reason_code == "pptx_probe_timeout"


def test_native_audit_recovery_is_not_sticky_when_confirmation_is_clean(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "materializing-audit.pptx"
    _write_deck(deck, with_image=False)
    pptx_evidence.clear_pptx_artifact_probe_cache()
    audit = pptx_evidence.build_native_deck_audit(
        source_pptx_sha256="a" * 64,
        source_pptx_size_bytes=deck.stat().st_size,
        slide_count=1,
        render_required_reasons={},
    )
    calls = 0

    def materializing_runner(command, **_kwargs):
        nonlocal calls
        calls += 1
        payload = (
            {
                "schema_version": 1,
                "status": "unavailable",
                "reason_code": "pptx_archive_recovery_required",
                "details": {"part_names": ["ppt/media/image1.png"]},
            }
            if calls == 1
            else {
                "schema_version": 1,
                "status": "available",
                "native_deck_audit": audit,
            }
        )
        Path(command[-1]).write_text(
            json.dumps(payload) + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(pptx_evidence.subprocess, "run", materializing_runner)
    with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
        pptx_evidence.recompute_native_deck_audit(deck)
    assert caught.value.reason_code == "pptx_probe_materialization_changed"
    assert calls == 2
    assert pptx_evidence.recompute_native_deck_audit(deck) == audit
    assert calls == 3


def test_dataless_cloud_placeholder_never_starts_worker_io(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "cloud-placeholder.pptx"
    _write_deck(deck, with_image=False)
    actual = deck.lstat()
    dataless_flag = pptx_evidence.PPTX_MACOS_DATALESS_FLAG or 0x40000000
    original_lstat = Path.lstat

    def dataless_lstat(path: Path):
        if path == deck:
            return SimpleNamespace(
                st_mode=actual.st_mode,
                st_dev=actual.st_dev,
                st_ino=actual.st_ino,
                st_size=actual.st_size,
                st_mtime_ns=actual.st_mtime_ns,
                st_ctime_ns=actual.st_ctime_ns,
                st_flags=dataless_flag,
            )
        return original_lstat(path)

    if pptx_evidence.PPTX_MACOS_DATALESS_FLAG == 0:
        monkeypatch.setattr(
            pptx_evidence,
            "PPTX_MACOS_DATALESS_FLAG",
            dataless_flag,
        )
    monkeypatch.setattr(Path, "lstat", dataless_lstat)
    monkeypatch.setattr(
        pptx_evidence.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("dataless deck started worker I/O"),
    )
    pptx_evidence.clear_pptx_artifact_probe_cache()

    with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
        pptx_evidence.probe_pptx_artifact(deck)
    assert caught.value.reason_code == "pptx_cloud_placeholder_unavailable"


def test_dataless_flag_uses_explicit_darwin_fallback(pptx_evidence) -> None:
    expected = int(
        getattr(
            pptx_evidence.stat_module,
            "SF_DATALESS",
            0x40000000 if sys.platform == "darwin" else 0,
        )
    )
    assert pptx_evidence.PPTX_MACOS_DATALESS_FLAG == expected
    if sys.platform == "darwin":
        assert expected == 0x40000000


def test_structural_crc_damage_is_unavailable_not_placeholder_recovered(
    pptx_evidence,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "damaged-slide.pptx"
    _write_deck(deck, with_image=False)
    damaged_part = _damage_member(
        deck, lambda name: name == "ppt/slides/slide1.xml"
    )

    with pytest.raises(
        pptx_evidence.PptxEvidenceError,
        match=f"structural PPTX member.*{damaged_part}",
    ):
        pptx_evidence.probe_pptx_artifact(deck)


def test_corrupt_member_scan_enforces_recovery_record_cap(
    pptx_evidence,
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "many-corrupt.zip"
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for index in range(
            pptx_evidence.PPTX_ARTIFACT_PROBE_MAX_RECOVERY_RECORDS + 1
        ):
            archive.writestr(f"ppt/media/image{index}.bin", b"asset")
    package = bytearray(package_path.read_bytes())
    cursor = 0
    while True:
        header = package.find(b"PK\x01\x02", cursor)
        if header < 0:
            break
        recorded_crc = struct.unpack_from("<I", package, header + 16)[0]
        struct.pack_into("<I", package, header + 16, recorded_crc ^ 0xFFFFFFFF)
        name_size, extra_size, comment_size = struct.unpack_from(
            "<HHH", package, header + 28
        )
        cursor = header + 46 + name_size + extra_size + comment_size

    with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
        pptx_evidence._corrupt_zip_members(bytes(package))
    assert caught.value.reason_code == "pptx_probe_result_oversized"


def test_malformed_container_is_structured_unavailable(
    pptx_evidence,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "not-a-deck.pptx"
    deck.write_bytes(b"not an OOXML ZIP package")

    with pytest.raises(
        pptx_evidence.PptxEvidenceError,
        match="invalid PPTX ZIP container",
    ):
        pptx_evidence.probe_pptx_artifact(deck)


def test_extractor_reports_recovered_media_and_keeps_schema_versions_distinct(
    pptx_extraction,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "damaged-media.pptx"
    _write_deck(deck, with_image=True)
    damaged_part = _damage_member(
        deck, lambda name: name.startswith("ppt/media/")
    )

    result = pptx_extraction.extract_pptx(deck, ocr=False)

    assert result["schema_version"] == 3
    assert result["pipeline_version"] == "1.2.0"
    assert result["archive_recovery"][0]["part_name"] == damaged_part
    assert result["corrupt_assets"] == [
        {
            "part_name": damaged_part,
            "error_type": "crc_mismatch",
            "status": "recovered_with_placeholder",
        }
    ]
    assert result["native_deck_audit"]["schema_version"] == 1
    assert result["native_deck_audit"]["extraction_schema_version"] == 3


def test_render_receipt_binds_exact_source_render_and_ranges(
    pptx_extraction,
    pptx_evidence,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "render-required.pptx"
    deck.parent.mkdir(parents=True, exist_ok=True)
    image_path = tmp_path / "full-bleed.png"
    Image.new("RGB", (640, 480), "navy").save(image_path)
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_picture(
        str(image_path),
        0,
        0,
        width=presentation.slide_width,
        height=presentation.slide_height,
    )
    presentation.save(deck)
    rendered = tmp_path / "rendered.pdf"
    _write_pdf(rendered, page_count=1)

    result = pptx_extraction.extract_pptx(
        deck,
        ocr=False,
        rendered_pdf_path=rendered,
        inspected_page_ranges=[[1, 1]],
    )
    audit = pptx_evidence.validate_native_deck_audit(
        result["native_deck_audit"], slide_count=1
    )

    assert audit["render_required_slide_numbers"] == [1]
    receipt = audit["rendered_page_inspection"]
    assert receipt["inspected_page_ranges"] == [[1, 1]]
    assert receipt["complete"] is True
    tampered = json.loads(json.dumps(audit))
    tampered["rendered_page_inspection"]["inspected_page_ranges"] = []
    with pytest.raises(
        pptx_evidence.PptxEvidenceError,
        match="inspected_required_slide_numbers",
    ):
        pptx_evidence.validate_native_deck_audit(tampered, slide_count=1)


@pytest.mark.parametrize(
    ("size_bytes", "slide_count"),
    [(True, 1), (1, True), (0, 1), (1, 0)],
)
def test_native_audit_builder_rejects_nonpositive_and_boolean_integers(
    pptx_evidence,
    size_bytes,
    slide_count,
) -> None:
    with pytest.raises(pptx_evidence.PptxEvidenceError):
        pptx_evidence.build_native_deck_audit(
            source_pptx_sha256="a" * 64,
            source_pptx_size_bytes=size_bytes,
            slide_count=slide_count,
            render_required_reasons={},
        )


def test_render_builder_rejects_boolean_slide_count_before_file_io(
    pptx_evidence,
    tmp_path: Path,
) -> None:
    with pytest.raises(pptx_evidence.PptxEvidenceError, match="positive integer"):
        pptx_evidence.build_rendered_page_inspection(
            source_pptx_sha256="a" * 64,
            rendered_pdf_path=tmp_path / "missing.pdf",
            inspected_page_ranges=[],
            required_slide_numbers=[],
            slide_count=True,
        )


def test_native_audit_rejects_future_or_extra_fields(
    pptx_evidence,
) -> None:
    audit = pptx_evidence.build_native_deck_audit(
        source_pptx_sha256="a" * 64,
        source_pptx_size_bytes=1,
        slide_count=1,
        render_required_reasons={},
    )
    future = dict(audit, schema_version=2)
    with pytest.raises(pptx_evidence.PptxEvidenceError, match="schema_version"):
        pptx_evidence.validate_native_deck_audit(future)
    extra = dict(audit, unexpected=True)
    with pytest.raises(pptx_evidence.PptxEvidenceError, match="unknown"):
        pptx_evidence.validate_native_deck_audit(extra)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0, 101.0, True])
def test_finite_confidence_rejects_nonfinite_or_out_of_domain(
    pptx_evidence,
    value,
) -> None:
    assert pptx_evidence.finite_confidence(value) is None


def test_extractor_has_no_inner_broad_exception_handler(
    pptx_extraction,
) -> None:
    tree = ast.parse(Path(pptx_extraction.__file__).read_text(encoding="utf-8"))
    broad_handlers: list[tuple[str, int]] = []
    for function in (
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    ):
        for node in ast.walk(function):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                broad_handlers.append((function.name, node.lineno))

    assert len(broad_handlers) == 1
    assert broad_handlers[0][0] == "main"


def test_single_file_cli_reports_parser_failure_without_traceback(
    pptx_extraction,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "broken.pptx"
    deck.write_bytes(b"not an OOXML ZIP package")

    completed = subprocess.run(
        [sys.executable, pptx_extraction.__file__, str(deck), "--no-ocr"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert "invalid PPTX ZIP container" in completed.stderr
    assert "Traceback" not in completed.stderr
