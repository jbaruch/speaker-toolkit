#!/usr/bin/env python3
"""Image-generation model registry — the single source of truth for the
model roster, vendor aliases, optimization attributes, and freshness.

Three consumers read this module:
  - generate-illustrations.py imports MODEL_REGISTRY / COMPARE_MODELS for
    --compare and resolve_model_id() for alias-safe API dispatch.
  - The illustrations skill Step 2 runs `--check-freshness` as a deterministic
    precheck before any image work (is the roster itself out of date?).
  - The illustrations skill Step 3 runs `--shortlist <priorities>` to narrow
    the roster by what the speaker optimizes for, before rendering anything.

Importable (underscore name, entry-guarded main) and executable:
    python3 model_registry.py --check-freshness
    python3 model_registry.py --shortlist quality,build-editability

Stdlib only (Python 3.8+).
"""

import argparse
import json
import sys
from datetime import date, datetime

# --- Vendor endpoints ---
#
# Single source of truth for the API bases. Both generate-illustrations.py and
# generate-thumbnail.py import these so a version bump happens in one place.
# Gemini generateContent and Imagen :predict share this base. It stays on v1beta:
# verified 2026-06-15 that gemini-3-pro-image (the default) is served only on
# v1beta and 404s on v1, though flash/imagen exist on both.
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
OPENAI_API_BASE = "https://api.openai.com/v1"

# --- Registry ---
#
# Each entry:
#   id       — canonical API model id (what the vendor endpoints accept)
#   display  — human label; vendor codename in parens where one exists
#   family   — vendor family for endpoint dispatch (gemini / imagen / openai)
#   aliases  — codenames / alternate ids that resolve to this id. The
#              "nano-banana" line is Google's codename for the Gemini image
#              models; without this map a refresh agent searching the web sees
#              "Gemini 3 Pro Image" and drops the "nano-banana-*" entry as
#              unknown. Aliases keep the two names bound to one id. The
#              "-preview" Gemini ids are kept here as aliases too: Google
#              deprecates them 2026-06-25, so canonical is the GA id, but baked
#              outlines that reference the preview id still resolve.
#   cost     — relative price tier: low | medium | high
#   speed    — relative latency tier: fast | medium | slow
#   quality  — relative fidelity tier: medium | high
#   edit     — image-edit support: strong | none. Drives build-editability:
#              Imagen has no edit endpoint, so build chains cannot run on it.
#
# This roster is a SEED CACHE, not an allowlist. Rendering dispatches by family
# prefix and accepts any id (see generate-illustrations.py model_family /
# resolve_model_id), so a new model from a supported vendor renders with no edit
# here. The roster only feeds --shortlist ranking and --compare. A model not yet
# cached can be ranked for one talk by injecting its web-discovered attributes
# via shortlist_models(extra_models=...) / `--shortlist --add` — no table edit.
# Persistent additions land here through the Step 2 freshness refresh.
#
# Tiers are coarse and drift with the market. The freshness check refreshes
# both the roster and these tiers when new flagships ship — bump
# REGISTRY_LAST_REVIEWED (ISO date) whenever this block is reconciled.
REGISTRY_LAST_REVIEWED = "2026-06-15"
REGISTRY_FRESHNESS_MAX_AGE_DAYS = 90

MODEL_REGISTRY = [
    {
        "id": "gemini-3-pro-image",
        "display": "Gemini 3 Pro Image (Nano Banana Pro)",
        "family": "gemini",
        "aliases": ["gemini-3-pro-image-preview", "nano-banana-pro", "nano-banana-pro-preview"],
        "cost": "medium",
        "speed": "medium",
        "quality": "high",
        "edit": "strong",
    },
    {
        "id": "gemini-3.1-flash-image",
        "display": "Gemini 3.1 Flash Image (Nano Banana)",
        "family": "gemini",
        "aliases": ["gemini-3.1-flash-image-preview", "nano-banana", "gemini-flash-image"],
        "cost": "low",
        "speed": "fast",
        "quality": "medium",
        "edit": "strong",
    },
    {
        "id": "imagen-4.0-ultra-generate-001",
        "display": "Imagen 4 Ultra",
        "family": "imagen",
        "aliases": ["imagen-4-ultra"],
        "cost": "medium",
        "speed": "medium",
        "quality": "high",
        "edit": "none",
    },
    {
        # Snapshot-pinned for reproducible illustration style; the rolling
        # "gpt-image-2" alias resolves here so baked outlines still dispatch.
        "id": "gpt-image-2-2026-04-21",
        "display": "GPT Image 2",
        "family": "openai",
        "aliases": ["gpt-image-2"],
        "cost": "high",
        "speed": "slow",
        "quality": "high",
        "edit": "strong",
    },
]

# Historical id list — preserves the COMPARE_MODELS contract for --compare and
# any downstream code/tests that referenced the bare list.
COMPARE_MODELS = [m["id"] for m in MODEL_REGISTRY]

# Soft ranking priorities: attribute + tier ordering (best first).
PRIORITY_RANKINGS = {
    "cost": ("cost", ["low", "medium", "high"]),
    "speed": ("speed", ["fast", "medium", "slow"]),
    "quality": ("quality", ["high", "medium"]),
}
# build-editability is a hard filter, not a soft rank.
VALID_PRIORITIES = set(PRIORITY_RANKINGS) | {"build-editability"}


def resolve_model_id(name):
    """Resolve a model name or vendor codename to its canonical registry id.

    Matches the id or any alias, case-insensitively. Unknown / ad-hoc ids are
    returned unchanged so they still dispatch by family. This is what keeps an
    outline that baked `nano-banana-pro` working against the real
    `gemini-3-pro-image` endpoint.
    """
    if not name:
        return name
    stripped = name.strip()
    key = stripped.lower()
    for m in MODEL_REGISTRY:
        if key == m["id"].lower():
            return m["id"]
        if any(key == alias.lower() for alias in m.get("aliases", [])):
            return m["id"]
    # Unknown id: return it stripped so stray whitespace can't misclassify the
    # vendor family in model_family()'s prefix check.
    return stripped


# Model-id prefixes we ship a vendor adapter for (Google generateContent /
# Imagen :predict, OpenAI images). model_family() falls back to "gemini" for any
# unknown prefix, so it can't tell a real Gemini id from an unsupported vendor.
SUPPORTED_MODEL_PREFIXES = ("gpt-image", "imagen", "gemini", "nano-banana")


def is_supported_model(name):
    """True if the model's resolved id maps to a vendor adapter we ship.

    Gates callers that accept arbitrary ids (e.g. style-explore candidates) so
    an unsupported vendor like `midjourney-*` fails fast with an actionable
    message instead of being misrouted to the Gemini endpoint.
    """
    resolved = resolve_model_id(name)
    if not resolved:
        return False
    return resolved.lower().startswith(SUPPORTED_MODEL_PREFIXES)


def model_attributes(name):
    """Return the registry entry for a model name/alias, or None if unknown."""
    canonical = resolve_model_id(name)
    for m in MODEL_REGISTRY:
        if m["id"] == canonical:
            return m
    return None


def shortlist_models(priorities, registry=None, extra_models=None):
    """Filter + rank the registry by optimization priorities, best first.

    - "build-editability" is a HARD filter: drops models whose edit == "none"
      (Imagen has no edit endpoint, so build chains cannot run on it).
    - cost / speed / quality are SOFT signals: candidates are ranked by the
      summed tier-position across the requested signals (lower is better), with
      registry order as a stable tie-break.

    extra_models: optional list of ad-hoc model entries (same shape as a
    registry entry; at minimum an "id") to rank alongside the cached roster.
    This is the live-injection path for a web-discovered model that isn't cached
    yet — the agent supplies the attributes, the algorithm stays deterministic.

    Priority order does not change the result; all soft signals weigh equally.
    With no priorities, returns the full set in declared order (registry first,
    then injected). Raises ValueError on an unknown priority or a malformed
    extra entry.
    """
    reg = list(MODEL_REGISTRY if registry is None else registry)
    if extra_models:
        for i, m in enumerate(extra_models):
            if not isinstance(m, dict) or not m.get("id"):
                raise ValueError(f"extra_models[{i}] needs at least an 'id' field.")
        reg = reg + list(extra_models)
    # De-duplicate (preserving first occurrence) so an accidental repeat can't
    # double a soft signal's weight — order and repetition are not meant to matter.
    priorities = list(dict.fromkeys(priorities))
    for p in priorities:
        if p not in VALID_PRIORITIES:
            raise ValueError(
                f"Unknown priority '{p}'. Valid priorities: "
                f"{', '.join(sorted(VALID_PRIORITIES))}."
            )
    if "build-editability" in priorities:
        # Keep only models EXPLICITLY marked edit-capable. A missing/blank edit
        # field (e.g. an injected model that forgot it) must not slip into a
        # build-required shortlist, so treat unknown edit support as not-capable.
        reg = [m for m in reg if m.get("edit") and m.get("edit") != "none"]
    soft = [p for p in priorities if p in PRIORITY_RANKINGS]

    def score(model):
        total = 0
        for p in soft:
            attr, order = PRIORITY_RANKINGS[p]
            tier = model.get(attr)
            total += order.index(tier) if tier in order else len(order)
        return total

    return sorted(reg, key=score)


def check_freshness(today=None):
    """Compute registry staleness from REGISTRY_LAST_REVIEWED.

    Pure function — no I/O, no web access. Staleness is a date heuristic: it
    tells the agent WHETHER to web-search for newer flagships, not what they
    are. `today` is injectable for deterministic tests.

    Returns a dict: last_reviewed, max_age_days, age_days, stale, models[].
    """
    today = today or date.today()
    reviewed = datetime.strptime(REGISTRY_LAST_REVIEWED, "%Y-%m-%d").date()
    age_days = (today - reviewed).days
    return {
        "last_reviewed": REGISTRY_LAST_REVIEWED,
        "max_age_days": REGISTRY_FRESHNESS_MAX_AGE_DAYS,
        "age_days": age_days,
        "stale": age_days > REGISTRY_FRESHNESS_MAX_AGE_DAYS,
        "models": list(MODEL_REGISTRY),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Query the image-generation model registry.",
        epilog="Examples:\n"
               "  %(prog)s --check-freshness\n"
               "  %(prog)s --shortlist quality,build-editability\n"
               "  %(prog)s --shortlist cost\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check-freshness",
        action="store_true",
        help="Emit registry staleness JSON (precheck before image work)",
    )
    group.add_argument(
        "--shortlist",
        metavar="PRIORITIES",
        help="Comma-separated priorities (cost, speed, quality, "
             "build-editability); emit ranked candidate JSON, best first",
    )
    parser.add_argument(
        "--add",
        metavar="JSON",
        help="JSON array of extra model entries to rank alongside the cached "
             "roster (live injection of a web-discovered model); with --shortlist",
    )
    args = parser.parse_args()

    if args.check_freshness:
        print(json.dumps(check_freshness(), indent=2))
        return

    extra_models = None
    if args.add:
        try:
            extra_models = json.loads(args.add)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --add is not valid JSON ({exc}).", file=sys.stderr)
            sys.exit(1)
        if not isinstance(extra_models, list):
            print("ERROR: --add must be a JSON array of model entries.", file=sys.stderr)
            sys.exit(1)

    priorities = [p.strip() for p in args.shortlist.split(",") if p.strip()]
    try:
        ranked = shortlist_models(priorities, extra_models=extra_models)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"priorities": priorities, "shortlist": ranked}, indent=2))


if __name__ == "__main__":
    main()
