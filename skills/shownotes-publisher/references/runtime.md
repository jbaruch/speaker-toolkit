# Runtime Selection

Resolve the configured interpreter before any other toolkit command. Read the
tracking database once through the stdlib-only owner reader:

```bash
"{host_python}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/read-tracking-database.py" \
  "~/.claude/rhetoric-knowledge-vault/tracking-database.json"
```

Use its JSON report to resolve `vault_root` from `database.config.vault_root`
and the exact non-empty `database.config.python_path`. Set `python_path` to
that value, then repeat the same owner read with `"{python_path}"` and
`{vault_root}/tracking-database.json`; require its database and SHA-256 to
match the first report. The unconfigured `host_python` is authorized for that
one owner-reader invocation only. Then require the core lane, which carries the
PyYAML the outline and verifier scripts import:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core --require-lanes core
```

`python_path` is the interpreter for every later toolkit command in this skill
and its references. If it is absent, empty, mismatched, or fails the probe,
stop and invoke `Skill(skill: "vault-ingress")` with Step 1 as the handoff
context. Never fall back to whichever `python3` is on `PATH`.
