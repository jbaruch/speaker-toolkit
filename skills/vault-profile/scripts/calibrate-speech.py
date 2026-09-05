#!/usr/bin/env python3
"""Plan or derive a family-balanced speech calibration from one configured vault.

Usage: calibrate-speech.py VAULT_ROOT --speaker NAME --language CODE [--run]
       [--allow-download] [--maximum-recordings 12] [--demo-mode ID ...]
       [--as-of TIMEZONE_AWARE_ISO_TIME]

Default is metadata-only planning. --run enables bounded source acquisition and
fresh native word transcription; --allow-download additionally enables the
ingress YouTube owner when no local recording is declared. No captions, catalog
reparsing, transcript writes, or existing-profile replacement occur. Use the
database-configured interpreter; there is no PATH fallback or auto-install.

Stdout: one schema-v1 {ok, data|error} JSON envelope. Successful data retains the
catalog digest, complete cohort plan, runtime report, and (with --run) a complete
schema-v2 profile. Treat this output as private evidence. A valid low-confidence
report is not permission to use a planning default. Save to a fresh candidate,
never redirect over an existing profile. Exit 0 reports a completed plan/run,
1 rejects inputs or capabilities, 2 reports usage or unexpected tool failure.
Per-recording acquisition failures remain explicit exclusions; global failures
emit no usable candidate. Interrupts propagate. Bounds are owned by the cohort,
speech-profile and ingress media contracts, not overridable CLI thresholds.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Iterator, NoReturn

INGRESS = Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"
if str(INGRESS) not in sys.path:
    sys.path.insert(0, str(INGRESS))

from local_media_contract import LocalMediaError  # noqa: E402
from local_media_download import download_youtube_audio  # noqa: E402
from local_media_evidence import probe_local_media  # noqa: E402
from local_media_transcription import transcribe_local_words  # noqa: E402
from local_media_words import WordSampleError  # noqa: E402
from speech_calibration import calibrate  # noqa: E402
from speech_cohort import plan_cohort, sample_window  # noqa: E402
from speech_rates import SpeechRateError, encode  # noqa: E402
from tracking_database_io import TrackingDatabaseIOError  # noqa: E402
from vault_root_authority import (  # noqa: E402
    VaultRootAuthorityError,
    materialize_native_authority,
    resolve_vault_root_authority,
)


def _owner_script(filename: str) -> ModuleType:
    """Load fixed shipped entrypoints; callers never choose a module or path."""
    name = "speech_calibration_owner_" + filename.replace("-", "_").replace(".", "_")
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, INGRESS / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError("shipped owner module unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _read_context(vault_root: str) -> tuple[Path, dict]:
    root = materialize_native_authority(vault_root, authority="cli_root")
    report = _owner_script("read-tracking-database.py").execute(
        root / "tracking-database.json"
    )
    config = report["database"]["config"]
    root = resolve_vault_root_authority(
        database_path=report["database_path"], config=config, cli_vault_root=root
    )
    configured = config.get("python_path")
    if not isinstance(configured, str) or configured != sys.executable:
        raise SpeechRateError(
            "pace_interpreter_mismatch",
            "Use config.python_path from the strict owner read; repair missing configuration through ingress.",
        )
    return root, report


@contextmanager
def _source(row: dict, root: Path) -> Iterator[tuple[object, object]]:
    source = row["source"]
    if source["kind"] == "local_media":
        # The acquisition owner receives the original locator. Do not resolve,
        # pre-open, hash or hydrate the declared recording in this caller.
        yield source["locator"], root
    else:
        with download_youtube_audio(source["video_id"]) as (path, provider_duration):
            if provider_duration <= 0:
                raise LocalMediaError("ytdlp_metadata_invalid")
            yield path, path.parent


def execute(args: argparse.Namespace) -> dict:
    root, catalog = _read_context(args.vault_root)
    generated_at = args.as_of or datetime.now(timezone.utc).isoformat()
    # Validate supplied time before acquiring any media, using the owner schema.
    calibration = {
        "schema_version": 2,
        "speaker": args.speaker,
        "language": args.language,
        "catalog_sha256": catalog["sha256"],
        "generated_at": generated_at,
        "demo_modes": args.demo_mode,
        "samples": [],
        "exclusions": [],
    }
    calibrate(calibration)
    plan = plan_cohort(
        catalog["database"],
        args.speaker,
        language=args.language,
        maximum_recordings=args.maximum_recordings,
        allow_download=args.allow_download,
        demo_modes=args.demo_mode,
    )
    required = ["core"]
    if args.run:
        required += ["source-media", "speech-calibration"]
        if args.allow_download:
            required.append("youtube-download")
    runtime = _owner_script("check-runtime.py").build_report(
        tuple(required), tuple(required)
    )
    if runtime["ok"] is not True:
        raise SpeechRateError(
            "pace_runtime_unavailable",
            "Run the configured interpreter's check-runtime.py for the required lanes; repair missing dependencies before calibration.",
        )
    result = {
        "schema_version": 1,
        "status": "plan_only",
        "catalog_sha256": catalog["sha256"],
        "cohort": plan,
        "runtime": runtime,
        "profile": None,
    }
    if args.run:
        by_id = {row["recording_id"]: row for row in plan["recordings"]}
        calibration["speaker"] = plan["speaker"]
        calibration["exclusions"] = [
            {
                "schema_version": 1,
                "recording_id": row["recording_id"],
                "reasons": row["reasons"],
            }
            for row in plan["recordings"]
            if row["status"] != "selected"
        ]
        for index, recording_id in enumerate(plan["selected_recording_ids"], 1):
            print(
                f"Speech calibration: recording {index}/{len(plan['selected_recording_ids'])}",
                file=sys.stderr,
                flush=True,
            )
            row = by_id[recording_id]
            try:
                with _source(row, root) as (path, trusted_root):
                    probe = probe_local_media(path, trusted_root=trusted_root)
                    start, duration = sample_window(probe.duration_seconds)
                    _, receipt = transcribe_local_words(
                        path,
                        probe=probe,
                        trusted_root=trusted_root,
                        sample_start_seconds=start,
                        sample_duration_seconds=duration,
                    )
                # A download context's cleanup must succeed before admission.
                calibration["samples"].append(
                    {
                        "schema_version": 1,
                        "recording_id": recording_id,
                        "family": row["family"],
                        "mode": row["mode"],
                        "year": row["year"],
                        "words": receipt,
                    }
                )
            except (LocalMediaError, SpeechRateError) as exc:
                reason = (
                    exc.reason_code if isinstance(exc, LocalMediaError) else exc.code
                )
                if reason in {
                    "media_cleanup_failed",
                    "whisper_dependency_unavailable",
                    "whisper_provider_version_unsupported",
                    "whisper_model_download_failed",
                }:
                    raise
                calibration["exclusions"].append(
                    {
                        "schema_version": 1,
                        "recording_id": recording_id,
                        "reasons": [reason],
                    }
                )
                if isinstance(exc, WordSampleError):
                    print(
                        json.dumps(
                            {
                                "schema_version": 1,
                                "code": reason,
                                "word_timing": exc.word_timing,
                            }
                        ),
                        file=sys.stderr,
                        flush=True,
                    )
                print(
                    f"Speech calibration: recording excluded ({reason}); inspect the source through its owner.",
                    file=sys.stderr,
                    flush=True,
                )
        profile = calibrate(calibration)
        result["profile"] = profile
        result["status"] = (
            "calibrated"
            if profile["summary"]["confidence"]["level"] == "conditional"
            else "low_confidence"
        )
    _, current = _read_context(str(root))
    if current["sha256"] != catalog["sha256"]:
        raise SpeechRateError(
            "pace_catalog_changed",
            "The catalog changed during calibration; rerun against one unchanged owner snapshot.",
        )
    encode(result)
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise SpeechRateError(
            "pace_usage_invalid", "Use --help for the command's arguments."
        )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--help"]:
        print(json.dumps({"schema_version": 1, "ok": True, "data": {"help": __doc__}}))
        return 0
    parser = _Parser(add_help=False)
    parser.add_argument("vault_root")
    parser.add_argument("--speaker", required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--maximum-recordings", type=int, default=12)
    parser.add_argument("--demo-mode", action="append", default=[])
    parser.add_argument("--as-of")
    try:
        result = execute(parser.parse_args(argv))
    except (
        SpeechRateError,
        LocalMediaError,
        TrackingDatabaseIOError,
        VaultRootAuthorityError,
    ) as exc:
        if isinstance(exc, SpeechRateError):
            code, message = exc.code, str(exc)
        elif isinstance(exc, LocalMediaError):
            code, message = (
                exc.reason_code,
                "Repair the bounded media owner's source, runtime or cleanup failure before rerunning.",
            )
        else:
            code, message = (
                "pace_catalog_unavailable",
                "Repair the vault root or catalog through its strict ingress owner reader.",
            )
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "error": {"code": code, "message": message},
                }
            )
        )
        print(f"Speech calibration failed: {code}; {message}", file=sys.stderr)
        return 2 if code == "pace_usage_invalid" else 1
    print(encode({"schema_version": 1, "ok": True, "data": result}).decode())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    # Callers require one JSON failure envelope; a traceback/non-JSON exit is
    # their silent-failure shape. Emit a closed tool error so propagation cannot
    # erase the report or disclose provider/source data. outer-boundary-process-contract.
    except Exception:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "error": {
                        "code": "pace_tool_failed",
                        "message": "Inspect the configured runtime and rerun the calibration owner.",
                    },
                }
            )
        )
        print("Speech calibration failed: pace_tool_failed", file=sys.stderr)
        raise SystemExit(2) from None
