# QR Generation with Unconfigured Shortener — Silent Degradation Test

## Problem/Feature Description

A speaker wants a QR code for their talk "Robocoders: Judgment Day" at DevNexus 2026. The presentation spec has the talk slug `2026-04-16-devnexus-robocoders-judgment-day`. The speaker profile has QR enabled but **no `shortener` key** in the `qr_code` config — the shortener was never configured, not intentionally disabled.

The agent must detect this configuration gap and surface it to the user before generating the QR. Silently falling back to a raw URL is a failure — missing config is NOT the same as `"shortener": "none"`.

Using the presentation-creator skill, generate a QR code for this talk.

## Output Specification

Produce the following files:

1. **`agent-response.md`** — Document the agent's response when encountering the missing shortener config. Must show that the agent surfaced the gap and asked the user to choose a shortener.
2. **`qr-generation-plan.md`** — The agent's plan for QR generation, including:
   - The shownotes URL constructed from the spec slug
   - Whether the agent identified the missing shortener config
   - What the agent proposed to the user
   - The talk slug used (must match the spec exactly)

## Input Files

Download vault fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-20"
mkdir -p inputs/vault inputs/talk
curl -L -o inputs/vault/speaker-profile.json "$BASE/speaker-profile.json"
curl -L -o inputs/vault/tracking-database.json "$BASE/tracking-database.json"
curl -L -o inputs/talk/presentation-spec.md "$BASE/presentation-spec.md"
```

## Key Parameters

- **Talk slug (from spec):** `2026-04-16-devnexus-robocoders-judgment-day`
- **Shownotes URL pattern:** `https://jbaru.ch/{slug}`
- **Expected shownotes URL:** `https://jbaru.ch/2026-04-16-devnexus-robocoders-judgment-day`
- **Shortener config:** MISSING (key absent from qr_code config — not set to "none")
- **Expected behavior:** Agent surfaces the gap, asks user to choose a shortener

## Notes on Verification

The critical test: does the agent recognize that a missing `shortener` key is different from `"shortener": "none"`? The agent must NOT silently generate a QR with the raw URL. It must ask the user to configure a shortener or explicitly opt out.

Also verify: the shownotes URL uses the slug from `presentation-spec.md`, not an agent-invented slug.
