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
- Targets: files co-shipped in this plugin under `{speaker_toolkit_root}/skills/` or `{speaker_toolkit_root}/rules/`, named literally in a command.
- A target outside this plugin's package source does NOT qualify.
- Each target script's module docstring (or header comment) owns its input/output contract; commands follow it, never a restatement.
- Consumer-owned paths (talk directories, vault paths, shownotes sites) are never rooted here.

## No Authority Granted

- The lookup selects a path and nothing else.
- It grants no runtime authority and waives no check after lookup.
- Each target's own contract, the configured-interpreter rule (`{python_path}`), and every gate the target names still apply.

## Regression Coverage

- `tests/test_installed_plugin_paths.py` verifies the lookup and its output:
  - every shipped `SKILL.md` declares the lookup;
  - the declared lookup resolves the plugin root, from a clone and from an installed mount copy;
  - every rooted command path names a target that exists under that root;
  - no operational toolkit path is left unrooted.
