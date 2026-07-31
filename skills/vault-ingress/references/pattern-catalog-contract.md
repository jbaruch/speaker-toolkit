# Pattern Catalog Graph Contract

Run the catalog auditor before selecting or re-analyzing talks:

```bash
python3 skills/vault-ingress/scripts/audit-pattern-catalog.py
```

Pass `--catalog <patterns-directory>` to inspect another catalog. The command
uses local Markdown and YAML only. It does not use the network or modify any
file. Stdout is one deterministic JSON document. Exit `0` means no structural
errors, exit `1` means the catalog contract is broken, and argument errors use
exit `2`.

## Authority boundaries

- `_index.md` owns the complete public inventory and lifecycle placement.
- Only the catalog-root `_index.md` is reserved; every other Markdown file
  under the catalog tree is audited and fingerprinted as an entry.
- Entry frontmatter owns machine-readable identity, polarity, observability,
  evidence gates, graph declarations, and aliases.
- YAML mapping keys must be unique at every nesting level. The catalog
  consumers reject duplicates instead of accepting PyYAML's last value.
- `evaluable_from` is an OR list. String items are singleton alternatives;
  nested lists are conjunctive alternatives whose underlying sources must all
  be present with `source_comparison` evidence.
- Entry prose owns definitions, boundaries, examples, and semantic intent.
- `inverse_of` is symmetric. Either endpoint may originate the assertion, but
  both endpoints must declare it.
- `related_patterns` is directional and curated. Reciprocity is not implied.
- Scoring uses a direct scale. Strong means the named pattern or antipattern is
  present; absent means it is not present.

The exact namespaces, parsing rules, and scoring labels live in
`skills/vault-ingress/scripts/audit-pattern-catalog.py` under the named
top-of-file constants and `normalize_alias`.

## Report contract

The top-level shape is:

```json
{
  "schema_version": 1,
  "valid": true,
  "catalog": {
    "path": "skills/presentation-creator/references/patterns",
    "index": "_index.md",
    "fingerprint": "sha256"
  },
  "summary": {
    "entries_loaded": 111,
    "errors": 0,
    "semantic_debts": 0
  },
  "errors": [],
  "semantic_debts": [],
  "graph": {
    "related_edges": [],
    "inverse_declarations": [],
    "alias_namespace": []
  }
}
```

All issue objects carry the same keys: `code`, `entry_id`, `field`, `message`,
`path`, and `related_id`. Arrays, graph edges, issue codes, and summary maps are
sorted. The fingerprint is shared with ingress return validation and covers
the exact bytes of the catalog-root `_index.md` plus every recursive Markdown
entry in relative-path order. The root index is not an entry; a nested
`_index.md` is both fingerprinted and audited as an invalid entry file. An
index-only edit therefore changes the fingerprint persisted for an ingress
return. The report has no timestamp or run-specific identifier.

## Structural errors

The `errors` lane contains mechanically decidable contract failures:

- Index and file inventories disagree or repeat an ID or checklist entry.
- Index dimensions or creator phases are empty, out of range/namespace, or
  duplicated; index related-ID lists may be empty but may not repeat an ID.
- Filename, ID, directory, lifecycle part, index kind, or polarity disagree.
- Frontmatter contains invalid YAML or repeats a mapping key at any depth.
- An evidence-source alternative is empty, duplicated, unknown, or uses
  `source_comparison` as an underlying member of a conjunctive alternative.
- Frontmatter lists or creator-phase values violate their declared shape.
- Observable state and source-gate metadata/prose are incompatible.
- Related or inverse references are dangling, duplicated, or self-referential.
- An inverse declaration is not reciprocal.
- Direct scoring labels are missing, duplicated, or polarity-inverted.
- IDs, names, or explicit aliases collide after catalog normalization.
- The index go-live checklist disagrees with `observable: false`.

Do not start ingress while `valid` is false. Fix only facts whose authority is
already explicit. Mirroring the other endpoint of an existing inverse
declaration is structural repair; inventing a new inverse is a semantic edit.

## Semantic debt

The `semantic_debts` lane records deterministic disagreements whose repair
requires judgment. Current examples include display-name, dimension, creator
phase, or related-list drift between the compact index and detailed entry, plus
an inverse declaration joining entries with the same polarity.

Semantic debt does not change the exit status. Present it for human review with
both source values. Do not choose an authority, rewrite prose, add aliases, or
change semantic relationships automatically. A repeated or popular suggestion
is evidence for review, not authorization to edit the catalog.

## Repair sequence

1. Preserve the first JSON report as review evidence outside the catalog.
2. Repair objective schema errors without changing semantic meaning.
3. Re-run until `valid` is true and the fingerprint reflects the repaired tree.
4. Present `semantic_debts` separately to the speaker or catalog owner.
5. Apply approved semantic decisions manually and re-run the audit.

The auditor never supplies an apply mode. Catalog changes remain reviewable
Markdown edits with their own tests and diff.
