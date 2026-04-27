# QR Generation Rules

## 1. ALWAYS Use generate-qr.py

NEVER call the `qrcode` library directly or generate QR images through any
other means. ALWAYS use `generate-qr.py`. The script handles URL shortening,
custom back-half, tracking DB updates, color matching, and secrets.

When the target is not a .pptx deck (e.g., presenterm, PDF, or standalone PNG),
use `--png-only` mode:

```bash
python3 generate-qr.py --png-only --talk-slug SLUG --shownotes-url URL \
    --output /path/to/qr.png --bg-color "128,0,128"
```

## 2. NEVER Use a Random Shortener Hash

The custom back-half MUST be the talk slug. The script does this automatically:
`--talk-slug 2026-04-16-devnexus-robocoders-judgment-day` creates
`bit.ly/2026-04-16-devnexus-robocoders-judgment-day` (not `bit.ly/a3xK9f`).

Random hashes are untraceable and unprofessional. The back-half IS the slug.

## 3. QR Always Encodes the Shortener URL

The QR code MUST encode the bit.ly/rebrandly URL, never the raw shownotes URL.
The shortener is the decoupling layer — if the shownotes URL changes later,
update the shortener target, and every printed QR code stays valid.

The only exception is `"shortener": "none"` (explicit opt-out), where the raw
URL is the only option.

## 4. Slug Convention

Slug format: `{YYYY-MM-DD}-{conference-slug}-{talk-short-name}`

- Derive mechanically from: delivery date + conference name + talk title
- Kebab-case, lowercase, no special characters
- No abbreviations, no ambiguity
- The slug is agreed with the author in Phase 1 and persisted in
  `presentation-spec.md`. NEVER invent, rephrase, or re-derive it.

Example: `2026-04-16-devnexus-robocoders-judgment-day`

Read the speaker's convention from
`publishing_process.shownotes.slug_convention.template` in the profile. If
not set (or if it disagrees with recent shownotes entries under
`publishing_process.shownotes.source.path_or_url` /
`shownotes.source.talks_subdir`), treat the observed live convention as
authoritative and offer to update the profile via vault-clarification.

## 5. Missing Shortener Config = STOP

When the speaker profile has no `shortener` configured (key missing, not set
to `"none"`), STOP and ask the user to choose one.

- `"shortener": "none"` → explicit opt-out, proceed without shortening
- `shortener` key missing → NOT CONFIGURED → ask before proceeding

Silent generation with a raw URL when shortening was never discussed = failure.

## 6. Missing API Token = STOP

If `secrets.json` is missing or lacks the required API token, STOP and guide
the user to create it. Do not silently degrade to a raw URL.

The script prints actionable creation commands — but the agent must treat a
missing token as a blocker, not a fallback trigger.
