"""Native-lane orchestration with fake CLI outcomes and generated image bytes."""

from dataclasses import asdict, replace
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from conftest import SCRIPTS_ILL, _import_script


@pytest.fixture
def cli():
    return _import_script(Path(SCRIPTS_ILL) / "image_cli.py", "image_cli")


@pytest.fixture
def png():
    stream = io.BytesIO()
    Image.new("RGB", (24, 16), "navy").save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def events():
    return b"\n".join(
        json.dumps(value).encode()
        for value in (
            {"type": "thread.started", "thread_id": "fixed"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "done"},
            },
            {"type": "turn.completed", "usage": {}},
        )
    )


@pytest.fixture
def ready(cli):
    return cli.CliProbe("ready", "/fake/codex", "0.153.2", auth_mode="chatgpt")


@pytest.fixture
def lane(cli, ready):
    return cli.ImageLane(
        "openai",
        "cli",
        "generate",
        "gpt-image-2-2026-04-21",
        cli.CODEX_NATIVE_MODEL,
        "native_observed",
        "cli_forced",
        ready.binary,
        ready.version,
    )


def test_absence_is_not_a_failed_probe(cli, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli, "_worker", lambda *a: pytest.fail("must not start worker"))
    assert cli.probe_codex() == cli.CliProbe("absent")


def test_present_probe_uses_authenticated_worker(cli, monkeypatch, ready):
    calls = []
    monkeypatch.setattr(cli.shutil, "which", lambda name: ready.binary)

    def worker(operation, payload):
        calls.append((operation, payload))
        return asdict(ready)

    monkeypatch.setattr(cli, "_worker", worker)
    assert cli.probe_codex() == ready
    assert calls == [(cli.PROBE_OPERATION, {"binary": ready.binary})]


@pytest.mark.parametrize(
    "reason", ["cli_worker_timeout", "cli_auth_required", "cli_worker_resource_limit"]
)
def test_present_probe_failure_does_not_become_absence(cli, monkeypatch, reason):
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/fake/codex")

    def worker(*args):
        raise cli.ImageLaneError(reason, "repair")

    monkeypatch.setattr(cli, "_worker", worker)
    result = cli.probe_codex()
    assert result.state == "failed"
    assert result.failure_code == reason


@pytest.mark.parametrize("value", [None, {}, {"state": "absent"}])
def test_malformed_probe_is_visible(cli, monkeypatch, value):
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/fake/codex")
    monkeypatch.setattr(cli, "_worker", lambda *args: value)
    assert cli.probe_codex().failure_code == "cli_probe_malformed"


@pytest.mark.parametrize("auth_mode", ["chatgpt", "api"])
def test_probe_observes_version_help_and_auth_without_logging_in(
    cli, monkeypatch, tmp_path, auth_mode
):
    binary = tmp_path / "codex"
    binary.write_bytes(b"fake executable")
    calls = []
    login = (
        b"Logged in using ChatGPT"
        if auth_mode == "chatgpt"
        else b"Logged in using an API key - fixture-only"
    )
    outputs = [
        (b"codex-cli 0.153.2\n", b""),
        (b"--ephemeral --skip-git-repo-check --json --image --sandbox --color", b""),
        (b"", login),
    ]

    def run(command, workspace):
        calls.append(command)
        stdout, stderr = outputs.pop(0)
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(cli, "run_cli_command", run)
    probe = cli._probe(str(binary), tmp_path)
    assert probe.version == "0.153.2"
    assert probe.auth_mode == auth_mode
    assert [command[1:] for command in calls] == [
        ["--version"],
        ["exec", "--help"],
        ["login", "status"],
    ]
    assert "fixture-only" not in repr(probe)


@pytest.mark.parametrize(
    "stage,result,reason",
    [
        (0, (1, b"", b"private"), "cli_version_invalid"),
        (0, (0, b"not a version", b""), "cli_version_invalid"),
        (1, (0, b"--json", b""), "cli_invocation_unsupported"),
        (2, (1, b"", b"private"), "cli_auth_required"),
        (2, (0, b"", b"unrecognized private status"), "cli_auth_unverified"),
    ],
)
def test_probe_failure_is_closed_and_stops(
    cli, monkeypatch, tmp_path, stage, result, reason
):
    binary = tmp_path / "codex"
    binary.write_bytes(b"fake executable")
    outputs = [
        (0, b"codex-cli 0.153.2", b""),
        (0, b"--ephemeral --skip-git-repo-check --json --image --sandbox --color", b""),
        (0, b"", b"Logged in using ChatGPT"),
    ]
    outputs[stage] = result
    calls = []

    def run(command, workspace):
        calls.append(command)
        code, out, err = outputs.pop(0)
        return SimpleNamespace(returncode=code, stdout=out, stderr=err)

    monkeypatch.setattr(cli, "run_cli_command", run)
    with pytest.raises(cli.ImageLaneError, match=reason) as caught:
        cli._probe(str(binary), tmp_path)
    assert len(calls) == stage + 1
    assert "private" not in str(caught.value)


def test_render_sends_prompt_on_stdin_and_reads_literal_output(
    cli, monkeypatch, tmp_path, png, events, ready
):
    monkeypatch.setattr(cli, "_probe", lambda *args: ready)
    calls = []

    def run(command, workspace, *, input_bytes):
        calls.append((command, input_bytes))
        (workspace / cli.OUTPUT_NAME).write_bytes(png)
        return SimpleNamespace(returncode=0, stdout=events, stderr=b"")

    monkeypatch.setattr(cli, "run_cli_command", run)
    metadata = cli._render(
        {
            "binary": ready.binary,
            "version": ready.version,
            "prompt": "private visual request",
            "reference": None,
        },
        tmp_path,
    )
    image = cli._decode_image(metadata, tmp_path)
    assert image.data == png
    assert (image.width, image.height, image.mime_type) == (24, 16, "image/png")
    assert image.sha256 == hashlib.sha256(png).hexdigest()
    command, stdin = calls[0]
    assert command[-2:] == ["--", "-"]
    assert "private visual request" not in " ".join(command)
    assert b"private visual request" in stdin
    assert "workspace-write" in command
    assert not any(
        "bypass" in argument or "ignore-rules" in argument for argument in command
    )


def test_edit_uses_private_reference_and_variadic_separator(
    cli, monkeypatch, tmp_path, png, events, ready
):
    reference = tmp_path / "original.png"
    reference.write_bytes(png)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(cli, "_probe", lambda *args: ready)
    calls = []

    def run(command, directory, *, input_bytes):
        calls.append(command)
        (directory / cli.OUTPUT_NAME).write_bytes(png)
        return SimpleNamespace(returncode=0, stdout=events, stderr=b"")

    monkeypatch.setattr(cli, "run_cli_command", run)
    cli._render(
        {
            "binary": ready.binary,
            "version": ready.version,
            "prompt": "make it red",
            "reference": str(reference),
        },
        workspace,
    )
    assert calls[0][-4:] == ["-i", str(workspace / "reference.png"), "--", "-"]
    assert str(reference) not in calls[0]
    assert reference.read_bytes() == png


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"version": "0.153.3"}, "cli_binary_changed"),
        ({"binary": "/different/codex"}, "cli_binary_changed"),
        ({"auth_mode": "api"}, "cli_subscription_required"),
    ],
)
def test_render_rechecks_version_and_subscription(
    cli, monkeypatch, tmp_path, ready, updates, reason
):
    monkeypatch.setattr(cli, "_probe", lambda *args: replace(ready, **updates))
    monkeypatch.setattr(
        cli, "run_cli_command", lambda *a, **kw: pytest.fail("must not render")
    )
    with pytest.raises(cli.ImageLaneError, match=reason):
        cli._render(
            {
                "binary": ready.binary,
                "version": ready.version,
                "prompt": "image",
                "reference": None,
            },
            tmp_path,
        )


@pytest.mark.parametrize(
    "code,output,event_output,reason",
    [
        (55, b"valid", "valid", "cli_provider_failed"),
        (0, None, "valid", "cli_image_missing"),
        (0, b"not an image", "valid", "cli_image_invalid"),
        (0, b"valid", "invalid", "cli_events_invalid"),
        (0, b"valid", "failed", "cli_provider_failed"),
    ],
)
def test_failed_native_attempt_never_becomes_success_or_retry(
    cli, monkeypatch, tmp_path, ready, png, events, code, output, event_output, reason
):
    monkeypatch.setattr(cli, "_probe", lambda *args: ready)
    calls = []

    def run(command, workspace, *, input_bytes):
        calls.append(command)
        if output is not None:
            (workspace / cli.OUTPUT_NAME).write_bytes(
                png if output == b"valid" else output
            )
        data = (
            events
            if event_output == "valid"
            else (
                b'{"type":"turn.failed","error":{"message":"private provider error"}}'
                if event_output == "failed"
                else b"unstructured success"
            )
        )
        return SimpleNamespace(returncode=code, stdout=data, stderr=b"private details")

    monkeypatch.setattr(cli, "run_cli_command", run)
    with pytest.raises(cli.ImageLaneError, match=reason) as caught:
        cli._render(
            {
                "binary": ready.binary,
                "version": ready.version,
                "prompt": "image",
                "reference": None,
            },
            tmp_path,
        )
    assert len(calls) == 1
    assert "private" not in str(caught.value)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"[]",
        b"done",
        b'{"type":"turn.completed"}',
        b'{"type":"thread.started","type":"turn.completed"}',
        b'{"type":"thread.started","value":NaN}',
        b'{"type":"turn.started"}\n{"type":"thread.started"}\n{"type":"turn.completed"}',
        b'{"type":"thread.started"}\n{"type":"turn.started"}\n{"type":"item.completed"}\n{"type":"turn.completed"}',
    ],
)
def test_events_cannot_claim_completion_from_malformed_or_reordered_state(cli, data):
    with pytest.raises(cli.ImageLaneError, match="cli_events_invalid"):
        cli._completed_turn(data)


def test_completed_stream_cannot_continue_or_repeat(cli, events):
    cli._completed_turn(events)
    with pytest.raises(cli.ImageLaneError, match="cli_events_invalid"):
        cli._completed_turn(events + b'\n{"type":"turn.completed"}')


def test_installed_cli_pre_turn_item_diagnostics_are_counted_not_suppressed(cli):
    # Shape observed on 0.153.2 with a completed, exit-zero minimal CLI turn.
    # Diagnostic text is synthetic and must never leave the adapter.
    records = [
        {"type": "thread.started", "thread_id": "fixed"},
        {
            "type": "item.completed",
            "item": {"type": "error", "message": "synthetic-private-value"},
        },
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"type": "error", "message": "synthetic-private-value"},
        },
        {"type": "item.completed", "item": {"type": "agent_message", "text": "ready"}},
        {"type": "turn.completed", "usage": {}},
    ]
    assert (
        cli._completed_turn(b"\n".join(json.dumps(value).encode() for value in records))
        == 2
    )
    for event in ("error", "turn.failed"):
        failed = records[:3] + [{"type": event, "message": "synthetic-private-value"}]
        with pytest.raises(cli.ImageLaneError, match="cli_provider_failed") as caught:
            cli._completed_turn(
                b"\n".join(json.dumps(value).encode() for value in failed)
            )
        assert "synthetic-private-value" not in str(caught.value)


@pytest.mark.parametrize(
    "item_type", ["agent_message", "command_execution", "file_change"]
)
def test_non_diagnostic_items_before_turn_still_refuse(cli, item_type):
    records = [
        {"type": "thread.started"},
        {"type": "item.completed", "item": {"type": item_type}},
        {"type": "turn.started"},
        {"type": "turn.completed"},
    ]
    with pytest.raises(cli.ImageLaneError, match="cli_events_invalid"):
        cli._completed_turn(b"\n".join(json.dumps(value).encode() for value in records))


def test_output_digest_rejects_replaced_bytes(cli, tmp_path, png):
    (tmp_path / cli.OUTPUT_NAME).write_bytes(png)
    metadata = {
        "filename": cli.OUTPUT_NAME,
        "size": len(png),
        "width": 24,
        "height": 16,
        "sha256": "0" * 64,
        "warning_count": 0,
    }
    with pytest.raises(cli.ImageLaneError, match="cli_image_changed"):
        cli._decode_image(metadata, tmp_path)


def test_worker_owns_scratch_cleanup_on_success_and_refusal(cli, monkeypatch, png):
    seen = []
    fail = False

    def supervise(command, operation, generations, payload, limits, **kwargs):
        workspace = Path(payload["workspace"])
        seen.append(workspace)
        assert command[-1] == cli.WORKER_FLAG
        assert set(generations) == {"workspace"}
        (workspace / cli.OUTPUT_NAME).write_bytes(png)
        if fail:
            raise cli.SupervisorError("worker_timeout")
        return SimpleNamespace(
            payload={
                "filename": cli.OUTPUT_NAME,
                "size": len(png),
                "width": 24,
                "height": 16,
                "sha256": hashlib.sha256(png).hexdigest(),
                "warning_count": 0,
            }
        )

    monkeypatch.setattr(cli, "run_authenticated_worker", supervise)
    result = cli._worker(cli.RENDER_OPERATION, {})
    assert result.data == png
    assert not seen[-1].exists()
    fail = True
    with pytest.raises(cli.ImageLaneError, match="cli_worker_timeout"):
        cli._worker(cli.RENDER_OPERATION, {})
    assert not seen[-1].exists()


def test_worker_preserves_interrupt_and_cleans_scratch(cli, monkeypatch):
    seen = []

    def supervise(command, operation, generations, payload, limits, **kwargs):
        seen.append(Path(payload["workspace"]))
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_authenticated_worker", supervise)
    with pytest.raises(KeyboardInterrupt):
        cli._worker(cli.RENDER_OPERATION, {})
    assert not seen[0].exists()


@pytest.mark.parametrize(
    "updates,reference,reason",
    [
        ({"lane": "api"}, None, "invalid_cli_lane"),
        ({"served_model": "gpt-image-2-2026-04-21"}, None, "invalid_cli_lane"),
        ({"operation": "edit"}, None, "invalid_image_references"),
        ({}, "/fake/reference.png", "invalid_image_references"),
    ],
)
def test_public_render_rejects_incoherent_plan(cli, lane, updates, reference, reason):
    with pytest.raises(cli.ImageLaneError, match=reason):
        cli.render_codex(replace(lane, **updates), "image", reference_path=reference)


def test_public_render_dispatches_without_losing_the_requested_operation(
    cli, monkeypatch, lane, png
):
    calls = []
    expected = cli.CliImage(png, 24, 16, hashlib.sha256(png).hexdigest())

    def worker(operation, payload):
        calls.append((operation, payload))
        return expected

    monkeypatch.setattr(cli, "_worker", worker)
    assert cli.render_codex(lane, "image") == expected
    assert calls == [
        (
            cli.RENDER_OPERATION,
            {
                "binary": lane.binary,
                "version": lane.version,
                "prompt": "image",
                "reference": None,
            },
        )
    ]
