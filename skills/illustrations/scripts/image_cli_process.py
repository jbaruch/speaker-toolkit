"""Bounded CLI pipes inside the authenticated image worker.

The shared artifact supervisor owns wall time, memory and descendant cleanup.
This helper limits retained CLI output and private-workspace growth. It is not
a standalone process sandbox and must not be called outside that supervisor.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from typing import BinaryIO, cast


sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts")
)
from artifact_supervisor import _PipeDrainer, _PipeWriter  # noqa: E402
from artifact_metadata import WINDOWS_REPARSE_POINT_ATTRIBUTE  # noqa: E402


PIPE_JOIN_SECONDS = 1.0
POLL_SECONDS = 0.02
CLI_STDOUT_BYTES = 16 * 1024 * 1024
CLI_STDERR_BYTES = 64 * 1024
CLI_STDIN_BYTES = 128 * 1024
WORKSPACE_MAX_BYTES = 128 * 1024 * 1024
WORKSPACE_MAX_ENTRIES = 128
WORKSPACE_MAX_DEPTH = 8
PROCESS_FAILURES = frozenset(
    {
        "cli_start_failed",
        "cli_pipe_failed",
        "cli_stdout_limit",
        "cli_stderr_limit",
        "cli_stdin_limit",
        "cli_workspace_limit",
        "cli_workspace_invalid",
        "cli_cleanup_failed",
    }
)


class CliProcessError(RuntimeError):
    """A closed failure category; never includes raw child diagnostics."""

    def __init__(self, reason: str) -> None:
        if reason not in PROCESS_FAILURES:
            raise ValueError("invalid CLI process failure code")
        self.reason_code = reason
        super().__init__(reason)


@dataclass(frozen=True)
class CliProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def subscription_environment() -> dict[str, str]:
    """Keep cached CLI login; withhold inherited API and access-token variables.

    This does not read, replace or remove any credential file or change the
    user's environment. The worker separately checks the CLI's active method.
    """
    return {
        name: value
        for name, value in os.environ.items()
        if not name.upper().endswith(("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD"))
    }


def check_workspace(path: Path) -> None:
    """Bound private scratch growth without following any symlink."""
    pending = [(path, 0)]
    entries = byte_count = 0
    try:
        while pending:
            directory, depth = pending.pop()
            directory_facts = directory.lstat()
            if not stat.S_ISDIR(directory_facts.st_mode) or (
                getattr(directory_facts, "st_file_attributes", 0)
                & WINDOWS_REPARSE_POINT_ATTRIBUTE
            ):
                raise CliProcessError("cli_workspace_invalid")
            with os.scandir(directory) as children:
                for child in children:
                    entries += 1
                    if entries > WORKSPACE_MAX_ENTRIES:
                        raise CliProcessError("cli_workspace_limit")
                    facts = child.stat(follow_symlinks=False)
                    if (
                        getattr(facts, "st_file_attributes", 0)
                        & WINDOWS_REPARSE_POINT_ATTRIBUTE
                    ):
                        raise CliProcessError("cli_workspace_invalid")
                    if stat.S_ISREG(facts.st_mode):
                        byte_count += facts.st_size
                        if byte_count > WORKSPACE_MAX_BYTES:
                            raise CliProcessError("cli_workspace_limit")
                    elif stat.S_ISDIR(facts.st_mode):
                        if depth >= WORKSPACE_MAX_DEPTH:
                            raise CliProcessError("cli_workspace_limit")
                        pending.append((Path(child.path), depth + 1))
                    else:
                        raise CliProcessError("cli_workspace_invalid")
    except OSError as exc:
        raise CliProcessError("cli_workspace_invalid") from exc


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
        raise CliProcessError("cli_cleanup_failed") from exc


def run_cli_command(
    command: list[str], workspace: Path, *, input_bytes: bytes = b""
) -> CliProcessResult:
    """Run one command inside the caller's authenticated worker, without retry."""
    if not isinstance(input_bytes, bytes) or len(input_bytes) > CLI_STDIN_BYTES:
        raise CliProcessError("cli_stdin_limit")
    check_workspace(workspace)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace,
            env=subscription_environment(),
            close_fds=True,
            bufsize=0,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise CliProcessError("cli_start_failed") from exc
    if process.stdin is None or process.stdout is None or process.stderr is None:
        try:
            _stop(process)
        finally:
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
        raise CliProcessError("cli_pipe_failed")
    writer = _PipeWriter(cast(BinaryIO, process.stdin), input_bytes)
    stdout = _PipeDrainer(cast(BinaryIO, process.stdout), CLI_STDOUT_BYTES)
    stderr = _PipeDrainer(cast(BinaryIO, process.stderr), CLI_STDERR_BYTES)
    streams = (writer, stdout, stderr)
    started = []
    try:
        try:
            for stream in streams:
                stream.start()
                started.append(stream)
            while process.poll() is None:
                if stdout.overflowed:
                    raise CliProcessError("cli_stdout_limit")
                if stderr.overflowed:
                    raise CliProcessError("cli_stderr_limit")
                if any(stream.failed for stream in streams):
                    raise CliProcessError("cli_pipe_failed")
                check_workspace(workspace)
                time.sleep(POLL_SECONDS)
            for stream in started:
                stream.join(PIPE_JOIN_SECONDS)
            if any(stream.alive or stream.failed for stream in streams):
                raise CliProcessError("cli_pipe_failed")
            if stdout.overflowed:
                raise CliProcessError("cli_stdout_limit")
            if stderr.overflowed:
                raise CliProcessError("cli_stderr_limit")
            check_workspace(workspace)
            return CliProcessResult(int(process.returncode), stdout.data, stderr.data)
        except (OSError, ValueError, RuntimeError) as exc:
            if isinstance(exc, CliProcessError):
                raise
            raise CliProcessError("cli_pipe_failed") from exc
    finally:
        try:
            _stop(process)
        finally:
            for stream in started:
                stream.join(PIPE_JOIN_SECONDS)
            for stream in streams:
                stream.close()
