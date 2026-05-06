# Plan Thumbnail Revision After Speaker Feedback

## Problem/Feature Description

A speaker already generated a first thumbnail for their talk "Robocoders: Judgment Day" using slide 10 (a courtroom illustration). The speaker reviewed it and gave this feedback:

> "The face looks a bit too idealized — doesn't look like me. Also, I want the text at the top instead of the bottom. And let's try the split_panel style instead of overlay. Keep the same slide and title text."

The agent must plan the revision. The speaker chose slide 10, which has an existing illustration in the `illustrations/` directory. The profile has thumbnail preferences configured but the speaker is overriding some of them for this iteration.

Using the illustrations skill, plan the thumbnail revision. Document the exact command and explain the revision strategy.

## Output Specification

Produce the following files:

1. **`revision-plan.md`** — The complete revision plan including:
   - The revised `generate-thumbnail.py` command with updated arguments
   - Which arguments changed vs the original run
   - Where the slide image comes from (resolution chain)
   - How the "face looks too idealized" feedback is addressed (per the thumbnail rules — via style variant or slide change, not by adding face-preservation language to the prompt)
   - Strategy explanation: iterate on specific components, not restart from scratch
2. **`original-vs-revised.md`** — Side-by-side comparison of original and revised command arguments showing what changed

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 1,
  "generated_date": "2026-04-15",
  "talks_analyzed": 1,
  "speaker": {
    "name": "Baruch Sadogursky",
    "handle": "@jbaruch",
    "website": "https://jbaru.ch",
    "shownotes_url_pattern": "https://jbaru.ch/{slug}"
  },
  "publishing_process": {
    "thumbnail": {
      "enabled": true,
      "speaker_photo_path": "/Users/jbaruch/photos/devnexus-headshot.jpg",
      "style_preference": "overlay",
      "title_position": "bottom",
      "brand_colors": ["#5B2C6F", "#C0392B"]
    }
  }
}

=============== FILE: inputs/presentation-outline.md ===============
# Robocoders: Judgment Day
**Spec:** Keynote | 45 min | DevNexus 2026

## Illustration Style Anchor
**Model:** `gemini-3-pro-image-preview`
### STYLE ANCHOR (FULL — Landscape 1920x1080)
> Retro sci-fi propaganda poster aesthetic. Bold colors, dramatic lighting.

## Act 1: The Reality Check [12 min, slides 5-20]
### Slide 10: The Verdict
- Format: **FULL**
- Illustration: A dramatic courtroom scene with a robot on trial
- Image prompt: `[STYLE ANCHOR]. A dramatic courtroom with a robot defendant.`
- Visual: Full-bleed illustration
- Speaker: The evidence is clear.

=============== FILE: inputs/illustrations/slide-10.png ===============
(This file exists as a placeholder — the illustration was generated in Phase 5)

=============== FILE: inputs/first-run-command.txt ===============
python3 generate-thumbnail.py \
  --slide-image illustrations/slide-10.png \
  --speaker-photo /Users/jbaruch/photos/devnexus-headshot.jpg \
  --title "JUDGMENT DAY" \
  --style overlay \
  --title-position bottom \
  --brand-colors "#5B2C6F,#C0392B"

## Key Parameters

- **Speaker feedback:** face too idealized, change to split_panel style, text at top
- **Selected slide:** 10 (courtroom illustration — unchanged)
- **Title text:** "JUDGMENT DAY" (unchanged)
- **Original style:** overlay → **Revised:** split_panel
- **Original title-position:** bottom → **Revised:** top
- **Face issue:** needs stronger preservation language
- **Illustration exists:** illustrations/slide-10.png (from Phase 5)
