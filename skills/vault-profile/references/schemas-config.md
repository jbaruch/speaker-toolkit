# Vault Config & Intent Schemas

## Config Fields — Clarification Session Questions

Fields below `template_skip_patterns` are asked during vault-clarification
Step 4 (first session only) when empty. The question column shows what to
ask the speaker.

| Config field | Question |
|-------------|----------|
| `speaker_name` | "Name as it appears on slides?" |
| `speaker_handle` | "Social handle for footers?" |
| `speaker_website` | "Website for talk resources?" |
| `shownotes.source.type` | "Where do your shownotes live? Local Jekyll, Hugo, Eleventy, Astro, a remote URL, or no shownotes site?" |
| `shownotes.source.path_or_url` | "Path (or base URL) to the shownotes site root?" |
| `shownotes.source.talks_subdir` | "Subdirectory under the site root where talk entries live? (e.g., `_talks`, `content/talks`)" |
| `shownotes.url.base` | "Base URL where the shownotes site is deployed?" |
| `shownotes.url.template` | "Permalink template for a single talk? (e.g., `/talks/{slug}/`, `/{yyyy}-{mm}-{dd}-{slug}/`)" |
| `shownotes.thumbnail_path_template` | "Where in the site repo does the SSG template expect the talk thumbnail? (e.g., `assets/images/thumbnails/{slug}-thumbnail.png`)" |
| `shownotes.slug_convention.template` | "Convention for talk slugs? (e.g., `{venue-compact}{yy}-{short-id}`)" |
| `template_pptx_path` | "PowerPoint template path?" |
| `presentation_file_convention` | "File organization? (default: `{conference}/{year}/{talk-slug}/`)" |
| `publishing_process.export_format` | "How do you export final decks — PDF, keep .pptx only, or both?" |
| `publishing_process.export_method` | "How do you produce the PDF? (e.g., PowerPoint AppleScript, LibreOffice CLI, manual)" |
| `publishing_process.qr_code` | "Do you put QR codes in your decks? If yes, what do they link to?" |
| `publishing_process.additional_steps` | "Any other distribution steps after exporting?" |

## Full Config Schema

```json
{
  "config": {
    "vault_root": "~/.claude/rhetoric-knowledge-vault",
    "vault_storage_path": "/actual/path/if/custom (null when using default location)",
    "pptx_source_dir": "/path/to/Presentations",
    "python_path": "/path/to/python3",
    "template_skip_patterns": ["template"],
    "speaker_name": "",
    "speaker_handle": "",
    "speaker_website": "",

    "shownotes": {
      "enabled": true,
      "source": {
        "type": "local_jekyll",
        "path_or_url": "/path/to/shownotes-site-root",
        "talks_subdir": "_talks"
      },
      "url": {
        "base": "https://speaking.example.com",
        "template": "/{slug}/"
      },
      "thumbnail_path_template": "assets/images/thumbnails/{slug}-thumbnail.png",
      "slug_convention": {
        "template": "{venue-compact}{yy}-{short-id}",
        "examples": []
      },
      "ssg_template_pointer": "{source.path_or_url}/_layouts/default.html"
    },

    "template_pptx_path": "",
    "presentation_file_convention": "{pptx_source_dir}/{conference}/{year}/{talk-slug}/",
    "clarification_sessions_completed": 0
  }
}
```

## Shownotes Config — Field Reference

**`shownotes.enabled`** — false means no shownotes site; skip Step 6.1 entirely,
the QR target must be a `custom_url` if enabled at all.

**`shownotes.source.type`** — one of:

| Type | Talks live at | Frontmatter |
|---|---|---|
| `local_jekyll` | `{path_or_url}/{talks_subdir}/*.md` | Jekyll YAML |
| `local_hugo` | `{path_or_url}/{talks_subdir}/*.md` | TOML/YAML/JSON front matter |
| `local_eleventy` | `{path_or_url}/{talks_subdir}/*.md` | YAML with `permalink:` per-file |
| `local_astro` | `{path_or_url}/{talks_subdir}/*.md` (content collections) | YAML |
| `remote_url` | read-only; browse `{path_or_url}` for live entries | n/a — scrape |
| `none` | no shownotes | n/a |

**`shownotes.source.path_or_url`** — local filesystem path when `type` starts
with `local_`, HTTPS URL when `type` is `remote_url`, null otherwise.

**`shownotes.source.talks_subdir`** — subdirectory under the site root where
talk entries live. Common values: `_talks` (Jekyll collections),
`content/talks` (Hugo), `src/content/talks` (Astro). null for `remote_url` /
`none`.

**`shownotes.url.base`** — deployed site base URL (no trailing slash).

**`shownotes.url.template`** — path component appended to `url.base` to form
the live URL. Template variables:

| Variable | Meaning |
|---|---|
| `{slug}` | The talk slug from the Presentation Spec |
| `{yyyy}` | 4-digit year from the talk's `date` frontmatter field |
| `{mm}` | 2-digit month |
| `{dd}` | 2-digit day |
| `{venue}` | Slugified venue name |
| `{yy}` | 2-digit year |

Presets for common SSGs (starting points — verify against the actual deployed
URLs before shipping):

- Jekyll `_talks` collection (default permalink): `/talks/{slug}/`
- Jekyll with date permalink: `/{yyyy}/{mm}/{dd}/{slug}/`
- Hugo default content section: `/{talks_subdir}/{slug}/`
- Eleventy (permalink is per-file): use the most common pattern from your
  entries; if each file overrides it, set `url.template` to null and let the
  slug-convention step read the literal URL from per-file `permalink:`
- Flat speaker-site with slug convention: `/{slug}/`

**`shownotes.thumbnail_path_template`** — filesystem path (relative to
`source.path_or_url`) where the SSG template expects the talk thumbnail image.
The exact convention is encoded in the SSG template file (e.g., Jekyll
`_layouts/default.html` `og:image` tag) — see `ssg_template_pointer`. The
default for Jekyll-based shownotes in this toolkit is:

```
assets/images/thumbnails/{slug}-thumbnail.png
```

Both the nested `thumbnails/` subdirectory AND the `-thumbnail` suffix are
mandatory for this convention — flat paths fall back to
`placeholder-thumbnail.svg` on the live site with no warning.

**`shownotes.slug_convention.template`** — pattern used to generate new talk
slugs. Template variables are derived from talk metadata (venue, date, title).
See the phase1-intent.md reference for derivation rules.

**`shownotes.slug_convention.examples`** — array of recent slugs that match
the current convention; used by presentation-creator Phase 1 to validate
against drift (older analyses often encode retired conventions).

**`shownotes.ssg_template_pointer`** — path to the SSG template file that
encodes the URL and thumbnail-path conventions. Stored so the convention can
be re-derived after a site redesign without spelunking through the template tree.

## Migration from Legacy Fields

Vaults created before this schema had `config.talks_source_dir` and
`config.shownotes_url_pattern` as flat fields. Vault-profile regeneration maps
them as follows:

| Legacy field | New location |
|---|---|
| `config.talks_source_dir` | `config.shownotes.source.path_or_url` + `talks_subdir` (split on the last path segment) |
| `config.shownotes_url_pattern` (flat `{slug}`) | `config.shownotes.url.base` + `config.shownotes.url.template` (template defaults to `/{slug}/`) |

If a vault presents only the legacy fields, readers should upgrade-on-read
(build the shownotes block in memory) and vault-profile writes the new schema
on next regeneration. Do not leave both shapes populated — one source of truth.

## Confirmed Intents Schema

Stored in the `confirmed_intents` array of the tracking database. Populated during
clarification sessions when the speaker confirms a pattern is intentional.

```json
{
  "confirmed_intents": [{
    "pattern": "delayed_self_introduction",
    "intent": "deliberate|accidental|context_dependent",
    "rule": "Use two-phase intro: brief bio at slide 3, full re-intro mid-talk",
    "note": "Speaker confirmed this is an intentional rhetorical device"
  }]
}
```
