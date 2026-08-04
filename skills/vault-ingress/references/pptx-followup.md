# PPTX Follow-up and Visual Finalization

This is the complete normative Step 6 contract for `vault-ingress`. It covers
post-batch PPTX selection, bounded extraction, current-schema admission,
rendered-page evidence, matching, and cross-talk visual updates.

Runs once after all Step 3 batches have completed.

Process PPTX files not yet extracted during Step 3: unmatched catalog entries, talks
that used PDF as primary but have a PPTX available, or entries with
`pptx_visual_status: "pending"`. Skip if already `"extracted"`. Use the bounded directory invocation from
[bootstrap-and-preflight.md](bootstrap-and-preflight.md) and select the root-relative results that
remain pending; do not replace it with `**/*.pptx` or a shell/per-file extraction
loop. Reuse the exact config-derived `{template_skip_arguments}` (including zero
arguments for an empty array), keep the explicit `--directory` flag, preserve every
bounded skip receipt, and never admit a `~$` Office lock file.
Require schema v4 for current analysis. Regenerate v0-v3 output and stop on an
unknown future schema rather than interpreting missing fields as zero. When
rendered pages were inspected, rerun that selected deck as one supervised
single-artifact invocation with `--rendered-pdf <path.pdf>` and one or more
`--inspected-pages <PAGE|START-END>` arguments so the extraction receipt binds the
exact artifacts and covered pages. A non-empty `archive_recovery`
blocks a required native-deck claim until the source is restored or re-exported.
For every catalog finding or citation, OCR is affirmative only at the individual
receipt level: use `recovered_text` only when that same receipt has
`trustworthy_text: true`. Never promote `ocr_text` or an OCR channel's aggregate
`text` directly; both retain low-confidence text for review.

**PPTX matching rules:** The .pptx files are in `Conference/Year/TalkName.pptx` and
shownotes entries have `conference` and `title` fields. Fuzzy-match by: normalize
conference names (strip year, "Days", "Conference"), match by date proximity and title
substring. Skip Office locks beginning `~$`, files with "static" in name, conflict
copies matching `(N).pptx`, and files matching `config.template_skip_patterns`.
Some talks have multiple .pptx files
(one per delivery) — match to the closest date.

After 3+ extractions, populate `slide-design-spec.md`; after 5+, analyze cross-talk
patterns (colors, fonts, footers).
