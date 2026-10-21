# Task-Specific Pattern Discovery

Use the compact menu for authoring, guardrails, slide design, and delivery
preparation. The full catalog index also carries evidence/scoring contracts for
ingress; those contracts are not required to select a rhetorical instrument.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/pattern-menu.py" --phase architecture
```

Select the current phase using the script's `--help`; use `--kind antipattern`
for the guardrail scan. Exit 0 emits `{phase, kind, catalog_root, entries}`;
each row has `id`, `name`, `path`, `summary`, and `observable`. Non-zero reports
the catalog repair on stderr with empty stdout. It performs no writes.

Read individual files under the returned catalog root only for relevant options,
selected patterns, or contextual warnings. Delivery preparation selects publishing
patterns; unobservable entries become reminders, never historical detections.

## Lifecycle Owners

Interpret the catalog's lifecycle labels through the current skill owners:

- `slides` and legacy Phase 5 labels refer to `Skill(skill: "presentation-builder")`.
- `publishing` and legacy creator Phase 6 labels refer to
  `Skill(skill: "presentation-publisher")`. Its Step 4 owns delivery preparation;
  the full publishing action includes that preparation when requested.
- Go-live reminders, including Spaced Follow-Up under **Post-Event**, belong to
  the publisher's [delivery checklist](../../presentation-publisher/references/delivery.md).

Use the current owner's requested action and approvals; never resume a retired
creator phase. This mapping lives outside the catalog's fingerprinted bytes.
See the [catalog fingerprint contract](../../vault-ingress/references/pattern-catalog-contract.md#report-contract).

## History Authorization

This is current taxonomy, not speaker history. Before consuming usage, mastery,
novelty, recurrence, or trend data, use
[pattern-history-authorization.md](pattern-history-authorization.md). A taxonomy
row cannot authorize a historical claim. The catalog index and pattern bytes
remain unchanged; the menu is generated on demand outside the fingerprinted tree.
