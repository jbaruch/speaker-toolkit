#!/usr/bin/env python3
"""Verify a talk skill's source, rendered attachment, and downloadable bytes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

import yaml


class SkillPage(HTMLParser):
    """Collect the site's skill section and download link from rendered HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.section = False
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        classes = (fields.get("class") or "").split()
        if tag == "section" and "talk-skill" in classes:
            self.section = True
        href = fields.get("href")
        if tag == "a" and "talk-skill__raw" in classes and href:
            self.links.add(href)


def validate_source(site: Path, stem: str) -> tuple[Path, bytes, str]:
    """Validate a paired single-file skill without modifying the source."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", stem):
        raise ValueError("Use the existing talk filename stem (lowercase kebab-case)")
    page = site / "_talks" / f"{stem}.md"
    if not page.is_file():
        raise ValueError(f"Create the matching talk page first: {page}")
    skill = site / "_skills" / stem / "SKILL.md"
    raw = skill.read_bytes()
    text = raw.decode("utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
    if not match:
        raise ValueError(f"Add YAML frontmatter at the start of {skill}")
    data = yaml.safe_load(match[1])
    if not isinstance(data, dict):
        raise ValueError(f"Frontmatter must be a mapping: {skill}")
    name = data.get("name")
    if (
        not isinstance(name, str)
        or len(name) > 64
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
    ):
        raise ValueError(
            f"Set name to 1–64 lowercase letters/digits/single hyphens: {skill}"
        )
    description = data.get("description")
    if (
        not isinstance(description, str)
        or not description.strip()
        or len(description) > 1024
    ):
        raise ValueError(
            f"Set a nonblank description of at most 1024 characters: {skill}"
        )
    if not text[match.end() :].strip():
        raise ValueError(f"Write substantive talk teaching in the skill body: {skill}")
    if len(text.splitlines()) >= 500:
        raise ValueError(
            f"Condense the single-file skill to fewer than 500 lines: {skill}"
        )
    companions = [p.name for p in skill.parent.iterdir() if p.name != "SKILL.md"]
    if companions:
        raise ValueError(
            f"Only SKILL.md is served; inline required companion content: {companions}"
        )
    return skill, raw, name


def check_rendered(html: bytes, raw: bytes, expected: bytes, skill_path: str) -> None:
    """Require a rendered skill section, its download link, and exact raw content."""
    if raw != expected:
        raise ValueError(
            "Raw skill differs from source; rebuild/deploy the matching commit"
        )
    page = SkillPage()
    page.feed(html.decode("utf-8"))
    if not page.section or skill_path not in page.links:
        raise ValueError(
            "Skill section/download link missing; check site support and matching page stem"
        )


def fetch(url: str) -> bytes:
    """Read a deployed resource, rejecting non-200 responses."""
    with urlopen(url, timeout=30) as response:
        if response.status != 200:
            raise ValueError(f"Expected HTTP 200; received {response.status}: {url}")
        return response.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument(
        "--site", required=True, type=Path, help="Shownotes source repository"
    )
    parser.add_argument("--stem", required=True, help="Talk filename without .md")
    parser.add_argument("--build-dir", type=Path, help="Fresh Jekyll output directory")
    parser.add_argument(
        "--site-url", help="Deployed site origin, e.g. https://speaking.jbaru.ch"
    )
    parser.add_argument("--baseurl", default="", help="Jekyll baseurl, e.g. /shownotes")
    args = parser.parse_args(argv)
    try:
        skill, raw, name = validate_source(args.site, args.stem)
        base = args.baseurl.rstrip("/")
        if base and (not base.startswith("/") or base.startswith("//")):
            raise ValueError(
                "--baseurl must be empty or a site-relative path such as /shownotes"
            )
        skill_path = f"{base}/skills/{args.stem}/SKILL.md"
        page_path = f"{base}/talks/{args.stem}/"
        report = {
            "ok": True,
            "name": name,
            "skill_path": str(skill),
            "checks": ["source"],
        }
        if args.build_dir:
            check_rendered(
                (args.build_dir / "talks" / args.stem / "index.html").read_bytes(),
                (args.build_dir / "skills" / args.stem / "SKILL.md").read_bytes(),
                raw,
                skill_path,
            )
            report["checks"].append("build")
        if args.site_url:
            origin = args.site_url.rstrip("/")
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError(
                    "--site-url must be an HTTP(S) origin; pass its path via --baseurl"
                )
            check_rendered(
                fetch(origin + page_path), fetch(origin + skill_path), raw, skill_path
            )
            report["checks"].append("live")
            report["skill_url"] = origin + skill_path
        print(json.dumps(report))
        return 0
    # The agent expects JSON even on failure; a traceback leaves no verdict.
    # Emit ok:false plus stderr so a failed verification cannot look like success.
    except Exception as exc:  # noqa: BLE001 — outer-boundary-process-contract
        print(json.dumps({"ok": False, "error": str(exc)}))
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
