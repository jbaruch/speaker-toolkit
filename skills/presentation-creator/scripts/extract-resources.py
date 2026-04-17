#!/usr/bin/env python3
"""
Extract resource references from a presentation outline.

Parses the outline markdown for URLs, GitHub/GitLab repos, book/paper
references, tool/library mentions, and RFC/standards citations. Produces
a resources.json file for speaker review and shownotes publishing.

Usage:
    python3 extract-resources.py <outline.md>
    python3 extract-resources.py <outline.md> --output resources.json
    python3 extract-resources.py <outline.md> --spec presentation-spec.md
    python3 extract-resources.py <outline.md> --format markdown

Requires:
    - Python 3.7+ (stdlib only — no pip install needed)
"""

import argparse
import json
import os
import re
import sys
from datetime import date


# --- Outline Parsing ---

def _current_slide_num(line, state):
    """Update and return current slide number from heading lines."""
    m = re.match(r"###\s+Slide\s+(\d+):", line)
    if m:
        state["slide_num"] = int(m.group(1))
    return state.get("slide_num")


def _in_code_block(line, state):
    """Track whether we're inside a fenced code block."""
    if line.strip().startswith("```"):
        state["in_code"] = not state.get("in_code", False)
    return state.get("in_code", False)


def _is_image_prompt_line(line):
    """Check if a line is an image prompt field (should be excluded)."""
    stripped = line.strip()
    return stripped.startswith("- Image prompt:") or stripped.startswith("- image prompt:")


def _is_speaker_note(line):
    """Check if a line is a speaker note field."""
    stripped = line.strip()
    return stripped.startswith("- Speaker:") or stripped.startswith("- speaker:")


def _is_visual_desc(line):
    """Check if a line is a visual description field."""
    stripped = line.strip()
    return (stripped.startswith("- Visual:") or stripped.startswith("- visual:")
            or stripped.startswith("- Illustration:") or stripped.startswith("- illustration:"))


def parse_outline_text(text):
    """Parse outline text into sections with slide context.

    Returns a list of (slide_num_or_none, section_name, line_text) tuples,
    excluding code blocks and image prompt lines.
    """
    lines = text.split("\n")
    state = {"slide_num": None, "in_code": False, "section": "preamble"}
    result = []

    for line in lines:
        if _in_code_block(line, state):
            continue
        if state.get("in_code", False):
            continue
        if _is_image_prompt_line(line):
            continue

        # Track section headings
        h2 = re.match(r"##\s+(.+)", line)
        if h2:
            state["section"] = h2.group(1).strip()

        _current_slide_num(line, state)

        result.append((state.get("slide_num"), state["section"], line))

    return result


# --- Resource Extractors ---

def extract_urls(parsed_lines):
    """Extract HTTP/HTTPS URLs from outline text."""
    url_re = re.compile(r"https?://[^\s\)\]\},\"'`>]+")
    resources = []
    seen = set()

    for slide_num, section, line in parsed_lines:
        for match in url_re.finditer(line):
            url = match.group(0).rstrip(".,;:!?)")
            # Skip duplicate URLs
            if url in seen:
                # Add slide number to existing entry
                for r in resources:
                    if r["value"] == url and slide_num and slide_num not in r["slide_nums"]:
                        r["slide_nums"].append(slide_num)
                        r["context"] = _merge_context(r["context"], section, slide_num)
                continue
            seen.add(url)
            resources.append({
                "type": "url",
                "value": url,
                "context": _slide_context(section, slide_num),
                "slide_nums": [slide_num] if slide_num else [],
                "approved": False,
            })

    return resources


def extract_repos(parsed_lines):
    """Extract GitHub/GitLab repository references."""
    # Matches github.com/org/repo or gitlab.com/org/repo in URLs or plain text
    repo_re = re.compile(r"(?:https?://)?(?:github|gitlab)\.com/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)")
    resources = []
    seen = set()

    for slide_num, section, line in parsed_lines:
        for match in repo_re.finditer(line):
            repo = match.group(1).rstrip(".,;:!?)/")
            # Strip common suffixes like /tree/main, /blob/...
            repo = re.sub(r"/(tree|blob|issues|pulls|releases|wiki)(/.*)?$", "", repo)
            key = repo.lower()
            if key in seen:
                for r in resources:
                    if r["value"].lower() == key and slide_num and slide_num not in r["slide_nums"]:
                        r["slide_nums"].append(slide_num)
                continue
            seen.add(key)
            host = "github.com" if "github" in line else "gitlab.com"
            resources.append({
                "type": "repo",
                "value": f"{host}/{repo}",
                "context": _slide_context(section, slide_num),
                "slide_nums": [slide_num] if slide_num else [],
                "url": f"https://{host}/{repo}",
                "approved": False,
            })

    return resources


def extract_books(parsed_lines):
    """Extract book/paper references from Coda sections and Further Reading."""
    resources = []
    # Look for lines in Coda or Further Reading sections, or lines with
    # book-like patterns: "Book Title" by Author, ISBN patterns
    book_patterns = [
        # "Title" by Author
        re.compile(r'"([^"]{5,}?)"\s+by\s+([A-Z][a-zA-Z\s,.]+)', re.IGNORECASE),
        # *Title* by Author
        re.compile(r'\*([^*]{5,}?)\*\s+by\s+([A-Z][a-zA-Z\s,.]+)', re.IGNORECASE),
        # **Title** by Author
        re.compile(r'\*\*([^*]{5,}?)\*\*\s+by\s+([A-Z][a-zA-Z\s,.]+)', re.IGNORECASE),
    ]
    seen = set()

    for slide_num, section, line in parsed_lines:
        for pattern in book_patterns:
            for match in pattern.finditer(line):
                title = match.group(1).strip()
                key = title.lower()
                if key in seen:
                    continue
                seen.add(key)
                resources.append({
                    "type": "book",
                    "value": title,
                    "context": _slide_context(section, slide_num),
                    "slide_nums": [slide_num] if slide_num else [],
                    "approved": False,
                })

    return resources


def extract_rfcs(parsed_lines):
    """Extract RFC and standards citations."""
    rfc_re = re.compile(r"\bRFC[\s-]?(\d{3,5})\b", re.IGNORECASE)
    resources = []
    seen = set()

    for slide_num, section, line in parsed_lines:
        for match in rfc_re.finditer(line):
            rfc_num = match.group(1)
            if rfc_num in seen:
                for r in resources:
                    if r["value"] == f"RFC {rfc_num}" and slide_num and slide_num not in r["slide_nums"]:
                        r["slide_nums"].append(slide_num)
                continue
            seen.add(rfc_num)
            resources.append({
                "type": "rfc",
                "value": f"RFC {rfc_num}",
                "context": _slide_context(section, slide_num),
                "slide_nums": [slide_num] if slide_num else [],
                "url": f"https://www.rfc-editor.org/rfc/rfc{rfc_num}",
                "approved": False,
            })

    return resources


def extract_tools(parsed_lines):
    """Extract tool/library/framework mentions with slide references.

    Looks for capitalized tool names, backtick-quoted identifiers, and
    common framework patterns in speaker notes and visual descriptions.
    """
    # Common tool/framework patterns — look for backtick-quoted names
    # in speaker notes and visual descriptions
    tool_re = re.compile(r"`([A-Za-z][A-Za-z0-9._-]{1,40})`")
    resources = []
    seen = set()

    for slide_num, section, line in parsed_lines:
        # Only scan speaker notes and visual descriptions for tool mentions
        if not (_is_speaker_note(line) or _is_visual_desc(line)):
            continue
        for match in tool_re.finditer(line):
            name = match.group(1)
            # Skip things that look like code snippets or prompts
            if len(name) <= 2 or name.startswith("--") or "=" in name:
                continue
            # Skip common non-tool patterns
            if name.lower() in ("true", "false", "null", "none", "n/a",
                                "todo", "tbd", "wip", "fixme"):
                continue
            key = name.lower()
            if key in seen:
                for r in resources:
                    if r["value"].lower() == key and slide_num and slide_num not in r["slide_nums"]:
                        r["slide_nums"].append(slide_num)
                        r["context"] = _merge_context(r["context"], section, slide_num)
                continue
            seen.add(key)
            resources.append({
                "type": "tool",
                "value": name,
                "context": _slide_context(section, slide_num),
                "slide_nums": [slide_num] if slide_num else [],
                "url": None,
                "approved": False,
            })

    return resources


# --- Context Helpers ---

def _slide_context(section, slide_num):
    """Build a context string from section name and slide number."""
    if slide_num:
        return f"Slide {slide_num} ({section})"
    return section


def _merge_context(existing_context, section, slide_num):
    """Merge additional slide context into existing context string."""
    new_ref = f"Slide {slide_num}" if slide_num else section
    if new_ref not in existing_context:
        return f"{existing_context}, {new_ref}"
    return existing_context


# --- Spec Parsing ---

def read_talk_slug(spec_path):
    """Extract the talk slug from a presentation-spec.md file."""
    if not spec_path or not os.path.isfile(spec_path):
        return None
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            text = f.read()
        # Look for "Shownotes slug:" line
        m = re.search(r"Shownotes slug:\s*(\S+)", text)
        if m:
            return m.group(1).strip()
        # Fallback: look for slug in file path
        return None
    except OSError:
        return None


# --- Output ---

def build_output(resources, talk_slug=None):
    """Build the output JSON structure."""
    return {
        "talk_slug": talk_slug,
        "extracted_at": date.today().isoformat(),
        "resources": resources,
    }


def format_markdown(data):
    """Format resources as a readable markdown list for speaker review."""
    lines = []
    lines.append(f"# Extracted Resources")
    if data["talk_slug"]:
        lines.append(f"**Talk:** {data['talk_slug']}")
    lines.append(f"**Extracted:** {data['extracted_at']}")
    lines.append(f"**Total items:** {len(data['resources'])}")
    lines.append("")

    # Group by type
    by_type = {}
    for r in data["resources"]:
        by_type.setdefault(r["type"], []).append(r)

    type_labels = {
        "url": "URLs",
        "repo": "Repositories",
        "book": "Books & Papers",
        "rfc": "RFCs & Standards",
        "tool": "Tools & Libraries",
    }

    for rtype, label in type_labels.items():
        items = by_type.get(rtype, [])
        if not items:
            continue
        lines.append(f"## {label} ({len(items)})")
        lines.append("")
        for item in items:
            slides = ", ".join(str(s) for s in item["slide_nums"]) if item["slide_nums"] else "n/a"
            url_part = f" — {item['url']}" if item.get("url") else ""
            lines.append(f"- [ ] **{item['value']}**{url_part}")
            lines.append(f"  Slides: {slides} | Context: {item['context']}")
        lines.append("")

    return "\n".join(lines)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Extract resource references from a presentation outline.",
        epilog="Produces a resources.json for speaker review before shownotes publishing.",
    )
    parser.add_argument("outline", help="Path to presentation-outline.md")
    parser.add_argument("--output", "-o", help="Output path (default: resources.json in outline directory)")
    parser.add_argument("--spec", help="Path to presentation-spec.md (for talk slug)")
    parser.add_argument("--format", choices=["json", "markdown"], default="json",
                        help="Output format (default: json)")

    args = parser.parse_args()

    if not os.path.isfile(args.outline):
        print(f"ERROR: Outline not found: {args.outline}")
        sys.exit(1)

    # Read outline
    with open(args.outline, "r", encoding="utf-8") as f:
        text = f.read()

    # Parse
    parsed = parse_outline_text(text)

    # Extract all resource types
    resources = []
    resources.extend(extract_urls(parsed))
    resources.extend(extract_repos(parsed))
    resources.extend(extract_books(parsed))
    resources.extend(extract_rfcs(parsed))
    resources.extend(extract_tools(parsed))

    # Remove repo entries that are already covered by a URL entry pointing to the same repo
    url_values = {r["value"] for r in resources if r["type"] == "url"}
    resources = [r for r in resources if r["type"] != "repo"
                 or r.get("url") not in url_values]

    # Sort: URLs first, then repos, books, rfcs, tools; within each by slide number
    type_order = {"url": 0, "repo": 1, "book": 2, "rfc": 3, "tool": 4}
    resources.sort(key=lambda r: (type_order.get(r["type"], 99),
                                   min(r["slide_nums"]) if r["slide_nums"] else 9999))

    # Get talk slug
    talk_slug = read_talk_slug(args.spec)
    if not talk_slug and args.spec:
        print(f"WARNING: Could not extract talk slug from {args.spec}")

    # Auto-detect spec if not provided
    if not talk_slug:
        outline_dir = os.path.dirname(os.path.abspath(args.outline))
        auto_spec = os.path.join(outline_dir, "presentation-spec.md")
        if os.path.isfile(auto_spec):
            talk_slug = read_talk_slug(auto_spec)

    data = build_output(resources, talk_slug)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        outline_dir = os.path.dirname(os.path.abspath(args.outline))
        ext = ".md" if args.format == "markdown" else ".json"
        output_path = os.path.join(outline_dir, f"resources{ext}")

    # Write output
    if args.format == "markdown":
        content = format_markdown(data)
    else:
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Summary
    by_type = {}
    for r in resources:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1

    print(f"Extracted {len(resources)} resources from {args.outline}")
    for rtype, count in sorted(by_type.items()):
        print(f"  {rtype}: {count}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
