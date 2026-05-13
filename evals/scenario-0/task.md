# Slide Deck Visual Audit Report

## Problem/Feature Description

A design consultancy manages dozens of PowerPoint presentations for their clients, organized in subdirectories by client name. The directories contain a mix of files — some are real presentations, others are not. They need a visual design audit across the real presentations.

The presentations are in a directory tree with client subdirectories. Each real presentation has varied content: different background colors, multiple fonts, auto-shapes like callouts and starbursts, footer text at the bottom of slides, and speaker notes.

Produce a structured JSON audit report covering each presentation file the agent decides is worth auditing, with per-slide visual data and global design statistics.

## Output Specification

Produce the following files:

1. **`extraction_results.json`** — A structured JSON audit of the test directory containing:
   - Per-file results for each presentation included in the audit
   - Per-slide data: background colors, fonts used, shapes present, layout info, speaker notes presence, footer text
   - Global design statistics: font frequency, background color frequency, color sequence across all slides
   - Shape type detail — not just "shape" but what kind (callouts, starbursts, etc.)

2. **`run_log.txt`** — A log showing which files were processed and which were not, with reasons

## Setup

Install python-pptx before starting:
```bash
pip install python-pptx
```

Download the test deck directory tree from the project repository, preserving the original filenames:
```bash
mkdir -p test_decks/acme-corp test_decks/beta-inc
curl -L -o "test_decks/acme-corp/Q1 Review.pptx" "https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-0/acme-corp/Q1%20Review.pptx"
curl -L -o "test_decks/acme-corp/Q1 Review static.pptx" "https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-0/acme-corp/Q1%20Review%20static.pptx"
curl -L -o "test_decks/acme-corp/Q1 Review (1).pptx" "https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-0/acme-corp/Q1%20Review%20(1).pptx"
curl -L -o "test_decks/beta-inc/Product Launch.pptx" "https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-0/beta-inc/Product%20Launch.pptx"
curl -L -o "test_decks/beta-inc/Presentation Template 2024.pptx" "https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-0/beta-inc/Presentation%20Template%202024.pptx"
```

The test directory contains:
- `test_decks/acme-corp/Q1 Review.pptx` — 4 slides: purple/red/yellow/green backgrounds, Impact + Arial + Bangers fonts, cloud callout and explosion shapes, footer text, speaker notes
- `test_decks/acme-corp/Q1 Review static.pptx`
- `test_decks/acme-corp/Q1 Review (1).pptx`
- `test_decks/beta-inc/Product Launch.pptx` — 3 slides: blue/orange/salmon backgrounds, Georgia + Verdana fonts, footer text on every slide, speaker notes on 2 slides
- `test_decks/beta-inc/Presentation Template 2024.pptx`
