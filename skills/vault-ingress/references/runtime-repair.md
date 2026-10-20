# Runtime Repair

A repair-only entry into vault-ingress. Another skill's runtime resolver (the
shared presentation/publishing `skills/shownotes-publisher/scripts/resolve-runtime.py`)
refused and invoked vault-ingress with a `runtime_repair` handoff carrying its
`reason_code`, the lane it needs, and the absolute `database` locator it read.
Run only the repair that code names, then finish: never select a batch,
reparse, or regenerate anything.

Every read, migration and `set_config` of this repair targets the handoff's
`database`, with `vault_root` set to its directory, never the default vault
locator. A handoff without `database` names no target: report that and finish.

| `reason_code` | Repair |
|---|---|
| `database_not_current` | the owner migration, dry run then apply, in the "Schema gate" passage of [Bootstrap and Preflight](bootstrap-and-preflight.md) |
| `config_incomplete`, `interpreter_unusable`, `interpreter_not_absolute`, `interpreter_unsupported` | record an absolute interpreter, at least the Python version `check-runtime.py` names, that has the toolkit requirements as `config.python_path` through the owner `set_config` mutation, per that same passage |
| `runtime_lane_unavailable` | install the toolkit requirements into `config.python_path` |
| `runtime_lane_unresolved` | none to install: the imports never finished probing, which a cold interpreter on a network filesystem does; run the lane check below once to warm it |
| `database_mismatch`, `database_generation_conflict` | none: the vault changed while the resolver read it; report that sync must settle |
| `owner_read_failed`, `runtime_probe_failed`, `vault_root_invalid`, `resolver_failed` | none: report the resolver's `error` to the speaker; it carries the owner's remedy when `owner_code` is present |

Confirm an interpreter repair with the lane the handoff names (`outline` for
schema consumers, `core` for text/export tasks):

```bash
"{configured python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes "{lane}" --require-lanes "{lane}"
```

Report what was repaired, or why nothing was, and return to the caller.
