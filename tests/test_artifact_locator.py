"""Host-independent and native-host tests for artifact locator materialization."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest


SCRIPTS = Path(__file__).parents[1] / "skills" / "vault-ingress" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

artifact_locator = importlib.import_module("artifact_locator")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("talk.pptx", "relative"),
        ("conference/talk.pptx", "relative"),
        ("conference/name with spaces.pptx", "relative"),
        ("conférence/talk.pptx", "relative"),
        (".hidden/talk.pptx", "relative"),
        (PurePosixPath("conference/talk.pptx"), "relative"),
        ("/talk.pptx", "posix_absolute"),
        ("/Volumes/Talks/talk.pptx", "posix_absolute"),
        ("/Volumes/Talks/talk.pptx ", "posix_absolute"),
        ("/", "posix_absolute"),
        (PurePosixPath("/srv/talk.pptx"), "posix_absolute"),
        (r"C:\talk.pptx", "windows_drive_absolute"),
        ("c:/conference/talk.pptx", "windows_drive_absolute"),
        ("Z:\\", "windows_drive_absolute"),
        (r"C:\conference/mixed\talk.pptx", "windows_drive_absolute"),
        (PureWindowsPath(r"D:\Talks\talk.pptx"), "windows_drive_absolute"),
        (r"\\server\share\talk.pptx", "windows_unc_absolute"),
        (r"\\server/share\folder/talk.pptx", "windows_unc_absolute"),
        (r"\\server\share", "windows_unc_absolute"),
        ("\\\\server\\share\\", "windows_unc_absolute"),
        (PureWindowsPath(r"\\server\share\talk.pptx"), "windows_unc_absolute"),
    ],
)
def test_classifier_recognizes_closed_locator_flavors(
    raw: object,
    expected: str,
) -> None:
    assert artifact_locator.classify_artifact_locator(raw) == expected


@pytest.mark.parametrize(
    ("raw", "reason_code"),
    [
        (None, "artifact_locator_not_text"),
        (7, "artifact_locator_not_text"),
        (b"talk.pptx", "artifact_locator_not_text"),
        ("", "artifact_locator_empty_or_whitespace"),
        (" ", "artifact_locator_empty_or_whitespace"),
        ("\ttalk.pptx", "artifact_locator_empty_or_whitespace"),
        ("talk.pptx\n", "artifact_locator_empty_or_whitespace"),
        (" talk.pptx", "artifact_locator_empty_or_whitespace"),
        ("talk.pptx ", "artifact_locator_empty_or_whitespace"),
        ("talk\x00.pptx", "artifact_locator_nul_byte"),
        ("~", "artifact_locator_home_expansion_unsupported"),
        ("~/talk.pptx", "artifact_locator_home_expansion_unsupported"),
        ("~speaker/talk.pptx", "artifact_locator_home_expansion_unsupported"),
        (r"~\talk.pptx", "artifact_locator_home_expansion_unsupported"),
        (r"\\?\C:\talk.pptx", "artifact_locator_windows_device_namespace"),
        (r"\\.\C:\talk.pptx", "artifact_locator_windows_device_namespace"),
        (r"\??\C:\talk.pptx", "artifact_locator_windows_device_namespace"),
        (r"\\??\C:\talk.pptx", "artifact_locator_windows_device_namespace"),
        (r"//?/C:/talk.pptx", "artifact_locator_windows_device_namespace"),
        (r"//./C:/talk.pptx", "artifact_locator_windows_device_namespace"),
        (r"/??/C:/talk.pptx", "artifact_locator_windows_device_namespace"),
        (r"//??/C:/talk.pptx", "artifact_locator_windows_device_namespace"),
        ("C:", "artifact_locator_windows_drive_relative"),
        ("C:talk.pptx", "artifact_locator_windows_drive_relative"),
        ("c:folder/talk.pptx", "artifact_locator_windows_drive_relative"),
        ("conference/C:talk.pptx", "artifact_locator_windows_drive_relative"),
        ("conference/C:/talk.pptx", "artifact_locator_windows_drive_relative"),
        (r"\talk.pptx", "artifact_locator_windows_current_drive_rooted"),
        (r"\folder\talk.pptx", "artifact_locator_windows_current_drive_rooted"),
        ("//server/share/talk.pptx", "artifact_locator_ambiguous_double_slash"),
        ("///srv/talk.pptx", "artifact_locator_ambiguous_double_slash"),
        ("//", "artifact_locator_ambiguous_double_slash"),
        ("\\\\", "artifact_locator_malformed_unc"),
        (r"\\server", "artifact_locator_malformed_unc"),
        ("\\\\server\\", "artifact_locator_malformed_unc"),
        (r"\\server\\share", "artifact_locator_malformed_unc"),
        (r"\\\server\share", "artifact_locator_malformed_unc"),
        (r"\\\\server\share", "artifact_locator_malformed_unc"),
        (r"\\server\share\\folder", "artifact_locator_malformed_unc"),
        (r"\\server//share/folder", "artifact_locator_malformed_unc"),
        (r"\\server:\share\talk.pptx", "artifact_locator_malformed_unc"),
        (r"\\server\share:\talk.pptx", "artifact_locator_malformed_unc"),
        (".", "artifact_locator_dot_segment"),
        ("..", "artifact_locator_dot_segment"),
        ("./talk.pptx", "artifact_locator_dot_segment"),
        ("conference/../talk.pptx", "artifact_locator_dot_segment"),
        ("conference/./talk.pptx", "artifact_locator_dot_segment"),
        (r"conference\..\talk.pptx", "artifact_locator_dot_segment"),
        ("/srv/../talk.pptx", "artifact_locator_dot_segment"),
        (r"C:\Talks\..\talk.pptx", "artifact_locator_dot_segment"),
        (r"\\server\share\..\talk.pptx", "artifact_locator_dot_segment"),
        (r"conference\talk.pptx", "artifact_locator_noncanonical_relative"),
        (r"conference/talk\deck.pptx", "artifact_locator_noncanonical_relative"),
        ("conference//talk.pptx", "artifact_locator_noncanonical_relative"),
        ("conference///talk.pptx", "artifact_locator_noncanonical_relative"),
        ("conference/talk.pptx/", "artifact_locator_noncanonical_relative"),
        ("conference/.../talk.pptx", "artifact_locator_windows_trimmed_component"),
        ("conference./talk.pptx", "artifact_locator_windows_trimmed_component"),
        ("conference /talk.pptx", "artifact_locator_windows_trimmed_component"),
        ("conference/deck:stream.pptx", "artifact_locator_windows_reserved_character"),
        ("conference/deck?.pptx", "artifact_locator_windows_reserved_character"),
        ("conference/deck\x1f.pptx", "artifact_locator_windows_reserved_character"),
        ("CON/talk.pptx", "artifact_locator_windows_reserved_name"),
        ("con.pptx", "artifact_locator_windows_reserved_name"),
        ("con .pptx", "artifact_locator_windows_reserved_name"),
        ("aux.notes/talk.pptx", "artifact_locator_windows_reserved_name"),
        ("COM1/talk.pptx", "artifact_locator_windows_reserved_name"),
        ("lpt\u00b9.txt", "artifact_locator_windows_reserved_name"),
        ("CONIN$/talk.pptx", "artifact_locator_windows_reserved_name"),
        (r"C:\conference.\talk.pptx", "artifact_locator_windows_trimmed_component"),
        (
            r"C:\conference\deck:stream.pptx",
            "artifact_locator_windows_reserved_character",
        ),
        (r"C:\CON\talk.pptx", "artifact_locator_windows_reserved_name"),
        (
            r"\\server\share\conference.\talk.pptx",
            "artifact_locator_windows_trimmed_component",
        ),
        (
            r"\\server\share\deck:stream.pptx",
            "artifact_locator_windows_reserved_character",
        ),
        (r"\\server\share\NUL.pptx", "artifact_locator_windows_reserved_name"),
        (
            r"\\server.\share\talk.pptx",
            "artifact_locator_windows_trimmed_component",
        ),
        (
            "\\\\server\\share \\talk.pptx",
            "artifact_locator_windows_trimmed_component",
        ),
        (
            r"\\server?\share\talk.pptx",
            "artifact_locator_windows_reserved_character",
        ),
        (
            "\\\\server\\sha\x1fre\\talk.pptx",
            "artifact_locator_windows_reserved_character",
        ),
    ],
)
def test_classifier_rejects_ambiguous_or_noncanonical_forms(
    raw: object,
    reason_code: str,
) -> None:
    with pytest.raises(artifact_locator.ArtifactLocatorError) as caught:
        artifact_locator.classify_artifact_locator(raw)

    assert caught.value.reason_code == reason_code
    assert caught.value.args == (reason_code,)
    assert str(caught.value) == reason_code


@pytest.mark.parametrize("character", tuple('<>:"|?*'))
def test_portable_relative_components_reject_every_win32_reserved_character(
    character: str,
) -> None:
    locator = f"conference/deck{character}variant.pptx"

    with pytest.raises(artifact_locator.ArtifactLocatorError) as caught:
        artifact_locator.classify_artifact_locator(locator)

    assert caught.value.reason_code == "artifact_locator_windows_reserved_character"


@pytest.mark.parametrize("control", ("\x01", "\x1f"))
def test_portable_relative_components_reject_win32_control_characters(
    control: str,
) -> None:
    with pytest.raises(artifact_locator.ArtifactLocatorError) as caught:
        artifact_locator.classify_artifact_locator(f"conference/deck{control}.pptx")

    assert caught.value.reason_code == "artifact_locator_windows_reserved_character"


@pytest.mark.parametrize(
    "basename",
    (
        "CON",
        "PRN.txt",
        "AUX.notes",
        "NUL",
        "CONIN$",
        "CONOUT$.txt",
        "COM1",
        "COM9.txt",
        "COM\u00b9",
        "COM\u00b2.txt",
        "COM\u00b3",
        "LPT1",
        "LPT9.txt",
        "LPT\u00b9",
        "LPT\u00b2.txt",
        "LPT\u00b3",
        "CON .pptx",
    ),
)
def test_portable_relative_components_reject_win32_device_basenames(
    basename: str,
) -> None:
    with pytest.raises(artifact_locator.ArtifactLocatorError) as caught:
        artifact_locator.classify_artifact_locator(f"conference/{basename}")

    assert caught.value.reason_code == "artifact_locator_windows_reserved_name"


@pytest.mark.parametrize(
    "basename",
    ("COM0", "COM10", "LPT0", "LPT10", "CLOCK$", "DEL\x7f"),
)
def test_portable_relative_components_keep_nonreserved_near_misses(
    basename: str,
) -> None:
    assert (
        artifact_locator.classify_artifact_locator(f"conference/{basename}.pptx")
        == "relative"
    )


class _BytesPath:
    def __fspath__(self) -> bytes:
        return b"hidden-locator.pptx"


def test_non_text_pathlike_is_rejected_without_exposing_its_value() -> None:
    with pytest.raises(artifact_locator.ArtifactLocatorError) as caught:
        artifact_locator.classify_artifact_locator(_BytesPath())

    assert caught.value.reason_code == "artifact_locator_not_text"
    assert "hidden-locator" not in str(caught.value)


def test_error_instances_contain_only_a_closed_reason_code() -> None:
    secret_locator = "/private/credential-bearing/talk.pptx"
    error = artifact_locator.ArtifactLocatorError("artifact_locator_foreign_absolute")

    assert isinstance(error, ValueError)
    assert error.__dict__ == {"reason_code": "artifact_locator_foreign_absolute"}
    assert secret_locator not in str(error)
    assert secret_locator not in repr(error)

    with pytest.raises(ValueError, match="^invalid artifact locator reason code$"):
        artifact_locator.ArtifactLocatorError(secret_locator)


def _native_root() -> Path:
    return (
        Path(r"C:\trusted\artifacts") if os.name == "nt" else Path("/trusted/artifacts")
    )


def _native_absolute() -> str:
    return (
        r"C:\trusted\artifacts\talk.pptx"
        if os.name == "nt"
        else "/trusted/artifacts/talk.pptx"
    )


def _foreign_absolutes() -> tuple[str, str] | tuple[str]:
    if os.name == "nt":
        return ("/srv/talk.pptx",)
    return (r"C:\Talks\talk.pptx", r"\\server\share\talk.pptx")


def test_canonical_relative_locator_is_joined_from_pure_posix_parts() -> None:
    root = _native_root()

    materialized = artifact_locator.materialize_artifact_locator(
        PurePosixPath("conference/talk.pptx"),
        trusted_root=root,
    )

    assert materialized == root / "conference" / "talk.pptx"


def test_native_absolute_locator_and_root_materialize_lexically() -> None:
    root = _native_root()
    locator = _native_absolute()

    assert artifact_locator.materialize_native_root(root) == root
    assert artifact_locator.materialize_artifact_locator(locator) == Path(locator)
    assert artifact_locator.materialize_artifact_locator(
        locator,
        trusted_root=root,
    ) == Path(locator)


@pytest.mark.skipif(os.name == "nt", reason="POSIX-native filename semantics")
def test_native_posix_absolute_preserves_a_component_ending_in_space() -> None:
    locator = "/trusted/artifacts/talk.pptx "

    assert artifact_locator.materialize_artifact_locator(locator) == Path(locator)


def test_native_windows_unc_materializes_on_windows_only() -> None:
    locator = r"\\server\share\talk.pptx"

    if os.name == "nt":
        assert artifact_locator.materialize_artifact_locator(locator) == Path(locator)
        assert artifact_locator.materialize_native_root(r"\\server\share") == Path(
            r"\\server\share"
        )
    else:
        with pytest.raises(artifact_locator.ArtifactLocatorError) as caught:
            artifact_locator.materialize_artifact_locator(locator)
        assert caught.value.reason_code == "artifact_locator_foreign_absolute"


@pytest.mark.parametrize("locator", _foreign_absolutes())
def test_foreign_absolute_never_materializes(locator: str) -> None:
    with pytest.raises(artifact_locator.ArtifactLocatorError) as artifact_error:
        artifact_locator.materialize_artifact_locator(locator, _native_root())
    with pytest.raises(artifact_locator.ArtifactLocatorError) as root_error:
        artifact_locator.materialize_native_root(locator)

    assert artifact_error.value.reason_code == "artifact_locator_foreign_absolute"
    assert root_error.value.reason_code == "artifact_locator_foreign_absolute"
    assert locator not in str(artifact_error.value)
    assert locator not in str(root_error.value)


def test_relative_locator_requires_a_trusted_root() -> None:
    with pytest.raises(artifact_locator.ArtifactLocatorError) as caught:
        artifact_locator.materialize_artifact_locator("conference/talk.pptx")

    assert caught.value.reason_code == "artifact_locator_trusted_root_required"


@pytest.mark.parametrize("root", ["trusted/root", PurePosixPath("trusted/root")])
def test_relative_root_is_never_rebased_from_the_process_cwd(root: object) -> None:
    with pytest.raises(artifact_locator.ArtifactLocatorError) as caught:
        artifact_locator.materialize_native_root(root)

    assert caught.value.reason_code == "artifact_root_not_native_absolute"


def test_absolute_locator_still_validates_a_supplied_root() -> None:
    with pytest.raises(artifact_locator.ArtifactLocatorError) as caught:
        artifact_locator.materialize_artifact_locator(
            _native_absolute(),
            trusted_root="relative/root",
        )

    assert caught.value.reason_code == "artifact_root_not_native_absolute"


@pytest.mark.parametrize(
    ("root", "reason_code"),
    [
        ("~/artifacts", "artifact_locator_home_expansion_unsupported"),
        (r"\artifacts", "artifact_locator_windows_current_drive_rooted"),
        (r"C:artifacts", "artifact_locator_windows_drive_relative"),
        ("artifacts/../other", "artifact_locator_dot_segment"),
    ],
)
def test_root_lexical_failures_preserve_closed_reasons(
    root: object,
    reason_code: str,
) -> None:
    with pytest.raises(artifact_locator.ArtifactLocatorError) as caught:
        artifact_locator.materialize_native_root(root)

    assert caught.value.reason_code == reason_code


def test_materialization_does_not_call_filesystem_or_expansion_apis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("materialization performed filesystem normalization")

    monkeypatch.setattr(Path, "resolve", unexpected_call)
    monkeypatch.setattr(Path, "absolute", unexpected_call)
    monkeypatch.setattr(Path, "expanduser", unexpected_call)
    monkeypatch.setattr(Path, "cwd", unexpected_call)
    monkeypatch.setattr(Path, "exists", unexpected_call)
    monkeypatch.setattr(Path, "is_file", unexpected_call)
    monkeypatch.setattr(os.path, "abspath", unexpected_call)
    monkeypatch.setattr(os.path, "expanduser", unexpected_call)
    monkeypatch.setattr(os, "getcwd", unexpected_call)

    root = _native_root()
    assert (
        artifact_locator.materialize_artifact_locator(
            "conference/talk.pptx",
            root,
        )
        == root / "conference" / "talk.pptx"
    )
    assert artifact_locator.materialize_native_root(root) == root
