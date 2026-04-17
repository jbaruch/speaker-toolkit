# Video Slide Extraction Quality Diagnostics

## Problem/Feature Description

Six conference talk recordings have been processed through the video-slide-extraction pipeline. The extraction results vary widely — some are clean, others show signs of wide-angle recording dedup failure, missing transcripts, wrong languages, wrong speakers, or Whisper hallucination.

Analyze the extraction results and produce a structured diagnostics report for each case.

## Setup

Download the fixed extraction results:

```bash
curl -sLO https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-13/extraction_results.json
```

## Task

Analyze `extraction_results.json` (6 recordings) and produce `diagnostics_report.json` containing a per-recording diagnostic entry. Each entry must include:

1. **Recording type classification** — classify each recording into one of at least 3 categories (e.g., fullscreen slides, picture-in-picture, wide-angle room) based on extraction metrics (frame-to-unique ratio, slide region detection)

2. **Dedup quality assessment** — for `case_wide_angle` (1200 frames → 900 "unique"), detect that the 1.33:1 ratio indicates dedup failure from speaker movement, and recommend:
   - Increasing hash threshold to 14–18 (above the default 8)
   - Using manual slide region cropping to isolate the projected screen

3. **Transcript quality assessment** for each case:
   - `case_no_transcript`: flag as missing, recommend Whisper fallback
   - `case_wrong_language`: detect Russian transcript when English was expected — but do NOT flag as an error if the talk was actually delivered in Russian (the speaker is bilingual)
   - `case_whisper_hallucination`: detect the 0.45 repetition ratio and the repeated "Thank you for watching" loop as hallucination artifacts
   - Track transcript source (youtube_auto_captions vs whisper_transcription) as a field

4. **Speaker identity verification** — for `case_wrong_speaker`, flag that detected speaker "James Gosling" doesn't match expected "Baruch Sadogursky" (possible wrong recording from a playlist)

5. **Clean pass-through** — for `case_clean` (50 frames → 45 unique, valid transcript, correct speaker), produce NO warnings. Classify as healthy.

## Output Specification

Produce `diagnostics_report.json` with this structure per case:
- `recording_type`: classification string
- `dedup_quality`: assessment with optional `recommended_threshold`
- `transcript_quality`: assessment with `source`, `status`, and optional warnings
- `speaker_match`: boolean + details
- `recommendations`: list of actionable strings (empty for clean recordings)

Also produce `recommendations_log.txt` — a human-readable summary of all flagged issues and recommendations, suitable for a production operator to review.
