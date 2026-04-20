"""Tests for generate-talk-timings.py — timemytalk.app timer generation."""


OUTLINE_WITH_PACING = """\
# Presentation Outline

## Opening [3 min, slides 1-3]

### Slide 1: Title
- Speaker: Welcome everyone!

### Slide 2: Agenda
- Speaker: Here's what we'll cover.

## Act 1: The Challenge [5 min, slides 4-8]

### Slide 4: Problem Statement
- Speaker: Let me set the scene.

## Act 2: The Journey [12 min, slides 9-20]

### Slide 9: Step One
- Speaker: First we need to understand...

## Coda [5 min, slides 21-25]

### Slide 21: Summary
- Speaker: Let's wrap up.

## Pacing Summary

| Section | Duration |
|---------|----------|
| Opening | 3 min |
| Act 1: The Challenge | 5 min |
| Act 2: The Journey | 12 min |
| Coda | 5 min |
| **Total** | **25 min** |
"""


OUTLINE_SUBMUNITE = """\
## Pacing Summary

| Section | Duration |
|---------|----------|
| Intro | 1:30 min |
| Main | 3 min |
| Outro | :30 min |
"""


OUTLINE_EMPTY_PACING = """\
# Presentation Outline

## Pacing Summary

| Section | Duration |
|---------|----------|
| **Total** | **0 min** |
"""

OUTLINE_NO_PACING = """\
# Presentation Outline

## Opening [3 min, slides 1-3]

Just an outline with no pacing table at all.
"""


def test_parse_pacing_table(generate_talk_timings):
    """Pacing summary table is parsed into section/duration pairs."""
    sections = generate_talk_timings.parse_pacing_table(OUTLINE_WITH_PACING)
    names = [name for name, _ in sections]
    assert "Opening" in names
    assert "Act 1: The Challenge" in names
    assert "Act 2: The Journey" in names
    assert "Coda" in names
    assert len(sections) == 4


def test_pacing_durations_correct(generate_talk_timings):
    """Durations are parsed correctly as seconds."""
    sections = generate_talk_timings.parse_pacing_table(OUTLINE_WITH_PACING)
    dur_map = {name: dur for name, dur in sections}
    assert dur_map["Opening"] == 180       # 3 min
    assert dur_map["Act 1: The Challenge"] == 300   # 5 min
    assert dur_map["Act 2: The Journey"] == 720     # 12 min
    assert dur_map["Coda"] == 300           # 5 min


def test_cumulative_times(generate_talk_timings):
    """Timing lines use cumulative start times."""
    sections = generate_talk_timings.parse_pacing_table(OUTLINE_WITH_PACING)
    lines = generate_talk_timings.generate_timings(sections)
    assert lines[0] == "0:00 Opening"
    assert lines[1] == "3:00 Act 1: The Challenge"
    assert lines[2] == "8:00 Act 2: The Journey"
    assert lines[3] == "20:00 Coda"
    assert lines[4] == "25:00 FINISH"


def test_finish_equals_total(generate_talk_timings):
    """FINISH time equals the sum of all section durations."""
    sections = generate_talk_timings.parse_pacing_table(OUTLINE_WITH_PACING)
    lines = generate_talk_timings.generate_timings(sections)
    total_seconds = sum(dur for _, dur in sections)
    expected_finish = generate_talk_timings.format_seconds(total_seconds)
    assert lines[-1] == f"{expected_finish} FINISH"


def test_qa_flag_adds_chapter(generate_talk_timings):
    """--qa flag adds a Q&A chapter before FINISH."""
    sections = generate_talk_timings.parse_pacing_table(OUTLINE_WITH_PACING)
    lines = generate_talk_timings.generate_timings(sections, qa_minutes=5)
    # Q&A should be second-to-last
    assert "Q&A" in lines[-2]
    assert lines[-2] == "25:00 Q&A"
    # FINISH should account for Q&A
    assert lines[-1] == "30:00 FINISH"


def test_empty_pacing_table(generate_talk_timings):
    """Empty pacing table (only total row) produces empty sections list."""
    sections = generate_talk_timings.parse_pacing_table(OUTLINE_EMPTY_PACING)
    assert sections == []


def test_no_pacing_table(generate_talk_timings):
    """Outline without pacing summary returns empty sections list."""
    sections = generate_talk_timings.parse_pacing_table(OUTLINE_NO_PACING)
    assert sections == []


def test_subminute_resolution(generate_talk_timings):
    """Sub-minute durations like 1:30 and :30 are parsed correctly."""
    sections = generate_talk_timings.parse_pacing_table(OUTLINE_SUBMUNITE)
    dur_map = {name: dur for name, dur in sections}
    assert dur_map["Intro"] == 90    # 1:30
    assert dur_map["Main"] == 180    # 3 min
    assert dur_map["Outro"] == 30    # :30


def test_subminute_cumulative_times(generate_talk_timings):
    """Cumulative times handle sub-minute sections correctly."""
    sections = generate_talk_timings.parse_pacing_table(OUTLINE_SUBMUNITE)
    lines = generate_talk_timings.generate_timings(sections)
    assert lines[0] == "0:00 Intro"
    assert lines[1] == "1:30 Main"
    assert lines[2] == "4:30 Outro"
    assert lines[3] == "5:00 FINISH"


def test_format_seconds(generate_talk_timings):
    """format_seconds produces MM:SS strings."""
    assert generate_talk_timings.format_seconds(0) == "0:00"
    assert generate_talk_timings.format_seconds(90) == "1:30"
    assert generate_talk_timings.format_seconds(300) == "5:00"
    assert generate_talk_timings.format_seconds(1500) == "25:00"
    assert generate_talk_timings.format_seconds(3600) == "60:00"


def test_parse_section_headers(generate_talk_timings):
    """Section headers with [N min, slides X-Y] are parsed."""
    headers = generate_talk_timings.parse_section_headers(OUTLINE_WITH_PACING)
    names = [name for name, _ in headers]
    assert "Opening" in names
    assert "Act 1: The Challenge" in names
    assert "Act 2: The Journey" in names
    assert "Coda" in names


def test_generate_timings_returns_list(generate_talk_timings):
    """generate_timings returns a list of strings."""
    sections = [("Intro", 120), ("Main", 300)]
    lines = generate_talk_timings.generate_timings(sections)
    assert isinstance(lines, list)
    assert all(isinstance(l, str) for l in lines)
    assert len(lines) == 3  # 2 sections + FINISH
