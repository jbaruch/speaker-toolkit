"""Bounded subprocess pipes for use *inside* an authenticated media worker.

The outer artifact supervisor owns wall, process-tree and memory limits. This
helper adds strict retained-output and streamed-file byte limits without ever
collecting a media download in memory. A failed stream is never a usable file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import threading
import time
from typing import BinaryIO, cast

from artifact_supervisor import DiagnosticReceipt, _PipeDrainer
from local_media_contract import LocalMediaError, refuse


CHUNK_BYTES = 64 * 1024
PIPE_JOIN_SECONDS = 1.0
POLL_SECONDS = 0.01


@dataclass(frozen=True)
class MediaToolResult:
    returncode: int
    stdout: bytes
    streamed_bytes: int
    diagnostics: DiagnosticReceipt


class _FileSink:
    """Stop before the first byte that would exceed the on-disk ceiling."""

    def __init__(self, source: BinaryIO, target: BinaryIO, limit: int) -> None:
        self.source, self.target, self.limit = source, target, limit
        self.byte_count = 0
        self.overflowed = False
        self.failed = False
        self.complete = False
        self.thread = threading.Thread(target=self._run, daemon=True)

    @property
    def alive(self) -> bool:
        return self.thread.is_alive()

    def start(self) -> None:
        self.thread.start()

    def join(self, seconds: float) -> None:
        self.thread.join(seconds)

    def close(self) -> None:
        try:
            self.source.close()
        except OSError:
            self.failed = True

    def _run(self) -> None:
        try:
            while chunk := self.source.read(CHUNK_BYTES):
                if self.byte_count + len(chunk) > self.limit:
                    self.overflowed = True
                    return
                if self.target.write(chunk) != len(chunk):
                    self.failed = True
                    return
                self.byte_count += len(chunk)
            self.target.flush()
            self.complete = True
        except (OSError, ValueError):
            self.failed = True


def _stop(process: subprocess.Popen[bytes]) -> None:
    try:
        if process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=PIPE_JOIN_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=PIPE_JOIN_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        raise LocalMediaError("media_cleanup_failed") from exc


def run_media_tool(
    command: list[str],
    *,
    stdout_limit: int,
    stderr_limit: int,
    output: Path | None = None,
    cwd: Path | None = None,
) -> MediaToolResult:
    """Capture bounded metadata or stream one literal exclusive-create output."""
    destination = None
    try:
        if output is not None:
            destination = output.open("xb", buffering=0)
        return _run(command, stdout_limit, stderr_limit, destination, cwd)
    except OSError as exc:
        raise LocalMediaError("media_pipe_failed") from exc
    finally:
        if destination is not None:
            destination.close()


def _run(
    command: list[str],
    stdout_limit: int,
    stderr_limit: int,
    destination: BinaryIO | None,
    cwd: Path | None,
) -> MediaToolResult:
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            close_fds=True,
            cwd=cwd,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise LocalMediaError("media_dependency_unavailable") from exc
    if process.stdout is None or process.stderr is None:
        try:
            _stop(process)
        finally:
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
        refuse("media_pipe_failed")
    stdout = (
        _FileSink(cast(BinaryIO, process.stdout), destination, stdout_limit)
        if destination is not None
        else _PipeDrainer(cast(BinaryIO, process.stdout), stdout_limit)
    )
    stderr = _PipeDrainer(cast(BinaryIO, process.stderr), stderr_limit)
    try:
        try:
            stdout.start()
            stderr.start()
        except RuntimeError as exc:
            raise LocalMediaError("media_pipe_failed") from exc
        while process.poll() is None:
            if stdout.overflowed or stderr.overflowed or stdout.failed or stderr.failed:
                _stop(process)
                break
            time.sleep(POLL_SECONDS)
        returncode = process.wait()
        stdout.join(PIPE_JOIN_SECONDS)
        stderr.join(PIPE_JOIN_SECONDS)
        if stdout.overflowed:
            refuse("media_tool_stdout_limit")
        if stderr.overflowed:
            refuse("media_tool_stderr_limit")
        if (
            stdout.alive
            or stderr.alive
            or stdout.failed
            or stderr.failed
            or (isinstance(stdout, _FileSink) and not stdout.complete)
        ):
            refuse("media_pipe_failed")
        return MediaToolResult(
            returncode,
            stdout.data if isinstance(stdout, _PipeDrainer) else b"",
            stdout.byte_count if isinstance(stdout, _FileSink) else 0,
            stderr.receipt,
        )
    finally:
        try:
            _stop(process)
        finally:
            stdout.close()
            stderr.close()
