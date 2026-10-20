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

On `ok: false` (exit 1) with `reason_code: database_generation_conflict`,
another writer changed the database mid-read: run the resolver once more
before anything else. On any other `ok: false`, stop publishing and invoke
`Skill(skill: "vault-ingress")` with this repair-only handoff as context:
`runtime_repair: {reason_code: "{reason_code}", lane: "outline", database:
"{database}"}`, where `database` is the failure's absolute locator. That entry
runs only the repair the code names, against that database alone, and returns
without starting an ingest. When it returns, run the resolver once more with
`--database "{database}"` and continue with Step 1 on `ok: true`. When the
repair reports nothing it could fix, or the resolver refuses again, finish here
and report the `reason_code`. Never fall back to whichever `python3` is on
`PATH`.

The checks the resolver composes, and its reason codes, are its own contract:
see `skills/shownotes-publisher/scripts/resolve-runtime.py` (module docstring).
