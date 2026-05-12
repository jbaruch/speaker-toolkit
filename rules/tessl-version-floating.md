# Tessl Version Floating

## Why

- `tessl update` rewrites `tessl.json` in-place at runtime, and the resolved-version state under `.tessl/tiles/` is gitignored. Pinning a literal version in `tessl.json` produces silent drift where the committed manifest and the running install disagree across every `tessl install`.
- The runtime-managed-manifest narrow exception in `jbaruch/coding-policy: dependency-management` permits a floating-but-explicit specifier (`"version": "latest"`) for this exact shape, subject to three preconditions. This rule is the authority-of-record satisfying preconditions (1) and (3): it names the carve-out, lists every covered manifest, and explains why pin/lock semantics break.

## Covered Manifests

- `tessl.json` (project root) — consumed by `tessl install` to populate the gitignored `.tessl/tiles/` directory that backs `@.tessl/RULES.md` resolution at agent runtime. Vendored-mode means every `tessl install` re-resolves dependencies, and any pin here would diverge from the running install on the very next `tessl update`. Every dependency in this manifest must float — mixed pin/float within a covered manifest is forbidden by the carve-out's "any disallowed specifier" clause.

No other manifest in this repo is covered. Every other dependency-bearing manifest (`pyproject.toml`, etc.) still pins per the default clause of `dependency-management`.

## Enforcement

- A deploy-time check at `scripts/check-tessl-pins.sh` walks every covered manifest and fails the build if any dependency uses a specifier other than the permitted floating value `"latest"` — rejecting literal pins, version ranges, tags, and anything else, per the carve-out's warning that "rejecting only literal pins lets a non-literal pinned/ranged value slip through".
- The check runs in CI on every push and pull request via `.github/workflows/tests.yml`, ahead of the test suite. CI failure blocks merge per `ci-safety`.

## Scope Limits

- The carve-out does not widen to "any manifest". To extend it to a new manifest, name the manifest in the **Covered Manifests** list above AND ensure `scripts/check-tessl-pins.sh` walks it. Adding a manifest without updating both invalidates the precondition.
- The carve-out does not widen by transitivity. Manifests `tessl install` does not rewrite — manifests inside vendored tiles, manifests in subtrees not consumed by `tessl install` — still pin per the default policy.
