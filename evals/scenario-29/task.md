# Pick the Right Thumbnail Aesthetic from Vault Signals

## Problem/Feature Description

A speaker delivered "Never Trust a Monkey" at JCON Europe 2026 last week. The recording is on YouTube. The speaker asks for a thumbnail and provides the YouTube URL — that's the entire request. They have no opinion on aesthetic; they want the agent to recommend one.

Pick the recommended aesthetic from the speaker's profile, generate the thumbnail, and document the reasoning so a reviewer can audit the pick.

## Output Specification

Produce two files:

1. **`aesthetic-decision.md`** — The decision write-up. Must include:
   - Which profile field produced the recommendation, with the exact value quoted from the profile.
   - Which earlier-precedence fields were checked first and not used (so the audit trail is complete).
   - The recommended `--aesthetic` value.
   - A one-line note on whether a side-by-side two-candidate comparison is offered.
2. **`generate-command.sh`** — The `generate-thumbnail.py` invocation that the agent would run, with all arguments substituted from the profile.

## Input Files

The following file is provided. Extract it before beginning.

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 1,
  "generated_date": "2026-04-15",
  "talks_analyzed": 18,
  "speaker": {
    "name": "Dr. Maya Patel",
    "handle": "@mpresearch",
    "website": "https://mpresearch.dev",
    "shownotes_url_pattern": "https://mpresearch.dev/{slug}"
  },
  "publishing_process": {
    "thumbnail": {
      "speaker_photo_path": "/Users/maya/photos/headshot-2026.jpg",
      "style_preference": "slide_dominant",
      "title_position": "top",
      "brand_colors": ["#1F3A5F", "#E8B04B"]
    },
    "shownotes": {
      "enabled": false
    }
  },
  "visual_style_history": {
    "default_illustration_style": "comic-book halftone with bold ink outlines",
    "style_departures": [
      {
        "talk_slug": "ml-fairness-2024",
        "style": "watercolor diagram",
        "trigger": "academic audience"
      }
    ],
    "mode_visual_profiles": [
      {
        "mode_id": "viral_keynote",
        "default_aesthetic": "comic_book"
      }
    ],
    "confirmed_visual_intents": [
      {
        "pattern": "halftone shading on every slide",
        "rule": "comic-book caricature for any speaker portrait"
      }
    ]
  }
}
=============== END FILE ===============

The talk's working directory contains:

- `presentation-outline.md` (no Illustration Style Anchor section for this particular talk).
- `illustrations/slide-08.png` — the illustrated slide the speaker chose for the thumbnail (already provided).
- The YouTube URL: `https://youtube.com/watch?v=monkey2026`.
- The hook title: the speaker has confirmed `"NEVER TRUST A MONKEY"`.
