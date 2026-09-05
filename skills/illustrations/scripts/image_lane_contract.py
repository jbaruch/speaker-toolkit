"""Pure image-provider lane selection; no provider call or credential read.

The caller supplies the current CLI probe outcome. A failed probe is distinct
from an absent executable and never authorizes a metered retry. Resolution
preserves the requested model/geometry unless the caller explicitly permits
native output. This module describes a proposed render, not an output receipt.

Codex's recorded generate/edit probe in issue #385 establishes native output,
not an exact image-model snapshot, typed size control, masks, or multi-reference
composition. Unsupported CLI requirements remain on their API adapter in auto
mode; forcing CLI makes the incompatibility an error instead of weakening it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
import re


LANES = frozenset({"auto", "api", "cli"})
FAMILIES = frozenset({"gemini", "imagen", "openai"})
OPERATIONS = frozenset({"generate", "edit"})
PROBE_STATES = frozenset({"absent", "ready", "failed"})
CODEX_NATIVE_MODEL = "codex-native-image-model-unpinned"
FAMILY_PREFIXES = {
    "openai": ("gpt-image",),
    "imagen": ("imagen",),
    "gemini": ("gemini", "nano-banana"),
}
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,255}\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z")
_REASON = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class ImageLaneError(ValueError):
    """A closed selection failure; raw CLI diagnostics do not cross this boundary."""

    def __init__(self, reason: str, action: str) -> None:
        if _REASON.fullmatch(reason) is None:
            raise ValueError("invalid image-lane reason code")
        self.reason_code = reason
        super().__init__(f"{reason}; {action}")


@dataclass(frozen=True)
class ImageRequest:
    """The resolved API model and render constraints the caller must preserve."""

    family: str
    model: str
    operation: str = "generate"
    requested_size: tuple[int, int] | None = None
    reference_count: int = 0
    masked: bool = False
    allow_native_model: bool = False
    allow_native_geometry: bool = False


@dataclass(frozen=True)
class CliProbe:
    """Fresh adapter probe result, not a cached claim of subscription eligibility.

    Ready establishes executable/version, invocation surface, and authentication
    mode without logging in or changing credentials. The actual
    render can still fail for login, tool availability, quota, or provider errors.
    None of those failures permits selecting a different lane afterwards.
    """

    state: str
    binary: str | None = None
    version: str | None = None
    failure_code: str | None = None
    auth_mode: str | None = None


@dataclass(frozen=True)
class ImageLane:
    """One dispatch decision. No image-generation success is implied."""

    family: str
    lane: str
    operation: str
    requested_model: str
    served_model: str
    geometry: str
    reason_code: str
    binary: str | None = None
    version: str | None = None


def _validate_request(request: ImageRequest, forced_lane: str) -> None:
    if not isinstance(request, ImageRequest):
        raise ImageLaneError("invalid_image_request", "supply an ImageRequest")
    if not isinstance(forced_lane, str) or forced_lane not in LANES:
        raise ImageLaneError("invalid_image_lane", "select auto, api, or cli")
    if not isinstance(request.family, str) or request.family not in FAMILIES:
        raise ImageLaneError("unsupported_image_family", "select a supported vendor")
    if not isinstance(request.model, str) or _MODEL.fullmatch(request.model) is None:
        raise ImageLaneError("invalid_image_model", "supply a canonical model ID")
    if not request.model.lower().startswith(FAMILY_PREFIXES[request.family]):
        raise ImageLaneError(
            "image_model_family_mismatch",
            "resolve the model through the shared registry",
        )
    if not isinstance(request.operation, str) or request.operation not in OPERATIONS:
        raise ImageLaneError("invalid_image_operation", "select generate or edit")
    if any(
        type(value) is not bool
        for value in (
            request.masked,
            request.allow_native_model,
            request.allow_native_geometry,
        )
    ):
        raise ImageLaneError("invalid_image_request", "use explicit boolean options")
    if (
        type(request.reference_count) is not int
        or not 0 <= request.reference_count <= 16
    ):
        raise ImageLaneError(
            "invalid_image_references", "supply a bounded reference count"
        )
    if request.operation == "generate" and (request.reference_count or request.masked):
        raise ImageLaneError(
            "invalid_image_references", "use edit for reference images"
        )
    if request.operation == "edit" and request.reference_count == 0:
        raise ImageLaneError("invalid_image_references", "supply the image to edit")
    if request.requested_size is not None and (
        not isinstance(request.requested_size, tuple)
        or len(request.requested_size) != 2
        or any(
            type(value) is not int or not 0 < value <= 16384
            for value in request.requested_size
        )
    ):
        raise ImageLaneError("invalid_image_size", "supply positive width and height")
    if request.family == "imagen" and request.operation == "edit":
        raise ImageLaneError("image_edit_unsupported", "choose an edit-capable model")


def _validate_probe(probe: CliProbe) -> None:
    if (
        not isinstance(probe, CliProbe)
        or not isinstance(probe.state, str)
        or probe.state not in PROBE_STATES
    ):
        raise ImageLaneError("invalid_cli_probe", "rerun the CLI adapter probe")
    if probe.state == "absent":
        if any(
            value is not None
            for value in (
                probe.binary,
                probe.version,
                probe.failure_code,
                probe.auth_mode,
            )
        ):
            raise ImageLaneError("invalid_cli_probe", "rerun the CLI adapter probe")
        return
    if (
        not isinstance(probe.binary, str)
        or not probe.binary.strip()
        or len(probe.binary) > 4096
        or any(character in probe.binary for character in ("\0", "\n", "\r"))
        or not (
            PurePosixPath(probe.binary).is_absolute()
            or PureWindowsPath(probe.binary).is_absolute()
        )
    ):
        raise ImageLaneError("invalid_cli_probe", "resolve the CLI executable again")
    if probe.state == "failed":
        if (
            not isinstance(probe.failure_code, str)
            or _REASON.fullmatch(probe.failure_code) is None
        ):
            raise ImageLaneError("invalid_cli_probe", "rerun the CLI adapter probe")
        return
    if (
        not isinstance(probe.version, str)
        or len(probe.version) > 64
        or _VERSION.fullmatch(probe.version) is None
        or probe.failure_code is not None
        or probe.auth_mode not in ("chatgpt", "api", "unknown")
    ):
        raise ImageLaneError("invalid_cli_probe", "resolve the CLI version again")


def _cli_incompatibility(request: ImageRequest) -> str | None:
    if request.family != "openai":
        return "family_api_only"
    if not request.allow_native_model:
        return "cli_cannot_pin_image_model"
    if request.requested_size is not None and not request.allow_native_geometry:
        return "cli_cannot_guarantee_image_size"
    if request.masked:
        return "cli_mask_not_supported"
    if request.reference_count > 1:
        return "cli_multiple_references_unverified"
    return None


def resolve_image_lane(
    request: ImageRequest,
    probe: CliProbe | None,
    *,
    forced_lane: str = "auto",
) -> ImageLane:
    """Choose once, before credentials or rendering; never retry another provider.

    API-only/forced-API requests need no CLI probe. A compatible auto/CLI request
    requires a fresh one. Only an absent executable permits automatic API fallback;
    a failed or malformed probe refuses dispatch. Native substitutions each require
    their own request opt-in and are explicit in the returned lane description.
    """
    _validate_request(request, forced_lane)
    reason = "api_forced" if forced_lane == "api" else _cli_incompatibility(request)
    if reason is not None:
        if forced_lane == "cli":
            raise ImageLaneError(
                reason, "use the API lane or revise explicit render constraints"
            )
        return ImageLane(
            request.family,
            "api",
            request.operation,
            request.model,
            request.model,
            "requested",
            reason,
        )
    if probe is None:
        raise ImageLaneError(
            "cli_probe_required", "probe the installed CLI before selecting a lane"
        )
    _validate_probe(probe)
    if probe.state == "failed":
        raise ImageLaneError(
            "cli_probe_failed",
            f"repair the CLI ({probe.failure_code}); no automatic metered retry was selected",
        )
    if probe.state == "absent":
        if forced_lane == "cli":
            raise ImageLaneError(
                "image_cli_absent", "install the CLI or explicitly select the API lane"
            )
        return ImageLane(
            request.family,
            "api",
            request.operation,
            request.model,
            request.model,
            "requested",
            "cli_absent",
        )
    if probe.auth_mode != "chatgpt":
        raise ImageLaneError(
            "image_cli_subscription_required",
            "select ChatGPT authentication yourself; this resolver changes no credentials and selects no metered retry",
        )
    return ImageLane(
        request.family,
        "cli",
        request.operation,
        request.model,
        CODEX_NATIVE_MODEL,
        "native_observed",
        "cli_forced" if forced_lane == "cli" else "cli_available",
        probe.binary,
        probe.version,
    )
