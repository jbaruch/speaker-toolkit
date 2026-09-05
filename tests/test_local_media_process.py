"""Real synthetic subprocesses exercise bounded captured and streamed pipes."""

from __future__ import annotations

import io
from pathlib import Path
import sys

import pytest

from conftest import SCRIPTS_VI, _import_script


@pytest.fixture
def process():
    return _import_script(
        Path(SCRIPTS_VI) / "local_media_process.py", "local_media_process"
    )


def test_captured_metadata_and_diagnostics_have_separate_bounds(process):
    result = process.run_media_tool(
        [
            sys.executable,
            "-c",
            "import sys; print('metadata'); sys.stderr.write('diagnostic')",
        ],
        stdout_limit=128,
        stderr_limit=32,
    )
    assert result.returncode == 0
    assert result.stdout == b"metadata\n"
    assert result.streamed_bytes == 0
    assert result.diagnostics.byte_count == 10


def test_media_stream_goes_only_to_literal_output(process, tmp_path):
    path = tmp_path / "audio.mp3"
    result = process.run_media_tool(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 1024)"],
        stdout_limit=1024,
        stderr_limit=32,
        output=path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.streamed_bytes == 1024
    assert path.read_bytes() == b"x" * 1024


@pytest.mark.parametrize(
    "stream,limit,reason",
    [
        ("stdout", 32, "media_tool_stdout_limit"),
        ("stderr", 32, "media_tool_stderr_limit"),
    ],
)
def test_captured_overflow_is_never_success(process, stream, limit, reason):
    with pytest.raises(process.LocalMediaError, match=reason):
        process.run_media_tool(
            [sys.executable, "-c", f"import sys; sys.{stream}.write('x' * 33)"],
            stdout_limit=limit,
            stderr_limit=limit,
        )


def test_on_disk_ceiling_is_enforced_before_excess_bytes_are_written(process, tmp_path):
    path = tmp_path / "audio.mp3"
    with pytest.raises(process.LocalMediaError, match="media_tool_stdout_limit"):
        process.run_media_tool(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'x' * 262144)",
            ],
            stdout_limit=65536,
            stderr_limit=32,
            output=path,
        )
    assert path.stat().st_size <= 65536


def test_exclusive_create_does_not_replace_prior_file(process, tmp_path):
    path = tmp_path / "audio.mp3"
    path.write_bytes(b"original")
    with pytest.raises(process.LocalMediaError, match="media_pipe_failed"):
        process.run_media_tool(
            [sys.executable, "-c", "print('replace')"],
            stdout_limit=128,
            stderr_limit=32,
            output=path,
        )
    assert path.read_bytes() == b"original"


def test_nonzero_return_is_explicit_and_not_an_exception(process):
    result = process.run_media_tool(
        [sys.executable, "-c", "raise SystemExit(3)"], stdout_limit=128, stderr_limit=32
    )
    assert result.returncode == 3


def test_missing_tool_is_typed(process, tmp_path):
    with pytest.raises(process.LocalMediaError, match="media_dependency_unavailable"):
        process.run_media_tool(
            [str(tmp_path / "missing")], stdout_limit=128, stderr_limit=32
        )


def test_thread_start_failure_stops_child_and_is_typed(process, monkeypatch):
    def failed_start(self):
        raise RuntimeError("cannot allocate drainer")

    monkeypatch.setattr(process._PipeDrainer, "start", failed_start)
    with pytest.raises(process.LocalMediaError, match="media_pipe_failed"):
        process.run_media_tool(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout_limit=128,
            stderr_limit=32,
        )


def test_partial_sink_write_is_a_failure_not_a_short_success(process):
    class ShortWriter(io.BytesIO):
        def write(self, value):
            return super().write(value[:1])

    target = ShortWriter()
    sink = process._FileSink(io.BytesIO(b"synthetic media"), target, 128)
    sink.start()
    sink.join(1)
    assert sink.failed
    assert sink.byte_count == 0


def test_failed_sink_read_is_explicit(process):
    class BrokenReader(io.BytesIO):
        def read(self, count: int | None = -1):
            raise OSError("private/source failed")

    sink = process._FileSink(BrokenReader(), io.BytesIO(), 128)
    sink.start()
    sink.join(1)
    assert sink.failed
    assert sink.byte_count == 0


def test_a_sink_that_did_not_finish_cannot_report_success(
    process, tmp_path, monkeypatch
):
    monkeypatch.setattr(process._FileSink, "_run", lambda self: None)
    with pytest.raises(process.LocalMediaError, match="media_pipe_failed"):
        process.run_media_tool(
            [sys.executable, "-c", "print('media')"],
            stdout_limit=128,
            stderr_limit=32,
            output=tmp_path / "audio.mp3",
        )
