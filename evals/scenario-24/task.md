# Plan a YouTube Thumbnail for a Delivered Talk

## Problem/Feature Description

A speaker delivered "Robocoders: Judgment Day" at DevNexus 2026 two weeks ago. The recording is now on YouTube at `https://youtube.com/watch?v=abc123`. The speaker wants a YouTube thumbnail that will maximize click-through rate.

The outline has an illustration strategy (retro sci-fi propaganda poster aesthetic) with several full-bleed illustration slides, plus text slides, a bio slide, a shownotes slide, and bullet-heavy slides. The speaker's profile has thumbnail preferences configured.

Using the presentation-creator skill, plan the complete thumbnail generation workflow: select candidate slides, propose a title, and document the exact command to generate the thumbnail.

## Output Specification

Produce the following files:

1. **`thumbnail-plan.md`** — Complete thumbnail workflow plan including:
   - List of 3-5 candidate slides ranked by visual impact, with reasoning for each
   - Which slides were excluded and why
   - 2-3 proposed title text options (short hooks, not the full talk title)
   - The exact `generate-thumbnail.py` command that would be run (with all arguments)
   - Where the speaker photo comes from
   - How face preservation is handled in the generation process
2. **`slide-candidates.md`** — Formatted list of candidate slides with:
   - Slide number and description
   - Why this slide is a good/bad candidate
   - Source for the slide image (illustration file, extraction, etc.)

## Input Files

Download vault fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-24"
mkdir -p inputs/vault inputs/talk
curl -L -o inputs/vault/speaker-profile.json "$BASE/speaker-profile.json"
curl -L -o inputs/vault/secrets.json "$BASE/secrets.json"
curl -L -o inputs/vault/tracking-database.json "$BASE/tracking-database.json"
curl -L -o inputs/talk/presentation-spec.md "$BASE/presentation-spec.md"
curl -L -o inputs/talk/presentation-outline.md "$BASE/presentation-outline.md"
```

## Key Parameters

- **YouTube URL:** `https://youtube.com/watch?v=abc123`
- **Talk title:** "Robocoders: Judgment Day"
- **Illustration style:** Retro sci-fi propaganda poster
- **Illustration slides:** 1, 10, 25 (full-bleed illustrations)
- **Bio slide:** 4 (should be avoided)
- **Shownotes slide:** 3 (should be avoided)
- **Bullet-heavy slide:** 18 (should be avoided)
- **Profile thumbnail preferences:** style=overlay, title_position=bottom, brand_colors=#5B2C6F,#C0392B
- **Speaker photo path:** configured in profile
