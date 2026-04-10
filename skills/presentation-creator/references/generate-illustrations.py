#!/usr/bin/env python3
"""
Generate illustrations for a presentation outline.

Parses the outline markdown for style anchors and per-slide image prompts,
generates images via the Gemini API, and saves them to an illustrations/ directory.

Usage:
    python3 generate-illustrations.py <outline.md> all
    python3 generate-illustrations.py <outline.md> remaining
    python3 generate-illustrations.py <outline.md> 2 5 9
    python3 generate-illustrations.py <outline.md> 2-10
    python3 generate-illustrations.py <outline.md> --compare 2

Requires:
    - GEMINI_API_KEY environment variable
    - Python 3.7+ (stdlib only — no pip install needed)
"""

import argparse
import base64
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# --- Constants ---

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Curated list of Gemini models known to support image generation.
# Used by --compare mode. Update as new models become available.
COMPARE_MODELS = [
    "gemini-2.0-flash-preview-image-generation",
    "gemini-2.0-flash-exp",
    "imagen-3.0-generate-002",
]

RATE_LIMIT_DELAY = 5  # seconds between API requests


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
    anchor_pattern = re.compile(
        r"###\s+STYLE ANCHOR\s+\((\w+)\s*—[^)]*\)\s*\n>\s*(.+?)(?=\n###|\n---|\n##|\Z)",
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
        fmt_match = re.search(r"-\s*Format:\s*\*\*(\w+)\*\*", block)
        slide_format = fmt_match.group(1) if fmt_match else None

        # Extract image prompt
        prompt_match = re.search(r"-\s*Image prompt:\s*`(.+?)`", block, re.DOTALL)
        prompt = prompt_match.group(1).strip() if prompt_match else None

        if prompt:
            result["slides"].append({
                "slide_num": slide_num,
                "title": title,
                "format": slide_format,
                "prompt": prompt,
            })

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
                int(re.search(r"slide-(\d+)", f).group(1))
                for f in glob.glob(pattern)
                if re.search(r"slide-(\d+)", f)
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


# --- Gemini API ---

def generate_image(prompt, model, api_key):
    """Call the Gemini generateContent API to produce an image.

    Returns:
        tuple (image_bytes, mime_type) on success, or (None, error_message) on failure.
    """
    url = f"{GEMINI_API_BASE}/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
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
    except Exception as e:
        return None, str(e)

    # Extract image from response
    try:
        candidates = body.get("candidates", [])
        for candidate in candidates:
            parts = candidate.get("content", {}).get("parts", [])
            for part in parts:
                if "inlineData" in part:
                    inline = part["inlineData"]
                    image_bytes = base64.b64decode(inline["data"])
                    mime_type = inline.get("mimeType", "image/png")
                    return image_bytes, mime_type
    except (KeyError, IndexError):
        pass

    return None, f"No image in response: {json.dumps(body)[:500]}"


def mime_to_ext(mime_type):
    """Convert MIME type to file extension."""
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return mapping.get(mime_type, ".png")


# --- Main Commands ---

def run_generate(outline_path, slide_args):
    """Generate illustrations for selected slides."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: Set the GEMINI_API_KEY environment variable.")
        print("Get a key from https://aistudio.google.com/app/apikey")
        sys.exit(1)

    outline = parse_outline(outline_path)

    if not outline["model"]:
        print("ERROR: No model found in outline. Add a **Model:** `model-name` line")
        print("to the Illustration Style Anchor section.")
        sys.exit(1)

    if not outline["slides"]:
        print("No slides with image prompts found in the outline.")
        sys.exit(0)

    output_dir = os.path.join(os.path.dirname(os.path.abspath(outline_path)), "illustrations")
    os.makedirs(output_dir, exist_ok=True)

    to_generate = parse_slide_selection(slide_args, outline["slides"], output_dir)

    if not to_generate:
        print("Nothing to generate — all requested slides already have images.")
        sys.exit(0)

    slides_by_num = {s["slide_num"]: s for s in outline["slides"]}
    model = outline["model"]

    print(f"Model: {model}")
    print(f"Style anchors: {', '.join(outline['anchors'].keys()) or 'none'}")
    print(f"Generating {len(to_generate)} illustration(s): slides {', '.join(map(str, to_generate))}")
    print(f"Output: {output_dir}/")
    print()

    success = 0
    failed = 0

    for i, num in enumerate(to_generate):
        slide = slides_by_num[num]
        prompt = resolve_prompt(slide["prompt"], slide["format"], outline["anchors"])

        print(f"[{i+1}/{len(to_generate)}] Slide {num}: {slide['title']}")

        image_bytes, result = generate_image(prompt, model, api_key)

        if image_bytes is None:
            print(f"  FAILED: {result}")
            failed += 1
        else:
            ext = mime_to_ext(result)
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
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: Set the GEMINI_API_KEY environment variable.")
        sys.exit(1)

    outline = parse_outline(outline_path)

    slides_by_num = {s["slide_num"]: s for s in outline["slides"]}
    if slide_num not in slides_by_num:
        print(f"ERROR: Slide {slide_num} has no image prompt in the outline.")
        available = sorted(slides_by_num.keys())
        print(f"Available slides with prompts: {', '.join(map(str, available))}")
        sys.exit(1)

    slide = slides_by_num[slide_num]
    prompt = resolve_prompt(slide["prompt"], slide["format"], outline["anchors"])

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

        image_bytes, result = generate_image(prompt, model, api_key)

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


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="Generate illustrations for a presentation outline.",
        epilog="Examples:\n"
               "  %(prog)s outline.md all\n"
               "  %(prog)s outline.md remaining\n"
               "  %(prog)s outline.md 2 5 9\n"
               "  %(prog)s outline.md 2-10\n"
               "  %(prog)s outline.md --compare 2\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("outline", help="Path to the presentation outline markdown file")
    parser.add_argument(
        "--compare",
        type=int,
        metavar="SLIDE",
        help="Compare models using the given slide number as test prompt",
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

    if args.compare:
        run_compare(args.outline, args.compare)
    else:
        run_generate(args.outline, args.slides)


if __name__ == "__main__":
    main()
