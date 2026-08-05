# Vault Config & Intent Schemas

## Config Fields — Clarification Session Questions

Fields below `template_skip_patterns` are asked during vault-clarification
Step 5 (first session only) when empty. The question column shows what to
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

The exclusion value below is one illustrative valid customization, not the
canonical owner default.

```json
{
  "config": {
    "schema_version": 2,
    "vault_root": "~/.claude/rhetoric-knowledge-vault",
    "vault_storage_path": "/native/absolute/database-parent (optional; null/absent uses that parent)",
    "pptx_source_dir": "/path/to/Presentations",
    "python_path": "/path/to/python3",
    "template_skip_patterns": ["template"],
    "pptx_directory_exclusions": ["example-tool-cache"],
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

### PPTX directory exclusions

Config schema v2 requires `pptx_directory_exclusions`: a bounded, unique array
of literal directory-name components. Matching is case-insensitive and exact at
any descendant depth. Values are not paths, substrings, globs, or regular
expressions; `/`, `\\`, control characters, pattern metacharacters,
case-insensitive duplicates, `.` and `..` are invalid. The code-owned owner
default is intentionally not reproduced here; use the
[vault-ingress PPTX scan contract](../../vault-ingress/references/bootstrap-and-preflight.md#scan-for-pptx-files).
Do not broaden the code-owned default to plausible authored-content directory
names without an explicit speaker-specific customization.

Dual readers accept config schema v1 only as read-only compatibility and
owner-migration state; it is never current or writable. It cannot authorize PPTX
catalog coverage or an absence conclusion because no current directory-exclusion
policy is established until migration succeeds. The vault-ingress migration
stamps schema v2 and supplies the canonical defaults when the list is absent. A
valid custom list already present on a schema-v1 record is preserved exactly. A
root-schema-v1/config-schema-v1 vault receives only this config upgrade; the root
and every unrelated record remain unchanged. Future or malformed config
generations fail closed. Consumers never synthesize defaults or rewrite config
themselves.

### Trusted vault storage root

`vault_storage_path` is an optional assertion about the vault that contains
`tracking-database.json`; it is not a redirect. Absent or JSON null uses the
database parent. Every other present value must be a host-native absolute path
lexically equal to that parent. Readers do not expand `~`, rebase relative,
drive-relative (`C:vault`), or current-drive-rooted (`\vault`) values, translate
foreign path flavors, collapse dot segments, or resolve symlinks to manufacture
equality. Empty/blank and invalid locator forms fail closed before evidence
freshness or profile cohort construction.

Profile readers never repair this field. Use vault-ingress's expectation-bound
owner mutation and rerun preflight before regenerating a profile; the concrete
dry-run/apply/re-read sequence is documented in
[source-identity-preflight.md](../../vault-ingress/references/source-identity-preflight.md#repair-a-stored-root-assertion).

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

If a vault presents only the legacy fields, readers build the shownotes block
in memory. vault-ingress owns persistence of the current config shape. Do not
leave both shapes populated — one source of truth.

## Confirmed Intents Schema

Stored in the `confirmed_intents` array of the tracking database. Populated during
clarification sessions when the speaker confirms a pattern is intentional.

```json
{
  "confirmed_intents": [{
    "schema_version": 1,
    "pattern": "delayed_self_introduction",
    "intent": "deliberate",
    "rule": "Use two-phase intro: brief bio at slide 3, full re-intro mid-talk",
    "note": "Speaker confirmed this is an intentional rhetorical device",
    "confirmed_date": "2026-08-01",
    "source_talk": "2026-08-01-example.md"
  }]
}
```

Required fields are exact integer `schema_version: 1`, `pattern`, `intent`,
`rule`, and `note`. The owner also accepts the clarification
provenance fields `confirmed_date`, one of `source_talk` / legacy `talk` /
`source_talks`, and `retrofit_targets`. The plural fields are non-empty unique
string arrays. Existing speaker-owned non-empty intent labels remain readable;
the three labels in the example are the recommended vocabulary. Unknown fields
are not part of the record.
