#!/usr/bin/env python3
"""Build an offline, human-approved crop reviewer from a proposals TSV.

Usage: build-crop-reviewer.py PROPOSALS OUTPUT_HTML --batch-id ID [--python PATH]
TSV columns: id, title, conference, date, video_path, output_dir, manifest,
mode, region. Modes: crop, full-frame, no-slides. Region: normalized L,T,R,B
for crop, blank otherwise. Paths are native absolute paths, not shell fragments.

Every talk requires a validated individual-frame bundle from build-contact-sheet.py.
The builder verifies current recording content against the sampled source. It
never approves a proposal, runs extraction, reparses, or reads/writes the vault DB.
Stdout: one JSON report with frames_per_talk and the output path. Exit 0 succeeds,
1 reports an operational/input rejection, 2 reports invalid CLI usage. Existing
identical HTML is reusable; changed HTML requires a fresh output filename.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile
from typing import NoReturn

from artifact_supervisor import SupervisorError
from crop_frames import CropFramesError, load_frame_bundle
from ingress_contract import YOUTUBE_ID_RE
from video_evidence import VideoEvidenceError, probe_video_artifact


SCHEMA_VERSION = 1
MAX_TALKS = 500
MAX_TSV_BYTES = 2 * 1024**2
MAX_HTML_BYTES = 256 * 1024**2
COLUMNS = (
    "id",
    "title",
    "conference",
    "date",
    "video_path",
    "output_dir",
    "manifest",
    "mode",
    "region",
)
USAGE = "build-crop-reviewer.py PROPOSALS OUTPUT_HTML --batch-id ID [--python PATH]"


class ReviewerError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(
            f"{code}: check the proposals and frame manifests; regenerate stale samples or choose a fresh reviewer filename and retry"
        )


def _text(value: object, *, required: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 4096
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or (required and not value.strip())
    ):
        raise ReviewerError("crop_proposal_text_invalid")
    return value


def _path(value: str) -> str:
    _text(value, required=True)
    if not Path(value).is_absolute():
        raise ReviewerError("crop_proposal_path_invalid")
    return value


def parse_proposals(text: str) -> list[dict]:
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter="\t", strict=True)
        if reader.fieldnames != list(COLUMNS):
            raise ReviewerError("crop_proposal_columns_invalid")
        result = []
        seen = set()
        for row in reader:
            if len(result) >= MAX_TALKS or set(row) != set(COLUMNS):
                raise ReviewerError("crop_proposal_rows_invalid")
            for key, value in row.items():
                _text(value, required=key not in {"conference", "date", "region"})
            if not YOUTUBE_ID_RE.fullmatch(row["id"]) or row["id"] in seen:
                raise ReviewerError("crop_proposal_id_invalid")
            seen.add(row["id"])
            for key in ("video_path", "output_dir", "manifest"):
                _path(row[key])
            mode = row["mode"]
            if mode not in {"crop", "full-frame", "no-slides"}:
                raise ReviewerError("crop_proposal_mode_invalid")
            if mode == "crop":
                try:
                    region = [float(number) for number in row["region"].split(",")]
                except ValueError as exc:
                    raise ReviewerError("crop_proposal_region_invalid") from exc
                if len(region) != 4 or not (
                    0 <= region[0] < region[2] <= 1 and 0 <= region[1] < region[3] <= 1
                ):
                    raise ReviewerError("crop_proposal_region_invalid")
            else:
                if row["region"]:
                    raise ReviewerError("crop_proposal_region_invalid")
                region = [0, 0, 1, 1]
            result.append({**row, "region": region})
        if not result:
            raise ReviewerError("crop_proposal_empty")
        return result
    except csv.Error as exc:
        raise ReviewerError("crop_proposal_tsv_invalid") from exc


def script_json(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _read_template(name: str) -> str:
    path = Path(__file__).with_name(name)
    if not path.exists():
        path = path.with_name(path.name + ".txt")
    return path.read_text(encoding="utf-8")


def build_reviewer(
    proposals: Path, output: Path, *, batch_id: str, python_path: str = sys.executable
) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", batch_id):
        raise ReviewerError("crop_batch_id_invalid")
    _path(python_path)
    with proposals.open("rb") as stream:
        raw = stream.read(MAX_TSV_BYTES + 1)
    if len(raw) > MAX_TSV_BYTES:
        raise ReviewerError("crop_proposal_size_limit")
    try:
        rows = parse_proposals(raw.decode("utf-8-sig"))
    except UnicodeError as exc:
        raise ReviewerError("crop_proposal_encoding_invalid") from exc
    talks = []
    identities = []
    total = 0
    extractor = str(Path(__file__).with_name("video-slide-extraction.py").resolve())
    for row in rows:
        bundle = load_frame_bundle(row["manifest"])
        manifest = bundle["manifest"]
        source = probe_video_artifact(row["video_path"])
        if (
            source.source_sha256 != manifest["source"]["source_sha256"]
            or source.source_size_bytes != manifest["source"]["source_size_bytes"]
        ):
            raise ReviewerError("crop_proposal_source_mismatch")
        frames = [
            {
                "schema_version": SCHEMA_VERSION,
                "timestamp": item["timestamp_seconds"],
                "image": "data:image/jpeg;base64," + bundle["artifacts"][item["file"]],
            }
            for item in manifest["frames"]
        ]
        total += sum(len(frame["image"]) for frame in frames)
        if total > MAX_HTML_BYTES:
            raise ReviewerError("crop_reviewer_size_limit")
        command_prefix = shlex.join(
            [
                python_path,
                extractor,
                row["video_path"],
                row["output_dir"],
                "--expected-source-sha256",
                source.source_sha256,
            ]
        )
        identity = {
            "schema_version": SCHEMA_VERSION,
            **row,
            "manifest_sha256": bundle["manifest_sha256"],
            "command_prefix": command_prefix,
        }
        identities.append(identity)
        talks.append(
            {
                "schema_version": SCHEMA_VERSION,
                "id": row["id"],
                "title": row["title"],
                "conference": row["conference"],
                "date": row["date"],
                "region": row["region"],
                "mode": row["mode"],
                "frames": frames,
                "command_prefix": command_prefix,
            }
        )
    fingerprint = hashlib.sha256(script_json(identities).encode()).hexdigest()
    template = _read_template("crop-reviewer-shell.html")
    javascript = _read_template("crop-reviewer.js")
    if (
        template.count("__TALKS_JSON__") != 1
        or template.count("__BATCH_JSON__") != 1
        or template.count("__REVIEWER_JS__") != 1
    ):
        raise ReviewerError("crop_reviewer_template_invalid")
    replacements = {
        "__REVIEWER_JS__": javascript,
        "__BATCH_JSON__": script_json(
            {
                "schema_version": SCHEMA_VERSION,
                "id": batch_id,
                "fingerprint": fingerprint,
            }
        ),
        "__TALKS_JSON__": script_json(talks),
    }
    # One substitution pass: data containing another marker remains literal.
    html = re.sub(
        r"__REVIEWER_JS__|__BATCH_JSON__|__TALKS_JSON__",
        lambda match: replacements[match.group()],
        template,
    )
    encoded = html.encode("utf-8")
    if len(encoded) > MAX_HTML_BYTES:
        raise ReviewerError("crop_reviewer_size_limit")
    output = output.absolute()
    if output.is_symlink():
        raise ReviewerError("crop_reviewer_output_conflict")
    if output.exists():
        with output.open("rb") as stream:
            prior = stream.read(MAX_HTML_BYTES + 1)
        if prior != encoded:
            raise ReviewerError("crop_reviewer_output_conflict")
        reused = True
    else:
        with tempfile.TemporaryDirectory(
            prefix=".crop-review-stage-", dir=output.parent
        ) as directory:
            staged = Path(directory) / "review.html"
            staged.write_bytes(encoded)
            staged.chmod(0o600)
            os.link(staged, output)
        reused = False
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "output": str(output),
        "reused": reused,
        "batch_fingerprint": fingerprint,
        "frames_per_talk": {talk["id"]: len(talk["frames"]) for talk in talks},
    }


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        print(
            json.dumps(
                {"ok": False, "code": "crop_reviewer_usage_invalid", "usage": USAGE}
            )
        )
        print(f"invalid reviewer command; usage: {USAGE}", file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments in (["--help"], ["-h"]):
        print(json.dumps({"ok": True, "usage": USAGE}))
        return 0
    parser = ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("proposals", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(arguments)
    try:
        report = build_reviewer(
            args.proposals, args.output, batch_id=args.batch_id, python_path=args.python
        )
    except (
        ReviewerError,
        CropFramesError,
        SupervisorError,
        VideoEvidenceError,
        OSError,
    ) as exc:
        code = (
            exc.code
            if isinstance(exc, (ReviewerError, CropFramesError))
            else exc.reason_code
            if isinstance(exc, (SupervisorError, VideoEvidenceError))
            else "crop_reviewer_io_failure"
        )
        print(json.dumps({"ok": False, "code": code}))
        print(str(ReviewerError(code)), file=sys.stderr)
        return 1
    print(json.dumps(report))
    return 0


def run_cli() -> int:
    try:
        return main()
    # Agent callers treat absent JSON as a broken process contract. Emit one
    # closed failure; propagation would lose the contract and expose paths.
    # outer-boundary-process-contract
    except Exception:  # noqa: BLE001
        print(json.dumps({"ok": False, "code": "crop_reviewer_unexpected_failure"}))
        print(
            "reviewer build failed unexpectedly; repair the runtime and retry",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())
