"""Exercise single-file talk skill validation and download integrity end to end."""

import json
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills/shownotes-publisher/scripts/verify-talk-skill.py"
)
STEM = "2024-06-12-evaluate-ai-claims"
SKILL = """---
name: evaluate-ai-claims
description: Evaluate AI productivity claims when deciding whether to adopt a tool.
---
# Evaluate AI claims

Compare the claimed outcome to its baseline and measurement method.
Distinguish task completion speed from independently verified correctness.
"""


@pytest.fixture
def site(tmp_path):
    repo = tmp_path / "site with spaces"
    (repo / "_talks").mkdir(parents=True)
    (repo / "_talks" / f"{STEM}.md").write_text("---\nlayout: talk\n---\n# AI claims\n")
    skill = repo / "_skills" / STEM / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(SKILL)
    return repo


def run(site, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--site", str(site), "--stem", STEM, *args],
        capture_output=True,
        text=True,
    )


def build(site, base=""):
    output = site / "_site"
    page = output / "talks" / STEM / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text(
        '<section class="talk-skill" aria-labelledby="talk-skill-heading">'
        f'<a class="talk-skill__raw" href="{base}/skills/{STEM}/SKILL.md" download>'
        "Download SKILL.md</a></section>"
    )
    raw = output / "skills" / STEM / "SKILL.md"
    raw.parent.mkdir(parents=True)
    raw.write_bytes((site / "_skills" / STEM / "SKILL.md").read_bytes())
    return output


def assert_failure(result, diagnostic):
    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False
    assert diagnostic in result.stderr
    assert "Traceback" not in result.stderr


def test_source_preserves_legacy_stem_and_independent_install_name(site):
    result = run(site)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["name"] == "evaluate-ai-claims"
    assert report["checks"] == ["source"]
    assert Path(report["skill_path"]).read_text() == SKILL


@pytest.mark.parametrize(
    ("content", "diagnostic"),
    [
        ("# no metadata", "Add YAML frontmatter"),
        ("---\n- list\n---\nBody", "must be a mapping"),
        ("---\nname: [broken\n---\nBody", "expected"),
        (SKILL.replace("name: evaluate-ai-claims", "name: NoCaps"), "Set name"),
        (SKILL.replace("name: evaluate-ai-claims", "name: double--hyphen"), "Set name"),
        (SKILL.replace("name: evaluate-ai-claims", "name: " + "a" * 65), "Set name"),
        (SKILL.replace("name: evaluate-ai-claims", "name: 123"), "Set name"),
        ("---\nname: valid\ndescription: ''\n---\nBody", "Set a nonblank description"),
        (
            "---\nname: valid\ndescription: true\n---\nBody",
            "Set a nonblank description",
        ),
        ("---\nname: valid\n---\nBody", "Set a nonblank description"),
        (
            "---\nname: valid\ndescription: " + "x" * 1025 + "\n---\nBody",
            "Set a nonblank description",
        ),
        (
            "---\nname: valid\ndescription: Useful\n---\n  \n",
            "substantive talk teaching",
        ),
        (SKILL + "line\n" * 500, "fewer than 500 lines"),
    ],
)
def test_invalid_skill_fails_with_actionable_json(site, content, diagnostic):
    (site / "_skills" / STEM / "SKILL.md").write_text(content)
    assert_failure(run(site), diagnostic)


def test_orphan_is_rejected_even_though_jekyll_skips_it(site):
    (site / "_talks" / f"{STEM}.md").unlink()
    assert_failure(run(site), "matching talk page")


def test_companion_files_cannot_silently_disappear_from_download(site):
    (site / "_skills" / STEM / "references.md").write_text("Essential steps")
    assert_failure(run(site), "Only SKILL.md is served")


def test_non_utf8_and_missing_skill_fail_cleanly(site):
    skill = site / "_skills" / STEM / "SKILL.md"
    skill.write_bytes(b"\xff")
    assert_failure(run(site), "utf-8")
    skill.unlink()
    assert_failure(run(site), "SKILL.md")


def test_path_traversal_stem_is_rejected(site):
    assert_failure(run(site, "--stem", "../elsewhere"), "filename stem")


def test_built_skill_requires_both_attachment_and_identical_raw_bytes(site):
    output = build(site, "/shownotes")
    result = run(site, "--build-dir", str(output), "--baseurl", "/shownotes")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["checks"] == ["source", "build"]


@pytest.mark.parametrize("broken", ["section", "link", "raw", "missing"])
def test_build_catches_silent_publish_failures(site, broken):
    output = build(site)
    page = output / "talks" / STEM / "index.html"
    raw = output / "skills" / STEM / "SKILL.md"
    if broken == "section":
        page.write_text(page.read_text().replace('class="talk-skill"', 'class="other"'))
    elif broken == "link":
        page.write_text(page.read_text().replace(f"/skills/{STEM}/", "/skills/wrong/"))
    elif broken == "raw":
        raw.write_text("<html>Not Found</html>")
    else:
        raw.unlink()
    result = run(site, "--build-dir", str(output))
    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False


@pytest.fixture
def server(site):
    output = build(site, "/shownotes")
    webroot = site / "web"
    webroot.mkdir()
    output.rename(webroot / "shownotes")
    handler = partial(SimpleHTTPRequestHandler, directory=str(webroot))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", webroot
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join()


def test_live_download_and_page_under_baseurl(site, server):
    origin, _ = server
    result = run(site, "--site-url", origin, "--baseurl", "/shownotes")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["checks"] == ["source", "live"]
    assert report["skill_url"] == f"{origin}/shownotes/skills/{STEM}/SKILL.md"


def test_http_200_stale_or_html_download_is_not_success(site, server):
    origin, webroot = server
    (webroot / "shownotes" / "skills" / STEM / "SKILL.md").write_text(
        "<html>Error</html>"
    )
    assert_failure(
        run(site, "--site-url", origin, "--baseurl", "/shownotes"),
        "differs from source",
    )


def test_http_404_is_not_success(site, server):
    origin, webroot = server
    (webroot / "shownotes" / "skills" / STEM / "SKILL.md").unlink()
    assert_failure(run(site, "--site-url", origin, "--baseurl", "/shownotes"), "404")


@pytest.mark.parametrize(
    "origin", ["file:///tmp", "https://example.com/path", "https://u:p@example.com"]
)
def test_invalid_site_origin_is_rejected(site, origin):
    assert_failure(run(site, "--site-url", origin), "must be an HTTP(S) origin")
