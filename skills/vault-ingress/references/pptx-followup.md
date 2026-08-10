# PPTX Follow-up and Visual Finalization

This is the complete normative Step 6 contract for `vault-ingress`. It covers
post-batch PPTX selection, bounded extraction, current-schema admission,
rendered-page evidence, matching, and cross-talk visual updates.

Runs once after all Step 3 batches have completed.

Process exactly the PPTX files `classify-pptx-evidence.py` reports as
`needs_extraction` — no additional predicate. Unmatched entries and PDF-primary
talks with a PPTX are already covered: a deck with no current receipt reports
`pending`, so adding them separately can only re-extract a record the
classifier already proved current. Selection is never a boolean read: a stale,
legacy, or unverifiable record can carry `visual_extracted: true` and still
need extraction — see
[bootstrap-and-preflight.md](bootstrap-and-preflight.md) for the command and its
output contract. Use the bounded directory invocation from that same reference
and select the root-relative results it names; do not replace it with
`**/*.pptx` or a shell/per-file extraction loop. Reuse the exact config-derived `{template_skip_arguments}` and
`{directory_exclusion_arguments}` (including zero arguments for either empty
array), keep the explicit `--directory` flag, preserve every bounded skip
receipt, and never admit a `~$` Office lock file. Require the public schema-v1
`pptx_directory_batch` envelope. Safely extracted results from a partial batch
remain usable, but only `complete: true` authorizes a full-catalog conclusion,
a claim that a missing deck does not exist, or absence inferred from an empty
result. Legacy unversioned batch output has unknown completeness and must be
rerun before any such claim.
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
Configured `pptx_directory_exclusions` prune a real directory only by
case-insensitive exact component identity after symlink/reparse rejection; they
do not match substrings or authored file names. Preserve the single
`pptx_batch_directory_excluded` receipt and do not scan below it.
Some talks have multiple .pptx files
(one per delivery) — match to the closest date.

After 3+ extractions, populate `slide-design-spec.md`; after 5+, analyze cross-talk
patterns (colors, fonts, footers).
