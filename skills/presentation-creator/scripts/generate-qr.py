#!/usr/bin/env python3
"""Generate a QR code and insert it into a PowerPoint deck.

Generates an unbranded QR code encoding a shownotes URL (optionally shortened
via bit.ly or rebrand.ly), matches the QR background color to the target slide,
auto-selects foreground color for contrast, and inserts the QR image into the
deck at the configured slide position.

Two URL-resolution modes:
  --shownotes-url URL   Script resolves shortening itself via {vault}/secrets.json
  --short-url URL       Agent pre-resolved the short URL (via MCP); script just
                        generates the QR and inserts it

Usage:
    python3 generate-qr.py <deck.pptx> --talk-slug SLUG --shownotes-url URL
    python3 generate-qr.py <deck.pptx> --talk-slug SLUG --short-url URL
    python3 generate-qr.py <deck.pptx> --talk-slug SLUG --shownotes-url URL --dry-run
    python3 generate-qr.py <deck.pptx> --talk-slug SLUG --shownotes-url URL --profile PATH --vault PATH

Requires:
    - python-pptx  (pip install python-pptx)
    - qrcode       (pip install qrcode)
    - Pillow       (pip install Pillow — transitive dep of python-pptx)
"""

import argparse
import datetime
import json
import os
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

from pptx import Presentation
from pptx.util import Inches, Emu
from pptx.dml.color import RGBColor

# --- Constants ---

QR_BOX_SIZE = 10       # pixels per QR module
QR_BORDER = 4          # quiet-zone modules
QR_ERROR_CORRECTION = ERROR_CORRECT_M

# QR placement: bottom-right, 2 inches wide, 0.3 inch margin from edges
QR_WIDTH_INCHES = 2.0
QR_MARGIN_INCHES = 0.3


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


def create_bitly_link(long_url, api_token, preferred_short_path=None):
    """Create a new bit.ly short link.

    Returns:
        dict with keys: short_url, link_id, short_path
    """
    payload = {"long_url": long_url}
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    result = _http_request(
        "https://api-ssl.bitly.com/v4/bitlinks",
        data=payload,
        headers=headers,
        method="POST",
    )
    return {
        "short_url": result["link"],
        "link_id": result["id"],
        "short_path": result["id"].split("/", 1)[-1] if "/" in result["id"] else result["id"],
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


def resolve_short_url(shownotes_url, talk_slug, config, secrets, tracking_db, dry_run=False):
    """Resolve the short URL for a talk, using cache or API as needed.

    Args:
        shownotes_url: The full shownotes URL to shorten
        talk_slug: Unique talk identifier
        config: QR config from speaker profile (publishing_process.qr_code)
        secrets: Parsed secrets.json
        tracking_db: Parsed tracking-database.json
        dry_run: If True, skip API calls

    Returns:
        tuple (short_url, metadata_dict)
        metadata_dict has keys: shortener, short_path, link_id, short_url, target_url
    """
    shortener = config.get("shortener", "none")
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

    if shortener == "none":
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

    preferred_short_path = config.get("preferred_short_path")

    try:
        if shortener == "bitly":
            api_token = secrets.get("bitly", {}).get("api_token")
            if not api_token:
                print("  WARNING: No bitly.api_token in secrets.json, falling back to raw URL")
                return shownotes_url, _none_meta(talk_slug, shownotes_url)

            if existing and existing.get("shortener_link_id"):
                # Update existing link target
                print(f"  Updating bit.ly link {existing['shortener_link_id']} → {shownotes_url}")
                update_bitly_link(existing["shortener_link_id"], shownotes_url, api_token)
                meta = dict(existing)
                meta["target_url"] = shownotes_url
                meta["updated_at"] = datetime.date.today().isoformat()
                return existing["short_url"], meta
            else:
                # Create new link
                print(f"  Creating bit.ly link for {shownotes_url}")
                result = create_bitly_link(shownotes_url, api_token, preferred_short_path)
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
                print("  WARNING: No rebrandly.api_key in secrets.json, falling back to raw URL")
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
                print(f"  Creating rebrand.ly link for {shownotes_url}")
                result = create_rebrandly_link(shownotes_url, api_key, domain, preferred_short_path)
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

    if not indices:
        # Default: last slide
        indices.append(slide_count - 1)

    return sorted(indices)


# --- QR Insertion ---

def insert_qr_on_slides(prs, png_path, slide_indices):
    """Insert the QR PNG on the specified slides, bottom-right corner.

    Args:
        prs: Presentation object (mutated in place)
        png_path: Path to the QR PNG file
        slide_indices: List of 0-based slide indices
    """
    slide_width = prs.slide_width
    slide_height = prs.slide_height

    qr_width = Inches(QR_WIDTH_INCHES)
    # Maintain square aspect ratio
    qr_height = qr_width

    margin = Inches(QR_MARGIN_INCHES)
    left = slide_width - qr_width - margin
    top = slide_height - qr_height - margin

    for idx in slide_indices:
        slide = prs.slides[idx]
        slide.shapes.add_picture(png_path, left, top, qr_width, qr_height)
        print(f"  Inserted QR on slide {idx + 1}")


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
               "  %(prog)s deck.pptx --talk-slug arc-of-ai --shownotes-url URL --dry-run\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("deck", help="Path to the .pptx deck file")
    parser.add_argument("--talk-slug", required=True, help="Unique talk identifier (e.g., arc-of-ai)")

    url_group = parser.add_mutually_exclusive_group(required=True)
    url_group.add_argument("--shownotes-url", help="Full shownotes URL (script resolves shortening)")
    url_group.add_argument("--short-url", help="Pre-resolved short URL (skip shortening)")

    parser.add_argument("--profile", help="Path to speaker-profile.json (default: {vault}/speaker-profile.json)")
    parser.add_argument("--vault", help="Path to vault root directory")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls and deck modification")

    args = parser.parse_args()

    if not os.path.isfile(args.deck):
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
            shownotes_url, args.talk_slug, qr_config, secrets, tracking_db, args.dry_run
        )

    print(f"QR will encode: {qr_url}")

    # Open the deck
    prs = Presentation(args.deck)

    # Determine target slides
    target_url_for_detection = shownotes_url if args.shownotes_url else qr_url
    slide_indices = resolve_target_slide_indices(prs, qr_config, target_url_for_detection)
    print(f"Target slides: {[i + 1 for i in slide_indices]}")

    # Resolve background color from the first target slide
    target_slide = prs.slides[slide_indices[0]]
    bg_rgb = resolve_slide_bg_rgb(target_slide)
    if bg_rgb:
        print(f"Slide background: RGB{bg_rgb}")
    else:
        print("  WARNING: Could not detect solid background color, defaulting to white")
        bg_rgb = (255, 255, 255)

    bg_match = qr_config.get("bg_color_match", True)
    qr_bg = bg_rgb if bg_match else (255, 255, 255)
    qr_fg = choose_fg_color(qr_bg)
    print(f"QR colors: fg=RGB{qr_fg}, bg=RGB{qr_bg}")

    # Generate QR PNG
    deck_dir = os.path.dirname(os.path.abspath(args.deck))
    qr_filename = f"{args.talk_slug}-qr.png"
    qr_path = os.path.join(deck_dir, qr_filename)

    if not args.dry_run:
        generate_qr_png(qr_url, qr_fg, qr_bg, qr_path)
        size_kb = os.path.getsize(qr_path) / 1024
        print(f"QR PNG saved: {qr_path} ({size_kb:.1f} KB)")

        # Insert into deck
        insert_qr_on_slides(prs, qr_path, slide_indices)
        prs.save(args.deck)
        print(f"Deck saved: {args.deck}")
    else:
        print(f"DRY RUN: would save QR to {qr_path}")
        print(f"DRY RUN: would insert on slides {[i + 1 for i in slide_indices]}")

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
