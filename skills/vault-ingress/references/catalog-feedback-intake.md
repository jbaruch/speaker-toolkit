# Catalog Feedback Intake

`skills/vault-ingress/scripts/aggregate-catalog-feedback.py` is the deterministic,
offline intake gate between per-talk analysis and any human-authored catalog
change. It validates and aggregates feedback; it never edits pattern files,
the tracking database, returns, or the vault.

```bash
python3 skills/vault-ingress/scripts/aggregate-catalog-feedback.py \
  reparse/returns batch-returns.json \
  --catalog skills/presentation-creator/references/patterns
```

Inputs may be:

- one per-talk return object;
- an array of return objects, such as `batch-returns.json`;
- a wrapper with a `returns` array;
- a prior feedback-harvest wrapper whose return items use `feedback` instead of
  `catalog_feedback`; or
- one or more directories, searched recursively for `*.json`.

Concrete files are resolved, sorted, and de-duplicated before reading. Passing a
directory and a file already inside it cannot double the recurrence counts.
No network access is performed.

## The five lanes

`catalog_feedback` is an object whose values are arrays. It may omit empty lanes,
but it may not invent a sixth lane.

| Lane | Required shape | Meaning |
|---|---|---|
| `unmatched_observations` | `observation`, `why_no_pattern_fits`; optional `proposed_name`; `proposed_polarity` when a name is proposed | An observed move for which no exact catalog ID fits |
| `tensions` | at least two distinct exact `pattern_ids`, `nature`, `evidence` | Catalog entries that trade against or contradict one another |
| `definition_problems` | exact `pattern_id`, `problem`, `detail` | One existing entry whose definition cannot be applied reliably |
| `scoring_problems` | `issue`, `detail`; optional `polarity: neutral` | A score/model defect rather than a single catalog entry defect |
| `confusable_pairs` | exactly two distinct exact `pattern_ids`, `detail` | A pair whose boundary cannot be applied consistently |

All prose fields are nonempty strings. Extra evidence fields such as `example`,
`proposed_fix`, or source-specific detail are retained unchanged. An entry with
three or more confusable IDs is not a “pair”; split it into pairwise boundary
questions or move a multi-entry interaction to `tensions`.

## Polarity contract

The catalog file's YAML `id` and `type` are authoritative. `type` is `pattern`
or `antipattern`; the aggregator never guesses from an ID's spelling. In
particular, `anti-sell` is a positive pattern, while `ant-fonts` is an
antipattern. The output attaches the catalog-derived polarity to every exact ID.

Producers may assert the value as a guard:

- `catalog_polarity` on a one-ID `definition_problems` entry; or
- `catalog_polarities: {id: pattern|antipattern}` on a `tensions` or
  `confusable_pairs` entry. If supplied, its keys must exactly match
  `pattern_ids` and its values must agree with the catalog.

`unmatched_observations[].proposed_polarity` says whether a proposed new name is
a `pattern` or `antipattern`. New producers must include it whenever
`proposed_name` is present. Legacy feedback without it remains accepted and is
marked `unspecified` plus a warning so old findings stay reviewable. Invalid
values are rejected. If the same normalized suggestion is asserted with both
polarities across returns, the aggregate report fails with
`suggestion_polarity_conflict`.

Catalog loading itself validates duplicate IDs, missing/invalid frontmatter, and
the `_anti_*.md` filename/type convention. These are reported only; no catalog
file is repaired automatically.

## Exact IDs versus suggestions

Exact references are never normalized. Whitespace, casing changes, invented
IDs, and duplicate IDs in one entry are invalid. `exact_catalog_ids` groups only
validated catalog references and reports:

- catalog polarity and source file;
- occurrence count;
- distinct talk count;
- distinct source-return count;
- count by feedback lane; and
- every source/talk/entry provenance record.

Free-text `proposed_name` values are a different namespace. They are normalized
with Unicode NFKC, case-folding, and punctuation/space/underscore-to-hyphen
folding; meaning is not guessed. Thus `Fresh Move`, `fresh_move`, and
`fresh-move!` recur under `fresh-move`, while synonyms remain separate.
`normalized_suggestions` reports variants, polarity state, the same three
recurrence counts, and provenance. A suggestion normalizing to an existing exact
catalog ID is invalid rather than silently folded into the catalog-ID group.

Recurrence is evidence for human triage, not permission to edit. No count—large
or small—automatically adds, deletes, renames, or changes a pattern.

## Provenance

Every accepted or invalid entry carries:

```json
{
  "source_path": "/absolute/path/to/return.json",
  "source_return_index": 0,
  "talk_filename": "talk.md",
  "talk_id": null,
  "feedback_lane": "definition_problems",
  "feedback_entry_index": 2
}
```

`filename` is preferred as talk identity; `talk_id` is the fallback. A feedback
return with neither is invalid. Counts expose both distinct talks and distinct
source returns because the same talk may legitimately have multiple analysis
revisions. The raw feedback object is retained beside provenance.

## Accepted, rejected, and invalid inputs

The report classifies each concrete file exactly once:

- `accepted` — recognized return document with at least one feedback-bearing
  return and no invalid return/lane/entry;
- `rejected` — valid JSON that is not a return document, a recognized return
  without `catalog_feedback`, an empty return array, or a directory with no JSON;
- `invalid` — unreadable/non-UTF-8/malformed JSON, malformed return or feedback
  shape, unsupported lane, or invalid feedback entry.

For a mixed batch, valid entries are still aggregated and retain provenance, but
the concrete input is classified `invalid`; nothing is silently discarded.
Returns are independently classified under `returns`, and entry problems live
under `entries.invalid`.

Exit `0` means there are no invalid catalog files, inputs, feedback entries, or
cross-return polarity conflicts. Warnings and rejected non-feedback documents do
not make the report fail. Exit `1` means human repair/triage is required. Argparse
errors use exit `2` and still emit a JSON error object.

## Stable report (schema v1)

The report contains no clock time or generated UUID. Inputs, provenance,
validation findings, variants, and groups have deterministic sorts; stdout uses
sorted JSON keys. Important sections are:

```json
{
  "schema_version": 1,
  "ok": true,
  "read_only": true,
  "catalog": {"id_count": 111, "pattern_count": 83, "antipattern_count": 28},
  "input_summary": {"accepted": 3, "rejected": 1, "invalid": 0},
  "return_summary": {"accepted": 5, "rejected": 1, "invalid": 0},
  "entry_summary": {"accepted": 27, "invalid": 0, "warnings": 2},
  "lane_summary": {},
  "exact_catalog_ids": [],
  "normalized_suggestions": [],
  "inputs": {"accepted": [], "rejected": [], "invalid": []},
  "returns": {"accepted": [], "rejected": [], "invalid": []},
  "entries": {"accepted": [], "invalid": []},
  "validation": {"errors": [], "warnings": []}
}
```

Consumers route on codes and structured fields, never message prose. The report
is deliberately review material, not a patch plan.
