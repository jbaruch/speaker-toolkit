"""Pure lane decisions against fixed fake CLI probe outcomes; no provider I/O."""

from dataclasses import replace
from pathlib import Path

import pytest

from conftest import SCRIPTS_ILL, _import_script


@pytest.fixture
def lanes():
    return _import_script(
        Path(SCRIPTS_ILL) / "image_lane_contract.py", "image_lane_contract"
    )


@pytest.fixture
def image_request(lanes):
    return lanes.ImageRequest(
        "openai", "gpt-image-2-2026-04-21", requested_size=(2048, 1152)
    )


@pytest.fixture
def native_request(image_request):
    return replace(image_request, allow_native_model=True, allow_native_geometry=True)


@pytest.fixture
def ready(lanes):
    return lanes.CliProbe(
        "ready", "/synthetic/bin/codex", "0.153.2", auth_mode="chatgpt"
    )


@pytest.mark.parametrize("forced", ["auto", "api"])
def test_exact_model_stays_exact_without_consulting_cli(lanes, image_request, forced):
    result = lanes.resolve_image_lane(image_request, None, forced_lane=forced)
    assert result.lane == "api"
    assert result.served_model == image_request.model
    assert result.geometry == "requested"


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({}, "cli_cannot_pin_image_model"),
        ({"allow_native_model": True}, "cli_cannot_guarantee_image_size"),
        ({"family": "gemini", "model": "gemini-3-pro-image"}, "family_api_only"),
        (
            {"family": "imagen", "model": "imagen-4.0-ultra-generate-001"},
            "family_api_only",
        ),
    ],
)
def test_forced_cli_cannot_weaken_constraints(lanes, image_request, updates, reason):
    with pytest.raises(lanes.ImageLaneError) as caught:
        lanes.resolve_image_lane(
            replace(image_request, **updates), None, forced_lane="cli"
        )
    assert caught.value.reason_code == reason


@pytest.mark.parametrize("forced", ["auto", "cli"])
@pytest.mark.parametrize("edit", [False, True])
def test_native_choice_is_explicit_and_names_real_binary(
    lanes, native_request, ready, forced, edit
):
    if edit:
        native_request = replace(native_request, operation="edit", reference_count=1)
    result = lanes.resolve_image_lane(native_request, ready, forced_lane=forced)
    assert result.lane == "cli"
    assert result.served_model == lanes.CODEX_NATIVE_MODEL
    assert result.served_model != result.requested_model
    assert result.geometry == "native_observed"
    assert (result.binary, result.version) == (ready.binary, ready.version)
    assert result.operation == native_request.operation


def test_only_absence_authorizes_auto_api_fallback(lanes, native_request):
    result = lanes.resolve_image_lane(native_request, lanes.CliProbe("absent"))
    assert result.lane == "api"
    assert result.reason_code == "cli_absent"
    assert result.served_model == native_request.model


def test_forced_cli_absence_never_selects_api(lanes, native_request):
    with pytest.raises(lanes.ImageLaneError, match="image_cli_absent"):
        lanes.resolve_image_lane(
            native_request, lanes.CliProbe("absent"), forced_lane="cli"
        )


@pytest.mark.parametrize(
    "failure",
    [
        "timeout",
        "auth_required",
        "quota_exhausted",
        "unsupported_client",
        "version_invalid",
    ],
)
@pytest.mark.parametrize("forced", ["auto", "cli"])
def test_present_cli_failure_never_selects_a_paid_retry(
    lanes, native_request, failure, forced
):
    probe = lanes.CliProbe("failed", "/synthetic/bin/codex", failure_code=failure)
    with pytest.raises(lanes.ImageLaneError, match="cli_probe_failed"):
        lanes.resolve_image_lane(native_request, probe, forced_lane=forced)


def test_forced_api_needs_no_cli_or_native_substitution(lanes, native_request):
    result = lanes.resolve_image_lane(native_request, None, forced_lane="api")
    assert (result.lane, result.served_model, result.reason_code) == (
        "api",
        native_request.model,
        "api_forced",
    )


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"masked": True}, "cli_mask_not_supported"),
        ({"reference_count": 2}, "cli_multiple_references_unverified"),
    ],
)
def test_unproven_build_or_composition_capabilities_refuse_cli(
    lanes, native_request, ready, updates, reason
):
    image_request = replace(native_request, operation="edit", reference_count=1)
    image_request = replace(image_request, **updates)
    assert lanes.resolve_image_lane(image_request, ready).lane == "api"
    with pytest.raises(lanes.ImageLaneError, match=reason):
        lanes.resolve_image_lane(image_request, ready, forced_lane="cli")


@pytest.mark.parametrize("forced", ["auto", "api", "cli"])
def test_imagen_edit_never_routes_to_an_unsupported_endpoint(
    lanes, image_request, forced
):
    image_request = replace(
        image_request,
        family="imagen",
        model="imagen-4.0-ultra-generate-001",
        operation="edit",
        reference_count=1,
    )
    with pytest.raises(lanes.ImageLaneError, match="image_edit_unsupported"):
        lanes.resolve_image_lane(image_request, None, forced_lane=forced)


@pytest.mark.parametrize(
    "updates",
    [
        {"family": []},
        {"family": "unknown"},
        {"model": "private\nvalue"},
        {"operation": "unknown"},
        {"operation": []},
        {"reference_count": True},
        {"reference_count": -1},
        {"reference_count": 17},
        {"reference_count": 1},
        {"operation": "edit"},
        {"masked": True},
        {"masked": 1},
        {"allow_native_model": 1},
        {"allow_native_geometry": "yes"},
        {"requested_size": [2048, 1152]},
        {"requested_size": (0, 1152)},
        {"requested_size": (True, 1152)},
        {"requested_size": (2048,)},
    ],
)
def test_malformed_request_fails_before_any_lane_is_selected(
    lanes, image_request, updates
):
    with pytest.raises(lanes.ImageLaneError):
        lanes.resolve_image_lane(replace(image_request, **updates), None)


@pytest.mark.parametrize(
    "updates",
    [
        {"state": "unknown"},
        {"state": []},
        {"binary": "bad\npath"},
        {"binary": ""},
        {"version": "0.153.2 private data"},
        {"version": None},
        {"failure_code": "unexpected"},
        {"state": "absent"},
        {"state": "failed"},
    ],
)
def test_malformed_probe_never_becomes_api_fallback(
    lanes, native_request, ready, updates
):
    with pytest.raises(lanes.ImageLaneError, match="invalid_cli_probe"):
        lanes.resolve_image_lane(native_request, replace(ready, **updates))


def test_missing_probe_does_not_mean_absent(lanes, native_request):
    with pytest.raises(lanes.ImageLaneError, match="cli_probe_required"):
        lanes.resolve_image_lane(native_request, None)


def test_model_cannot_cross_vendor_dispatch(lanes, image_request):
    with pytest.raises(lanes.ImageLaneError, match="image_model_family_mismatch"):
        lanes.resolve_image_lane(
            replace(image_request, model="gemini-3-pro-image"), None
        )


@pytest.mark.parametrize("binary", ["codex", "relative/codex", "C:codex"])
def test_cli_binary_must_be_resolved(lanes, native_request, ready, binary):
    with pytest.raises(lanes.ImageLaneError, match="invalid_cli_probe"):
        lanes.resolve_image_lane(native_request, replace(ready, binary=binary))


@pytest.mark.parametrize("binary", ["/synthetic/bin/codex", r"C:\synthetic\codex.exe"])
def test_native_platform_binary_identity_is_preserved(
    lanes, native_request, ready, binary
):
    result = lanes.resolve_image_lane(native_request, replace(ready, binary=binary))
    assert result.binary == binary


@pytest.mark.parametrize("forced", [None, [], "unknown"])
def test_invalid_lane_override_is_not_auto(lanes, image_request, forced):
    with pytest.raises(lanes.ImageLaneError, match="invalid_image_lane"):
        lanes.resolve_image_lane(image_request, None, forced_lane=forced)


def test_failed_probe_category_is_visible_but_raw_provider_text_is_not_accepted(
    lanes, native_request
):
    with pytest.raises(lanes.ImageLaneError, match="quota_exhausted"):
        lanes.resolve_image_lane(
            native_request,
            lanes.CliProbe(
                "failed", "/synthetic/bin/codex", failure_code="quota_exhausted"
            ),
        )
    with pytest.raises(lanes.ImageLaneError, match="invalid_cli_probe"):
        lanes.resolve_image_lane(
            native_request,
            lanes.CliProbe(
                "failed",
                "/synthetic/bin/codex",
                failure_code="secret=private provider response",
            ),
        )


@pytest.mark.parametrize("auth_mode", ["api", "unknown"])
@pytest.mark.parametrize("forced", ["auto", "cli"])
def test_cli_cannot_masquerade_api_auth_as_subscription(
    lanes, native_request, ready, auth_mode, forced
):
    with pytest.raises(lanes.ImageLaneError, match="image_cli_subscription_required"):
        lanes.resolve_image_lane(
            native_request, replace(ready, auth_mode=auth_mode), forced_lane=forced
        )


@pytest.mark.parametrize("auth_mode", [None, "private response", [], True])
def test_unverified_auth_probe_is_not_cli_readiness(
    lanes, native_request, ready, auth_mode
):
    with pytest.raises(lanes.ImageLaneError, match="invalid_cli_probe"):
        lanes.resolve_image_lane(native_request, replace(ready, auth_mode=auth_mode))
