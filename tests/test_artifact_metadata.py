"""Shared artifact metadata and PPTX compatibility regressions."""

from __future__ import annotations

import copy
import os
import stat
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest


def _generation(
    artifact_metadata,
    *,
    size: int = 123,
    mode: int | None = None,
    flags: int | None = 0,
    file_attributes: int | None = 0,
):
    return artifact_metadata.FileGeneration(
        size=size,
        mtime_ns=2,
        ctime_ns=3,
        device=4,
        inode=5,
        mode=stat.S_IFREG | 0o644 if mode is None else mode,
        flags=flags,
        file_attributes=file_attributes,
    )


def _available_payload(artifact_metadata, generation=None):
    current = generation or _generation(artifact_metadata)
    return {
        "schema_version": artifact_metadata.METADATA_SCHEMA_VERSION,
        "status": "available",
        "generation": current.to_dict(),
        "root_generation": None,
        "reparse_tag": None,
    }


def _stat_snapshot(
    *,
    file_attributes: int = 0,
    reparse_tag: int | None = None,
):
    return SimpleNamespace(
        st_size=123,
        st_mtime_ns=2,
        st_ctime_ns=3,
        st_dev=4,
        st_ino=5,
        st_mode=stat.S_IFREG | 0o644,
        st_flags=0,
        st_file_attributes=file_attributes,
        st_reparse_tag=reparse_tag,
    )


def test_platform_constants_are_exact(artifact_metadata) -> None:
    assert artifact_metadata.METADATA_SCHEMA_VERSION == 1
    assert artifact_metadata.METADATA_FAILURE_KINDS == {
        "io",
        "missing",
        "not_regular",
        "root_escape",
        "symlink_or_reparse",
    }
    assert artifact_metadata.WINDOWS_REPARSE_POINT_ATTRIBUTE == 0x00000400
    assert artifact_metadata.WINDOWS_OFFLINE_ATTRIBUTE == 0x00001000
    assert artifact_metadata.WINDOWS_RECALL_ON_OPEN_ATTRIBUTE == 0x00040000
    assert artifact_metadata.WINDOWS_RECALL_ON_DATA_ACCESS_ATTRIBUTE == 0x00400000
    assert artifact_metadata.WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES == 0x00441000
    assert artifact_metadata.WINDOWS_CLOUD_REPARSE_TAGS == frozenset(
        0x9000001A + (suffix << 12) for suffix in range(16)
    )

    expected_dataless = int(
        getattr(
            artifact_metadata.stat_module,
            "SF_DATALESS",
            0x40000000 if sys.platform == "darwin" else 0,
        )
    )
    assert artifact_metadata.MACOS_DATALESS_FLAG == expected_dataless
    if sys.platform == "darwin":
        assert expected_dataless == 0x40000000


@pytest.mark.parametrize(
    ("attribute_name", "availability_field"),
    [
        ("WINDOWS_OFFLINE_ATTRIBUTE", "windows_offline"),
        ("WINDOWS_RECALL_ON_OPEN_ATTRIBUTE", "windows_recall_on_open"),
        (
            "WINDOWS_RECALL_ON_DATA_ACCESS_ATTRIBUTE",
            "windows_recall_on_data_access",
        ),
    ],
)
def test_windows_availability_bits_are_independent(
    artifact_metadata,
    attribute_name: str,
    availability_field: str,
) -> None:
    attribute = getattr(artifact_metadata, attribute_name)
    generation = _generation(artifact_metadata, file_attributes=attribute)

    availability = artifact_metadata.ArtifactAvailability.from_generation(
        generation,
        macos_dataless_flag=0,
        windows_cloud_file_attributes=attribute,
    )

    assert availability.state == "unavailable"
    assert availability.macos_dataless is False
    for field in (
        "windows_offline",
        "windows_recall_on_open",
        "windows_recall_on_data_access",
    ):
        assert getattr(availability, field) is (field == availability_field)


def test_windows_availability_respects_the_active_mask(artifact_metadata) -> None:
    generation = _generation(
        artifact_metadata,
        file_attributes=artifact_metadata.WINDOWS_RECALL_ON_OPEN_ATTRIBUTE,
    )

    availability = artifact_metadata.ArtifactAvailability.from_generation(
        generation,
        macos_dataless_flag=0,
        windows_cloud_file_attributes=artifact_metadata.WINDOWS_OFFLINE_ATTRIBUTE,
    )

    assert availability.state == "local"
    assert availability.windows_recall_on_open is False


def test_cloud_placeholder_details_preserve_bits_and_macos_precedence(
    artifact_metadata,
) -> None:
    dataless = 0x40000000
    flags = dataless | 0x20
    attributes = (
        artifact_metadata.WINDOWS_REPARSE_POINT_ATTRIBUTE
        | artifact_metadata.WINDOWS_OFFLINE_ATTRIBUTE
    )
    generation = _generation(
        artifact_metadata,
        flags=flags,
        file_attributes=attributes,
    )

    assert artifact_metadata.generation_cloud_placeholder_details(
        generation,
        macos_dataless_flag=dataless,
        windows_cloud_file_attributes=(
            artifact_metadata.WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES
        ),
    ) == {"st_flags": flags}
    assert artifact_metadata.generation_cloud_placeholder_details(
        _generation(
            artifact_metadata,
            flags=0,
            file_attributes=attributes,
        ),
        macos_dataless_flag=dataless,
        windows_cloud_file_attributes=(
            artifact_metadata.WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES
        ),
    ) == {"file_attributes": attributes}
    assert (
        artifact_metadata.generation_cloud_placeholder_details(
            _generation(
                artifact_metadata,
                flags=None,
                file_attributes=None,
            ),
            macos_dataless_flag=dataless,
            windows_cloud_file_attributes=(
                artifact_metadata.WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES
            ),
        )
        is None
    )


def test_reparse_policy_accepts_only_hydrated_supported_cloud_leaves(
    artifact_metadata,
) -> None:
    cloud_tag = min(artifact_metadata.WINDOWS_CLOUD_REPARSE_TAGS)
    hydrated = _stat_snapshot(
        file_attributes=artifact_metadata.WINDOWS_REPARSE_POINT_ATTRIBUTE,
        reparse_tag=cloud_tag,
    )
    unknown = _stat_snapshot(
        file_attributes=artifact_metadata.WINDOWS_REPARSE_POINT_ATTRIBUTE,
        reparse_tag=0xA000000C,
    )
    missing_tag = _stat_snapshot(
        file_attributes=artifact_metadata.WINDOWS_REPARSE_POINT_ATTRIBUTE,
    )

    assert artifact_metadata.reparse_tag(hydrated) == cloud_tag
    assert not artifact_metadata.is_unsupported_reparse(
        hydrated,
        allow_hydrated_cloud_file=True,
    )
    assert artifact_metadata.is_unsupported_reparse(
        hydrated,
        allow_hydrated_cloud_file=False,
    )
    assert artifact_metadata.is_unsupported_reparse(
        unknown,
        allow_hydrated_cloud_file=True,
    )
    assert artifact_metadata.reparse_tag(missing_tag) == -1
    assert artifact_metadata.is_unsupported_reparse(
        missing_tag,
        allow_hydrated_cloud_file=True,
    )


def test_inspection_binds_exact_leaf_and_stable_root_identity(
    artifact_metadata,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    deck = root / "nested" / "deck.pptx"
    deck.parent.mkdir(parents=True)
    deck.write_bytes(b"deck")

    receipt = artifact_metadata.inspect_metadata_generation(
        deck,
        trusted_root=root,
    )

    assert receipt.generation == artifact_metadata.FileGeneration.from_stat(
        deck.lstat()
    )
    assert receipt.root_generation == (
        artifact_metadata.FileGeneration.from_directory_identity(root.lstat())
    )
    assert receipt.reparse_tag is None


def test_metadata_relative_locator_is_materialized_beneath_native_root(
    artifact_metadata,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    deck = root / "nested" / "deck.pptx"
    deck.parent.mkdir(parents=True)
    deck.write_bytes(b"deck")

    receipt = artifact_metadata.inspect_metadata_generation(
        "nested/deck.pptx",
        trusted_root=root,
    )

    assert receipt.generation == artifact_metadata.FileGeneration.from_stat(
        deck.lstat()
    )
    assert receipt.root_generation == (
        artifact_metadata.FileGeneration.from_directory_identity(root.lstat())
    )


def test_metadata_invalid_locators_fail_before_filesystem_inspection(
    artifact_metadata,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    foreign_locators = (
        ["/foreign/deck.pptx"]
        if os.name == "nt"
        else [r"C:\conference\deck.pptx", r"\\server\share\deck.pptx"]
    )
    cases = [
        ("deck.pptx", None, "artifact_locator_trusted_root_required"),
        (
            "~/deck.pptx",
            None,
            "artifact_locator_home_expansion_unsupported",
        ),
        (
            r"conference\deck.pptx",
            tmp_path,
            "artifact_locator_noncanonical_relative",
        ),
        (
            tmp_path / "deck.pptx",
            "relative-root",
            "artifact_root_not_native_absolute",
        ),
        *[
            (foreign, None, "artifact_locator_foreign_absolute")
            for foreign in foreign_locators
        ],
    ]
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda *_args, **_kwargs: pytest.fail("invalid locator reached lstat"),
    )

    for locator, root, expected_failure in cases:
        with pytest.raises(artifact_metadata.ArtifactMetadataMalformed) as caught:
            artifact_metadata.inspect_metadata_generation(
                locator,
                trusted_root=root,
            )
        assert caught.value.locator_failure == expected_failure
        assert os.fspath(locator) not in str(caught.value)


def test_directory_identity_excludes_mutable_child_metadata(
    artifact_metadata,
) -> None:
    first = _stat_snapshot()
    first.st_mode = stat.S_IFDIR | 0o755
    changed_children = copy.copy(first)
    changed_children.st_size += 4096
    changed_children.st_mtime_ns += 1
    changed_children.st_ctime_ns += 1

    first_identity = artifact_metadata.FileGeneration.from_directory_identity(first)
    changed_identity = artifact_metadata.FileGeneration.from_directory_identity(
        changed_children
    )

    assert first_identity == changed_identity
    assert first_identity.size == 0
    assert first_identity.mtime_ns == 0
    assert first_identity.ctime_ns == 0


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("dev", 40),
        ("ino", 50),
        ("mode", stat.S_IFDIR | 0o700),
        ("flags", 4),
        ("file_attributes", 8),
    ],
)
def test_directory_identity_retains_swap_and_policy_fields(
    artifact_metadata,
    field: str,
    replacement: int,
) -> None:
    first = _stat_snapshot()
    first.st_mode = stat.S_IFDIR | 0o755
    changed = copy.copy(first)
    setattr(changed, f"st_{field}", replacement)

    assert artifact_metadata.FileGeneration.from_directory_identity(
        first
    ) != artifact_metadata.FileGeneration.from_directory_identity(changed)


def test_trusted_root_locator_maps_symlink_without_resolving_leaf(
    artifact_metadata,
    tmp_path: Path,
) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    locator = tmp_path / "canonical-vault"
    try:
        locator.symlink_to(storage, target_is_directory=True)
    except OSError:
        pytest.skip("directory policy does not permit symlink creation")
    requested = locator / "slides" / "missing.pdf"

    artifact, root = artifact_metadata.canonicalize_trusted_artifact_locator(
        requested,
        locator,
    )

    assert root == storage.resolve()
    assert artifact == storage.resolve() / "slides" / "missing.pdf"


def test_inspection_reports_closed_failure_kinds(
    artifact_metadata,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(artifact_metadata.ArtifactMetadataMalformed):
        artifact_metadata.inspect_metadata_generation(
            Path("relative.pptx"),
            trusted_root=None,
        )

    missing = tmp_path / "missing.pptx"
    with pytest.raises(artifact_metadata.ArtifactMetadataUnavailable) as caught:
        artifact_metadata.inspect_metadata_generation(missing, trusted_root=None)
    assert caught.value.failure_kind == "missing"
    assert caught.value.exception_type == "FileNotFoundError"

    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(artifact_metadata.ArtifactMetadataUnavailable) as caught:
        artifact_metadata.inspect_metadata_generation(directory, trusted_root=None)
    assert caught.value.failure_kind == "not_regular"
    assert caught.value.exception_type is None

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.pptx"
    with pytest.raises(artifact_metadata.ArtifactMetadataUnavailable) as caught:
        artifact_metadata.inspect_metadata_generation(
            outside,
            trusted_root=root,
        )
    assert caught.value.failure_kind == "root_escape"

    parent_file = root / "not-a-directory"
    parent_file.write_bytes(b"file")
    with pytest.raises(artifact_metadata.ArtifactMetadataUnavailable) as caught:
        artifact_metadata.inspect_metadata_generation(
            parent_file / "deck.pptx",
            trusted_root=root,
        )
    assert caught.value.failure_kind == "not_regular"

    blocked = tmp_path / "blocked.pptx"
    original_lstat = Path.lstat

    def blocked_lstat(path: Path):
        if path == blocked:
            raise PermissionError("sensitive path must not escape")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", blocked_lstat)
    with pytest.raises(artifact_metadata.ArtifactMetadataUnavailable) as caught:
        artifact_metadata.inspect_metadata_generation(blocked, trusted_root=None)
    assert caught.value.failure_kind == "io"
    assert caught.value.exception_type == "PermissionError"
    assert str(blocked) not in str(caught.value)


@pytest.mark.parametrize("supported", [True, False])
def test_inspection_allows_only_supported_hydrated_cloud_tags(
    artifact_metadata,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    supported: bool,
) -> None:
    deck = tmp_path / "cloud.pptx"
    cloud_tag = min(artifact_metadata.WINDOWS_CLOUD_REPARSE_TAGS)
    snapshot = _stat_snapshot(
        file_attributes=(
            artifact_metadata.WINDOWS_REPARSE_POINT_ATTRIBUTE
            | artifact_metadata.WINDOWS_OFFLINE_ATTRIBUTE
        ),
        reparse_tag=cloud_tag if supported else 0xA000000C,
    )
    monkeypatch.setattr(Path, "lstat", lambda _path: snapshot)

    if supported:
        receipt = artifact_metadata.inspect_metadata_generation(
            deck,
            trusted_root=None,
        )
        assert receipt.generation.file_attributes == snapshot.st_file_attributes
        assert receipt.reparse_tag == cloud_tag
    else:
        with pytest.raises(artifact_metadata.ArtifactMetadataUnavailable) as caught:
            artifact_metadata.inspect_metadata_generation(deck, trusted_root=None)
        assert caught.value.failure_kind == "symlink_or_reparse"


def test_decoder_accepts_closed_hydrated_cloud_receipt(artifact_metadata) -> None:
    cloud_tag = min(artifact_metadata.WINDOWS_CLOUD_REPARSE_TAGS)
    generation = _generation(
        artifact_metadata,
        file_attributes=(
            artifact_metadata.WINDOWS_REPARSE_POINT_ATTRIBUTE
            | artifact_metadata.WINDOWS_OFFLINE_ATTRIBUTE
        ),
    )
    root_generation = _generation(
        artifact_metadata,
        size=0,
        mode=stat.S_IFDIR | 0o755,
    )
    root_generation = replace(
        root_generation,
        mtime_ns=0,
        ctime_ns=0,
    )
    payload = {
        "schema_version": artifact_metadata.METADATA_SCHEMA_VERSION,
        "status": "available",
        "generation": generation.to_dict(),
        "root_generation": root_generation.to_dict(),
        "reparse_tag": cloud_tag,
    }

    receipt = artifact_metadata.decode_artifact_metadata_payload(
        payload,
        unavailable_reason_code="pdf_artifact_unavailable",
    )

    assert receipt.generation == generation
    assert receipt.root_generation == root_generation
    assert receipt.reparse_tag == cloud_tag


@pytest.mark.parametrize("field", ["size", "mtime_ns", "ctime_ns"])
def test_decoder_rejects_mutable_directory_metadata_in_root_identity(
    artifact_metadata,
    field: str,
) -> None:
    root_identity = _generation(
        artifact_metadata,
        size=0,
        mode=stat.S_IFDIR | 0o755,
    )
    root_identity = replace(
        root_identity,
        mtime_ns=0,
        ctime_ns=0,
    )
    malformed = replace(root_identity, **{field: 1})
    payload = _available_payload(artifact_metadata)
    payload["root_generation"] = malformed.to_dict()

    with pytest.raises(artifact_metadata.ArtifactMetadataMalformed):
        artifact_metadata.decode_artifact_metadata_payload(
            payload,
            unavailable_reason_code="pdf_artifact_unavailable",
        )


def test_decoder_preserves_closed_unavailable_receipt(artifact_metadata) -> None:
    payload = {
        "schema_version": artifact_metadata.METADATA_SCHEMA_VERSION,
        "status": "unavailable",
        "reason_code": "pdf_artifact_unavailable",
        "details": {
            "failure_kind": "missing",
            "exception_type": "FileNotFoundError",
        },
    }

    with pytest.raises(artifact_metadata.ArtifactMetadataUnavailable) as caught:
        artifact_metadata.decode_artifact_metadata_payload(
            payload,
            unavailable_reason_code="pdf_artifact_unavailable",
        )

    assert caught.value.failure_kind == "missing"
    assert caught.value.exception_type == "FileNotFoundError"
    assert str(caught.value) == "missing"


def test_decoder_rejects_malformed_or_inconsistent_receipts(
    artifact_metadata,
) -> None:
    regular = _generation(artifact_metadata)
    base = _available_payload(artifact_metadata, regular)
    malformed: list[dict[str, object]] = []

    extra = copy.deepcopy(base)
    extra["unexpected"] = True
    malformed.append(extra)

    missing = copy.deepcopy(base)
    missing.pop("generation")
    malformed.append(missing)

    negative_size = copy.deepcopy(base)
    negative_size["generation"]["size"] = -1
    malformed.append(negative_size)

    nonregular = copy.deepcopy(base)
    nonregular["generation"]["mode"] = stat.S_IFDIR | 0o755
    malformed.append(nonregular)

    bool_tag = copy.deepcopy(base)
    bool_tag["reparse_tag"] = True
    malformed.append(bool_tag)

    tag_without_attribute = copy.deepcopy(base)
    tag_without_attribute["reparse_tag"] = min(
        artifact_metadata.WINDOWS_CLOUD_REPARSE_TAGS
    )
    malformed.append(tag_without_attribute)

    attribute_without_tag = copy.deepcopy(base)
    attribute_without_tag["generation"]["file_attributes"] = (
        artifact_metadata.WINDOWS_REPARSE_POINT_ATTRIBUTE
    )
    malformed.append(attribute_without_tag)

    unknown_tag = copy.deepcopy(attribute_without_tag)
    unknown_tag["reparse_tag"] = 0xA000000C
    malformed.append(unknown_tag)

    root_is_file = copy.deepcopy(base)
    root_is_file["root_generation"] = regular.to_dict()
    malformed.append(root_is_file)

    wrong_reason = {
        "schema_version": artifact_metadata.METADATA_SCHEMA_VERSION,
        "status": "unavailable",
        "reason_code": "pptx_artifact_unavailable",
        "details": {"failure_kind": "missing"},
    }
    malformed.append(wrong_reason)

    for payload in malformed:
        with pytest.raises(artifact_metadata.ArtifactMetadataMalformed):
            artifact_metadata.decode_artifact_metadata_payload(
                payload,
                unavailable_reason_code="pdf_artifact_unavailable",
            )


def test_pptx_modules_keep_compatibility_constants_and_types(
    artifact_metadata,
    pptx_evidence,
    pptx_extraction,
) -> None:
    assert pptx_evidence.PPTX_MACOS_DATALESS_FLAG == (
        artifact_metadata.MACOS_DATALESS_FLAG
    )
    assert pptx_evidence.PPTX_WINDOWS_REPARSE_POINT_ATTRIBUTE == (
        artifact_metadata.WINDOWS_REPARSE_POINT_ATTRIBUTE
    )
    assert pptx_evidence.PPTX_WINDOWS_CLOUD_REPARSE_TAGS == (
        artifact_metadata.WINDOWS_CLOUD_REPARSE_TAGS
    )
    assert pptx_evidence._MetadataReceipt is (artifact_metadata.ArtifactMetadataReceipt)
    assert pptx_extraction._WINDOWS_REPARSE_POINT_ATTRIBUTE == (
        artifact_metadata.WINDOWS_REPARSE_POINT_ATTRIBUTE
    )
    assert pptx_extraction._WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES == (
        artifact_metadata.WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES
    )
    assert pptx_extraction._WINDOWS_CLOUD_REPARSE_TAGS == (
        artifact_metadata.WINDOWS_CLOUD_REPARSE_TAGS
    )


@pytest.mark.parametrize(
    "attribute_name",
    [
        "WINDOWS_OFFLINE_ATTRIBUTE",
        "WINDOWS_RECALL_ON_OPEN_ATTRIBUTE",
        "WINDOWS_RECALL_ON_DATA_ACCESS_ATTRIBUTE",
    ],
)
def test_pptx_batch_wrapper_keeps_exact_cloud_reason(
    artifact_metadata,
    pptx_extraction,
    attribute_name: str,
) -> None:
    snapshot = SimpleNamespace(
        st_file_attributes=(
            artifact_metadata.WINDOWS_REPARSE_POINT_ATTRIBUTE
            | getattr(artifact_metadata, attribute_name)
        ),
        st_reparse_tag=min(artifact_metadata.WINDOWS_CLOUD_REPARSE_TAGS),
    )

    assert (
        pptx_extraction._windows_leaf_rejection_reason(snapshot)
        == "pptx_batch_cloud_placeholder_unavailable"
    )


def test_pptx_metadata_invocation_contract_includes_fixed_identity(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck = Path(os.path.abspath(tmp_path / "deck.pptx"))
    generation = pptx_evidence.FileGeneration(
        size=123,
        mtime_ns=2,
        ctime_ns=3,
        device=4,
        inode=5,
        mode=stat.S_IFREG | 0o644,
        flags=None,
        file_attributes=None,
    )
    captured: dict[str, object] = {}

    def runner(
        command,
        operation,
        expected_generations,
        payload,
        limits,
        **kwargs,
    ):
        captured.update(
            command=command,
            operation=operation,
            expected_generations=expected_generations,
            payload=payload,
            limits=limits,
            kwargs=kwargs,
        )
        return SimpleNamespace(
            payload={
                "schema_version": 1,
                "status": "available",
                "generation": generation.to_dict(),
                "root_generation": None,
                "reparse_tag": None,
            },
            observed_generations={},
            diagnostics=None,
        )

    monkeypatch.setattr(pptx_evidence, "run_authenticated_worker", runner)

    receipt = pptx_evidence._run_bounded_metadata_worker(deck)

    assert receipt.generation == generation
    assert captured["command"] == [
        sys.executable,
        os.fspath(Path(pptx_evidence.__file__).absolute()),
        pptx_evidence.PPTX_SUPERVISED_WORKER_FLAG,
    ]
    assert captured["operation"] == "pptx_metadata"
    assert captured["expected_generations"] == {}
    assert captured["payload"] == {
        "pptx_path": os.fspath(deck),
        "trusted_root": None,
    }
    assert captured["limits"] is pptx_evidence.PPTX_METADATA_LIMITS
    assert captured["kwargs"] == {
        "immutable_process_identity": captured["command"][:2],
        "sensitive_values": (deck,),
        "schema_generation": 4,
        "pipeline_generation": "1.5.0",
    }
    assert os.fspath(deck) not in "\n".join(cast(list[str], captured["command"]))


def test_pptx_metadata_failure_adapter_is_byte_stable(
    pptx_evidence,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def runner(*_args, **_kwargs):
        return SimpleNamespace(
            payload={
                "schema_version": 1,
                "status": "unavailable",
                "reason_code": "pptx_artifact_unavailable",
                "details": {
                    "failure_kind": "missing",
                    "exception_type": "FileNotFoundError",
                },
            },
            observed_generations={},
            diagnostics=None,
        )

    monkeypatch.setattr(pptx_evidence, "run_authenticated_worker", runner)

    with pytest.raises(pptx_evidence.PptxEvidenceError) as caught:
        pptx_evidence._run_bounded_metadata_worker(tmp_path / "missing.pptx")

    assert caught.value.reason_code == "pptx_artifact_unavailable"
    assert caught.value.details == {
        "failure_kind": "missing",
        "exception_type": "FileNotFoundError",
    }
    assert str(caught.value) == (
        "PPTX artifact is unavailable; restore the file and retry"
    )


def test_pptx_metadata_child_payloads_are_byte_stable(
    pptx_evidence,
    tmp_path: Path,
) -> None:
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(b"deck")
    generation = pptx_evidence.FileGeneration.from_stat(deck.lstat())

    assert pptx_evidence._metadata_child(
        {"pptx_path": os.fspath(deck), "trusted_root": None}
    ) == {
        "schema_version": 1,
        "status": "available",
        "generation": generation.to_dict(),
        "root_generation": None,
        "reparse_tag": None,
    }

    missing = tmp_path / "missing.pptx"
    assert pptx_evidence._metadata_child(
        {"pptx_path": os.fspath(missing), "trusted_root": None}
    ) == {
        "schema_version": 1,
        "status": "unavailable",
        "reason_code": "pptx_artifact_unavailable",
        "details": {
            "failure_kind": "missing",
            "exception_type": "FileNotFoundError",
        },
    }
