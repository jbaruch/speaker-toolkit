#!/usr/bin/env python3
"""Answer "is the PowerPoint deck layer set up, and is it current?" in one call.

Three questions the skill used to have no way to ask, so it guessed:

  1. Is this the user's FIRST use? Every caller said "on first use, walk the user
     through deck-editing-setup.md" and nothing could tell first use from the
     hundredth. `status` answers it.
  2. Where is DeckOps.pptm? Eight wrappers print "confirm DeckOps.pptm is open"
     and none of them could say where it should be. The container lives at a
     canonical path under the vault (CONTAINER_DIRNAME / CONTAINER_NAME below),
     and a RUNNING PowerPoint reports where it actually opened it from.
  3. Is the imported macro current? A saved .pptm gives up no VBA source, so the
     only way to see inside is to ask the running PowerPoint for the module's own
     content stamp (DeckOpsVersion, stamped by sync-deck-drivers.py) and compare.
     A stale import is otherwise invisible: it runs, and it runs the OLD code.

Read-only. Opens nothing, saves nothing, and never launches PowerPoint.

Usage:
    deckops-doctor.py --vault-root <path> [--offline]

    --offline   skip the live PowerPoint probe (answers 1 and 2 only). Use in
                CI, or when PowerPoint must not be disturbed.

Stdout: one JSON object (see STATUSES). Stderr: an actionable line when the
status is not `ok`. Exit 0 whenever a verdict was reached — "setup required" is a
finding to act on, not a failure of this script. Exit 1 only when no verdict
could be reached, 2 on usage error.

The live probe drives PowerPoint, so it is manual-validation-only per
rules/deck-editing-rules.md; every deterministic part here (path derivation,
probe-output parsing, verdict) is unit-tested in tests/test_deckops_doctor.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from importlib import util as _importlib_util


def _load_sibling(name: str, filename: str):
    """Import a sibling script whose filename is not a valid module name."""
    path = Path(__file__).resolve().parent / filename
    spec = _importlib_util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"cannot load {path} — it must sit beside this script; reinstall the plugin"
        )
    module = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync_deck_drivers = _load_sibling("sync_deck_drivers", "sync-deck-drivers.py")

# Where the macro container and the importable .bas live, relative to the vault
# root. A stable per-machine location OUTSIDE the plugin tree on purpose: an
# installed plugin sits under a hidden `.tessl/` directory, which PowerPoint's
# VBA-editor Import panel will not show.
CONTAINER_DIRNAME = ".deckops"
CONTAINER_NAME = "DeckOps.pptm"

PROBE_DRIVER = "deckops-version.applescript"
PROBE_TIMEOUT_SEC = 90

# status -> the one thing the user or agent should do next.
STATUSES = {
    "ok": "Deck layer is ready.",
    "unsupported_platform": (
        "The PowerPoint deck layer is macOS + Microsoft PowerPoint only; no deck "
        "build can run on this host."
    ),
    "driver_drift": (
        "The deck drivers do not match their committed mirrors — reinstall the "
        "plugin, or in a dev checkout run: sync-deck-drivers.py mirror"
    ),
    "setup_required": (
        "First-time setup has not been done on this machine — walk the user "
        "through references/deck-editing-setup.md (all steps)."
    ),
    "powerpoint_not_running": (
        "PowerPoint is not running — ask the user to open {container} and keep it "
        "open for the whole build (deck-editing-setup.md Step 6)."
    ),
    "macro_unreachable": (
        "PowerPoint is running but the DeckOps macro did not answer — ask the user "
        "to open {container}, confirm macros are enabled, and confirm the module "
        "was imported (deck-editing-setup.md Steps 1-3)."
    ),
    "macro_stale": (
        "{container} holds an OLD build of the macro ({found}, expected {expected}) "
        "— re-import it per deck-editing-setup.md Step 3 before building."
    ),
}


def container_paths(vault_root: Path) -> dict[str, Path]:
    """The canonical per-machine deck-layer locations under a vault root."""
    d = vault_root.expanduser() / CONTAINER_DIRNAME
    return {
        "dir": d,
        "container": d / CONTAINER_NAME,
        "import_source": d / sync_deck_drivers.STAMP_DRIVER,
    }


def parse_probe(out: str) -> dict[str, str]:
    """Parse the probe driver's `key=value` lines.

    Values may contain `=` and `;`; keys never do. An unrecognizable line is
    dropped rather than guessed at — the verdict then falls to a missing `state`.
    """
    fields: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k:
            fields[k] = v.strip()
    return fields


def run_probe(scripts_dir: Path) -> dict[str, str]:
    """Ask the running PowerPoint for the loaded macro's stamp. Never launches it."""
    sync_deck_drivers.materialize(scripts_dir)
    driver = scripts_dir / PROBE_DRIVER
    if not driver.exists():
        return {"state": "probe_missing", "detail": f"{driver} not found"}
    try:
        proc = subprocess.run(
            ["osascript", str(driver)],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SEC,
            check=False,
        )
    except FileNotFoundError:
        return {"state": "probe_missing", "detail": "osascript not on PATH"}
    except subprocess.TimeoutExpired:
        return {
            "state": "macro_unreachable",
            "detail": (
                f"the probe did not return within {PROBE_TIMEOUT_SEC}s — a modal "
                "dialog in PowerPoint blocks every macro call until dismissed"
            ),
        }
    if proc.returncode != 0:
        return {"state": "macro_unreachable", "detail": proc.stderr.strip()}
    return parse_probe(proc.stdout)


def verdict(
    *,
    platform: str,
    driver_problems: list[str],
    container_exists: bool,
    expected_stamp: str,
    probe: dict[str, str] | None,
) -> str:
    """Classify the setup. `probe` is None when the live check was skipped."""
    if platform != "darwin":
        return "unsupported_platform"
    if driver_problems:
        return "driver_drift"
    if not container_exists:
        return "setup_required"
    if probe is None:
        return "ok"
    state = probe.get("state", "macro_unreachable")
    if state == "not_running":
        return "powerpoint_not_running"
    if state != "ok":
        return "macro_unreachable"
    if probe.get("stamp", "") != expected_stamp:
        return "macro_stale"
    return "ok"


def diagnose(vault_root: Path, scripts_dir: Path, offline: bool, platform: str) -> dict:
    paths = container_paths(vault_root)
    driver_problems = sync_deck_drivers.check(scripts_dir)

    src = scripts_dir / sync_deck_drivers.STAMP_DRIVER
    mirror = src.with_name(src.name + sync_deck_drivers.MIRROR_SUFFIX)
    stamp_src = src if src.exists() else mirror
    if stamp_src.exists():
        expected_stamp = sync_deck_drivers.read_stamp(
            stamp_src.read_text(encoding="utf-8")
        )
    else:
        expected_stamp = ""
        driver_problems = driver_problems + [
            f"neither {src.name} nor its mirror is present — reinstall the plugin"
        ]

    probe = None if (offline or platform != "darwin") else run_probe(scripts_dir)
    status = verdict(
        platform=platform,
        driver_problems=driver_problems,
        container_exists=paths["container"].is_file(),
        expected_stamp=expected_stamp,
        probe=probe,
    )

    import_source = paths["import_source"]
    report = {
        "status": status,
        "setup_complete": status in ("ok", "powerpoint_not_running", "macro_stale"),
        "platform": platform,
        "expected_stamp": expected_stamp,
        "container": {
            "canonical_path": str(paths["container"]),
            "exists": paths["container"].is_file(),
            "open_path": (probe or {}).get("container", ""),
        },
        "import_source": {
            "path": str(import_source),
            "exists": import_source.is_file(),
            "current": (
                import_source.is_file()
                and src.exists()
                and import_source.read_bytes() == src.read_bytes()
            ),
        },
        "drivers": {"problems": driver_problems},
        "live": probe if probe is not None else {"state": "skipped"},
    }
    report["next_step"] = STATUSES[status].format(
        container=paths["container"],
        found=(probe or {}).get("stamp", "unknown"),
        expected=expected_stamp,
    )
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Diagnose the PowerPoint deck-editing setup (read-only)."
    )
    ap.add_argument(
        "--vault-root",
        type=Path,
        required=True,
        help="the rhetoric-knowledge-vault root (config.vault_root)",
    )
    ap.add_argument(
        "--offline",
        action="store_true",
        help="skip the live PowerPoint probe",
    )
    ap.add_argument(
        "--scripts-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help=argparse.SUPPRESS,
    )
    args = ap.parse_args(argv)

    vault_root = args.vault_root.expanduser()
    if not vault_root.is_dir():
        print(
            f"ERROR: vault root not found: {vault_root} — pass the "
            "config.vault_root value read from the tracking database.",
            file=sys.stderr,
        )
        return 1

    # Resolve before deriving paths: the vault is commonly reached through a
    # symlink, and PowerPoint reports the REAL path of an open container. Two
    # spellings of one location would read as two locations.
    report = diagnose(
        vault_root.resolve(), args.scripts_dir, args.offline, sys.platform
    )
    print(json.dumps(report, indent=2))
    if report["status"] != "ok":
        print(f"{report['status']}: {report['next_step']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
