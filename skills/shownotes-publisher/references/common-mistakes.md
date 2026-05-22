# Common Mistakes — What NOT to Do

A curated list of failure modes specific to the shownotes Jekyll
pipeline. Each entry: the mistake, what visually happens, and the
right way.

## 1. Adding a Video URL Before the Recording Is Published

**Don't:**
```markdown
**Video:** TBD
**Video:** [Coming soon](#)
**Video:** [TODO]
**Video:** Recording coming soon
```

**What happens:** Any non-empty `extracted_video` value fires the
"Video Available" badge. The "Video Coming Soon" badge that the
speaker actually wants never renders. The video-embed section then
tries to embed "TBD" as a URL, producing a broken iframe.

**Do:** Omit the `**Video:**` line entirely. When the video lands,
add the line. The badge automatically flips on rebuild.

## 1b. Adding a Slides Placeholder URL — Same Trap, Different Field

**Don't:**
```markdown
**Slides:** [View Slides](#)
**Slides:** [View Slides](#) <!-- TODO -->
**Slides:** TBD
```

**What happens:** Identical to the Video gotcha — `extracted_slides`
becomes `#` (truthy), the layout's media section renders, and the
slides embed tries to load `#` as a URL. The page shows a broken
iframe inside the "Slides" panel.

**Do:** Omit the `**Slides:**` line entirely until you have a real
URL. The talk page is fully valid without a slides section. When
the URL lands, add the line — no other change needed.

## 1c. `thumbnail_url:` in Frontmatter

**Don't:**
```yaml
---
layout: talk
thumbnail_url: /assets/images/thumbnails/my-talk-thumbnail.png
---
```

**What happens:** Nothing useful. Thumbnails are resolved entirely
by the filename-slug naming convention (`/assets/images/thumbnails/{slug}-thumbnail.png`)
in `index.md`, `_layouts/default.html`, and
`_includes/embedded_resource.html`. The frontmatter field is checked
only as a truthiness signal for the homepage's "Highlighted
Presentations" inclusion filter (`index.md:104`), and that's
redundant with `extracted_slides`/`extracted_video` — both of which
are already populated from the body field block on any normal talk.

The field misleads a reader into thinking they can override the
thumbnail path. They can't. Setting it to a non-existent path
doesn't make a thumbnail appear; setting it to a different path
doesn't change which file the templates load.

**Do:** Skip the frontmatter field. Drop the thumbnail file at the
conventional path (`{slug}-thumbnail.png`). The templates find it
automatically; missing thumbnails fall back via `onerror` handler
to `/assets/images/placeholder-thumbnail.svg`.

## 2. Treating the Abstract as a Multi-Paragraph Section

**Don't:**
```markdown
## Abstract

This is the first paragraph of the abstract.

This is the second paragraph.

### Sub-section in Abstract

This is a third paragraph under a sub-heading.

- Bullet one
- Bullet two
```

**What happens:** Everything between `## Abstract` and the next `##`
heading gets joined into ONE STRING with whitespace collapsed.
Sub-headings and lists become run-on text:

> "This is the first paragraph of the abstract. This is the second
> paragraph. ### Sub-section in Abstract This is a third paragraph
> under a sub-heading. - Bullet one - Bullet two"

After markdownify, the `###` and `-` characters mostly survive as
literal text (markdownify on a single line doesn't reconstruct
headings or lists).

**Do:** One paragraph of flowing prose. If the talk has multiple
movements to describe, write a single dense paragraph that walks them
in sequence. Save the structured outline for the talk itself; the
abstract is the elevator pitch.

## 3. Slides or Video URL Without Markdown Link Syntax

**Don't:**
```markdown
**Slides:** https://drive.google.com/file/d/abc123/preview
**Video:** https://youtu.be/abc123
```

**What happens:** The parser's URL extraction regex
`\[([^\]]+)\]\(([^)]+)\)` doesn't match — it expects the
`[text](url)` form. The full plain-text value ends up in
`extracted_slides` / `extracted_video`. The status badge fires
(string is truthy), but the embed include then tries to detect URL
patterns inside the plain string. It often "works" for YouTube — the
`youtu.be/` or `youtube.com/watch?v=` substrings still trigger the
embed branch. For Google Drive PDFs the pattern match is less
forgiving.

**Do:** Always wrap in markdown link syntax:
```markdown
**Slides:** [View Slides](https://drive.google.com/file/d/abc123/preview)
**Video:** [View Video](https://youtu.be/abc123)
```

## 4. Multiple H1s in the Body

**Don't:**
```markdown
# Talk Title

…field block…

# Section One

Body for section one…

# Section Two

Body for section two…
```

**What happens:** Only the first `# ` line becomes
`extracted_title`. The subsequent H1s render as H1s in the body —
the layout's CSS sizes them as H1, which looks visually odd
(two title-sized headings on one talk page).

**Do:** One H1 (the talk title). Use `## ` for second-level
headings — but only `## Abstract` and `## Resources` are
parser-aware sections. Other `## Headings` render but aren't
extracted; they appear as body content between the field block and
the abstract OR after the Resources section.

## 5. Frontmatter Title

**Don't:**
```yaml
---
layout: talk
title: My Talk Title
---

# My Talk Title

…
```

**What happens:** The layout uses `extracted_title` as the visible
H1. The frontmatter `title:` overrides only the page title in some
rendering paths. The body H1 still renders. End result: title
appears once at the top (from the layout's H1 emission of
extracted_title) but the body `# My Talk Title` also renders below
the field block, producing duplication.

Worse: if you omit the body H1 thinking the frontmatter title
suffices, the parser's `extract_title_from_content` falls through to
"Untitled Talk" — and the LAYOUT's display logic compares
`extracted_title` against `page.title` to decide whether to humanize
the slug. The conditionals don't agree, and the page is broken in
subtle ways.

**Do:** Put the title in a `# Title` H1 at the top of the body. Skip
the frontmatter title field.

## 6. Resources Before Abstract

**Don't:**
```markdown
## Resources

- [link](https://example.org)

## Abstract

Prose.
```

**What happens:** The parser collects abstract from `## Abstract`
until the next `## ` heading. If Resources comes BEFORE Abstract,
Resources isn't reached by the abstract scanner (it stops at the
boundary, which here is end-of-file or another section). But the
Resources scanner finds `## Resources` and captures everything
after it — including the `## Abstract` line and its body. So:

- `extracted_abstract` = "Prose." ✓ (this works)
- `extracted_resources` = "- [link](https://example.org) ## Abstract Prose." ✗
  (Abstract content is folded into Resources)

**Do:** Order sections Abstract first, Resources last. Parser
behavior is sequential — Resources captures to end-of-file.

## 7. Abstract Below a Non-Field Block of Prose

**Don't:**
```markdown
# Talk Title

**Conference:** Foo 2026
**Date:** 2026-01-01

This is a personal note I want at the top of the page.

A presentation at Foo 2026 by {{ site.speaker.name }}

## Abstract

Prose.
```

**What happens:** The "personal note" line is captured by the
abstract's legacy fallback IF there's no `## Abstract` section, OR
ignored otherwise. With `## Abstract` present, this note line just
renders as body text between the field block and the presentation
context — invisible markdown structure but it does show up in the
final HTML.

The presentation context parser specifically looks for "A
presentation at" as the start marker — so the note above is fine
visually if you want it. Just be aware it's not "metadata"; it's
body text rendered as-is.

**Do:** If you want a pre-abstract callout, use it deliberately and
preview the rendered page. Most authors skip this and go
field-block → presentation-context → abstract → resources.

## 8. Subtitle Field

**Don't expect:**
```markdown
**Subtitle:** Engineering Context for Agentic AI
```

**What happens:** The parser doesn't extract Subtitle — it's not in
the metadata-field whitelist. The layout doesn't render a subtitle
either. The line shows up as inline body text after the field block,
which looks awkward.

**Do:** If a subtitle matters for the talk identity, embed it in the
H1 (`# Talk Title — Subtitle Here`) or in the first sentence of the
abstract. Don't author a Subtitle field expecting it to render
separately.

## 9. Co-speaker Field

Same as Subtitle. There's no parser support for `**Co-speaker:**` —
it renders as plain body text. The presentation context paragraph is
where co-speakers go: "by {{ site.speaker.name }} and Co-Name".

## 10. Editing a Pushed Talk by Re-Generating from Scratch

**Don't:** Open the existing file, read it, then write a fresh
composition with the "improved" version.

**What happens:** Speakers regularly hand-edit shownotes after
publish — typo fixes, resource additions, link updates. A
re-author wipes those edits silently. The talk page reverts to
whatever the generator's mental model was at write-time, which may
be days behind.

**Do:** Read the existing file. Modify only the lines that need to
change (typically: adding the `**Video:**` line when the recording
lands, appending a new resource link). Preserve everything else.

If a major rewrite IS warranted, explicitly tell the speaker the
existing file will be overwritten and confirm before proceeding.

## 11. Committing `<!-- TODO -->` Markers in Published Content

**Don't:**
```markdown
<!-- TODO: confirm slide/video URLs + generate thumbnail before publish -->
# Talk Title

**Slides:** [View Slides](#) <!-- TODO -->
**Video:** [Watch Video](#) <!-- TODO -->
```

**What happens:**

1. HTML comments at the top of the file survive into the rendered
   HTML (browsers strip them from display but they're in the source
   — anyone viewing source sees the TODO). It's a "publish anyway,
   fix later" pattern that often fails to get fixed
2. The inline `<!-- TODO -->` after the markdown link is captured
   by the parser's value group (`^\*\*Slides:\*\*\s*(.+)$` matches
   to end-of-line) — `extracted_slides` ends up containing the
   comment text in addition to the link. The URL extraction regex
   still finds `#` in the bracket-paren form, but the wider value
   pollutes debug output
3. Reviewers see the file looks "ready" — it has Slides/Video
   lines — then it ships with `#` placeholders intact

**Do:** If the work is incomplete, omit the incomplete fields. The
talk page renders fine without Slides or Video sections. When the
URLs land, add the lines with real values — no comment markers.

For tracking incomplete work, use a checklist in a PR description
or an issue, not a comment in the committed file. Speakers can grep
the repo for `TODO` if needed, but committed `<!-- TODO -->` in
published files inevitably stays there.
