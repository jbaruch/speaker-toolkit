"""Per-render integration with fake CLI/API boundaries; no vendor process or network."""

import argparse
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from conftest import SCRIPTS_ILL, _import_script
from test_generate_illustrations import (
    _candidates,
    _single_build_slide,
    _write_candidates,
    _write_gate_outline,
    _write_manifest,
)


@pytest.fixture
def provider():
    return _import_script(Path(SCRIPTS_ILL) / "image_provider.py", "image_provider")


@pytest.fixture
def cli():
    return _import_script(Path(SCRIPTS_ILL) / "image_cli.py", "image_cli")


@pytest.fixture
def png():
    stream = io.BytesIO()
    Image.new("RGB", (24, 16), "navy").save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def ready(cli, monkeypatch, png):
    result = cli.CliProbe("ready", "/fake/codex", "0.153.2", auth_mode="chatgpt")
    monkeypatch.setattr(cli, "probe_codex", lambda: result)
    monkeypatch.setattr(
        cli,
        "render_codex",
        lambda *a, **kw: cli.CliImage(png, 24, 16, hashlib.sha256(png).hexdigest()),
    )
    return result


@pytest.fixture
def no_credentials(generate_illustrations, monkeypatch):
    gi = generate_illustrations
    monkeypatch.setattr(
        gi, "load_secrets", lambda *a: pytest.fail("read API credentials")
    )
    for name in (
        "_call_openai_generate",
        "_call_openai_edit",
        "_call_gemini",
        "_call_imagen",
    ):
        monkeypatch.setattr(gi, name, lambda *a, **kw: pytest.fail("called paid API"))


@pytest.mark.parametrize("lane", ["auto", "api", "cli"])
def test_public_arguments_are_shared(provider, lane):
    parser = argparse.ArgumentParser()
    provider.add_image_lane_arguments(parser)
    args = parser.parse_args(["--image-lane", lane, "--allow-cli-native"])
    assert (args.image_lane, args.allow_cli_native) == (lane, True)
    assert parser.parse_args([]).image_lane == "auto"
    assert parser.parse_args([]).allow_cli_native is False


@pytest.mark.parametrize("lane", ["auto", "api"])
@pytest.mark.parametrize(
    "model", ["gpt-image-2", "nano-banana-pro", "imagen-4.0-generate-001"]
)
def test_exact_and_api_only_requests_never_probe(
    provider, cli, monkeypatch, lane, model, capsys
):
    monkeypatch.setattr(
        cli, "probe_codex", lambda: pytest.fail("unnecessary CLI probe")
    )
    result = provider.select_image_lane(model, provider.ImageProviderOptions(lane))
    assert result.lane == "api"
    assert result.served_model == result.requested_model
    message = json.loads(capsys.readouterr().err.removeprefix("IMAGE_LANE "))
    assert message["lane"] == "api"
    assert message["binary"] is None and message["version"] is None


def test_native_probe_is_fresh_for_each_selection(
    provider, cli, ready, monkeypatch, capsys
):
    probes = iter([ready, replace(ready, version="0.153.3")])
    monkeypatch.setattr(cli, "probe_codex", lambda: next(probes))
    options = provider.ImageProviderOptions("auto", True)
    first = provider.select_image_lane("gpt-image-2", options)
    second = provider.select_image_lane("gpt-image-2", options)
    assert (first.version, second.version) == ("0.153.2", "0.153.3")
    assert first.served_model == cli.CODEX_NATIVE_MODEL
    assert first.requested_model != first.served_model
    assert len(capsys.readouterr().err.splitlines()) == 2


def test_nonfatal_cli_diagnostics_are_visible_on_success(
    provider, cli, ready, monkeypatch, png, capsys
):
    lane = provider.select_image_lane(
        "gpt-image-2", provider.ImageProviderOptions("cli", True)
    )
    monkeypatch.setattr(
        cli,
        "render_codex",
        lambda *a, **kw: cli.CliImage(
            png,
            24,
            16,
            hashlib.sha256(png).hexdigest(),
            warning_count=4,
        ),
    )
    result = provider.render_cli(lane, "cup")
    assert result.data == png and result.provenance()["warning_count"] == 4
    assert "WARNING: cli_item_diagnostics (4)" in capsys.readouterr().err


@pytest.mark.parametrize("lane", ["auto", "cli"])
@pytest.mark.parametrize("edit", [False, True])
def test_native_generate_edit_need_no_api_credentials(
    provider,
    cli,
    ready,
    generate_illustrations,
    no_credentials,
    monkeypatch,
    png,
    tmp_path,
    capsys,
    lane,
    edit,
):
    gi = generate_illustrations
    keys = gi.ImageKeys(options=provider.ImageProviderOptions(lane, True))
    reference = tmp_path / "source.png"
    reference.write_bytes(png)
    calls = []

    def render(plan, prompt, *, reference_path=None):
        calls.append((plan.operation, prompt, reference_path))
        return cli.CliImage(png, 24, 16, hashlib.sha256(png).hexdigest())

    monkeypatch.setattr(cli, "render_codex", render)
    result = (
        gi.edit_image(str(reference), "Erase cup. Keep table.", "gpt-image-2", keys)
        if edit
        else gi.generate_image("A blue cup", "gpt-image-2", keys)
    )
    assert result.data == png
    assert result.lane.lane == "cli"
    assert result.width == 24 and result.height == 16
    assert calls[0][0] == ("edit" if edit else "generate")
    assert calls[0][2] == (str(reference) if edit else None)
    if edit:
        assert "DO NOT add any new elements" in calls[0][1]
    assert reference.read_bytes() == png
    stderr = capsys.readouterr().err
    assert '"binary": "/fake/codex"' in stderr
    assert '"version": "0.153.2"' in stderr
    assert '"width": 24' in stderr


@pytest.mark.parametrize("failure", ["probe", "auth", "render"])
def test_present_failure_never_reads_keys_or_retries_api(
    provider,
    cli,
    ready,
    generate_illustrations,
    no_credentials,
    monkeypatch,
    capsys,
    failure,
):
    gi = generate_illustrations
    if failure == "probe":
        monkeypatch.setattr(
            cli,
            "probe_codex",
            lambda: replace(ready, state="failed", failure_code="cli_auth_required"),
        )
    elif failure == "auth":
        monkeypatch.setattr(cli, "probe_codex", lambda: replace(ready, auth_mode="api"))
    else:

        def fail(*a, **kw):
            raise provider.ImageLaneError(
                "cli_provider_failed", "repair CLI; no API retry"
            )

        monkeypatch.setattr(cli, "render_codex", fail)
    result = gi.generate_image(
        "cup",
        "gpt-image-2",
        gi.ImageKeys(options=provider.ImageProviderOptions("auto", True)),
    )
    assert result.data is None
    assert "ERROR:" in capsys.readouterr().err


def test_absent_cli_uses_existing_api_and_reports_it(
    provider,
    cli,
    generate_illustrations,
    monkeypatch,
    capsys,
    png,
):
    gi = generate_illustrations
    monkeypatch.setattr(cli, "probe_codex", lambda: cli.CliProbe("absent"))
    calls = []
    monkeypatch.setattr(
        gi, "load_secrets", lambda *a: ({"openai": "fixture-key"}, "/fake/secrets.json")
    )

    def api(prompt, model, key, *, size):
        calls.append((model, key, size))
        return png, "image/png"

    monkeypatch.setattr(gi, "_call_openai_generate", api)
    result = gi.generate_image(
        "cup",
        "gpt-image-2",
        gi.ImageKeys(options=provider.ImageProviderOptions("auto", True)),
    )
    assert result.data == png
    assert calls == [("gpt-image-2-2026-04-21", "fixture-key", "2048x1152")]
    stderr = capsys.readouterr().err
    assert '"reason_code": "cli_absent"' in stderr
    assert "fixture-key" not in stderr


@pytest.mark.parametrize(
    "model,masked,reason",
    [
        ("gpt-image-2", False, "cli_cannot_pin_image_model"),
        ("gpt-image-2", True, "cli_mask_not_supported"),
        ("gemini-3-pro-image", False, "family_api_only"),
    ],
)
def test_forced_cli_refuses_unverified_edit_constraints(
    provider,
    generate_illustrations,
    no_credentials,
    model,
    masked,
    reason,
):
    gi = generate_illustrations
    options = provider.ImageProviderOptions("cli", masked)
    result = gi.edit_image(
        "/unused/source.png",
        "erase",
        model,
        gi.ImageKeys(options=options),
        erase_region=[0, 0, 1, 1] if masked else None,
    )
    assert result.data is None
    assert reason in result.detail


def test_generate_runner_absent_cli_exits_success_and_writes_image(
    provider,
    cli,
    generate_illustrations,
    monkeypatch,
    tmp_path,
    png,
):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, "gpt-image-2")
    _write_manifest(tmp_path, ["gpt-image-2"])
    monkeypatch.setattr(cli, "probe_codex", lambda: cli.CliProbe("absent"))
    monkeypatch.setattr(
        gi, "load_secrets", lambda *a: ({"openai": "fixture-key"}, "/fake/secrets.json")
    )
    monkeypatch.setattr(
        gi, "_call_openai_generate", lambda *a, **kw: (png, "image/png")
    )
    gi.run_generate(
        str(outline), ["all"], lane_options=provider.ImageProviderOptions("auto", True)
    )
    assert (tmp_path / "illustrations" / "slide-01.png").read_bytes() == png


def test_generate_runner_present_failure_exits_nonzero(
    provider,
    cli,
    ready,
    generate_illustrations,
    no_credentials,
    monkeypatch,
    tmp_path,
):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, "gpt-image-2")
    _write_manifest(tmp_path, ["gpt-image-2"])
    monkeypatch.setattr(
        cli,
        "probe_codex",
        lambda: replace(ready, state="failed", failure_code="cli_auth_required"),
    )
    with pytest.raises(SystemExit) as caught:
        gi.run_generate(
            str(outline),
            ["all"],
            lane_options=provider.ImageProviderOptions("auto", True),
        )
    assert caught.value.code == 1
    assert not (tmp_path / "illustrations" / "slide-01.png").exists()


@pytest.mark.parametrize("edit", [False, True])
def test_missing_api_key_is_a_reported_cell_failure_without_provider_call(
    generate_illustrations,
    monkeypatch,
    edit,
    capsys,
):
    gi = generate_illustrations
    monkeypatch.setattr(gi, "load_secrets", lambda *a: ({}, "/fake/secrets.json"))
    monkeypatch.setattr(
        gi, "_call_openai_generate", lambda *a, **kw: pytest.fail("called API")
    )
    monkeypatch.setattr(
        gi, "_call_openai_edit", lambda *a, **kw: pytest.fail("called API")
    )
    result = (
        gi.edit_image("/unused.png", "erase", "gpt-image-2", gi.ImageKeys())
        if edit
        else gi.generate_image("cup", "gpt-image-2", gi.ImageKeys())
    )
    assert result.data is None and "image_api_key_missing" in result.detail
    assert result.lane.lane == "api"
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_mixed_grid_retains_native_success_when_api_key_is_missing(
    provider,
    ready,
    generate_illustrations,
    monkeypatch,
    tmp_path,
    png,
):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, "gpt-image-2")
    candidates = _write_candidates(
        tmp_path,
        _candidates(
            slides={"FULL": 1},
            models=["gpt-image-2", "gemini-3-pro-image"],
            styles=[{"name": "Ink", "anchors": {"FULL": "Ink drawing."}}],
        ),
    )
    monkeypatch.setattr(gi, "load_secrets", lambda *a: ({}, "/fake/secrets.json"))
    monkeypatch.setattr(gi, "_call_gemini", lambda *a: pytest.fail("called API"))
    monkeypatch.setattr(gi.time, "sleep", lambda *a: None)
    with pytest.raises(SystemExit) as caught:
        gi.run_style_explore(
            str(outline),
            candidates,
            lane_options=provider.ImageProviderOptions("auto", True),
        )
    assert caught.value.code == 1
    base = tmp_path / "style-explore"
    cells = json.loads((base / "rendered.json").read_text())["cells"]
    assert [cell["status"] for cell in cells] == ["OK", "FAIL"]
    assert (base / cells[0]["rel_path"]).read_bytes() == png
    assert "image_api_key_missing" in cells[1]["error"]


@pytest.mark.parametrize("native", [False, True])
def test_v2_manifest_gate_uses_served_model_not_requested_model(
    provider,
    ready,
    generate_illustrations,
    tmp_path,
    png,
    native,
):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, "gpt-image-2")
    base = tmp_path / "style-explore"
    base.mkdir()
    (base / "image.png").write_bytes(png)
    lane = provider.select_image_lane(
        "gpt-image-2", provider.ImageProviderOptions("auto", native)
    )
    render = provider.ImageRender(png, "image/png", lane)
    result = {
        "style": "A",
        "format": "FULL",
        "model": "gpt-image-2",
        "status": "OK",
        "rel_path": "image.png",
        "provenance": render.provenance(),
    }
    path = gi.write_rendered_manifest(str(base), str(outline), [result])
    manifest = json.loads(Path(path).read_text())
    assert manifest["schema_version"] == 2
    assert manifest["models_rendered_ok"] == [lane.served_model]
    assert gi.check_style_explore(str(outline))["gate_passed"] is (not native)
    index = gi.render_explore_index({"styles": [{"name": "A"}]}, [result])
    assert lane.served_model in index
    assert f"({lane.lane})" in index
    assert Path(path).read_text() == json.dumps(manifest, indent=2)


@pytest.mark.parametrize(
    "provenance", [None, {}, {"lane": {}}, {"lane": {"lane": "api"}}]
)
def test_v2_missing_provenance_never_becomes_bake_evidence(
    generate_illustrations, tmp_path, png, provenance
):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, "gpt-image-2")
    base = tmp_path / "style-explore"
    base.mkdir()
    (base / "image.png").write_bytes(png)
    gi.write_rendered_manifest(
        str(base),
        str(outline),
        [
            {
                "style": "A",
                "format": "FULL",
                "model": "gpt-image-2",
                "status": "OK",
                "rel_path": "image.png",
                "provenance": provenance,
            }
        ],
    )
    assert gi.check_style_explore(str(outline))["gate_passed"] is False


@pytest.mark.parametrize(
    "model,reason",
    [
        ("gemini-3-pro-image", "family_api_only"),
        ("gpt-image-2", "cli_multiple_references_unverified"),
    ],
)
def test_thumbnail_forced_cli_refuses_before_keys_and_images(
    generate_thumbnail,
    monkeypatch,
    model,
    reason,
    capsys,
):
    gt = generate_thumbnail
    monkeypatch.setattr(gt, "load_api_key", lambda *a: pytest.fail("loaded API key"))
    monkeypatch.setattr(
        gt, "load_image_as_base64", lambda *a: pytest.fail("loaded source image")
    )
    args = SimpleNamespace(model=model, image_lane="cli", allow_cli_native=True)
    with pytest.raises(SystemExit) as caught:
        gt.compose_thumbnail(args)
    assert caught.value.code == 1
    assert reason in capsys.readouterr().err


def test_thumbnail_reports_each_api_render_and_resolves_alias(
    generate_thumbnail,
    monkeypatch,
    tmp_path,
    png,
    capsys,
):
    gt = generate_thumbnail
    monkeypatch.setattr(gt, "load_api_key", lambda *a: "fixture-key")
    monkeypatch.setattr(
        gt, "load_image_as_base64", lambda *a: ("fixture-image", "image/png")
    )
    calls = []

    def api(parts, model, key):
        calls.append(model)
        return png, "image/png"

    monkeypatch.setattr(gt, "call_gemini", api)
    args = SimpleNamespace(
        model="nano-banana-pro",
        image_lane="api",
        allow_cli_native=False,
        vault=None,
        slide_image="slide.png",
        speaker_photo="photo.png",
        brand_colors=None,
        aesthetic="photo",
        style="overlay",
        title="A cup",
        subtitle=None,
        portrait_style="ink",
        title_position="top",
        output=str(tmp_path / "thumbnail.png"),
    )
    gt.compose_thumbnail(args)
    assert calls == ["gemini-3-pro-image", "gemini-3-pro-image"]
    lines = capsys.readouterr().err.splitlines()
    lanes = [
        json.loads(line.removeprefix("IMAGE_LANE "))
        for line in lines
        if line.startswith("IMAGE_LANE ")
    ]
    assert len(lanes) == 2
    assert all(
        lane["lane"] == "api" and lane["reason_code"] == "api_forced" for lane in lanes
    )
    with Image.open(args.output) as image:
        assert image.size == (1280, 720)


def test_native_style_grid_persists_observed_output_without_passing_bake_gate(
    provider,
    cli,
    ready,
    generate_illustrations,
    no_credentials,
    monkeypatch,
    tmp_path,
    png,
):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, "gpt-image-2")
    candidates = _write_candidates(
        tmp_path,
        _candidates(
            slides={"FULL": 1},
            models=["gpt-image-2"],
            styles=[{"name": "Ink", "anchors": {"FULL": "Ink drawing."}}],
        ),
    )
    monkeypatch.setattr(gi.time, "sleep", lambda *a: None)
    gi.run_style_explore(
        str(outline),
        candidates,
        lane_options=provider.ImageProviderOptions("cli", True),
    )
    base = tmp_path / "style-explore"
    manifest = json.loads((base / "rendered.json").read_text())
    cell = manifest["cells"][0]
    assert cell["status"] == "OK"
    assert "cli-native-unpinned" in cell["rel_path"]
    assert (base / cell["rel_path"]).read_bytes() == png
    assert cell["provenance"]["width"] == 24
    assert cell["provenance"]["sha256"] == hashlib.sha256(png).hexdigest()
    assert cli.CODEX_NATIVE_MODEL in (base / "index.md").read_text()
    assert gi.check_style_explore(str(outline))["gate_passed"] is False


def test_native_compare_labels_observed_model_and_output_file(
    provider,
    cli,
    ready,
    generate_illustrations,
    no_credentials,
    monkeypatch,
    tmp_path,
    capsys,
):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, "gpt-image-2")
    monkeypatch.setattr(gi, "COMPARE_MODELS", ["gpt-image-2"])
    gi.run_compare(
        str(outline), 1, lane_options=provider.ImageProviderOptions("cli", True)
    )
    outputs = list((tmp_path / "illustrations" / "model-comparison").glob("*.png"))
    assert len(outputs) == 1 and "cli-native-unpinned" in outputs[0].name
    assert f"{cli.CODEX_NATIVE_MODEL} [cli]" in capsys.readouterr().out


@pytest.mark.parametrize("masked", [False, True])
def test_build_uses_previous_native_edit_or_refuses_masked_cli(
    provider,
    cli,
    ready,
    generate_illustrations,
    no_credentials,
    monkeypatch,
    tmp_path,
    png,
    masked,
):
    gi = generate_illustrations
    outline = _single_build_slide(
        [
            {"step": 0, "description": "Erase cup. Keep table.", "is_full": False},
            {
                "step": 1,
                "description": "Erase glass. Keep table.",
                "is_full": False,
                "erase_region": [0, 0, 1, 1] if masked else None,
            },
            {"step": 2, "description": "full", "is_full": True},
        ]
    )
    outline["model"] = "gpt-image-2"
    source = tmp_path / "slide-60.png"
    source.write_bytes(png)
    options = provider.ImageProviderOptions("cli", True)
    monkeypatch.setattr(
        gi,
        "_load_context",
        lambda *a, **kw: (gi.ImageKeys(options=options), outline, str(tmp_path)),
    )
    monkeypatch.setattr(gi, "enforce_render_gate", lambda *a: None)
    monkeypatch.setattr(gi.time, "sleep", lambda *a: None)
    seen = []

    def render(lane, prompt, *, reference_path):
        seen.append(reference_path)
        assert lane.operation == "edit"
        assert Path(reference_path).read_bytes() == png
        return cli.CliImage(png, 24, 16, hashlib.sha256(png).hexdigest())

    monkeypatch.setattr(cli, "render_codex", render)
    if masked:
        with pytest.raises(SystemExit) as caught:
            gi.run_build("ignored.yaml", "60", lane_options=options)
        assert caught.value.code == 1
        assert seen == []
        assert not (tmp_path / "builds" / "slide-60-build-00.png").exists()
    else:
        gi.run_build("ignored.yaml", "60", lane_options=options)
        assert seen == [str(source), str(tmp_path / "builds" / "slide-60-build-01.png")]
        assert (tmp_path / "builds" / "slide-60-build-00.png").read_bytes() == png
    assert source.read_bytes() == png


@pytest.mark.parametrize(
    "mode,arguments",
    [
        ("run_generate", ["all"]),
        ("run_edit", ["--edit", "1", "erase"]),
        ("run_fix", ["--fix", "1", "change"]),
        ("run_build", ["--build", "all"]),
        ("run_compare", ["--compare", "1"]),
        ("run_style_explore", ["--style-explore", "candidates.json"]),
    ],
)
def test_main_forwards_lane_options_to_every_render_mode(
    provider,
    generate_illustrations,
    monkeypatch,
    tmp_path,
    mode,
    arguments,
):
    gi = generate_illustrations
    outline = _write_gate_outline(tmp_path, "gpt-image-2")
    seen = []
    monkeypatch.setattr(gi, mode, lambda *a, **kw: seen.append(kw["lane_options"]))
    monkeypatch.setattr(gi, "_cli_vault_path", None)
    monkeypatch.setattr(
        gi.sys,
        "argv",
        [
            "generate",
            str(outline),
            *arguments,
            "--image-lane",
            "cli",
            "--allow-cli-native",
        ],
    )
    gi.main()
    assert seen == [provider.ImageProviderOptions("cli", True)]
