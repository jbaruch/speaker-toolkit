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
import lzma
import zipfile
import zlib
from pathlib import Path

from importlib import util as _importlib_util


def _load_sibling(name: str, filename: str):
    """Import a sibling script whose filename is not a valid module name."""
    path = Path(__file__).resolve().parent / filename
    hint = f"{path} must sit beside this script — reinstall the plugin"
    spec = _importlib_util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path} — {hint}")
    module = _importlib_util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, SyntaxError) as e:
        # A spec can be built for a file that is then unreadable, truncated, or
        # corrupt. A raw traceback here would replace the actionable diagnostic
        # this script exists to produce.
        raise ImportError(f"cannot execute {path} ({e}) — {hint}") from e
    return module


sync_deck_drivers = _load_sibling("sync_deck_drivers", "sync-deck-drivers.py")

# Where the macro container and the importable .bas live, relative to the vault
# root. A stable per-machine location OUTSIDE the plugin tree on purpose: an
# installed plugin sits under a hidden `.tessl/` directory, which PowerPoint's
# VBA-editor Import panel will not show.
CONTAINER_DIRNAME = ".deckops"
CONTAINER_NAME = "DeckOps.pptm"

# Markers looked for inside a container's ppt/vbaProject.bin. Module and
# procedure names sit in the project streams as plain bytes even though the
# source itself is compressed, so their presence separates "no module at all"
# from "an old module". A HINT that refines the advice, never the authority —
# the live probe decides whether the macro actually answers.
# Everything `zipfile` documents for opening an archive and reading a member off
# an attacker-shaped or merely broken file. Enumerated rather than a catch-all
# (rules/error-handling.md Specific Exceptions), and enumerated in FULL rather
# than one class per bug report — only three of these descend from OSError, and
# a container this cannot read must degrade to "no information", never abort a
# diagnosis the live probe may already have answered.
CONTAINER_READ_ERRORS = (
    zipfile.BadZipFile,  # not a zip, truncated, bad central directory
    zipfile.LargeZipFile,  # ZIP64 needed but disallowed
    zlib.error,  # valid archive, corrupt deflate stream (Exception, not OSError)
    NotImplementedError,  # unsupported compression method, e.g. AE-x encrypted
    ValueError,  # embedded NUL in the path, closed file, malformed member
    KeyError,  # member absent between namelist() and read()
    EOFError,  # stream ends mid-member
    RuntimeError,  # encrypted member, no password
    lzma.LZMAError,  # corrupt LZMA stream; unreachable via ALLOWED_COMPRESSION,
    # kept because a decoder error must never be the thing that escapes
    OSError,  # unreadable, permissions, a directory, I/O failure
)

# The compression methods PowerPoint actually writes. Checked BEFORE decoding, so
# an archive declaring anything else is reported unreadable without its codec ever
# being invoked. This is the root fix for a run of one-decoder-error-per-review:
# every codec zipfile supports raises its own exception type (zlib.error,
# lzma.LZMAError, and whatever a future Python adds), and enumerating them chases
# a set that grows. Refusing to decode what a real container never uses closes the
# whole family instead of its current members.
ALLOWED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})

VBA_PART = "ppt/vbaProject.bin"
# Cap on the bytes read out of that member. Only marker presence matters, and a
# real container's part is ~88 KB, so this is generous for the job while refusing
# to decompress an arbitrarily large member into memory on the strength of a
# declared size a hostile or damaged archive controls.
VBA_PART_READ_LIMIT = 8 * 1024 * 1024
MODULE_MARKER = b"RunDeckOps"
STAMP_MACRO_MARKER = b"DeckOpsVersion"

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
        "{container} holds an OLD build of the macro (found {found}, expected "
        "{expected}) — re-import it per deck-editing-setup.md Step 3 before "
        "building. Setup is otherwise done; this is a re-import, not a redo."
    ),
    # Reached by reading the container rather than by a macro that answered, so
    # the module being old is inferred, not observed. Disabled macros produce the
    # same silence, and dropping that remediation would strand a user whose only
    # real problem is a security setting.
    "macro_stale_inferred": (
        "{container} is open and holds a DeckOps module with no version macro, so "
        "it is a build predating the stamp (expected {expected}) — re-import it "
        "per deck-editing-setup.md Step 3. Disabled macros look identical from "
        "outside, so if the re-import does not clear this, confirm macros are "
        "enabled (Step 1)."
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


def inspect_container(path: Path) -> dict:
    """Read-only look inside a .pptm for the DeckOps module. Never opens PowerPoint.

    Answers the one question the live probe cannot: when DeckOpsVersion does not
    answer, is that because no module was ever imported, or because an OLD build
    is imported that predates the stamp macro? Every user upgrading from a
    pre-stamp plugin is in the second state, and telling them "never imported"
    sends them to redo setup instead of re-importing.

    Unreadable or malformed files report `readable: False` rather than raising —
    this refines a diagnostic and must never become one.
    """
    report = {
        "exists": False,
        "readable": False,
        "has_module": False,
        "has_stamp_macro": False,
    }
    # is_file() is inside the guard too: it stats the path, so a malformed one
    # (an embedded NUL) or an unreadable parent raises before any zip work.
    try:
        report["exists"] = path.is_file()
        if not report["exists"]:
            return report
        with zipfile.ZipFile(path) as z:
            if VBA_PART not in z.namelist():
                report["readable"] = True
                return report
            if z.getinfo(VBA_PART).compress_type not in ALLOWED_COMPRESSION:
                return report
            with z.open(VBA_PART) as member:
                blob = member.read(VBA_PART_READ_LIMIT)
    except CONTAINER_READ_ERRORS:
        return report
    report["readable"] = True
    report["has_module"] = MODULE_MARKER in blob
    report["has_stamp_macro"] = STAMP_MACRO_MARKER in blob
    return report


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
    container_holds_old_module: bool = False,
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
    if container_holds_old_module and probe.get("container"):
        # Only when PowerPoint actually HAS the container open does "the macro did
        # not answer" point at the module rather than at the file being closed.
        # Macros being disabled still produces the same silence, so this verdict
        # is inferred and its message carries both remediations.
        return "macro_stale_inferred"
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
            # check() validates the real driver's stamp, not an orphan mirror.
            if stamp_src == mirror:
                driver_problems = driver_problems + [str(e)]
    else:
        driver_problems = driver_problems + [
            f"neither {src.name} nor its mirror is present — reinstall the plugin"
        ]

    probe = None if (offline or platform != "darwin") else run_probe(scripts_dir)
    open_path = (probe or {}).get("container", "")

    # Inspect whichever container is real: the one PowerPoint has open wins over
    # the canonical path, since that is the file the macro would have come from.
    inspect_path = Path(open_path) if open_path else paths["container"]
    container_report = inspect_container(inspect_path)
    holds_old_module = (
        container_report["has_module"] and not container_report["has_stamp_macro"]
    )

    status = verdict(
        platform=platform,
        driver_problems=driver_problems,
        container_exists=paths["container"].is_file(),
        expected_stamp=expected_stamp,
        probe=probe,
        container_holds_old_module=holds_old_module,
    )

    import_source = paths["import_source"]
    report = {
        "status": status,
        "setup_complete": status
        in ("ok", "powerpoint_not_running", "macro_stale", "macro_stale_inferred"),
        "platform": platform,
        "expected_stamp": expected_stamp,
        "container": {
            "canonical_path": str(paths["container"]),
            "exists": paths["container"].is_file(),
            "open_path": open_path,
            "canonical_mismatch": bool(open_path)
            and open_path != str(paths["container"]),
            "inspected_path": str(inspect_path),
            "holds_module": container_report["has_module"],
            "holds_stamp_macro": container_report["has_stamp_macro"],
            "readable": container_report["readable"],
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
    # A pre-stamp module answers no version at all, so name that rather than
    # printing "unknown" at a user who has a perfectly good container.
    found = (probe or {}).get("stamp", "")
    if not found:
        found = (
            "no version macro — a build predating the stamp"
            if holds_old_module
            else "unknown"
        )
    report["next_step"] = STATUSES[status].format(
        container=open_path or paths["container"],
        found=found,
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
