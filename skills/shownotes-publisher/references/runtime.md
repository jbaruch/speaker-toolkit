# Runtime Selection

Set `host_python` to the current host's explicit absolute interpreter path (not
a PATH lookup). The resolver below is stdlib-only, and `host_python` runs it and
nothing else. Resolve the configured interpreter before any other toolkit
command:

```bash
"{host_python}" "{speaker_toolkit_root}/skills/shownotes-publisher/scripts/resolve-runtime.py"
```

Input: optional `--database <path>`, defaulting to the documented vault locator
`~/.claude/rhetoric-knowledge-vault/tracking-database.json`.

Output: one JSON object on stdout. On `ok: true` (exit 0), set `python_path` and
`vault_root` from it (the root is the database locator's directory, never
`config.vault_root`); every later Python toolkit command in this skill and its
references runs on `"{python_path}"`. Shell scripts keep the `bash` invocation
their step shows.

On `ok: false` (exit 1), stop publishing and run only the repair its
`reason_code` names. Each repair is one section of vault-ingress's own
reference, never the vault-ingress workflow, which would start an ingest:

| `reason_code` | Repair |
|---|---|
| `database_not_current` | the owner migration, dry run then apply, in the "Schema gate" passage of `skills/vault-ingress/references/bootstrap-and-preflight.md` |
| `config_incomplete`, `interpreter_unusable`, `interpreter_not_absolute` | record an absolute interpreter that has the toolkit requirements as `config.python_path` through the owner `set_config` mutation, per that same passage |
| `runtime_lane_unavailable` | install the toolkit requirements into `config.python_path` |
| `database_mismatch` | none: the vault changed between the two reads; wait for sync to settle |
| `owner_read_failed`, `resolver_failed` | none here: report `error` to the speaker |

Before retrying, confirm an interpreter repair with the lane the publisher
needs:

```bash
"{configured python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes outline --require-lanes outline
```

Then run the resolver once more and continue with Step 1 on `ok: true`. When
the repair has no action, does not complete, or the resolver refuses again,
finish here and report the `reason_code`. Never fall back to whichever
`python3` is on `PATH`.

The checks the resolver composes, and its reason codes, are its own contract:
see `skills/shownotes-publisher/scripts/resolve-runtime.py` (module docstring).
