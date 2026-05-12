# Thumbnail Generation — Detail

Reference for Step 7 (thumbnail) in `SKILL.md`. The
`thumbnail-generation-rules` steering rule is auto-loaded — apply it, don't
restate it.

## Pre-Flight

Before any thumbnail work, confirm the inputs:

1. **`speaker-profile.json`** — `publishing_process.thumbnail` config and
   `visual_style_history`.
2. **`secrets.json`** — Gemini API key.
3. **`presentation-spec.md`** — talk slug, metadata.
4. **`presentation-outline.md`** — slide references; the
   Illustration Style Anchor block (if present) feeds `--portrait-style`.
5. **YouTube video URL** — provided by the speaker at trigger time.

If shownotes are needed too (Step 7.2 in presentation-creator) and don't
exist yet, STOP and ask before generating the thumbnail.

## Sub-step 1: Slide Selection

Scan the outline for high-impact slides. Suggest 3–5 candidates ranked by
visual engagement:

- **Illustrations** — highest impact, already designed for visual punch.
- **Bold claims / provocative statements** — text that triggers curiosity.
- **Key diagrams / architecture visuals** — concrete and recognizable.
- **Demo screenshots** — when the demo is the main attraction.

Avoid: bio slides, shownotes URL slides, bullet-heavy slides, generic titles.

Present candidates to the speaker with slide numbers and brief descriptions.
The speaker picks one — never auto-select.

## Sub-step 2: Slide Image Resolution

Resolution chain:

1. **Existing illustration** (preferred) — check `illustrations/` for
   `slide-{NN}.*` matching the chosen slide.
2. **PPTX extraction** — use the helper mode:
   ```bash
   python3 skills/illustrations/scripts/generate-thumbnail.py \
     --extract-slide deck.pptx 15 --output slide-15.png
   ```
   Uses LibreOffice headless or PowerPoint AppleScript on macOS.
3. **Ask the speaker** — if extraction fails, request a screenshot or
   exported image of the slide.

## Sub-step 3: Speaker Photo

Resolution order:

1. `publishing_process.thumbnail.speaker_photo_path` from speaker profile.
2. Ask the speaker to provide a path or URL.

The photo must be a real photograph — never AI-generated. Expression should
convey engagement and energy, not a neutral corporate headshot.

## Sub-step 4: Hook Title Text

NOT the full talk title. A 3–5 word hook designed for thumbnail readability
at small sizes.

- Propose 2–3 options based on the talk's thesis and key claim.
- The speaker confirms or edits.
- ALL CAPS is standard.
- Must be readable at 160×90 pixels (YouTube search-result size).

## Sub-step 5: Aesthetic Selection

Walk the precedence chain (`thumbnail-generation-rules` Rule 7):

1. `publishing_process.thumbnail.aesthetic_preference` — explicit speaker
   preference (`"photo"` or `"comic_book"`). Honor it and stop.
2. `visual_style_history.default_illustration_style` — fuzzy-match against
   the comic-book family (`comic_book` / `comic-book` / `halftone` /
   `illustrated` / `cartoon` / `caricature`) → recommend `comic_book`.
   Documented styles outside that set (`retro_tech_manual`, `watercolor`,
   etc.) → out-of-scope; ask the speaker before generating.
3. `visual_style_history.confirmed_visual_intents` — same fuzzy-match
   against each entry's `pattern` and `rule` fields.
4. Default → `photo`.

Lead with the recommended aesthetic. Offer a two-candidate side-by-side
only when the speaker is genuinely undecided — not as a default. Comic-book
is high-variance: when it works, CTR rises significantly; when it misses,
it looks off-brand.

## Sub-step 6: Pass Through the Deck's Style Anchor

If `presentation-outline.md` has an `## Illustration Style Anchor` section
(with one or more `### STYLE ANCHOR (FORMAT — ratio)` entries inside it),
pass the matching entry's anchor paragraph to `generate-thumbnail.py` via
`--portrait-style "<anchor>"`. The script pre-stylizes the speaker photo
into the anchor's medium (sepia tech-manual, watercolor, pen-and-ink, etc.)
before composition, so the output palette matches the deck. Without this pass-through, photographic skin tones beside
an illustrated background produce a jarring two-medium composite even when
the aesthetic is otherwise correct.

If Phase 2 didn't produce a style anchor (stock-image-only deck), omit
`--portrait-style`.

## Sub-step 7: Generate

```bash
# Single recommended candidate (the precedence-chain winner)
python3 skills/illustrations/scripts/generate-thumbnail.py \
  --slide-image illustrations/slide-15.png \
  --speaker-photo ~/photos/headshot.jpg \
  --title "JUDGMENT DAY" \
  --subtitle "DevNexus 2026" \
  --vault ~/.claude/rhetoric-knowledge-vault \
  --aesthetic <photo|comic_book> \
  --style slide_dominant \
  --title-position top \
  --brand-colors "#5B2C6F,#C0392B" \
  --output thumbnail.png

# Anchor-matched (when the deck has an Illustration Style Anchor section)
python3 skills/illustrations/scripts/generate-thumbnail.py \
  --slide-image illustrations/slide-15.png \
  --speaker-photo ~/photos/headshot.jpg \
  --title "JUDGMENT DAY" \
  --aesthetic photo \
  --portrait-style "<full anchor paragraph>" \
  --output thumbnail-anchored.png
```

Apply other speaker preferences from `publishing_process.thumbnail`:

- `style_preference` → `--style`
- `title_position` → `--title-position`
- `brand_colors` → `--brand-colors`

`aesthetic_preference` is consumed at Sub-step 5 — don't re-apply it.

The script (per invocation, runs once per `--aesthetic`):

- Sends slide image + speaker photo + prompt to Gemini as multimodal input.
- Uses the researched prompt strategy per the chosen aesthetic.
- Validates output: exactly 1280×720, <2MB, PNG preferred.
- Saves to the specified output path (default: `thumbnail.png` in the
  illustrations dir).

## Sub-step 8: Speaker Review

Present the generated thumbnail. If rejected, iterate — never regenerate
from scratch:

- "Face looks wrong" → adjust style variant or try a different slide image.
  Don't add face-preservation language (it trips Gemini's safety filter on
  photo aesthetic).
- "Text is unreadable" → increase contrast, change `--title-position`.
- "Too busy" → switch to a simpler style variant.
- "Wrong mood" → adjust expression guidance in the prompt.

## Sub-step 9: Copy Thumbnail to Shownotes Site

If `publishing_process.shownotes.enabled` is true, the SSG template expects
the thumbnail at a specific path relative to the shownotes site root —
otherwise the live page falls back to a placeholder with no warning.

Resolve the destination using `publishing_process.shownotes`:

```
{shownotes.source.path_or_url}/{shownotes.thumbnail_path_template}
```

with `{slug}` substituted from the Presentation Spec. For Jekyll-based
shownotes the default template is
`assets/images/thumbnails/{slug}-thumbnail.png` — the nested `thumbnails/`
subdirectory AND the `-thumbnail` suffix are both mandatory. Do not strip
either.

Create the `thumbnails/` directory if it doesn't exist, then **copy** (don't
move) the generated thumbnail. The local copy in `illustrations/thumbnail.png`
stays with the talk's working directory for tracking.

If `shownotes.ssg_template_pointer` is set, read that file after a site
redesign to re-derive the path convention. Don't reinvent it from folklore.

## Sub-step 10: Tracking Database Update

Add to `thumbnails[]` in `tracking-database.json`:

```json
{
  "talk_slug": "judgment-day",
  "youtube_url": "https://youtube.com/watch?v=...",
  "source_slide_num": 15,
  "speaker_photo_used": "/path/to/headshot.jpg",
  "thumbnail_path": "illustrations/thumbnail.png",
  "shownotes_thumbnail_path": "assets/images/thumbnails/judgment-day-thumbnail.png",
  "dimensions": "1280x720",
  "file_size_kb": 185,
  "created_at": "2026-04-20",
  "approved": true
}
```

Also set `thumbnail_generated: true` on the talk's entry in `talks[]`.
