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

1. **Recording type classification** — classify each recording by recording type, using the extraction metrics provided

2. **Dedup quality assessment** — for `case_wide_angle` (1200 frames → 900 unique), assess what the ratio implies and recommend appropriate remediations.

3. **Transcript quality assessment** for each case:
   - `case_no_transcript`: flag as missing, recommend Whisper fallback
   - `case_wrong_language`: detect Russian transcript when English was expected. The speaker is bilingual and may have delivered the talk in Russian.
   - `case_whisper_hallucination`: review `case_whisper_hallucination` for signs the transcript is unreliable.

4. **Speaker identity verification** — review `case_wrong_speaker`; the extraction recorded a different speaker than expected. The expected speaker for the playlist is Baruch Sadogursky.

5. **Clean pass-through** — review `case_clean` (50 frames → 45 unique, valid transcript, correct speaker).

## Output Specification

Produce `diagnostics_report.json` containing a structured per-recording diagnostic record (one entry per case).

Also produce `recommendations_log.txt` — a human-readable summary of all flagged issues and recommendations, suitable for a production operator to review.
