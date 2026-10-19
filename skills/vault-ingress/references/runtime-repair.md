# Runtime Repair

A repair-only entry into vault-ingress. Another skill's runtime resolver (the
shownotes publisher's `skills/shownotes-publisher/scripts/resolve-runtime.py`)
refused and invoked vault-ingress with a `runtime_repair` handoff carrying its
`reason_code` and the lane it needs. Run only the repair that code names, then
finish: never select a batch, reparse, or regenerate anything.

| `reason_code` | Repair |
|---|---|
| `database_not_current` | the owner migration, dry run then apply, in the "Schema gate" passage of [Bootstrap and Preflight](bootstrap-and-preflight.md) |
| `config_incomplete`, `interpreter_unusable`, `interpreter_not_absolute`, `interpreter_unsupported` | record an absolute interpreter, at least the Python version `check-runtime.py` names, that has the toolkit requirements as `config.python_path` through the owner `set_config` mutation, per that same passage |
| `runtime_lane_unavailable` | install the toolkit requirements into `config.python_path` |
| `runtime_lane_unresolved` | none to install: the imports never finished probing, which a cold interpreter on a network filesystem does; run the lane check below once to warm it |
| `database_mismatch` | none: the vault changed between the resolver's two reads; report that sync must settle |
| `owner_read_failed`, `runtime_probe_failed`, `resolver_failed` | none: report the resolver's `error` to the speaker |

Confirm an interpreter repair with the lane the handoff names (`outline` for
the shownotes publisher):

```bash
"{configured python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes "{lane}" --require-lanes "{lane}"
```

Report what was repaired, or why nothing was, and return to the caller.
