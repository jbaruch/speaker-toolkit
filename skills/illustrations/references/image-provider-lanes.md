# Image Provider Lanes

Both generators use `model_registry.resolve_image_lane` before API credentials
or provider calls. `image_provider.py` supplies the shared options, fresh probe,
and stderr diagnostics. Resolution happens separately for each render.

## Choosing a lane

| Options | Behavior |
| --- | --- |
| Default: `--image-lane auto` | Prefer a compatible CLI. Preserve current pinned API models and exact-size requirements on API. |
| `--image-lane auto --allow-cli-native` | Prefer Codex for unmasked, single-reference OpenAI edits and generation. An absent executable permits reported API fallback. |
| `--image-lane cli --allow-cli-native` | Require the compatible subscription CLI; absence or unsupported constraints fail. No API-key requirement. |
| `--image-lane api` | Use the existing HTTP adapter without probing a CLI. |

`--allow-cli-native` is an explicit relaxation of image-model pinning and exact
geometry, not an alias change. The baked `gpt-image-2` alias still resolves to its
dated API snapshot. Native results report
`codex-native-image-model-unpinned`, actual width/height, and the output SHA-256.
They are not labelled as that snapshot or resized to pretend a size was served.
Use the API lane for exact output requirements or lane-pinned cost comparisons;
neither lane promises pixel-identical repeated generation.

Example, for an outline that has already passed its render-before-bake gate:

```bash
python3 "{speaker_toolkit_root}/skills/illustrations/scripts/generate-illustrations.py" \
  outline.yaml --image-lane cli --allow-cli-native -v 2
```

Native exploration grids are previews only. Their contact sheet and version-2
manifest retain requested and served identities; they cannot establish that a
dated API model was seen. Comparison/exploration native filenames carry
`-cli-native-unpinned`. The normal bake gate remains in force. A native preview
does not authorize overwriting the outline's model or claiming cross-lane parity.

## Verified capability and limits

The [installed-CLI probe record](https://github.com/jbaruch/speaker-toolkit/issues/385#issuecomment-5546340204)
records native Codex generation and editing, plus the failed Gemini attempts.
Only the proven OpenAI native lane is enabled. Gemini and Imagen use API; forcing
CLI reports `family_api_only`. Thumbnail composition is Gemini-only and uses two
reference images, so it remains API-only, including its optional portrait pass.
Slide extraction does not invoke an image provider.

Codex image-model pinning, exact dimensions, masks, and multiple references are
not proven by the installed probe. Masked builds stay on API in auto mode and
refuse forced CLI. Unmasked native builds preserve the existing backward edit
chain; inspect native dimensions and visual continuity before applying a deck.

## Authentication and failures

The adapter observes `codex login status`; only ChatGPT authentication is
eligible. It does not log in, log out, inspect auth files, set a forced login
method, or edit global configuration. Select subscription authentication yourself
if the probe reports API or unknown authentication. The child environment omits
API-key/token/secret/password variables; the caller's environment is unchanged.
This is an observed CLI authentication mode, not independent proof of billing.
See the official [authentication documentation](https://learn.chatgpt.com/docs/auth)
and [native image documentation](https://learn.chatgpt.com/docs/image-generation).

Every attempted render emits an `IMAGE_LANE` JSON line to stderr with lane,
family, operation, requested/served model, geometry, reason, and resolved binary
and version (`null` for API). Successful native renders add `IMAGE_OUTPUT` with
observed dimensions and digest. Raw CLI stderr, prompts, credentials, and
assistant text are not included in adapter failures.

Installed Codex can emit non-fatal `item.completed` diagnostics before the turn
starts and during it. Completed renders surface their count as a stderr warning
and `provenance.warning_count`; raw diagnostic text is withheld. Top-level
`error`, `turn.failed`, a non-zero exit, or invalid image output still refuse the
render. The [non-interactive CLI documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
describes the JSONL event families; the pre-turn item ordering is established by
the installed 0.153.2 probe and covered by a fixed synthetic fixture.

Absence is an expected non-result. A present executable that fails capability,
authentication, generation, quota, output validation, or supervision checks
produces a visible failure; no automatic metered retry follows. Repair the CLI
or explicitly rerun with `--image-lane api`. Generation, comparison, exploration,
and build commands exit non-zero if any requested render fails. Exploration
writes its partial result manifest before that exit.

## Dependency renewal and execution boundary

Codex is an optional runtime dependency, discovered on PATH. Capability is
renewed on every CLI selection and again before each render: resolved executable
identity, parsed version, required non-interactive flags, and authentication.
No minimum-version pin replaces that probe. A version change between selection
and rendering refuses the run. The actual image-tool invocation remains a
separate capability check: help text alone never counts as image success.

`image_cli.py` uses the co-shipped authenticated supervisor and an owner-private
temporary workspace. Its probe and render profiles bound wall time, memory, and
descendants; `image_cli_process.py` bounds pipes and workspace growth. Exact
limits and closed failure codes live in those modules. Output must be the literal
`image.png`, a bounded regular local leaf, with a valid single-frame PNG and a
completed structured CLI turn. The adapter checks copied reference bytes and
the original reference generation, verifies the output digest, and removes
scratch on success, refusal, and interruption. It never treats assistant prose
or an arbitrary returned path as output evidence.

The test suite uses fake CLI/process/provider boundaries only; it never invokes
a vendor binary or endpoint. Renew the manual probe after a capability change:
run one authorized native generation and one single-reference edit, inspect the
images, record binary/version, dimensions, and digests in the issue, then update
fixtures if the structured event contract changed. Do not induce quota exhaustion
or change authentication automatically.
