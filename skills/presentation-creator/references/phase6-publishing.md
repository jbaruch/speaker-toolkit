# Phase 6: Publishing — Detail

The publishing workflow is speaker-specific. Read `publishing_process` from
`speaker-profile.json`. Read the talk slug and metadata from `presentation-spec.md`
in the talk directory (saved in Phase 1). If the section is missing or empty,
fall back to asking the author interactively and document their answers for
next time.

### Step 6.1: Shownotes

Read `publishing_process.shownotes_publishing`. If `enabled`:

- Follow the `method` description (git push, CMS, manual)
- If `shownotes_repo_path` and `shownotes_template` are provided, generate the page
- Include: title, abstract, slide embed/download link, resource links, speaker bio
- Construct the shownotes URL by substituting the **talk slug from the Presentation
  Spec** (Phase 1) into `shownotes_url_pattern` from the speaker profile. The slug
  was agreed with the author in Phase 1 — NEVER invent or rephrase it. Example:
  pattern `speaking.example.com/{slug}` + spec slug `arc-of-ai` →
  `speaking.example.com/arc-of-ai`

If not enabled, skip.

### Step 6.2: QR Code

Read `publishing_process.qr_code`. If `enabled`:

1. Determine the URL to encode:
   - If `target` is `shownotes_url`, use the shownotes URL from Step 6.1
   - If `target` is `custom_url`, use the `custom_url` field

2. Resolve URL shortening using one of these paths:

| Path | Short URL resolution | QR image |
|---|---|---|
| MCP (preferred when configured) | Agent calls Bitly/Rebrandly MCP tool, passes `--short-url` to script | Script generates locally from the resolved URL |
| Direct API | Script calls bit.ly/rebrand.ly REST API via `secrets.json` | Script generates locally |
| None | Script uses the raw shownotes URL | Script generates locally |

**MCP path (preferred when Bitly or Rebrandly MCP server is installed):**
- Bitly MCP: `npx @bitly/mcp` — covers link creation, update, QR, and analytics
- Rebrandly MCP: see rebrandly.com MCP documentation
- Agent creates or updates the short link via MCP tools, then passes the resolved
  URL to `generate-qr.py` via `--short-url`

**Direct API path (when MCP is not available):**
- API keys must be stored in `{vault_root}/secrets.json` with `chmod 600`:
  ```json
  {
    "gemini": {"api_key": "..."},
    "bitly": {"api_token": "..."},
    "rebrandly": {"api_key": "..."}
  }
  ```
- Script reads `secrets.json` and calls the shortener's REST API directly
- The `shortener` field in the profile controls which service to use

**None path (no shortening):**
- Script encodes the raw shownotes URL directly into the QR code

3. Run the QR generation script:
   ```bash
   # MCP-preresolved mode:
   python3 skills/presentation-creator/scripts/generate-qr.py deck.pptx \
     --talk-slug SLUG --short-url https://bit.ly/arcofai

   # Direct API mode:
   python3 skills/presentation-creator/scripts/generate-qr.py deck.pptx \
     --talk-slug SLUG --shownotes-url https://jbaru.ch/arc-of-ai \
     --vault /path/to/vault

   # No shortening:
   python3 skills/presentation-creator/scripts/generate-qr.py deck.pptx \
     --talk-slug SLUG --shownotes-url https://jbaru.ch/arc-of-ai

   # PNG-only (no deck — for presenterm, PDF, or standalone use):
   python3 skills/presentation-creator/scripts/generate-qr.py --png-only \
     --talk-slug SLUG --shownotes-url https://jbaru.ch/arc-of-ai \
     --output /path/to/qr.png --bg-color 128,0,128
   ```

4. The script will:
   - Match the QR background color to the target slide (walks slide → layout → master
     for solid fill; falls back to white with a warning for theme-colored fills)
   - Auto-select foreground color (black on light backgrounds, white on dark) using
     WCAG relative luminance
   - Insert the QR as a 2" square in the bottom-right corner
   - Update `tracking-database.json` with the QR metadata in the `qr_codes[]` array

5. Re-running for the same `talk_slug` with a different target URL will PATCH the
   existing short link (keeping QR codes already printed valid) rather than creating
   a new one.

**Dependencies:** `pip install qrcode` (Pillow is already a transitive dep of python-pptx).

### Step 6.3: Export

Read `publishing_process.export_format` and `publishing_process.export_method`.

- If `export_script` is provided, run it (substituting the deck path)
- If `export_method` is a description, follow its instructions
- Common pattern: PowerPoint AppleScript for PDF (see [phase5-slides.md](phase5-slides.md))
- If no export info, ask: "How do you want to export? PDF, keep .pptx only, or both?"

### Step 6.4: Additional Steps

Read `publishing_process.additional_steps[]`. For each entry:

- If `automated` is true and `script` is provided, run it
- If `automated` is false, present the step to the author as a manual TODO
- Report completion status for each step

### Step 6.5: Go-Live Preparation Checklist

Before delivery, surface unobservable patterns from [patterns/_index.md](patterns/_index.md)
(the "Unobservable Patterns — Go-Live Checklist" section) as a preparation reminder.
These are patterns the vault **cannot score retroactively** because they involve
pre-event logistics, physical stage behaviors, or external systems — but they still
matter for delivery quality.

```
GO-LIVE CHECKLIST — {talk title}
==================================
PRE-EVENT:
[ ] Preparation — backups, cables, hydration, room layout check
[ ] Carnegie Hall — completed 4 rehearsals (pace, delivery, fixes, groove)
[ ] The Stakeout — staging area identified near venue
[ ] Posse — supporter(s) confirmed for front row
[ ] Seeding Satisfaction — plan to arrive early and mingle
[ ] Shoeless — comfort ritual ready

DURING DELIVERY:
[ ] Lightsaber — if laser pointer needed, max 2-3 steady moments
[ ] Red/Yellow/Green — exit feedback cards set up (if venue supports)

AVOID:
[ ] Laser Weapons — don't wave the pointer; use built-in highlights
[ ] Bunker — step out from behind the podium
[ ] Backchannel — don't monitor social media during the talk
==================================
```

### Step 6.6: Publishing Report

```
PUBLISHING REPORT — {talk title}
==================================
[DONE/SKIP] Shownotes: {url or "not configured"}
[DONE/SKIP] QR code: {inserted at slide N, encoded URL, shortener used}
[DONE/SKIP] Export: {format} → {output path}
[DONE/SKIP/TODO] {additional step name}: {status}
[INFO] Go-live checklist: {presented above}
==================================
```
