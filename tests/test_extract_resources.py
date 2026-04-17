"""Tests for extract-resources.py — resource extraction from outlines."""


OUTLINE = """\
## Section 1 [5 min, slides 1-5]

### Slide 1: Intro
- Speaker: Check out https://example.com/intro and RFC 7231 for context.
- Visual: The `Kubernetes` dashboard showing `Prometheus` metrics

### Slide 2: Deep Dive
- Speaker: See the repo at github.com/hashicorp/terraform for details.
- Body: "Design Patterns" by Erich Gamma is the classic reference.

```python
# This URL should be ignored: https://example.com/in-code-block
print("hello")
```

### Slide 3: Links
- Speaker: Visit https://example.com/intro again and https://new-site.org/docs
- Image prompt: `A beautiful landscape with mountains` — should be excluded
"""


def test_url_extraction(extract_resources):
    parsed = extract_resources.parse_outline_text(OUTLINE)
    urls = extract_resources.extract_urls(parsed)
    values = [r["value"] for r in urls]
    assert "https://example.com/intro" in values
    assert "https://new-site.org/docs" in values


def test_url_dedup(extract_resources):
    parsed = extract_resources.parse_outline_text(OUTLINE)
    urls = extract_resources.extract_urls(parsed)
    values = [r["value"] for r in urls]
    # https://example.com/intro appears twice but should be deduplicated
    assert values.count("https://example.com/intro") == 1


def test_url_in_code_block_excluded(extract_resources):
    parsed = extract_resources.parse_outline_text(OUTLINE)
    urls = extract_resources.extract_urls(parsed)
    values = [r["value"] for r in urls]
    assert "https://example.com/in-code-block" not in values


def test_repo_extraction(extract_resources):
    parsed = extract_resources.parse_outline_text(OUTLINE)
    repos = extract_resources.extract_repos(parsed)
    values = [r["value"] for r in repos]
    assert any("hashicorp/terraform" in v for v in values)


def test_book_extraction(extract_resources):
    parsed = extract_resources.parse_outline_text(OUTLINE)
    books = extract_resources.extract_books(parsed)
    values = [r["value"] for r in books]
    assert "Design Patterns" in values


def test_rfc_extraction(extract_resources):
    parsed = extract_resources.parse_outline_text(OUTLINE)
    rfcs = extract_resources.extract_rfcs(parsed)
    values = [r["value"] for r in rfcs]
    assert "RFC 7231" in values


def test_tool_extraction_from_speaker_notes(extract_resources):
    parsed = extract_resources.parse_outline_text(OUTLINE)
    tools = extract_resources.extract_tools(parsed)
    values = [r["value"] for r in tools]
    assert "Kubernetes" in values
    assert "Prometheus" in values


def test_slug_from_spec(extract_resources, tmp_path):
    spec = tmp_path / "presentation-spec.md"
    spec.write_text("# Spec\nShownotes slug: my-great-talk\n")
    slug = extract_resources.read_talk_slug(str(spec))
    assert slug == "my-great-talk"


def test_slug_missing_file(extract_resources):
    assert extract_resources.read_talk_slug("/nonexistent/path") is None


def test_slide_context(extract_resources):
    parsed = extract_resources.parse_outline_text(OUTLINE)
    urls = extract_resources.extract_urls(parsed)
    first_url = next(r for r in urls if r["value"] == "https://example.com/intro")
    assert 1 in first_url["slide_nums"]
