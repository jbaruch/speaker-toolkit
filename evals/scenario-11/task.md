# Presentation Analytics: Multi-Source Slide Ingestion

## Problem/Feature Description

A developer advocacy team maintains a database of conference talks and wants to analyze the visual design of each talk's slides. The challenge: slide sources come in different formats depending on what's available. Some talks have the original PowerPoint files, some only have PDFs exported to Google Drive, some only have a YouTube recording, and a few have nothing but a transcript.

The team needs a Python processing engine that, given a database of talks with varying source availability, determines the best slide acquisition strategy for each talk and processes them accordingly. The engine should prioritize higher-quality sources (original files > exported PDFs > video-extracted frames) and handle failures gracefully — if the primary source fails, it should fall back to the next best option.

The database is a JSON file where each talk entry has optional fields for different sources. The engine should set a `slide_source` field on each entry indicating which acquisition path was chosen, update the `status` field after processing, and produce a processing log.

**Key rules:**
- A talk **requires a video_url** to be fully processable (video is the transcript source). A talk with slides but no video cannot be fully processed — mark it as skipped.
- Status values: `processed` (full success), `processed_partial` (transcript-only, no slides), `skipped_no_sources` (no video), `skipped_download_failed` (all sources failed).
- For video-extracted slides, name the output PDF using the YouTube video ID (e.g., `slides/{youtube_id}.pdf`).
- After extracting slides from video, clean up the downloaded video file to save disk space.

## Output Specification

Produce the following files:

1. **`process_talks.py`** — A Python script that:
   - Reads a talks database JSON file
   - For each talk, determines the slide acquisition method based on available sources
   - Sets the `slide_source` field to indicate which method was selected
   - Sets appropriate `status` after processing (or simulated processing)
   - Handles the case where a talk has video but no slides — this is still processable
   - Handles error scenarios where downloads fail
   - Writes the updated database back to JSON

2. **`test_talks_db.json`** — A test database with at least 8 talk entries covering these cases:
   - A talk with both PPTX file and PDF available
   - A talk with only a PPTX file
   - A talk with only a Google Drive PDF URL
   - A talk with only a YouTube video URL (no slides at all)
   - A talk with a YouTube video AND a PDF
   - A talk with no video URL at all (but has slides)
   - A talk where both video and slides are missing
   - A talk with video URL but transcript download fails

3. **`processed_talks_db.json`** — The output after running process_talks.py on the test database

4. **`processing_log.txt`** — A log showing which source was selected for each talk and why

## Setup

No special dependencies required beyond Python standard library (the actual download/extraction steps should be simulated for testing).