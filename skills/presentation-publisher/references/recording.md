# Recording Updates for Other Shownotes Systems

Use this only when the site is not handled by `shownotes-publisher`. Jekyll recording updates invoke `Skill(skill: "shownotes-publisher")` and finish after its verified result.

Require the supplied recording URL, profile video-publishing settings, and existing page. Resolve the shared runtime without `--read-only` before the paired page/tracking write. Use the [owner compatibility contract](../../vault-ingress/references/schemas-db.md#schema-versioning) and [mutation contract](../../vault-ingress/references/schemas-db.md#owner-read-and-mutation-contract).

Update the existing shownotes page with the video recording link.

#### 1. Verify Shownotes Exist

Locate the existing published shownotes page. Look for:
- The shownotes URL in the strict owner-reader result for this talk
- Or construct from `publishing_process.shownotes.url.base` +
  `publishing_process.shownotes.url.template` (substitute `{slug}` and any
  date variables) — see [shownotes.md](shownotes.md) for template semantics

If shownotes don't exist, STOP and ask the speaker. Options:
- Create shownotes through a separately requested publishing action
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

For the Jekyll shownotes site with `_plugins/markdown_parser.rb`, invoke
`Skill(skill: "shownotes-publisher")` with the existing page and recording
URL. It preserves the existing talk skill on a video-only update, creates
one if missing, and reconciles newly available delivered teaching when a
content refresh is requested. Resume at tracking persistence after verified
publication; do not bypass its skill checks with a separate page-only push.

For other shownotes systems, continue below.

#### 3. Generate Shownotes Update

Create the video section content based on `embed_method`:

- **youtube_embed**: Full responsive YouTube embed iframe
- **link_only**: "Watch the Recording" heading with a link to the video
- **both**: Embed iframe + text link below

Include the video title, conference name, and year from the presentation spec.

#### 4. Apply Update

Use the publishing method configured for this shownotes destination:
- If git-based: create/update the shownotes file, commit, push
- If CMS: provide the content for the speaker to paste
- If manual: present the formatted content block

#### 5. Tracking Database Update

Persist `video_added_to_shownotes: true` and the YouTube `video_url` (plus the
derived `youtube_id` when absent) with one `update_talk_publishing` mutation.
The `expect` object must cover exactly the fields being set with values from the
latest strict read. Dry-run, review, apply against the reported input SHA, and
re-read through the
[owner mutation contract](../../vault-ingress/references/schemas-db.md#owner-read-and-mutation-contract).
Keep that talk record at `schema_version: 8`; this workflow is an authorized
current writer, not a schema owner or migrator.

---
