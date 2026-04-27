# Vault Config & Intent Schemas

## Config Fields — Clarification Session Questions

Fields below `template_skip_patterns` are asked during Step 4 (first session
only) when empty. The question column shows what to ask the speaker.

| Config field | Question |
|-------------|----------|
| `speaker_name` | "Name as it appears on slides?" |
| `speaker_handle` | "Social handle for footers?" |
| `speaker_website` | "Website for talk resources?" |
| `shownotes.source.type` | "Where do your shownotes live? Local Jekyll, Hugo, Eleventy, Astro, a remote URL, or no shownotes site?" |
| `shownotes.source.path_or_url` | "Path (or base URL) to the shownotes site root?" |
| `shownotes.source.talks_subdir` | "Subdirectory under the site root where talk entries live? (e.g., `_talks`, `content/talks`)" |
| `shownotes.url.base` | "Base URL where the shownotes site is deployed?" |
| `shownotes.url.template` | "Permalink template for a single talk? (e.g., `/talks/{slug}/`, `/{yyyy}-{mm}-{dd}-{slug}/`). Verify against your deployed URLs before confirming." |
| `shownotes.thumbnail_path_template` | "Where in the site repo does the SSG template expect the talk thumbnail? (e.g., `assets/images/thumbnails/{slug}-thumbnail.png`)" |
| `shownotes.slug_convention.template` | "Convention for talk slugs? (e.g., `{venue-compact}{yy}-{short-id}` → `devnexus26-robocoders`). What components and format?" |
| `shownotes.ssg_template_pointer` | "Which SSG template file encodes the URL/thumbnail conventions (so they can be re-derived after a redesign)? e.g., `_layouts/default.html` for Jekyll." |
| `template_pptx_path` | "PowerPoint template path?" |
| `presentation_file_convention` | "File organization? (default: `{conference}/{year}/{talk-slug}/`)" |
| `publishing_process.export_format` | "How do you export final decks — PDF, keep .pptx only, or both?" |
| `publishing_process.export_method` | "How do you produce the PDF? (e.g., PowerPoint AppleScript, LibreOffice CLI, manual)" |
| `publishing_process.qr_code` | "Do you put QR codes in your decks? If yes, what do they link to?" |
| `publishing_process.qr_code.shortener` | "Do you use a URL shortener for QR links? Options: `bitly`, `rebrandly`, or `none`." |
| `publishing_process.qr_code.bitly_domain` | _(Only if shortener=bitly)_ "Do you have a custom Bitly domain? (e.g., `jbaru.ch`, or leave blank for default `bit.ly`)" |
| `publishing_process.qr_code.rebrandly_domain` | _(Only if shortener=rebrandly)_ "What custom domain do you use with Rebrandly? (e.g., `jbaru.ch`, or leave blank for default)" |
| `publishing_process.qr_code.shortener_setup` | _(Only if shortener=bitly or rebrandly)_ "Add your API key to `{vault_root}/secrets.json` (`chmod 600`). Format: `{\"bitly\": {\"api_token\": \"...\"}}` or `{\"rebrandly\": {\"api_key\": \"...\"}}`. Alternatively, install the Bitly or Rebrandly MCP server for agent-driven shortening." |
| `gemini_api_key` | "Add your Gemini API key to `{vault_root}/secrets.json` under `gemini.api_key` (`chmod 600`). Format: `{\"gemini\": {\"api_key\": \"...\"}}`. Get a key from https://aistudio.google.com/app/apikey. The `GEMINI_API_KEY` env var also works as a fallback." |
| `publishing_process.additional_steps` | "Any other distribution steps after exporting?" |

## Full Config Schema

See the canonical schema and field reference in
[../../vault-profile/references/schemas-config.md](../../vault-profile/references/schemas-config.md).
That file also documents the migration path for vaults created before the
unified `shownotes` block.

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
