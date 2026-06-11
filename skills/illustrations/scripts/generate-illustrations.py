#!/usr/bin/env python3
"""
Generate illustrations for a presentation outline.

Reads outline.yaml (the single source of truth) for the baked model, per-format
style anchors, and per-slide image prompts, generates images via the
appropriate vendor API (Google Gemini, Google Imagen, or OpenAI — dispatched by
model-name prefix), and saves them to an illustrations/ directory.

Usage:
    python3 generate-illustrations.py <outline.yaml> all
    python3 generate-illustrations.py <outline.yaml> remaining
    python3 generate-illustrations.py <outline.yaml> 2 5 9
    python3 generate-illustrations.py <outline.yaml> 2-10
    python3 generate-illustrations.py <outline.yaml> --compare 2
    python3 generate-illustrations.py <outline.yaml> --style-explore candidates.json
    python3 generate-illustrations.py <outline.yaml> --edit 5 "Erase the label"
    python3 generate-illustrations.py <outline.yaml> --build 5
    python3 generate-illustrations.py <outline.yaml> --build all
    python3 generate-illustrations.py <outline.yaml> --fix 5 "Make the road wider"
    python3 generate-illustrations.py <outline.yaml> -v 2 5 9

Requires:
    - For Google models (gemini-*, nano-banana-*, imagen-*):
        Gemini API key in {vault}/secrets.json (preferred) or
        GEMINI_API_KEY env var (fallback).
    - For OpenAI models (gpt-image-*):
        OpenAI API key in {vault}/secrets.json under "openai".api_key
        or OPENAI_API_KEY env var (fallback).
    - Python 3.8+ (stdlib only — no pip install needed; uses the walrus
      operator and other 3.8+ syntax)
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
from datetime import datetime, timezone

from model_registry import COMPARE_MODELS, is_supported_model, resolve_model_id

# outline.yaml is the single source of truth; its pydantic schema + loader live
# with the presentation-creator scripts. Add that dir to the path so this skill
# parses the one schema rather than re-deriving an outline format.
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), os.pardir, os.pardir,
            "presentation-creator", "scripts",
        )
    ),
)
import outline_schema  # noqa: E402  (path appended above)

# --- Constants ---

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
OPENAI_API_BASE = "https://api.openai.com/v1"

# The model roster, vendor aliases, and per-model attributes live in
# model_registry.py (the single source of truth). --compare uses COMPARE_MODELS
# from there; resolve_model_id() maps baked codenames (e.g. nano-banana-pro) to
# the canonical API id before dispatch.

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

# Poster-theatrical composition (see rules/title-overlay-rules.md): the title
# and footer are rendered INTO the image as part of the scene, stylized in the
# deck's own visual vocabulary — not overlaid afterward. The opposite of a safe
# zone: text is integrated, no negative space is reserved.
POSTER_COMPOSITION = "poster-theatrical"

POSTER_EMBED_DIRECTIVE_TEMPLATE = (
    " EMBEDDED TEXT -- CRITICAL COMPOSITION RULE: Render the title \"{title}\" "
    "as an integral, stylized part of the scene itself — painted, carved, "
    "printed, lit, woven, or sculpted into the composition in the artwork's "
    "own lettering and materials, not pasted on as a flat overlay or caption. "
    "{footer_clause}All text must be fully blended and integrated into the "
    "illustration as if it belongs there. Do NOT reserve blank negative space "
    "for a title; the text is part of the artwork."
)

POSTER_FOOTER_CLAUSE_TEMPLATE = (
    "Also integrate the footer \"{footer}\" small along the lower edge of the "
    "frame, in the same stylized treatment. "
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

def _collapse_anchor(text):
    """Collapse a (possibly multi-line) anchor block into one prompt-ready line."""
    return " ".join(text.split())


def parse_outline(path):
    """Project outline.yaml onto the view the generator needs.

    outline.yaml is the single source of truth (schema + loader in
    skills/presentation-creator/scripts/outline_schema.py). The generated
    `.md` artifacts are never read here. Returns:

        dict with keys:
            model: str | None — baked illustration model (style_anchor.model)
            anchors: dict[str, str] — format token ("FULL"/"IMG+TXT") → anchor
            slides: list[dict] — prompt-bearing slides only, each with
                slide_num, title, format, prompt, and optional safe_zone /
                text / builds
            composition: str | None — "poster-theatrical" or None (standard)
            embedded_footer: str | None — poster-theatrical baked footer

    Build steps map to the generator's backwards-chaining view: each step's
    `description` is the `erase` prompt (additive `desc` stays human-facing in
    slides.md), and `is_full` marks the final step (a copy of the base image).
    A non-final step with no `erase` prompt becomes an empty description, which
    --build flags as missing its mandatory "Keep ..." clause.

    Uses the partial loader: the illustrations skill reads the outline in Phase 2
    (style strategy, before the deck is complete) as well as Phase 5, so it must
    not require the full-deck invariants (big-idea singleton, slide budget,
    callback pairing) that only hold once authoring finishes.
    """
    outline = outline_schema.load_outline_partial(path)
    anchor = outline.style_anchor

    result = {
        "model": anchor.model if anchor else None,
        "anchors": {
            "FULL": _collapse_anchor(anchor.full),
            "IMG+TXT": _collapse_anchor(anchor.imgtxt),
        } if anchor else {},
        "slides": [],
        "composition": (
            anchor.composition.value if anchor and anchor.composition else None
        ),
        "embedded_footer": anchor.embedded_footer if anchor else None,
    }

    for slide in outline.slides:
        if not slide.image_prompt:
            continue
        slide_data = {
            "slide_num": slide.n,
            "title": slide.title,
            "format": slide.format.value,
            "prompt": slide.image_prompt.strip(),
        }
        if slide.safe_zone:
            slide_data["safe_zone"] = {
                "zone": slide.safe_zone.zone.value,
                "surface": slide.safe_zone.surface,
            }
        text = (slide.text_overlay or "").strip()
        if text and text.lower() != "none":
            slide_data["text"] = text
        if slide.builds:
            max_step = max(b.step for b in slide.builds)
            steps = [
                {
                    "step": b.step,
                    "description": b.erase or "",
                    "is_full": b.step == max_step,
                }
                for b in sorted(slide.builds, key=lambda b: b.step)
            ]
            slide_data["builds"] = {"count": len(steps), "steps": steps}
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


def apply_safe_zone_directive(prompt, safe_zone):
    """Append the SAFE ZONE directive to a prompt when safe_zone is set.

    See rules/title-overlay-rules.md for the policy. Idempotent: if the
    prompt already contains a TITLE SAFE ZONE block, it is replaced.

    Safe zone presence is the signal — apply-illustrations-to-deck.py
    treats any slide with a `Safe zone:` line as FULL/title-overlay
    regardless of the `Format:` token (Safe zone takes precedence, see
    apply-illustrations-to-deck.py's `parse_img_txt_slides()` which
    excludes slides whose block also contains a Safe zone line). The
    generator mirrors that: when Safe zone is present, the slide is
    rendered as FULL and the directive is unconditionally applied.
    Callers also override per-format sizing to FULL whenever Safe zone
    is set — see `effective_slide_format()` and the `eff_format` use
    in each run_* call.
    """
    if not safe_zone:
        return prompt
    zone = safe_zone["zone"]
    if zone not in VALID_SAFE_ZONES:
        return prompt
    surface = safe_zone.get("surface") or DEFAULT_SAFE_ZONE_SURFACE[zone]
    if "TITLE SAFE ZONE" in prompt:
        prompt = prompt.split("TITLE SAFE ZONE", 1)[0].rstrip()
    directive = SAFE_ZONE_DIRECTIVE_TEMPLATE.format(
        zone_words=zone.replace("_", " "),
        surface=surface,
    )
    return prompt + directive


def apply_poster_embed_directive(prompt, title_text, footer_text):
    """Append the poster-theatrical EMBEDDED TEXT directive to a prompt.

    Used when the deck's composition is poster-theatrical: the title (and, when
    present, the footer) are rendered into the image as a stylized part of the
    scene rather than overlaid afterward. The inverse of a safe zone — no
    negative space is reserved. See rules/title-overlay-rules.md.
    Idempotent: an existing EMBEDDED TEXT block is replaced.
    """
    if not title_text:
        return prompt
    if "EMBEDDED TEXT" in prompt:
        prompt = prompt.split("EMBEDDED TEXT", 1)[0].rstrip()
    # The directive wraps the title/footer in double quotes; normalize any
    # embedded double quotes to single so a title like He said "Hi" doesn't
    # produce ambiguous nested quotes that degrade model compliance.
    title = title_text.replace('"', "'")
    footer_clause = ""
    if footer_text:
        footer_clause = POSTER_FOOTER_CLAUSE_TEMPLATE.format(
            footer=footer_text.replace('"', "'")
        )
    directive = POSTER_EMBED_DIRECTIVE_TEMPLATE.format(
        title=title,
        footer_clause=footer_clause,
    )
    return prompt + directive


def effective_slide_format(slide_format, safe_zone):
    """Resolve the format that should drive vendor sizing.

    apply-illustrations-to-deck.py treats `Safe zone:` presence as the
    FULL/title-overlay signal regardless of the Format token, so the
    generator must size accordingly — a 2:3 portrait can't host a 16:9
    safe zone meaningfully. Returns "FULL" whenever safe_zone is set;
    otherwise returns the declared slide_format unchanged.
    """
    if safe_zone:
        return "FULL"
    return slide_format


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


def _has_keep_clause(description):
    """True if the description has a positive "Keep <target>" sentence.

    The bare token `keep` is not enough — "Do not keep Panel 3" is a removal,
    not a preservation. Split on sentence boundaries and require a sentence that
    *begins* with "Keep" followed by a target, matching the documented
    "Keep the [X]." format and rejecting negated/non-clause wording.
    """
    return any(
        re.match(r"\s*keep\s+\S", sentence, re.IGNORECASE)
        for sentence in re.split(r"[.!?]+", description)
    )


def steps_missing_keep_clause(edit_steps):
    """Build erase steps lacking a positive "Keep <target>" preservation clause.

    Component #3 of the Edit Prompt Safety rule. An erase step with no Keep
    clause lets the model silently retain the element meant to be erased, so
    the build chain emits visually identical stages. Returns the offending
    steps (empty list means every step is compliant).
    """
    return [s for s in edit_steps if not _has_keep_clause(s["description"])]


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
        # gpt-image-* models return base64 by default and reject the
        # legacy `response_format` parameter (that's a DALL-E knob).
        # The url-branch in _extract_openai_image stays as a defensive
        # fallback in case future model versions change the default.
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
        # gpt-image-* returns base64 by default; do not send
        # `response_format` (legacy DALL-E knob; gpt-image-* 400s on it).
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
    model = resolve_model_id(model)
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

    model = resolve_model_id(model)
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


# --- Style-explore manifest + render-before-bake gate ---

RENDERED_MANIFEST = "rendered.json"


def style_explore_dir(outline_path):
    """The style-explore/ directory alongside the outline."""
    return os.path.join(
        os.path.dirname(os.path.abspath(outline_path)), "style-explore"
    )


def write_rendered_manifest(base_dir, outline_path, results):
    """Persist a machine-readable record of what the grid actually rendered.

    index.md is for humans; this manifest is the source of truth the
    render-before-bake gate reads. Only OK cells make a model gate-eligible —
    a model that failed every cell produced no image the speaker could pick.
    Idempotent: a re-run overwrites it with the latest grid.
    """
    cells = []
    ok_models = []
    for r in results:
        resolved = resolve_model_id(r["model"])
        cell = {
            "style": r["style"],
            "format": r["format"],
            "model": r["model"],
            "model_resolved": resolved,
            "status": r["status"],
        }
        if r["status"] == "OK":
            cell["rel_path"] = r.get("rel_path")
            ok_models.append(resolved)
        else:
            cell["error"] = r.get("error")
        cells.append(cell)

    manifest = {
        "schema_version": 1,
        "outline": os.path.basename(outline_path),
        # Talk-directory name — a per-talk discriminator. Outline filenames are
        # identical across talks (outline.yaml), so the basename alone can't
        # tell a copied grid from this talk's; the dir name (typically the talk
        # slug) can.
        "outline_dir": os.path.basename(os.path.dirname(os.path.abspath(outline_path))),
        "rendered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "models_rendered_ok": sorted(set(ok_models)),
        "cells": cells,
    }
    manifest_path = os.path.join(base_dir, RENDERED_MANIFEST)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest_path


def check_style_explore(outline_path):
    """Render-before-bake gate: was the outline's baked model actually rendered?

    Reads the baked **Model:** from the outline header and style-explore/
    rendered.json. gate_passed is True iff the manifest exists and the baked
    model (resolved to its canonical id) is among the OK-rendered models.
    Returns a verdict dict; never raises on a missing/unbaked model.
    """
    baked = parse_outline(outline_path).get("model")
    resolved = resolve_model_id(baked) if baked else None
    se_dir = style_explore_dir(outline_path)
    manifest_path = os.path.join(se_dir, RENDERED_MANIFEST)
    outline_name = os.path.basename(outline_path)
    outline_dir = os.path.basename(os.path.dirname(os.path.abspath(outline_path)))

    verdict = {
        "gate_passed": False,
        "model_baked": baked,
        "model_resolved": resolved,
        "rendered_models": [],
        "manifest_present": False,
        "error": None,
    }

    if not baked:
        verdict["error"] = (
            "No **Model:** is baked into the outline header. Run the style "
            "exploration first and pick a model from the rendered grid: "
            f"generate-illustrations.py {outline_name} "
            "--style-explore style-explore/candidates.json"
        )
        return verdict

    if not os.path.isfile(manifest_path):
        verdict["error"] = (
            f"No style-explore/{RENDERED_MANIFEST} next to {outline_name} — the "
            "exploration grid was never rendered, so the baked model "
            f"'{baked}' was never seen. Render it first: "
            f"generate-illustrations.py {outline_name} "
            "--style-explore style-explore/candidates.json"
        )
        return verdict

    # The file exists — "present" means present, even if unreadable below, so
    # callers can tell "missing" from "present but invalid" via `error`.
    verdict["manifest_present"] = True

    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as e:
        verdict["error"] = f"Could not read {manifest_path}: {e}"
        return verdict

    if not isinstance(manifest, dict):
        verdict["error"] = (
            f"{manifest_path} is not a JSON object — re-run --style-explore to "
            "regenerate it."
        )
        return verdict

    # Fail closed on a manifest we can't trust: an unsupported schema, or one
    # copied in from a different talk (basename AND talk-dir must match — see
    # rules/stateful-artifacts.md, "stale state is the default").
    if manifest.get("schema_version") != 1:
        verdict["error"] = (
            f"{manifest_path} has unsupported schema_version "
            f"{manifest.get('schema_version')!r} (expected 1) — re-run "
            "--style-explore to regenerate it."
        )
        return verdict
    if manifest.get("outline") != outline_name:
        verdict["error"] = (
            f"{manifest_path} was rendered for outline "
            f"{manifest.get('outline')!r}, not {outline_name!r} — it looks "
            "copied or stale. Re-run --style-explore for this outline."
        )
        return verdict
    manifest_dir = manifest.get("outline_dir")
    if not isinstance(manifest_dir, str) or manifest_dir != outline_dir:
        verdict["error"] = (
            f"{manifest_path} has outline_dir {manifest_dir!r}, expected "
            f"{outline_dir!r} — missing or mismatched talk discriminator (the "
            "grid looks copied from another talk or stale). Re-run "
            "--style-explore for this talk."
        )
        return verdict
    cells = manifest.get("cells")
    if not isinstance(cells, list):
        verdict["error"] = (
            f"{manifest_path} has a malformed 'cells' (expected a list) — "
            "re-run --style-explore to regenerate it."
        )
        return verdict

    # Don't trust models_rendered_ok: a model is eligible only when a cell that
    # rendered OK still has its image file on disk. A stale or hand-edited
    # manifest that lists a model with no backing file does not pass the gate
    # (rules/stateful-artifacts.md — verify against the live source).
    abs_se = os.path.realpath(se_dir)
    verified = set()
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("status") != "OK":
            continue
        rel = cell.get("rel_path")
        if not isinstance(rel, str) or not rel:
            continue
        # rel_path must resolve to a file INSIDE this talk's style-explore/.
        # Reject absolute paths and ../ traversal so a hand-edited manifest
        # can't point at an arbitrary existing image to fake render evidence.
        if os.path.isabs(rel):
            continue
        target = os.path.realpath(os.path.join(abs_se, rel))
        if os.path.commonpath([abs_se, target]) != abs_se:
            continue
        if not os.path.isfile(target):
            continue
        cell_model_raw = cell.get("model_resolved") or cell.get("model")
        if not isinstance(cell_model_raw, str):
            continue
        cell_model = resolve_model_id(cell_model_raw)
        if cell_model:
            verified.add(cell_model)
    rendered = sorted(verified)
    verdict["rendered_models"] = rendered

    if resolved in rendered:
        verdict["gate_passed"] = True
    else:
        verdict["error"] = (
            f"Baked model '{baked}' (resolved: {resolved}) was not rendered in "
            "the exploration grid. Models that rendered OK: "
            f"{', '.join(rendered) or 'none'}. Pick one of those, or re-run "
            f"--style-explore with '{baked}' in candidates.json so the speaker "
            "can see it before it's baked."
        )
    return verdict


def run_check_style_explore(outline_path):
    """CLI wrapper for the render-before-bake gate; emits verdict JSON."""
    verdict = check_style_explore(outline_path)
    print(json.dumps(verdict, indent=2))
    if not verdict["gate_passed"]:
        print(verdict["error"], file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def enforce_render_gate(outline_path):
    """Render-before-bake gate, shared by every model-producing deck path.

    Refuse to produce images from a model that was never rendered in an
    exploration grid the speaker could see. Both run_generate and run_build call
    this so no path can bake an unrendered model — closing the hole where an agent
    reasons a model into the anchor and skips the Step 8 grid. Exits non-zero with
    the verdict's actionable message on failure.
    """
    verdict = check_style_explore(outline_path)
    if not verdict["gate_passed"]:
        print(f"ERROR: {verdict['error']}", file=sys.stderr)
        sys.exit(1)


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

    enforce_render_gate(outline_path)

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
    poster = outline.get("composition") == POSTER_COMPOSITION

    if poster:
        # Poster-theatrical invariants: every illustrated slide must be FULL
        # with no Safe zone (text is baked in, nothing overlaid). Validate the
        # whole outline, not just this run's subset — a partial run must not be
        # able to bypass the deck-level invariant. (outline["slides"] holds only
        # prompt-bearing slides; EXCEPTION slides carry no prompt and render as
        # real assets, so they are correctly out of scope here.)
        bad = [
            s["slide_num"] for s in outline["slides"]
            if s["format"] != "FULL" or s.get("safe_zone")
        ]
        if bad:
            print(
                "ERROR: poster-theatrical composition requires every illustrated "
                f"slide to be Format: FULL with no Safe zone. Offending slide(s): "
                f"{', '.join(map(str, bad))}. Fix the outline or drop the "
                "**Composition:** poster-theatrical header.",
                file=sys.stderr,
            )
            sys.exit(1)

    for i, num in enumerate(to_generate):
        slide = slides_by_num[num]
        if poster:
            # Poster-theatrical: every slide is full-bleed and the title +
            # footer are rendered INTO the image (stylized, blended); no safe
            # zone is reserved. See rules/title-overlay-rules.md.
            eff_format = "FULL"
            prompt = resolve_prompt(slide["prompt"], eff_format, outline["anchors"])
            prompt = apply_poster_embed_directive(
                prompt,
                slide.get("text") or slide["title"],
                outline.get("embedded_footer"),
            )
        else:
            # Safe zone presence forces FULL throughout — anchor selection,
            # sizing, and the directive itself all use the effective format
            # so the prompt, the image geometry, and the apply-step layout
            # stay internally consistent.
            eff_format = effective_slide_format(slide["format"], slide.get("safe_zone"))
            prompt = resolve_prompt(slide["prompt"], eff_format, outline["anchors"])
            prompt = apply_safe_zone_directive(prompt, slide.get("safe_zone"))

        print(f"[{i+1}/{len(to_generate)}] Slide {num}: {slide['title']}")

        image_bytes, result = generate_image(prompt, model, keys, eff_format)

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
    # Safe zone presence forces FULL throughout (see effective_slide_format).
    eff_format = effective_slide_format(slide["format"], slide.get("safe_zone"))
    prompt = resolve_prompt(slide["prompt"], eff_format, outline["anchors"])
    prompt = apply_safe_zone_directive(prompt, slide.get("safe_zone"))

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

        image_bytes, result = generate_image(prompt, model, keys, eff_format)

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


# --- Style Exploration (Phase 2 strategy: style x model x format grid) ---

def style_slug(name):
    """Filesystem-safe kebab-case slug for a style name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "style"


def _format_slug(fmt):
    """Filesystem-safe token for a slide format (e.g. IMG+TXT -> img-txt)."""
    return re.sub(r"[^a-z0-9]+", "-", fmt.strip().lower()).strip("-") or "format"


def parse_candidates(path):
    """Parse + validate a style-explore candidates.json file.

    Schema (schema_version 1) is documented in
    skills/illustrations/references/style-explore-candidates-schema.md.

    Returns the parsed dict. Raises ValueError with an actionable message on a
    malformed file.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON ({e}).")

    if data.get("schema_version") != 1:
        raise ValueError(
            f"{path}: unsupported schema_version {data.get('schema_version')!r}; "
            "expected 1."
        )
    slides = data.get("slides")
    if not isinstance(slides, dict) or not slides:
        raise ValueError(
            f"{path}: 'slides' must map at least one format to a slide number "
            '(e.g. {"FULL": 7, "IMG+TXT": 12}).'
        )
    for fmt, n in slides.items():
        # bool is an int subclass — reject it too. A string ("7") would key
        # slides_by_num by the wrong type and silently skip the format.
        if not isinstance(n, int) or isinstance(n, bool):
            raise ValueError(
                f"{path}: slides['{fmt}'] must be an integer slide number, got {n!r}."
            )
    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError(f"{path}: 'models' must be a non-empty list of model ids.")
    for i, m in enumerate(models):
        if not isinstance(m, str) or not m.strip():
            raise ValueError(f"{path}: models[{i}] must be a non-empty string model id.")
    data["models"] = [m.strip() for m in models]
    styles = data.get("styles")
    if not isinstance(styles, list) or not styles:
        raise ValueError(f"{path}: 'styles' must be a non-empty list of style entries.")
    for i, style in enumerate(styles):
        if not isinstance(style, dict) or not isinstance(style.get("name"), str) \
                or not style["name"].strip():
            raise ValueError(f"{path}: styles[{i}] needs a non-empty string 'name'.")
        anchors = style.get("anchors")
        if not isinstance(anchors, dict) or not anchors:
            raise ValueError(
                f"{path}: styles[{i}] ('{style.get('name', '?')}') needs an "
                "'anchors' map of format -> anchor text."
            )
        for fmt, text in anchors.items():
            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"{path}: styles[{i}] ('{style['name']}') anchor for '{fmt}' "
                    "must be a non-empty string."
                )
    return data


def explore_dest(base_dir, style_name, fmt, model, ext):
    """Destination path for one style-explore render."""
    safe_model = model.replace("/", "_")
    return os.path.join(
        base_dir, style_slug(style_name), _format_slug(fmt), f"{safe_model}{ext}"
    )


def render_explore_index(candidates, results):
    """Render the style-explore/index.md contact sheet.

    results: list of dicts with keys style, format, model, status ("OK"/"FAIL"),
    plus rel_path (OK) or error (FAIL). Paths are relative to the style-explore
    directory so the links resolve in place.
    """
    slides = candidates.get("slides", {})
    slide_desc = ", ".join(f"{fmt} = slide {n}" for fmt, n in slides.items())
    lines = [
        "# Style Exploration",
        "",
        f"Representative slides: {slide_desc}",
        f"Models: {', '.join(candidates.get('models', []))}",
        "",
    ]
    by_style = {}
    for r in results:
        by_style.setdefault(r["style"], []).append(r)
    for style in candidates.get("styles", []):
        name = style["name"]
        lines.append(f"## {name}")
        lines.append("")
        for r in by_style.get(name, []):
            label = f"**{r['format']}** · `{r['model']}`"
            if r["status"] == "OK":
                lines.append(f"- {label} — [{r['rel_path']}]({r['rel_path']})")
            else:
                lines.append(f"- {label} — FAILED: {r['error']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_style_explore(outline_path, candidates_path):
    """Render a style x model x format exploration grid for Phase 2 strategy.

    Reads candidate styles + a model shortlist from candidates.json, pulls each
    format's representative scene prompt from the outline, substitutes each
    candidate style's anchor, and renders across the shortlisted models into a
    structured style-explore/ directory with an index.md contact sheet.
    """
    try:
        candidates = parse_candidates(candidates_path)
    except FileNotFoundError:
        print(f"ERROR: candidates file not found: {candidates_path}", file=sys.stderr)
        print(
            "Write style-explore/candidates.json first — see "
            "skills/illustrations/references/style-explore-candidates-schema.md.",
            file=sys.stderr,
        )
        sys.exit(1)
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    keys, secrets_path = load_secrets()
    outline = parse_outline(outline_path)
    slides_by_num = {s["slide_num"]: s for s in outline["slides"]}

    # Fail fast on a candidate id we have no adapter for — model_family() would
    # otherwise misroute it to the Gemini endpoint and fail mid-network.
    unsupported = [m for m in candidates["models"] if not is_supported_model(m)]
    if unsupported:
        print(
            f"ERROR: unsupported model id(s): {', '.join(unsupported)}.",
            file=sys.stderr,
        )
        print(
            "Supported families: gemini-* / nano-banana-*, imagen-*, gpt-image-*. "
            "A new vendor needs a _call_<vendor> adapter in this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    families = {model_family(resolve_model_id(m)) for m in candidates["models"]}
    _require_keys_for_families(keys, families, secrets_path)

    base_dir = os.path.join(
        os.path.dirname(os.path.abspath(outline_path)), "style-explore"
    )
    os.makedirs(base_dir, exist_ok=True)

    # Resolve each format's representative scene prompt from the outline.
    targets = []
    for fmt, slide_num in candidates["slides"].items():
        slide = slides_by_num.get(slide_num)
        if not slide:
            print(
                f"WARNING: slide {slide_num} (for {fmt}) has no image prompt in "
                "the outline; skipping that format.",
                file=sys.stderr,
            )
            continue
        safe_zone = slide.get("safe_zone")
        # A safe zone forces FULL sizing/anchor downstream; if that disagrees
        # with the format being explored, the cell would render at the wrong
        # geometry. Skip it so every rendered cell keys consistently on `fmt`.
        if effective_slide_format(fmt, safe_zone) != fmt:
            print(
                f"WARNING: slide {slide_num} for format {fmt} carries a Safe zone "
                f"that forces FULL; choose a representative {fmt} slide without a "
                "safe zone. Skipping that format.",
                file=sys.stderr,
            )
            continue
        targets.append((fmt, slide["prompt"], safe_zone))

    if not targets:
        print(
            "ERROR: none of the candidate slides have a usable image prompt for "
            "their format in the outline.",
            file=sys.stderr,
        )
        print(f"Slides referenced: {candidates['slides']}", file=sys.stderr)
        sys.exit(1)

    # Build the full render plan up front so the progress count is exact.
    plan = []
    for style in candidates["styles"]:
        for fmt, scene_prompt, safe_zone in targets:
            eff_format = effective_slide_format(fmt, safe_zone)
            # When a safe zone forces FULL, prefer the style's eff_format anchor
            # so anchor text, substitution, and sizing all agree; fall back to
            # the declared format's anchor.
            anchor = style["anchors"].get(eff_format) or style["anchors"].get(fmt)
            if not anchor:
                continue
            prompt = apply_safe_zone_directive(
                resolve_prompt(scene_prompt, eff_format, {eff_format: anchor}), safe_zone
            )
            for model in candidates["models"]:
                plan.append((style["name"], fmt, model, prompt, eff_format))

    total = len(plan)
    if total == 0:
        print(
            "ERROR: nothing to render — no candidate style defines an anchor for "
            "any of the selected formats.",
            file=sys.stderr,
        )
        print(
            "Add per-format anchors to the styles in the candidates file (see "
            "skills/illustrations/references/style-explore-candidates-schema.md), "
            "or point 'slides' at formats your styles cover.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        f"Style exploration -> {total} renders "
        f"({len(candidates['styles'])} styles x {len(targets)} formats x "
        f"{len(candidates['models'])} models)"
    )
    print(f"Output: {base_dir}/")
    print()

    results = []
    for i, (style_name, fmt, model, prompt, eff_format) in enumerate(plan, 1):
        print(f"[{i}/{total}] {style_name} · {fmt} · {model}...", end=" ", flush=True)
        image_bytes, result = generate_image(prompt, model, keys, eff_format)
        if image_bytes is None:
            print(f"FAILED: {result[:80]}")
            results.append({
                "style": style_name, "format": fmt, "model": model,
                "status": "FAIL", "error": result[:200],
            })
        else:
            ext = mime_to_ext(result)
            dest = explore_dest(base_dir, style_name, fmt, model, ext)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(image_bytes)
            print(f"OK ({len(image_bytes) / 1024:.0f} KB)")
            results.append({
                "style": style_name, "format": fmt, "model": model,
                "status": "OK", "rel_path": os.path.relpath(dest, base_dir),
            })
        if i < total:
            time.sleep(RATE_LIMIT_DELAY)

    index_path = os.path.join(base_dir, "index.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(render_explore_index(candidates, results))

    manifest_path = write_rendered_manifest(base_dir, outline_path, results)

    print()
    print(f"Wrote {index_path}")
    print(f"Wrote {manifest_path}")
    print("Review the grid, pick a style + model, then bake them into the outline header.")


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
    eff_format = (
        effective_slide_format(slide["format"], slide.get("safe_zone"))
        if slide else None
    )

    print(f"Model: {model}")
    print(f"Input: {input_path}")
    print(f"Edit prompt: {edit_prompt}")

    # Save as versioned output (never overwrite)
    ver = next_version(output_dir, slide_num)

    image_bytes, result = edit_image(input_path, edit_prompt, model, keys, eff_format)

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

    # Same render-before-bake gate as run_generate — build frames are produced
    # from the baked model too, so this path must not bypass it.
    enforce_render_gate(outline_path)

    total_steps = sum(s["builds"]["count"] for s in to_build)
    build_failed = False
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

        # Chain backwards: start from full, remove elements one at a time
        # Process steps in reverse order (excluding the final full step)
        edit_steps = [s for s in reversed(steps) if not s["is_full"]]

        # Edit Prompt Safety component #3 (rules/illustration-rules.md): every
        # erase step must carry an explicit "Keep ..." preservation list. Without
        # it the model silently keeps the element that was meant to be erased, so
        # the chain emits visually identical intermediate stages. Validate before
        # writing any artifact — a skipped slide must not leave a stray final
        # build copy (or a "copied" log line) that misleads downstream checks.
        missing_keep = steps_missing_keep_clause(edit_steps)
        if missing_keep:
            build_failed = True
            print(f"  ERROR: {len(missing_keep)} build step(s) lack an explicit "
                  '"Keep ..." preservation list:', file=sys.stderr)
            for s in missing_keep:
                print(f"    build-{s['step']:02d}: {s['description'][:70]}",
                      file=sys.stderr)
            print("  Phrase each step as an erase instruction naming every element "
                  "that must persist", file=sys.stderr)
            print('  ("Erase X. Keep the Y. Keep the Z.") — see '
                  "rules/illustration-rules.md component #3. Skipping slide.",
                  file=sys.stderr)
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

        prev_image = full_image

        for step in edit_steps:
            step_num = step["step"]
            desc = step["description"]

            print(f"  build-{step_num:02d}: {desc[:60]}...", end=" ", flush=True)

            image_bytes, result = edit_image(
                prev_image, desc, model, keys,
                effective_slide_format(slide["format"], slide.get("safe_zone")),
            )

            if image_bytes is None:
                build_failed = True
                print("FAILED")  # complete the stdout progress line opened above
                print(f"  slide {num} build-{step_num:02d} edit failed: {result[:100]}",
                      file=sys.stderr)
                print(f"  Aborting remaining build steps for slide {num} (chain broken)",
                      file=sys.stderr)
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

    # Surface any incomplete chain in the exit code so `--build all` automation
    # can detect that some slides produced no build sequence — whether skipped
    # for a missing Keep clause or aborted on an edit failure (file-hygiene
    # policy: non-zero exit on failure). Exit before the success line so a failed
    # run never prints a success-sounding "Done".
    if build_failed:
        print("ERROR: one or more slides did not produce a complete build chain.",
              file=sys.stderr)
        sys.exit(1)

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
    eff_format = (
        effective_slide_format(slide["format"], slide.get("safe_zone"))
        if slide else None
    )

    ver = next_version(output_dir, slide_num)
    print(f"Model: {model}")
    print(f"Input: {os.path.basename(input_path)}")
    print(f"Fix: {fix_prompt}")
    print(f"Output: slide-{slide_num:02d}-v{ver}")

    image_bytes, result = edit_image(input_path, fix_prompt, model, keys, eff_format)

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
               "  %(prog)s outline.yaml all\n"
               "  %(prog)s outline.yaml remaining\n"
               "  %(prog)s outline.yaml 2 5 9\n"
               "  %(prog)s outline.yaml 2-10\n"
               "  %(prog)s outline.yaml --compare 2\n"
               "  %(prog)s outline.yaml --style-explore style-explore/candidates.json\n"
               "  %(prog)s outline.yaml --edit 5 \"Erase the label\"\n"
               "  %(prog)s outline.yaml --build 5\n"
               "  %(prog)s outline.yaml --build all\n"
               "  %(prog)s outline.yaml --fix 5 \"Make the road wider\"\n"
               "  %(prog)s outline.yaml -v 2 5 9\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("outline", help="Path to outline.yaml (the single source of truth)")
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
        "--style-explore",
        metavar="CANDIDATES_JSON",
        help="Render a style x model x format grid from a candidates.json "
             "(Phase 2 strategy); writes style-explore/ + index.md + rendered.json",
    )
    parser.add_argument(
        "--check-style-explore",
        action="store_true",
        help="Render-before-bake gate: verify the outline's baked model was "
             "rendered in style-explore/; emits verdict JSON, exits non-zero on fail",
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
    elif args.style_explore:
        run_style_explore(args.outline, args.style_explore)
    elif args.check_style_explore:
        run_check_style_explore(args.outline)
    else:
        run_generate(args.outline, args.slides, versioned=args.version)


if __name__ == "__main__":
    main()
