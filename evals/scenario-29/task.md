# Pick the Right Thumbnail Aesthetic from Vault Signals

## Problem/Feature Description

A speaker delivered "Never Trust a Monkey" at JCON Europe 2026 last week. The recording is on YouTube. The speaker asks for a thumbnail and provides the YouTube URL — that's the entire request. They have no opinion on aesthetic; they want the agent to recommend one.

The illustrations skill must walk the aesthetic precedence chain (`thumbnail-generation-rules` Rule 7) before generating, not default to the CLI's `--aesthetic photo`. The chain is:

1. `publishing_process.thumbnail.aesthetic_preference` — explicit speaker preference. Honor and stop.
2. `visual_style_history.default_illustration_style` — fuzzy-match against the comic-book family.
3. `visual_style_history.confirmed_visual_intents` — same fuzzy-match.
4. Default → `photo`.

Generate the thumbnail using the recommended aesthetic. Document the reasoning so a reviewer can audit the pick.

## Output Specification

Produce two files:

1. **`aesthetic-decision.md`** — The decision write-up. Must include:
   - Which step in the precedence chain produced the answer (1, 2, 3, or 4).
   - The exact field value(s) consulted at that step (quote from the profile).
   - The recommended `--aesthetic` value.
   - A one-line note on whether a side-by-side comparison is offered (the rule says lead with the recommendation; offer comparison only when the speaker is genuinely undecided — they aren't here).
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

- `presentation-outline.md` (no STYLE ANCHOR — text-and-illustration deck without an explicit Phase 2 D#11 anchor for this particular talk).
- `illustrations/slide-08.png` — the illustrated slide the speaker chose for the thumbnail (already provided).
- The YouTube URL: `https://youtube.com/watch?v=monkey2026`.
- The hook title: the speaker has confirmed `"NEVER TRUST A MONKEY"`.

Note: `publishing_process.thumbnail.aesthetic_preference` is **not present** — the speaker hasn't pinned an explicit preference. The chain therefore falls through to step 2.
