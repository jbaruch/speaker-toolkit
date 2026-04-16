# Vault Config & Intent Schemas

## Config Fields — Clarification Session Questions

Fields below `template_skip_patterns` are asked during Step 5B (first session only)
when empty. The question column shows what to ask the speaker.

| Config field | Question |
|-------------|----------|
| `speaker_name` | "Name as it appears on slides?" |
| `speaker_handle` | "Social handle for footers?" |
| `speaker_website` | "Website for talk resources?" |
| `shownotes_url_pattern` | "URL pattern for talk pages? (e.g., `speaking.example.com/{slug}`)" |
| `template_pptx_path` | "PowerPoint template path?" |
| `presentation_file_convention` | "File organization? (default: `{conference}/{year}/{talk-slug}/`)" |
| `publishing_process.export_format` | "How do you export final decks — PDF, keep .pptx only, or both?" |
| `publishing_process.export_method` | "How do you produce the PDF? (e.g., PowerPoint AppleScript, LibreOffice CLI, manual)" |
| `publishing_process.shownotes_publishing` | "Do you publish shownotes for your talks? If yes, how?" |
| `publishing_process.qr_code` | "Do you put QR codes in your decks? If yes, what do they link to?" |
| `publishing_process.qr_code.shortener` | "Do you use a URL shortener for QR links? Options: `bitly`, `rebrandly`, or `none`." |
| `publishing_process.qr_code.rebrandly_domain` | _(Only if shortener=rebrandly)_ "What custom domain do you use with Rebrandly? (e.g., `jbaru.ch`, or leave blank for default)" |
| `publishing_process.qr_code.shortener_setup` | _(Only if shortener=bitly or rebrandly)_ "Add your API key to `{vault_root}/secrets.json` (`chmod 600`). Format: `{\"bitly\": {\"api_token\": \"...\"}}` or `{\"rebrandly\": {\"api_key\": \"...\"}}`. Alternatively, install the Bitly or Rebrandly MCP server for agent-driven shortening." |
| `gemini_api_key` | "Add your Gemini API key to `{vault_root}/secrets.json` under `gemini.api_key` (`chmod 600`). Format: `{\"gemini\": {\"api_key\": \"...\"}}`. Get a key from https://aistudio.google.com/app/apikey. The `GEMINI_API_KEY` env var also works as a fallback." |
| `publishing_process.additional_steps` | "Any other distribution steps after exporting?" |

## Full Config Schema

```json
{
  "config": {
    "vault_root": "~/.claude/rhetoric-knowledge-vault",
    "vault_storage_path": "/actual/path/if/custom (null when using default location)",
    "talks_source_dir": "/path/to/_talks",
    "pptx_source_dir": "/path/to/Presentations",
    "python_path": "/path/to/python3",
    "template_skip_patterns": ["template"],
    "speaker_name": "",
    "speaker_handle": "",
    "speaker_website": "",
    "shownotes_url_pattern": "",
    "template_pptx_path": "",
    "presentation_file_convention": "{pptx_source_dir}/{conference}/{year}/{talk-slug}/",
    "clarification_sessions_completed": 0
  }
}
```

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
