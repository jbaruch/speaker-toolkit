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

## 4. Speaker Photo Required (Input)

The speaker photo file passed to the script — `--speaker-photo` /
`publishing_process.thumbnail.speaker_photo_path` — must be a real
photograph of the speaker. Never an AI-generated headshot, stock-photo
substitute, or stylized portrait. The script uses it as the identity
anchor; an AI-generated input compounds artifacts when the model uses
it as a reference.

This rule scopes the **input only**. The output rendering depends on
`--aesthetic` (Rule 7):

- `aesthetic photo` — output preserves photographic realism. The face
  in the thumbnail looks like the speaker's face in the input.
- `aesthetic comic_book` — output renders the speaker as a comic-book
  caricature derived from the input photo. The output is illustrated,
  not photographic; identifying features (hair, beard, glasses, hat)
  are preserved so the speaker remains recognizable.

Both aesthetics still require a real photo as input; the comic-book
aesthetic transforms it into illustration, but the source must be a
photograph. Real-photo inputs produce thumbnails with faces, and faces
boost CTR 35-50% regardless of which aesthetic the output uses.

Expression: convey engagement, not a neutral corporate headshot. The
expression carries through whether the output is photographic or
caricatured.

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

## 6. Face Preservation — Framing, Not Demands

Frame the request as GRAPHIC COMPOSITION ("combine these two images into a
1280x720 graphic, portrait goes into the foreground"), not as face-preservation
("maintain exact facial features, bone structure, skin texture"). Assertive
face-preservation language combined with viral-styling demands reliably trips
Gemini's safety filter on real-person photos — the script saw 100%
`finishReason: IMAGE_OTHER` rejections with the original prompt.

This rule applies to the **photo aesthetic** (the script's default). The
**comic-book aesthetic** (Rule 7) handles speaker rendering differently —
through caricature, not photo realism — and isn't subject to the same filter.

Do (photo aesthetic):
- Treat the speaker photo as a compositing asset.
- Apply viral styling to TYPOGRAPHY and LAYOUT, not to the face.
- Keep realism understated: "natural and unmodified" is enough.

Don't (photo aesthetic):
- Demand specific facial features be preserved by name (bone structure, skin
  texture, expression). Those phrases push the filter.
- Combine face-preservation claims with high-energy/viral/aggressive language.

After generation, verify the output face matches the input photo. If the face
looks altered, change the **style variant** or **title position** — not the
face-preservation wording.

## 7. Aesthetic Choice — Photo vs Comic Book

Two aesthetics are supported via `--aesthetic`:

| Value | Description | When to use |
|---|---|---|
| `photo` | Photographic composite; speaker face left natural; slide as background | Speakers without an established illustrated brand; talks where corporate / documentary tone is required |
| `comic_book` | Full comic-book illustration; speaker rendered as caricature with halftone shading; scene re-illustrated to match | **Recommended** for speakers with a documented comic-book aesthetic in their vault notes (`visual_style_history.default_illustration_style` or `confirmed_visual_intents`); talks where viral reach matters more than realism |

**Choosing per speaker.** Read `visual_style_history` from the speaker
profile:

- If `default_illustration_style` includes "comic-book", "halftone",
  "illustrated", or similar — **comic_book** is the right default for
  this speaker. The JCON Europe 2026 "Never Trust a Monkey" win
  validates the approach for at least one such speaker; expand the
  evidence base by trying it on other talks where the speaker's
  brand fits.
- If the speaker has a different documented style (retro tech manual,
  watercolor, etc.) — neither default is right; the script's two
  aesthetics don't yet cover those, file an issue requesting the new
  variant rather than forcing photo.
- If the speaker has no documented illustration style — default to
  **photo**.

**Phase 7 Step 7.1 protocol:** when in doubt, offer the speaker BOTH
aesthetics for the same title/slide combination. Generate two
candidates, present side-by-side, let the speaker pick. The comic-book
treatment is high-variance: when it works it produces significantly
higher CTR than photo composites, when it misses it looks off-brand.
The two-candidate approach lets the speaker resolve that variance with
their own taste — but lead with the recommendation from
`visual_style_history`, don't present them as equal options when the
profile clearly favors one.

**Comic-book prompt anchors** (used internally by the script — don't reproduce
them in agent-rolled prompts):
- "Render a single 16:9 comic-book illustration"
- "Bold ink outlines, halftone dot shading, exaggerated dynamic angles"
- "Render the speaker as a comic-book caricature in matching style"
- "Preserve identifying features — hair, beard, glasses, hat, and any other
  distinguishing accessories"
- Title with "thick black outline and a thin contrasting inner outline
  (classic blockbuster comic-book treatment)"

**Why `--aesthetic` defaults to `photo` in the CLI:** speakers without
a documented illustrated brand are the safer fallback for the script's
default flag. The agent's recommendation, however, follows the profile's
`visual_style_history` — see "Choosing per speaker" above — and should
override the CLI default whenever the profile signals a clear illustrated
brand.

## 8. Model Selection and Retry Ladder

Face-composition with real-person photos only works on Nano Banana Pro
(`gemini-3-pro-image-preview`, the script's default). Earlier variants
(`gemini-2.5-flash-image`, `gemini-3.1-flash-image-preview`) reject any
face-composition prompt. Use `--model` only when you know the newer model
accepts the composition you need.

The script retries with progressively softer prompts ONLY on safety-filter
rejections (the API returns no image — IMAGE_OTHER, blocked candidate, empty
response). Transport-level failures (HTTP errors, rate limits, network
exceptions) surface immediately instead of burning all three retries on a
problem softening cannot fix.

Softness gradient:
- `default` — full prompt: base + typography styling + composition energy
- `softer` — drops the composition-energy modifier; typography styling stays
- `softest` — drops typography too; minimal composition framing only

If all three softness levels are rejected by the filter, the model has tightened
again: try a different slide image (less text-heavy backgrounds trip the filter
less often), or regenerate after a short delay.

## 9. Iterate, Don't Restart

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

## 10. Single Focal Point

One idea per thumbnail. Don't overload with multiple text blocks,
competing visuals, or busy backgrounds. You have 1.8 seconds to
capture attention at scroll speed.
