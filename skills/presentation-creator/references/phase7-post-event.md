# Phase 7: Post-Event — Detail

Triggered separately — days or weeks after delivery. Not part of the linear
Phase 0-6 flow. The talk has been given, the recording exists, and the speaker
wants a YouTube thumbnail and/or to update shownotes with the video.

## Pre-Flight Checklist

Before ANY Phase 7 action, load these files. If any is missing, STOP and ask.

1. **`speaker-profile.json`** — thumbnail preferences, video publishing config
2. **`secrets.json`** — API keys (Gemini for thumbnail generation)
3. **`presentation-spec.md`** — talk slug, metadata (source of truth)
4. **`presentation-outline.md`** — the outline (slide references, illustration references)
5. **YouTube video URL** — provided by the speaker at trigger time

If shownotes don't exist and the speaker wants Step 7.2, STOP and ask — either
run Phase 6 Step 6.1 first, or get the shownotes URL manually.

---

### Step 7.1: YouTube Thumbnail Generation

Generate a thumbnail that competes for clicks in YouTube search results and
suggested videos. The thumbnail combines a slide visual, the speaker's face,
and a short hook title.

#### 1. Slide Selection

Scan the outline for high-impact slides. Suggest 3-5 candidates ranked by
visual engagement:

- **Illustrations** — highest impact, already designed for visual punch
- **Bold claims / provocative statements** — text that triggers curiosity
- **Key diagrams / architecture visuals** — concrete and recognizable
- **Demo screenshots** — when the demo is the main attraction

Avoid: bio slides, shownotes URL slides, bullet-heavy slides, generic titles.

Present candidates to the speaker with slide numbers and brief descriptions.
The speaker picks one — never auto-select.

#### 2. Slide Image Resolution

Get the slide image using this resolution chain:

1. **Existing illustration** (preferred) — check `illustrations/` directory for
   `slide-{NN}.*` matching the chosen slide. These are already high-quality.
2. **PPTX extraction** — use the helper mode:
   ```bash
   python3 skills/presentation-creator/scripts/generate-thumbnail.py \
     --extract-slide deck.pptx 15 --output slide-15.png
   ```
   Uses LibreOffice headless or PowerPoint AppleScript on macOS.
3. **Ask user** — if extraction fails, ask the speaker for a screenshot or
   exported image of the slide.

#### 3. Speaker Photo

Resolution order:
1. `publishing_process.thumbnail.speaker_photo_path` from speaker profile
2. Ask the speaker to provide a path or URL

The photo must be a real photograph — never AI-generated. Expression should
convey engagement and energy, not a neutral corporate headshot.

#### 4. Thumbnail Title Text

This is NOT the full talk title. It's a 3-5 word hook designed for
thumbnail readability at small sizes.

- Propose 2-3 options based on the talk's thesis and key claim
- The speaker confirms or edits the text
- ALL CAPS is standard for YouTube thumbnails
- Must be readable when the thumbnail is displayed at 160x90 pixels

#### 5. Generate

Decide the recommended `--aesthetic` per the precedence chain in
`rules/thumbnail-generation-rules.md` Rule 7. Walk these in order; the
first match wins:

1. `publishing_process.thumbnail.aesthetic_preference` — explicit
   speaker preference (`"photo"` or `"comic_book"`). Honor it and stop.
2. `visual_style_history.default_illustration_style` — observed pattern
   from past talks. Fuzzy-match: matches the comic-book family
   (`comic_book` / `comic-book` / `halftone` / `illustrated` /
   `cartoon` / `caricature`) → recommend `comic_book`. Matches a
   different documented style (`retro_tech_manual`, `watercolor`, etc.)
   → out-of-scope for current aesthetics; ask the speaker before
   generating. Otherwise fall through.
3. `visual_style_history.confirmed_visual_intents` — same fuzzy-match
   against each entry's `pattern` and `rule` fields.
4. Default → `photo`.

Lead with the recommended aesthetic as the primary candidate. Offer a
two-candidate side-by-side comparison only when the speaker is
genuinely undecided or wants to validate before committing — not as a
default. The comic-book treatment is high-variance: when it works it
produces significantly higher CTR than photo composites, when it misses
it looks off-brand.

```bash
# Option A: photographic composite (conservative)
python3 skills/presentation-creator/scripts/generate-thumbnail.py \
  --slide-image illustrations/slide-15.png \
  --speaker-photo ~/photos/headshot.jpg \
  --title "JUDGMENT DAY" \
  --subtitle "DevNexus 2026" \
  --vault ~/.claude/rhetoric-knowledge-vault \
  --aesthetic photo \
  --style slide_dominant \
  --title-position top \
  --brand-colors "#5B2C6F,#C0392B" \
  --output thumbnail-photo.png

# Option B: comic-book caricature (viral)
python3 skills/presentation-creator/scripts/generate-thumbnail.py \
  --slide-image illustrations/slide-15.png \
  --speaker-photo ~/photos/headshot.jpg \
  --title "JUDGMENT DAY" \
  --subtitle "DevNexus 2026" \
  --vault ~/.claude/rhetoric-knowledge-vault \
  --aesthetic comic_book \
  --style slide_dominant \
  --title-position top \
  --brand-colors "#5B2C6F,#C0392B" \
  --output thumbnail-comic.png
```

For most runs only ONE candidate is needed — the one chosen by the
precedence chain above. The two-candidate command set is only for
genuine uncertainty.

Apply other speaker preferences from `publishing_process.thumbnail`:
- `style_preference` → `--style`
- `title_position` → `--title-position`
- `brand_colors` → `--brand-colors`

(`aesthetic_preference` is consumed at the top of this step as the first
entry in the precedence chain — don't re-apply it here.)

The script:
- Sends both images + prompt to Gemini as multimodal input
- Uses researched prompt strategy per the chosen aesthetic
- Validates output: exactly 1280x720, <2MB, PNG preferred
- Saves to the specified output path (default: `thumbnail.png` in illustrations dir)

#### 6. Speaker Review

Present the generated thumbnail for approval. If rejected:
- Adjust specific prompt components (style, position, colors, text)
- Try a different slide image
- Do NOT regenerate from scratch — iterate on the existing prompt

Common revision requests:
- "Face looks wrong" → strengthen face preservation language
- "Text is unreadable" → increase contrast, change position
- "Too busy" → switch to simpler style variant
- "Wrong mood" → adjust expression guidance

#### 7. Copy Thumbnail to Shownotes Site

If `publishing_process.shownotes.enabled` is true, the SSG template expects
the thumbnail at a specific path relative to the shownotes site root —
otherwise the live page falls back to a placeholder image with no warning.

Resolve the destination using `publishing_process.shownotes`:

```
{shownotes.source.path_or_url}/{shownotes.thumbnail_path_template}
```

with `{slug}` substituted from the Presentation Spec. For Jekyll-based
shownotes in this toolkit the default template is
`assets/images/thumbnails/{slug}-thumbnail.png` — both the nested
`thumbnails/` subdirectory AND the `-thumbnail` suffix are mandatory. Do not
strip either when landing the file.

Create the `thumbnails/` directory if it doesn't exist, then copy (don't move)
the generated thumbnail — the local copy in `illustrations/thumbnail.png`
stays with the talk's working directory for tracking.

If the SSG template pointer (`shownotes.ssg_template_pointer`) is set, read
that file after a site redesign to re-derive the path convention. Don't
re-invent it from folklore.

#### 8. Tracking Database Update

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

---

### Step 7.2: Video to Shownotes

Update the existing shownotes page with the video recording link.

#### 1. Verify Shownotes Exist

Check that shownotes were published in Phase 6 Step 6.1. Look for:
- The shownotes URL in `tracking-database.json` for this talk
- Or construct from `publishing_process.shownotes.url.base` +
  `publishing_process.shownotes.url.template` (substitute `{slug}` and any
  date variables) — see phase6-publishing.md for the full template semantics

If shownotes don't exist, STOP and ask the speaker. Options:
- Run Phase 6 Step 6.1 to create them now
- Provide the shownotes URL manually
- Skip this step

#### 2. Read Video Publishing Config

Read `publishing_process.video_publishing` from speaker profile:

- `enabled` — if false, skip this step
- `embed_method` — `youtube_embed`, `link_only`, or `both`
- `shownotes_video_section` — where/how the video section goes in shownotes
- `video_description_template` — template for YouTube video description

If `video_publishing` is not configured, ask interactively:
- "How should the video appear in shownotes? (embed, link, or both)"
- "Where in the shownotes should it go?"

#### 3. Generate Shownotes Update

Create the video section content based on `embed_method`:

- **youtube_embed**: Full responsive YouTube embed iframe
- **link_only**: "Watch the Recording" heading with a link to the video
- **both**: Embed iframe + text link below

Include the video title, conference name, and year from the presentation spec.

#### 4. Apply Update

Use the same publishing method as Phase 6 Step 6.1:
- If git-based: create/update the shownotes file, commit, push
- If CMS: provide the content for the speaker to paste
- If manual: present the formatted content block

#### 5. Tracking Database Update

Set `video_added_to_shownotes: true` on the talk's entry in `talks[]`.

Add the YouTube URL to the talk entry if not already present.

---

### Phase 7 Report

```
POST-EVENT REPORT — {talk title}
==================================
[DONE/SKIP] Thumbnail: {path, dimensions, size}
[DONE/SKIP] Video to shownotes: {shownotes URL, embed method}
[INFO] YouTube URL: {url}
==================================
```
