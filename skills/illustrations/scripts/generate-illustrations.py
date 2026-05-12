#!/usr/bin/env python3
"""
Generate illustrations for a presentation outline.

Parses the outline markdown for style anchors and per-slide image prompts,
generates images via the appropriate vendor API (Google Gemini, Google
Imagen, or OpenAI — dispatched by model-name prefix), and saves them
to an illustrations/ directory.

Usage:
    python3 generate-illustrations.py <outline.md> all
    python3 generate-illustrations.py <outline.md> remaining
    python3 generate-illustrations.py <outline.md> 2 5 9
    python3 generate-illustrations.py <outline.md> 2-10
    python3 generate-illustrations.py <outline.md> --compare 2
    python3 generate-illustrations.py <outline.md> --edit 5 "Erase the label"
    python3 generate-illustrations.py <outline.md> --build 5
    python3 generate-illustrations.py <outline.md> --build all
    python3 generate-illustrations.py <outline.md> --fix 5 "Make the road wider"
    python3 generate-illustrations.py <outline.md> -v 2 5 9

Requires:
    - For Google models (gemini-*, nano-banana-*, imagen-*):
        Gemini API key in {vault}/secrets.json (preferred) or
        GEMINI_API_KEY env var (fallback).
    - For OpenAI models (gpt-image-*):
        OpenAI API key in {vault}/secrets.json under "openai".api_key
        or OPENAI_API_KEY env var (fallback).
    - Python 3.7+ (stdlib only — no pip install needed)
"""

import argparse
import base64
import glob
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid

# --- Constants ---

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
OPENAI_API_BASE = "https://api.openai.com/v1"

# Curated list of current flagship image-generation models from major vendors.
# Used by --compare mode. The illustrations skill's Step 2 (model-freshness
# check) tracks this list — bump it when newer flagships ship rather than
# leaving stale entries in place.
COMPARE_MODELS = [
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-image-preview",
    "nano-banana-pro-preview",
    "imagen-4.0-ultra-generate-001",
    "gpt-image-2",
]

# Per-format sizing for vendors that take explicit size / aspect-ratio
# params. Gemini infers aspect from prompt hints, so it doesn't appear
# here. The "FULL" entry is also the unknown-format fallback.
#   openai_size:  gpt-image-* accepts 2048x1152 (true 16:9) and
#                 1024x1536 (true 2:3 portrait).
#   imagen_aspect: Imagen :predict accepts 1:1, 9:16, 16:9, 3:4, 4:3.
#                  3:4 is closest to the IMG+TXT 2:3 anchor (Imagen
#                  has no native 2:3).
FORMAT_SIZING = {
    "FULL": {"openai_size": "2048x1152", "imagen_aspect": "16:9"},
    "IMG+TXT": {"openai_size": "1024x1536", "imagen_aspect": "3:4"},
}
OPENAI_DEFAULT_SIZE = FORMAT_SIZING["FULL"]["openai_size"]
IMAGEN_DEFAULT_ASPECT = FORMAT_SIZING["FULL"]["imagen_aspect"]


def sizing_for(slide_format):
    """Look up vendor-specific sizing for a slide format.

    Unknown / missing formats fall back to FULL (16:9 landscape) — that's
    the historical default and matches the typical deck slide.
    """
    return FORMAT_SIZING.get(slide_format, FORMAT_SIZING["FULL"])

RATE_LIMIT_DELAY = 5  # seconds between API requests

IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]

# --- Title safe-zone policy (see rules/title-overlay-rules.md) ---

VALID_SAFE_ZONES = {
    "upper_third", "middle_third", "lower_third",
    "left_half", "right_half",
}

DEFAULT_SAFE_ZONE_SURFACE = {
    "upper_third": "a clean uniform region at the top of the frame, drawn from the style's established backdrop",
    "middle_third": "a clean uninterrupted region at the center of the frame, framed by the subject on top and bottom",
    "lower_third": "a clean uniform region at the bottom of the frame, drawn from the style's established backdrop",
    "left_half": "a clean uniform region covering the left half of the frame, drawn from the style's established backdrop",
    "right_half": "a clean uniform region covering the right half of the frame, drawn from the style's established backdrop",
}

SAFE_ZONE_DIRECTIVE_TEMPLATE = (
    " TITLE SAFE ZONE -- CRITICAL COMPOSITION RULE: Reserve the "
    "{zone_words} of the 16:9 frame as clean uninterrupted negative "
    "space filled only with {surface}. No subjects, objects, text, "
    "props, or focal points may appear in this region. The scene's "
    "subjects must be composed entirely in the remaining portion of "
    "the frame. This negative space will carry an overlaid title."
)

# Canonical MIME <-> extension mapping
_MIME_EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_EXT_MIME_MAP = {v: k for k, v in _MIME_EXT_MAP.items()}
_EXT_MIME_MAP[".jpeg"] = "image/jpeg"  # common alias

_VERSION_RE = re.compile(r"-v(\d+)")

_cli_vault_path = None  # set by main() from --vault arg


# --- Model Family Dispatch ---

def model_family(model_name):
    """Classify a model into a vendor family for endpoint dispatch.

    Families:
        - "openai" — gpt-image-* (OpenAI /images/generations + /images/edits)
        - "imagen" — imagen-* (Google /v1beta/models/<m>:predict)
        - "gemini" — everything else, currently gemini-* and nano-banana-*
          (Google /v1beta/models/<m>:generateContent)
    """
    name = model_name.lower()
    if name.startswith("gpt-image"):
        return "openai"
    if name.startswith("imagen"):
        return "imagen"
    return "gemini"


def family_key_name(family):
    """Map a model family to the secrets.json key name it requires.

    Imagen and Gemini both authenticate with the Google AI Studio key.
    """
    if family == "openai":
        return "openai"
    return "gemini"


# --- Outline Parsing ---

def parse_outline(path):
    """Parse a presentation outline markdown file.

    Returns:
        dict with keys:
            model: str — model name from the header
            anchors: dict[str, str] — format name → anchor paragraph
            slides: list[dict] — each with slide_num, title, format, prompt
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    result = {
        "model": None,
        "anchors": {},
        "slides": [],
    }

    # Extract model name: **Model:** `model-name`
    model_match = re.search(r"\*\*Model:\*\*\s*`([^`]+)`", text)
    if model_match:
        result["model"] = model_match.group(1)

    # Extract style anchors: ### STYLE ANCHOR (FORMAT — dimensions)\n> paragraph
    # Format tokens may include `+` and `-` (e.g. IMG+TXT) — match the
    # parser used by the per-slide Format: line below.
    anchor_pattern = re.compile(
        r"###\s+STYLE ANCHOR\s+\(([\w+-]+)\s*—[^)]*\)\s*\n>\s*(.+?)(?=\n###|\n---|\n##|\Z)",
        re.DOTALL,
    )
    for match in anchor_pattern.finditer(text):
        format_name = match.group(1).strip()
        anchor_text = match.group(2).strip()
        # Collapse multi-line blockquote into single paragraph
        anchor_text = re.sub(r"\n>\s*", " ", anchor_text)
        result["anchors"][format_name] = anchor_text

    # Extract per-slide data
    slide_pattern = re.compile(
        r"###\s+Slide\s+(\d+):\s*(.+?)(?=\n###|\n##|\Z)", re.DOTALL
    )
    for match in slide_pattern.finditer(text):
        slide_num = int(match.group(1))
        title = match.group(2).split("\n")[0].strip()
        block = match.group(0)

        # Extract format
        # Allow `+` and `-` inside format tokens (e.g. IMG+TXT, IMG-TXT) on
        # top of \w's alphanumerics+underscore. The downstream apply script's
        # regex already permits IMG+TXT explicitly — keep these in sync.
        fmt_match = re.search(r"-\s*Format:\s*\*\*([\w+-]+)\*\*", block)
        slide_format = fmt_match.group(1) if fmt_match else None

        # Extract image prompt
        prompt_match = re.search(r"-\s*Image prompt:\s*`(.+?)`", block, re.DOTALL)
        prompt = prompt_match.group(1).strip() if prompt_match else None

        # Extract optional Safe zone: <zone> (<surface>)
        safe_zone = None
        _zone_alt = "|".join(VALID_SAFE_ZONES)
        zone_match = re.search(
            rf"-\s*Safe zone:\s*({_zone_alt})"
            r"(?:\s*\(([^)]+)\))?",
            block,
        )
        if zone_match:
            zone = zone_match.group(1)
            surface = (zone_match.group(2) or "").strip() or None
            safe_zone = {"zone": zone, "surface": surface}
        elif re.search(r"-\s*Safe zone:", block):
            print(
                f"  WARNING: Slide {slide_num}: Safe zone field present but invalid; "
                f"expected one of {', '.join(sorted(VALID_SAFE_ZONES))}"
            )

        # Extract build specifications
        builds = None
        builds_match = re.search(r"-\s*Builds:\s*(\d+)\s+steps?", block)
        if builds_match:
            build_count = int(builds_match.group(1))
            build_steps = []
            build_step_pattern = re.compile(
                r"-\s*build-(\d+):\s*(.+?)(?=\n\s*-\s*build-|\n\s*(?!-\s*build-)|\Z)",
                re.DOTALL,
            )
            for bm in build_step_pattern.finditer(block):
                step_num = int(bm.group(1))
                step_desc = bm.group(2).strip().split("\n")[0].strip()
                is_full = "[FULL]" in step_desc
                build_steps.append({
                    "step": step_num,
                    "description": step_desc,
                    "is_full": is_full,
                })
            builds = {
                "count": build_count,
                "steps": sorted(build_steps, key=lambda s: s["step"]),
            }

        if prompt:
            slide_data = {
                "slide_num": slide_num,
                "title": title,
                "format": slide_format,
                "prompt": prompt,
            }
            if safe_zone:
                slide_data["safe_zone"] = safe_zone
            if builds:
                slide_data["builds"] = builds
            result["slides"].append(slide_data)

    return result


def resolve_prompt(prompt, slide_format, anchors):
    """Replace [STYLE ANCHOR] token with the actual anchor text for the format."""
    if "[STYLE ANCHOR]" not in prompt:
        return prompt

    # Try the slide's format first, then fall back to first available anchor
    anchor = anchors.get(slide_format)
    if not anchor and anchors:
        anchor = next(iter(anchors.values()))
    if not anchor:
        print(f"  WARNING: No style anchor found for format '{slide_format}'")
        return prompt.replace("[STYLE ANCHOR].", "").replace("[STYLE ANCHOR]", "")

    return prompt.replace("[STYLE ANCHOR]", anchor)


def apply_safe_zone_directive(prompt, safe_zone, slide_format=None, slide_label=None):
    """Append the SAFE ZONE directive to a prompt when safe_zone is set.

    See rules/title-overlay-rules.md for the policy. Idempotent: if the
    prompt already contains a TITLE SAFE ZONE block, it is stripped
    before the new directive is appended (or before the non-16:9 early
    return, so a stale 16:9 directive doesn't survive a FULL→IMG+TXT
    format change on the same slide).

    Safe-zone composition is meaningful only for 16:9 frames. The skip
    decision is sourced from FORMAT_SIZING via `sizing_for()` — formats
    that map to a non-16:9 imagen aspect (IMG+TXT → 3:4) are skipped
    with a warning. Unknown / talk-specific format tokens (DIAGRAM,
    QUOTE, WIDE, etc.) fall through `sizing_for`'s FULL fallback and
    receive the directive — matching apply-illustrations-to-deck.py's
    behavior of treating Safe zone: presence as the title-overlay
    signal regardless of format token.

    `slide_label` (e.g. "5 (The Question)") is prepended to the warning
    so the operator can identify which outline entry needs fixing even
    when the warning fires before the per-slide header prints.
    """
    if not safe_zone:
        return prompt

    # Strip any stale directive first so a prior FULL run doesn't leak
    # into a non-16:9 early return or a fresh FULL append.
    if "TITLE SAFE ZONE" in prompt:
        prompt = prompt.split("TITLE SAFE ZONE", 1)[0].rstrip()

    # Skip when the format has known non-16:9 sizing (currently only
    # IMG+TXT → 3:4). Unknown formats fall back to FULL/16:9 and get
    # the directive.
    if (
        slide_format is not None
        and sizing_for(slide_format)["imagen_aspect"] != "16:9"
    ):
        label_prefix = f"Slide {slide_label}: " if slide_label else ""
        print(
            f"  WARNING: {label_prefix}Safe zone directive skipped — "
            f"Format: {slide_format} is a non-16:9 format (per "
            "FORMAT_SIZING). Safe zones only make sense for 16:9 slides; "
            "remove the `Safe zone:` line from this outline block to "
            "silence this warning, or change the slide's Format to a "
            "16:9 token."
        )
        return prompt
    zone = safe_zone["zone"]
    if zone not in VALID_SAFE_ZONES:
        return prompt
    surface = safe_zone.get("surface") or DEFAULT_SAFE_ZONE_SURFACE[zone]
    directive = SAFE_ZONE_DIRECTIVE_TEMPLATE.format(
        zone_words=zone.replace("_", " "),
        surface=surface,
    )
    return prompt + directive


# --- Slide Number Selection ---

def parse_slide_selection(args, available_slides, output_dir):
    """Parse CLI slide selection into a list of slide numbers.

    Args:
        args: list of CLI arguments after the outline path
        available_slides: list of slide dicts from parse_outline
        output_dir: path to illustrations/ directory

    Returns:
        list of slide numbers to generate
    """
    all_nums = [s["slide_num"] for s in available_slides]

    if not args or args[0] == "all":
        return all_nums

    if args[0] == "remaining":
        existing = set()
        for pattern in [os.path.join(output_dir, f"slide-{n:02d}.*") for n in all_nums]:
            existing.update(
                int(m.group(1))
                for f in glob.glob(pattern)
                if (m := re.search(r"slide-(\d+)", f))
            )
        return [n for n in all_nums if n not in existing]

    # Explicit numbers: "2 5 9" or "2-10"
    selected = set()
    for arg in args:
        if "-" in arg and not arg.startswith("-"):
            start, end = arg.split("-", 1)
            selected.update(range(int(start), int(end) + 1))
        else:
            selected.add(int(arg))

    return sorted(n for n in selected if n in all_nums)


# --- File Helpers ---

def find_base_image(output_dir, slide_num):
    """Find the unversioned base image for a slide, or None."""
    for ext in IMAGE_EXTENSIONS:
        candidate = os.path.join(output_dir, f"slide-{slide_num:02d}{ext}")
        if os.path.isfile(candidate):
            return candidate
    return None


def find_latest_image(output_dir, slide_num):
    """Find the latest version of a slide image (versioned or base), or None."""
    versioned = []
    for f in glob.glob(os.path.join(output_dir, f"slide-{slide_num:02d}-v*.*")):
        m = _VERSION_RE.search(f)
        if m:
            versioned.append((int(m.group(1)), f))
    if versioned:
        versioned.sort()
        return versioned[-1][1]
    return find_base_image(output_dir, slide_num)


def final_build_dest(builds_dir, slide_num, final_step, source_path):
    """Compose the final-build destination path, preserving the source extension.

    The final build step is a verbatim copy of the slide's base image —
    keeping its extension matters because base images may be .jpg / .png /
    .webp depending on the generating vendor.
    """
    src_ext = os.path.splitext(source_path)[1].lower() or ".jpg"
    return os.path.join(builds_dir, f"slide-{slide_num:02d}-build-{final_step:02d}{src_ext}")


def next_version(output_dir, slide_num):
    """Find the next available version number for a slide."""
    existing = glob.glob(os.path.join(output_dir, f"slide-{slide_num:02d}-v*.*"))
    if not existing:
        return 2
    versions = [int(m.group(1)) for f in existing if (m := _VERSION_RE.search(f))]
    return max(versions, default=1) + 1


def mime_to_ext(mime_type):
    """Convert MIME type to file extension."""
    return _MIME_EXT_MAP.get(mime_type, ".png")


def ext_to_mime(ext):
    """Convert file extension to MIME type."""
    return _EXT_MIME_MAP.get(ext.lower(), "image/jpeg")


# --- Shared Setup ---

def load_secrets(vault_path=None):
    """Load API keys from vault secrets.json with env-var fallbacks.

    Resolution order per vendor:
        1. {vault}/secrets.json → gemini.api_key / openai.api_key
        2. GEMINI_API_KEY / OPENAI_API_KEY env vars

    Returns:
        tuple (keys_dict, secrets_path) where keys_dict maps
        "gemini" / "openai" → key string or None.
    """
    keys = {"gemini": None, "openai": None}

    if vault_path is None:
        vault_path = _cli_vault_path
    if vault_path is None:
        vault_path = os.path.expanduser("~/.claude/rhetoric-knowledge-vault")
    secrets_path = os.path.join(vault_path, "secrets.json")

    if os.path.isfile(secrets_path):
        try:
            with open(secrets_path, "r", encoding="utf-8") as f:
                secrets = json.load(f)
            keys["gemini"] = secrets.get("gemini", {}).get("api_key") or None
            keys["openai"] = secrets.get("openai", {}).get("api_key") or None
        except json.JSONDecodeError as e:
            print(
                f"WARNING: {secrets_path} is not valid JSON ({e}); "
                "falling back to environment variables. Fix the file or "
                "delete it to silence this warning.",
                file=sys.stderr,
            )
        except OSError as e:
            print(
                f"WARNING: {secrets_path} could not be read ({e}); "
                "falling back to environment variables. Check file "
                "permissions.",
                file=sys.stderr,
            )

    if not keys["gemini"]:
        keys["gemini"] = os.environ.get("GEMINI_API_KEY") or None
    if not keys["openai"]:
        keys["openai"] = os.environ.get("OPENAI_API_KEY") or None

    return keys, secrets_path


def _require_keys_for_families(keys, families, secrets_path):
    """Verify keys needed for the given model families are present.

    Exits with an actionable per-vendor message if any required key
    is missing.
    """
    needed = {family_key_name(f) for f in families}
    missing = sorted(k for k in needed if not keys.get(k))
    if not missing:
        return

    print("ERROR: Missing API key(s) for the model(s) you're using.")
    secrets_exists = os.path.isfile(secrets_path)
    for k in missing:
        if k == "gemini":
            print()
            print("  Gemini and Imagen models need a Google AI Studio key.")
            print("  Get one at: https://aistudio.google.com/app/apikey")
            if secrets_exists:
                print(f"  Add to {secrets_path}:")
                print('    "gemini": {"api_key": "YOUR_KEY"}')
            else:
                print(f"  Create {secrets_path}:")
                print(f'    echo \'{{"gemini": {{"api_key": "YOUR_KEY"}}}}\' > {secrets_path}')
                print(f"    chmod 600 {secrets_path}")
            print("  Or set the GEMINI_API_KEY environment variable.")
        elif k == "openai":
            print()
            print("  OpenAI gpt-image-* models need an OpenAI API key.")
            print("  Get one at: https://platform.openai.com/api-keys")
            if secrets_exists:
                print(f"  Add to {secrets_path}:")
                print('    "openai": {"api_key": "YOUR_KEY"}')
            else:
                print(f"  Create {secrets_path}:")
                print(f'    echo \'{{"openai": {{"api_key": "YOUR_KEY"}}}}\' > {secrets_path}')
                print(f"    chmod 600 {secrets_path}")
            print("  Or set the OPENAI_API_KEY environment variable.")
    sys.exit(1)


def _load_context(outline_path, require_model=True, vault_path=None, compare_mode=False):
    """Common preamble: load API keys, parse outline, compute paths.

    Determines which vendor families need keys based on:
        - compare_mode=True → every family in COMPARE_MODELS + outline's
          baked Model (if any)
        - compare_mode=False → just the outline's Model family

    Returns:
        tuple (keys, outline, output_dir) where keys is a dict
        {"gemini": str|None, "openai": str|None}.
    """
    keys, secrets_path = load_secrets(vault_path)
    outline = parse_outline(outline_path)

    if require_model and not outline["model"]:
        print("ERROR: No model found in outline. Add a **Model:** `model-name` line")
        print("to the Illustration Style Anchor section.")
        sys.exit(1)

    families = set()
    if compare_mode:
        for m in COMPARE_MODELS:
            families.add(model_family(m))
        if outline["model"]:
            families.add(model_family(outline["model"]))
    elif outline["model"]:
        families.add(model_family(outline["model"]))
    else:
        families.add("gemini")

    _require_keys_for_families(keys, families, secrets_path)

    output_dir = os.path.join(
        os.path.dirname(os.path.abspath(outline_path)), "illustrations"
    )
    return keys, outline, output_dir


# --- Gemini API ---

def _call_gemini(parts, model, api_key):
    """Send parts to the Gemini generateContent API and extract the image.

    Args:
        parts: list of content parts (text, inlineData, etc.)
        model: Gemini model name
        api_key: API key

    Returns:
        tuple (image_bytes, mime_type) on success, or (None, error_message) on failure.
    """
    url = f"{GEMINI_API_BASE}/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return None, f"HTTP {e.code}: {error_body[:500]}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return None, str(e)

    # Extract image from response
    try:
        for candidate in body.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "inlineData" in part:
                    inline = part["inlineData"]
                    image_bytes = base64.b64decode(inline["data"])
                    mime_type = inline.get("mimeType", "image/png")
                    return image_bytes, mime_type
    except (KeyError, IndexError):
        pass

    return None, f"No image in response: {json.dumps(body)[:500]}"


def _call_imagen(prompt, model, api_key, aspect_ratio=IMAGEN_DEFAULT_ASPECT):
    """Send a prompt to Google's Imagen :predict endpoint.

    Imagen uses a different endpoint shape from Gemini's generateContent.
    Aspect ratio is set via the parameters block, not inferred from prompt.

    Returns:
        tuple (image_bytes, mime_type) on success, or (None, error_message) on failure.
    """
    url = f"{GEMINI_API_BASE}/{model}:predict?key={api_key}"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": aspect_ratio},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return None, f"HTTP {e.code}: {error_body[:500]}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return None, str(e)

    preds = body.get("predictions", [])
    if preds and preds[0].get("bytesBase64Encoded"):
        image_bytes = base64.b64decode(preds[0]["bytesBase64Encoded"])
        mime = preds[0].get("mimeType", "image/png")
        return image_bytes, mime
    return None, f"No image in Imagen response: {json.dumps(body)[:500]}"


# --- OpenAI API ---

def _multipart_body(fields, files):
    """Build a multipart/form-data body. Returns (bytes, boundary)."""
    boundary = "----GenIllustBnd" + uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
        body += str(v).encode("utf-8")
        body += b"\r\n"
    for name, filename, mime, content in files:
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\n'
        ).encode()
        body += f"Content-Type: {mime}\r\n\r\n".encode()
        body += content
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), boundary


def _extract_openai_image(body):
    """Pull image bytes + mime from an OpenAI Images API response body."""
    data_arr = body.get("data", [])
    if not data_arr:
        return None, f"No data in OpenAI response: {json.dumps(body)[:500]}"
    first = data_arr[0]
    if first.get("b64_json"):
        return base64.b64decode(first["b64_json"]), "image/png"
    if first.get("url"):
        try:
            with urllib.request.urlopen(first["url"], timeout=120) as r:
                return r.read(), "image/png"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return None, f"Failed to fetch image URL: {e}"
    return None, f"OpenAI response has neither b64_json nor url: {json.dumps(first)[:500]}"


def _call_openai_generate(prompt, model, api_key, size=OPENAI_DEFAULT_SIZE):
    """Call OpenAI /images/generations to produce a fresh image."""
    url = f"{OPENAI_API_BASE}/images/generations"
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": "high",
        "n": 1,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return None, f"HTTP {e.code}: {error_body[:500]}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return None, str(e)

    return _extract_openai_image(body)


def _call_openai_edit(input_path, prompt, model, api_key, size=OPENAI_DEFAULT_SIZE):
    """Call OpenAI /images/edits to edit an existing image."""
    with open(input_path, "rb") as f:
        image_bytes = f.read()
    ext = os.path.splitext(input_path)[1].lower()
    mime = ext_to_mime(ext)
    filename = os.path.basename(input_path)

    body, boundary = _multipart_body(
        fields={"model": model, "prompt": prompt, "size": size,
                "quality": "high", "n": "1"},
        files=[("image", filename, mime, image_bytes)],
    )
    url = f"{OPENAI_API_BASE}/images/edits"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=500) as resp:
            resp_body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return None, f"HTTP {e.code}: {error_body[:500]}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return None, str(e)

    return _extract_openai_image(resp_body)


# --- Vendor-Agnostic Dispatchers ---

def generate_image(prompt, model, keys, slide_format=None):
    """Generate a fresh image via the appropriate vendor endpoint.

    Args:
        prompt: text prompt
        model: model name (dispatch is by name prefix — see model_family)
        keys: dict from load_secrets() — {"gemini": ..., "openai": ...}
        slide_format: outline format name (e.g. "FULL", "IMG+TXT") used to
            pick the per-vendor size / aspect-ratio param. Falls back to
            FULL (16:9 landscape) when None or unknown.

    Returns:
        tuple (image_bytes, mime_type) on success, or (None, error_message) on failure.
    """
    family = model_family(model)
    sizing = sizing_for(slide_format)
    if family == "openai":
        return _call_openai_generate(
            prompt, model, keys["openai"], size=sizing["openai_size"]
        )
    if family == "imagen":
        return _call_imagen(
            prompt, model, keys["gemini"], aspect_ratio=sizing["imagen_aspect"]
        )
    return _call_gemini([{"text": prompt}], model, keys["gemini"])


def edit_image(input_path, edit_prompt, model, keys, slide_format=None):
    """Edit an existing image via the appropriate vendor endpoint.

    Auto-appends vendor-agnostic safety suffixes to the prompt to prevent
    unwanted additions and patch artifacts.

    Args:
        slide_format: see generate_image — controls OpenAI edit size so
            the output matches the source slide's geometry.

    Returns:
        tuple (image_bytes, mime_type) on success, or (None, error_message) on failure.
    """
    suffixes = []
    lower_prompt = edit_prompt.lower()
    if "do not add any new elements" not in lower_prompt:
        suffixes.append("DO NOT add any new elements.")
    if "let background continue naturally" not in lower_prompt:
        suffixes.append("Let background continue naturally -- no parchment patch.")
    if suffixes:
        edit_prompt = edit_prompt.rstrip(". ") + ". " + " ".join(suffixes)

    family = model_family(model)
    sizing = sizing_for(slide_format)
    if family == "openai":
        return _call_openai_edit(
            input_path, edit_prompt, model, keys["openai"], size=sizing["openai_size"]
        )
    if family == "imagen":
        return None, (
            f"Image editing is not supported for Imagen models ({model}). "
            "Imagen has no public edit endpoint — use a Gemini or OpenAI "
            "model for --edit / --build / --fix workflows."
        )

    # Gemini path: send image as base64 inline data on generateContent
    with open(input_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(input_path)[1].lower()
    input_mime = ext_to_mime(ext)
    parts = [
        {"inlineData": {"mimeType": input_mime, "data": image_data}},
        {"text": edit_prompt},
    ]
    return _call_gemini(parts, model, keys["gemini"])


# --- Main Commands ---

def run_generate(outline_path, slide_args, versioned=False):
    """Generate illustrations for selected slides."""
    keys, outline, output_dir = _load_context(outline_path)
    model = outline["model"]
    os.makedirs(output_dir, exist_ok=True)

    if not outline["slides"]:
        print("No slides with image prompts found in the outline.")
        sys.exit(0)

    to_generate = parse_slide_selection(slide_args, outline["slides"], output_dir)

    if not to_generate:
        print("Nothing to generate — all requested slides already have images.")
        sys.exit(0)

    slides_by_num = {s["slide_num"]: s for s in outline["slides"]}

    print(f"Model: {model}")
    print(f"Style anchors: {', '.join(outline['anchors'].keys()) or 'none'}")
    print(f"Generating {len(to_generate)} illustration(s): slides {', '.join(map(str, to_generate))}")
    if versioned:
        print("Versioned mode: saving as slide-NN-vM.ext (never overwrites)")
    print(f"Output: {output_dir}/")
    print()

    success = 0
    failed = 0

    for i, num in enumerate(to_generate):
        slide = slides_by_num[num]
        prompt = resolve_prompt(slide["prompt"], slide["format"], outline["anchors"])
        prompt = apply_safe_zone_directive(
            prompt,
            slide.get("safe_zone"),
            slide["format"],
            slide_label=f"{num} ({slide['title']})",
        )

        print(f"[{i+1}/{len(to_generate)}] Slide {num}: {slide['title']}")

        image_bytes, result = generate_image(prompt, model, keys, slide["format"])

        if image_bytes is None:
            print(f"  FAILED: {result}")
            failed += 1
        else:
            ext = mime_to_ext(result)
            if versioned:
                ver = next_version(output_dir, num)
                filename = f"slide-{num:02d}-v{ver}{ext}"
            else:
                filename = f"slide-{num:02d}{ext}"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            size_kb = len(image_bytes) / 1024
            print(f"  OK: {filename} ({size_kb:.0f} KB)")
            success += 1

        # Rate limiting between requests
        if i < len(to_generate) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    print()
    print(f"Done: {success} generated, {failed} failed, out of {len(to_generate)} requested.")


def run_compare(outline_path, slide_num):
    """Generate the same prompt across multiple models for comparison."""
    keys, outline, _ = _load_context(outline_path, require_model=False, compare_mode=True)

    slides_by_num = {s["slide_num"]: s for s in outline["slides"]}
    if slide_num not in slides_by_num:
        print(f"ERROR: Slide {slide_num} has no image prompt in the outline.")
        available = sorted(slides_by_num.keys())
        print(f"Available slides with prompts: {', '.join(map(str, available))}")
        sys.exit(1)

    slide = slides_by_num[slide_num]
    prompt = resolve_prompt(slide["prompt"], slide["format"], outline["anchors"])
    prompt = apply_safe_zone_directive(
        prompt,
        slide.get("safe_zone"),
        slide["format"],
        slide_label=f"{slide_num} ({slide['title']})",
    )

    output_dir = os.path.join(
        os.path.dirname(os.path.abspath(outline_path)),
        "illustrations",
        "model-comparison",
    )
    os.makedirs(output_dir, exist_ok=True)

    # Use outline model + the comparison list, deduplicated
    models = []
    if outline["model"] and outline["model"] not in COMPARE_MODELS:
        models.append(outline["model"])
    models.extend(COMPARE_MODELS)

    print(f"Comparing {len(models)} models using slide {slide_num}: {slide['title']}")
    print(f"Prompt: {prompt[:120]}...")
    print(f"Output: {output_dir}/")
    print()

    results = []

    for i, model in enumerate(models):
        print(f"[{i+1}/{len(models)}] {model}...", end=" ", flush=True)

        image_bytes, result = generate_image(prompt, model, keys, slide["format"])

        if image_bytes is None:
            print(f"FAILED: {result[:100]}")
            results.append((model, "FAIL", "-", "-"))
        else:
            ext = mime_to_ext(result)
            safe_model = model.replace("/", "_")
            filename = f"slide-{slide_num:02d}-{safe_model}{ext}"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            size_kb = len(image_bytes) / 1024
            print(f"OK ({size_kb:.0f} KB)")
            results.append((model, "OK", f"{size_kb:.0f} KB", filepath))

        if i < len(models) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    # Summary table
    print()
    print("MODEL COMPARISON RESULTS")
    print("=" * 70)
    print(f"{'Model':<45} {'Status':<8} {'Size':<10}")
    print("-" * 70)
    for model, status, size, path in results:
        print(f"{model:<45} {status:<8} {size:<10}")
    print("=" * 70)
    print()
    print(f"Review images in: {output_dir}/")
    print("Set your chosen model in the outline: **Model:** `model-name`")


def run_edit(outline_path, slide_num, edit_prompt):
    """Edit an existing slide illustration via the model's edit endpoint."""
    keys, outline, output_dir = _load_context(outline_path)
    model = outline["model"]

    input_path = find_base_image(output_dir, slide_num)
    if not input_path:
        print(f"ERROR: No existing image found for slide {slide_num} in {output_dir}/")
        print("Generate the base image first, then edit it.")
        sys.exit(1)

    slide = next((s for s in outline["slides"] if s["slide_num"] == slide_num), None)
    slide_format = slide["format"] if slide else None

    print(f"Model: {model}")
    print(f"Input: {input_path}")
    print(f"Edit prompt: {edit_prompt}")

    # Save as versioned output (never overwrite)
    ver = next_version(output_dir, slide_num)

    image_bytes, result = edit_image(input_path, edit_prompt, model, keys, slide_format)

    if image_bytes is None:
        print(f"FAILED: {result}")
        sys.exit(1)

    ext = mime_to_ext(result)
    filename = f"slide-{slide_num:02d}-v{ver}{ext}"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    size_kb = len(image_bytes) / 1024
    print(f"OK: {filename} ({size_kb:.0f} KB)")
    print(f"Review and compare with the original. If good, replace slide-{slide_num:02d}.")


def run_build(outline_path, slide_arg):
    """Generate progressive-reveal build images using backwards-chaining."""
    keys, outline, output_dir = _load_context(outline_path)
    model = outline["model"]
    builds_dir = os.path.join(output_dir, "builds")
    os.makedirs(builds_dir, exist_ok=True)

    slides_by_num = {s["slide_num"]: s for s in outline["slides"]}

    # Determine which slides to build
    if slide_arg == "all":
        to_build = [s for s in outline["slides"] if "builds" in s]
    else:
        num = int(slide_arg)
        if num not in slides_by_num:
            print(f"ERROR: Slide {num} not found in outline.")
            sys.exit(1)
        slide = slides_by_num[num]
        if "builds" not in slide:
            print(f"ERROR: Slide {num} has no build specification in the outline.")
            print("Add a '- Builds: N steps' section with build-00 through build-NN entries.")
            sys.exit(1)
        to_build = [slide]

    if not to_build:
        print("No slides with build specifications found in the outline.")
        sys.exit(0)

    total_steps = sum(s["builds"]["count"] for s in to_build)
    print(f"Model: {model}")
    print(f"Building {len(to_build)} slide(s), {total_steps} total build steps")
    print(f"Output: {builds_dir}/")
    print()

    for slide in to_build:
        num = slide["slide_num"]
        builds = slide["builds"]
        steps = builds["steps"]

        # The full slide image is the starting point
        full_image = find_base_image(output_dir, num)
        if not full_image:
            print(f"Slide {num}: SKIP — no base image found (generate it first)")
            continue

        print(f"Slide {num}: {slide['title']} — {len(steps)} build steps")

        # An outline can declare `- Builds: N steps` without any parsable
        # `build-XX:` entries beneath it — skip cleanly rather than crashing
        # on max() of an empty sequence.
        if not steps:
            print(f"  SKIP — Builds declared but no build-NN entries parsed")
            continue

        # Copy full image as the final build step. The dest path preserves
        # the source extension — base images may be .jpg / .png / .webp
        # depending on the generating vendor.
        final_step = max(s["step"] for s in steps)
        final_build = steps[-1]
        if final_build["is_full"]:
            dest = final_build_dest(builds_dir, num, final_step, full_image)
            shutil.copy2(full_image, dest)
            print(f"  build-{final_step:02d}: copied from slide-{num:02d} (full)")

        # Chain backwards: start from full, remove elements one at a time
        # Process steps in reverse order (excluding the final full step)
        edit_steps = [s for s in reversed(steps) if not s["is_full"]]
        prev_image = full_image

        for step in edit_steps:
            step_num = step["step"]
            desc = step["description"]

            print(f"  build-{step_num:02d}: {desc[:60]}...", end=" ", flush=True)

            image_bytes, result = edit_image(
                prev_image, desc, model, keys, slide["format"]
            )

            if image_bytes is None:
                print(f"FAILED: {result[:100]}")
                print(f"  Aborting remaining build steps for slide {num} (chain broken)")
                break

            ext = mime_to_ext(result)
            filename = f"slide-{num:02d}-build-{step_num:02d}{ext}"
            filepath = os.path.join(builds_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            size_kb = len(image_bytes) / 1024
            print(f"OK ({size_kb:.0f} KB)")

            # Use this step's output as input for the next (earlier) step
            prev_image = filepath

            time.sleep(RATE_LIMIT_DELAY)

        print()

    print("Done. Review build images in:", builds_dir)


def run_fix(outline_path, slide_num, fix_prompt):
    """Apply a targeted fix to an existing slide image, saving as a new version."""
    keys, outline, output_dir = _load_context(outline_path)
    model = outline["model"]

    input_path = find_latest_image(output_dir, slide_num)
    if not input_path:
        print(f"ERROR: No existing image found for slide {slide_num}")
        sys.exit(1)

    slide = next((s for s in outline["slides"] if s["slide_num"] == slide_num), None)
    slide_format = slide["format"] if slide else None

    ver = next_version(output_dir, slide_num)
    print(f"Model: {model}")
    print(f"Input: {os.path.basename(input_path)}")
    print(f"Fix: {fix_prompt}")
    print(f"Output: slide-{slide_num:02d}-v{ver}")

    image_bytes, result = edit_image(input_path, fix_prompt, model, keys, slide_format)

    if image_bytes is None:
        print(f"FAILED: {result}")
        sys.exit(1)

    ext = mime_to_ext(result)
    filename = f"slide-{slide_num:02d}-v{ver}{ext}"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    size_kb = len(image_bytes) / 1024
    print(f"OK: {filename} ({size_kb:.0f} KB)")


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="Generate illustrations for a presentation outline.",
        epilog="Examples:\n"
               "  %(prog)s outline.md all\n"
               "  %(prog)s outline.md remaining\n"
               "  %(prog)s outline.md 2 5 9\n"
               "  %(prog)s outline.md 2-10\n"
               "  %(prog)s outline.md --compare 2\n"
               "  %(prog)s outline.md --edit 5 \"Erase the label\"\n"
               "  %(prog)s outline.md --build 5\n"
               "  %(prog)s outline.md --build all\n"
               "  %(prog)s outline.md --fix 5 \"Make the road wider\"\n"
               "  %(prog)s outline.md -v 2 5 9\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("outline", help="Path to the presentation outline markdown file")
    parser.add_argument(
        "--vault",
        default=None,
        help="Path to the rhetoric knowledge vault (default: ~/.claude/rhetoric-knowledge-vault)",
    )
    parser.add_argument(
        "--compare",
        type=int,
        metavar="SLIDE",
        help="Compare models using the given slide number as test prompt",
    )
    parser.add_argument(
        "--edit",
        nargs=2,
        metavar=("SLIDE", "PROMPT"),
        help="Edit an existing slide image (e.g., --edit 5 \"Erase the label\")",
    )
    parser.add_argument(
        "--build",
        metavar="SLIDE_OR_ALL",
        help="Generate progressive-reveal builds (e.g., --build 5 or --build all)",
    )
    parser.add_argument(
        "--fix",
        nargs=2,
        metavar=("SLIDE", "PROMPT"),
        help="Targeted fix pass on a slide (e.g., --fix 5 \"Make the road wider\")",
    )
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="Save as slide-NN-vM.ext instead of overwriting (for generate mode)",
    )
    parser.add_argument(
        "slides",
        nargs="*",
        help="Slide selection: 'all', 'remaining', or slide numbers (e.g., 2 5 9, 2-10)",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.outline):
        print(f"ERROR: Outline file not found: {args.outline}")
        sys.exit(1)

    # Store vault path for _load_context
    global _cli_vault_path
    _cli_vault_path = args.vault

    if args.edit:
        run_edit(args.outline, int(args.edit[0]), args.edit[1])
    elif args.build:
        run_build(args.outline, args.build)
    elif args.fix:
        run_fix(args.outline, int(args.fix[0]), args.fix[1])
    elif args.compare:
        run_compare(args.outline, args.compare)
    else:
        run_generate(args.outline, args.slides, versioned=args.version)


if __name__ == "__main__":
    main()
