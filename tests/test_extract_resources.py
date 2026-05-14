"""Tests for extract-resources.py — resource extraction from outline.yaml."""

import copy
from pathlib import Path

import pytest
import yaml


FIXTURE = Path(__file__).parent / "fixtures" / "outline-example.yaml"


@pytest.fixture(scope="session")
def base_data():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _outline_with(outline_schema, base, mutator):
    data = copy.deepcopy(base)
    mutator(data)
    return outline_schema.Outline.model_validate(data)


def test_extracts_url_from_text_overlay(extract_resources, outline_schema, base_data):
    o = _outline_with(outline_schema, base_data, lambda d:
        d["slides"][0].__setitem__("text_overlay", "Visit https://example.com/intro"))
    parsed = extract_resources.parse_outline_yaml(o)
    urls = extract_resources.extract_urls(parsed)
    assert any(r["value"] == "https://example.com/intro" for r in urls)


def test_extracts_url_from_script_line(extract_resources, outline_schema, base_data):
    o = _outline_with(outline_schema, base_data, lambda d:
        d["slides"][0]["script"].append({"line": "See https://example.com/docs"}))
    parsed = extract_resources.parse_outline_yaml(o)
    urls = extract_resources.extract_urls(parsed)
    assert any(r["value"] == "https://example.com/docs" for r in urls)


def test_excludes_url_from_image_prompt(extract_resources, outline_schema, base_data):
    """Image prompts are excluded — generation prompts often have incidental URLs."""
    o = _outline_with(outline_schema, base_data, lambda d:
        d["slides"][0].__setitem__("image_prompt",
                                    "[STYLE ANCHOR]. See https://nope.example.com"))
    parsed = extract_resources.parse_outline_yaml(o)
    urls = extract_resources.extract_urls(parsed)
    assert not any("nope.example.com" in r["value"] for r in urls)


def test_url_dedup(extract_resources, outline_schema, base_data):
    def mutate(d):
        d["slides"][0]["text_overlay"] = "https://example.com/intro"
        d["slides"][1]["text_overlay"] = "Also https://example.com/intro"
    o = _outline_with(outline_schema, base_data, mutate)
    parsed = extract_resources.parse_outline_yaml(o)
    urls = extract_resources.extract_urls(parsed)
    values = [r["value"] for r in urls]
    assert values.count("https://example.com/intro") == 1


def test_extracts_github_repo(extract_resources, outline_schema, base_data):
    o = _outline_with(outline_schema, base_data, lambda d:
        d["slides"][0]["script"].append(
            {"line": "Code: github.com/hashicorp/terraform"}))
    parsed = extract_resources.parse_outline_yaml(o)
    repos = extract_resources.extract_repos(parsed)
    assert any("hashicorp/terraform" in r["value"] for r in repos)


def test_extracts_book(extract_resources, outline_schema, base_data):
    o = _outline_with(outline_schema, base_data, lambda d:
        d["slides"][0]["script"].append(
            {"line": '"Design Patterns" by Erich Gamma is the classic.'}))
    parsed = extract_resources.parse_outline_yaml(o)
    books = extract_resources.extract_books(parsed)
    assert any(r["value"] == "Design Patterns" for r in books)


def test_extracts_rfc(extract_resources, outline_schema, base_data):
    o = _outline_with(outline_schema, base_data, lambda d:
        d["slides"][0]["script"].append({"line": "Reference: RFC 7231 for HTTP semantics."}))
    parsed = extract_resources.parse_outline_yaml(o)
    rfcs = extract_resources.extract_rfcs(parsed)
    assert any(r["value"] == "RFC 7231" for r in rfcs)


def test_extracts_tool_from_speaker_notes(extract_resources, outline_schema, base_data):
    o = _outline_with(outline_schema, base_data, lambda d:
        d["slides"][0]["script"].append(
            {"line": "We use `Kubernetes` and `Prometheus` for ops."}))
    parsed = extract_resources.parse_outline_yaml(o)
    tools = extract_resources.extract_tools(parsed)
    values = [r["value"] for r in tools]
    assert "Kubernetes" in values
    assert "Prometheus" in values


def test_slide_context_carries_chapter_title(extract_resources, outline_schema, base_data):
    o = _outline_with(outline_schema, base_data, lambda d:
        d["slides"][0].__setitem__("text_overlay", "https://example.com/x"))
    parsed = extract_resources.parse_outline_yaml(o)
    urls = extract_resources.extract_urls(parsed)
    first = next(r for r in urls if r["value"] == "https://example.com/x")
    # Slide 1 is in chapter ch1 — title "The Setup"
    assert 1 in first["slide_nums"]
    assert "The Setup" in first["context"]


def test_url_in_thesis_has_no_slide_num(extract_resources, outline_schema, base_data):
    o = _outline_with(outline_schema, base_data, lambda d:
        d["talk"].__setitem__("thesis", "See https://example.com/thesis-link"))
    parsed = extract_resources.parse_outline_yaml(o)
    urls = extract_resources.extract_urls(parsed)
    thesis_url = next(r for r in urls if r["value"] == "https://example.com/thesis-link")
    assert thesis_url["slide_nums"] == []
    assert thesis_url["context"] == "preamble"
