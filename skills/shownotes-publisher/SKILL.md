---
name: shownotes-publisher
description: >
  Publish a talk page to the Jekyll-based shownotes site (e.g.,
  speaking.jbaru.ch). Composes the `_talks/<file>.md` markdown so the
  custom Jekyll parser plugin extracts the right fields, the talk.html
  layout renders correctly, and the "Video Coming Soon" badge fires
  when the recording isn't ready yet. Use when the user says "publish
  shownotes", "create shownotes page", "add talk to shownotes",
  "shownotes for <talk>", "shownotes site", "speaking.jbaru.ch", or
  asks to update a talk page (e.g., "add the video to the shownotes",
  "the video is out", "update shownotes with the recording"). Also
  trigger for first-time publishing before a talk is delivered, when
  only the slides URL exists. The Jekyll site at `~/Projects/shownotes`
  uses a custom markdown parser (`_plugins/markdown_parser.rb`) that
  imposes specific format rules — this skill encodes those rules so
  the agent doesn't author content that silently fails to render.
user-invocable: true
---

# Shownotes Publisher

Process steps in order. Do not skip ahead. This skill writes a
markdown file into the Jekyll shownotes site's `_talks/` collection
where a custom parser plugin extracts structured fields by pattern
matching on the body. The format is strict — small mistakes silently
flatten content or break conditional rendering.

The shownotes site lives at `~/Projects/shownotes` and is published to
`https://speaking.jbaru.ch` via GitHub Pages. Authoritative references:

- Parser: `~/Projects/shownotes/_plugins/markdown_parser.rb`
- Layout: `~/Projects/shownotes/_layouts/talk.html`
- Config: `~/Projects/shownotes/_config.yml`
- Examples: `~/Projects/shownotes/_talks/*.md`

Deeper reference material (parser contract, template conditionals,
common mistakes) lives at
[references/parser-contract.md](references/parser-contract.md),
[references/template-conditionals.md](references/template-conditionals.md),
and [references/common-mistakes.md](references/common-mistakes.md).

## Step 1 — Gather Context Automatically; Ask Only for the Slides URL

Everything the shownotes page needs is already in the talk's
artifacts by the time this skill runs. Do not ask the user to
re-supply anything that is derivable. Read automatically:

**From `outline.yaml` — the talk's presentation spec.** Load via
`skills/presentation-creator/scripts/outline_schema.py`. Never
re-parse YAML by hand. Map fields directly:

| Shownotes field | Source in outline.yaml |
|---|---|
| Title (body H1) | `talk.title` |
| Filename slug | `talk.slug` — the only source. Never invent, derive from venue, or rephrase |
| Conference | `talk.venue` |
| Date | `talk.delivery_date` (ISO `YYYY-MM-DD`) |
| Speakers | `talk.speakers[]` — single → `"by {{ site.speaker.display_name | default: site.speaker.name }}"`; multi → append `"and {co-speaker names}"` |
| Abstract seed | `talk.thesis` |

**From the talk directory:**

- `resources.json` (produced by `extract-resources.py` in Phase 6
  Step 6.0) — becomes the `## Resources` section. If the file is
  missing OR has no `approved: true` items, omit the section
- Any existing `_talks/{filename_stem}.md` — if this is an update
  (not a first publish), read it first so Step 7 preserves hand-edits.
  `{filename_stem}` is defined in Step 2

**Ask the user EXACTLY one question:**

> "What's the slides PDF embed URL? (Google Drive
> `https://drive.google.com/file/d/.../preview` form)"

That is the only input that's external to the talk's existing
artifacts. The speaker just uploaded the deck PDF to Drive
post-rehearsal; the URL is in their clipboard, not in any file.

**Don't ask about Video at this step.** Video URLs almost always
arrive later (post-recording publish). If the user volunteers a
video URL in the same turn, capture it; otherwise omit the
`**Video:**` line per Step 5 to fire the "Video Coming Soon" badge.

**Ask later only if a needed value is missing or ambiguous:**

- `outline.yaml` doesn't exist or doesn't validate → STOP and ask
  the speaker to run the presentation-creator skill first
- `talk.slug` is missing → STOP and ask (this should never happen —
  slug is schema-required)
- `talk.thesis` is empty → ask the speaker for a one-paragraph
  abstract (Step 4 rules apply)
- `talk.delivery_date` is missing → ask if the talk has been
  delivered yet; if not, the page can still publish (pre-talk
  announcement with slides only)
- Existing `_talks/{filename_stem}.md` exists AND the speaker didn't
  flag this as an update → ask before overwriting (Step 7)

Read first. Only ask on ambiguity.

Proceed immediately to Step 2.

## Step 2 — Compose Filename

The talk slug `{talk_slug}` is `outline.yaml::talk.slug` — the spec
is the only source. Already kebab-case validated by `outline_schema.py`.
Never invent it, never derive it from the venue or title, never
rephrase.

Filename convention in `_talks/`, picked by rule:

- If `talk.delivery_date` is set → `{YYYY-MM-DD}-{talk_slug}.md`
  (e.g., `2026-05-07-devoxx-uk-2026-300-tokens.md`)
- If `talk.delivery_date` is not set (pre-talk publish) →
  `{talk_slug}.md` (e.g., `geecon-2026-absolutely-right.md`)

Don't ask the user which convention to use. The presence of
`delivery_date` is the signal.

The chosen filename's stem (everything before `.md`) is the
`{filename_stem}` used by Steps 6, 8, and 9 for the thumbnail path
and the live URL. Examples:

| `talk_slug` | `delivery_date` | filename | `filename_stem` |
|---|---|---|---|
| `devoxx-uk-2026-300-tokens` | `2026-05-07` | `2026-05-07-devoxx-uk-2026-300-tokens.md` | `2026-05-07-devoxx-uk-2026-300-tokens` |
| `geecon-2026-absolutely-right` | (absent) | `geecon-2026-absolutely-right.md` | `geecon-2026-absolutely-right` |

If an existing file at the conventional path was created in the
OTHER convention (e.g., the file is `{talk_slug}.md` but
`talk.delivery_date` is now set), keep the existing filename
unchanged. Renaming a published talk breaks the live URL and any
QR codes printed against it.

Full path: `~/Projects/shownotes/_talks/{filename_stem}.md`.

Proceed immediately to Step 3.

## Step 3 — Compose Frontmatter

Minimum frontmatter:

```yaml
---
layout: talk
---
```

The Jekyll plugin auto-inserts this if absent, but write it explicitly
to make the file portable across plugin versions.

**Do NOT put in frontmatter:**

- `title:` — the title comes from the H1 in the body
  (`extract_title_from_content`). A frontmatter title overrides the H1
  for the page title but the H1 still renders as the visible title,
  causing duplication
- `video:`, `slides:`, `conference:`, `date:` — these are extracted
  from the body via the `**Field:** value` pattern. Putting them in
  frontmatter doesn't help and may confuse a future reader
- `description:`, `abstract:` — extracted from body sections; same
  reasoning
- `thumbnail_url:` — does nothing useful. The thumbnail path is
  resolved entirely by the **filename slug naming convention** (see
  Step 6 and references/template-conditionals.md). The frontmatter
  field is checked only as a truthiness signal for whether to
  include the talk in the homepage "Highlighted Presentations" set,
  and even that's redundant with `extracted_slides`/`extracted_video`.
  Setting the field misleads a reader into thinking it overrides the
  thumbnail path — it doesn't. Drop the file at the conventional
  location instead

Proceed immediately to Step 4.

## Step 4 — Compose the Body

Body structure is a strict sequence the parser expects. Every value
in `{braces}` below is derived from `outline.yaml` or
`resources.json` per Step 1 — not asked from the user (except the
slides URL, which is the one question from Step 1).

```markdown
# {talk.title}

**Conference:** {talk.venue}
**Date:** {talk.delivery_date}
**Slides:** [View Slides]({slides_url_from_step_1})
**Video:** [View Video]({video_url})       # ← omit this line entirely if no video yet

A presentation at {talk.venue} in
                    {Month YYYY} in
                    {City, Country} by
                    {{ site.speaker.display_name | default: site.speaker.name }}

## Abstract

{talk.thesis, lightly adapted into one flowing paragraph. No
sub-headings, no lists, no code blocks. See
[references/parser-contract.md](references/parser-contract.md) for
the exact capture-and-flatten mechanic.}

## Resources

- [{title}]({url})            # one bullet per approved resources.json entry
- [{title}]({url})

### Optional Sub-Sections

Sub-sections under Resources DO render correctly — Resources
captures everything after `## Resources` until end-of-file.
```

**Where each value comes from:**

- `{talk.title}` → first H1. Body content, not frontmatter
- `{talk.venue}` → `**Conference:**` value AND first phrase of the
  "A presentation at" paragraph
- `{talk.delivery_date}` → `**Date:**` value (ISO `YYYY-MM-DD`).
  Omit the `**Date:**` line entirely when `talk.delivery_date` is
  not set (pre-talk publish) — an empty value won't match the
  parser's `(.+)` capture and renders as stray body text
- `{Month YYYY}` → derived from `talk.delivery_date` when set;
  omit the date-related sub-phrase from the presentation context
  paragraph when not set (`"A presentation at {talk.venue} by …"`)
- `{City, Country}` → use `talk.venue` text as-is; do not ask a
  second question for the city if the venue string doesn't carry
  one. The presentation context paragraph reads fine with the
  venue alone (`"A presentation at Devoxx UK 2026 by …"`)
- `{slides_url_from_step_1}` → the answer to Step 1's single question
- `{video_url}` → omit the line unless the user provided a real
  YouTube URL with the slides URL (see Step 5)
- Co-speaker case (`len(talk.speakers) > 1`): append `and {name}`
  for each additional speaker after the liquid template variable

**Field block rules (lines 2–5 of the example):**

- Each field is `**FieldName:** value` on its own line
- Field names: `Conference`, `Date`, `Slides`, `Video` — case-insensitive
  match in the parser, but write them in title case for readability
- Slides and Video URLs MUST be wrapped in markdown link syntax
  `[Link Text](url)` — the parser extracts the URL from `$2` of
  `\[([^\]]+)\]\(([^)]+)\)`. A bare URL or plain text won't populate
  `extracted_slides`/`extracted_video` and the media embed section
  won't render
- Date format: `YYYY-MM-DD` (ISO 8601) so `date_to_xmlschema` and
  `date: "%B %d, %Y"` filters in the layout produce the right output

**Presentation context paragraph rules:**

- Must start with `A presentation at` — the parser uses this as the
  anchor to start collecting
- Runs until the next `##` or `#` heading
- Multi-line is fine; lines join with spaces
- Liquid template variables are processed:
  `{{ site.speaker.display_name | default: site.speaker.name }}` is
  the speaker-name pattern used across existing entries

**Abstract section rules — the big gotcha:**

The abstract is one paragraph of flowing prose. Full extraction
mechanics (capture boundary, join + whitespace collapse, what
survives markdownify, what doesn't) live in
[references/parser-contract.md](references/parser-contract.md).
The short-form authoring guidance:

- One paragraph, no sub-headings, no lists, no code blocks, no
  tables — these structures captured by the parser but flattened
  to literal text in the joined output (e.g., `### Subhead`
  becomes `### Subhead` text in the final paragraph; `- item`
  becomes `- item - item` inline)
- `## ` is the section boundary — anything after `## ` belongs to
  the next section, never to the abstract
- Inline marks survive: `**bold**`, `_italic_`, `[link](url)`,
  `` `code` `` all render correctly after the join

**Resources section rules — the contrast:**

- Everything after `## Resources` is passed verbatim to `markdownify`
- Sub-headings (`### Section`) render as sub-headings
- Lists render as lists
- Markdown link formatting renders normally
- Bold/italic in list items renders

Use Resources for structured content; Abstract for the narrative.

Proceed immediately to Step 5.

## Step 5 — "Coming Soon" Patterns: Omit, Don't Placeholder

The layout's conditional rendering for both Slides and Video sections
is driven by truthiness of the extracted field. The ONLY correct way
to express "not yet available" is to **omit the field line entirely**.

### Video — "Video Coming Soon" badge

The template (`talk.html` lines 55-63) checks `page.extracted_video`:

- non-empty → renders the "Video Available" badge + the side-by-side
  `<video-embed>` section
- empty/missing → renders the "Video Coming Soon" badge + no video
  embed

Adding any of the following BREAKS the conditional and shows a wrong
badge plus a broken embed (the embed include tries to use the
placeholder string as a URL):

- `**Video:** TBD`
- `**Video:** [Coming soon](#)`
- `**Video:** [Watch Video](#)`
- `**Video:** [TODO]`
- `**Video:** Coming soon`

### Slides — same pattern, same trap

The slides embed conditional (`talk.html` lines 70-90) renders the
slides section whenever `extracted_slides` is truthy. A placeholder
URL like `[View Slides](#)` makes `extracted_slides` = `#` (truthy)
→ the slides embed section renders, with a broken `#` iframe.

Wrong (commonly attempted, always broken):

- `**Slides:** [View Slides](#)`
- `**Slides:** [View Slides](#) <!-- TODO -->`
- `**Slides:** TBD`
- `**Slides:** Coming soon`

Right when slides aren't ready: **omit the `**Slides:**` line
entirely**. The talk page renders without a slides section until
the line is added.

### Updating a published file when the URL lands

When the actual URL is ready:

1. Open the existing `_talks/{filename_stem}.md`
2. Add (or update) the `**Slides:**` / `**Video:**` line with the
   real markdown-link form: `**Video:** [View Video]({youtube_url})`
3. Place the line in the field block, between
   `**Date:**` and the blank line that separates the field block from
   the "A presentation at..." paragraph
4. Commit + push

The badge and embed section automatically fill in on the next build.

### Don't leave TODO markers in committed files

Inline HTML comments like `<!-- TODO: confirm URL -->` survive in the
file but don't render visibly in the page. They DO pollute the
source, get picked up by greps, and on inline-after-link forms
(`[text](url) <!-- TODO -->`) the parser's value-capture pulls the
comment into `extracted_*` field values. If the work is incomplete,
omit the field; don't commit a TODO placeholder.

Proceed immediately to Step 6.

## Step 6 — Thumbnail

Thumbnails are resolved by the **filename-stem naming convention**,
NOT by frontmatter metadata. The site computes the expected path
from the `.md` filename:

```
/assets/images/thumbnails/{filename_stem}-thumbnail.png
```

where `{filename_stem}` is the talk's `.md` filename minus the
extension — as defined in Step 2 (may include the date prefix
when `talk.delivery_date` is set). Examples (matching the filenames
from Step 2):

| Talk file | Expected thumbnail file |
|-----------|-------------------------|
| `2026-05-07-devoxx-uk-2026-300-tokens.md` | `assets/images/thumbnails/2026-05-07-devoxx-uk-2026-300-tokens-thumbnail.png` |
| `geecon-2026-absolutely-right.md` | `assets/images/thumbnails/geecon-2026-absolutely-right-thumbnail.png` |

This path is hard-coded into three places in the site:

- `index.md` — the homepage "Highlighted Presentations" grid
- `_layouts/default.html` — OpenGraph + Twitter card meta tags
- `_includes/embedded_resource.html` — slides/video thumbnail
  fallbacks inside the talk page

There is NO frontmatter override. Even if you set `thumbnail_url:`
in frontmatter, the templates compute the path from the filename and
ignore your value. The frontmatter field is checked only for
truthiness as a featured-talks inclusion signal, and that's
redundant with `extracted_slides`/`extracted_video`. So:

- Drop the thumbnail file at the conventional path (4:3 aspect ratio,
  PNG; any resolution — the site resizes to 400×300)
- Do NOT set `thumbnail_url:` in frontmatter
- If no thumbnail is provided, the `onerror` fallback in the
  templates swaps in `/assets/images/placeholder-thumbnail.svg` —
  the page still renders correctly, just with a generic placeholder

The thumbnail-generation flow itself lives in the `illustrations`
skill — invoke `Skill(skill: "illustrations")` if a thumbnail needs
to be produced. This skill does not generate images; it just places
them at the right path.

Proceed immediately to Step 7.

## Step 7 — Write the File

Compose the full file content per Steps 3 + 4 + 5 + 6 and write it
to `~/Projects/shownotes/_talks/{filename_stem}.md`.

If a file at that path already exists, this is an UPDATE — typically
the video-add case from Step 5, or a resource refresh. In the update
case:

- Read the existing file first
- Modify only the lines that need to change (e.g., add the
  `**Video:**` line, append a new resource)
- Preserve every other line — comments, source URLs, unrelated
  resources, any speaker-added prose

NEVER overwrite an existing file with a fresh composition unless
the user explicitly requests a full rewrite — speakers often hand-edit
shownotes post-publish (typo fixes, resource additions) and a
re-author wipes those edits.

Proceed immediately to Step 8.

## Step 8 — Validate Locally

Before pushing, validate that the file parses correctly:

```bash
cd ~/Projects/shownotes
bundle exec jekyll build 2>&1 | tail -20
```

A successful build means the file is at least syntactically valid and
the parser didn't error. Open the built page locally to eyeball:

```bash
bundle exec jekyll serve --port 4000 2>&1 &
open "http://localhost:4000/talks/{filename_stem}/"
```

Confirm visually:

- Title renders as the H1 from the body
- Conference + Date + Video badge are correct (Video Available vs
  Video Coming Soon)
- Slides embed shows
- Abstract renders as a single flowing paragraph
- Resources renders as a list (or sub-sectioned if you used
  `### Sub-headings` there)

If a field doesn't render as expected, the parser likely didn't match
the pattern. Re-check Step 4 field-block rules.

Proceed immediately to Step 9.

## Step 9 — Publish

```bash
cd ~/Projects/shownotes
git add _talks/{filename_stem}.md [assets/images/thumbnails/{filename_stem}-thumbnail.png]
git commit -m "Add shownotes: {Talk Title} at {Conference}"
git push
```

After the push, GitHub Pages builds and deploys (~1-2 min). The talk
goes live at:

```
{site.url}/talks/{filename_stem}/
```

where `site.url` is `https://speaking.jbaru.ch` per `_config.yml`,
unless overridden by the speaker's profile.

If a QR code is needed for the live URL, hand off to the
presentation-creator skill's Phase 6 Step 6.2 — that's where the QR
generation lives.

Finish here — the skill is complete.
