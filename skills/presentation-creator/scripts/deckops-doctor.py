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

Side effects, stated plainly rather than as a blanket "read-only" claim:

  * Never touches a deck, a template, the macro container, or PowerPoint's state.
    It opens no document, saves no document, and never launches PowerPoint.
  * DOES restore missing drivers into the PLUGIN's own scripts directory, via
    sync-deck-drivers.py materialize — the same install-restore every `.sh`
    wrapper performs. This runs in --offline mode too. Without it a fresh
    `tessl install` (mirrors, no sources) reads as ten orphan mirrors and a valid
    installation is told to reinstall itself. Existing drivers are never
    overwritten, so an in-progress edit in a dev checkout is safe.

Usage:
    deckops-doctor.py --vault-root <path> [--offline]

    --offline   skip the live PowerPoint probe (answers 1 and 2 only). Use in
                CI, or when PowerPoint must not be disturbed. Driver restoration
                still runs — see Side effects.

Stdout: one JSON object (see STATUSES). Stderr: an actionable line when the
status is not `ok`. Exit 0 whenever a verdict was reached — "setup required" is a
finding to act on, not a failure of this script. Exit 1 when no verdict could be
reached: an unusable vault root, or a probe that failed outright (`probe_failed`,
`probe_missing`), where the setup state is unknown rather than diagnosed. Exit 2
on usage error.

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
        "The deck drivers do not match their committed mirrors — read "
        "`drivers.problems`. A driver left stale by a plugin update is refreshed "
        "with `sync-deck-drivers.py materialize --force`; a mirror left behind by "
        "a dev-tree edit, with `sync-deck-drivers.py mirror`."
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
        "was imported into THAT file (deck-editing-setup.md Steps 1-3)."
    ),
    "probe_failed": (
        "The PowerPoint probe could not run, so the setup state is UNKNOWN — read "
        "`live.detail`. Denied Automation consent is the usual cause (System "
        "Settings -> Privacy & Security -> Automation). Re-run with --offline to "
        "check the on-disk half alone."
    ),
    "probe_missing": (
        "The probe driver or `osascript` is missing, so the setup state is UNKNOWN "
        "— read `live.detail`. Reinstall the plugin, or re-run with --offline to "
        "check the on-disk half alone."
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
            "state": "probe_failed",
            "detail": (
                f"the probe did not return within {PROBE_TIMEOUT_SEC}s — a modal "
                "dialog in PowerPoint blocks every macro call until dismissed"
            ),
        }
    if proc.returncode != 0:
        # The driver returns state=macro_unreachable (exit 0) for the ONE expected
        # failure, an unavailable macro. A non-zero exit is therefore something
        # else — denied Automation consent, a cancel, an unexpected error — and
        # must not be laundered into a setup verdict that sends the user to build
        # a second container.
        return {"state": "probe_failed", "detail": proc.stderr.strip()}
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
    if probe is None:
        # Offline: the on-disk container at the canonical path is all there is to see.
        return "ok" if container_exists else "setup_required"
    state = probe.get("state", "probe_failed")
    if state in ("probe_failed", "probe_missing"):
        # The probe could not answer, so nothing is known about the setup. Saying
        # "setup_required" here would prescribe a fix for a question never asked.
        return state
    if state == "ok":
        # A macro that answers proves setup regardless of where the container file
        # sits — a user whose DeckOps.pptm predates the canonical path is set up,
        # not unconfigured. `container.canonical_mismatch` reports the difference.
        return "ok" if probe.get("stamp", "") == expected_stamp else "macro_stale"
    if not container_exists and not probe.get("container"):
        return "setup_required"
    if state == "not_running":
        return "powerpoint_not_running"
    return "macro_unreachable"


def diagnose(vault_root: Path, scripts_dir: Path, offline: bool, platform: str) -> dict:
    paths = container_paths(vault_root)

    # Restore before judging. A fresh `tessl install` lands the .txt mirrors and
    # none of their sources, which check() reads as ten orphan mirrors — a valid
    # installation told to reinstall itself. Materializing first is the supported
    # recovery, so try it before reporting drift (error-handling: Graceful Fallback).
    materialized = [p.name for p in sync_deck_drivers.materialize(scripts_dir)]
    driver_problems = sync_deck_drivers.check(scripts_dir)

    src = scripts_dir / sync_deck_drivers.STAMP_DRIVER
    mirror = src.with_name(src.name + sync_deck_drivers.MIRROR_SUFFIX)
    stamp_src = src if src.exists() else mirror
    expected_stamp = ""
    if stamp_src.exists():
        try:
            expected_stamp = sync_deck_drivers.read_stamp(
                stamp_src.read_text(encoding="utf-8")
            )
        except ValueError as e:
            # check() already recorded this as a driver problem; crashing here
            # would swallow the actionable diagnostic it produced.
            driver_problems = driver_problems + [str(e)]
    else:
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

    open_path = (probe or {}).get("container", "")
    import_source = paths["import_source"]
    report = {
        "status": status,
        "setup_complete": status in ("ok", "powerpoint_not_running", "macro_stale"),
        "platform": platform,
        "expected_stamp": expected_stamp,
        "container": {
            "canonical_path": str(paths["container"]),
            "exists": paths["container"].is_file(),
            "open_path": open_path,
            "canonical_mismatch": bool(open_path)
            and open_path != str(paths["container"]),
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
        "drivers": {"materialized": materialized, "problems": driver_problems},
        "live": probe if probe is not None else {"state": "skipped"},
    }
    # Name the container the user actually has open, when there is one — telling
    # them to open the canonical path while a DeckOps.pptm sits open elsewhere
    # sends them to create a second one.
    report["next_step"] = STATUSES[status].format(
        container=open_path or paths["container"],
        found=(probe or {}).get("stamp", "unknown"),
        expected=expected_stamp,
    )
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Diagnose the PowerPoint deck-editing setup. Never touches a deck, a "
            "template, the macro container, or PowerPoint; does restore missing "
            "drivers into the plugin's own scripts directory."
        )
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
    # A verdict is success; a probe that could not run is not a verdict.
    return 1 if report["status"] in ("probe_failed", "probe_missing") else 0


if __name__ == "__main__":
    sys.exit(main())
