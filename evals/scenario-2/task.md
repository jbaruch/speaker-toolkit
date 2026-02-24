# Talk Processing Batch Report

## Problem/Feature Description

A speaker's rhetoric knowledge vault has been running automated analysis on their talks. The system downloads YouTube transcripts and slide PDFs for each talk, analyzes them, and updates a tracking database. But downloads are unreliable — sometimes the transcript download fails, sometimes the slides download fails, sometimes both fail. The system needs to correctly categorize each talk's processing outcome and update the vault's running summary document.

You have a tracking database with 8 talks that just went through a processing run. Each talk has a recorded download result from the latest run. Based on the outcomes, update the tracking database with the correct status for each talk, and produce an updated rhetoric summary document that incorporates the new observations from successfully processed talks.

The key constraint: the rhetoric summary is a living document that has been built up over months. New observations should be integrated into the existing content — patterns should be refined and new ones added, but nothing should be removed from the summary even if a new talk contradicts an earlier observation. Contradictions should be noted as evolving patterns, not overwrites.

## Output Specification

Produce the following files:

1. **`tracking-database-updated.json`** — The updated tracking database with correct status values for all 8 talks
2. **`rhetoric-style-summary-updated.md`** — The updated rhetoric summary incorporating new observations
3. **`processing-report.txt`** — A report showing what happened with each talk and the vault state

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/tracking-database.json ===============
{
  "config": {
    "vault_root": "/vault",
    "talks_source_dir": "/talks",
    "pptx_source_dir": "/presentations",
    "python_path": "python3",
    "template_skip_patterns": ["template"]
  },
  "talks": [
    {
      "filename": "2024-01-15-microservices-myths.md",
      "title": "Microservices Myths",
      "conference": "QCon London",
      "date": "2024-01-15",
      "video_url": "https://www.youtube.com/watch?v=abc123",
      "slides_url": "https://drive.google.com/file/d/1ABC/view",
      "pptx_path": "QCon/2024/Microservices Myths.pptx",
      "youtube_id": "abc123",
      "google_drive_id": "1ABC",
      "status": "pending"
    },
    {
      "filename": "2024-03-20-devops-culture.md",
      "title": "DevOps Culture Reset",
      "conference": "DevOps Days",
      "date": "2024-03-20",
      "video_url": "https://www.youtube.com/watch?v=def456",
      "slides_url": "https://drive.google.com/file/d/2DEF/view",
      "youtube_id": "def456",
      "google_drive_id": "2DEF",
      "status": "pending"
    },
    {
      "filename": "2024-05-10-ci-pipeline.md",
      "title": "CI Pipeline Masterclass",
      "conference": "FOSDEM",
      "date": "2024-05-10",
      "video_url": "https://www.youtube.com/watch?v=ghi789",
      "youtube_id": "ghi789",
      "status": "pending"
    },
    {
      "filename": "2024-06-15-platform-eng.md",
      "title": "Platform Engineering Done Right",
      "conference": "PlatformCon",
      "date": "2024-06-15",
      "video_url": "https://www.youtube.com/watch?v=jkl012",
      "pptx_path": "PlatformCon/2024/Platform Engineering Done Right.pptx",
      "youtube_id": "jkl012",
      "status": "pending"
    },
    {
      "filename": "2024-07-22-security-shift.md",
      "title": "Security Shift Left",
      "conference": "BSides",
      "date": "2024-07-22",
      "video_url": "https://www.youtube.com/watch?v=mno345",
      "slides_url": "https://drive.google.com/file/d/3MNO/view",
      "youtube_id": "mno345",
      "google_drive_id": "3MNO",
      "status": "pending"
    },
    {
      "filename": "2024-08-30-testing-prod.md",
      "title": "Testing in Production",
      "conference": "SREcon",
      "date": "2024-08-30",
      "slides_url": "https://drive.google.com/file/d/4PQR/view",
      "google_drive_id": "4PQR",
      "status": "pending"
    },
    {
      "filename": "2024-09-15-container-security.md",
      "title": "Container Security Deep Dive",
      "conference": "KubeCon",
      "date": "2024-09-15",
      "status": "pending"
    },
    {
      "filename": "2024-10-05-gitops-journey.md",
      "title": "GitOps Journey",
      "conference": "GitOpsCon",
      "date": "2024-10-05",
      "video_url": "https://www.youtube.com/watch?v=stu678",
      "slides_url": "https://drive.google.com/file/d/5STU/view",
      "pptx_path": "GitOpsCon/2024/GitOps Journey.pptx",
      "youtube_id": "stu678",
      "google_drive_id": "5STU",
      "status": "pending"
    }
  ],
  "pptx_catalog": [],
  "confirmed_intents": []
}
=============== END OF FILE ===============

=============== FILE: inputs/download-results.json ===============
{
  "results": [
    {"filename": "2024-01-15-microservices-myths.md", "transcript_download": "success", "slides_download": "success", "notes": "Both sources acquired successfully"},
    {"filename": "2024-03-20-devops-culture.md", "transcript_download": "success", "slides_download": "failed", "notes": "Google Drive returned 403 forbidden"},
    {"filename": "2024-05-10-ci-pipeline.md", "transcript_download": "failed", "slides_download": "not_applicable", "notes": "No auto-captions available on YouTube; no slides source configured"},
    {"filename": "2024-06-15-platform-eng.md", "transcript_download": "success", "slides_download": "success", "notes": "PPTX extraction completed"},
    {"filename": "2024-07-22-security-shift.md", "transcript_download": "failed", "slides_download": "success", "notes": "yt-dlp timed out, but PDF downloaded successfully"},
    {"filename": "2024-08-30-testing-prod.md", "transcript_download": "not_applicable", "slides_download": "success", "notes": "No video_url configured"},
    {"filename": "2024-09-15-container-security.md", "transcript_download": "not_applicable", "slides_download": "not_applicable", "notes": "No video_url, no slides_url, no pptx_path"},
    {"filename": "2024-10-05-gitops-journey.md", "transcript_download": "failed", "slides_download": "failed", "notes": "Network timeout on both downloads"}
  ]
}
=============== END OF FILE ===============

=============== FILE: inputs/rhetoric-style-summary.md ===============
# Rhetoric & Style Summary

Last updated: 2024-09-01

## Section 1: Presentation Modes
The speaker operates in two modes: "Myth Buster" (problem-diagnosis-solution, heavy memes) and "Deep Dive" (demo-driven, minimal slides).

## Section 2: Opening Patterns
Typically opens with a bold claim or audience poll. Bio at slide 3.

## Section 4: Humor & Wit
Self-deprecating humor, meme cascades, callback humor.

## Section 7: Verbal Signatures
"is not a thing", "right?", "raise your hand if"

## Section 15: Areas for Improvement
- Tends to rush the closing section
- Opening framing sometimes too long
=============== END OF FILE ===============
