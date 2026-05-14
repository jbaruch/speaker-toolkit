#!/usr/bin/env python3
"""Extract resource references from outline.yaml.

Walks the validated Outline and extracts URLs, GitHub/GitLab repos,
book/paper references, RFC/standards citations, and tool/library
mentions. Produces a resources.json (or markdown) file for speaker
review and shownotes publishing.

Image prompts are excluded — generation prompts often contain incidental
URLs that aren't actual talk resources.

Usage:
    python3 extract-resources.py <outline.yaml>
    python3 extract-resources.py <outline.yaml> --output resources.json
    python3 extract-resources.py <outline.yaml> --format markdown
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import yaml  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import outline_schema as _os  # noqa: E402


# --- Outline parsing (YAML → flat parsed-line tuples) ----------------


def parse_outline_yaml(outline: _os.Outline) -> list[tuple[int | None, str, str]]:
    """Walk the outline and emit (slide_num, section, line_text) tuples.

    Section = chapter title for slide-anchored lines; "interlude {id}" for
    interlude-anchored lines; "preamble" for talk-level metadata.

    Image prompts are excluded. Script `cue:` items are excluded (they're
    stage directions, not resource references).
    """
    chapter_titles = {c.id: c.title for c in outline.chapters}
    result: list[tuple[int | None, str, str]] = []

    # Talk-level metadata that may contain URLs
    if outline.talk.thesis:
        for line in outline.talk.thesis.splitlines():
            result.append((None, "preamble", line))
    if outline.talk.shownotes_url_base:
        result.append((None, "preamble", outline.talk.shownotes_url_base))
    if outline.talk.catalog_reference:
        result.append((None, "preamble", outline.talk.catalog_reference))

    for slide in outline.slides:
        section = chapter_titles.get(slide.chapter, slide.chapter)
        if slide.visual:
            for line in slide.visual.splitlines():
                result.append((slide.n, section, f"- Visual: {line}"))
        if slide.text_overlay:
            for line in slide.text_overlay.splitlines():
                result.append((slide.n, section, line))
        # Image prompts are deliberately excluded
        for item in slide.script:
            if item.line is not None:
                speaker = f"{item.speaker}: " if item.speaker else ""
                result.append((slide.n, section, f"- Speaker: {speaker}{item.line}"))
            elif item.parenthetical is not None:
                result.append((slide.n, section, f"  ({item.parenthetical})"))

    for il in outline.interludes:
        section = f"interlude {il.id}"
        for item in il.script:
            if item.line is not None:
                speaker = f"{item.speaker}: " if item.speaker else ""
                result.append((None, section, f"- Speaker: {speaker}{item.line}"))
            elif item.parenthetical is not None:
                result.append((None, section, f"  ({item.parenthetical})"))

    return result


def _is_speaker_note(line: str) -> bool:
    return line.strip().startswith("- Speaker:")


def _is_visual_desc(line: str) -> bool:
    s = line.strip()
    return s.startswith("- Visual:") or s.startswith("- Illustration:")


# --- Resource extractors (unchanged logic from prior version) --------


def extract_urls(parsed_lines):
    url_re = re.compile(r"https?://[^\s\)\]\},\"'`>]+")
    resources = []
    seen = set()
    for slide_num, section, line in parsed_lines:
        for match in url_re.finditer(line):
            url = match.group(0).rstrip(".,;:!?)")
            if url in seen:
                for r in resources:
                    if (r["value"] == url and slide_num
                            and slide_num not in r["slide_nums"]):
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
    repo_re = re.compile(
        r"(?:https?://)?(?:github|gitlab)\.com/"
        r"([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)",
    )
    resources = []
    seen = set()
    for slide_num, section, line in parsed_lines:
        for match in repo_re.finditer(line):
            repo = match.group(1).rstrip(".,;:!?)/")
            repo = re.sub(r"/(tree|blob|issues|pulls|releases|wiki)(/.*)?$", "", repo)
            key = repo.lower()
            if key in seen:
                for r in resources:
                    if (r["value"].lower().endswith("/" + key.split("/")[-1])
                            and slide_num and slide_num not in r["slide_nums"]):
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
    book_patterns = [
        re.compile(r'"([^"]{5,}?)"\s+by\s+([A-Z][a-zA-Z\s,.]+)', re.IGNORECASE),
        re.compile(r'\*([^*]{5,}?)\*\s+by\s+([A-Z][a-zA-Z\s,.]+)', re.IGNORECASE),
        re.compile(r'\*\*([^*]{5,}?)\*\*\s+by\s+([A-Z][a-zA-Z\s,.]+)', re.IGNORECASE),
    ]
    resources = []
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
    rfc_re = re.compile(r"\bRFC[\s-]?(\d{3,5})\b", re.IGNORECASE)
    resources = []
    seen = set()
    for slide_num, section, line in parsed_lines:
        for match in rfc_re.finditer(line):
            rfc_num = match.group(1)
            if rfc_num in seen:
                for r in resources:
                    if (r["value"] == f"RFC {rfc_num}" and slide_num
                            and slide_num not in r["slide_nums"]):
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
    tool_re = re.compile(r"`([A-Za-z][A-Za-z0-9._-]{1,40})`")
    resources = []
    seen = set()
    for slide_num, section, line in parsed_lines:
        if not (_is_speaker_note(line) or _is_visual_desc(line)):
            continue
        for match in tool_re.finditer(line):
            name = match.group(1)
            if len(name) <= 2 or name.startswith("--") or "=" in name:
                continue
            if name.lower() in (
                "true", "false", "null", "none", "n/a",
                "todo", "tbd", "wip", "fixme",
            ):
                continue
            key = name.lower()
            if key in seen:
                for r in resources:
                    if (r["value"].lower() == key and slide_num
                            and slide_num not in r["slide_nums"]):
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


# --- Context helpers -------------------------------------------------


def _slide_context(section: str, slide_num: int | None) -> str:
    if slide_num is not None:
        return f"Slide {slide_num} ({section})"
    return section


def _merge_context(existing: str, section: str, slide_num: int | None) -> str:
    new_ref = f"Slide {slide_num}" if slide_num is not None else section
    if new_ref not in existing:
        return f"{existing}, {new_ref}"
    return existing


# --- Output ----------------------------------------------------------


def build_output(resources, talk_slug=None):
    return {
        "talk_slug": talk_slug,
        "extracted_at": date.today().isoformat(),
        "resources": resources,
    }


def format_markdown(data):
    lines = ["# Extracted Resources"]
    if data["talk_slug"]:
        lines.append(f"**Talk:** {data['talk_slug']}")
    lines.append(f"**Extracted:** {data['extracted_at']}")
    lines.append(f"**Total items:** {len(data['resources'])}")
    lines.append("")
    by_type: dict[str, list] = {}
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
            slides = ", ".join(
                str(s) for s in item["slide_nums"]
            ) if item["slide_nums"] else "n/a"
            url_part = f" — {item['url']}" if item.get("url") else ""
            lines.append(f"- [ ] **{item['value']}**{url_part}")
            lines.append(f"  Slides: {slides} | Context: {item['context']}")
        lines.append("")
    return "\n".join(lines)


# --- Main ------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Extract resource references from outline.yaml.",
        epilog="Produces resources.json for speaker review before shownotes publishing.",
    )
    parser.add_argument("outline", help="Path to outline.yaml")
    parser.add_argument(
        "--output", "-o",
        help="Output path (default: resources.json next to outline.yaml)",
    )
    parser.add_argument(
        "--format", choices=["json", "markdown"], default="json",
        help="Output format (default: json)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.outline):
        print(f"ERROR: outline not found: {args.outline}", file=sys.stderr)
        sys.exit(1)

    try:
        outline = _os.load_outline(args.outline)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        print(f"failed to load {args.outline}: {exc}", file=sys.stderr)
        sys.exit(1)

    parsed = parse_outline_yaml(outline)

    resources: list[dict] = []
    resources.extend(extract_urls(parsed))
    resources.extend(extract_repos(parsed))
    resources.extend(extract_books(parsed))
    resources.extend(extract_rfcs(parsed))
    resources.extend(extract_tools(parsed))

    url_values = {r["value"] for r in resources if r["type"] == "url"}
    resources = [
        r for r in resources
        if r["type"] != "repo" or r.get("url") not in url_values
    ]

    type_order = {"url": 0, "repo": 1, "book": 2, "rfc": 3, "tool": 4}
    resources.sort(key=lambda r: (
        type_order.get(r["type"], 99),
        min(r["slide_nums"]) if r["slide_nums"] else 9999,
    ))

    data = build_output(resources, outline.talk.slug)

    if args.output:
        output_path = args.output
    else:
        outline_dir = os.path.dirname(os.path.abspath(args.outline))
        ext = ".md" if args.format == "markdown" else ".json"
        output_path = os.path.join(outline_dir, f"resources{ext}")

    content = format_markdown(data) if args.format == "markdown" \
        else json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    by_type = {}
    for r in resources:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    print(f"Extracted {len(resources)} resources from {args.outline}")
    for rtype, count in sorted(by_type.items()):
        print(f"  {rtype}: {count}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
