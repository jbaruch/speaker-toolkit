"""Security and resource-boundary tests for artifact_supervisor.py."""

from __future__ import annotations

import ctypes
import importlib.util
import io
import json
import os
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

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
SPEC = importlib.util.spec_from_file_location("artifact_supervisor", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
artifact_supervisor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = artifact_supervisor
SPEC.loader.exec_module(artifact_supervisor)


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
import time
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
    time.sleep(30)
elif mode == "spawn_tree":
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with open(request.payload["pid_receipt"], "w", encoding="ascii") as receipt:
        receipt.write(str(child.pid))
    time.sleep(30)
elif mode == "spawn_group_success":
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with open(request.payload["pid_receipt"], "w", encoding="ascii") as receipt:
        receipt.write(str(child.pid))
    supervisor.write_worker_response(
        request,
        payload={{"child_pid": child.pid}},
        observed_generations=request.expected_generations,
        stream=protocol,
    )
    time.sleep(0.2)
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


def _run(mode, *, limits=None, payload=None, monitor_factory=None):
    request_payload = {"mode": mode}
    if payload:
        request_payload.update(payload)
    return artifact_supervisor.run_authenticated_worker(
        [sys.executable, "-c", WORKER_CODE],
        "probe",
        {"pptx": _generation()},
        request_payload,
        limits or _limits(),
        schema_generation=3,
        pipeline_generation="1.2.0",
        monitor_factory=monitor_factory or PermissiveMonitor,
    )


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
    assert caught.value.details == {
        "artifact": "<redacted>",
        "secret": "<redacted>",
        "<redacted>": "artifact-key",
        "<redacted>#2": "secret-key",
    }


def test_wall_limit_terminates_worker():
    started = time.monotonic()
    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run("timeout", limits=_limits(wall_seconds=0.2))

    assert caught.value.reason_code == "worker_timeout"
    assert time.monotonic() - started < 3


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group assertion")
def test_timeout_kills_descendant_process_group(tmp_path):
    receipt = tmp_path / "child.pid"
    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(
            "spawn_tree",
            limits=_limits(wall_seconds=0.4),
            payload={"pid_receipt": str(receipt)},
        )

    assert caught.value.reason_code == "worker_timeout"
    child_pid = int(receipt.read_text(encoding="ascii"))
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and psutil.pid_exists(child_pid):
        time.sleep(0.02)
    if psutil.pid_exists(child_pid):
        child = psutil.Process(child_pid)
        assert child.status() == psutil.STATUS_ZOMBIE


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


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-tree assertion")
def test_clean_exit_reports_and_kills_known_same_group_descendant(tmp_path):
    receipt = tmp_path / "child.pid"

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run(
            "spawn_group_success",
            payload={"pid_receipt": str(receipt)},
            monitor_factory=artifact_supervisor._ProcessTreeMonitor,
        )

    child_pid = int(receipt.read_text(encoding="ascii"))
    assert caught.value.reason_code == "worker_process_tree_leak"
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and psutil.pid_exists(child_pid):
        time.sleep(0.02)
    if psutil.pid_exists(child_pid):
        child = psutil.Process(child_pid)
        assert child.status() == psutil.STATUS_ZOMBIE


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


def test_fast_exit_race_is_confirmed_by_popen_and_cleanup_does_not_mask(tmp_path):
    class ZombieRaceMonitor(PermissiveMonitor):
        def sample(self):
            time.sleep(0.1)
            raise artifact_supervisor.SupervisorError("worker_monitor_identity_changed")

    artifact = tmp_path / "tiny-malformed.pptx"
    result = _run(
        "success",
        payload={"artifact": str(artifact)},
        monitor_factory=ZombieRaceMonitor,
    )
    assert result.payload["leaked"] is False

    with pytest.raises(artifact_supervisor.SupervisorError) as caught:
        _run("fast_exit", monitor_factory=ZombieRaceMonitor)
    assert caught.value.reason_code == "worker_exit"


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
            raise RuntimeError("synthetic cleanup failure")

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

    class Process:
        pid = 123

        def poll(self):
            return 0

        def wait(self, *, timeout):
            observed["wait"] = timeout
            time.sleep(min(0.01, timeout))
            return 0

    class Controller:
        def terminate(self):
            return None

        def close(self):
            return None

    class Monitor:
        def kill_seen(self, timeout):
            observed["kill"] = timeout
            time.sleep(min(0.01, timeout))

        def any_seen_alive(self):
            return False

    class Pipe:
        alive = True

        def close(self):
            return None

        def join(self, timeout):
            observed["join"] = timeout
            time.sleep(min(0.01, timeout))
            self.alive = False

    pipe = Pipe()
    started = time.monotonic()
    failure = artifact_supervisor._cleanup_invocation(
        Process(),
        Controller(),
        Monitor(),
        pipe,
        None,
        None,
        0.1,
    )
    elapsed = time.monotonic() - started

    assert failure is None
    assert 0 < observed["kill"] < observed["wait"] <= 0.1
    assert 0 < observed["join"] < observed["kill"]
    assert elapsed < 0.15


def test_cleanup_deadline_bounds_a_blocking_cleanup_step():
    entered = threading.Event()
    release = threading.Event()

    class Process:
        def poll(self):
            return 0

        def wait(self, *, timeout):
            return 0

    class Controller:
        def terminate(self):
            entered.set()
            release.wait(1.0)

        def close(self):
            return None

    started = time.monotonic()
    failure = artifact_supervisor._cleanup_invocation(
        Process(),
        Controller(),
        None,
        None,
        None,
        None,
        0.05,
    )
    elapsed = time.monotonic() - started
    assert entered.wait(0.5)
    release.set()

    assert isinstance(failure, TimeoutError)
    assert elapsed < 0.5


def test_cleanup_thread_does_not_swallow_keyboard_interrupt():
    class Process:
        def poll(self):
            return 0

        def wait(self, *, timeout):
            return 0

    class Controller:
        def terminate(self):
            raise KeyboardInterrupt

        def close(self):
            return None

    with pytest.raises(KeyboardInterrupt):
        artifact_supervisor._cleanup_invocation(
            Process(),
            Controller(),
            None,
            None,
            None,
            None,
            0.5,
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
    ):
        result = real_cleanup(
            process,
            controller,
            monitor,
            writer,
            stdout_reader,
            stderr_reader,
            timeout,
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
            limits=_limits(max_memory_bytes=1),
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


def test_shared_ingress_imports_do_not_require_optional_psutil():
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
for module_name in ("artifact_supervisor", "pptx_evidence", "pattern_evidence"):
    __import__(module_name)
for module_name, filename in (
    ("queue_state_import_probe", "queue-state.py"),
    ("preflight_vault_import_probe", "preflight-vault.py"),
):
    spec = importlib.util.spec_from_file_location(module_name, script_dir / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
print("shared-ingress-imports-ok")
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "shared-ingress-imports-ok\n"


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

        def terminate(self):
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
