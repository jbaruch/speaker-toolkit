# Slide Deck Visual Audit Tool

## Problem/Feature Description

A design consultancy manages dozens of PowerPoint presentations for their clients. They need a Python tool that can scan a directory of `.pptx` files and extract exact visual design data — hex colors, font names, shape types, layout information — to build a style audit report. The tool should handle messy real-world directories where some files are static PDF-export copies, Google Drive conflict duplicates, or conference-provided templates that shouldn't be analyzed.

The consultancy wants to understand: what background colors are used and how often, which fonts appear across decks, what special shapes (callout bubbles, starbursts) are present, and where footers live on each slide. The output must be structured JSON so it can feed into their analytics pipeline.

## Output Specification

Produce the following files:

1. **`extract_pptx.py`** — A Python script that:
   - Takes a directory path as input and recursively finds `.pptx` files
   - Filters out files that shouldn't be processed (static exports, duplicate copies, template files)
   - Extracts per-slide visual data and global design statistics from each valid file
   - Outputs a JSON report for each processed file

2. **`test_decks/`** — A directory with at least 5 synthetic `.pptx` test files created using python-pptx, including:
   - Two normal presentation files with varied slides (different backgrounds, fonts, shapes)
   - One file named with "static" in the name
   - One file named with a `(1)` conflict copy pattern
   - One file with "template" in the name

3. **`extraction_results.json`** — The actual output from running your extraction tool on the test directory

4. **`run_log.txt`** — A log showing which files were processed and which were skipped, with reasons

## Setup

Install python-pptx before starting:
```bash
pip install python-pptx
```
