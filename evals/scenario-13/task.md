# Conference Recording Slide Extraction Quality Analyzer

## Problem/Feature Description

A media production company processes hundreds of conference talk recordings to extract slide content for archival and analysis. They've discovered that their slide extraction pipeline (frame extraction + perceptual hash deduplication) produces wildly different quality results depending on the recording style. Fullscreen slide captures work perfectly, but wide-angle room recordings where a speaker walks around in front of projected slides produce thousands of "unique" frames that are actually the same slide with different speaker positions.

The company needs a diagnostic tool that analyzes the output of a slide extraction run and classifies the recording type, flags quality issues, recommends parameter adjustments, and identifies when a non-target speaker might have been recorded instead of the expected presenter.

The tool should also handle transcript quality assessment — some recordings have no captions, some have captions in unexpected languages, and some produce Whisper transcriptions with hallucination artifacts. Track the transcript source type (e.g., `youtube_auto`, `whisper`, `manual`) as a field in the output, since source type significantly affects quality interpretation.

The JSON output should have top-level sections: `recording_type`, `dedup_quality`, `transcript_quality`, `speaker_match`, and `recommendations`.

## Output Specification

Produce the following files:

1. **`extraction_diagnostics.py`** — A Python script that:
   - Takes extraction results (frame count, unique slide count, hash threshold used, slide region detection info, PDF page count) and talk metadata (expected speaker name, expected language)
   - Classifies the recording type (fullscreen slides, picture-in-picture, wide-angle room, split screen, audio-only)
   - Flags quality issues and recommends parameter adjustments
   - Assesses transcript quality (usable, partial, hallucinated, wrong language, missing)
   - Checks whether the detected speaker matches the expected speaker
   - Outputs a structured diagnostics report

2. **`test_cases.json`** — At least 6 test cases covering:
   - A clean fullscreen recording (50 frames → 45 unique slides, good ratio)
   - A wide-angle room recording (1200 frames → 900 "unique" — dedup failed)
   - A recording with no transcript available
   - A recording with a transcript in an unexpected language (e.g., expected English, got Russian)
   - A recording where the speaker doesn't match (wrong person in the video)
   - A recording with Whisper transcription showing hallucination patterns

3. **`diagnostics_output.json`** — Results from running all test cases

4. **`recommendations_log.txt`** — Human-readable log of recommendations for each case

## Setup

No special dependencies required beyond Python standard library.