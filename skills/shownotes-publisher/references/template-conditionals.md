# Template Conditionals — What `talk.html` Renders

`~/Projects/shownotes/_layouts/talk.html` is the talk page layout. It
reads the `extracted_*` fields the parser populates and decides what
to render. This file maps each conditional to the source field that
controls it, so an author knows exactly which extracted field they
need to populate (or leave empty) to produce a given visual outcome.

## Title Block

```liquid
{% assign display_title = page.extracted_title | default: page.title %}
{% if page.extracted_title %}
<h1 class="talk-title">{{ display_title }}</h1>
{% else %}
<h1 class="talk-title">{{ display_title | replace: "-", " " | capitalize }}</h1>
{% endif %}
```

- If `extracted_title` is set → renders the H1 as-is
- Else falls back to humanizing the slugified filename (replaces
  dashes with spaces and capitalizes)

The fallback is the parser's safety net — but never relying on it
means: always include `# {Talk Title}` as the first H1 in the body.

## Conference Name

```liquid
{% if page.extracted_conference %}
  <span class="meta-item conference-name">{{ page.extracted_conference }}</span>
{% elsif page.conference %}
  <span class="meta-item conference-name">{{ page.conference }}</span>
{% endif %}
```

- `extracted_conference` from the body's `**Conference:** value` line
  is preferred
- Frontmatter `conference:` is a legacy fallback the layout supports
  but the parser doesn't populate
- If neither is set, no conference name renders

## Date

Same pattern as conference: `extracted_date` from body, then frontmatter
`date:`, then nothing. The layout applies `date_to_xmlschema` and
formats with `%B %d, %Y` — so an ISO YYYY-MM-DD value renders as
"May 14, 2026".

## Video Status Badge — the conditional that matters most

```liquid
{% if page.extracted_video %}
<span class="meta-item status-badge video-published">Video Available</span>
{% else %}
<span class="meta-item status-badge video-pending">Video Coming Soon</span>
{% endif %}
```

This is the source of the "don't add video until it's available"
rule. Three states:

| Body has `**Video:**` line? | `extracted_video` | Badge | Video embed renders? |
|---|---|---|---|
| Absent | `nil` (falsy) | "Video Coming Soon" | No |
| Present with valid URL | URL string (truthy) | "Video Available" | Yes |
| Present with bare-text placeholder (`TBD`, `Coming soon`) | the text string (still truthy) | "Video Available" | Yes — but the embed will be broken because no valid URL was extracted |

The "Video Available" badge fires on ANY truthy `extracted_video` —
the layout doesn't validate that the value is a real URL. A
placeholder like `**Video:** TBD` will mark the talk "Available" and
attempt to embed `TBD` as a video. Both wrong.

The only correct way to express "video not yet available" is to
**omit the line entirely**.

## Media Section (Slides + Video Embeds)

```liquid
{% if page.extracted_slides or page.extracted_video %}
<section class="talk-main-content">
  <div class="media-container">
    {% if page.extracted_slides %}<div class="media-item slides-embed">…</div>{% endif %}
    {% if page.extracted_video %}<div class="media-item video-embed">…</div>{% endif %}
  </div>
</section>
{% endif %}
```

- If neither slides nor video is set → no media section renders
- If only slides → just slides (typical for pre-talk publish)
- If only video → just video (rare; usually means slides URL is broken)
- Both → side-by-side embed

The embed itself is handled by `_includes/embedded_resource.html`,
which pattern-matches the URL to decide the embed format:

- `docs.google.com/presentation/d/` → Google Slides iframe
- `drive.google.com/file/d/` → Google Drive PDF preview (with
  fallback when blocked by content extensions)
- `youtube.com/watch?v=` or `youtu.be/` → YouTube iframe

A URL that doesn't match any pattern produces a broken embed. Use the
documented forms: Google Drive `/preview` for slides PDFs, full
YouTube watch URLs for videos.

## Abstract

```liquid
{% if page.extracted_abstract %}
<div class="talk-abstract">
  <h2>Abstract</h2>
  {{ page.extracted_abstract | markdownify }}
</div>
{% endif %}
```

Markdownified at the very end. By the time `markdownify` runs, the
extracted_abstract value is ONE STRING — the parser already joined
lines with spaces. So markdown structure that depends on line breaks
(headings, lists, code blocks) is gone before markdownify sees it.

This is why "abstract is one paragraph" is the strict rule.

## Resources

```liquid
{% if page.extracted_resources and page.extracted_resources != "" %}
<div class="talk-resources">
  <h2>Resources</h2>
  <div class="resources-list">{{ page.extracted_resources | markdownify }}</div>
</div>
{% endif %}
```

Markdownified verbatim — line breaks preserved. Full markdown works
here.

## Presentation Context

```liquid
{% if page.extracted_presentation_context %}
<div class="talk-presentation-context">
  {{ page.extracted_presentation_context }}
</div>
{% endif %}
```

NOT markdownified — rendered as-is. The parser has already processed
liquid template variables (e.g., the speaker name interpolation), so
the output is plain text with whatever HTML the source contained.
Don't include markdown syntax expecting it to render.

## Thumbnail Resolution — Filename Convention, Not Frontmatter

Thumbnails are NOT controlled by frontmatter. The path is computed
from the talk's `.md` filename in three independent places:

**`index.md` (Highlighted Presentations grid):**

```liquid
{% assign talk_slug = talk.path | split: '/' | last | replace: '.md', '' %}
{% assign thumbnail_path = '/assets/images/thumbnails/' | append: talk_slug | append: '-thumbnail.png' %}
```

**`_layouts/default.html` (OG + Twitter card meta tags):**

```liquid
<meta property="og:image" content="{{ '/assets/images/thumbnails/' | append: talk_slug | append: '-thumbnail.png' | absolute_url }}">
<meta name="twitter:image" content="{{ '/assets/images/thumbnails/' | append: talk_slug | append: '-thumbnail.png' | absolute_url }}">
```

**`_includes/embedded_resource.html` (slides/video preview thumbs):**

```liquid
{% assign local_thumbnail_path = "/assets/images/thumbnails/" | append: talk_slug | append: "-thumbnail.png" %}
{% assign thumb_url = local_thumbnail_path | relative_url %}
```

All three derive `{slug}` from the `.md` filename, append
`-thumbnail.png`, and prefix `/assets/images/thumbnails/`. No
frontmatter field — `thumbnail_url:` or otherwise — overrides this.

### What `thumbnail_url:` in frontmatter actually does

Exactly one thing: `index.md:104` checks
`{% if talk.extracted_slides or talk.extracted_video or talk.thumbnail_url %}`
to decide whether to include the talk in the homepage's
"Highlighted Presentations" featured set. The check is for
truthiness only — the value is never read for a URL. And the check is
redundant in practice because `extracted_slides` is almost always
populated for any talk that has a slides URL in the body, so the
frontmatter field rarely affects the outcome.

Setting `thumbnail_url:` to a non-existent path doesn't make it
exist; setting it to a different path doesn't override the
slug-derived path; omitting it doesn't disable the thumbnail.

### Missing-thumbnail fallback

Every `<img>` tag that points to the slug-derived thumbnail has an
`onerror` handler that swaps in the placeholder SVG:

```html
<img src="{{ thumb_url }}" ...
     data-fallback="{{ placeholder_url }}"
     onerror="this.onerror=null;this.src=this.dataset.fallback;">
```

So a talk without a thumbnail file at the conventional path still
renders the page correctly — the browser fires `onerror` on the 404
and substitutes `/assets/images/placeholder-thumbnail.svg`.

## Structured Data (JSON-LD)

The layout emits a JSON-LD `PresentationDigitalDocument` block using:

- `name`: `extracted_title` (or `page.title` fallback)
- `author.name`: `site.speaker.display_name` (or `site.speaker.name`)
- `publisher.name`: `extracted_conference`
- `datePublished`: `extracted_date`
- `description`: `extracted_abstract` (when set)
- `url`: absolute URL of the page

These are all derived — no extra authoring step needed. If a field
is missing, the JSON-LD entry for it is missing too, which degrades
SEO but doesn't break the page.
