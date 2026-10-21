# Task-Specific Pattern Discovery

Use the compact menu for authoring, guardrails, slide design, and delivery
preparation. The full catalog index also carries evidence/scoring contracts for
ingress; those contracts are not required to select a rhetorical instrument.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/pattern-menu.py" --phase architecture
```

Select the current phase using the script's `--help`; use `--kind antipattern`
for the guardrail scan. Exit 0 emits `{phase, kind, workflow, catalog_root, entries}`;
each row has `id`, `name`, `path`, `summary`, and `observable`. Non-zero reports
the catalog repair on stderr with empty stdout. It performs no writes.

Read individual files under the returned catalog root only for relevant options,
selected patterns, or contextual warnings. Delivery preparation selects publishing
patterns; unobservable entries become reminders, never historical detections.

## Lifecycle Owners

The emitted `workflow` contains `skill`, `action`, and `step` for the selected
phase. A null `step` leaves context-dependent lane selection to the owner;
the builder selects its engine from the validated outline. Exact legacy labels
are accepted as phase input; `--help` lists them.
`pattern-menu.py` owns the mapping in `PHASE_WORKFLOWS` and `LEGACY_PHASE_ALIASES`.
For lifecycle work already requested, use `Skill(skill: "{workflow.skill}")`
with that action and step. A lookup alone authorizes no additional action.
Inside an already selected owner action, continue that action instead of
restarting from the broad lifecycle route. Preserve the caller's scope and
approvals; never resume a retired creator phase.
Go-live reminders, including Spaced Follow-Up under **Post-Event**, use the
current [delivery checklist](../../presentation-publisher/references/delivery.md).
The mapping remains outside the catalog's fingerprinted bytes.
See the [catalog fingerprint contract](../../vault-ingress/references/pattern-catalog-contract.md#report-contract).

## History Authorization

This is current taxonomy, not speaker history. Before consuming usage, mastery,
novelty, recurrence, or trend data, use
[pattern-history-authorization.md](pattern-history-authorization.md). A taxonomy
row cannot authorize a historical claim. The catalog index and pattern bytes
remain unchanged; the menu is generated on demand outside the fingerprinted tree.
