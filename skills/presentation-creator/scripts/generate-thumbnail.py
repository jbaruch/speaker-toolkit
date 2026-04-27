#!/usr/bin/env python3
"""
Generate a YouTube thumbnail for a presentation.

Composes a thumbnail from a slide image and speaker photo using the Gemini
API, following YouTube thumbnail best practices (faces, bold text, high
contrast). Also supports extracting slide images from PPTX decks.

Usage:
    # Compose thumbnail via Gemini
    python3 generate-thumbnail.py \
      --slide-image illustrations/slide-15.png \
      --speaker-photo ~/photos/headshot.jpg \
      --title "JUDGMENT DAY" \
      [--subtitle "DevNexus 2026"] \
      [--output thumbnail.png] \
      [--vault ~/.claude/rhetoric-knowledge-vault] \
      [--style slide_dominant|split_panel|overlay] \
      [--aesthetic photo|comic_book] \
      [--portrait-style "<anchor>"] \
      [--title-position top|bottom|overlay] \
      [--brand-colors "#5B2C6F,#C0392B"] \
      [--model gemini-3-pro-image-preview]

    # Extract slide image from PPTX (helper mode, no Gemini)
    python3 generate-thumbnail.py --extract-slide deck.pptx 15 \
      [--output slide-15.png]

Requires:
    - Gemini API key in {vault}/secrets.json (preferred) or GEMINI_API_KEY env var
    - Pillow (pip install Pillow)
    - Python 3.7+
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

try:
    from PIL import Image
except ImportError:
    print("ERROR: 'Pillow' package not installed. Run: pip install Pillow")
    sys.exit(1)


# --- Constants ---

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3-pro-image-preview"

YOUTUBE_WIDTH = 1280
YOUTUBE_HEIGHT = 720
YOUTUBE_MAX_BYTES = 2 * 1024 * 1024  # 2 MB

# MIME <-> extension mapping
_MIME_EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_EXT_MIME_MAP = {v: k for k, v in _MIME_EXT_MAP.items()}
_EXT_MIME_MAP[".jpeg"] = "image/jpeg"


# --- Style Variants ---

STYLE_VARIANTS = {
    "slide_dominant": (
        "The slide visual fills most of the frame as the background. "
        "The speaker appears in the lower-right or lower-left quadrant "
        "at approximately 30-40% of frame height."
    ),
    "split_panel": (
        "Left half shows the speaker from shoulders up. Right half shows "
        "the slide visual. A subtle diagonal or gradient divides them. "
        "Both halves have equal visual weight."
    ),
    "overlay": (
        "The slide visual fills the entire background. The speaker is "
        "composited as a cutout overlay in the foreground, positioned to "
        "complement the slide's focal areas."
    ),
}

TITLE_POSITION_GUIDANCE = {
    "top": "Position the title text in the top third of the frame, centered horizontally.",
    "bottom": "Position the title text in the bottom third of the frame, centered horizontally.",
    "overlay": "Position the title text overlaid on the most visually quiet area of the image.",
}

EXPRESSION_DEFAULT = (
    "Show an engaging, confident expression — slight smile, direct eye "
    "contact with the camera, conveying authority and approachability."
)


# --- API Key Loading ---

def load_api_key(vault_path=None):
    """Load Gemini API key from secrets.json or environment.

    Resolution order:
        1. {vault}/secrets.json -> gemini.api_key
        2. GEMINI_API_KEY environment variable
    """
    if vault_path is None:
        vault_path = os.path.expanduser("~/.claude/rhetoric-knowledge-vault")

    secrets_path = os.path.join(vault_path, "secrets.json")
    if os.path.isfile(secrets_path):
        try:
            with open(secrets_path, "r", encoding="utf-8") as f:
                secrets = json.load(f)
            key = secrets.get("gemini", {}).get("api_key") or None
            if key:
                return key
        except (json.JSONDecodeError, OSError):
            pass

    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key

    print("ERROR: No Gemini API key found.")
    print(f"Add to {secrets_path}:")
    print('  "gemini": {"api_key": "YOUR_KEY"}')
    print("Or set the GEMINI_API_KEY environment variable.")
    sys.exit(1)


# --- Image Utilities ---

def load_image_as_base64(path):
    """Load an image file and return (base64_data, mime_type).

    Supports local files and HTTPS URLs.
    """
    if path.startswith("https://") or path.startswith("http://"):
        req = urllib.request.Request(path)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            mime = content_type.split(";")[0].strip()
            return base64.b64encode(data).decode("utf-8"), mime

    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        print(f"ERROR: Image not found: {path}")
        sys.exit(1)

    ext = os.path.splitext(path)[1].lower()
    mime = _EXT_MIME_MAP.get(ext, "image/png")

    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("utf-8"), mime


def validate_and_resize(image_bytes, mime_type):
    """Ensure the thumbnail meets YouTube specs: 1280x720, <2MB, PNG/JPG.

    Returns (final_bytes, final_mime).
    """
    from io import BytesIO

    img = Image.open(BytesIO(image_bytes))

    # Resize to exactly 1280x720
    if img.size != (YOUTUBE_WIDTH, YOUTUBE_HEIGHT):
        img = img.resize((YOUTUBE_WIDTH, YOUTUBE_HEIGHT), Image.LANCZOS)

    # Convert to RGB if necessary (e.g., RGBA)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Try PNG first
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    png_bytes = buf.getvalue()

    if len(png_bytes) <= YOUTUBE_MAX_BYTES:
        return png_bytes, "image/png"

    # Fall back to JPEG with decreasing quality
    for quality in (95, 90, 85, 80, 75):
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        jpg_bytes = buf.getvalue()
        if len(jpg_bytes) <= YOUTUBE_MAX_BYTES:
            return jpg_bytes, "image/jpeg"

    # Last resort: return JPEG at quality 75
    return jpg_bytes, "image/jpeg"


# --- Gemini API ---

# Sentinel prefixes for error messages returned by call_gemini.
# Callers use these to distinguish safety-filter rejections (where softening
# the prompt may help) from transport-level failures (where it can't).
_ERR_FILTER = "FILTER: "
_ERR_HTTP = "HTTP: "
_ERR_OTHER = "OTHER: "


def call_gemini(parts, model, api_key):
    """Send parts to Gemini generateContent API and extract the image.

    Returns (image_bytes, mime_type) on success.
    Returns (None, error_message) on failure, where error_message starts with
    one of the _ERR_* prefixes:
        _ERR_FILTER — request returned no image (safety filter / IMAGE_OTHER /
                      empty candidates). Softening the prompt may help.
        _ERR_HTTP   — HTTP-level failure (auth, rate limit, server error).
                      Softening won't help; surface to caller.
        _ERR_OTHER  — anything else (network, JSON parse, unexpected exception).
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
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # HTTPError is a subclass of URLError; must catch first.
        error_body = e.read().decode("utf-8", errors="replace")
        return None, f"{_ERR_HTTP}{e.code}: {error_body[:500]}"
    except urllib.error.URLError as e:
        # DNS resolution failure, connection refused, TLS error, etc.
        return None, f"{_ERR_OTHER}URLError: {e.reason}"
    except TimeoutError as e:
        return None, f"{_ERR_OTHER}timeout: {e}"
    except json.JSONDecodeError as e:
        return None, f"{_ERR_OTHER}invalid JSON in response: {e}"

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

    return None, f"{_ERR_FILTER}No image in response: {json.dumps(body)[:500]}"


# --- Portrait Pre-Stylization (Issue #31) ---
#
# When a deck has an Illustration Style Anchor (e.g., retro tech-manual sepia,
# watercolor, ink-on-parchment), neither --aesthetic photo (palette mismatch)
# nor --aesthetic comic_book (fixed warm-Marvel palette) produces a portrait
# that fits the deck. The two-pass solution: first stylize the speaker photo
# into the deck's anchor (one Gemini image-edit call), then run the normal
# composition step using the stylized portrait as input. Output palette
# matches the anchor automatically.

_PORTRAIT_STYLIZE_PROMPT_TEMPLATE = (
    "Render this portrait in the following illustration style: {anchor}. "
    "Preserve identifying features (hair, beard, glasses, hat, accessories) "
    "so the person remains recognizable. Output only the stylized portrait, "
    "framed as a headshot from the shoulders up, on a neutral background "
    "consistent with the requested style."
)


def stylize_portrait(speaker_b64, speaker_mime, anchor, model, api_key):
    """Pre-stylize the speaker photo to match a deck illustration style anchor.

    Returns (stylized_b64, stylized_mime) on success, or raises RuntimeError on
    failure. The composition pipeline downstream treats the stylized portrait
    as if it were the original speaker photo.
    """
    prompt = _PORTRAIT_STYLIZE_PROMPT_TEMPLATE.format(anchor=anchor)
    parts = [
        {"inlineData": {"mimeType": speaker_mime, "data": speaker_b64}},
        {"text": prompt},
    ]
    image_bytes, result = call_gemini(parts, model, api_key)
    if image_bytes is None:
        # Either FILTER, HTTP, or OTHER. Caller decides how to surface; we
        # don't soften the prompt for stylization because the prompt is
        # already minimal (no viral-styling demands or face-preservation
        # absolutes). If Gemini rejects this, the deck's anchor is likely
        # the trigger and softening won't help.
        raise RuntimeError(
            f"Portrait pre-stylization failed: {result}"
        )
    stylized_b64 = base64.b64encode(image_bytes).decode("utf-8")
    return stylized_b64, result  # `result` is the mime_type on success


# --- Prompt Construction ---
#
# Prompt softening note (Issue #19):
# Gemini's safety filter rejects prompts that combine assertive face-preservation
# language ("maintain exact facial features, bone structure...") with viral-
# styling demands ("high visual energy, competes against hundreds of others")
# when applied to a real-person photograph. Softer framing — "combine these two
# images into a 16:9 graphic, image 2 goes in a circular badge" — passes through
# on gemini-3-pro-image-preview. We apply viral styling to TYPOGRAPHY and
# COMPOSITION rather than to the face, and avoid realism claims.
#
# Aesthetic note (Issue #23):
# `aesthetic="photo"` (default) is the conservative path: photographic
# composite, face left natural. `aesthetic="comic_book"` is the viral path:
# the entire frame is rendered as a comic-book illustration — speaker
# caricatured in line-art with halftone shading, scene rendered in matching
# style. The comic-book treatment side-steps the safety filter (the face is
# being interpreted, not modified) and matches the speaker's documented
# on-brand "comic-book aesthetic". Reverse-engineered from the JCON 2026
# "Never Trust a Monkey" winner; will become default once it generalizes.

AESTHETIC_PHOTO = "photo"
AESTHETIC_COMIC_BOOK = "comic_book"
VALID_AESTHETICS = (AESTHETIC_PHOTO, AESTHETIC_COMIC_BOOK)

VALID_SOFTNESS = ("default", "softer", "softest")


def build_thumbnail_prompt(title, style="slide_dominant", title_position="top",
                           subtitle=None, brand_colors=None, softness="default",
                           aesthetic=AESTHETIC_PHOTO):
    """Build the Gemini prompt for thumbnail generation.

    aesthetic:
        "photo"      — photographic composite; face natural and unmodified.
        "comic_book" — full comic-book illustration; speaker caricatured.

    softness (progressively shorter prompts to evade the safety filter):
        "default"  — full prompt: base + typography styling + composition energy
        "softer"   — drops the composition-energy modifier; typography stays
        "softest"  — drops typography too; minimal composition framing only
    """
    if aesthetic not in VALID_AESTHETICS:
        raise ValueError(
            f"Unknown aesthetic {aesthetic!r}; expected one of {VALID_AESTHETICS}"
        )
    if softness not in VALID_SOFTNESS:
        raise ValueError(
            f"Unknown softness {softness!r}; expected one of {VALID_SOFTNESS}"
        )

    style_desc = STYLE_VARIANTS.get(style, STYLE_VARIANTS["slide_dominant"])
    position_desc = TITLE_POSITION_GUIDANCE.get(title_position,
                                                 TITLE_POSITION_GUIDANCE["top"])

    subtitle_line = ""
    if subtitle:
        subtitle_line = (
            f'\nInclude the subtitle "{subtitle}" in a smaller font near the '
            f"main title text, clearly subordinate to the main title."
        )

    brand_guidance = ""
    if brand_colors:
        brand_guidance = (
            f"\nBRAND COLORS: Use these colors as accents for text outlines, "
            f"dividers, or highlights: {', '.join(brand_colors)}. "
            f"Do not let them dominate — they are accents, not backgrounds."
        )

    if aesthetic == AESTHETIC_COMIC_BOOK:
        return _build_comic_book_prompt(
            title, style_desc, position_desc, subtitle_line, brand_guidance, softness
        )
    return _build_photo_prompt(
        title, style_desc, position_desc, subtitle_line, brand_guidance, softness
    )


def _build_photo_prompt(title, style_desc, position_desc, subtitle_line,
                        brand_guidance, softness):
    """Photographic composite: face natural, slide as background, viral typography."""
    base = f"""Combine the two provided images into a single 16:9 graphic, \
1280x720 pixels.

IMAGE 1 is a presentation slide. Use it as the background visual element; \
you may crop or zoom to fill the frame. Preserve its legibility.

IMAGE 2 is a portrait photo. Composite it into the foreground following \
this layout: {style_desc} Keep the person's appearance natural and \
unmodified — this is a compositing task, not a retouching task.

Add the title text "{title}" in a bold, heavy-weight sans-serif font with a \
thick outline or drop shadow so it reads clearly at small sizes. \
{position_desc}{subtitle_line}"""

    if softness == "softest":
        return base + brand_guidance

    typography_styling = """

TYPOGRAPHY: High contrast between text and background. Warm accent colors \
(reds, yellows, oranges) are preferred for the title treatment. The title \
should be the primary visual hook."""

    if softness == "softer":
        return base + typography_styling + brand_guidance

    composition_energy = """

COMPOSITION: Single clear focal point. Clean layout — one idea, not \
cluttered. Strong visual hierarchy: slide imagery supports the title, \
the portrait adds human presence, the title carries the message."""

    return base + typography_styling + composition_energy + brand_guidance


def _build_comic_book_prompt(title, style_desc, position_desc, subtitle_line,
                             brand_guidance, softness):
    """Comic-book illustration: caricatured speaker, halftone-shaded scene."""
    base = f"""Render a single 16:9 comic-book illustration, 1280x720 pixels, \
combining the two provided images.

IMAGE 1 is a presentation slide. Reinterpret its scene and key visual \
elements in comic-book style: bold ink outlines, halftone dot shading, \
exaggerated dynamic angles, action lines and impact effects where motion is \
implied. Use it as the full background of the frame. Preserve recognizable \
imagery so the slide's idea still reads.

IMAGE 2 is a portrait photo of the speaker. Render the speaker as a \
comic-book caricature in matching style: thick ink outlines, halftone \
shading, slight stylized exaggeration. Preserve identifying features — \
hair, beard, glasses, hat, and any other distinguishing accessories visible \
in the reference — so the speaker is immediately recognizable. Place the \
caricature in the foreground following this layout: {style_desc}

Add the title text "{title}" in a bold, heavy-weight sans-serif font with a \
thick black outline and a thin contrasting inner outline (classic \
blockbuster comic-book treatment). The title must read clearly at 160x90 \
pixels (YouTube search-result size). {position_desc}{subtitle_line}"""

    if softness == "softest":
        return base + brand_guidance

    typography_styling = """

TYPOGRAPHY: Yellow or warm-accent title color preferred, with thick black \
outline plus a thin white inner outline. High contrast against the scene \
behind it. The title is the primary visual hook."""

    if softness == "softer":
        return base + typography_styling + brand_guidance

    composition_energy = """

COMPOSITION: Single clear focal point — the caricatured speaker plus a \
recognizable scene behind them. Warm palette (reds, oranges, yellows) with \
halftone backgrounds and sunburst or radiating action lines. Keep the layout \
readable at thumbnail size: one idea, not cluttered."""

    return base + typography_styling + composition_energy + brand_guidance


# --- Slide Extraction ---

def extract_slide_from_pptx(pptx_path, slide_num, output_path=None):
    """Extract a slide image from a PPTX deck.

    Tries LibreOffice headless first, then PowerPoint AppleScript on macOS.
    Returns the output path on success, None on failure.
    """
    if not os.path.isfile(pptx_path):
        print(f"ERROR: Deck not found: {pptx_path}")
        return None

    if output_path is None:
        output_dir = os.path.dirname(os.path.abspath(pptx_path))
        output_path = os.path.join(output_dir, f"slide-{slide_num}.png")

    # Try LibreOffice headless
    try:
        tmpdir = os.path.join(os.path.dirname(os.path.abspath(pptx_path)), "_lo_export_tmp")
        os.makedirs(tmpdir, exist_ok=True)

        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "png",
             "--outdir", tmpdir, os.path.abspath(pptx_path)],
            capture_output=True, text=True, timeout=120,
        )

        if result.returncode == 0:
            # LibreOffice exports all slides; find the right one
            basename = os.path.splitext(os.path.basename(pptx_path))[0]
            # LibreOffice names them basename.png for single-page or
            # basename-N.png for multi-page (varies by version)
            candidates = sorted([
                f for f in os.listdir(tmpdir)
                if f.startswith(basename) and f.endswith(".png")
            ])
            if slide_num <= len(candidates):
                src = os.path.join(tmpdir, candidates[slide_num - 1])
                import shutil
                shutil.move(src, output_path)
                # Clean up
                import shutil as _shutil
                _shutil.rmtree(tmpdir, ignore_errors=True)
                print(f"Extracted slide {slide_num} via LibreOffice: {output_path}")
                return output_path

        # Clean up on failure
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    except FileNotFoundError:
        pass  # LibreOffice not installed
    except subprocess.TimeoutExpired:
        print("WARNING: LibreOffice timed out")
    except Exception as e:
        print(f"WARNING: LibreOffice extraction failed: {e}")

    # Try PowerPoint AppleScript on macOS
    if sys.platform == "darwin":
        try:
            script = f"""
            tell application "Microsoft PowerPoint"
                open "{os.path.abspath(pptx_path)}"
                delay 2
                set theSlide to slide {slide_num} of active presentation
                save theSlide in "{os.path.abspath(output_path)}" as save as PNG
                close active presentation saving no
            end tell
            """
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and os.path.isfile(output_path):
                print(f"Extracted slide {slide_num} via PowerPoint AppleScript: {output_path}")
                return output_path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        except Exception as e:
            print(f"WARNING: PowerPoint AppleScript failed: {e}")

    print(f"ERROR: Could not extract slide {slide_num} from {pptx_path}")
    print("Please provide a screenshot of the slide manually.")
    return None


# --- Compose Mode ---

def compose_thumbnail(args):
    """Generate a thumbnail by composing slide image + speaker photo via Gemini."""
    api_key = load_api_key(args.vault)
    model = args.model or DEFAULT_MODEL

    # Load images
    print(f"Loading slide image: {args.slide_image}")
    slide_b64, slide_mime = load_image_as_base64(args.slide_image)

    print(f"Loading speaker photo: {args.speaker_photo}")
    speaker_b64, speaker_mime = load_image_as_base64(args.speaker_photo)

    # Parse brand colors
    brand_colors = None
    if args.brand_colors:
        brand_colors = [c.strip() for c in args.brand_colors.split(",")]

    print(f"Model: {model}")
    print(f"Aesthetic: {args.aesthetic}")
    print(f"Style: {args.style}")
    print(f"Title: \"{args.title}\"")
    if args.subtitle:
        print(f"Subtitle: \"{args.subtitle}\"")

    # Pre-stylize portrait to match the deck's illustration anchor when set.
    # This makes the composition step's input photo already palette-matched
    # to the anchor, fixing the "skin tones beside sepia" mismatch that both
    # standard aesthetics produce on illustrated decks. See Issue #31.
    if args.portrait_style:
        print(f"Pre-stylizing portrait to anchor: {args.portrait_style[:80]}"
              f"{'...' if len(args.portrait_style) > 80 else ''}")
        speaker_b64, speaker_mime = stylize_portrait(
            speaker_b64, speaker_mime, args.portrait_style, model, api_key,
        )

    print("Generating thumbnail...")

    # Build the image parts once; the prompt text is rebuilt per softness level.
    image_parts = [
        {"inlineData": {"mimeType": slide_mime, "data": slide_b64}},
        {"inlineData": {"mimeType": speaker_mime, "data": speaker_b64}},
    ]

    # Retry ladder fires ONLY on safety-filter rejections (call_gemini returns
    # an error prefixed with _ERR_FILTER). Softening the prompt cannot fix
    # transport-level failures (HTTP errors, network exceptions), so those
    # surface immediately instead of burning the full ladder.
    image_bytes, result_mime = None, None
    last_error = None
    for softness in VALID_SOFTNESS:
        prompt = build_thumbnail_prompt(
            title=args.title,
            style=args.style,
            title_position=args.title_position,
            subtitle=args.subtitle,
            brand_colors=brand_colors,
            softness=softness,
            aesthetic=args.aesthetic,
        )
        parts = image_parts + [{"text": prompt}]
        image_bytes, result_mime = call_gemini(parts, model, api_key)
        if image_bytes is not None:
            if softness != "default":
                print(f"  (succeeded on '{softness}' retry after filter rejection)")
            break
        last_error = result_mime
        if not last_error.startswith(_ERR_FILTER):
            # Transport-level failure — softening won't help. Fail loud.
            print(
                f"ERROR: Gemini API request failed (non-filter error): {last_error}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"  '{softness}' attempt rejected by safety filter: {last_error[:200]}",
              file=sys.stderr)

    if image_bytes is None:
        print(
            f"ERROR: Gemini API rejected all three softness levels. "
            f"Last error: {last_error}",
            file=sys.stderr,
        )
        print(
            "Face-composition prompts are model-dependent. See "
            "rules/thumbnail-generation-rules.md for known limitations.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate and resize to YouTube specs
    final_bytes, final_mime = validate_and_resize(image_bytes, result_mime)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        outline_dir = os.path.dirname(os.path.abspath(args.slide_image))
        ext = ".png" if final_mime == "image/png" else ".jpg"
        output_path = os.path.join(outline_dir, f"thumbnail{ext}")

    with open(output_path, "wb") as f:
        f.write(final_bytes)

    size_kb = len(final_bytes) / 1024
    print(f"Thumbnail saved: {output_path}")
    print(f"  Dimensions: {YOUTUBE_WIDTH}x{YOUTUBE_HEIGHT}")
    print(f"  Size: {size_kb:.0f} KB")
    print(f"  Format: {final_mime}")

    return output_path


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Generate a YouTube thumbnail for a presentation.",
        epilog="Composes slide image + speaker photo via Gemini API.",
    )

    # Compose mode arguments
    parser.add_argument("--slide-image", help="Path or URL to the slide image")
    parser.add_argument("--speaker-photo", help="Path or URL to the speaker photo")
    parser.add_argument("--title", help="Thumbnail title text (3-5 word hook)")
    parser.add_argument("--subtitle", help="Optional subtitle (e.g., conference name)")
    parser.add_argument("--output", "-o", help="Output path (default: thumbnail.png)")
    parser.add_argument("--vault", help="Path to rhetoric-knowledge-vault (for secrets.json)")
    parser.add_argument("--style", choices=["slide_dominant", "split_panel", "overlay"],
                        default="slide_dominant",
                        help="Thumbnail composition layout (default: slide_dominant)")
    parser.add_argument("--aesthetic", choices=list(VALID_AESTHETICS),
                        default=AESTHETIC_PHOTO,
                        help="Rendering aesthetic (default: photo). 'comic_book' "
                             "produces a caricatured, halftone-shaded illustration "
                             "in the speaker's on-brand comic-book style.")
    parser.add_argument("--portrait-style", default=None,
                        help="Deck Illustration Style Anchor. When set, the "
                             "speaker photo is first pre-stylized to match the "
                             "anchor (e.g., retro tech-manual sepia, watercolor) "
                             "before composition — fixes palette mismatch on "
                             "decks with a strong visual style. Pass through from "
                             "Phase 2's STYLE ANCHOR block when present.")
    parser.add_argument("--title-position", choices=["top", "bottom", "overlay"],
                        default="top",
                        help="Title text position (default: top)")
    parser.add_argument("--brand-colors", help="Comma-separated brand hex colors")
    parser.add_argument("--model", help=f"Gemini model (default: {DEFAULT_MODEL})")

    # Extract-slide mode
    parser.add_argument("--extract-slide", nargs=2, metavar=("PPTX", "SLIDE_NUM"),
                        help="Extract a slide image from a PPTX deck")

    args = parser.parse_args()

    # Extract-slide mode
    if args.extract_slide:
        pptx_path, slide_num_str = args.extract_slide
        try:
            slide_num = int(slide_num_str)
        except ValueError:
            print(f"ERROR: Invalid slide number: {slide_num_str}")
            sys.exit(1)
        result = extract_slide_from_pptx(pptx_path, slide_num, args.output)
        sys.exit(0 if result else 1)

    # Compose mode — validate required args
    if not args.slide_image:
        parser.error("--slide-image is required for thumbnail generation")
    if not args.speaker_photo:
        parser.error("--speaker-photo is required for thumbnail generation")
    if not args.title:
        parser.error("--title is required for thumbnail generation")

    compose_thumbnail(args)


if __name__ == "__main__":
    main()
