# Alternate Entry Flows — Detail

Load this file when the request is not a fresh linear Phase 0–6 build:

- a **late-entry single task** (QR code, export, shownotes) — read "Late Entry";
- **adapting an existing talk** — read "Adapting Existing Talks";
- a **CFP abstract** — read "CFP Abstract Writing";
- any **sessions-catalog** read or write — read "Sessions Catalog".

Vault loading (SKILL.md "Before You Start") is mandatory for every flow here.

## Late Entry (single-task requests)

Even when the user asks for a single task, do not jump straight to the action.
Minimum context before ANY Phase 6 action:

- `speaker-profile.json` — publishing config, shortener, URL patterns
- `secrets.json` — API keys for shorteners and Gemini
- `outline.yaml` — source of truth for talk slug, metadata, slides, and the
  shownotes URL. Read it via
  `"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/outline_schema.py"`
  (the pydantic model exposes `talk.slug`, `talk.title`,
  `talk.shownotes_url_base`, etc.) — never re-parse the YAML by hand.

If a file is missing or fails to validate, STOP and ask. Do not guess values that
should come from files. Never hand-write code when a script exists — if the
script isn't working, diagnose why (wrong args, missing config, missing secrets)
and fix the inputs.

**Phase 7 late entry** requires the same files plus a YouTube video URL from the
speaker. If shownotes don't exist and Step 7.2 is requested, STOP and ask —
either run Phase 6 Step 6.1 first or get the shownotes URL manually.

## Adapting Existing Talks

1. Check if the talk has been ingested by the vault. If not, process it first.
2. Read the original talk's analysis from `{vault_root}/analyses/`.
3. Copy the previous deck as the starting point — do NOT start from a fresh
   template.
4. Start at Phase 1 with the original spec pre-filled, modify as needed.
5. Auto-generate an adaptation checklist: footer, shownotes slug, time-sensitive
   content, slide budget, profanity register, locale references, commercial
   intent.
6. For structural edits (delete/reorder slides, import slides from another deck,
   global text replace), edit through real PowerPoint via
   `"{speaker_toolkit_root}/skills/presentation-creator/scripts/run-deck-ops.sh"`.
   python-pptx editing is not used — it strips per-slide background fills,
   flattening illustrated decks. See `rules/deck-editing-rules.md` (macOS +
   Microsoft PowerPoint only). On first use, walk the user through
   `references/deck-editing-setup.md` (enable macros, import the macro, grant
   Automation consent) before invoking the script.

## CFP Abstract Writing

1. Complete Phase 0–1 (lighter touch).
2. Skip Phase 2 — not needed for an abstract.
3. Write: title, abstract (200–300 words), key takeaways (3–5 bullets), speaker
   bio.
4. Phase 4 revision as normal.
5. Save approved materials to the Sessions Catalog.

## Sessions Catalog

The sessions catalog (`{vault_root}/sessions-catalog.md`) is the single source of
submission-ready materials for active talks. Load it during Phase 0 to know the
active rotation and flag overlapping territory. Pull an existing entry before
starting a new CFP; adapt rather than rewrite.

**What goes in the catalog.** Each entry contains:

- **Title** — including subtitle if any
- **Abstract** — submission-ready, anti-pattern-checked
- **Outline** — with section descriptions and time allocations
- **Small Print** — notes for the Program Committee: positioning, scope
  clarifications, or anything the PC should know. Internal, not public-facing.

**Catalog maintenance.**

- Save approved title, abstract, and outline after CFP abstract writing (step 5)
  and after Phase 4 if no entry exists yet. Remove or archive entries when a talk
  is retired.
- The catalog reflects the **latest approved version** — full history lives in
  the tracking database and analysis files.
- Run an anti-pattern check on entries before saving (use the blog-writer skill's
  `ai-anti-patterns.md` if installed). Keep the "Last updated" date current.
- Entries are separated by `---` horizontal rules for easy scanning.
