# Shownotes Coordination

Read `publishing_process.shownotes`. If `enabled`:

For the Jekyll shownotes site with `_plugins/markdown_parser.rb`, invoke
`Skill(skill: "shownotes-publisher")` with the talk directory, configured
site path, and supplied slides URL. It owns the page and the downloadable
skill distilled from the talk, validation, and publishing. Resume below at
live URL verification and tracking persistence after it completes. Do not
bypass that flow with a page-only push. A pre-talk publish uses substantive
notes and demos; it does not wait for a recording.

For other shownotes systems, follow the page flow below and inspect their
skill publishing contract before promising a downloadable skill. Do not
assume Jekyll's `_skills/` convention works on another SSG.

- Generate the talk page at
  `{shownotes.source.path_or_url}/{shownotes.source.talks_subdir}/{slug}.md`
  (adapt the extension for Hugo/Astro content collections if the SSG uses a
  different convention — check `shownotes.source.type` and existing entries).
- Follow the `publishing_method` description (git push, CMS, manual) to make
  it live.
- If `shownotes.shownotes_template` is provided, use it as the frontmatter /
  layout skeleton for the new page. Otherwise follow the convention observed
  in existing entries under the talks subdir.
- Include: title, abstract, slide embed/download link, speaker bio.
- If `resources.json` exists and has `approved: true` items, include a
  "Resources" section with those links. Read from `resources.json` in the
  talk working directory (produced by resource curation) — do not re-scan the outline.

**Construct the live shownotes URL** by composing `shownotes.url.base` + the
result of substituting the Presentation Spec's slug (and other variables, if
the template uses them) into `shownotes.url.template`. The slug was agreed
with the author in Phase 1 — NEVER invent or rephrase it.

Template variables supported:
- `{slug}` — talk slug from Presentation Spec
- `{yyyy}`, `{mm}`, `{dd}` — 4- and 2-digit date components from the talk
  frontmatter `date` field
- `{yy}` — 2-digit year
- `{venue}` — slugified venue name

Examples:

| `shownotes.url.base` | `shownotes.url.template` | slug | Resulting URL |
|---|---|---|---|
| `https://speaking.example.com` | `/{slug}/` | `arc-of-ai` | `https://speaking.example.com/arc-of-ai/` |
| `https://speaker.dev` | `/talks/{slug}/` | `arc-of-ai` | `https://speaker.dev/talks/arc-of-ai/` |
| `https://example.com` | `/{yyyy}-{mm}-{dd}-{slug}/` | `jfokus-robocoders` | `https://example.com/2026-04-16-jfokus-robocoders/` |

If the SSG uses per-file `permalink:` frontmatter (common in Eleventy), read
the permalink from the newly-generated page's frontmatter rather than
synthesizing from `url.template`. In that case `shownotes.url.template` may
be null.

Before passing the URL downstream (QR code, bit.ly target, post-event video
description), verify the URL is reachable — a 404 on the deployed site
breaks printed QR codes with no recovery path.

After the page is live and verified, persist `shownotes_url` and
`shownotes_published: true` on the matching talk with one
`update_talk_publishing` mutation. Its `expect` object must cover those same
fields with their exact values from the latest strict read. Apply it through the
[owner mutation contract](../../vault-ingress/references/schemas-db.md#owner-read-and-mutation-contract),
never by rewriting the database.

If not enabled, skip.
