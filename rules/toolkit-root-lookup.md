---
alwaysApply: false
applyTo: "skills/*/SKILL.md, skills/*/references/**/*.md — when writing or reviewing a command that runs a co-shipped toolkit script or reads a co-shipped file"
description: Named lookup rule for the {speaker_toolkit_root} path form toolkit commands use in a clone and an installed mount
---

# Toolkit Root Lookup

## Authority Claimed

- `jbaruch/coding-policy: skill-authoring` Script References — a resolved plugin root, for skills that run both from a clone and from an installed mount, under this plugin's own named lookup rule.
- `jbaruch/coding-policy: script-delegation` Scoped Plugin Contracts — this rule is the named rule its precondition 1 requires.

## Lookup

- Input: the absolute path of the loaded `SKILL.md`.
- Output: `speaker_toolkit_root`, the plugin root two directories above that file's directory, used as an absolute path.
- The same lookup serves a clone and an installed mount: it reads only the skill's own location.
- Never derive it from the consumer working directory, `PATH`, an environment variable, or a git remote.
- Every shipped `SKILL.md` carries this lookup.

## Authored Scope and Co-Shipped Targets

- Scope: the skills listed in `.tessl-plugin/plugin.json` `skills`, and their `references/`.
- Targets: files or directories co-shipped in this plugin under `skills/` or `rules/`, named literally in a command after the resolved root.
- A directory target is a co-shipped data directory a command passes as an argument (a pattern catalog, a bundled CLI's source tree).
- Every target, file or directory, resolves inside the plugin root.
- A target outside this plugin's package source does NOT qualify.
- Each target script's module docstring (or header comment) is authoritative for its input/output contract.
- A command's step prose summarizes the inputs, outputs, exit codes and side effects the caller acts on, and leaves internal logic to the script.
- Consumer-owned paths (talk directories, vault paths, shownotes sites) are never rooted here.

## No Authority Granted

- The lookup selects a path and nothing else.
- It grants no runtime authority and waives no check after lookup.
- Each target's own contract, the configured-interpreter rule (`{python_path}`), and every gate the target names still apply.

## Regression Coverage

- `tests/test_installed_plugin_paths.py` verifies the lookup and its output:
  - every shipped `SKILL.md` declares the lookup;
  - the declared lookup resolves the plugin root, from a clone and from an installed mount copy;
  - every rooted command path names a file or directory that exists and resolves inside that root;
  - no operational toolkit path is left unrooted.
