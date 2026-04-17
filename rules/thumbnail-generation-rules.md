# Thumbnail Generation Rules

Steering rules for Phase 7 Step 7.1 — YouTube thumbnail generation.

## 1. Script First

ALWAYS use `generate-thumbnail.py` — no hand-rolled Gemini calls or PIL
composition. The script encapsulates the researched prompt strategy, face
preservation, and YouTube spec compliance.

```bash
python3 skills/presentation-creator/scripts/generate-thumbnail.py \
  --slide-image illustrations/slide-15.png \
  --speaker-photo ~/photos/headshot.jpg \
  --title "JUDGMENT DAY" \
  --style slide_dominant
```

## 2. YouTube Specs Non-Negotiable

1280x720 pixels, 16:9, <2MB, PNG or JPG. Text must be readable at
160x90 pixels (YouTube search result size). The script validates
dimensions and file size automatically, resizing and compressing as
needed. Do not override these constraints.

## 3. Slide Selection is Collaborative

The agent suggests 3-5 candidate slides ranked by visual impact:
- Illustrations > bold claims > diagrams > text slides
- **Never auto-select** — the speaker picks

Avoid these slide types:
- Bio/intro slides
- Shownotes URL slides
- Bullet-heavy slides
- Generic title slides

## 4. Speaker Photo Required

Real photo only — never AI-generated. Thumbnails with faces get 35-50%
higher click-through rates. The expression should convey engagement, not
a neutral corporate headshot.

Resolution order:
1. `publishing_process.thumbnail.speaker_photo_path` from profile
2. Ask the user to provide a path or URL

## 5. Title Text: 5 Words Maximum

This is a HOOK, not the full talk title. Bold sans-serif, thick
outline/shadow. Warm accent colors preferred. The speaker confirms
the text before generation.

Examples:
- "Robocoders: Judgment Day" -> "JUDGMENT DAY"
- "The Arc of AI" -> "AI CHANGES EVERYTHING"
- "Building Resilient Systems" -> "WHEN SYSTEMS BREAK"

## 6. Face Preservation

The Gemini prompt MUST include:
- "Maintain exact facial features, bone structure, skin texture, and
  natural appearance from the reference"
- "Do not stylize, beautify, alter, or idealize the face"

After generation, verify the output face matches the input photo. If
the face looks altered, regenerate with stronger preservation language.

## 7. Iterate, Don't Restart

When the speaker requests changes, modify specific prompt components
(expression, position, colors, text) rather than regenerating from
scratch. Gemini's conversational refinement produces better results
than cold restarts.

Adjustment targets:
- **Face position** — change the style variant (slide_dominant, split_panel, overlay)
- **Expression** — adjust the expression guidance in the prompt
- **Colors** — add or change `--brand-colors`
- **Text** — update `--title` or `--title-position`
- **Background** — try a different slide image

## 8. Single Focal Point

One idea per thumbnail. Don't overload with multiple text blocks,
competing visuals, or busy backgrounds. You have 1.8 seconds to
capture attention at scroll speed.
