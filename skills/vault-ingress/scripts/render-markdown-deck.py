#!/usr/bin/env python3
"""Render a markdown-authored deck to PDF and report what it actually contains.

Slidev, presenterm, Marp, and reveal-md author decks as markdown. Nothing in
this toolkit reads markdown as slide evidence, so those talks were analysed
transcript-only while the deck sat in a git repo next to them. This renders the
deck to a PDF the existing `static_slides` path already understands, then hands
back a receipt saying what was rendered and how far to trust its slide count.

Two things this deliberately does NOT do:

* It never exports one page per click. Slidev's `--with-clicks` (and the
  equivalent elsewhere) turns a 40-slide deck into 228 pages of cumulative
  build states, and a `slide_count` read off that page count is simply wrong.
  Every renderer here is invoked in its one-page-per-slide mode.
* It never reconciles a page count with the source's own slide count. Both are
  reported. A disagreement means the deck uses a construct this reader does not
  model, and saying so is the useful answer.

The build structure the per-click export would have carried is recovered from
the source instead: the author's own reveal markers, counted per slide. That is
`progressive-reveal` evidence — ordered cumulative content — and it is NOT
evidence that anything animated on screen.

Usage::

    render-markdown-deck.py <deck.md> --output <slides/talk.pdf> [--flavor F]
    render-markdown-deck.py <deck.md> --probe

Exit 0 with one JSON receipt on stdout. Exit 1 with a diagnostic on stderr when
the deck cannot be read, the renderer is unavailable, or the render fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from failure_diagnostics import emit_unexpected_failure
from markdown_deck import (
    MARP,
    PRESENTERM,
    REVEAL_MD,
    SLIDEV,
    FLAVORS,
    MarkdownDeckError,
    detect_flavor,
    read_deck,
)
from pdf_evidence import PdfEvidenceError, probe_pdf_artifact


RECEIPT_SCHEMA_VERSION = 1
# A deck source larger than this is not a deck. Bounded so a mistyped path at a
# multi-gigabyte file fails in milliseconds rather than filling memory.
MAX_DECK_BYTES = 8_000_000
DEFAULT_RENDER_TIMEOUT_SECONDS = 900
# presenterm sizes its export canvas off the terminal it runs in: 16px per
# column, 32px per row (measured against presenterm 0.16.1). 45x160 gives a
# 2560x1440 canvas — verified: presenterm reports
# `exporting using rows=45, columns=160, width=2560, height=1440`. The PDF page
# box then carries weasyprint's own margins on top of that canvas.
PRESENTERM_PTY_ROWS = 45
PRESENTERM_PTY_COLUMNS = 160


@dataclass(frozen=True)
class RendererSpec:
    """How one markdown deck tool is invoked for a one-page-per-slide export."""

    flavor: str
    commands: tuple[str, ...]
    needs_pty: bool
    lane: str

    def argv(self, deck: Path, output: Path) -> list[str]:
        if self.flavor == PRESENTERM:
            return [self.commands[0], "--export-pdf", str(deck), "-o", str(output)]
        if self.flavor == SLIDEV:
            # `--with-clicks` is off by default and stays off: one page per
            # slide is the count that means anything.
            return [
                self.commands[0],
                "export",
                str(deck),
                "--format",
                "pdf",
                "--output",
                str(output),
            ]
        if self.flavor == MARP:
            return [self.commands[0], "--pdf", str(deck), "-o", str(output)]
        return [self.commands[0], str(deck), "--print", str(output)]


RENDERERS: dict[str, RendererSpec] = {
    PRESENTERM: RendererSpec(
        flavor=PRESENTERM,
        # presenterm shells out to weasyprint for the PDF itself and reports
        # `spawning 'weasyprint' failed` when it is absent.
        commands=("presenterm", "weasyprint"),
        needs_pty=True,
        lane="markdown-deck-presenterm",
    ),
    SLIDEV: RendererSpec(
        flavor=SLIDEV,
        commands=("slidev",),
        needs_pty=False,
        lane="markdown-deck-slidev",
    ),
    MARP: RendererSpec(
        flavor=MARP,
        commands=("marp",),
        needs_pty=False,
        lane="markdown-deck-marp",
    ),
    REVEAL_MD: RendererSpec(
        flavor=REVEAL_MD,
        commands=("reveal-md",),
        needs_pty=False,
        lane="markdown-deck-reveal-md",
    ),
}


class RenderError(RuntimeError):
    """The deck could not be rendered, with a message naming the next step."""


def read_deck_source(deck: Path) -> str:
    """Return the deck's text, refusing anything that is not a readable deck."""
    try:
        size = deck.stat().st_size
    except OSError as exc:
        raise RenderError(
            f"cannot read deck {deck}: {exc.strerror or exc} — check the path "
            "and permissions"
        ) from exc
    if size > MAX_DECK_BYTES:
        raise RenderError(
            f"deck {deck} is {size} bytes, over the {MAX_DECK_BYTES}-byte limit "
            "— point --deck at the markdown source, not a build artifact"
        )
    try:
        return deck.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RenderError(
            f"deck {deck} is not UTF-8 text — a markdown deck source is "
            f"expected, got undecodable bytes at offset {exc.start}"
        ) from exc
    except OSError as exc:
        raise RenderError(
            f"cannot read deck {deck}: {exc.strerror or exc} — check the path "
            "and permissions"
        ) from exc


def missing_commands(spec: RendererSpec) -> list[str]:
    """Return the spec's commands that are not on PATH, in declaration order."""
    return [command for command in spec.commands if shutil.which(command) is None]


def _run_with_pty(argv: Sequence[str], timeout_seconds: int) -> tuple[int, str]:
    """Run a command attached to a sized pseudo-terminal, returning its output.

    presenterm refuses to export without a terminal (`Inappropriate ioctl for
    device (os error 25)`) and reads the export canvas size from the terminal's
    window size, reporting `render: screen is too small` when that is 0x0. A
    plain pipe gives it neither.

    `timeout_seconds` is a wall limit on the whole run, not an idle limit: a
    renderer that keeps printing progress while making none would otherwise
    never trip a per-read timeout.
    """
    try:
        import fcntl
        import pty
        import select
        import struct
        import termios
    except ImportError as exc:  # pragma: no cover - POSIX-only support module
        raise RenderError(
            f"{argv[0]} needs a pseudo-terminal, which this platform does not "
            "provide — export the deck by hand and register the PDF instead"
        ) from exc

    master, slave = pty.openpty()
    try:
        fcntl.ioctl(
            slave,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", PRESENTERM_PTY_ROWS, PRESENTERM_PTY_COLUMNS, 0, 0),
        )
        try:
            process = subprocess.Popen(
                list(argv),
                stdin=slave,
                stdout=slave,
                stderr=slave,
                close_fds=True,
            )
        except OSError as exc:
            raise RenderError(f"cannot start {argv[0]}: {exc.strerror or exc}") from exc
        os.close(slave)
        slave = -1
        chunks: list[bytes] = []
        deadline = time.monotonic() + timeout_seconds
        deadline_expired = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                deadline_expired = True
                break
            ready, _, _ = select.select([master], [], [], remaining)
            if not ready:
                deadline_expired = True
                break
            try:
                data = os.read(master, 65536)
            except OSError:
                # The child closed its end: a pty reports EIO here, not EOF.
                # The run is not judged by this — `process.wait()` below still
                # decides, and a non-zero exit is still a failure.
                break
            if not data:
                break
            chunks.append(data)
        if deadline_expired:
            process.kill()
            process.wait()
            raise RenderError(
                f"{argv[0]} did not finish within {timeout_seconds}s and was "
                "killed — raise --timeout-seconds or export the deck by hand"
            )
        returncode = process.wait()
    finally:
        if slave != -1:
            os.close(slave)
        os.close(master)
    return returncode, b"".join(chunks).decode("utf-8", "replace")


def _run_plain(argv: Sequence[str], timeout_seconds: int) -> tuple[int, str]:
    """Run a command with pipes, returning its exit code and merged output."""
    try:
        completed = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderError(
            f"{argv[0]} did not finish within {timeout_seconds}s — raise "
            "--timeout-seconds or export the deck by hand"
        ) from exc
    except OSError as exc:
        raise RenderError(f"cannot start {argv[0]}: {exc.strerror or exc}") from exc
    return completed.returncode, completed.stdout.decode("utf-8", "replace")


def _tail(text: str, limit: int = 2000) -> str:
    """Return the last of a renderer's output, stripped of terminal control."""
    printable = "".join(
        character
        for character in text
        if character in "\n\t" or character.isprintable()
    )
    collapsed = "\n".join(
        line.rstrip() for line in printable.splitlines() if line.strip()
    )
    return collapsed[-limit:]


def render(
    deck: Path,
    output: Path,
    spec: RendererSpec,
    *,
    timeout_seconds: int,
) -> int:
    """Render the deck into `output` and return its page count.

    Nothing reaches `output` until the bounded PDF probe has accepted the
    staged file. A renderer that exits 0 over a corrupt PDF must not replace
    a valid earlier render with an unreadable one, so the probe runs on the
    staging copy and a rejection leaves the previous artifact untouched.
    """
    absent = missing_commands(spec)
    if absent:
        raise RenderError(
            f"the {spec.lane} lane is unavailable: {', '.join(absent)} not on "
            f"PATH. Install {' and '.join(spec.commands)}, or export the deck "
            "by hand and register the PDF"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        staged = Path(staging) / output.name
        argv = spec.argv(deck, staged)
        runner = _run_with_pty if spec.needs_pty else _run_plain
        returncode, transcript = runner(argv, timeout_seconds)
        if returncode != 0:
            raise RenderError(
                f"{spec.commands[0]} exited {returncode} rendering {deck}:\n"
                f"{_tail(transcript)}"
            )
        if not staged.exists():
            raise RenderError(
                f"{spec.commands[0]} exited 0 without writing {staged.name} — "
                f"its output was:\n{_tail(transcript)}"
            )
        try:
            page_count = probe_pdf_artifact(
                staged, trusted_root=Path(staging)
            ).page_count
        except PdfEvidenceError as exc:
            raise RenderError(
                f"{spec.commands[0]} wrote a PDF the bounded probe rejected "
                f"({exc.reason_code}) — it is not usable as slide evidence, so "
                f"{output} was left as it was"
            ) from exc
        os.replace(staged, output)
    return page_count


def _output_generation(output: Path | None) -> tuple[int, int] | None:
    """Return an output file's mtime and size, or None when it is absent.

    Compared before and after a run so the failure boundary reports whether
    THIS run committed a render, rather than whether some earlier run left a
    PDF at the same path.
    """
    if output is None:
        return None
    try:
        info = output.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_receipt(
    deck: Path,
    source: str,
    decision_flavor: str,
    decided_by: str,
    evidence: str,
    *,
    output: Path | None,
    page_count: int | None,
    output_sha256: str | None,
) -> dict[str, object]:
    """Return the deterministic receipt for one deck reading or render."""
    structure = read_deck(source, decision_flavor)
    declared = structure.slide_count
    agreement = None if page_count is None else page_count == declared
    absent = missing_commands(RENDERERS[decision_flavor])
    receipt: dict[str, object] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "deck_path": str(deck),
        "deck_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "flavor": decision_flavor,
        "flavor_decided_by": decided_by,
        "flavor_evidence": evidence,
        "lane": RENDERERS[decision_flavor].lane,
        "lane_available": not absent,
        "missing_commands": absent,
        "source_structure": structure.to_dict(),
        "rendered": output is not None,
        "output_path": None if output is None else str(output),
        "output_sha256": output_sha256,
        "page_count": page_count,
        "source_slide_count": declared,
        "slide_count_agrees_with_source": agreement,
    }
    # The number a caller should record as `slide_count`. The renderer owns the
    # format's pagination and was invoked one-page-per-slide, so its page count
    # wins whenever there is one. Without a render there is nothing but the
    # source reading, and it is labelled as such.
    if page_count is not None:
        receipt["slide_count"] = page_count
        receipt["slide_count_basis"] = "rendered_pages"
    else:
        receipt["slide_count"] = declared
        receipt["slide_count_basis"] = "source_separators"
    return receipt


def execute(
    deck: Path,
    *,
    output: Path | None,
    flavor: str | None,
    timeout_seconds: int,
) -> dict[str, object]:
    """Read the deck, optionally render it, and return the receipt."""
    source = read_deck_source(deck)
    if flavor is None:
        try:
            decision = detect_flavor(source, deck_path=deck)
        except MarkdownDeckError as exc:
            raise RenderError(str(exc)) from exc
        decided_by, evidence = decision.decided_by, decision.evidence
        chosen = decision.flavor
    else:
        chosen, decided_by, evidence = flavor, "operator", flavor
    page_count: int | None = None
    output_sha256: str | None = None
    if output is not None:
        page_count = render(
            deck, output, RENDERERS[chosen], timeout_seconds=timeout_seconds
        )
        output_sha256 = _sha256(output)
    try:
        return build_receipt(
            deck,
            source,
            chosen,
            decided_by,
            evidence,
            output=output,
            page_count=page_count,
            output_sha256=output_sha256,
        )
    except MarkdownDeckError as exc:
        raise RenderError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("deck", type=Path, help="path to the deck's markdown source")
    parser.add_argument(
        "--output",
        type=Path,
        help="PDF to write, normally {vault_root}/slides/{talk}.pdf",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="read the deck and report the flavor and lane without rendering",
    )
    parser.add_argument(
        "--flavor",
        choices=FLAVORS,
        help="name the authoring tool instead of detecting it",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_RENDER_TIMEOUT_SECONDS,
        help=f"renderer wall limit (default {DEFAULT_RENDER_TIMEOUT_SECONDS})",
    )
    args = parser.parse_args(argv)
    if args.probe == (args.output is not None):
        parser.error("pass exactly one of --output <pdf> or --probe")
    if args.timeout_seconds < 1:
        parser.error("--timeout-seconds must be a positive number of seconds")
    before = _output_generation(args.output)
    try:
        receipt = execute(
            args.deck,
            output=args.output,
            flavor=args.flavor,
            timeout_seconds=args.timeout_seconds,
        )
    except RenderError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    # An agent reads a non-zero exit as "no deck was rendered" and moves the
    # talk on transcript-only. A traceback here would say neither what failed
    # nor whether a PDF now sits at --output for the next run to trust, and it
    # would print the deck path the caller already knows into a log that
    # should not carry it.
    except Exception as exc:  # noqa: BLE001 - outer-boundary-process-contract
        emit_unexpected_failure(
            exc,
            "render_markdown_deck_unexpected_failure",
            "Rendering the markdown deck failed unexpectedly. Read "
            "`output_written` before retrying: false means nothing was "
            "committed and the command can be re-run as-is; true means a PDF "
            "is already at the output path and the next run will replace it.",
            {"output_written": _output_generation(args.output) != before},
        )
        return 3
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
