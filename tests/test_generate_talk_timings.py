"""Tests for generate-talk-timings.py — chapter-driven timing files from outline.yaml."""

import copy
from pathlib import Path

import pytest
import yaml


FIXTURE = Path(__file__).parent / "fixtures" / "outline-example.yaml"


@pytest.fixture(scope="session")
def outline(outline_schema):
    return outline_schema.load_outline(FIXTURE)


@pytest.fixture(scope="session")
def base_data():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def test_format_seconds(generate_talk_timings):
    assert generate_talk_timings.format_seconds(0) == "0:00"
    assert generate_talk_timings.format_seconds(59) == "0:59"
    assert generate_talk_timings.format_seconds(60) == "1:00"
    assert generate_talk_timings.format_seconds(125) == "2:05"


def test_emits_chapter_line_per_chapter(generate_talk_timings, outline):
    lines = generate_talk_timings.generate_timings(outline.chapters)
    # 3 chapters + FINISH
    assert len(lines) == 4
    assert lines[0].endswith("The Setup")
    assert lines[1].endswith("The Turn")
    assert lines[2].endswith("The Close")
    assert lines[3].endswith("FINISH")


def test_cumulative_times(generate_talk_timings, outline):
    """Fixture: ch1=6 min, ch2=12 min, ch3=12 min. Cumulative: 0, 6, 18, 30."""
    lines = generate_talk_timings.generate_timings(outline.chapters)
    assert lines[0].startswith("0:00 ")
    assert lines[1].startswith("6:00 ")
    assert lines[2].startswith("18:00 ")
    assert lines[3].startswith("30:00 ")  # FINISH at 30 min


def test_qa_adds_chapter_before_finish(generate_talk_timings, outline):
    lines = generate_talk_timings.generate_timings(outline.chapters, qa_minutes=5)
    assert "Q&A" in lines[-2]
    assert lines[-2].startswith("30:00 ")
    assert lines[-1].startswith("35:00 FINISH")


def test_zero_qa_omits_qa_line(generate_talk_timings, outline):
    lines = generate_talk_timings.generate_timings(outline.chapters, qa_minutes=0)
    assert not any("Q&A" in line for line in lines)


def test_subminute_chapter(generate_talk_timings, outline_schema, base_data):
    """target_min: 0.5 → 30 seconds; cumulative arithmetic still correct."""
    data = copy.deepcopy(base_data)
    data["chapters"][0]["target_min"] = 0.5
    o = outline_schema.Outline.model_validate(data)
    lines = generate_talk_timings.generate_timings(o.chapters)
    # ch1 starts at 0:00, ch2 starts at 0:30
    assert lines[0].startswith("0:00 ")
    assert lines[1].startswith("0:30 ")


def test_finish_equals_chapter_sum(generate_talk_timings, outline):
    """The FINISH timestamp equals the sum of chapter durations."""
    total_s = sum(int(c.target_min * 60) for c in outline.chapters)
    lines = generate_talk_timings.generate_timings(outline.chapters)
    expected = generate_talk_timings.format_seconds(total_s)
    assert lines[-1].startswith(f"{expected} FINISH")
