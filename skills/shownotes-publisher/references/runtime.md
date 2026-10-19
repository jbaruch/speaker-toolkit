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
`vault_root` from it; every later toolkit command in this skill and its
references runs on `"{python_path}"`. On `ok: false` (exit 1), stop and invoke
`Skill(skill: "vault-ingress")` with the reported `handoff` as context;
`reason_code` and `error` name what failed. Never fall back to whichever
`python3` is on `PATH`.

The checks the resolver composes, and its reason codes, are its own contract:
see `skills/shownotes-publisher/scripts/resolve-runtime.py` (module docstring).
