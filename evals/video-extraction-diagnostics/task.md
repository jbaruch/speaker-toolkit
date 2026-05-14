# Video Slide Extraction Quality Diagnostics

## Problem/Feature Description

Six conference talk recordings have been processed through the video-slide-extraction pipeline. The extraction results vary widely.

Analyze the extraction results and produce a structured diagnostics report for each case.

## Setup

Download the fixed extraction results:

```bash
curl -sLO https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/video-extraction-diagnostics/extraction_results.json
```

## Task

Analyze `extraction_results.json` (6 recordings, identified `r1` through `r6` in the fixture) and produce `diagnostics_report.json` containing a per-recording diagnostic entry.

For each recording, examine the available extraction metadata (frame counts, unique-frame counts, hash threshold, slide-region detection, transcript source, transcript language, detected vs expected speaker, word counts) and produce:

- a recording-type classification
- a dedup quality assessment, with remediations if dedup appears to have failed
- a transcript quality assessment, including handling of missing transcripts, language-vs-expectation mismatches, and any quality issues you detect in the transcript content
- a speaker identity check, since the playlist's expected speaker is known
- a clean pass-through verdict for recordings that show no anomalies

The expected speaker for this playlist is Baruch Sadogursky. The fixture's recordings include a mix of healthy and unhealthy cases; do not assume which is which from the IDs — derive each verdict from the metadata.

## Output Specification

Produce `diagnostics_report.json` containing a structured per-recording diagnostic record (one entry per recording).

Also produce `recommendations_log.txt` — a human-readable summary of all flagged issues and recommendations, suitable for a production operator to review.
