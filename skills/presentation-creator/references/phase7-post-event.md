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

Delegate to the illustrations skill — it owns slide selection, photo
resolution, aesthetic precedence, composition via Gemini, speaker iteration,
shownotes copy, and tracking-database updates:

```
Skill(skill: "illustrations")
```

See `skills/illustrations/references/thumbnails.md` for the full
workflow. Returns control here once the thumbnail is approved and the
tracking database is updated.

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
