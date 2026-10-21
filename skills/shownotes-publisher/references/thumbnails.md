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

Decide explicitly:

- If the convention-path image exists, select it as `{thumbnail_source}` for
  validation below. A valid PNG needs no rewrite. A failed validation stops the
  publish until a valid source is available.
- If it is absent and the talk has slides, a YouTube thumbnail, or a video frame,
  invoke `Skill(skill: "illustrations")` to generate the thumbnail. Set
  `{thumbnail_source}` to the returned file's actual path; the generator may
  emit PNG or JPEG. Keep that original for its other destinations.
- If it is absent and no source exists yet, explicitly record the deferral.
  The site's placeholder SVG is the interim. When a source becomes available,
  invoke illustrations and place its result through the command below.

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
