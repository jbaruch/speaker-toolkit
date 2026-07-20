# Copilot code review — scope

This repository runs a separate policy reviewer (the `.github/workflows/review-codex.yml` workflow —
the OpenAI Codex CLI on a ChatGPT subscription — which reviews every PR against the installed
`jbaruch/coding-policy` rules). It owns conventions and policy. **Your job is the complementary lane: correctness and risk.**
Spend your review budget where the policy reviewer does not look.

## Review for
- Logic errors, wrong conditions, off-by-one, incorrect edge-case handling.
- Race conditions, ordering bugs, non-idempotent retries, lost updates.
- Resource leaks (unclosed files/connections), unbounded growth, needless recompute on hot paths.
- Missing or wrong error handling that lets a real failure pass silently or crash — not stylistic preference.
- Security: injection, unsafe deserialization, authz gaps, secrets in code or logs, unvalidated untrusted input.
- Test coverage gaps: a changed branch or failure path with no test; an assertion that would pass even if the code were wrong.

## Do NOT comment on (the policy reviewer owns these)
- Naming/style conventions, formatting, import order.
- Commit-message or PR-title format, changelog entries, branch naming.
- Rule/policy compliance, doc structure, skill/rule authoring conventions.
- Restating project rules — assume they are enforced by the policy reviewer.

## Repo facts (avoid false positives)
- Verify a tool's real semantics before flagging — prefer a missed bug over a confident false positive.
