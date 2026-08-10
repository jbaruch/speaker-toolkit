"""Security and resource-boundary tests for artifact_supervisor.py."""

from __future__ import annotations

import ctypes
import importlib
import io
import json
import os
import select
import struct
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import psutil
import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "vault-ingress"
    / "scripts"
    / "artifact_supervisor.py"
)
SCRIPT_DIR = SCRIPT.parent
script_dir = os.fspath(SCRIPT_DIR)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
artifact_supervisor = importlib.import_module("artifact_supervisor")


WORKER_CODE = f"""
import base64
import dataclasses
import hashlib
import hmac
import json
import os
import struct
import subprocess
import sys
import threading
sys.path.insert(0, {str(SCRIPT_DIR)!r})
import artifact_supervisor as supervisor

request = supervisor.read_worker_request()
mode = request.payload.get("mode")
protocol = supervisor.isolate_protocol_output()

def valid_frame(payload):
    buffer = __import__("io").BytesIO()
    supervisor.write_worker_response(
        request,
        payload=payload,
        observed_generations=request.expected_generations,
        stream=buffer,
    )
    return buffer.getvalue()

def signed_body(
    body_bytes,
    *,
    authenticated=True,
    bindings_bytes=None,
    observed_generations=None,
):
    expected = {{
        name: value.to_dict() for name, value in request.expected_generations.items()
    }}
    observed = expected if observed_generations is None else observed_generations
    if bindings_bytes is None:
        bindings_bytes = supervisor._canonical_json({{
            "expected_generations": expected,
            "observed_generations": observed,
        }})
    unsigned = {{
        "protocol": supervisor.PROTOCOL_VERSION,
        "request_id": request.request_id,
        "operation": request.operation,
        "request_sha256": request.request_sha256,
        "limit_profile_id": request.limit_profile_id,
        "schema_generation": request.schema_generation,
        "pipeline_generation": request.pipeline_generation,
        "ok": True,
        "bindings_sha256": hashlib.sha256(bindings_bytes).hexdigest(),
        "bindings_b64": base64.b64encode(bindings_bytes).decode("ascii"),
        "body_sha256": hashlib.sha256(body_bytes).hexdigest(),
        "body_b64": base64.b64encode(body_bytes).decode("ascii"),
    }}
    signature = hmac.new(
        request.key,
        supervisor._canonical_json(unsigned),
        hashlib.sha256,
    ).hexdigest()
    unsigned["hmac_sha256"] = signature if authenticated else "0" * 64
    encoded = supervisor._canonical_json(unsigned)
    return struct.pack(">I", len(encoded)) + encoded

if mode == "success":
    artifact = request.payload["artifact"]
    leaked = any(artifact in value for value in sys.argv)
    leaked = leaked or any(
        artifact in name or artifact in value for name, value in os.environ.items()
    )
    print("parser diagnostic at /private/source/deck.pptx", flush=True)
    supervisor.write_worker_response(
        request,
        payload={{
            "leaked": leaked,
            "profile": request.limit_profile_id,
            "schema": request.schema_generation,
            "pipeline": request.pipeline_generation,
        }},
        observed_generations=request.expected_generations,
        stream=protocol,
    )
elif mode == "wrong_auth":
    frame = bytearray(valid_frame({{"value": 1}}))
    document = json.loads(frame[4:])
    document["hmac_sha256"] = "0" * 64
    encoded = supervisor._canonical_json(document)
    protocol.write(struct.pack(">I", len(encoded)) + encoded)
elif mode == "wrong_binding":
    altered = dataclasses.replace(
        request,
        pipeline_generation=request.pipeline_generation + ".other",
    )
    supervisor.write_worker_response(
        altered,
        payload={{"value": 1}},
        observed_generations=altered.expected_generations,
        stream=protocol,
    )
elif mode == "changed_generation":
    observed = dict(request.expected_generations)
    name = next(iter(observed))
    observed[name] = dataclasses.replace(observed[name], size=observed[name].size + 1)
    supervisor.write_worker_response(
        request,
        payload={{"value": 1}},
        observed_generations=observed,
        stream=protocol,
    )
elif mode == "signed_duplicate_body":
    protocol.write(signed_body(b'{{"payload":{{"x":1,"x":2}}}}'))
elif mode == "signed_nonfinite_body":
    protocol.write(signed_body(b'{{"payload":NaN}}'))
elif mode == "signed_deep_body":
    body = b'{{"payload":' + b'[' * 70 + b'0' + b']' * 70 + b'}}'
    protocol.write(signed_body(body))
elif mode == "signed_duplicate_bindings":
    bindings = (
        b'{{"expected_generations":{{}},"expected_generations":{{}},'
        b'"observed_generations":{{}}}}'
    )
    protocol.write(signed_body(b'{{"payload":{{}}}}', bindings_bytes=bindings))
elif mode == "signed_nonfinite_bindings":
    bindings = b'{{"expected_generations":NaN,"observed_generations":{{}}}}'
    protocol.write(signed_body(b'{{"payload":{{}}}}', bindings_bytes=bindings))
elif mode == "signed_deep_bindings":
    nested = b'[' * 70 + b'0' + b']' * 70
    bindings = (
        b'{{"expected_generations":' + nested + b',"observed_generations":{{}}}}'
    )
    protocol.write(signed_body(b'{{"payload":{{}}}}', bindings_bytes=bindings))
elif mode == "unauthenticated_invalid_body":
    protocol.write(
        signed_body(b'{{"payload":{{"x":1,"x":2}}}}', authenticated=False)
    )
elif mode == "unauthenticated_nonfinite_body":
    protocol.write(signed_body(b'{{"payload":NaN}}', authenticated=False))
elif mode == "unauthenticated_deep_body":
    body = b'{{"payload":' + b'[' * 70 + b'0' + b']' * 70 + b'}}'
    protocol.write(signed_body(body, authenticated=False))
elif mode == "unauthenticated_invalid_bindings":
    bindings = (
        b'{{"expected_generations":{{}},"expected_generations":{{}},'
        b'"observed_generations":{{}}}}'
    )
    protocol.write(
        signed_body(
            b'{{"payload":{{}}}}',
            authenticated=False,
            bindings_bytes=bindings,
        )
    )
elif mode == "unauthenticated_nonfinite_bindings":
    bindings = b'{{"expected_generations":NaN,"observed_generations":{{}}}}'
    protocol.write(
        signed_body(
            b'{{"payload":{{}}}}',
            authenticated=False,
            bindings_bytes=bindings,
        )
    )
elif mode == "unauthenticated_deep_bindings":
    nested = b'[' * 70 + b'0' + b']' * 70
    bindings = (
        b'{{"expected_generations":' + nested + b',"observed_generations":{{}}}}'
    )
    protocol.write(
        signed_body(
            b'{{"payload":{{}}}}',
            authenticated=False,
            bindings_bytes=bindings,
        )
    )
elif mode == "changed_generation_invalid_body":
    observed = {{
        name: value.to_dict() for name, value in request.expected_generations.items()
    }}
    name = next(iter(observed))
    observed[name]["size"] += 1
    protocol.write(
        signed_body(
            b'{{"payload":{{"x":1,"x":2}}}}',
            observed_generations=observed,
        )
    )
elif mode == "partial":
    protocol.write(b"\\x00\\x00\\x00\\x10{{}}")
elif mode == "trailing":
    protocol.write(valid_frame({{"value": 1}}) + b"trailing")
elif mode == "oversize":
    protocol.write(b"x" * 131072)
elif mode == "diagnostic_oversize":
    sys.stderr.buffer.write(b"x" * 131072)
    sys.stderr.buffer.flush()
    supervisor.write_worker_response(
        request,
        payload={{"value": 1}},
        observed_generations=request.expected_generations,
        stream=protocol,
    )
elif mode == "worker_error":
    supervisor.write_worker_response(
        request,
        error=supervisor.SupervisorError(
            "pptx_worker_unavailable",
            {{
                "artifact": request.payload["artifact"],
                "secret": request.key.hex(),
                request.payload["artifact"]: "artifact-key",
                request.key.hex(): "secret-key",
            }},
        ),
        observed_generations=request.expected_generations,
        stream=protocol,
    )
elif mode == "timeout":
    threading.Event().wait()
elif mode == "spawn_tree":
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import threading; threading.Event().wait()",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with open(request.payload["pid_receipt"], "w", encoding="ascii") as receipt:
        receipt.write(str(child.pid))
    with open(request.payload["ready_fifo"], "wb", buffering=0) as ready:
        ready.write(b"1")
    threading.Event().wait()
elif mode == "spawn_group_success":
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import threading; threading.Event().wait()",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with open(request.payload["pid_receipt"], "w", encoding="ascii") as receipt:
        receipt.write(str(child.pid))
    with open(request.payload["ready_fifo"], "wb", buffering=0) as ready:
        ready.write(b"1")
    with open(request.payload["release_fifo"], "rb", buffering=0) as release:
        if release.read(1) != b"1":
            raise RuntimeError("test release handshake failed")
    supervisor.write_worker_response(
        request,
        payload={{"child_pid": child.pid}},
        observed_generations=request.expected_generations,
        stream=protocol,
    )
    protocol.flush()
    protocol.close()
    with open(request.payload["done_fifo"], "wb", buffering=0) as done:
        done.write(b"1")
    raise SystemExit(0)
elif mode == "fast_exit":
    raise RuntimeError("synthetic worker failure")
else:
    raise RuntimeError("unknown test mode")
protocol.flush()
protocol.close()
"""


class PermissiveMonitor:
    """Deterministic test monitor; production psutil behavior is unit-tested below."""

    def __init__(self, _pid, _limits):
        pass

    def establish(self):
        return None

    def sample(self):
        return (1, 1)

    def has_live_descendants(self):
        return False

    def kill_seen(self, _timeout=0.5):
        return None

    def any_seen_alive(self):
        return False


class IdentityLossMonitor(PermissiveMonitor):
    """Monitor that always reports the worker's process identity changed."""

    def sample(self):
        raise artifact_supervisor.SupervisorError("worker_monitor_identity_changed")


class ScriptedProcess:
    """Popen stand-in whose exit becomes observable at a chosen call.

    Exit-versus-monitor precedence depends on when the exit is observed, never
    on how long a real interpreter takes to start and die.  ``exit_on_poll``
    names the 1-based ``poll()`` call that first reports the exit, and
    ``exits_during_wait`` decides whether the supervisor's bounded settle wait
    confirms one, so each observation order is chosen instead of raced.
    """

    pid = 4242

    def __init__(self, *, exit_code=1, exit_on_poll=None, exits_during_wait=False):
        self.returncode = None
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
        self.wait_timeouts: list[float] = []
        self.killed = False
        self._exit_code = exit_code
        self._exit_on_poll = exit_on_poll
        self._exits_during_wait = exits_during_wait
        self._polls = 0

    def poll(self):
        self._polls += 1
        if self.returncode is None and self._polls == self._exit_on_poll:
            self.returncode = self._exit_code
        return self.returncode

    def wait(self, timeout: float = 0.0):
        self.wait_timeouts.append(timeout)
        if self.returncode is None:
            if not self._exits_during_wait:
                raise subprocess.TimeoutExpired("worker", timeout)
            self.returncode = self._exit_code
        return self.returncode

    def kill(self):
        self.killed = True
        if self.returncode is None:
            self.returncode = self._exit_code


class TerminatingController:
    """Controller stand-in that kills only a worker still reported as live."""

    def __init__(self, process, _limits):
        self.process = process

    def establish(self):
        return None

    def terminate(self, _timeout=None):
        if self.process.poll() is None:
            self.process.kill()

    def close(self):
        return None


def _generation():
    return artifact_supervisor.FileGeneration(
        size=123,
        mtime_ns=456,
        ctime_ns=789,
        device=10,
        inode=11,
        mode=0o100600,
        flags=0x40000000,
        file_attributes=None,
    )


def _limits(**overrides):
    values = {
        "profile_id": "pptx-probe-v1",
        "wall_seconds": 5.0,
        "max_memory_bytes": 512 * 1024 * 1024,
        "max_input_bytes": 64 * 1024,
        "max_output_bytes": 64 * 1024,
        "max_diagnostic_bytes": 4 * 1024,
        "max_processes": 8,
        "sample_interval_seconds": 0.01,
        "cleanup_seconds": 2.0,
    }
    values.update(overrides)
    return artifact_supervisor.SupervisorLimits(**values)


def _frozen_clock() -> float:
    """Default supervisor clock for tests that never exercise the wall deadline."""
    return 0.0


def _read_fifo_signal(fd: int) -> None:
    # Block on the event, never on a duration. A real-time bound here decides
    # the test's outcome by runner speed: a stalled runner misses the deadline
    # and reports a handshake failure that never happened. A worker that truly
    # never signals is a hang the job's own timeout catches, which is a louder
    # and more honest signal than a false assertion failure.
    select.select([fd], [], [])
    assert os.read(fd, 1) == b"1"


def _run(
    mode,
    *,
    limits=None,
    payload=None,
    monitor_factory=None,
    process_backend=None,
    credentials=None,
    clock=None,
    sleeper=None,
):
    """Run one worker under an injected clock.

    The clock defaults to a frozen reading so no assertion can be preempted by
    the wall deadline on a loaded runner.  Tests that exercise the deadline
    itself pass an advancing clock of their own.
    """

    request_payload = {"mode": mode}
    if payload:
        request_payload.update(payload)
    return artifact_supervisor.run_authenticated_worker(
        [sys.executable, "-c", WORKER_CODE],
        "probe",
        {"pptx": _generation()},
        request_payload,
        limits or _limits(),
        credentials=credentials,
        schema_generation=3,
        pipeline_generation="1.2.0",
        process_backend=process_backend,
        monitor_factory=monitor_factory or PermissiveMonitor,
        clock=clock if clock is not None else _frozen_clock,
        sleeper=sleeper,
    )


def test_artifact_consumers_reuse_one_supervisor_module_identity(
    artifact_metadata,
    pdf_evidence,
    pptx_evidence,
    video_evidence,
) -> None:
    assert artifact_supervisor is sys.modules["artifact_supervisor"]
    assert artifact_metadata.FileGeneration is artifact_supervisor.FileGeneration
    assert pdf_evidence.FileGeneration is artifact_supervisor.FileGeneration
    assert pptx_evidence.FileGeneration is artifact_supervisor.FileGeneration
    assert video_evidence.FileGeneration is artifact_supervisor.FileGeneration
    assert pdf_evidence.DiagnosticReceipt is artifact_supervisor.DiagnosticReceipt
    assert video_evidence.DiagnosticReceipt is artifact_supervisor.DiagnosticReceipt
    assert pdf_evidence.SupervisorError is artifact_supervisor.SupervisorError
    assert pptx_evidence.SupervisorError is artifact_supervisor.SupervisorError


def test_success_is_private_bound_and_returns_only_diagnostic_receipt(tmp_path):
    artifact = tmp_path / "private deck.pptx"
    result = _run("success", payload={"artifact": str(artifact)})

    assert result.payload == {
        "leaked": False,
        "pipeline": "1.2.0",
        "profile": "pptx-probe-v1",
        "schema": 3,
    }
    assert result.observed_generations == {"pptx": _generation()}
    assert result.diagnostics.byte_count > 0
    assert len(result.diagnostics.sha256) == 64
    assert result.diagnostics.truncated is False
    assert not hasattr(result.diagnostics, "text")
    assert str(artifact) not in repr(result.diagnostics)


def test_production_monitor_smoke_uses_real_process_tree(tmp_path):
    """Exercise the installed psutil monitor instead of the deterministic fake."""
    artifact = tmp_path / "production-monitor.pptx"

    result = artifact_supervisor.run_authenticated_worker(
        [sys.executable, "-c", WORKER_CODE],
        "probe",
        {"pptx": _generation()},
        {"mode": "success", "artifact": str(artifact)},
        _limits(),
        schema_generation=3,
        pipeline_generation="1.2.0",
        clock=_frozen_clock,
    )

    assert result.payload == {
        "leaked": False,
        "pipeline": "1.2.0",
        "profile": "pptx-probe-v1",
        "schema": 3,
    }
    assert result.observed_generations == {"pptx": _generation()}


@pytest.mark.parametrize(
    ("mode", "reason_code"),
    [
        ("wrong_auth", "worker_response_authentication_failed"),
        ("wrong_binding", "worker_response_binding_mismatch"),
        ("changed_generation", "worker_generation_changed"),
        ("signed_duplicate_body", "invalid_worker_response_body"),
        ("signed_nonfinite_body", "invalid_worker_response_body"),
        ("signed_deep_body", "invalid_worker_response"),
        ("signed_duplicate_bindings", "invalid_worker_response_bindings"),
        ("signed_nonfinite_bindings", "invalid_worker_response_bindings"),
        ("signed_deep_bindings", "invalid_worker_response_bindings"),
        ("partial", "invalid_worker_response"),
        ("trailing", "invalid_worker_response"),
    ],
)
def test_invalid_responses_fail_closed(mode, reason_code):
    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(mode)

    assert caught.value.reason_code == reason_code


@pytest.mark.parametrize(
    "mode",
    [
        "unauthenticated_invalid_body",
        "unauthenticated_nonfinite_body",
        "unauthenticated_deep_body",
        "unauthenticated_invalid_bindings",
        "unauthenticated_nonfinite_bindings",
        "unauthenticated_deep_bindings",
    ],
)
def test_response_authentication_precedes_nested_decode(mode):
    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(mode)

    assert caught.value.reason_code == "worker_response_authentication_failed"


def test_generation_mismatch_precedes_nested_body_decode():
    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run("changed_generation_invalid_body")

    assert caught.value.reason_code == "worker_generation_changed"
    assert caught.value.details == {"generation_names": ["pptx"]}


def test_outer_response_parser_is_shallow_fixed_and_capped(monkeypatch):
    def recursive_decode_forbidden(*_args, **_kwargs):
        raise AssertionError("outer parser must not call recursive JSON decoding")

    monkeypatch.setattr(artifact_supervisor.json, "loads", recursive_decode_forbidden)
    deeply_nested = b"[" * 10_000 + b"0" + b"]" * 10_000
    forged_unknown = b'{"unknown":' + deeply_nested + b"}"
    forged_known = b'{"body_b64":' + deeply_nested + b"}"

    for payload in (forged_unknown, forged_known):
        with pytest.raises(ValueError):
            artifact_supervisor._strict_response_envelope(payload, len(payload))

    oversized_name = b'{"operation":"' + b"x" * 65 + b'"}'
    with pytest.raises(ValueError, match="field limit"):
        artifact_supervisor._strict_response_envelope(
            oversized_name,
            len(oversized_name),
        )

    malformed_scalars = (
        b'{"ok":true,"ok":false}',
        b'{"schema_generation":NaN}',
        b'{"schema_generation":' + b"9" * 33 + b"}",
    )
    for payload in malformed_scalars:
        with pytest.raises(ValueError):
            artifact_supervisor._strict_response_envelope(payload, len(payload))


def test_output_and_diagnostic_caps_are_enforced():
    with pytest.raises(artifact_supervisor.SupervisorError) as output_error:
        _run("oversize", limits=_limits(max_output_bytes=512))
    assert output_error.value.reason_code == "worker_output_limit_exceeded"

    with pytest.raises(artifact_supervisor.SupervisorError) as diagnostic_error:
        _run("diagnostic_oversize", limits=_limits(max_diagnostic_bytes=128))
    assert diagnostic_error.value.reason_code == "worker_diagnostic_limit_exceeded"
    assert diagnostic_error.value.diagnostics.byte_count == 131072
    assert diagnostic_error.value.diagnostics.truncated is True


def test_worker_error_redacts_paths_and_authentication_key(tmp_path):
    artifact = tmp_path / "sensitive.pptx"
    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run("worker_error", payload={"artifact": str(artifact)})

    assert caught.value.reason_code == "pptx_worker_unavailable"
    assert str(artifact) not in json.dumps(caught.value.details)
    assert caught.value.details.get("artifact") == "<redacted>"
    assert caught.value.details.get("secret") == "<redacted>"
    assert set(caught.value.details) == {
        "artifact",
        "secret",
        "<redacted>",
        "<redacted>#2",
    }
    assert {
        caught.value.details["<redacted>"],
        caught.value.details["<redacted>#2"],
    } == {"artifact-key", "secret-key"}


def test_wall_limit_terminates_worker_with_controlled_clock(monkeypatch):
    class Clock:
        value = 0.0

        def monotonic(self):
            return self.value

    class Process:
        pid = 4242
        returncode = None

        def __init__(self):
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()
            self.killed = False

        def poll(self):
            return self.returncode

        def kill(self):
            self.killed = True
            self.returncode = -9

        def wait(self, timeout=None):
            assert timeout is not None
            return self.returncode

    class Controller:
        instances = []

        def __init__(self, process, _limits):
            self.process = process
            self.established = False
            self.terminated = False
            self.closed = False
            self.instances.append(self)

        def establish(self):
            self.established = True

        def terminate(self, _timeout=None):
            self.terminated = True
            self.process.kill()

        def close(self):
            self.closed = True

    class Monitor(PermissiveMonitor):
        instance = None

        def __init__(self, _pid, _limits):
            self.killed = False
            type(self).instance = self

        def sample(self):
            clock.value = 1.0
            return (1, 1)

        def kill_seen(self, _timeout=0.5):
            self.killed = True

    clock = Clock()
    process = Process()
    monkeypatch.setattr(artifact_supervisor, "_ProcessController", Controller)

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(
            "timeout",
            limits=_limits(wall_seconds=0.5),
            process_backend=lambda *_args, **_kwargs: process,
            monitor_factory=Monitor,
            credentials=artifact_supervisor.WorkerCredentials(b"k" * 32),
            clock=clock.monotonic,
            sleeper=lambda _seconds: None,
        )

    assert caught.value.reason_code == "worker_timeout"
    assert process.killed is True
    assert Controller.instances[0].established is True
    assert Controller.instances[0].terminated is True
    assert Controller.instances[0].closed is True
    assert Monitor.instance is not None and Monitor.instance.killed is True


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group assertion")
def test_timeout_kills_descendant_process_group_without_polling(tmp_path):
    receipt = tmp_path / "child.pid"
    ready_fifo = tmp_path / "ready.fifo"
    os.mkfifo(ready_fifo)
    ready_fd = os.open(ready_fifo, os.O_RDWR | os.O_NONBLOCK)

    class Clock:
        def __init__(self):
            self._value = 0.0
            self._lock = threading.Lock()

        def monotonic(self):
            with self._lock:
                return self._value

        def expire(self):
            with self._lock:
                self._value = 1.0

    clock = Clock()
    monitors = []

    class HandshakeMonitor(artifact_supervisor._ProcessTreeMonitor):
        def __init__(self, pid, limits):
            super().__init__(pid, limits)
            self._baseline_sampled = False
            self.handshake_complete = False
            monitors.append(self)

        def sample(self):
            if not self._baseline_sampled:
                observed = super().sample()
                self._baseline_sampled = True
                return observed
            _read_fifo_signal(ready_fd)
            observed = super().sample()
            self.handshake_complete = True
            clock.expire()
            return observed

    try:
        with pytest.raises(artifact_supervisor.SupervisorError) as caught:
            _run(
                "spawn_tree",
                limits=_limits(wall_seconds=0.5),
                payload={
                    "pid_receipt": str(receipt),
                    "ready_fifo": str(ready_fifo),
                },
                monitor_factory=HandshakeMonitor,
                credentials=artifact_supervisor.WorkerCredentials(b"k" * 32),
                clock=clock.monotonic,
                sleeper=lambda _seconds: None,
            )
    finally:
        os.close(ready_fd)

    assert caught.value.reason_code == "worker_timeout"
    assert int(receipt.read_text(encoding="ascii")) > 0
    assert monitors[0].handshake_complete is True
    assert monitors[0].any_seen_alive() is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group assertion")
def test_reaped_workers_never_signal_a_stale_numeric_process_group(monkeypatch):
    attempted_groups: list[tuple[int, int]] = []

    def signal_stale_group(process_group: int, signal_number: int) -> None:
        attempted_groups.append((process_group, signal_number))
        raise AssertionError("a reaped worker has no safe process-group identity")

    class ReapedProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def poll(self):
            return 0

        def kill(self):
            raise AssertionError("a reaped worker must not be killed by PID")

    monkeypatch.setattr(artifact_supervisor.os, "killpg", signal_stale_group)

    for pid in range(50_000, 50_256):
        artifact_supervisor._ProcessController(
            ReapedProcess(pid),
            _limits(),
        ).terminate()

    assert attempted_groups == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group assertion")
def test_group_kill_winning_pid_kill_race_is_successful_cleanup(monkeypatch):
    attempted_groups: list[tuple[int, int]] = []

    def kill_group(process_group: int, signal_number: int) -> None:
        attempted_groups.append((process_group, signal_number))

    class ExitedAfterGroupKill:
        pid = 12345

        def poll(self):
            return None

        def kill(self):
            raise ProcessLookupError("group kill already reaped the child")

    monkeypatch.setattr(artifact_supervisor.os, "killpg", kill_group)

    artifact_supervisor._ProcessController(
        ExitedAfterGroupKill(),
        _limits(),
    ).terminate()

    assert attempted_groups == [(12345, artifact_supervisor.signal.SIGKILL)]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group assertion")
def test_group_kill_permission_race_after_root_exit_is_successful(monkeypatch):
    attempted_groups: list[tuple[int, int]] = []

    def deny_disappearing_group(process_group: int, signal_number: int) -> None:
        attempted_groups.append((process_group, signal_number))
        raise PermissionError("the child exited before its group was signalled")

    class ExitedDuringGroupKill:
        pid = 12345

        def __init__(self) -> None:
            self.returncode = None
            self.wait_timeouts: list[float] = []

        def poll(self):
            return self.returncode

        def wait(self, *, timeout):
            self.wait_timeouts.append(timeout)
            self.returncode = 0
            return self.returncode

        def kill(self):
            raise AssertionError("a confirmed exited worker must not be killed")

    monkeypatch.setattr(artifact_supervisor.sys, "platform", "darwin")
    monkeypatch.setattr(
        artifact_supervisor.os,
        "killpg",
        deny_disappearing_group,
    )

    process = ExitedDuringGroupKill()
    limits = _limits()
    settle_budget = limits.sample_interval_seconds / 2
    artifact_supervisor._ProcessController(process, limits).terminate(settle_budget)

    assert attempted_groups == [(12345, artifact_supervisor.signal.SIGKILL)]
    assert process.wait_timeouts == [settle_budget]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group assertion")
def test_group_kill_permission_error_for_live_root_remains_visible(monkeypatch):
    def deny_live_group(_process_group: int, _signal_number: int) -> None:
        raise PermissionError("live group cannot be signalled")

    class LiveProcess:
        pid = 12345

        def __init__(self) -> None:
            self.killed = False

        def poll(self):
            return None

        def wait(self, *, timeout):
            raise subprocess.TimeoutExpired("worker", timeout)

        def kill(self):
            self.killed = True

    process = LiveProcess()
    monkeypatch.setattr(artifact_supervisor.sys, "platform", "darwin")
    monkeypatch.setattr(artifact_supervisor.os, "killpg", deny_live_group)

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        artifact_supervisor._ProcessController(process, _limits()).terminate()

    assert caught.value.reason_code == "worker_cleanup_failed"
    assert isinstance(caught.value.__cause__, PermissionError)
    assert process.killed is True


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-tree assertion")
def test_clean_exit_reports_and_kills_known_descendant_with_handshake(tmp_path):
    receipt = tmp_path / "child.pid"
    ready_fifo = tmp_path / "ready.fifo"
    release_fifo = tmp_path / "release.fifo"
    done_fifo = tmp_path / "done.fifo"
    os.mkfifo(ready_fifo)
    os.mkfifo(release_fifo)
    os.mkfifo(done_fifo)
    ready_fd = os.open(ready_fifo, os.O_RDWR | os.O_NONBLOCK)
    release_fd = os.open(release_fifo, os.O_RDWR | os.O_NONBLOCK)
    done_fd = os.open(done_fifo, os.O_RDWR | os.O_NONBLOCK)
    monitors = []
    processes = []

    def spawn_process(*args, **kwargs):
        process = subprocess.Popen(*args, **kwargs)
        processes.append(process)
        return process

    class HandshakeMonitor(artifact_supervisor._ProcessTreeMonitor):
        def __init__(self, pid, limits):
            super().__init__(pid, limits)
            self._baseline_sampled = False
            self.handshake_complete = False
            monitors.append(self)

        def sample(self):
            if not self._baseline_sampled:
                observed = super().sample()
                self._baseline_sampled = True
                return observed
            if not self.handshake_complete:
                _read_fifo_signal(ready_fd)
                observed = super().sample()
                assert os.write(release_fd, b"1") == 1
                _read_fifo_signal(done_fd)
                assert processes[0].wait() == 0
                self.handshake_complete = True
                return observed
            return super().sample()

    try:
        with pytest.raises(artifact_supervisor.SupervisorError) as caught:
            _run(
                "spawn_group_success",
                payload={
                    "pid_receipt": str(receipt),
                    "ready_fifo": str(ready_fifo),
                    "release_fifo": str(release_fifo),
                    "done_fifo": str(done_fifo),
                },
                limits=_limits(wall_seconds=0.5),
                monitor_factory=HandshakeMonitor,
                process_backend=spawn_process,
                credentials=artifact_supervisor.WorkerCredentials(b"k" * 32),
                clock=lambda: 0.0,
                sleeper=lambda _seconds: None,
            )
    finally:
        os.close(ready_fd)
        os.close(release_fd)
        os.close(done_fd)

    assert caught.value.reason_code == "worker_process_tree_leak"
    assert int(receipt.read_text(encoding="ascii")) > 0
    assert monitors[0].handshake_complete is True
    assert monitors[0].any_seen_alive() is False


def test_monitor_barrier_fails_before_request_delivery():
    class FailingMonitor:
        def __init__(self, _pid, _limits):
            pass

        def establish(self):
            raise artifact_supervisor.SupervisorError("worker_monitor_unavailable")

        def sample(self):
            raise AssertionError("sample must not run")

        def has_live_descendants(self):
            return False

        def kill_seen(self, _timeout=0.5):
            return None

        def any_seen_alive(self):
            return False

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run("success", monitor_factory=FailingMonitor)

    assert caught.value.reason_code == "worker_monitor_unavailable"


def test_monitor_barrier_failure_closes_all_raw_pipes(monkeypatch):
    class Stream(io.BytesIO):
        def __init__(self):
            super().__init__()
            self.write_count = 0

        def write(self, data):
            self.write_count += 1
            return super().write(data)

    class Process:
        pid = 4242
        returncode = None

        def __init__(self):
            self.stdin = Stream()
            self.stdout = Stream()
            self.stderr = Stream()

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

    class Controller:
        def __init__(self, process, _limits):
            self.process = process

        def establish(self):
            return None

        def terminate(self, _timeout=None):
            self.process.kill()

        def close(self):
            return None

    class FailingMonitor(PermissiveMonitor):
        def establish(self):
            raise artifact_supervisor.SupervisorError("worker_monitor_unavailable")

    process = Process()
    monkeypatch.setattr(artifact_supervisor, "_ProcessController", Controller)

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(
            "success",
            process_backend=lambda *_args, **_kwargs: process,
            monitor_factory=FailingMonitor,
            credentials=artifact_supervisor.WorkerCredentials(b"k" * 32),
            clock=lambda: 0.0,
        )

    assert caught.value.reason_code == "worker_monitor_unavailable"
    assert process.stdin.write_count == 0
    assert process.stdin.closed is True
    assert process.stdout.closed is True
    assert process.stderr.closed is True


def test_exited_worker_is_confirmed_by_popen_and_cleanup_does_not_mask(tmp_path):
    processes = []

    class ExitedBeforeSampleMonitor(PermissiveMonitor):
        def sample(self):
            # Block on the exit event, never on a duration (see
            # _read_fifo_signal): this asserts the precedence of a confirmed
            # exit, not how fast an interpreter can start and die.
            processes[-1].wait()
            raise artifact_supervisor.SupervisorError("worker_monitor_identity_changed")

    def record_process(*args, **kwargs):
        process = subprocess.Popen(*args, **kwargs)
        processes.append(process)
        return process

    artifact = tmp_path / "tiny-malformed.pptx"
    result = _run(
        "success",
        payload={"artifact": str(artifact)},
        monitor_factory=ExitedBeforeSampleMonitor,
        process_backend=record_process,
    )
    assert result.payload["leaked"] is False

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(
            "fast_exit",
            monitor_factory=ExitedBeforeSampleMonitor,
            process_backend=record_process,
        )
    assert caught.value.reason_code == "worker_exit"
    assert len(processes) == 2


def test_confirmed_exit_outranks_a_monitor_error_at_the_next_poll(monkeypatch):
    process = ScriptedProcess(exit_on_poll=2)
    monkeypatch.setattr(
        artifact_supervisor,
        "_ProcessController",
        TerminatingController,
    )

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(
            "fast_exit",
            process_backend=lambda *_args, **_kwargs: process,
            monitor_factory=IdentityLossMonitor,
            credentials=artifact_supervisor.WorkerCredentials(b"k" * 32),
            sleeper=lambda _seconds: None,
        )

    assert caught.value.reason_code == "worker_exit"
    # The re-poll already confirmed the exit, so no settle wait was charged.
    assert process.wait_timeouts[0] == 0
    assert process.killed is False


def test_confirmed_exit_outranks_a_monitor_error_inside_the_settle_window(monkeypatch):
    limits = _limits()
    process = ScriptedProcess(exits_during_wait=True)
    monkeypatch.setattr(
        artifact_supervisor,
        "_ProcessController",
        TerminatingController,
    )

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(
            "fast_exit",
            limits=limits,
            process_backend=lambda *_args, **_kwargs: process,
            monitor_factory=IdentityLossMonitor,
            credentials=artifact_supervisor.WorkerCredentials(b"k" * 32),
            sleeper=lambda _seconds: None,
        )

    assert caught.value.reason_code == "worker_exit"
    assert process.wait_timeouts[0] == limits.sample_interval_seconds
    assert process.killed is False


def test_monitor_identity_error_survives_a_settle_window_confirming_nothing(
    monkeypatch,
):
    limits = _limits()
    process = ScriptedProcess()
    monkeypatch.setattr(
        artifact_supervisor,
        "_ProcessController",
        TerminatingController,
    )

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(
            "fast_exit",
            limits=limits,
            process_backend=lambda *_args, **_kwargs: process,
            monitor_factory=IdentityLossMonitor,
            credentials=artifact_supervisor.WorkerCredentials(b"k" * 32),
            sleeper=lambda _seconds: None,
        )

    assert caught.value.reason_code == "worker_monitor_identity_changed"
    assert process.wait_timeouts[0] == limits.sample_interval_seconds
    assert process.killed is True


def test_monitor_identity_loss_does_not_accept_a_still_live_worker():
    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(
            "timeout",
            limits=_limits(sample_interval_seconds=0.02),
            monitor_factory=IdentityLossMonitor,
        )

    assert caught.value.reason_code == "worker_monitor_identity_changed"


def test_cleanup_failure_overrides_signed_success(tmp_path):
    class CleanupFailingMonitor:
        def __init__(self, _pid, _limits):
            pass

        def establish(self):
            return None

        def sample(self):
            return (1, 1)

        def has_live_descendants(self):
            return False

        def kill_seen(self, _timeout=0.5):
            raise artifact_supervisor.SupervisorError("worker_cleanup_failed")

        def any_seen_alive(self):
            return False

    artifact = tmp_path / "deck.pptx"
    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(
            "success",
            payload={"artifact": str(artifact)},
            monitor_factory=CleanupFailingMonitor,
        )

    assert caught.value.reason_code == "worker_cleanup_failed"
    assert caught.value.details == {"prior_reason_code": None}


def test_cleanup_steps_share_one_absolute_timeout_budget():
    observed: dict[str, float] = {}

    class Clock:
        def __init__(self):
            self._value = 0.0
            self._lock = threading.Lock()

        def monotonic(self):
            with self._lock:
                return self._value

        def advance(self, seconds):
            with self._lock:
                self._value += seconds

    clock = Clock()

    class Process:
        pid = 123

        def poll(self):
            return 0

        def wait(self, *, timeout):
            observed["wait"] = timeout
            clock.advance(min(0.01, timeout))
            return 0

    class Controller:
        def terminate(self, timeout: float = 0.0):
            observed["terminate"] = timeout
            return None

        def close(self):
            return None

    class Monitor:
        def kill_seen(self, timeout):
            observed["kill"] = timeout
            clock.advance(min(0.01, timeout))

        def any_seen_alive(self):
            return False

    class Pipe:
        alive = True

        def close(self):
            return None

        def join(self, timeout):
            observed["join"] = timeout
            clock.advance(min(0.01, timeout))
            self.alive = False

    pipe = Pipe()
    failure = artifact_supervisor._cleanup_invocation(
        Process(),
        Controller(),
        Monitor(),
        pipe,
        None,
        None,
        0.1,
        clock=clock.monotonic,
    )

    assert failure is None
    assert observed["terminate"] == pytest.approx(0.1)
    assert observed["wait"] == pytest.approx(0.1)
    assert observed["kill"] == pytest.approx(0.09)
    assert observed["join"] == pytest.approx(0.08)


def test_cleanup_deadline_reports_a_still_running_cleanup_thread(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    created_threads = []
    real_thread = threading.Thread
    main_thread_id = threading.get_ident()

    class Clock:
        main_calls = 0

        def monotonic(self):
            if threading.get_ident() != main_thread_id:
                return 0.0
            self.main_calls += 1
            if self.main_calls == 1:
                return 0.0
            # Block on the event, never on a duration (see _read_fifo_signal).
            entered.wait()
            return 1.0

    class Process:
        def poll(self):
            return 0

        def wait(self, *, timeout):
            return 0

    class Controller:
        def terminate(self, _timeout=None):
            entered.set()
            release.wait()

        def close(self):
            return None

    def thread_factory(*args, **kwargs):
        worker = real_thread(*args, **kwargs)
        created_threads.append(worker)
        return worker

    monkeypatch.setattr(
        artifact_supervisor,
        "threading",
        SimpleNamespace(Thread=thread_factory),
    )
    clock = Clock()
    try:
        failure = artifact_supervisor._cleanup_invocation(
            Process(),
            Controller(),
            None,
            None,
            None,
            None,
            0.05,
            clock=clock.monotonic,
        )
    finally:
        release.set()
        for worker in created_threads:
            # Released above, so this joins on the event (see _read_fifo_signal).
            worker.join()

    assert isinstance(failure, TimeoutError)
    assert entered.is_set()
    assert created_threads


@pytest.mark.parametrize("interrupt_type", [KeyboardInterrupt, SystemExit])
def test_cleanup_join_propagates_main_thread_interrupt(monkeypatch, interrupt_type):
    class InterruptingThread:
        def __init__(self, *, target, name, daemon):
            pass

        def start(self):
            return None

        def join(self, _timeout):
            raise interrupt_type

        def is_alive(self):
            return False

    monkeypatch.setattr(
        artifact_supervisor,
        "threading",
        SimpleNamespace(Thread=InterruptingThread),
    )
    with pytest.raises(interrupt_type):
        artifact_supervisor._cleanup_invocation(
            None,
            None,
            None,
            None,
            None,
            None,
            0.5,
            clock=lambda: 0.0,
        )


def test_cleanup_thread_start_failure_still_terminates_and_closes(monkeypatch):
    class FailingThread:
        def __init__(self, *, target, name, daemon):
            pass

        def start(self):
            raise RuntimeError("synthetic thread start failure")

    class Process:
        def __init__(self):
            self.killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    class Controller:
        def __init__(self, process):
            self.process = process
            self.terminated = False
            self.closed = False

        def terminate(self, _timeout=None):
            self.terminated = True
            self.process.kill()

        def close(self):
            self.closed = True

    class Monitor:
        def __init__(self):
            self.killed = False

        def kill_seen(self, timeout):
            assert timeout == 0.0
            self.killed = True

    class Pipe:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    process = Process()
    controller = Controller(process)
    monitor = Monitor()
    pipe = Pipe()
    monkeypatch.setattr(
        artifact_supervisor,
        "threading",
        SimpleNamespace(Thread=FailingThread),
    )

    failure = artifact_supervisor._cleanup_invocation(
        process,
        controller,
        monitor,
        pipe,
        None,
        None,
        0.5,
        clock=lambda: 0.0,
    )

    assert isinstance(failure, RuntimeError)
    assert process.killed is True
    assert controller.terminated is True
    assert controller.closed is True
    assert monitor.killed is True
    assert pipe.closed is True


def test_unexpected_cleanup_programming_error_propagates():
    class Process:
        def poll(self):
            return 0

        def wait(self, *, timeout):
            return 0

    class Controller:
        def terminate(self, _timeout=None):
            raise RuntimeError("synthetic programming error")

    with pytest.raises(RuntimeError, match="synthetic programming error"):
        artifact_supervisor._cleanup_invocation_before_deadline(
            Process(),
            Controller(),
            None,
            None,
            None,
            None,
            1.0,
            clock=lambda: 0.0,
        )


def test_late_pipe_overflow_after_cleanup_rejects_signed_success(
    tmp_path,
    monkeypatch,
):
    real_cleanup = artifact_supervisor._cleanup_invocation

    def cleanup_with_late_overflow(
        process,
        controller,
        monitor,
        writer,
        stdout_reader,
        stderr_reader,
        timeout,
        *,
        clock=None,
    ):
        result = real_cleanup(
            process,
            controller,
            monitor,
            writer,
            stdout_reader,
            stderr_reader,
            timeout,
            clock=clock,
        )
        assert stdout_reader is not None
        stdout_reader._overflow.set()
        return result

    monkeypatch.setattr(
        artifact_supervisor,
        "_cleanup_invocation",
        cleanup_with_late_overflow,
    )
    artifact = tmp_path / "deck.pptx"

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run("success", payload={"artifact": str(artifact)})

    assert caught.value.reason_code == "worker_output_limit_exceeded"


def test_memory_limit_is_established_before_stdin_is_written():
    class MemoryFailingMonitor(PermissiveMonitor):
        def establish(self):
            raise artifact_supervisor.SupervisorError(
                "worker_memory_limit_exceeded", {"limit_bytes": 1}
            )

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(
            "success",
            limits=_limits(),
            monitor_factory=MemoryFailingMonitor,
        )

    assert caught.value.reason_code == "worker_memory_limit_exceeded"


def test_request_reader_rejects_duplicate_nonfinite_trailing_and_partial_json():
    malformed_payloads = [
        b'{"protocol":"artifact-worker-v1","protocol":"artifact-worker-v1"}',
        b'{"value":NaN}',
        b"{} trailing",
    ]
    framed = [struct.pack(">I", len(value)) + value for value in malformed_payloads]
    framed.extend([b"\x00\x00", struct.pack(">I", 50) + b"{}"])

    for value in framed:
        with pytest.raises(artifact_supervisor.SupervisorError) as caught:
            artifact_supervisor.read_worker_request(io.BytesIO(value))
        assert caught.value.reason_code == "invalid_worker_request"


def test_protocol_integer_parsing_is_bounded():
    oversized_integer = b'{"value":' + b"9" * 33 + b"}"
    frame = struct.pack(">I", len(oversized_integer)) + oversized_integer

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        artifact_supervisor.read_worker_request(io.BytesIO(frame))

    assert caught.value.reason_code == "invalid_worker_request"


def test_request_input_cap_and_sensitive_argv_fail_before_process_start(tmp_path):
    with pytest.raises(artifact_supervisor.SupervisorError) as too_large:
        artifact_supervisor.run_authenticated_worker(
            [sys.executable, "-c", "raise AssertionError('must not start')"],
            "probe",
            {},
            {"value": "x" * 4096},
            _limits(max_input_bytes=512),
        )
    assert too_large.value.reason_code == "worker_input_limit_exceeded"

    artifact = tmp_path / "deck.pptx"
    with pytest.raises(artifact_supervisor.SupervisorError) as unsafe:
        artifact_supervisor.run_authenticated_worker(
            [sys.executable, "-c", "pass", str(artifact)],
            "probe",
            {},
            {"artifact": str(artifact)},
            _limits(),
        )
    assert unsafe.value.reason_code == "unsafe_worker_process_metadata"


def test_immutable_worker_identity_may_be_nested_below_sensitive_root(tmp_path):
    root = tmp_path / "Presentations"
    command = [
        str(root / ".venv" / "bin" / "python3"),
        str(root / "vault" / "worker.py"),
        "--worker",
    ]
    starts = []

    def fail_after_metadata_check(parts, **_kwargs):
        starts.append(parts)
        raise OSError("fixture stops before process creation")

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        artifact_supervisor.run_authenticated_worker(
            command,
            "probe",
            {},
            {"root_path": str(root)},
            _limits(),
            immutable_process_identity=command[:2],
            sensitive_values=(root,),
            process_backend=fail_after_metadata_check,
        )

    assert caught.value.reason_code == "worker_start_failed"
    assert starts == [command]


def test_immutable_worker_identity_never_exempts_sensitive_mutable_argv(tmp_path):
    root = tmp_path / "Presentations"
    command = [
        str(root / ".venv" / "bin" / "python3"),
        str(root / "vault" / "worker.py"),
        "--root",
        str(root),
    ]
    starts = []

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        artifact_supervisor.run_authenticated_worker(
            command,
            "probe",
            {},
            {"root_path": str(root)},
            _limits(),
            immutable_process_identity=command[:2],
            sensitive_values=(root,),
            process_backend=lambda *args, **kwargs: starts.append((args, kwargs)),
        )

    assert caught.value.reason_code == "unsafe_worker_process_metadata"
    assert starts == []


def test_immutable_worker_identity_never_exempts_artifact_equal_entrypoint(tmp_path):
    root = tmp_path / "Presentations"
    artifact = root / "vault" / "worker.py"
    command = [
        str(root / ".venv" / "bin" / "python3"),
        str(artifact),
        "--worker",
    ]

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        artifact_supervisor.run_authenticated_worker(
            command,
            "probe",
            {},
            {"artifact": str(artifact)},
            _limits(),
            immutable_process_identity=command[:2],
            sensitive_values=(artifact,),
            process_backend=lambda *_args, **_kwargs: pytest.fail(
                "artifact-equal identity reached process creation"
            ),
        )

    assert caught.value.reason_code == "unsafe_worker_process_metadata"


@pytest.mark.parametrize(
    "identity_kind",
    ["short", "long", "relative", "different_prefix"],
)
def test_immutable_worker_identity_must_be_exact_two_absolute_prefix_paths(
    tmp_path,
    identity_kind,
):
    root = tmp_path / "Presentations"
    command = [
        str(root / ".venv" / "bin" / "python3"),
        str(root / "vault" / "worker.py"),
        "--worker",
    ]
    identities = {
        "short": command[:1],
        "long": command,
        "relative": ["python3", command[1]],
        "different_prefix": [command[0], str(root / "vault" / "other.py")],
    }

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        artifact_supervisor.run_authenticated_worker(
            command,
            "probe",
            {},
            {"root_path": str(root)},
            _limits(),
            immutable_process_identity=identities[identity_kind],
            sensitive_values=(root,),
            process_backend=lambda *_args, **_kwargs: pytest.fail(
                "invalid identity reached process creation"
            ),
        )

    assert caught.value.reason_code == "invalid_worker_command"


def test_sensitive_payload_keys_and_environment_names_are_removed(monkeypatch):
    sensitive = "/private/vault/secret-deck.pptx"
    sensitive_name = f"PREFIX_{sensitive}_SUFFIX"
    monkeypatch.setenv(sensitive_name, "innocent-value")
    monkeypatch.setenv("SENSITIVE_VALUE_HOLDER", f"prefix:{sensitive}:suffix")
    monkeypatch.setenv("SAFE_WORKER_VALUE", "present")

    assert artifact_supervisor._payload_sensitive_strings({sensitive: "value"}) == (
        sensitive,
    )
    environment = artifact_supervisor._sanitized_environment((sensitive,))
    assert sensitive_name not in environment
    assert "SENSITIVE_VALUE_HOLDER" not in environment
    assert environment["SAFE_WORKER_VALUE"] == "present"


def test_file_generation_round_trip_and_limit_validation(tmp_path):
    artifact = tmp_path / "deck.pptx"
    artifact.write_bytes(b"deck")
    generation = artifact_supervisor.FileGeneration.from_stat(artifact.stat())

    assert (
        artifact_supervisor.FileGeneration.from_dict(generation.to_dict()) == generation
    )
    with pytest.raises(ValueError):
        artifact_supervisor.SupervisorLimits(profile_id="INVALID PROFILE")
    with pytest.raises(ValueError):
        artifact_supervisor.build_worker_request("probe", {}, {}, schema_generation=0)
    with pytest.raises(ValueError):
        artifact_supervisor.WorkerCredentials(bytearray(32))


def test_file_generation_uses_windows_birthtime_for_path_handle_compatibility(
    monkeypatch,
):
    common = {
        "st_size": 123,
        "st_mtime_ns": 456,
        "st_dev": 10,
        "st_ino": 11,
        "st_mode": 0o100600,
        "st_file_attributes": 0x20,
    }
    path_snapshot = cast(
        os.stat_result,
        SimpleNamespace(**common, st_ctime_ns=789, st_birthtime_ns=789),
    )
    handle_snapshot = cast(
        os.stat_result,
        SimpleNamespace(**common, st_ctime_ns=987, st_birthtime_ns=789),
    )
    replacement_snapshot = cast(
        os.stat_result,
        SimpleNamespace(
            **{**common, "st_ino": 12},
            st_ctime_ns=987,
            st_birthtime_ns=789,
        ),
    )
    monkeypatch.setattr(artifact_supervisor.os, "name", "nt")

    path_generation = artifact_supervisor.FileGeneration.from_stat(path_snapshot)
    handle_generation = artifact_supervisor.FileGeneration.from_stat(handle_snapshot)

    assert path_generation == handle_generation
    assert path_generation.ctime_ns == 789
    assert (
        artifact_supervisor.FileGeneration.from_stat(replacement_snapshot)
        != path_generation
    )


def test_file_generation_falls_back_to_windows_ctime_without_birthtime(monkeypatch):
    snapshot = cast(
        os.stat_result,
        SimpleNamespace(
            st_size=123,
            st_mtime_ns=456,
            st_ctime_ns=987,
            st_dev=10,
            st_ino=11,
            st_mode=0o100600,
        ),
    )
    monkeypatch.setattr(artifact_supervisor.os, "name", "nt")

    generation = artifact_supervisor.FileGeneration.from_stat(snapshot)

    assert generation.ctime_ns == 987


def test_file_generation_keeps_non_windows_ctime_semantics(monkeypatch):
    snapshot = cast(
        os.stat_result,
        SimpleNamespace(
            st_size=123,
            st_mtime_ns=456,
            st_ctime_ns=987,
            st_birthtime_ns=789,
            st_dev=10,
            st_ino=11,
            st_mode=0o100600,
        ),
    )
    monkeypatch.setattr(artifact_supervisor.os, "name", "posix")

    generation = artifact_supervisor.FileGeneration.from_stat(snapshot)

    assert generation.ctime_ns == 987


def test_shared_pptx_imports_do_not_require_optional_psutil():
    code = f"""
import importlib.abc
import importlib.util
import sys
from pathlib import Path

class BlockPsutil(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "psutil" or fullname.startswith("psutil."):
            raise ModuleNotFoundError("synthetic missing psutil")
        return None

sys.meta_path.insert(0, BlockPsutil())
script_dir = Path({str(SCRIPT_DIR)!r})
sys.path.insert(0, str(script_dir))
for module_name in (
    "artifact_supervisor",
    "pptx_evidence",
    "video_evidence",
    "pattern_evidence",
):
    __import__(module_name)
print("shared-pptx-imports-ok")
"""
    # No timeout: block on the probe's exit event, never on a duration (see
    # _read_fifo_signal).
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "shared-pptx-imports-ok\n"


@pytest.mark.skipif(
    os.name != "posix",
    reason="vault transaction entrypoints use POSIX tracking-database locking",
)
def test_posix_ingress_entrypoint_imports_do_not_require_optional_psutil():
    code = f"""
import importlib.abc
import importlib.util
import sys
from pathlib import Path

class BlockPsutil(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "psutil" or fullname.startswith("psutil."):
            raise ModuleNotFoundError("synthetic missing psutil")
        return None

sys.meta_path.insert(0, BlockPsutil())
script_dir = Path({str(SCRIPT_DIR)!r})
sys.path.insert(0, str(script_dir))
for module_name, filename in (
    ("queue_state_import_probe", "queue-state.py"),
    ("preflight_vault_import_probe", "preflight-vault.py"),
):
    spec = importlib.util.spec_from_file_location(module_name, script_dir / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
print("posix-ingress-entrypoint-imports-ok")
"""
    # No timeout: block on the probe's exit event, never on a duration (see
    # _read_fifo_signal).
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "posix-ingress-entrypoint-imports-ok\n"


def test_monitor_fails_closed_only_when_optional_psutil_is_needed(monkeypatch):
    real_import = artifact_supervisor.importlib.import_module

    def missing_psutil(name):
        if name == "psutil":
            raise ModuleNotFoundError("synthetic missing psutil")
        return real_import(name)

    monkeypatch.setattr(artifact_supervisor, "psutil", None)
    monkeypatch.setattr(
        artifact_supervisor.importlib,
        "import_module",
        missing_psutil,
    )

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        artifact_supervisor._ProcessTreeMonitor(123, _limits()).establish()

    assert caught.value.reason_code == "worker_monitor_unavailable"
    assert caught.value.details == {"dependency": "psutil"}


@pytest.mark.parametrize("actual_version", ["7.2.1", "7.2.3", None, (7, 2, 2)])
def test_monitor_fails_closed_on_unsupported_psutil_version(
    monkeypatch,
    actual_version,
):
    monkeypatch.setattr(
        artifact_supervisor,
        "psutil",
        SimpleNamespace(__version__=actual_version),
    )

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        artifact_supervisor._load_psutil()

    assert caught.value.reason_code == "worker_monitor_unavailable"
    assert caught.value.details == {
        "dependency": "psutil",
        "required_version": "7.2.2",
        "actual_version": actual_version if isinstance(actual_version, str) else None,
    }


def test_null_is_a_valid_authenticated_success_payload():
    request = artifact_supervisor.build_worker_request(
        "probe",
        {},
        {},
        credentials=artifact_supervisor.WorkerCredentials(b"k" * 32),
        request_id="1" * 64,
    )
    stream = io.BytesIO()
    artifact_supervisor.write_worker_response(
        request,
        payload=None,
        observed_generations={},
        stream=stream,
    )

    result = artifact_supervisor._verify_response(
        stream.getvalue(),
        request,
        artifact_supervisor.DiagnosticReceipt.empty(),
        (),
    )
    assert result.payload is None


def test_response_frame_limit_reports_output_not_request_cause():
    request = artifact_supervisor.build_worker_request(
        "probe",
        {},
        {},
        credentials=artifact_supervisor.WorkerCredentials(b"k" * 32),
        request_id="1" * 64,
    )

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        artifact_supervisor.write_worker_response(
            request,
            payload={"value": "x" * 4096},
            observed_generations={},
            stream=io.BytesIO(),
            max_output_bytes=512,
        )

    assert caught.value.reason_code == "worker_output_limit_exceeded"
    assert caught.value.details == {"limit_bytes": 512}


def test_psutil_monitor_aggregates_tree_rss_and_binds_root_identity(monkeypatch):
    class Memory:
        def __init__(self, rss):
            self.rss = rss

    class FakeProcess:
        def __init__(self, pid, rss, children=()):
            self.pid = pid
            self.identity = float(pid)
            self.rss = rss
            self.descendants = list(children)

        def create_time(self):
            return self.identity

        def children(self, recursive=False):
            assert recursive is True
            return list(self.descendants)

        def memory_info(self):
            return Memory(self.rss)

        def is_running(self):
            return True

    child = FakeProcess(102, 20)
    root = FakeProcess(101, 10, (child,))
    monkeypatch.setattr(artifact_supervisor, "psutil", psutil)
    monkeypatch.setattr(psutil, "Process", lambda _pid: root)
    monitor = artifact_supervisor._ProcessTreeMonitor(
        root.pid,
        _limits(max_memory_bytes=31),
    )
    monitor.establish()
    assert monitor.sample() == (2, 30)

    root.identity += 1
    with pytest.raises(artifact_supervisor.SupervisorError) as changed:
        monitor.sample()
    assert changed.value.reason_code == "worker_monitor_identity_changed"


def test_psutil_monitor_fails_closed_on_aggregate_memory_and_process_count(
    monkeypatch,
):
    class Memory:
        rss = 20

    class FakeProcess:
        def __init__(self, pid):
            self.pid = pid

        def create_time(self):
            return float(self.pid)

        def children(self, recursive=False):
            assert recursive is True
            return [FakeProcess(202)]

        def memory_info(self):
            return Memory()

        def is_running(self):
            return True

    root = FakeProcess(201)
    monkeypatch.setattr(artifact_supervisor, "psutil", psutil)
    monkeypatch.setattr(psutil, "Process", lambda _pid: root)

    with pytest.raises(artifact_supervisor.SupervisorError) as memory_error:
        artifact_supervisor._ProcessTreeMonitor(
            root.pid,
            _limits(max_memory_bytes=39),
        ).establish()
    assert memory_error.value.reason_code == "worker_memory_limit_exceeded"

    with pytest.raises(artifact_supervisor.SupervisorError) as process_error:
        artifact_supervisor._ProcessTreeMonitor(
            root.pid,
            _limits(max_processes=1),
        ).establish()
    assert process_error.value.reason_code == "worker_process_limit_exceeded"


def test_cleanup_always_terminates_containment_after_clean_root_exit():
    class ExitedProcess:
        def poll(self):
            return 0

        def wait(self, timeout):
            return 0

    class Controller:
        terminated = False
        closed = False

        def terminate(self, _timeout=None):
            self.terminated = True

        def close(self):
            self.closed = True

    class Monitor(PermissiveMonitor):
        killed = False

        def kill_seen(self, _timeout=0.5):
            self.killed = True

    controller = Controller()
    monitor = Monitor(1, _limits())
    cleanup_error = artifact_supervisor._cleanup_invocation(
        ExitedProcess(),
        controller,
        monitor,
        None,
        None,
        None,
        1.0,
    )

    assert cleanup_error is None
    assert controller.terminated is True
    assert controller.closed is True
    assert monitor.killed is True


def test_protocol_duplicate_fd_is_explicitly_non_inheritable(monkeypatch):
    read_fd, write_fd = os.pipe()
    duplicated_fd = 987
    monkeypatch.setattr(sys.stdout, "fileno", lambda: write_fd)
    monkeypatch.setattr(sys.stderr, "fileno", lambda: write_fd)
    monkeypatch.setattr(artifact_supervisor.os, "dup", lambda _fd: duplicated_fd)
    inheritable_calls = []
    monkeypatch.setattr(
        artifact_supervisor.os,
        "set_inheritable",
        lambda fd, inheritable: inheritable_calls.append((fd, inheritable)),
    )
    monkeypatch.setattr(artifact_supervisor.os, "dup2", lambda _source, _target: None)
    monkeypatch.setattr(
        artifact_supervisor.os,
        "fdopen",
        lambda _fd, _mode, buffering=0: io.BytesIO(),
    )
    try:
        stream = artifact_supervisor.isolate_protocol_output()
        stream.close()
    finally:
        os.close(read_fd)
        os.close(write_fd)

    assert inheritable_calls == [(duplicated_fd, False)]


@pytest.mark.parametrize(
    ("failure_point", "failure_type"),
    [
        ("set_inheritable", OSError),
        ("dup2", OSError),
        ("fdopen", OSError),
        ("set_inheritable", KeyboardInterrupt),
        ("dup2", SystemExit),
    ],
)
def test_protocol_duplicate_fd_closes_on_setup_failure(
    monkeypatch,
    failure_point,
    failure_type,
):
    duplicated_fd = 987
    closed = []

    def maybe_fail(point):
        if failure_point == point:
            raise failure_type("synthetic protocol setup failure")

    monkeypatch.setattr(artifact_supervisor.os, "dup", lambda _fd: duplicated_fd)
    monkeypatch.setattr(
        artifact_supervisor.os,
        "set_inheritable",
        lambda _fd, _inheritable: maybe_fail("set_inheritable"),
    )
    monkeypatch.setattr(
        artifact_supervisor.os,
        "dup2",
        lambda _source, _target: maybe_fail("dup2"),
    )

    def open_protocol(_fd, _mode, buffering=0):
        maybe_fail("fdopen")
        return io.BytesIO()

    monkeypatch.setattr(artifact_supervisor.os, "fdopen", open_protocol)
    monkeypatch.setattr(
        artifact_supervisor.os,
        "close",
        lambda fd: closed.append(fd),
    )

    try:
        if issubclass(failure_type, OSError):
            with pytest.raises(artifact_supervisor.SupervisorError) as caught:
                artifact_supervisor.isolate_protocol_output()
            assert caught.value.reason_code == "protocol_isolation_failed"
        else:
            with pytest.raises(failure_type):
                artifact_supervisor.isolate_protocol_output()
    finally:
        # os is a shared process module; restore descriptor operations before
        # pytest's own output-capture teardown runs.
        monkeypatch.undo()

    assert closed == [duplicated_fd]


@pytest.mark.parametrize(
    ("failure_type", "expected_type"),
    [
        (OSError, artifact_supervisor.SupervisorError),
        (KeyboardInterrupt, KeyboardInterrupt),
        (SystemExit, SystemExit),
    ],
)
def test_windows_job_assignment_failure_closes_and_propagates_expected_type(
    monkeypatch,
    failure_type,
    expected_type,
):
    jobs = []

    class Job:
        def __init__(self, _limits):
            self.closed = False
            jobs.append(self)

        def assign(self, _pid):
            raise failure_type("synthetic assignment failure")

        def close(self):
            self.closed = True

    monkeypatch.setattr(artifact_supervisor.os, "name", "nt")
    monkeypatch.setattr(artifact_supervisor, "_WindowsJob", Job)
    controller = artifact_supervisor._ProcessController(
        SimpleNamespace(pid=42),
        _limits(),
    )

    with pytest.raises(expected_type) as caught:
        controller.establish()

    if expected_type is artifact_supervisor.SupervisorError:
        assert caught.value.reason_code == "worker_containment_unavailable"
    assert jobs[0].closed is True


def test_windows_creation_flags_never_request_breakaway(monkeypatch):
    monkeypatch.setattr(
        artifact_supervisor.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False
    )
    monkeypatch.setattr(
        artifact_supervisor.subprocess, "CREATE_BREAKAWAY_FROM_JOB", 1024, raising=False
    )

    assert artifact_supervisor._windows_creation_flags() == 512


def test_windows_job_api_uses_pointer_width_handles_and_verifies_assignment():
    class Function:
        def __init__(self, implementation=lambda *_args: 1):
            self.implementation = implementation
            self.argtypes = None
            self.restype = None
            self.calls = []

        def __call__(self, *args):
            self.calls.append(args)
            return self.implementation(*args)

    def mark_assigned(_process, _job, output):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_int)).contents.value = 1
        return 1

    class Kernel:
        CreateJobObjectW = Function()
        SetInformationJobObject = Function()
        OpenProcess = Function(lambda *_args: 1234)
        AssignProcessToJobObject = Function()
        IsProcessInJob = Function(mark_assigned)
        TerminateJobObject = Function()
        CloseHandle = Function()

    kernel = Kernel()
    artifact_supervisor._configure_windows_job_api(kernel)
    assert kernel.CreateJobObjectW.restype is ctypes.c_void_p
    assert kernel.OpenProcess.restype is ctypes.c_void_p

    job = object.__new__(artifact_supervisor._WindowsJob)
    job._kernel32 = kernel
    job._handle = 5678
    job.assign(99)

    requested_rights = kernel.OpenProcess.calls[0][0]
    assert requested_rights & job._PROCESS_TERMINATE
    assert requested_rights & job._PROCESS_SET_QUOTA
    assert requested_rights & job._PROCESS_QUERY_LIMITED_INFORMATION
    assert kernel.AssignProcessToJobObject.calls == [(5678, 1234)]
    assert len(kernel.IsProcessInJob.calls) == 1


@pytest.mark.parametrize(
    "configuration_failure",
    [None, KeyboardInterrupt, SystemExit],
    ids=["windows-error", "keyboard-interrupt", "system-exit"],
)
def test_windows_job_configuration_failure_closes_handle(
    monkeypatch,
    configuration_failure,
):
    class Function:
        def __init__(self, implementation=lambda *_args: 1):
            self.implementation = implementation
            self.argtypes = None
            self.restype = None
            self.calls = []

        def __call__(self, *args):
            self.calls.append(args)
            return self.implementation(*args)

    def configure(*_args):
        if configuration_failure is not None:
            raise configuration_failure("synthetic configuration failure")
        return 0

    class Kernel:
        def __init__(self):
            self.CreateJobObjectW = Function(lambda *_args: 5678)
            self.SetInformationJobObject = Function(configure)
            self.OpenProcess = Function()
            self.AssignProcessToJobObject = Function()
            self.IsProcessInJob = Function()
            self.TerminateJobObject = Function()
            self.CloseHandle = Function()

    kernel = Kernel()
    monkeypatch.setattr(artifact_supervisor.os, "name", "nt")
    monkeypatch.setattr(
        artifact_supervisor.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: kernel,
        raising=False,
    )
    job = object.__new__(artifact_supervisor._WindowsJob)
    expected = OSError if configuration_failure is None else configuration_failure

    with pytest.raises(expected):
        job.__init__(_limits())

    assert kernel.CloseHandle.calls == [(5678,)]
    assert job._handle is None


def test_windows_job_process_handle_close_failure_is_visible():
    class Function:
        def __init__(self, implementation=lambda *_args: 1):
            self.implementation = implementation
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self.implementation(*args)

    def mark_assigned(_process, _job, output):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_int)).contents.value = 1
        return 1

    class Kernel:
        OpenProcess = Function(lambda *_args: 1234)
        AssignProcessToJobObject = Function()
        IsProcessInJob = Function(mark_assigned)
        CloseHandle = Function(lambda *_args: 0)

    job = object.__new__(artifact_supervisor._WindowsJob)
    job._kernel32 = Kernel()
    job._handle = 5678

    with pytest.raises(OSError):
        job.assign(99)
