# Parser Contract — What the Jekyll Plugin Extracts

The custom Jekyll plugin at `~/Projects/shownotes/_plugins/markdown_parser.rb`
scans each `_talks/*.md` file at site-init time and populates a set of
`extracted_*` fields on the Jekyll document. The talk.html layout
consumes those fields. This file is the line-by-line contract.

## Auto-frontmatter Injection

If a `_talks/*.md` file does not start with `---`, the plugin's
`after_init` hook prepends:

```yaml
---
layout: talk
---
```

This means a talk file CAN technically be markdown-only with no
frontmatter — the plugin will fix it on first run by writing back to
disk. But this overwrites the file, so always commit the frontmatter
explicitly to avoid surprise edits in git status.

## extracted_title

- Source: first line in the body starting with `# ` (single hash +
  single space)
- Empty H1 → `"Untitled Talk"`
- No H1 → `"Untitled Talk"`
- Frontmatter `title:` overrides only if explicitly set in the
  frontmatter (the parser checks the raw file for `^title:`)
- The layout uses `extracted_title` as the visible page title AND in
  the `<title>` tag AND in the JSON-LD `name` field

## extracted_conference, extracted_date

- Pattern: `^\*\*Conference:\*\*\s*(.+)$` (case-insensitive on the
  field name), same for `Date`
- Match is on a LINE — the field must be on its own line, not inline
- Value is the trimmed string after the colon
- If value contains `[text](url)`, the URL is returned (relevant for
  Slides/Video, not typically Conference/Date)
- Date layout filter expects YYYY-MM-DD; other formats partially
  parse and render unpredictably

## extracted_slides, extracted_video

- Same `**Field:** value` pattern
- The URL extraction is critical: the regex captures the URL from
  `[link text](url)` syntax via `\[([^\]]+)\]\(([^)]+)\)` — `$2` is
  the URL
- Plain text URL (`**Video:** https://youtube.com/watch?v=…`) — the
  parser returns the full plain text, NOT just the URL. The
  `embedded_resource.html` include then tries to match patterns like
  `contains "youtube.com/watch?v="`, which DOES still work for some
  URLs, but the markdown link form is the documented contract
- Absence of the entire line → field is `nil` → the layout's
  conditional `{% if page.extracted_video %}` falls through to the
  "Video Coming Soon" badge

## extracted_abstract

Captured from the `## Abstract` section:

- Collection starts on the line after `## Abstract`
- Collection stops at the next `## ` heading (including `## Resources`)
- Empty lines within the abstract are collected as `''` in the buffer
- The buffer is joined with `' '` then run through `gsub(/\s+/, ' ').strip`
- Final value is ONE STRING with no line breaks, no markdown
  structure beyond inline `**bold**`, `_italic_`, `[link](url)`,
  backticks for `\`code\``
- This string is then passed through `markdownify` in the layout
- Sub-headings (`### Subhead`) inside abstract are folded into prose
- Lists (`- item`) flatten to `- item - item - item` literal text
- Code blocks flatten (backticks survive, fences become text)
- Tables flatten

The legacy fallback parser (`extract_abstract_legacy`) runs only when
the `## Abstract` section is absent — it tries to find content after
the "A presentation at" line. The modern format always uses the
explicit section.

## extracted_resources

Captured from the `## Resources` section:

- Collection starts on the line AFTER `## Resources`
- Collection runs to the end of the file (no closing terminator)
- The captured text is joined with `\n` (newlines preserved)
- Passed through `markdownify` verbatim — full markdown supported:
  - Sub-headings (`### Sub-section`)
  - Lists (bullet, numbered)
  - Bold/italic
  - Markdown links
  - Code blocks
  - Tables

In contrast to abstract, Resources is the place to use structured
markdown.

## extracted_presentation_context

Captured starting from a line that begins with `A presentation at`:

- Collection starts on the matching line itself (it's included in
  the captured text)
- Collection runs until a `##` or `#` heading OR the first empty line
  AFTER content has been collected
- Lines are joined with `' '` (spaces) — multi-line is fine
- The joined string is passed through `Liquid::Template.parse` and
  rendered with the site's `site_payload` — supports liquid
  template variables like `{{ site.speaker.display_name | default:
  site.speaker.name }}`
- On liquid parse error, falls back to the raw concatenated string

This is the convention you see across existing entries:

```
A presentation at GeeCON in
                    May 2026 in
                    Kraków, Poland by
                    {{ site.speaker.display_name | default: site.speaker.name }}
```

## Fallback Behavior

If the plugin throws an exception on any field extraction, it sets
sane defaults to prevent template errors:

- `extracted_title ||= page.title || 'Untitled Talk'`
- `extracted_conference ||= 'Unknown Conference'`
- All `extracted_*` text fields default to `''`

So a malformed file will at least render — but every missing field
degrades the page. Don't rely on the fallback; structure the file
correctly.

## What the Plugin Does NOT Extract

Fields present in some files but ignored by the parser:

- `**Subtitle:**` — used in some recent talks (e.g.,
  geecon-2026-absolutely-right.md) but not captured into any
  `extracted_*` field. Will render as inline body text after the H1
  if the parser doesn't strip it (it doesn't — the metadata-skipping
  legacy path applies only when there's no `## Abstract`). The
  current layout doesn't surface a subtitle anywhere
- `**Co-speaker:**` — same as Subtitle; not extracted, not rendered
  by the layout
- HTML comments like `<!-- Source: … -->` — preserved in the file
  body but never rendered (they're HTML comments)

If you need a field that the parser doesn't extract today, propose
the change at the parser level — don't paper over it in the template.
