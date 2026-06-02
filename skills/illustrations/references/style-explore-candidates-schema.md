# Style-Explore Candidates Schema

`candidates.json` is the input the agent writes during Phase 2 style strategy
and `generate-illustrations.py --style-explore` reads to render the
exploration grid.

- **Owner skill**: illustrations (Step 3 — Define Style Strategy)
- **Writer**: the agent, after proposing candidate styles and computing the
  model shortlist
- **Reader**: `generate-illustrations.py --style-explore`
- **Location**: `style-explore/candidates.json` in the talk working directory

## Schema (schema_version 1)

```json
{
  "schema_version": 1,
  "slides": { "FULL": 7, "IMG+TXT": 12 },
  "models": ["gemini-3-pro-image-preview", "gemini-3.1-flash-image-preview"],
  "styles": [
    {
      "name": "Blueprint Schematic",
      "anchors": {
        "FULL": "Full-bleed style anchor paragraph for this style.",
        "IMG+TXT": "Portrait anchor paragraph for this style."
      }
    }
  ]
}
```

## Fields

- `schema_version` — integer, must be `1`. The reader rejects other values.
- `slides` — maps each format to one representative slide number from the
  outline. The render pulls that slide's scene prompt and substitutes each
  style's anchor for the `[STYLE ANCHOR]` token. A format whose slide has no
  image prompt in the outline is skipped with a warning.
- `models` — the shortlisted model ids (from `model_registry.py --shortlist`),
  best-first. Each is rendered for every style × format. Codenames resolve via
  the registry alias map before dispatch.
- `styles` — candidate styles. Each needs a `name` and an `anchors` map of
  format → anchor text. A style that omits a format is skipped for that format.

## Output

The render writes `style-explore/<style-slug>/<format-slug>/<model>.<ext>` per
cell plus `style-explore/index.md`, a contact sheet grouped by style linking
each rendered image. Migrations bump `schema_version`; the owner skill performs
the upgrade on read.
