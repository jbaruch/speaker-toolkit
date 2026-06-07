---
alwaysApply: true
---

# Shownotes Content Publish

## Why

- The `shownotes-publisher` skill writes talk pages into the Jekyll shownotes site and pushes them to the site's default branch. These pages are prose and data a human audience reads directly, not code or agent-loaded context.
- `jbaruch/coding-policy: ci-safety`'s Content-Only Direct-Push Carve-Out permits a direct push to `main` for such content under its Form B client-side gate, used where a platform cannot express server-side allowlist enforcement (github.com personal repos). This rule is the authority-of-record satisfying precondition 1: it names the carve-out, the covered path globs, the enforcing gate script, and the review the direct-push does not carry.

## Covered Paths

- `_talks/**` — the Jekyll `_talks/` collection; one markdown page per talk, authored for human reading on the shownotes site.
- `assets/images/thumbnails/**` — talk thumbnail images the rendered pages reference.

These are the only paths a direct push may modify, and both are content surfaces a reader consumes directly. No code, rule, skill, script, manifest, workflow file, or configuration is in scope. A push touching anything else is out of scope and forces branch + PR.

## Enforcement

- Form B client-side gate: `skills/shownotes-publisher/scripts/content-only-gate.sh` is the deterministic gate (per `jbaruch/coding-policy: script-delegation`). It enumerates every path the pending push would change in the target work tree and exits 0 only when every one matches a covered glob above; any out-of-glob path exits non-zero.
- `shownotes-publisher` Step 9 runs the gate before publishing and direct-pushes only on exit 0. An out-of-glob path, or an indeterminate gate result, forces an automatic branch + PR fallback — never an operator override.
- The allowlist is the `ALLOWED_PREFIXES` constant at the top of the gate script. The globs above and that constant stay in sync.

## What Direct-Push Does NOT Carry

- The direct push bypasses the pull-request review cycle on the shownotes site: no gh-aw policy review and no human or Copilot review runs on the content before it lands.
- It does not bypass post-publish verification. `ci-safety` still requires watching the Pages deploy to a successful conclusion and confirming the live URL returns HTTP 200.

## Scope Limits

- The carve-out covers only the two globs above on the shownotes site. To extend it, name the new glob here AND add it to `ALLOWED_PREFIXES` in the gate script. Adding one without the other invalidates the precondition.
- The carve-out does not widen to any other repo or branch. Every other path, and every change to this speaker-toolkit repo, still goes through pull requests.
