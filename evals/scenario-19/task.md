# QR Code Generation with Background Color Matching

## Problem/Feature Description

A speaker has a 4-slide PowerPoint deck for their talk "The Arc of AI". The closing slide (slide 4) has a purple (#5B2C6F) background. Slide 3 contains the shownotes URL `https://jbaru.ch/arc-of-ai` as visible text.

The speaker wants a QR code inserted on the closing slide that:
- Encodes the shownotes URL
- Matches the purple background so it blends visually
- Uses a contrasting foreground color (white, since purple is dark) so the QR is scannable
- Is placed in the bottom-right corner

The speaker's profile specifies `shortener: "none"`, so no URL shortening is needed — the raw shownotes URL is encoded directly.

Using the presentation-creator skill, generate the QR code and insert it into the deck. The tracking database should be updated with the QR metadata.

## Output Specification

Produce the following files:

1. **`deck-with-qr.pptx`** — The deck with the QR code inserted on the closing slide (slide 4).
2. **`arc-of-ai-qr.png`** — The QR code PNG file (should have purple background, white foreground).
3. **`tracking-database.json`** — Updated tracking database with a `qr_codes[]` entry for this talk.
4. **`verification-report.md`** — A report documenting:
   - Which script was used
   - The QR URL decoded from the PNG
   - The background color detected from the slide
   - The foreground/background colors used for the QR
   - Whether the QR was inserted on the correct slide
   - The tracking database entry

## Input Files

Download the base deck and vault fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-19"
mkdir -p inputs/vault
curl -L -o inputs/base-deck.pptx "$BASE/base-deck.pptx"
curl -L -o inputs/vault/speaker-profile.json "$BASE/speaker-profile.json"
curl -L -o inputs/vault/secrets.json "$BASE/secrets.json"
curl -L -o inputs/vault/tracking-database.json "$BASE/tracking-database.json"
```

Then copy the deck to the working directory before processing:
```bash
cp inputs/base-deck.pptx deck-with-qr.pptx
```

## Key Parameters

- **Talk slug:** `arc-of-ai`
- **Shownotes URL:** `https://jbaru.ch/arc-of-ai`
- **Shortener:** `none` (raw URL encoded directly)
- **Target slide:** closing (last slide, index 3)
- **Expected slide background:** purple `#5B2C6F` (solid fill, set at slide level)
- **Expected QR foreground:** white (because purple has low luminance)
- **Expected QR background:** purple (bg_color_match is true)

## Notes on Verification

The QR PNG can be decoded with `pyzbar` or `zbarimg` to verify it encodes the expected URL. The quiet zone (border area) pixels should match the purple background color. The foreground modules should be white because the purple background's WCAG relative luminance (~0.065) is below 0.5.
