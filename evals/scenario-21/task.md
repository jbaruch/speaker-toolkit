# QR Generation with Bitly Custom Back-Half and Slug from Spec

## Problem/Feature Description

A speaker wants a QR code for their talk "Robocoders: Judgment Day" at DevNexus 2026. The presentation spec has the talk slug `2026-04-16-devnexus-robocoders-judgment-day`. The speaker profile has QR enabled with `shortener: "bitly"`.

The agent must:
1. Read the talk slug from `presentation-spec.md` (not invent one)
2. Construct the shownotes URL from the profile's `shownotes_url_pattern` + the spec slug
3. Use `generate-qr.py` (not the qrcode library directly) to create the QR
4. The QR must encode the **bitly URL** (decoupling layer), not the raw shownotes URL
5. The bitly link must use the talk slug as the custom back-half (not a random hash)

Using the presentation-creator skill, plan the QR generation workflow and document the commands that would be run.

## Output Specification

Produce the following files:

1. **`qr-generation-plan.md`** — The complete plan including:
   - The exact `generate-qr.py` command that would be run
   - The shownotes URL (constructed from pattern + spec slug)
   - Confirmation that bitly will use the talk slug as custom back-half
   - Confirmation that the QR will encode the bitly URL, not the raw URL
2. **`verification-report.md`** — Document:
   - Which script was referenced (must be generate-qr.py)
   - The talk slug source (must be presentation-spec.md)
   - The expected bitly URL format (bit.ly/{talk-slug})
   - Why the QR encodes the bitly URL (decoupling layer explanation)

## Input Files

Download vault fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-21"
mkdir -p inputs/vault inputs/talk
curl -L -o inputs/vault/speaker-profile.json "$BASE/speaker-profile.json"
curl -L -o inputs/vault/secrets.json "$BASE/secrets.json"
curl -L -o inputs/vault/tracking-database.json "$BASE/tracking-database.json"
curl -L -o inputs/talk/presentation-spec.md "$BASE/presentation-spec.md"
```

## Key Parameters

- **Talk slug (from spec):** `2026-04-16-devnexus-robocoders-judgment-day`
- **Shownotes URL pattern:** `https://jbaru.ch/{slug}`
- **Expected shownotes URL:** `https://jbaru.ch/2026-04-16-devnexus-robocoders-judgment-day`
- **Shortener:** `bitly` (configured in profile)
- **Expected bitly custom back-half:** `2026-04-16-devnexus-robocoders-judgment-day`
- **Expected QR-encoded URL:** `https://bit.ly/2026-04-16-devnexus-robocoders-judgment-day`
- **Secrets:** bitly api_token present in secrets.json

## Notes on Verification

The critical tests:
1. The slug comes from presentation-spec.md, not agent-invented
2. The bitly link uses the talk slug as custom back-half (not a random hash)
3. The QR encodes the bitly URL (decoupling layer), not the raw shownotes URL
4. generate-qr.py is used, not direct qrcode library calls
5. The --talk-slug argument matches the spec slug exactly
