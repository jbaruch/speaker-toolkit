"""CLI pipe/resource outcomes against fake processes, never a vendor executable."""

import io
from pathlib import Path
import subprocess
import sys

import pytest

from conftest import SCRIPTS_ILL, _import_script


@pytest.fixture
def process_module():
    return _import_script(
        Path(SCRIPTS_ILL) / "image_cli_process.py", "image_cli_process"
    )


class InputSink(io.BytesIO):
    received = b""

    def close(self):
        if not self.closed:
            self.received = self.getvalue()
        super().close()


class FakeProcess:
    def __init__(self, stdout=b"image result", stderr=b"", returncode=0):
        self.stdin = InputSink()
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode

    def poll(self):
        return self.returncode


def test_command_retains_outputs_and_withholds_api_environment(
    process_module, monkeypatch, tmp_path
):
    child = FakeProcess(stderr=b"diagnostic")
    seen = {}

    def spawn(command, **kwargs):
        seen.update(command=command, **kwargs)
        return child

    monkeypatch.setenv("OPENAI_API_KEY", "fixture-only")
    monkeypatch.setenv("GEMINI_API_KEY", "fixture-only")
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "fixture-only")
    monkeypatch.setenv("IMAGE_TEST_SETTING", "kept")
    monkeypatch.setattr(process_module.subprocess, "Popen", spawn)
    result = process_module.run_cli_command(
        ["/fake/codex", "exec", "--", "-"], tmp_path, input_bytes=b"private prompt"
    )
    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        b"image result",
        b"diagnostic",
    )
    assert child.stdin.received == b"private prompt"
    assert seen["cwd"] == tmp_path
    assert not any(
        "API_KEY" in key or key == "CODEX_ACCESS_TOKEN" for key in seen["env"]
    )
    assert seen["env"]["IMAGE_TEST_SETTING"] == "kept"
    assert seen["close_fds"] is True
    assert all(pipe.closed for pipe in (child.stdin, child.stdout, child.stderr))
    # The worker's environment shaping does not change the caller environment.
    assert process_module.os.environ["OPENAI_API_KEY"] == "fixture-only"


@pytest.mark.parametrize("returncode", [1, 55, 137])
def test_failed_exit_is_returned_not_retried(
    process_module, monkeypatch, tmp_path, returncode
):
    calls = []

    def spawn(command, **kwargs):
        calls.append(command)
        return FakeProcess(returncode=returncode)

    monkeypatch.setattr(process_module.subprocess, "Popen", spawn)
    result = process_module.run_cli_command(["/fake/codex"], tmp_path)
    assert result.returncode == returncode
    assert len(calls) == 1


@pytest.mark.parametrize(
    "stream,constant,reason",
    [
        ("stdout", "CLI_STDOUT_BYTES", "cli_stdout_limit"),
        ("stderr", "CLI_STDERR_BYTES", "cli_stderr_limit"),
    ],
)
def test_output_overflow_refuses_even_after_child_exits(
    process_module, monkeypatch, tmp_path, stream, constant, reason
):
    child = FakeProcess(
        stdout=b"12345" if stream == "stdout" else b"",
        stderr=b"12345" if stream == "stderr" else b"",
    )
    monkeypatch.setattr(process_module, constant, 4)
    monkeypatch.setattr(process_module.subprocess, "Popen", lambda *a, **kw: child)
    with pytest.raises(process_module.CliProcessError, match=reason):
        process_module.run_cli_command(["/fake/codex"], tmp_path)
    assert all(pipe.closed for pipe in (child.stdin, child.stdout, child.stderr))


def test_oversized_input_does_not_spawn(process_module, monkeypatch, tmp_path):
    monkeypatch.setattr(process_module, "CLI_STDIN_BYTES", 4)
    monkeypatch.setattr(
        process_module.subprocess,
        "Popen",
        lambda *a, **kw: pytest.fail("must not spawn"),
    )
    with pytest.raises(process_module.CliProcessError, match="cli_stdin_limit"):
        process_module.run_cli_command(["/fake/codex"], tmp_path, input_bytes=b"12345")


@pytest.mark.parametrize("error", [OSError("private"), ValueError("private")])
def test_spawn_failure_is_redacted(process_module, monkeypatch, tmp_path, error):
    def spawn(*args, **kwargs):
        raise error

    monkeypatch.setattr(process_module.subprocess, "Popen", spawn)
    with pytest.raises(
        process_module.CliProcessError, match="cli_start_failed"
    ) as caught:
        process_module.run_cli_command(["/fake/codex"], tmp_path)
    assert "private" not in str(caught.value)


def test_thread_start_failure_closes_every_pipe(process_module, monkeypatch, tmp_path):
    child = FakeProcess()
    monkeypatch.setattr(process_module.subprocess, "Popen", lambda *a, **kw: child)

    def cannot_start(self):
        raise RuntimeError("private thread error")

    monkeypatch.setattr(process_module._PipeDrainer, "start", cannot_start)
    with pytest.raises(process_module.CliProcessError, match="cli_pipe_failed"):
        process_module.run_cli_command(["/fake/codex"], tmp_path)
    assert all(pipe.closed for pipe in (child.stdin, child.stdout, child.stderr))


@pytest.mark.parametrize(
    "constant,value,setup",
    [
        ("WORKSPACE_MAX_BYTES", 2, "bytes"),
        ("WORKSPACE_MAX_ENTRIES", 1, "entries"),
        ("WORKSPACE_MAX_DEPTH", 0, "depth"),
    ],
)
def test_workspace_growth_refuses(
    process_module, monkeypatch, tmp_path, constant, value, setup
):
    if setup == "bytes":
        (tmp_path / "image.png").write_bytes(b"123")
    elif setup == "entries":
        (tmp_path / "one").touch()
        (tmp_path / "two").touch()
    else:
        (tmp_path / "nested").mkdir()
    monkeypatch.setattr(process_module, constant, value)
    with pytest.raises(process_module.CliProcessError, match="cli_workspace_limit"):
        process_module.check_workspace(tmp_path)


def test_workspace_accepts_small_regular_nested_outputs(process_module, tmp_path):
    (tmp_path / "scratch").mkdir()
    (tmp_path / "scratch" / "artifact").write_bytes(b"fixed")
    process_module.check_workspace(tmp_path)


def test_workspace_refuses_non_directory_root(process_module, tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"fixed")
    with pytest.raises(process_module.CliProcessError, match="cli_workspace_invalid"):
        process_module.check_workspace(image)


def test_fake_cli_reads_stdin_and_writes_bounded_pipes(
    process_module, monkeypatch, tmp_path
):
    real_spawn = subprocess.Popen

    def fake_cli(command, **kwargs):
        assert command == ["/fake/codex", "exec", "--", "-"]
        return real_spawn(
            [
                sys.executable,
                "-c",
                "import sys; data=sys.stdin.buffer.read(); "
                "sys.stdout.buffer.write(data.upper()); sys.stderr.write('fake only')",
            ],
            **kwargs,
        )

    monkeypatch.setattr(process_module.subprocess, "Popen", fake_cli)
    result = process_module.run_cli_command(
        ["/fake/codex", "exec", "--", "-"], tmp_path, input_bytes=b"fixture"
    )
    assert result.stdout == b"FIXTURE"
    assert result.stderr == b"fake only"
    assert result.returncode == 0


def test_stop_escalates_and_bounds_waits(process_module):
    events = []

    class Stubborn:
        def poll(self):
            return None

        def terminate(self):
            events.append("terminate")

        def wait(self, timeout):
            events.append(("wait", timeout))
            if "kill" not in events:
                raise subprocess.TimeoutExpired("fake", timeout)

        def kill(self):
            events.append("kill")

    process_module._stop(Stubborn())
    assert events == [
        "terminate",
        ("wait", process_module.PIPE_JOIN_SECONDS),
        "kill",
        ("wait", process_module.PIPE_JOIN_SECONDS),
    ]
