# Presentation Analytics: Multi-Source Slide Ingestion

## Problem/Feature Description

A developer advocacy team maintains a database of conference talks and wants to analyze the visual design of each talk's slides. The challenge: slide sources come in different formats depending on what's available. Some talks have the original PowerPoint files, some only have PDFs exported to Google Drive, some only have a YouTube recording from which frames could be extracted, and a few have nothing but a transcript.

The team needs to process this database: for each talk, determine the best slide acquisition strategy, attempt processing, handle failures with fallbacks, and update each entry with the outcome. The key insight is that not all source types are equal — there's a clear quality hierarchy — and a talk's processability depends on whether it has a video recording, not just whether it has slides.

You are given the database below. Process it: determine each talk's slide source, simulate the acquisition (some will fail as noted), apply fallback logic, and produce the updated database with correct status and slide source values. Also produce a processing log explaining each decision.

## Output Specification

Produce the following files:

1. **`processed_talks_db.json`** — The updated database with correct `slide_source` and `status` values for all 8 talks
2. **`processing_log.txt`** — A log showing which source was selected for each talk, what happened, and why the final status was set

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/test_talks_db.json ===============
{
  "talks": [
    {
      "filename": "2024-01-15-microservices-myths.md",
      "title": "Microservices Myths",
      "video_url": "https://www.youtube.com/watch?v=abc123",
      "youtube_id": "abc123",
      "slides_url": "https://drive.google.com/file/d/1ABC/view",
      "pptx_path": "QCon/2024/Microservices Myths.pptx",
      "status": "pending",
      "notes": "Both PPTX and PDF available, transcript downloads OK, slides download OK"
    },
    {
      "filename": "2024-03-20-devops-culture.md",
      "title": "DevOps Culture Reset",
      "video_url": "https://www.youtube.com/watch?v=def456",
      "youtube_id": "def456",
      "slides_url": "https://drive.google.com/file/d/2DEF/view",
      "status": "pending",
      "notes": "PDF only. Transcript OK, slides download FAILS, video extraction also FAILS (low quality)"
    },
    {
      "filename": "2024-05-10-ci-pipeline.md",
      "title": "CI Pipeline Masterclass",
      "video_url": "https://www.youtube.com/watch?v=ghi789",
      "youtube_id": "ghi789",
      "status": "pending",
      "notes": "Video only — no slides source at all. Transcript download FAILS. Video extraction should produce slides/{youtube_id}.pdf"
    },
    {
      "filename": "2024-06-15-platform-eng.md",
      "title": "Platform Engineering Done Right",
      "video_url": "https://www.youtube.com/watch?v=jkl012",
      "youtube_id": "jkl012",
      "pptx_path": "PlatformCon/2024/Platform Engineering.pptx",
      "status": "pending",
      "notes": "PPTX only (no PDF). Transcript OK, PPTX extraction OK"
    },
    {
      "filename": "2024-07-22-security-shift.md",
      "title": "Security Shift Left",
      "video_url": "https://www.youtube.com/watch?v=mno345",
      "youtube_id": "mno345",
      "slides_url": "https://drive.google.com/file/d/3MNO/view",
      "status": "pending",
      "notes": "PDF only. Transcript FAILS, slides download OK"
    },
    {
      "filename": "2024-08-30-testing-prod.md",
      "title": "Testing in Production",
      "slides_url": "https://drive.google.com/file/d/4PQR/view",
      "status": "pending",
      "notes": "Has slides but NO video_url — is this talk processable?"
    },
    {
      "filename": "2024-09-15-container-security.md",
      "title": "Container Security Deep Dive",
      "status": "pending",
      "notes": "No video_url, no slides_url, no pptx_path — nothing available"
    },
    {
      "filename": "2024-10-05-gitops-journey.md",
      "title": "GitOps Journey",
      "video_url": "https://www.youtube.com/watch?v=stu678",
      "youtube_id": "stu678",
      "slides_url": "https://drive.google.com/file/d/5STU/view",
      "pptx_path": "GitOpsCon/2024/GitOps Journey.pptx",
      "status": "pending",
      "notes": "Has everything, but transcript download FAILS and slides download FAILS"
    }
  ]
}
=============== END OF FILE ===============
