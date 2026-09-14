# Ingress End Report

This is the complete normative Step 11 contract for `vault-ingress`. The end
report is the speaker-facing text delivered in the conversation. Analyses, the
profile, badge JSON, and the obligations ledger supplement it; none of them is
the report. A run is not finished until the report is delivered and recorded.

## When

After Step 10, once the run's clarification obligation carries an explicit
disposition and any accepted session has completed (Step 9). `record-report`
refuses earlier so the report can carry a profile refresh the answers caused.
On a resumed run whose `pending` entry says `deliver_end_report`, compose the
report from the current database, summary, and profile state for that run's
recorded talks.

## Sections, in order

1. **Scope.** Every talk the run recorded, by title and filename, with its
   status: processed, processed partially, or skipped and why. Take the list
   from the run's ledger record and the Step 4 persist summaries.
2. **Findings.** The significant per-talk observations. A new presentation
   mode or instrument comes first and prominently; then consequential
   delivered-versus-planned differences and anything Step 5 changed in the
   rhetoric summary.
3. **Patterns and antipatterns.** The current classifications from the
   profile and Section 15, each with the evidence it rests on and its
   uncertainty. Name what could not be evaluated and why.
4. **Goals.** Each active goal's Step 8 outcome in the owner vocabulary
   (`achieved`, `improving`, `stalled`, `regressed`, `needs_rebaseline`,
   `unverifiable`), never paraphrased into a stronger verdict.
5. **Profile changes.** The Step 7 diff plus any refresh after clarification,
   or an explicit "profile unchanged" or "no profile exists" line.
6. **Badges.** Every badge added this run with the evidence behind it, or an
   explicit "no new badges" line. Badges come from the non-pattern lane only.
7. **Clarification outcome.** What was offered, the speaker's disposition,
   and, when a session ran, what it confirmed or corrected.
8. **Artifacts.** Paths to the analyses, summary, and profile, as supplements.

## Provenance Restrictions

- A pattern-generation reset is never improvement or regression
  ([profile-construction-rules.md](../../vault-profile/references/profile-construction-rules.md),
  Generation reset).
- An unavailable comparison is reported as unavailable with its reason; never
  normalize denominators or pick a mixed cohort (Important Notes in
  `SKILL.md`; [processing-rules.md](processing-rules.md)).
- An unavailable trend or mode never erases an available mastery, recurrence,
  underuse, or combination classification; report what is available.
- Goal statuses are the Step 8 assessments verbatim.
- Section 15 prose never sources a classification or availability decision.
- The report is English ([rules/vault-language-policy.md](../../../rules/vault-language-policy.md)).

## Deliver, Then Record

Deliver the report in the conversation, write the same text to a file, and
record it:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/run-obligations.py" \
  "{vault_root}/tracking-database.json" record-report \
  --run-id "{run_id}" --now "{iso_timestamp}" --report-file "{delivered_report_path}"
```

Exit 0 copies the text to `{vault_root}/ingress-reports/{run_id}.md`, binds it
by digest, and stamps the run complete. Exit 2 with `invalid_transition` means
the clarification obligation is unresolved; return to Step 9. Exit 2 with
`report_empty` means a placeholder was passed; the report is the delivered
text. Ledger shape and reason codes: [schemas-obligations.md](schemas-obligations.md).
