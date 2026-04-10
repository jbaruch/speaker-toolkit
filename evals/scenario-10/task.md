# Conference Video Slide Extractor

## Problem/Feature Description

A conference organizer records all their sessions on video but doesn't always collect speaker slide decks. They want a Python tool that can take a directory of JPEG frames (previously extracted from video at regular intervals) and produce a clean PDF containing only the unique slides — deduplicating the hundreds of near-identical frames that result from a static slide being on screen for 30+ seconds.

The tool should handle real-world conference video quirks: some recordings show the speaker in a picture-in-picture overlay or have conference branding bars around the edges. The tool needs to focus its deduplication on the projected slide content, not the speaker's movements or static branding.

The organizer processes ~50 talks per conference and wants to automate the full pipeline: given a video file, extract frames, identify the slide region, remove duplicate frames, and produce a single PDF per talk. Intermediate files should be cleaned up automatically to save disk space.

## Output Specification

Produce the following files:

1. **`extract_slides.py`** — A Python script that:
   - Extracts frames from a video file at a configurable frame rate
   - Auto-detects the region of the frame where slides are projected (vs speaker camera, branding bars)
   - Deduplicates consecutive frames that show the same slide
   - Combines the unique frames into a multi-page PDF
   - Cleans up intermediate frame files after PDF generation
   - Prints progress and statistics (frames extracted, unique slides found, PDF size)

2. **`test_extract.py`** — A test script that:
   - Creates synthetic test images (e.g., 20 frames where groups of consecutive frames are near-identical, simulating a 10-slide talk with 2 frames per slide)
   - Runs the deduplication logic on them
   - Verifies the correct number of unique slides is detected
   - Tests that the cleanup removes intermediate files

3. **`run_log.txt`** — Output from running the test script, showing frame counts, dedup results, and cleanup confirmation

## Setup

Install dependencies before starting:
```bash
pip install imagehash Pillow numpy
```

Ensure `ffmpeg` is available on PATH for the frame extraction step.

**Implementation guidance:**
- Default frame rate should be **0.5 fps** (one frame every 2 seconds) — this captures slide transitions without generating excessive frames.
- Use `imagehash.phash()` with `hash_size=16` for finer-grained perceptual comparison than the default.
- Region detection should work on **downsampled frames** (e.g., resized to 320x180) for efficiency, not full-resolution frames.