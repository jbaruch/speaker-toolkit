---
name: shownotes-publisher
description: >
  Publish a talk page to the Jekyll-based shownotes site (e.g.,
  speaking.jbaru.ch). Composes a markdown file in the site's
  `_talks/` collection so the custom Jekyll parser plugin extracts
  the right fields, the talk.html layout renders correctly, and the
  "Video Coming Soon" badge fires when the recording isn't ready
  yet. Use when the user says "publish shownotes", "create shownotes
  page", "add talk to shownotes", "shownotes for [some talk]",
  "shownotes site", "speaking.jbaru.ch", or asks to update a talk
  page (e.g., "add the video to the shownotes", "the video is out",
  "update shownotes with the recording"). Also trigger for
  first-time publishing before a talk is delivered, when only the
  slides URL exists. The Jekyll site at `~/Projects/shownotes` uses
  a custom markdown parser (`_plugins/markdown_parser.rb`) that
  imposes specific format rules — this skill encodes those rules so
  the agent doesn't author content that silently fails to render.
user-invocable: true
---

# Shownotes Publisher

Process steps in order. Do not skip ahead. This skill writes a
markdown file into the Jekyll shownotes site's `_talks/` collection
where a custom parser plugin (`_plugins/markdown_parser.rb` in the
target site) extracts structured fields by pattern matching on the
body. The format is strict — small mistakes silently flatten
content or break conditional rendering.

Reference files in this skill:
[references/parser-contract.md](references/parser-contract.md) —
extraction grammar per `extracted_*` field;
[references/template-conditionals.md](references/template-conditionals.md) —
how `talk.html` renders each field;
[references/common-mistakes.md](references/common-mistakes.md) —
13 failure modes with the right way.

Default target: `~/Projects/shownotes` (deployed at
`https://speaking.jbaru.ch`).

## Step 1 — Gather Context Automatically; Ask Only for the Slides URL

Everything the shownotes page needs is already in the talk's
artifacts by the time this skill runs. Do not ask the user to
re-supply anything that is derivable. Read automatically:

**From `outline.yaml` — the talk's presentation spec.** Load via
the schema script's JSON emit mode:

```bash
python3 skills/presentation-creator/scripts/outline_schema.py \
    --emit-json <path-to-outline.yaml>
```

Script contract:

- Input: path to `outline.yaml` as a single positional argument
- Stdout (exit 0): JSON of the validated `Outline` model
- Stderr (exit 1): `FAIL: ...` — abort and surface the failure

Parse the JSON, never re-parse YAML by hand. Map fields directly:

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
- Any existing `_talks/` page for this talk — check `{talk_slug}.md`
  first, then a legacy `{YYYY-MM-DD}-{talk_slug}.md` (older
  date-prefix convention) — if this is an update (not a first
  publish), read it first so Step 7 preserves hand-edits. The
  filename that exists becomes `{talk_page_stem}` (defined in Step 2)

**Ask the user EXACTLY one question — the slides PDF embed URL**
(Google Drive `https://drive.google.com/file/d/.../preview` form).
That's the only value not in any file — the speaker just uploaded
the deck. Don't ask about Video; URLs arrive post-recording, and
omitting the line is what fires the "Video Coming Soon" badge
(Step 5). If the user volunteers a video URL in the same turn,
capture it.

Ask follow-ups ONLY on ambiguity:

- outline.yaml absent or invalid → STOP, invoke
  `Skill(skill: "presentation-creator")` to repair, then resume
- `talk.thesis` empty → ask the speaker for a one-paragraph
  abstract (Step 4 rules apply)
- `talk.delivery_date` missing → confirm whether the talk has
  happened (pre-talk publish is fine; the date only feeds the body's
  `**Date:**` line in Step 4, not the filename)
- Existing `_talks/` page (either `{talk_slug}.md` or a legacy
  `{YYYY-MM-DD}-{talk_slug}.md`) exists AND speaker didn't flag
  this as an update → ask before overwriting (Step 7)

Proceed immediately to Step 2.

## Step 2 — Compose Filename

The talk slug `{talk_slug}` is `outline.yaml::talk.slug` — the spec
is the only source. Already kebab-case validated by `outline_schema.py`.
Never invent it, never derive it from the venue or title, never
rephrase.

For a NEW talk, the filename in `_talks/` is always `{talk_slug}.md`
(e.g., `geecon-2026-absolutely-right.md`). No date prefix —
`talk.slug` is the single source of truth for both the filename and
the live URL, and already carries any year qualifier the speaker
chose. A date in the URL belongs *in* the slug, never bolted on by
the publisher.

`{talk_page_stem}` is the published page's filename without `.md` —
the value Steps 5–9 use for every file path, thumbnail path, preview
URL, branch name, and live-URL check:

- New talk, or a talk already published at `{talk_slug}.md` →
  `{talk_page_stem}` = `{talk_slug}`; full path
  `~/Projects/shownotes/_talks/{talk_slug}.md`.
- Updating a talk already published at a legacy
  `{YYYY-MM-DD}-{talk_slug}.md` (older date-prefix convention) →
  `{talk_page_stem}` = that existing date-prefixed stem. Keep the
  filename unchanged; never rename a published talk — renaming breaks
  the live URL and any QR codes printed against it.

Proceed immediately to Step 3.

## Step 3 — Compose Frontmatter

Minimum (and maximum) frontmatter:

```yaml
---
layout: talk
---
```

The Jekyll plugin auto-inserts this if absent; write it explicitly
for portability. Do NOT add `title:`, `video:`, `slides:`,
`conference:`, `date:`, `description:`, `abstract:`, or
`thumbnail_url:` — every one of these is either extracted from the
body, ignored by the templates, or duplicates content (see
[references/common-mistakes.md](references/common-mistakes.md)
entries 1c and 5 for the failure modes).

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

**Authoring rules (full grammar in
[references/parser-contract.md](references/parser-contract.md)):**

- Field-block lines: `**FieldName:** value`, one per line. URLs
  wrapped as `[text](url)` — bare URLs don't populate the
  `extracted_*` fields. Date in ISO `YYYY-MM-DD`
- Omit a field line entirely when its value is missing — empty
  values fail to parse and `**Field:** TBD` fires the wrong state
  (covered in Step 5)
- Presentation-context paragraph starts with `A presentation at`
  (the parser anchor) and runs to the next `##` heading
- Abstract is exactly one paragraph — the parser joins all lines
  with spaces and collapses whitespace before `markdownify`, so
  any sub-headings / lists / code blocks inside flatten to literal
  text
- Resources is passed verbatim to `markdownify` — sub-headings,
  lists, and formatting all render

Proceed immediately to Step 5.

## Step 5 — "Coming Soon" Patterns: Omit, Don't Placeholder

`talk.html`'s conditional rendering keys off truthiness of
`extracted_slides` and `extracted_video`. Any non-empty value flips
the badge to "Available" and the embed include tries to load the
value as a URL — so placeholder strings always produce the wrong
badge plus a broken iframe. The only correct way to express "not
yet available" is to **omit the field line entirely**.

Common placeholder shapes and what they break are enumerated in
[references/common-mistakes.md](references/common-mistakes.md)
entries 1 (Video) and 1b (Slides). The fix in every case: omit the
line; add it when the real URL lands.

**Updating a published file when the URL lands:**

1. Open the existing `_talks/{talk_page_stem}.md` (read-then-edit
   per Step 7's preservation rule)
2. Add the `**Slides:**` or `**Video:**` line in real markdown-link
   form, placed inside the field block (between `**Date:**` and the
   blank line before the `A presentation at...` paragraph)
3. Commit + publish via Step 9's flow

The badge and embed automatically fill in on the next build.

Never commit `<!-- TODO -->` HTML comments — inline comments after
a link line are captured by the parser's value group and pollute
`extracted_*` values. Tracking for incomplete work belongs in a PR
description or an issue, not the committed file.

Proceed immediately to Step 6.

## Step 6 — Thumbnail

Thumbnails are resolved by **filename naming convention** — the
site's templates compute the path from the `.md` filename:

```
/assets/images/thumbnails/{talk_page_stem}-thumbnail.png
```

Example (new talk, stem = slug): `geecon-2026-absolutely-right.md` →
`assets/images/thumbnails/geecon-2026-absolutely-right-thumbnail.png`.

Drop the thumbnail file (4:3 PNG; the site resizes to 400×300) at
that path. Do NOT set `thumbnail_url:` in frontmatter — it's
checked only for truthiness as a featured-talks signal and never
read as a URL; see
[references/common-mistakes.md](references/common-mistakes.md)
entry 1c and
[references/template-conditionals.md](references/template-conditionals.md)
for the three template locations that hard-code the slug-derived
path.

**Decide explicitly — do not skip this step.** Check whether the
convention-path file already exists in the shownotes repo
(`assets/images/thumbnails/{talk_page_stem}-thumbnail.png`):

- **Exists** → done; the page uses it.
- **Absent, and a source image is available** (the talk's slides
  exist, or a YouTube thumbnail / video frame was already produced) →
  produce it now: hand off to `Skill(skill: "illustrations")` to
  generate the thumbnail (this skill places files, it does not generate
  images), then drop the 4:3 PNG at the convention path.
- **Absent, and no source image yet** (pre-talk publish, no slides or
  video) → record that the thumbnail is deferred to Phase 7
  (post-event). The placeholder SVG (`onerror` fallback) is the
  intentional interim, not a silent skip; when the video lands and
  Phase 7 runs, generate the thumbnail and drop it at the convention
  path.

Never fall through this step without either producing the thumbnail or
explicitly recording the deferral. Then proceed to Step 7.

## Step 7 — Write the File

Compose the full file content per Steps 3 + 4 + 5 + 6 and write it
to `~/Projects/shownotes/_talks/{talk_page_stem}.md`.

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

Before pushing, validate the file parses cleanly. The subshell +
`pipefail` is required — without it, `tail`'s successful exit masks
a failing `jekyll build`:

```bash
cd ~/Projects/shownotes
( set -o pipefail && bundle exec jekyll build 2>&1 | tail -20 ) \
  || { echo "Build failed — fix per Step 4 and re-run"; exit 1; }
```

The `|| { ...; exit 1; }` guard makes the build a hard gate: a
non-zero exit aborts before any of the visual-check commands run.
Only after the build is green, open the rendered page locally:

```bash
bundle exec jekyll serve --port 4000 2>&1 &
open "http://localhost:4000/talks/{talk_page_stem}/"
```

Visually confirm: title, conference + date + correct video badge
(Available vs Coming Soon), slides embed, single-paragraph
abstract, resources list. If a field doesn't render, the parser
didn't match — re-check Step 4 rules.

Proceed immediately to Step 9.

## Step 9 — Publish

**Default flow — branch + PR.** Required under
`jbaruch/coding-policy: ci-safety` unless the target repo has the
Content-Only Direct-Push Carve-Out wired (authority-of-record rule
+ server-side path enforcement on `_talks/**` /
`assets/images/thumbnails/**` — see that rule for full
preconditions).

```bash
cd ~/Projects/shownotes
git checkout -b shownotes/{talk_page_stem}
git add _talks/{talk_page_stem}.md [assets/images/thumbnails/{talk_page_stem}-thumbnail.png]
git commit -m "Add shownotes: {Talk Title} at {Conference}"
git push -u origin shownotes/{talk_page_stem}
gh pr create --fill
gh pr checks --watch --fail-fast
# After merge, watch the Pages deployment and confirm 200:
gh run watch --exit-status $(gh run list --workflow=pages-build-deployment --branch=main --limit=1 --json databaseId --jq '.[0].databaseId')
curl -fsI "{site.url}/talks/{talk_page_stem}/" | head -1   # expect: HTTP/2 200
```

**Direct-push (carve-out wired AND changes touch only carve-out
paths):**

```bash
cd ~/Projects/shownotes
git add _talks/{talk_page_stem}.md [assets/images/thumbnails/{talk_page_stem}-thumbnail.png]
git commit -m "Add shownotes: {Talk Title} at {Conference}"
git push
gh run watch --exit-status $(gh run list --workflow=pages-build-deployment --branch=main --limit=1 --json databaseId --jq '.[0].databaseId')
curl -fsI "{site.url}/talks/{talk_page_stem}/" | head -1   # expect: HTTP/2 200
```

The carve-out bypasses the PR cycle but NOT the CI/deploy watch —
`ci-safety` requires both the run conclusion and the 200 to confirm
the publish landed. If the carve-out status is unknown, default to
the branch + PR flow.

If a QR code is needed for the live URL, hand off via
`Skill(skill: "presentation-creator")` — the QR generation flow
lives in that skill's Phase 6 Step 6.2.

Finish here — the skill is complete.
