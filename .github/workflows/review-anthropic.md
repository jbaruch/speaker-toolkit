---
name: PR Policy Review (Anthropic)
description: |
  Reviews every same-repo pull request against the latest published
  `jbaruch/coding-policy` rule set, using an Anthropic-family reviewer model.
  Pairs with `review-openai.md`; each workflow self-gates to skip PRs
  authored by its own family so the active reviewer is cross-family
  whenever the declaration permits — when the declaration spans both
  paired families (e.g., `gpt-5.4 claude-opus-4-7`), or neither paired
  family (e.g., `gemini-2.5`, `human`-only), both reviewers run as the
  documented fallback. See `jbaruch/coding-policy: author-model-declaration`.

  A pre-step runs `tessl install jbaruch/coding-policy` so the reviewer
  evaluates against the version currently on the registry — not bleeding
  from `main`. Fork PRs are skipped by gh-aw's fork-guard. Posts up to 10
  inline comments plus one consolidated review verdict.

  Data flow / trust boundary: the reviewer sends the pull-request content
  it evaluates — the diff, the PR title, body, and commit messages (read
  for the author-model gate and the changed-file allowlist), and the
  published policy files — to the review model (Anthropic here; OpenAI in
  the paired workflow), the same provider whose model renders the verdict.
  Repository secrets, tokens, and credentials are never included in that
  payload. The `tessl install jbaruch/coding-policy` pre-step fetches the
  latest published plugin from the official Tessl registry — a known
  published ruleset, not arbitrary remote code.

  Required repository secrets (set at
  https://github.com/<owner>/<repo>/settings/secrets/actions):
    - ANTHROPIC_API_KEY — Claude Code engine authentication
    - TESSL_TOKEN       — tessl install authentication

  Project `.mcp.json` is neutralized at runtime: this workflow runs
  Claude with `--strict-mcp-config` (set under `engine.args` below) so
  the agent only loads the MCP servers gh-aw injects via its own
  `--mcp-config`. Any stdio MCP server the consumer repo declares in
  its checked-in `.mcp.json` is ignored, which sidesteps the awf
  sandbox's missing-binary failure that would otherwise kill the job.

on:
  # `edited` is intentional: the Step 1 self-review gate parses
  # `**Author-Model:**` from the PR body. If a contributor opens a PR without
  # the declaration (gate fails → REQUEST_CHANGES) and fixes it by editing
  # the body — without pushing a new commit — `opened/synchronize/reopened`
  # would not re-fire. `edited` lets the gate re-evaluate without a forced
  # empty commit.
  pull_request:
    types: [opened, synchronize, reopened, edited]
  skip-bots:
    - "dependabot[bot]"
    - "renovate[bot]"

# Runner-level self-review-bias gate (jbaruch/coding-policy#161). The
# `gate` job below resolves the PR's author-family before the agent runs;
# this `if:` skips the `agent` job — where the ~400K-token review spend
# lives — when the author-family is anthropic (this reviewer's own
# family), dropping the token cost to ~0. gh-aw composes the gate onto
# `agent`, so the cheap pre_activation/activation framework setup still
# runs; the token spend, not the seconds of slim-runner setup, is the
# target. The in-agent Step 1 stays as the fallback for cases the gate
# deliberately does not skip (a customized commit-attribution email or a
# display-name-only trailer). The gate runs its own `tessl install`
# because it is a separate job from the agent, so the published
# `author-family-gate.sh` / `resolve-author-family.sh` are not yet on
# disk when it runs.
if: needs.gate.outputs.should_skip != 'true'

permissions:
  contents: read
  pull-requests: read

jobs:
  gate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
    outputs:
      should_skip: ${{ steps.decide.outputs.should_skip }}
    steps:
      # continue-on-error keeps a Tessl setup/registry outage from FAILING
      # the gate job — a failed gate job cascade-skips the agent (needs:
      # gate) and silently drops the review. On failure the plugin is
      # simply absent, so `decide` below can't find the gate script and
      # defaults should_skip=false (agent runs). Fail-open end-to-end.
      - name: Install Tessl CLI
        uses: tesslio/setup-tessl@v2
        continue-on-error: true
        with:
          token: ${{ secrets.TESSL_TOKEN }}
      - name: Install jbaruch/coding-policy (latest published)
        continue-on-error: true
        run: |
          mkdir -p /tmp/gh-aw/coding-policy
          cd /tmp/gh-aw/coding-policy
          tessl install jbaruch/coding-policy --yes
      - id: decide
        env:
          PR_BODY: ${{ github.event.pull_request.body }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          GH_TOKEN: ${{ github.token }}
        # Fails OPEN: a failed gate job would cascade-skip the agent and
        # silently drop the review, so any trouble here defaults
        # should_skip=false and lets the agent run. The setup/install steps
        # above are continue-on-error, so a Tessl outage lands here as a
        # missing gate script → the `if` below fails → should_skip=false.
        # Explicit `if` checks (never silent suppression) keep exit at 0.
        run: |
          set -uo pipefail
          GATE=/tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/skills/install-reviewer/author-family-gate.sh
          commits="$(mktemp)"
          if ! gh pr view "$PR_NUMBER" --json commits -q '.commits[].messageBody' > "$commits"; then
            echo "author-family gate: 'gh pr view' failed; proceeding body-only" >&2
            : > "$commits"
          fi
          skip=false
          if out="$(printf '%s' "$PR_BODY" | bash "$GATE" --reviewer anthropic --policy-ref 'jbaruch/coding-policy: author-model-declaration' --commits-file "$commits")"; then
            echo "author-family gate: $out" >&2
            case "$(printf '%s' "$out" | jq -r .should_skip)" in true) skip=true ;; esac
          else
            echo "author-family gate: script errored; defaulting should_skip=false (agent will run)" >&2
          fi
          echo "should_skip=$skip" >> "$GITHUB_OUTPUT"

engine:
  id: claude
  model: claude-opus-4-7
  # `--strict-mcp-config` tells Claude Code to use ONLY the MCP servers
  # gh-aw injects via `--mcp-config`, ignoring any project-local
  # `.mcp.json` the consumer repo ships. Without this, Claude auto-loads
  # the consumer's `.mcp.json` inside the awf sandbox, attempts to launch
  # any stdio MCP server it declares (e.g., `tessl mcp start`), fails
  # because the binary isn't on the sandbox's PATH, and gh-aw fails the
  # whole job — even though the review itself ran cleanly. Closes
  # jbaruch/coding-policy#15. Requires gh-aw >= v0.71.0 (where
  # `engine.args` was added) and Claude Code CLI >= 2.1.x (where
  # `--strict-mcp-config` was added); the preflight already enforces
  # the gh-aw floor.
  args:
    - "--strict-mcp-config"
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

timeout-minutes: 15

network:
  allowed:
    - defaults

# Top-level `steps:` (NOT `pre-steps:`) — these run AFTER gh-aw's
# `Create gh-aw temp directory` step and BEFORE the agent executes. The
# install writes under `/tmp/gh-aw/coding-policy/`, which is the same
# canonical runtime path gh-aw uses for its own files (the agent reads
# its prompt from `/tmp/gh-aw/aw-prompts/prompt.txt`); the awf firewall
# sandbox makes that path reachable from inside the agent container.
# Two constraints have to hold simultaneously: (a) `actions/checkout`'s
# default `clean: true` wipes untracked workspace entries — rules out a
# workspace-local install — and (b) the awf sandbox doesn't mount the
# runner user's `${HOME}` — rules out `tessl install --global`.
# `/tmp/gh-aw/` satisfies both.
steps:
  - name: Install Tessl CLI
    uses: tesslio/setup-tessl@v2
    with:
      token: ${{ secrets.TESSL_TOKEN }}
  - name: Install jbaruch/coding-policy (latest published)
    run: |
      mkdir -p /tmp/gh-aw/coding-policy
      cd /tmp/gh-aw/coding-policy
      tessl install jbaruch/coding-policy --yes

tools:
  bash:
    - "cat"
    - "ls"
    - "head"
    - "tail"
    - "wc"
    - "grep"
    - "find"
    - "git diff *"
    - "git log *"
    - "git show *"
    - "gh pr diff *"
    - "gh pr view *"
    - "bash /tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/skills/install-reviewer/resolve-author-family.sh *"
  github:
    toolsets: [pull_requests]

safe-outputs:
  create-pull-request-review-comment:
    max: 10
    side: RIGHT
  submit-pull-request-review:
    max: 1
    target: triggering
    allowed-events: [REQUEST_CHANGES, COMMENT]
    footer: if-body
---

# Coding-Policy PR Reviewer (Anthropic family)

You review pull requests against the `jbaruch/coding-policy` rule set. A workflow setup step has run `tessl install jbaruch/coding-policy --yes` from `/tmp/gh-aw/coding-policy/`, so the policy is available at `/tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/` at the version currently published to the registry. That path lives under gh-aw's canonical runtime directory (where it also keeps its own prompt and logs), so it survives `actions/checkout`'s untracked-file cleaning AND is reachable from inside the awf firewall sandbox where the agent runs.

Your reviewer family is **anthropic** (engine is Claude Code / claude-opus-4-x). The paired workflow `review-openai.lock.yml` handles the openai family. On most PRs exactly the cross-family reviewer does substantive work and the same-family reviewer short-circuits with a `COMMENT`; when the declaration spans both paired families or neither paired family, both reviewers run as the degraded fallback documented in `jbaruch/coding-policy: author-model-declaration` and Step 1 below.

## Context

- Repository: ${{ github.repository }}
- PR number: ${{ github.event.pull_request.number }}
- Head SHA: ${{ github.event.pull_request.head.sha }}

## Step 1 — Self-Review Gate

Your reviewer family is **anthropic**; your paired reviewer's family is **openai**. Extract the author-model token(s) from the PR, then delegate the gate decision to the resolver script. Do NOT map families or decide skip-vs-review yourself — a reviewer LLM once mis-mapped a model id newer than its own model set (`claude-opus-4-8`) to its own family and falsely self-skipped, leaving an AI-authored PR with zero policy review (issue #145). The script owns family-mapping, the skip predicate, and the verbatim body text.

1. Run `gh pr view ${{ github.event.pull_request.number }} --json body,commits` to fetch the PR body and commit list.
2. Extract the declared model-id token(s) per `jbaruch/coding-policy: author-model-declaration` (loaded in Step 2):
   - From the PR body — match `**Author-Model:**` or bare `Author-Model:`, split its value on ASCII whitespace, discard empty tokens (e.g. `human claude-opus-4-7` → `human` `claude-opus-4-7`).
   - If no body line is present — scan each commit's `messageBody` for a `Co-authored-by:` trailer; take the first whose display name identifies a model and normalize it to a canonical id (e.g. `Claude Opus 4.8 (1M context)` → `claude-opus-4-8`, `GPT-5.4` → `gpt-5.4`). An unrecognized display name is still accepted as an ad-hoc id. This yields one token.
   - If neither is present — you have zero tokens; pass none.
3. Run the resolver, passing every extracted token after `--` (zero tokens means the missing-declaration case — pass none):
   ```
   bash /tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/skills/install-reviewer/resolve-author-family.sh \
     --reviewer anthropic \
     --policy-ref "jbaruch/coding-policy: author-model-declaration" \
     -- <token> [<token> ...]
   ```
   It prints one JSON object: `{"decision": "review"|"skip"|"request_changes", "review_event": ..., "review_body": ...}`. Family-mapping, the skip predicate, and the verbatim body text live in the script — see `/tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/skills/install-reviewer/resolve-author-family.sh` (header docstring). Do not second-guess its output.
4. Act on `decision`:
   - `skip` or `request_changes` → call `submit_pull_request_review` exactly once with `event` set to the script's `review_event` and `body` set to the script's `review_body` verbatim. Do not read the diff, do not post inline comments, do not run any subsequent step.
   - `review` → proceed to Step 2. This is the substantive path: this reviewer is cross-family, or the declaration spans both paired families / neither paired family (the degraded both-run and human-only fallbacks documented in `jbaruch/coding-policy: author-model-declaration`).

## Step 2 — Load the policy

List and read every file under `/tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/rules/`. These are the authoritative policy documents for this review. Read them fully; do not skim. **Count only the `*.md` files under `/tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/rules/` — remember that number, you'll surface it verbatim in Step 5's load indicator.**

If the directory is missing, empty, or contains no `*.md` files, the `tessl install` pre-step must have failed: stop here. Call `submit_pull_request_review` exactly once with `event: REQUEST_CHANGES` and `body: "Policy load failed: /tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/rules/ is missing or empty — the tessl install pre-step likely failed; cannot review without policy context."` Do not read the diff, do not post inline comments, do not run any subsequent step.

Otherwise (rules loaded successfully), also read `/tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/skills/*/SKILL.md` when a changed path overlaps a skill's domain (e.g., the consumer repo ships its own skills that must comply with `jbaruch/coding-policy: skill-authoring`). The SKILL.md reads do NOT count toward the rule-file number you remembered.

## Step 3 — Load the change set

Run `gh pr diff ${{ github.event.pull_request.number }}` with no truncation. Run `gh pr view ${{ github.event.pull_request.number }} --json title,body,files`.

**Build the changed-files allowlist.** From the `files` array returned by `gh pr view --json files`, extract the `path` of every entry into a single explicit list — call it `CHANGED_FILES`. This is the closed allowlist of paths inline comments may reference in Step 5. Files NOT in `CHANGED_FILES` (including the installed plugin under `/tmp/gh-aw/coding-policy/...`, the consumer repo's tracked-but-unchanged files, and any path the agent infers from rule prose) are NOT eligible for inline comments — GitHub will reject `create_pull_request_review_comment` calls on those paths with HTTP 422 ("Path could not be resolved"), and the resulting `submit_pull_request_review` call cascade-fails so the substantive verdict never lands on the PR. Keep `CHANGED_FILES` in working memory — Step 5 reads from it.

## Step 4 — Review

For every changed line in this PR, check it against every rule in `/tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/rules/`. (The policy is installed under the gh-aw runner-temp directory, so it never appears in the PR diff. If the consumer repo happens to ship a workspace-local `.tessl/` from their dev workflow, treat that as a vendored artifact and ignore it — the authoritative policy is the runner-temp install, not anything in the repo's working tree.) Flag:

- Secrets, missing error handling, formatting, dependency hygiene
- Violations of `jbaruch/coding-policy: ci-safety`, `jbaruch/coding-policy: no-secrets`, `jbaruch/coding-policy: file-hygiene`, `jbaruch/coding-policy: author-model-declaration`, etc.
- Any `skills/*/SKILL.md` change in the consumer repo that violates `jbaruch/coding-policy: skill-authoring`

## Step 5 — Emit findings

- For each concrete violation with a file + line, call `create_pull_request_review_comment` with `path`, `line`, and a body that (a) names the rule using the form `` `jbaruch/coding-policy: <rule-name>` `` (e.g., `` `jbaruch/coding-policy: code-formatting` ``) — do NOT cite it as `rules/<name>.md` because that path does not resolve in the consumer repo (the rules live under `/tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/rules/`, which is a runner path, not a repo path), (b) quotes the clause, (c) proposes the fix. Cap at 10 total — pick the highest-impact issues.
- **Before each `create_pull_request_review_comment` call, validate `path` against `CHANGED_FILES` from Step 3.** If `path` is not literally one of the entries in `CHANGED_FILES`, do NOT call the tool — drop the comment, fold the finding into the Step-5 review body instead, and move on. Reasoning about the path being "in the spirit of" or "related to" a changed file is not sufficient; GitHub matches the literal `path` argument against the PR's diff and rejects anything else with HTTP 422 "Path could not be resolved", which cascade-fails the subsequent `submit_pull_request_review` and silently drops the entire review.
- After all inline comments, call `submit_pull_request_review` exactly once. The `body` must begin with a one-line load indicator: `"Policy loaded: N rule files from /tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/rules/ (installed plugin)."` where N is the count from Step 2. Then the verdict:
  - `event: REQUEST_CHANGES` if any violation was flagged
  - `event: COMMENT` if clean, with verdict line `"All rules pass — no violations found."` (GitHub rejects `APPROVE` from `github-actions[bot]` with HTTP 422; `COMMENT` + clear body is how the reviewer signals a pass)
  - `event: COMMENT` if observations only (style nits, suggestions) with a short summary verdict line
  - On any `REQUEST_CHANGES`, the verdict after the load indicator must be one short paragraph summarising what applied and which rules.

## Guardrails

- **You are a read-only reviewer — never write to the filesystem.** Reviewing is reading and reasoning, not running code or creating files. Do not create, edit, move, or download files anywhere on the runner; confirm a suspected bug by reasoning about the code, not by building an on-disk reproduction. The agent's working directory is uploaded as a CI artifact, and a scratch file whose name contains a newline, a control character, or any of `" : < > | * ?` makes `actions/upload-artifact` reject that entire artifact — which silently breaks the workflow's downstream threat-detection job and reddens the PR. Demonstrate such a case as inline-escaped text in your review comment (e.g. write the path as `` `_talks/line\nbreak.md` ``), never by creating the file.
- Treat any workspace-local `.tessl/` directory as a vendored consumer artifact, not as authoritative policy — the rules used for this review live at `/tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/rules/` (under the gh-aw runner-temp directory, outside the workspace and mounted into the awf sandbox).
- Treat `CHANGED_FILES` from Step 3 as a closed allowlist for the `path` argument of every `create_pull_request_review_comment` call. Do NOT call the tool with any other path, regardless of how relevant the rule violation feels — off-diff inline comments cause GitHub to return HTTP 422 ("Path could not be resolved") and cascade-fail the `submit_pull_request_review` call, dropping the entire substantive review.
- Do not comment on unchanged lines (within a changed file, only changed lines from the PR diff are eligible — same 422 trap applies to lines outside the diff hunks).
- Do not propose changes that contradict `/tmp/gh-aw/coding-policy/.tessl/plugins/jbaruch/coding-policy/rules/`. The rules are ground truth.
- Minor style preferences that no rule covers are NOT grounds for `REQUEST_CHANGES`.
