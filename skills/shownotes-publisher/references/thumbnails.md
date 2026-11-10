# Thumbnail Placement

Read in Step 6. The site's templates compute the image path from the talk-page
filename, including for social previews:

```text
assets/images/thumbnails/{talk_page_stem}-thumbnail.png
```

For `geecon-2026-absolutely-right.md`, use
`assets/images/thumbnails/geecon-2026-absolutely-right-thumbnail.png`.
Do not set `thumbnail_url:` in frontmatter; see
[common mistakes, entry 1c](common-mistakes.md) for its featured-talk flag semantics.

The thumbnail has two phases: a deck slide before the video exists, and the
generated YouTube thumbnail once it does. Decide explicitly:

- **This run adds the `**Video:**` line** (Step 5's URL-lands update): generate
  the YouTube thumbnail through the source-only handoff below and place it over
  the existing image. It replaces the pre-video slide.
- **The page has a `**Video:**` line and no convention-path image:** use the
  same source-only handoff.
- **The convention-path image exists and this run does not add the
  `**Video:**` line:** keep it. Select it as `{thumbnail_source}` for validation
  below. A valid PNG needs no rewrite; retain legacy dimensions, including 4:3
  thumbnails. A failed decoding or format validation stops the publish until a
  valid source is available.
- **No `**Video:**` line, no image, and the talk has a deck:** place a slide
  as-is. Propose 3–5 candidates ranked by the illustrations
  [slide selection](../../illustrations/references/thumbnails.md#sub-step-1-slide-selection);
  the speaker picks one, never auto-select. Resolve its image through
  [slide image resolution](../../illustrations/references/thumbnails.md#sub-step-2-slide-image-resolution)
  and set `{thumbnail_source}` to it. No generation, speaker photo, hook text or
  compositing.
- **No `**Video:**` line, no image, no deck:** record the deferral. The site's
  placeholder SVG is the interim until a deck or video arrives.

Source-only handoff: invoke `Skill(skill: "illustrations")` with
`thumbnail_scope: source_only`. Follow its
[source-generation scope](../../illustrations/references/thumbnails.md#requested-scope):
it returns an approved image without calling shownotes or placing/publishing it.
Set `{thumbnail_source}` to the returned file's actual path; the generator may
emit PNG or JPEG. Keep that original for its other destinations.

For an available image, run the placement owner; never rename JPEG bytes to PNG:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/shownotes-publisher/scripts/place-thumbnail.py" \
  --source "{thumbnail_source}" \
  --destination "{shownotes_repo}/assets/images/thumbnails/{talk_page_stem}-thumbnail.png"
```

The script's module docstring owns accepted inputs, output validation, atomic
placement, source preservation, dependencies, and exit codes. On exit 0, require
`ok: true` and use its emitted PNG path. On failure, stop publishing, repair the
reported input/runtime/filesystem problem, and rerun. Never substitute a raw copy.

The site's [thumbnail display geometry](template-conditionals.md#thumbnail-display-geometry)
accepts the illustrations owner's source dimensions. Check title and face
visibility in the destination preview. Finish Step 6 only after validated
placement or the explicit no-source deferral, then proceed to Step 7.
Retain the approved `thumbnail_source` and placement receipt with the publication
result. Return them to an invoking illustrations workflow so it can resume its
remaining tracking work without generating the image again.
