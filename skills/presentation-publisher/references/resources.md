# Resource Curation

Extract and curate resource links from the finalized outline before any
publishing step. Resources scattered across speaker notes, visual descriptions,
and Coda slides are easy to miss — this step catches them systematically.

1. Run the extraction script against `outline.yaml`:
   ```bash
   "{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/extract-resources.py" outline.yaml
   ```

2. The script produces `resources.json` in the talk working directory with
   categorized entries: URLs, repos, books/papers, RFCs, and tool mentions.
   Each entry includes slide references and context.

3. Present the extracted resources to the speaker as a formatted review list,
   grouped by type. Coda section items are flagged and listed first — the
   speaker deliberately chose to surface them.

4. The speaker reviews, approves, removes false positives, adds missing items,
   and edits entries. Save the approved list back to `resources.json` with
   `approved: true` on accepted items.

5. For a full publishing workflow or a requested tracking update, re-resolve the
   runtime without `--read-only` before persistence. An extraction-only request
   finishes with the approved local `resources.json` and makes no tracking write.
   For a tracking update, persist a complete `resources[]` entry with `schema_version: 1`, the talk slug,
   item count, and category breakdown through the ingress owner's `upsert_resource` mutation.
   Expect the exact existing record for the slug, or `{"$missing": true}` for a
   first entry. Dry-run, review, apply against the reported input SHA, and re-read
   as specified by the
   [owner mutation contract](../../vault-ingress/references/schemas-db.md#owner-read-and-mutation-contract).

If the speaker declines resource gathering, skip this step — shownotes publication will
omit the resource links section from shownotes.
