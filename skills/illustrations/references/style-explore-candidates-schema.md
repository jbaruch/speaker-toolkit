# Style-Explore Schema

`--style-explore` has two artifacts: `candidates.json` (input the agent writes)
and `rendered.json` (output the script writes). One doc owns both.

- **Owner skill**: illustrations (Step 8 — Render the Exploration Grid)
- **Location**: both live in `style-explore/` in the talk working directory

## candidates.json — input

- **Writer**: the agent, after proposing candidate styles (Step 7) and computing
  the model shortlist (Step 6)
- **Reader**: `generate-illustrations.py --style-explore`

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

Only `schema_version` 1 is accepted today — the reader rejects any other value.
`candidates.json` is a transient per-talk input, not a persisted record, so
there is no on-read migration. A future schema change bumps the version and
teaches the reader to handle the new shape.

## rendered.json — output

- **Writer**: `generate-illustrations.py --style-explore` (`write_rendered_manifest`)
- **Readers**: `generate-illustrations.py --check-style-explore` and the
  `run_generate` render-before-bake guard
- **Purpose**: the machine-readable record of what actually rendered, so the gate
  can confirm a baked model was rendered. `index.md` is the human contact sheet;
  `rendered.json` is the gate's source of truth.

```json
{
  "schema_version": 1,
  "outline": "presentation-outline.md",
  "outline_dir": "devnexus26-robocoders",
  "rendered_at": "2026-06-08T12:00:00Z",
  "models_rendered_ok": ["gemini-3-pro-image-preview"],
  "cells": [
    {"style": "Blueprint Schematic", "format": "FULL",
     "model": "nano-banana-pro", "model_resolved": "gemini-3-pro-image-preview",
     "status": "OK", "rel_path": "blueprint-schematic/full/gemini-3-pro-image-preview.png"},
    {"style": "Blueprint Schematic", "format": "FULL",
     "model": "gpt-image-2", "model_resolved": "gpt-image-2",
     "status": "FAIL", "error": "rate limited"}
  ]
}
```

- `cells` — one entry per rendered cell; `model_resolved` is the canonical id the
  gate compares against (codenames resolve via the registry alias map).
- The gate does NOT trust `models_rendered_ok`. It derives the eligible set from
  `cells` with `status == "OK"` whose `rel_path` image file still exists on disk
  under `style-explore/` — a stale or hand-edited manifest listing a model with
  no backing file does not pass (per `rules/stateful-artifacts.md`: verify against
  the live source). `models_rendered_ok` remains a human-readable summary.
- `outline` (basename) and `outline_dir` (talk-directory name) are both checked
  against the current talk; a grid copied from another talk fails closed even when
  the outline filename matches.
- The render overwrites `rendered.json` each run (idempotent), so it always
  reflects the latest grid.
- The gate checks the model only, not anchor text — editing an anchor paragraph
  without re-rendering still passes; the gate's job is "model came from a render."

The render also writes `style-explore/<style-slug>/<format-slug>/<model>.<ext>`
per cell and `style-explore/index.md`, a contact sheet grouped by style linking
each rendered image.
