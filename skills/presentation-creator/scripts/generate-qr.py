#!/usr/bin/env python3
"""Generate a QR code and optionally insert it into a PowerPoint deck.

Generates an unbranded QR code encoding a shownotes URL (optionally shortened
via bit.ly or rebrand.ly), matches the QR background color to the target slide,
auto-selects foreground color for contrast, and inserts the QR image into the
deck at the configured slide position.

Two URL-resolution modes:
  --shownotes-url URL   Script resolves shortening itself via {vault}/secrets.json
  --short-url URL       Agent pre-resolved the short URL (via MCP); script just
                        generates the QR and inserts it

PNG-only mode (no deck required):
  --png-only            Generate the QR PNG without opening or modifying a deck.
                        Use --bg-color R,G,B and --output PATH to control colors
                        and output location. URL shortening and tracking DB
                        updates still run normally.

Usage:
    python3 generate-qr.py <deck.pptx> --talk-slug SLUG --shownotes-url URL
    python3 generate-qr.py <deck.pptx> --talk-slug SLUG --short-url URL
    python3 generate-qr.py <deck.pptx> --talk-slug SLUG --shownotes-url URL --dry-run
    python3 generate-qr.py <deck.pptx> --talk-slug SLUG --shownotes-url URL --profile PATH --vault PATH
    python3 generate-qr.py --png-only --talk-slug SLUG --shownotes-url URL --output qr.png --bg-color 128,0,128

Requires:
    - python-pptx  (pip install python-pptx)
    - qrcode       (pip install qrcode)
    - Pillow       (pip install Pillow — transitive dep of python-pptx)
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
except ImportError:
    print("ERROR: 'qrcode' package not installed. Run: pip install qrcode")
    sys.exit(1)

try:
    from PIL import Image  # noqa: F401 — validates Pillow is available
except ImportError:
    print("ERROR: 'Pillow' package not installed. Run: pip install Pillow")
    sys.exit(1)

from pptx import Presentation  # read-only: background-color match + slide-finding
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches

# --- Constants ---

QR_BOX_SIZE = 10       # pixels per QR module
QR_BORDER = 4          # quiet-zone modules
QR_ERROR_CORRECTION = ERROR_CORRECT_M

# QR placement: bottom-right, 2 inches wide, 0.3 inch margin from edges
QR_WIDTH_INCHES = 2.0
QR_MARGIN_INCHES = 0.3

# Existing-QR detection: a roughly-square picture whose side sits in this band is
# treated as a QR to replace. Decks adapted (trimmed) from another talk carry
# inherited QRs at varying positions; this finds them regardless of placement.
QR_DETECT_MIN_INCHES = 1.5
QR_DETECT_MAX_INCHES = 2.5
QR_SQUARE_TOL_INCHES = 0.1


# --- Vault / Config Loading ---

def load_vault_config(vault_path, profile_path=None):
    """Load speaker profile, secrets, and tracking database from the vault.

    Returns:
        tuple (speaker_profile, secrets, tracking_db)
        Any of these may be empty dicts if the file doesn't exist.
    """
    speaker_profile = {}
    secrets = {}
    tracking_db = {}

    # Speaker profile
    sp_path = profile_path or os.path.join(vault_path, "speaker-profile.json")
    if os.path.isfile(sp_path):
        with open(sp_path, "r", encoding="utf-8") as f:
            speaker_profile = json.load(f)

    # Secrets
    secrets_path = os.path.join(vault_path, "secrets.json")
    if os.path.isfile(secrets_path):
        with open(secrets_path, "r", encoding="utf-8") as f:
            secrets = json.load(f)

    # Tracking database
    tdb_path = os.path.join(vault_path, "tracking-database.json")
    if os.path.isfile(tdb_path):
        with open(tdb_path, "r", encoding="utf-8") as f:
            tracking_db = json.load(f)

    return speaker_profile, secrets, tracking_db


# --- URL Shortening ---

def _http_request(url, data=None, headers=None, method="GET"):
    """Make an HTTP request using stdlib urllib. Returns parsed JSON or raises."""
    if headers is None:
        headers = {}
    if data is not None:
        data = json.dumps(data).encode("utf-8")
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def create_bitly_link(long_url, api_token, custom_back_half=None, domain=None):
    """Create a new bit.ly short link.

    Args:
        long_url: The URL to shorten
        api_token: Bitly API token
        custom_back_half: Custom back-half for the short URL (e.g., talk slug).
            If provided, creates {domain}/{custom_back_half} instead of a random hash.
        domain: Custom Bitly domain (e.g., "jbaru.ch"). Defaults to "bit.ly".

    Returns:
        dict with keys: short_url, link_id, short_path
    """
    bitly_domain = domain or "bit.ly"
    payload = {"long_url": long_url, "domain": bitly_domain}
    if custom_back_half:
        payload["title"] = custom_back_half  # for tracking
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    # Create the link first
    result = _http_request(
        "https://api-ssl.bitly.com/v4/bitlinks",
        data=payload,
        headers=headers,
        method="POST",
    )
    link_id = result["id"]
    short_url = result["link"]
    short_path = link_id.split("/", 1)[-1] if "/" in link_id else link_id

    # Set custom back-half if requested
    if custom_back_half:
        try:
            _http_request(
                f"https://api-ssl.bitly.com/v4/custom_bitlinks",
                data={
                    "bitlink_id": link_id,
                    "custom_bitlink": f"{bitly_domain}/{custom_back_half}",
                },
                headers=headers,
                method="POST",
            )
            short_url = f"https://{bitly_domain}/{custom_back_half}"
            short_path = custom_back_half
            print(f"  Custom back-half set: {bitly_domain}/{custom_back_half}")
        except Exception as e:
            print(f"  WARNING: Custom back-half failed ({e}), using generated: {short_url}")

    return {
        "short_url": short_url,
        "link_id": link_id,
        "short_path": short_path,
    }


def update_bitly_link(link_id, new_long_url, api_token):
    """Update an existing bit.ly link's target URL via PATCH."""
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    _http_request(
        f"https://api-ssl.bitly.com/v4/bitlinks/{link_id}",
        data={"long_url": new_long_url},
        headers=headers,
        method="PATCH",
    )


def create_rebrandly_link(long_url, api_key, domain=None, slashtag=None):
    """Create a new rebrand.ly short link.

    Returns:
        dict with keys: short_url, link_id, short_path
    """
    payload = {"destination": long_url}
    if domain:
        payload["domain"] = {"fullName": domain}
    if slashtag:
        payload["slashtag"] = slashtag

    headers = {
        "apikey": api_key,
        "Content-Type": "application/json",
    }
    result = _http_request(
        "https://api.rebrandly.com/v1/links",
        data=payload,
        headers=headers,
        method="POST",
    )
    return {
        "short_url": f"https://{result['shortUrl']}",
        "link_id": result["id"],
        "short_path": result["slashtag"],
    }


def update_rebrandly_link(link_id, new_long_url, api_key):
    """Update an existing rebrand.ly link's target URL."""
    headers = {
        "apikey": api_key,
        "Content-Type": "application/json",
    }
    _http_request(
        f"https://api.rebrandly.com/v1/links/{link_id}",
        data={"destination": new_long_url},
        headers=headers,
        method="POST",
    )


def _print_missing_key_help(service, key_name, vault_path):
    """Print actionable help when an API key is missing from secrets.json."""
    secrets_path = os.path.join(vault_path, "secrets.json") if vault_path else "secrets.json"
    if vault_path and not os.path.isfile(secrets_path):
        print(f"  WARNING: No {service}.{key_name} found — secrets.json does not exist. Falling back to raw URL.")
        print(f"  Create it:")
        print(f'    echo \'{{\"{service}\": {{\"{key_name}\": \"YOUR_KEY\"}}}}\' > {secrets_path}')
        print(f"    chmod 600 {secrets_path}")
    else:
        print(f"  WARNING: No {service}.{key_name} in secrets.json, falling back to raw URL.")
        print(f"  Add to {secrets_path}:")
        print(f'    \"{service}\": {{\"{key_name}\": \"YOUR_KEY\"}}')


def resolve_short_url(shownotes_url, talk_slug, config, secrets, tracking_db, dry_run=False, vault_path=None):
    """Resolve the short URL for a talk, using cache or API as needed.

    Args:
        shownotes_url: The full shownotes URL to shorten
        talk_slug: Unique talk identifier
        config: QR config from speaker profile (publishing_process.qr_code)
        secrets: Parsed secrets.json
        tracking_db: Parsed tracking-database.json
        dry_run: If True, skip API calls
        vault_path: Path to vault (for actionable error messages)

    Returns:
        tuple (short_url, metadata_dict)
        metadata_dict has keys: shortener, short_path, link_id, short_url, target_url
    """
    shortener = config.get("shortener")
    qr_codes = tracking_db.get("qr_codes", [])

    # Look up existing entry
    existing = None
    for entry in qr_codes:
        if entry.get("talk_slug") == talk_slug:
            existing = entry
            break

    # If cached and target matches, reuse
    if existing and existing.get("target_url") == shownotes_url:
        print(f"  Reusing cached short URL for '{talk_slug}': {existing['short_url']}")
        return existing["short_url"], existing

    # Distinguish "not configured" from "explicitly disabled"
    if shortener is None:
        print("  WARNING: No URL shortener configured in speaker profile (publishing_process.qr_code.shortener).")
        print("  Add 'shortener: bitly' or 'shortener: rebrandly' to your profile,")
        print("  or set 'shortener: none' to explicitly use raw URLs.")
        print("  Proceeding with raw URL.")

    if shortener in (None, "none"):
        meta = {
            "talk_slug": talk_slug,
            "target_url": shownotes_url,
            "shortener": "none",
            "short_path": None,
            "short_url": shownotes_url,
            "shortener_link_id": None,
        }
        return shownotes_url, meta

    if dry_run:
        print(f"  DRY RUN: would call {shortener} API for {shownotes_url}")
        return shownotes_url, {
            "talk_slug": talk_slug,
            "target_url": shownotes_url,
            "shortener": shortener,
            "short_path": None,
            "short_url": shownotes_url,
            "shortener_link_id": None,
        }

    # The custom back-half (bit.ly) / slashtag (rebrand.ly) is ALWAYS the talk
    # slug — no override (see rules/qr-generation-rules.md). It is the decoupling
    # layer and the human-readable, traceable short path.
    custom_back_half = talk_slug

    try:
        if shortener == "bitly":
            api_token = secrets.get("bitly", {}).get("api_token")
            if not api_token:
                _print_missing_key_help("bitly", "api_token", vault_path)
                return shownotes_url, _none_meta(talk_slug, shownotes_url)

            bitly_domain = config.get("bitly_domain")  # e.g., "jbaru.ch"

            if existing and existing.get("shortener_link_id"):
                # Update existing link target
                print(f"  Updating bit.ly link {existing['shortener_link_id']} → {shownotes_url}")
                update_bitly_link(existing["shortener_link_id"], shownotes_url, api_token)
                meta = dict(existing)
                meta["target_url"] = shownotes_url
                meta["updated_at"] = datetime.date.today().isoformat()
                return existing["short_url"], meta
            else:
                # Create new link with talk slug as custom back-half
                domain_label = bitly_domain or "bit.ly"
                print(f"  Creating {domain_label} link for {shownotes_url} (back-half: {custom_back_half})")
                result = create_bitly_link(shownotes_url, api_token, custom_back_half, domain=bitly_domain)
                meta = {
                    "talk_slug": talk_slug,
                    "target_url": shownotes_url,
                    "shortener": "bitly",
                    "short_path": result["short_path"],
                    "short_url": result["short_url"],
                    "shortener_link_id": result["link_id"],
                }
                return result["short_url"], meta

        elif shortener == "rebrandly":
            api_key = secrets.get("rebrandly", {}).get("api_key")
            if not api_key:
                _print_missing_key_help("rebrandly", "api_key", vault_path)
                return shownotes_url, _none_meta(talk_slug, shownotes_url)

            domain = config.get("rebrandly_domain")

            if existing and existing.get("shortener_link_id"):
                print(f"  Updating rebrand.ly link {existing['shortener_link_id']} → {shownotes_url}")
                update_rebrandly_link(existing["shortener_link_id"], shownotes_url, api_key)
                meta = dict(existing)
                meta["target_url"] = shownotes_url
                meta["updated_at"] = datetime.date.today().isoformat()
                return existing["short_url"], meta
            else:
                print(f"  Creating rebrand.ly link for {shownotes_url} (slashtag: {custom_back_half})")
                result = create_rebrandly_link(shownotes_url, api_key, domain, custom_back_half)
                meta = {
                    "talk_slug": talk_slug,
                    "target_url": shownotes_url,
                    "shortener": "rebrandly",
                    "short_path": result["short_path"],
                    "short_url": result["short_url"],
                    "shortener_link_id": result["link_id"],
                }
                return result["short_url"], meta

        else:
            print(f"  WARNING: Unknown shortener '{shortener}', using raw URL")
            return shownotes_url, _none_meta(talk_slug, shownotes_url)

    except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
        print(f"  WARNING: {shortener} API failed ({e}), falling back to raw URL")
        return shownotes_url, _none_meta(talk_slug, shownotes_url)


def _none_meta(talk_slug, shownotes_url):
    """Build a metadata dict for the shortener=none fallback."""
    return {
        "talk_slug": talk_slug,
        "target_url": shownotes_url,
        "shortener": "none",
        "short_path": None,
        "short_url": shownotes_url,
        "shortener_link_id": None,
    }


# --- Slide Background Color Resolution ---

def resolve_slide_bg_rgb(slide):
    """Walk slide → layout → master to find an explicit solid fill background.

    Returns:
        tuple (R, G, B) as ints 0-255, or None if no solid fill found.
    """
    for obj in [slide, slide.slide_layout, slide.slide_layout.slide_master]:
        bg = obj.background
        fill = bg.fill
        if fill.type is not None:
            # Check for solid fill
            try:
                color = fill.fore_color
                if color.type is not None:
                    rgb = color.rgb
                    return (rgb[0], rgb[1], rgb[2])
            except (AttributeError, TypeError):
                continue
    return None


def choose_fg_color(bg_rgb):
    """Auto-contrast: pick black or white foreground based on background luminance.

    Uses WCAG relative luminance formula:
        L = 0.2126*R/255 + 0.7152*G/255 + 0.0722*B/255

    Returns:
        tuple (R, G, B) — white (255,255,255) for dark backgrounds,
        black (0,0,0) for light backgrounds.
    """
    if bg_rgb is None:
        return (0, 0, 0)  # default to black on unknown background

    r, g, b = bg_rgb
    luminance = 0.2126 * r / 255 + 0.7152 * g / 255 + 0.0722 * b / 255

    if luminance < 0.5:
        return (255, 255, 255)  # white foreground on dark background
    else:
        return (0, 0, 0)  # black foreground on light background


# --- QR Code Generation ---

def generate_qr_png(url, fg_rgb, bg_rgb, out_path):
    """Generate a QR code PNG file.

    Args:
        url: The URL to encode
        fg_rgb: Foreground color as (R, G, B) tuple
        bg_rgb: Background color as (R, G, B) tuple, or None for white
        out_path: Path to save the PNG file
    """
    if bg_rgb is None:
        bg_rgb = (255, 255, 255)

    qr = qrcode.QRCode(
        error_correction=QR_ERROR_CORRECTION,
        box_size=QR_BOX_SIZE,
        border=QR_BORDER,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color=fg_rgb, back_color=bg_rgb)
    img.save(out_path)
    return out_path


# --- Slide Detection ---

def find_shownotes_slide(prs, shownotes_url):
    """Find the slide index containing the shownotes URL text.

    Returns:
        int (0-based slide index) or None if not found.
    """
    for idx, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    full_text = "".join(run.text for run in paragraph.runs)
                    if shownotes_url in full_text:
                        return idx
    return None


def slide_has_existing_qr(slide):
    """True if the slide carries a QR-like picture: a roughly-square picture
    whose side sits in the QR size band.

    Decks adapted (trimmed) from another talk inherit that talk's QR images at
    whatever positions they had. Detecting them by shape — independent of the
    configured placement — lets every QR-bearing slide be targeted for
    replacement, instead of only the config-positioned slide.
    """
    lo = Inches(QR_DETECT_MIN_INCHES)
    hi = Inches(QR_DETECT_MAX_INCHES)
    sq_tol = Inches(QR_SQUARE_TOL_INCHES)
    for shape in slide.shapes:
        if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
            continue
        w, h = shape.width, shape.height
        if w is None or h is None:
            continue
        if lo <= w <= hi and abs(w - h) < sq_tol:
            return True
    return False


def resolve_target_slide_indices(prs, config, shownotes_url):
    """Determine which slides should receive the QR code.

    Args:
        prs: Presentation object
        config: QR config from speaker profile
        shownotes_url: The shownotes URL (for content detection)

    Returns:
        list of 0-based slide indices
    """
    position = config.get("slide_position", "closing")
    slide_count = len(prs.slides)

    indices = []

    if position in ("shownotes_slide", "both"):
        sn_idx = find_shownotes_slide(prs, shownotes_url)
        if sn_idx is not None:
            indices.append(sn_idx)
        else:
            # Fallback: slide index 3 (common shownotes position)
            fallback = min(3, slide_count - 1)
            print(f"  WARNING: Shownotes URL not found in slide text, falling back to slide {fallback + 1}")
            indices.append(fallback)

    if position in ("closing", "both"):
        closing_idx = slide_count - 1
        if closing_idx not in indices:
            indices.append(closing_idx)

    # Always target every slide that already carries a QR — a deck adapted from
    # another talk inherits stale QRs (e.g. an early shownotes slide + closing)
    # that must be replaced in place, not left beside a freshly-added one.
    for idx, slide in enumerate(prs.slides):
        if idx not in indices and slide_has_existing_qr(slide):
            indices.append(idx)

    if not indices:
        # Default: last slide
        indices.append(slide_count - 1)

    return sorted(indices)


# --- QR Insertion ---

def insert_qr_via_powerpoint(deck_path, jobs, scripts_dir):
    """Insert the QR PNG(s) into the deck via the real PowerPoint app.

    Replaces the old python-pptx write (`insert-qr.sh` → InsertQR VBA macro), so
    PowerPoint serializes a valid .pptx (see rules/deck-editing-rules.md). On each
    target slide the macro detects any existing QR-like picture (square, in the QR
    size band, at any position) and replaces it in place; otherwise it places a new
    QR bottom-right (idempotent re-runs). macOS + Microsoft PowerPoint only.

    jobs: list of (png_path, [1-based slide numbers]) — one per QR color variant.
    Each variant is a separate InsertQR pass; the deck is threaded through
    uniquely-named intermediates (PowerPoint keys open decks by filename) and the
    final result is moved back to deck_path.
    """
    wrapper = os.path.join(scripts_dir, "insert-qr.sh")
    if not os.path.isfile(wrapper):
        raise SystemExit(f"insert-qr.sh not found at {wrapper} — reinstall the tile")
    current = deck_path
    for n, (png_path, slide_nums) in enumerate(jobs):
        out = f"{deck_path}.qrtmp{n}.pptx"  # distinct basename — no open-deck collision
        csv = ",".join(str(x) for x in slide_nums)
        try:
            subprocess.run([wrapper, current, out, png_path, csv], check=True)
        except subprocess.CalledProcessError:
            raise SystemExit(
                f"ERROR: QR insertion failed in PowerPoint (insert-qr.sh on slide(s) {csv}). "
                "Confirm DeckOps.pptm is open with macros enabled and Automation consent "
                "granted — see skills/presentation-creator/references/deck-editing-setup.md"
            )
        if current != deck_path:
            os.remove(current)  # drop the prior intermediate
        current = out
    shutil.move(current, deck_path)


# --- Tracking Database ---

def update_tracking_db(tracking_db, entry, qr_png_rel_path):
    """Append or replace a qr_codes entry in the tracking database.

    Args:
        tracking_db: The full tracking database dict (mutated in place)
        entry: Metadata dict from resolve_short_url
        qr_png_rel_path: Relative path to the QR PNG file
    """
    if "qr_codes" not in tracking_db:
        tracking_db["qr_codes"] = []

    today = datetime.date.today().isoformat()
    talk_slug = entry["talk_slug"]

    new_entry = {
        "talk_slug": talk_slug,
        "target_url": entry["target_url"],
        "shortener": entry["shortener"],
        "short_path": entry.get("short_path"),
        "short_url": entry["short_url"],
        "shortener_link_id": entry.get("shortener_link_id"),
        "qr_png_rel_path": qr_png_rel_path,
        "created_at": today,
        "updated_at": today,
    }

    # Replace existing entry for same talk_slug, or append
    replaced = False
    for i, existing in enumerate(tracking_db["qr_codes"]):
        if existing.get("talk_slug") == talk_slug:
            new_entry["created_at"] = existing.get("created_at", today)
            tracking_db["qr_codes"][i] = new_entry
            replaced = True
            break

    if not replaced:
        tracking_db["qr_codes"].append(new_entry)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Generate a QR code and insert it into a PowerPoint deck.",
        epilog="Examples:\n"
               "  %(prog)s deck.pptx --talk-slug arc-of-ai --shownotes-url https://jbaru.ch/arc-of-ai\n"
               "  %(prog)s deck.pptx --talk-slug arc-of-ai --short-url https://bit.ly/arcofai\n"
               "  %(prog)s deck.pptx --talk-slug arc-of-ai --shownotes-url URL --dry-run\n"
               "  %(prog)s --png-only --talk-slug SLUG --shownotes-url URL --output qr.png\n"
               "  %(prog)s --png-only --talk-slug SLUG --short-url URL --bg-color 128,0,128\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("deck", nargs="?", default=None, help="Path to the .pptx deck file (not required with --png-only)")
    parser.add_argument("--talk-slug", required=True, help="Unique talk identifier (e.g., arc-of-ai)")

    url_group = parser.add_mutually_exclusive_group(required=True)
    url_group.add_argument("--shownotes-url", help="Full shownotes URL (script resolves shortening)")
    url_group.add_argument("--short-url", help="Pre-resolved short URL (skip shortening)")

    parser.add_argument("--png-only", action="store_true",
                        help="Generate QR PNG only, without opening or modifying a deck")
    parser.add_argument("--output", metavar="PATH",
                        help="Output path for QR PNG (default: {deck_dir}/{talk-slug}-qr.png, or ./{talk-slug}-qr.png with --png-only)")
    parser.add_argument("--bg-color", metavar="R,G,B",
                        help="QR background color as R,G,B (e.g., 128,0,128). Default: detected from deck, or white with --png-only")
    parser.add_argument("--profile", help="Path to speaker-profile.json (default: {vault}/speaker-profile.json)")
    parser.add_argument("--vault", help="Path to vault root directory")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls and deck modification")

    args = parser.parse_args()

    if not args.png_only and not args.deck:
        parser.error("deck is required unless --png-only is specified")

    if args.deck and not os.path.isfile(args.deck):
        print(f"ERROR: Deck file not found: {args.deck}")
        sys.exit(1)

    # Determine vault path
    vault_path = args.vault
    if not vault_path:
        vault_path = os.path.expanduser("~/.claude/rhetoric-knowledge-vault")

    # Load config
    speaker_profile, secrets, tracking_db = load_vault_config(vault_path, args.profile)
    qr_config = speaker_profile.get("publishing_process", {}).get("qr_code", {})

    # Determine the URL to encode in the QR
    if args.short_url:
        # MCP-preresolved mode
        qr_url = args.short_url
        shownotes_url = args.shownotes_url or qr_url  # for tracking
        meta = {
            "talk_slug": args.talk_slug,
            "target_url": qr_url,
            "shortener": "mcp_preresolved",
            "short_path": None,
            "short_url": qr_url,
            "shortener_link_id": None,
        }
        print(f"Using pre-resolved short URL: {qr_url}")
    else:
        # Direct resolution mode
        shownotes_url = args.shownotes_url
        print(f"Resolving short URL for: {shownotes_url}")
        qr_url, meta = resolve_short_url(
            shownotes_url, args.talk_slug, qr_config, secrets, tracking_db, args.dry_run,
            vault_path=vault_path,
        )

    print(f"QR will encode: {qr_url}")

    # Parse --bg-color if provided
    explicit_bg = None
    if args.bg_color:
        try:
            parts = [int(x.strip()) for x in args.bg_color.split(",")]
            if len(parts) != 3 or not all(0 <= x <= 255 for x in parts):
                raise ValueError
            explicit_bg = tuple(parts)
        except ValueError:
            print(f"ERROR: --bg-color must be R,G,B with values 0-255 (got: {args.bg_color})")
            sys.exit(1)

    # --- PNG-only mode: no deck needed ---
    if args.png_only:
        qr_bg = explicit_bg or (255, 255, 255)
        qr_fg = choose_fg_color(qr_bg)
        print(f"QR colors: fg=RGB{qr_fg}, bg=RGB{qr_bg}")

        qr_filename = f"{args.talk_slug}-qr.png"
        qr_path = args.output or os.path.join(".", qr_filename)

        if not args.dry_run:
            generate_qr_png(qr_url, qr_fg, qr_bg, qr_path)
            size_kb = os.path.getsize(qr_path) / 1024
            print(f"QR PNG saved: {qr_path} ({size_kb:.1f} KB)")
        else:
            print(f"DRY RUN: would save QR to {qr_path}")

    # --- Deck mode: open deck, detect colors, insert ---
    else:
        prs = Presentation(args.deck)

        # Determine target slides
        target_url_for_detection = shownotes_url if args.shownotes_url else qr_url
        slide_indices = resolve_target_slide_indices(prs, qr_config, target_url_for_detection)
        print(f"Target slides: {[i + 1 for i in slide_indices]}")

        bg_match = qr_config.get("bg_color_match", True)
        deck_dir = os.path.dirname(os.path.abspath(args.deck))

        # Resolve background color per slide — different slides may have
        # different backgrounds (e.g., shownotes vs closing/thank-you).
        # Group slides by their QR color scheme to avoid redundant PNGs.
        slide_colors = {}  # idx -> (qr_bg, qr_fg)
        for idx in slide_indices:
            if explicit_bg:
                bg_rgb = explicit_bg
            else:
                slide_bg = resolve_slide_bg_rgb(prs.slides[idx])
                if slide_bg:
                    bg_rgb = slide_bg
                else:
                    print(f"  WARNING: Could not detect background for slide {idx + 1}, defaulting to white")
                    bg_rgb = (255, 255, 255)
            qr_bg = bg_rgb if bg_match else (255, 255, 255)
            qr_fg = choose_fg_color(qr_bg)
            slide_colors[idx] = (qr_bg, qr_fg)
            print(f"  Slide {idx + 1}: bg=RGB{qr_bg}, fg=RGB{qr_fg}")

        # Group slides by color scheme to generate minimal QR PNGs
        color_groups = {}  # (qr_bg, qr_fg) -> [slide_indices]
        for idx, colors in slide_colors.items():
            color_groups.setdefault(colors, []).append(idx)

        if not args.dry_run:
            qr_paths_generated = []
            insert_jobs = []  # (png_path, [1-based slide numbers]) — one per color variant
            for (qr_bg, qr_fg), indices in color_groups.items():
                if len(color_groups) == 1:
                    qr_filename = f"{args.talk_slug}-qr.png"
                else:
                    # Multiple color variants — suffix with bg hex
                    bg_hex = "{:02x}{:02x}{:02x}".format(*qr_bg)
                    qr_filename = f"{args.talk_slug}-qr-{bg_hex}.png"

                qr_path = args.output if (args.output and len(color_groups) == 1) else os.path.join(deck_dir, qr_filename)
                generate_qr_png(qr_url, qr_fg, qr_bg, qr_path)
                size_kb = os.path.getsize(qr_path) / 1024
                print(f"  QR PNG saved: {qr_filename} ({size_kb:.1f} KB) — for slide(s) {[i + 1 for i in indices]}")
                qr_paths_generated.append(qr_path)
                insert_jobs.append((qr_path, [i + 1 for i in indices]))  # VBA is 1-based

            # Release the read-only deck handle, then write via the real
            # PowerPoint app (valid OOXML; see rules/deck-editing-rules.md).
            prs = None
            here = os.path.dirname(os.path.abspath(__file__))
            insert_qr_via_powerpoint(args.deck, insert_jobs, here)
            print(f"Deck updated via PowerPoint: {args.deck}")
            # Use first generated path for tracking DB
            qr_filename = os.path.basename(qr_paths_generated[0])
        else:
            # Dry run — just report what would happen
            for (qr_bg, qr_fg), indices in color_groups.items():
                print(f"  DRY RUN: would generate QR bg=RGB{qr_bg} fg=RGB{qr_fg} for slides {[i + 1 for i in indices]}")
            qr_filename = f"{args.talk_slug}-qr.png"

    # Update tracking database
    meta["target_url"] = shownotes_url if args.shownotes_url else qr_url
    update_tracking_db(tracking_db, meta, qr_filename)

    if not args.dry_run:
        tdb_path = os.path.join(vault_path, "tracking-database.json")
        if os.path.isdir(vault_path):
            with open(tdb_path, "w", encoding="utf-8") as f:
                json.dump(tracking_db, f, indent=2, ensure_ascii=False)
            print(f"Tracking DB updated: {tdb_path}")
        else:
            print(f"  NOTE: Vault path {vault_path} not found, tracking DB not persisted")

    print("\nDone.")


if __name__ == "__main__":
    main()
