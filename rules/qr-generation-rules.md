---
alwaysApply: false
applyTo: "skills/presentation-creator/** — when generating or replacing QR codes during the presentation publishing flow (Phase 6)"
---

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

The short link's back-half MUST ALWAYS be the talk slug — the bit.ly custom
back-half AND the rebrand.ly slashtag, with no override. When a custom domain is
configured in the vault profile (`bitly_domain` / `rebrandly_domain`), the short
link MUST use it. The script does this automatically: `--talk-slug
devnexus26-robocoders` with `bitly_domain: jbaru.ch` creates
`jbaru.ch/devnexus26-robocoders` (not `bit.ly/a3xK9f`). If the slug back-half
can't be set, the script fails to a raw-URL fallback rather than keeping a random
hash.

Random hashes are untraceable and unprofessional. The back-half IS the slug.

## 3. QR Always Encodes the Shortener URL

The QR code MUST encode the bit.ly/rebrandly URL, never the raw shownotes URL.
The shortener is the decoupling layer — if the shownotes URL changes later,
update the shortener target, and every printed QR code stays valid.

The only exception is `"shortener": "none"` (explicit opt-out), where the raw
URL is the only option.

## 4. Slug Convention

The back-half IS `talk.slug` — composed and agreed with the author in Phase 1
(per the speaker's `slug_convention.template`) and persisted in `outline.yaml` /
`presentation-spec.md`. The QR step uses it VERBATIM: never invent, rephrase,
re-derive, abbreviate, or date-prefix it. The back-half must equal the published
shownotes slug.

- Kebab-case, lowercase, no special characters
- No date prefix (e.g. `devnexus26-robocoders`, not `2026-04-16-devnexus-robocoders`)

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

## 7. First Short Link = ASK + SAVE the Custom Domain

The first time a short link is created for the active shortener, the custom-domain
decision MUST be recorded in the vault profile. Three states of
`publishing_process.qr_code.{shortener}_domain`:

- Key ABSENT → never asked. ASK whether the user has a custom domain (e.g.
  `jbaru.ch`) and SAVE the answer before the link is created.
- A domain string → use it for the short link.
- `null` → recorded decision: no custom domain, use the shortener default (`bit.ly`).

Save the decision either way — the domain string, or `null` for "no custom domain".
A `null` is a recorded decision, not an absent value; never re-ask once saved. On
the Direct API path `generate-qr.py` STOPS when the key is absent; on the MCP path
the agent makes the same check before resolving the link.

## 8. Replace Existing QRs In Place

A deck adapted (trimmed) from another talk carries that talk's QR images. The QR
step detects every existing QR — the closing slide AND any earlier shownotes
slide — and replaces it in place at the same position and size, never adding a
second QR beside it.

Detection is by CONTENT, not size: an inherited QR can be any size (the same QR
may appear at 1.8" and 2.8"), so a size band misses it. A QR is a square picture
that is both ~2-color and roughly balanced between those colors — which excludes
colored diagrams (many colors) and mostly-one-color text screenshots (unbalanced).
This runs in `generate-qr.py` (`find_qr_rects`), which can read pixels; it hands
the matched geometry to the `InsertQR` macro (`RunDeckOps.bas`), which can't run
image libraries and just removes those exact shapes and places the QR there. The
thresholds are named in `generate-qr.py`.
