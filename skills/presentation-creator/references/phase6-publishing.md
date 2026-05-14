# Phase 6: Publishing — Detail

## Pre-Flight Checklist

Before ANY Phase 6 action, load these files. If any is missing, STOP and ask.

1. **`speaker-profile.json`** — publishing config, shortener, URL patterns, QR settings
2. **`secrets.json`** — API keys (bitly, rebrandly, gemini). Missing key = stop, not fallback.
3. **`outline.yaml`** — source of truth for talk slug, metadata, slides, and shownotes URL.
   Load via `scripts/outline_schema.py` (pydantic model exposes `talk.slug`, `talk.title`,
   `talk.shownotes_url_base`, `slides`, etc.) — never re-parse the YAML by hand.

Do not guess values that should come from these files. Do not proceed with partial
context — every silent assumption becomes a wrong default downstream.

---

The publishing workflow is speaker-specific. Read `publishing_process` from
`speaker-profile.json`. Read the talk slug and metadata from `outline.yaml`
(`talk:` block, authored in Phase 1). If the section is missing or empty,
fall back to asking the author interactively and document their answers for
next time.

### Step 6.0: Resources Gathering

Extract and curate resource links from the finalized outline before any
publishing step. Resources scattered across speaker notes, visual descriptions,
and Coda slides are easy to miss — this step catches them systematically.

1. Run the extraction script against `outline.yaml`:
   ```bash
   python3 skills/presentation-creator/scripts/extract-resources.py outline.yaml
   ```

2. The script produces `resources.json` in the talk working directory with
   categorized entries: URLs, repos, books/papers, RFCs, and tool mentions.
   Each entry includes slide references and context.

3. Present the extracted resources to the speaker as a formatted review list,
   grouped by type. Coda section items are flagged and listed first — the
   speaker deliberately chose to surface them.

4. The speaker reviews, approves, removes false positives, adds missing items,
   and edits entries. Save the approved list back to `resources.json` with
   `approved: true` on accepted items.

5. Update `tracking-database.json` with a `resources[]` entry recording the
   talk slug, item count, and category breakdown.

If the speaker declines resource gathering, skip this step — Step 6.1 will
omit the resource links section from shownotes.

### Step 6.1: Shownotes

Read `publishing_process.shownotes`. If `enabled`:

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
  talk working directory (produced by Step 6.0) — do not re-scan the outline.

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
| `https://jbaru.ch` | `/talks/{slug}/` | `devnexus26-robocoders` | `https://jbaru.ch/talks/devnexus26-robocoders/` |

If the SSG uses per-file `permalink:` frontmatter (common in Eleventy), read
the permalink from the newly-generated page's frontmatter rather than
synthesizing from `url.template`. In that case `shownotes.url.template` may
be null.

Before passing the URL downstream (QR code, bit.ly target, post-event video
description), verify the URL is reachable — a 404 on the deployed site
breaks printed QR codes with no recovery path.

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

**No raw-dogging:** NEVER bypass `generate-qr.py` with hand-rolled python-pptx or
direct `qrcode` library calls. If the script targets the wrong slides, uses the wrong
shortener, or produces the wrong colors — fix the inputs (profile config, secrets,
arguments), don't patch the outputs with ad-hoc code. The script is the single source
of truth for QR generation; working around it silently drops shortening, tracking,
and color matching.

**Dependencies:** `pip install qrcode` (Pillow is already a transitive dep of python-pptx).

### Step 6.3: Export

Read `publishing_process.export_format` and `publishing_process.export_method`.

- If `export_script` is provided, run it (substituting the deck path)
- If `export_method` is a description, follow its instructions
- Common pattern: PowerPoint AppleScript for PDF (see [phase5-slides.md](phase5-slides.md))
- If no export info, ask: "How do you want to export? PDF, keep .pptx only, or both?"

### Step 6.4: Talk Timer Artifact

**Optional step:** generate a plain-text timing file from `outline.yaml`'s
`chapters[]` (each chapter has `target_min`). Run unless the author opts out.

Source: `chapters[].title` and `chapters[].target_min` in `outline.yaml`.

Generate a plain-text timing file for [timemytalk.app](https://timemytalk.app)
by running:

```bash
python3 skills/presentation-creator/scripts/generate-talk-timings.py \
  outline.yaml --output talk-timings.txt

# If the talk slot includes Q&A time:
python3 skills/presentation-creator/scripts/generate-talk-timings.py \
  outline.yaml --qa 5 --output talk-timings.txt
```

**Format:** one line per chapter, `MM:SS Label`, using cumulative start times.
The final line is always `MM:SS FINISH` where the timestamp equals the total
talk duration (including Q&A if applicable).

**Granularity guidelines:**
- 25-min talks: 8-13 chapters
- 45-60 min talks: 10-15 chapters
- Subdivide chapters exceeding ~5 min into multiple chapters in `outline.yaml`

**Q&A:** if the talk slot includes Q&A time, pass `--qa MINUTES` to append a
Q&A chapter before FINISH.

The speaker uploads the resulting `.txt` file to timemytalk.app before delivery.

### Step 6.5: Additional Steps

Read `publishing_process.additional_steps[]`. For each entry:

- If `automated` is true and `script` is provided, run it
- If `automated` is false, present the step to the author as a manual TODO
- Report completion status for each step

### Step 6.6: Go-Live Preparation Checklist

Before delivery, surface a delivery-readiness checklist composed of two strands:

1. **Unobservable patterns** from [patterns/_index.md](patterns/_index.md) (the
   "Unobservable Patterns — Go-Live Checklist" section). These are patterns the vault
   **cannot score retroactively** because they involve pre-event logistics, physical
   stage behaviors, or external systems.
2. **Observable delivery reminders** that the speaker can decide to apply on the day —
   venue setup choices (lights, lectern, mic), opening discipline, time discipline,
   and screen-blackout tactics. These *are* observable post-talk, but the speaker
   benefits from a pre-talk reminder regardless of the vault's ability to score them
   later.

Both strands matter for delivery quality and belong in the same checklist.

```
GO-LIVE CHECKLIST — {talk title}
==================================
VENUE SETUP:
[ ] Lights ON — keep light on the speaker (Reynolds: audience must see your face;
    they cannot read facial expressions in the dark; dim only the screen-area lights
    if the projector requires it)
[ ] Lectern moved aside — step out from behind any podium or table; place computer
    on the floor in front of the stage so you don't have to turn back to advance slides
[ ] Mic test — wireless lavalier or headset preferred over handheld; do not rely on
    shouting

PRE-EVENT:
[ ] Preparation — backups, cables, hydration, room layout check
[ ] Carnegie Hall — completed 4 rehearsals (pace, delivery, fixes, groove)
[ ] The Stakeout — staging area identified near venue
[ ] Posse — supporter(s) confirmed for front row
[ ] Seeding Satisfaction — plan to arrive early and mingle
[ ] First Impression — pre-event communications (invitation tone, agenda
    framing, bio wording) have already shaped the audience's view of you
    before you walk in; the room you walk into builds on that. Do NOT
    arrive heads-down at the laptop fixing slides. Engage warmly with
    early-arrivers, shake hands, ask questions. The mood you project
    before the talk starts is part of the talk.
[ ] Shoeless — comfort ritual ready

DURING DELIVERY:
[ ] Honeymoon-window discipline — first 1–2 minutes earn the talk; do NOT spend
    them on agenda slides, "let me introduce myself," or "thanks for the invitation"
    filler. Open with the planned PUNCH hook (see outline)
[ ] Never apologize, never confess nerves — both are self-focused at a moment that
    should be audience-focused. Acknowledge nerves to yourself; do not share them
    with the audience
[ ] Hara hachi bu — finish at 90–95% of the allotted time, never run over;
    "leave them slightly hungry, not stuffed"
[ ] Screen Blackout — use the B key (or planned black slides) at section boundaries,
    personal stories, and audience-question moments to redirect attention
[ ] Lightsaber — if laser pointer needed, max 2-3 steady moments
[ ] Red/Yellow/Green — exit feedback cards set up (if venue supports)

AVOID:
[ ] Laser Weapons — don't wave the pointer; use built-in highlights
[ ] Bunker — step out from behind the podium
[ ] Backchannel — don't monitor social media during the talk
==================================
```

### Step 6.7: Publishing Report

```
PUBLISHING REPORT — {talk title}
==================================
[DONE/SKIP] Resources: {N approved items from resources.json, or "skipped"}
[DONE/SKIP] Shownotes: {url or "not configured"}
[DONE/SKIP] QR code: {inserted at slide N, encoded URL, shortener used}
[DONE/SKIP] Export: {format} → {output path}
[DONE/SKIP] Talk timer: {output path, or "no pacing summary in outline"}
[DONE/SKIP/TODO] {additional step name}: {status}
[INFO] Go-live checklist: {presented above}
==================================
```
