# Processing Rules

## Language Policy — English Only

All analysis output, rhetoric summary updates, tracking DB entries, and profile data
MUST be written in English regardless of the talk's delivery language. For non-English talks:

- **Verbatim quotes**: ALWAYS write English translation FIRST, then the original in
  parentheses. Never the reverse. Format: `"English text" (оригинальный текст)`.
  Example: `"That's the whole point" (В этом весь смысл)` — NOT
  `"В этом весь смысл" (That's the whole point)`
- **Verbal signatures**: store separately tagged with language code (e.g.,
  `[ru] "получается что"`) — do NOT merge into the main English signature list
- **Slide text**: translate in the analysis, note original language
- **Humor/wordplay**: note when a joke is language-dependent and untranslatable
- Tag the talk entry with `delivery_language` in the tracking DB

## Pattern Taxonomy Migration

If the pattern taxonomy exists (`skills/presentation-creator/references/patterns/_index.md`)
but any talks with status `"processed"` or `"processed_partial"` have no
`pattern_observations` (or `pattern_observations.pattern_ids` is empty), mark them
`"needs-reprocessing"` with `reprocess_reason: "pattern_scoring_added"`. Report:
"N talks need reprocessing for pattern scoring."

## Pattern Tagging Rules

Scan observations against the pattern taxonomy index at
`skills/presentation-creator/references/patterns/_index.md` (path relative to tile root).
Skip patterns marked `observable: false` — these are pre-event logistics and physical
stage behaviors that cannot be detected from transcripts or slides. For each observable
pattern/antipattern, determine if the talk exhibits it (strong/moderate/weak confidence),
record evidence, and compute per-talk pattern score:
count(patterns) − count(antipatterns). Return in the `pattern_observations` field.

## Structured Field Extraction

When the analysis identifies co-presenters, delivery language, or other structured
metadata, populate the corresponding DB fields (`co_presenter`, `delivery_language`,
etc.) — do NOT leave structured data buried only in `rhetoric_notes` free text.

Backfill empty `structured_data` from earlier runs using `rhetoric_notes`.
