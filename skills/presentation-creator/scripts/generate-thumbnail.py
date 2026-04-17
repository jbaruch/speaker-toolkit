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

def call_gemini(parts, model, api_key):
    """Send parts to Gemini generateContent API and extract the image.

    Returns (image_bytes, mime_type) on success, (None, error_message) on failure.
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
        error_body = e.read().decode("utf-8", errors="replace")
        return None, f"HTTP {e.code}: {error_body[:500]}"
    except Exception as e:
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


# --- Prompt Construction ---

def build_thumbnail_prompt(title, style="slide_dominant", title_position="top",
                           subtitle=None, brand_colors=None):
    """Build the Gemini prompt for thumbnail generation.

    The prompt follows the DeepMind 5-component model (Style, Subject,
    Setting, Action, Composition) with YouTube-specific optimizations.
    """
    style_desc = STYLE_VARIANTS.get(style, STYLE_VARIANTS["slide_dominant"])
    position_desc = TITLE_POSITION_GUIDANCE.get(title_position,
                                                 TITLE_POSITION_GUIDANCE["top"])

    subtitle_line = ""
    if subtitle:
        subtitle_line = (
            f'\nAlso include the subtitle "{subtitle}" in a smaller font '
            f"near the title text, clearly subordinate to the main title."
        )

    brand_guidance = ""
    if brand_colors:
        brand_guidance = (
            f"\nBRAND COLORS: Use these colors as accents for text outlines, "
            f"dividers, or highlights: {', '.join(brand_colors)}. "
            f"Do not let them dominate — they are accents, not backgrounds."
        )

    prompt = f"""STYLE: Professional YouTube video thumbnail photograph. High contrast, \
vibrant, attention-grabbing. {style_desc}

SUBJECT: Two visual elements to compose together:
1. "The slide" — the provided slide image. Use as the dominant background \
visual element. Maintain the key visual content but you may crop, zoom, \
or adjust to fill the frame dynamically.
2. "The speaker" — the provided speaker photo. Maintain exact facial \
features, bone structure, skin texture, and natural appearance from the \
reference. Do not stylize, beautify, alter, or idealize the face. \
{EXPRESSION_DEFAULT}

TEXT: Add the text "{title}" in bold, heavy-weight sans-serif font with \
thick outline or drop shadow for maximum contrast. Text must be readable \
when the thumbnail is displayed at 160x90 pixels (YouTube search result \
size). {position_desc}{subtitle_line}

COMPOSITION: 16:9 aspect ratio, 1280x720 pixels. Single clear focal \
point. The speaker's face should be prominently visible — thumbnails with \
expressive faces get 35-50% higher click-through rates. {style_desc}
{brand_guidance}

CRITICAL REQUIREMENTS:
- The speaker's face must be clearly visible and recognizable
- Text must be readable at small sizes (bold, high contrast, outlined)
- High visual energy — this thumbnail competes against hundreds of others
- Clean composition — one idea, not cluttered
- Warm accent colors (reds, yellows, oranges) for emotional engagement"""

    return prompt


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

    # Build prompt
    prompt = build_thumbnail_prompt(
        title=args.title,
        style=args.style,
        title_position=args.title_position,
        subtitle=args.subtitle,
        brand_colors=brand_colors,
    )

    print(f"Model: {model}")
    print(f"Style: {args.style}")
    print(f"Title: \"{args.title}\"")
    if args.subtitle:
        print(f"Subtitle: \"{args.subtitle}\"")
    print("Generating thumbnail...")

    # Build multimodal request parts
    parts = [
        {"inlineData": {"mimeType": slide_mime, "data": slide_b64}},
        {"inlineData": {"mimeType": speaker_mime, "data": speaker_b64}},
        {"text": prompt},
    ]

    image_bytes, result_mime = call_gemini(parts, model, api_key)

    if image_bytes is None:
        print(f"ERROR: Gemini API failed: {result_mime}")
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
                        help="Thumbnail composition style (default: slide_dominant)")
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
