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
    python3 generate-illustrations.py <outline.md> --edit 5 "Erase the label"
    python3 generate-illustrations.py <outline.md> --build 5
    python3 generate-illustrations.py <outline.md> --build all
    python3 generate-illustrations.py <outline.md> --fix 5 "Make the road wider"
    python3 generate-illustrations.py <outline.md> -v 2 5 9

Requires:
    - Gemini API key in {vault}/secrets.json (preferred) or GEMINI_API_KEY env var (fallback)
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

# --- Constants ---

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Curated list of Gemini models known to support image generation.
# Used by --compare mode. Update as new models become available.
COMPARE_MODELS = [
    "gemini-3-pro-image-preview",
    "gemini-2.0-flash-preview-image-generation",
    "imagen-3.0-generate-002",
]

RATE_LIMIT_DELAY = 5  # seconds between API requests

IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]

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

def _load_context(outline_path, require_model=True, vault_path=None):
    """Common preamble: check API key, parse outline, compute paths.

    API key resolution order:
        1. {vault}/secrets.json → gemini.api_key
        2. GEMINI_API_KEY environment variable (backward compat)

    Returns:
        tuple (api_key, outline, output_dir)
    """
    api_key = None

    # Try secrets.json first
    if vault_path is None:
        vault_path = _cli_vault_path
    if vault_path is None:
        vault_path = os.path.expanduser("~/.claude/rhetoric-knowledge-vault")
    secrets_path = os.path.join(vault_path, "secrets.json")
    if os.path.isfile(secrets_path):
        try:
            with open(secrets_path, "r", encoding="utf-8") as f:
                secrets = json.load(f)
            api_key = secrets.get("gemini", {}).get("api_key") or None
        except (json.JSONDecodeError, OSError):
            pass

    # Fall back to env var
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("ERROR: No Gemini API key found.")
        print("Set it in {vault}/secrets.json under gemini.api_key,")
        print("or set the GEMINI_API_KEY environment variable.")
        print("Get a key from https://aistudio.google.com/app/apikey")
        sys.exit(1)

    outline = parse_outline(outline_path)

    if require_model and not outline["model"]:
        print("ERROR: No model found in outline. Add a **Model:** `model-name` line")
        print("to the Illustration Style Anchor section.")
        sys.exit(1)

    output_dir = os.path.join(
        os.path.dirname(os.path.abspath(outline_path)), "illustrations"
    )
    return api_key, outline, output_dir


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


def generate_image(prompt, model, api_key):
    """Call the Gemini generateContent API to produce an image.

    Returns:
        tuple (image_bytes, mime_type) on success, or (None, error_message) on failure.
    """
    return _call_gemini([{"text": prompt}], model, api_key)


def edit_image(input_path, edit_prompt, model, api_key):
    """Call the Gemini API to edit an existing image.

    Sends the image as base64 inline data along with a text edit prompt.
    Auto-appends safety suffixes to prevent unwanted additions.

    Returns:
        tuple (image_bytes, mime_type) on success, or (None, error_message) on failure.
    """
    # Read and encode the input image
    with open(input_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    # Detect MIME type from extension
    ext = os.path.splitext(input_path)[1].lower()
    input_mime = ext_to_mime(ext)

    # Auto-append safety suffixes if not already present
    suffixes = []
    lower_prompt = edit_prompt.lower()
    if "do not add any new elements" not in lower_prompt:
        suffixes.append("DO NOT add any new elements.")
    if "let background continue naturally" not in lower_prompt:
        suffixes.append("Let background continue naturally -- no parchment patch.")
    if suffixes:
        edit_prompt = edit_prompt.rstrip(". ") + ". " + " ".join(suffixes)

    parts = [
        {"inlineData": {"mimeType": input_mime, "data": image_data}},
        {"text": edit_prompt},
    ]
    return _call_gemini(parts, model, api_key)


# --- Main Commands ---

def run_generate(outline_path, slide_args, versioned=False):
    """Generate illustrations for selected slides."""
    api_key, outline, output_dir = _load_context(outline_path)
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

        print(f"[{i+1}/{len(to_generate)}] Slide {num}: {slide['title']}")

        image_bytes, result = generate_image(prompt, model, api_key)

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
    api_key, outline, _ = _load_context(outline_path, require_model=False)

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


def run_edit(outline_path, slide_num, edit_prompt):
    """Edit an existing slide illustration using Gemini's image editing API."""
    api_key, outline, output_dir = _load_context(outline_path)
    model = outline["model"]

    input_path = find_base_image(output_dir, slide_num)
    if not input_path:
        print(f"ERROR: No existing image found for slide {slide_num} in {output_dir}/")
        print("Generate the base image first, then edit it.")
        sys.exit(1)

    print(f"Model: {model}")
    print(f"Input: {input_path}")
    print(f"Edit prompt: {edit_prompt}")

    # Save as versioned output (never overwrite)
    ver = next_version(output_dir, slide_num)

    image_bytes, result = edit_image(input_path, edit_prompt, model, api_key)

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
    api_key, outline, output_dir = _load_context(outline_path)
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

        # Copy full image as the final build step
        final_step = max(s["step"] for s in steps)
        final_build = steps[-1] if steps else None
        if final_build and final_build["is_full"]:
            dest = os.path.join(builds_dir, f"slide-{num:02d}-build-{final_step:02d}.jpg")
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

            image_bytes, result = edit_image(prev_image, desc, model, api_key)

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
    api_key, outline, output_dir = _load_context(outline_path)
    model = outline["model"]

    input_path = find_latest_image(output_dir, slide_num)
    if not input_path:
        print(f"ERROR: No existing image found for slide {slide_num}")
        sys.exit(1)

    ver = next_version(output_dir, slide_num)
    print(f"Model: {model}")
    print(f"Input: {os.path.basename(input_path)}")
    print(f"Fix: {fix_prompt}")
    print(f"Output: slide-{slide_num:02d}-v{ver}")

    image_bytes, result = edit_image(input_path, fix_prompt, model, api_key)

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
