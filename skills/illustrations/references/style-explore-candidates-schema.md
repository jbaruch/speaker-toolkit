# Style-Explore Schema

`--style-explore` has two artifacts: `candidates.json` (input the agent writes)
and `rendered.json` (output the script writes). One doc owns both.

- **Owner skill**: illustrations (Step 8 — Render the Exploration Grid)
- **Location**: both live in `style-explore/` in the talk working directory

## candidates.json — input

- **Writers**: the catalog owner script emits v2 from selected catalog entries;
  legacy agent-authored v1 files remain readable. Both follow Step 7 proposals
  and the Step 6 model shortlist.
- **Reader**: `generate-illustrations.py --style-explore`

## Legacy schema (schema_version 1)

```json
{
  "schema_version": 1,
  "slides": { "FULL": 7, "IMG+TXT": 12 },
  "models": ["gemini-3-pro-image", "gemini-3.1-flash-image"],
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

The reader accepts legacy v1 and catalog-backed v2 — other versions are refused.
`candidates.json` is a transient per-talk input, not a persisted record, so
there is no on-read migration. A future schema change bumps the version and
teaches the reader to handle the new shape.

## Catalog-backed schema (schema_version 2)

The root has exactly `schema_version: 2`, `slides`, `models`, and `styles`.
Every style is a complete closed catalog-v1 entry plus its versioned
`catalog_source` receipt. The entry retains both anchors, conventions,
composition, text treatment, tags, sample, and provenance; none is dropped
during projection. The exact shape, bounds, and selection command are owned by
[skills/illustrations/references/style-catalog.md](style-catalog.md).

The generator validates the v2 shape before loading credentials or rendering.
One grid uses one composition; posters use FULL only, require an actual
representative-slide `text_overlay`, and reject safe zones. Poster prompts use
the candidate's text treatment, not a previously baked style's lettering. The
normal compose-only guard and render-before-bake gate still apply. Reads of
either version do not migrate or rewrite the input.

## rendered.json — output

- **Writer**: `generate-illustrations.py --style-explore` (`write_rendered_manifest`)
- **Readers**: `generate-illustrations.py --check-style-explore` and the
  `run_generate` / `run_build` render-before-bake guards; strategy consumers use
  the `--check-style-explore` verdict, not their own manifest parser
- **Purpose**: the machine-readable record of what actually rendered, so the gate
  can confirm a baked model was rendered. `index.md` is the human contact sheet;
  `rendered.json` is the gate's source of truth.

```json
{
  "schema_version": 2,
  "outline": "outline.yaml",
  "outline_dir": "devnexus26-robocoders",
  "rendered_at": "2026-06-08T12:00:00Z",
  "models_rendered_ok": ["gemini-3-pro-image"],
  "cells": [
    {"style": "Blueprint Schematic", "format": "FULL",
     "model": "nano-banana-pro", "model_resolved": "gemini-3-pro-image",
     "status": "OK", "rel_path": "blueprint-schematic/full/gemini-3-pro-image.png",
     "provenance": {
       "lane": {"family": "gemini", "lane": "api", "operation": "generate",
                "requested_model": "gemini-3-pro-image", "served_model": "gemini-3-pro-image",
                "geometry": "requested", "reason_code": "family_api_only",
                "binary": null, "version": null},
       "width": null, "height": null, "sha256": null, "warning_count": 0}},
    {"style": "Blueprint Schematic", "format": "FULL",
     "model": "gpt-image-2", "model_resolved": "gpt-image-2-2026-04-21",
     "status": "FAIL", "error": "rate limited", "provenance": null}
  ]
}
```

Fields:

- `outline` — outline filename; `outline_dir` — talk-directory name. Together a
  per-talk discriminator.
- `models_rendered_ok` — human-readable summary of successful **served** model
  identities, not a list of bake-eligible requested models.
- `cells` — one entry per rendered cell: `model` / `model_resolved` (codenames
  resolve via the registry alias map), `format`, `style`, `status`, and `rel_path`
  (relative to `style-explore/`) or `error`, plus `provenance`.
- `provenance` — `null` for a failure before selection; otherwise `lane` carries
  the dispatch plan's fields shown above. `width`, `height`, and `sha256` are
  populated from verified native output, or `null` when unavailable. API output
  keeps its existing adapter contract; these fields do not invent an inspection.
  `warning_count` is a non-negative integer counting native non-fatal item
  diagnostics, also announced on stderr; API outcomes use zero.
- Native `lane: cli` uses served model `codex-native-image-model-unpinned`,
  `geometry: native_observed`, and the resolved absolute binary/version. Such a
  cell cannot prove a dated API model, even if `model_resolved` names one.

The writer emits v2. The reader accepts historical API-only v1 and v2 during the
additive rollout; reading either version is read-only. V1 has no native cells,
so its historical model identity remains usable subject to existing live-file
checks. V2 never infers absent provenance. The next owner `--style-explore` run
replaces its prior grid manifest with v2 from actual new render outcomes; no
reader stamps old images with guessed native metadata. Missing, malformed, or
future versions provide no usable prior state and return an actionable failure.
Other skills must not rewrite this artifact or initiate a paid rerender merely
to migrate it.

The render-before-bake gate's eligibility predicate — which cells count, the
live-file evidence check, path containment, and the per-talk copied/stale
checks — is owned by `generate-illustrations.py` `check_style_explore` (the source
of truth); it is deliberately not restated here. The render overwrites
`rendered.json` each run (idempotent), so it always reflects the latest grid.

The render also writes `style-explore/<style-slug>/<format-slug>/<model>.<ext>`
per cell and `style-explore/index.md`, a contact sheet grouped by style linking
each rendered image.
