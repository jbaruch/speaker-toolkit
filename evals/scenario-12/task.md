# Conference Talk Post-Analysis Debrief System

## Problem/Feature Description

A speaker coaching consultancy analyzes conference talks from transcripts and slide decks. After the automated analysis identifies jokes, audience interactions, and rhetoric patterns, a human coach debriefs the speaker to capture information that transcripts and slides can't reveal — which jokes actually landed, what the room energy was like, whether demo failures were staged, and what spontaneous moments occurred that aren't in the recording.

The consultancy needs a Python tool that takes an analyzed talk (with identified humor beats, audience interactions, and blind spots) and generates a structured debrief questionnaire. The questionnaire should be tailored to the specific talk — not generic questions, but questions grounded in the actual observations from the analysis. After the speaker answers, the tool should produce a structured debrief report that grades each humor beat and captures blind spot observations.

The consultancy processes talks of varying recency — some from last week, some from years ago. The debrief depth should adapt accordingly, since speakers remember recent talks vividly but older talks only in broad strokes.

## Output Specification

Produce the following files:

1. **`debrief_generator.py`** — A Python script that:
   - Reads a JSON analysis file containing identified humor beats, audience interactions, and areas for improvement
   - Generates a structured debrief questionnaire tailored to the specific talk
   - Adapts question depth based on talk recency (detailed for recent, compressed for old)
   - After receiving answers (simulated via a test input file), produces a debrief report with humor grading and blind spot observations

2. **`test_analysis.json`** — A synthetic talk analysis with at least: 5 humor beats (mix of planned jokes, meme slides, and spontaneous moments), 3 audience interaction points, 2 demo sections, and a talk date within the past week

3. **`test_analysis_old.json`** — A synthetic talk analysis for a talk from 3 years ago (same structure but different date)

4. **`test_answers.json`** — Simulated speaker answers for the recent talk debrief

5. **`debrief_report.json`** — Output from running the tool with the recent talk analysis and test answers

6. **`debrief_report_old.json`** — Output from running the tool with the old talk analysis (demonstrating compressed questioning)

## Setup

No special dependencies required beyond Python standard library.