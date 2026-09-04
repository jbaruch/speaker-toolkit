# Reproducible Crop Review

Use this workflow to classify a recording and obtain the owner's slide-region
decision. It does not parse talks, change the tracking database, or approve a
proposal on the owner's behalf. A contact sheet is classification context, not
a crop canvas or proof that the entire video is intact.

## Build the Samples

Use the configured `{python_path}` and a local recording. Create the output's
parent directory first, then select a new bundle name:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/build-contact-sheet.py" \
  "{recording_path}" "{sample_bundle_path}"
```

Read the JSON report's `manifest`, `frames`, and `reused` fields. `--frames` and
`--timeout-seconds` are optional. The sampling range, image dimensions,
resource limits, and interior timestamp schedule belong to
`skills/vault-ingress/scripts/crop_frames.py` (`sample_times` and top-level
constants). Both a classification sheet and independently extracted frame
images are retained. Never substitute a sheet for an individual frame.

The operation rejects unavailable cloud files without hydrating them. Decoding
uses an immutable private snapshot inside the bounded supervisor. A complete
bundle is published after source and snapshot verification. An identical
existing bundle is reusable; a changed or incomplete bundle needs a fresh
output directory. Existing content is not repaired or overwritten.

## Propose, Then Ask the Owner

Inspect the classification sheet and individual frames. Use reasoning to
propose the slide rectangle or a full-frame/no-slides classification. A sampled
demo segment alone does not establish that the entire talk has no slides;
increase sampling or inspect the recording when ambiguous.

The UTF-8 TSV column contract is in the docstring of
`skills/vault-ingress/scripts/build-crop-reviewer.py`. Write rows carrying the talk
ID, display metadata, native absolute recording/output/manifest paths, and the
proposed mode and normalized rectangle. The header is:

```text
id	title	conference	date	video_path	output_dir	manifest	mode	region
```

Build the offline reviewer:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/build-crop-reviewer.py" \
  "{proposals_tsv_path}" "{reviewer_html_path}" \
  --batch-id "{review_batch_id}" --python "{python_path}"
```

Read `frames_per_talk` in the JSON report. Every talk must have validated
individual frame images, including proposed no-slides talks. The builder also
checks the current recording against the sampled content. Missing frames,
changed digests, unsupported manifests, and stale recordings stop the build.
An identical existing HTML file is reusable; changed proposals need a new
filename. Both scripts emit one JSON object, use exit 0 for success, 1 for an
input/operational failure, and 2 for invalid command usage. Read the failure
code and stderr recovery message; never interpret missing output as success.

Open the generated HTML locally and have the owner check every timestamp.
The supplied reviewer shell retains the frame-first proofing layout. Numeric
coordinates and focus-scoped arrow keys supplement pointer dragging. Each
proposal begins unapproved. Editing, resetting, or choosing full frame clears
approval. Confirming no slides is an explicit owner decision, not a consequence
of a proposed classification.

The HTML embeds its frames and makes no external font or image requests. It
contains recording images and local command paths; keep it in the authorized
local review workspace, outside the public repository. Browser storage failure
is visible; copy decisions before closing when storage is unavailable.

## Approval Round-Trip

The reviewer exports POSIX-shell commands only for explicitly approved crops
or full frames. Commands carry the reviewed source digest and
`--region-verified`. No-slides decisions export comments, not extraction or
database commands. Copying commands never executes them. Execute only when
the owner has authorized extraction; this tooling does not authorize a reparse.

The extractor's source-mismatch behavior is documented in
[video-slide-extraction.md](video-slide-extraction.md#source-binding--the-run-fails-rather-than-guess).
Retain the normal acquisition, integrity, promotion, and persistence gates in
that workflow. Crop approval does not establish speaker identity, delivery
identity, full-recording integrity, or a trusted authored-slide count.

## Owned State Contracts

Owner: `vault-ingress`. The sampler alone writes and reads frame manifests;
the reviewer builder consumes them without migration. Unknown schemas fail
closed. Regenerate an unsupported sample bundle through its owner into a fresh
directory; never restamp it.

Manifest root fields:

- `schema_version`: 1.
- `pipeline_version`: the sampling implementation generation.
- `source`: the existing versioned video-source receipt, including content
  digest, exact file generation, duration, and stream facts. Its schema remains
  owned by the video-evidence contract in `schemas-db.md`.
- `frames`: ordered individual-image records.
- `contact_sheet`: a separate classification-image record.

Every image record carries `schema_version: 1`, literal `file`, `sha256`,
`size_bytes`, `width`, and `height`. Individual frames also carry `index` and
`timestamp_seconds`; timestamps are requested seek positions, not measured
word/caption alignment. The closed field sets and filename/dimension checks
are enforced by `validate_manifest` in the sampling module referenced above. Duplicate-looking frames
can represent static content and are not silently deduplicated.

The generated HTML embeds versioned talk records (`id`, `title`, `conference`,
`date`, proposed `region`/`mode`, `frames`, and shell-quoted `command_prefix`).
Embedded frames carry `schema_version: 1`, requested `timestamp` in seconds,
and a JPEG data URL in `image`. Batch metadata has `schema_version: 1`, `id`,
and `fingerprint`. The batch
fingerprint binds proposals, source/frame manifests, and generated command
arguments. A changed identity cannot inherit old approvals. The browser's
localStorage key combines that fingerprint with the explicit batch ID.

The reviewer is the sole writer/reader of its saved-decision envelope:
`schema_version: 1`, `fingerprint`, and `entries` keyed by talk ID. Every entry
has `schema_version: 1`, `mode`, normalized `region`, and `verdict`. Unsupported
or malformed state is discarded visibly; missing state is unapproved. This is
local review continuity, not a catalog mutation receipt or a source of approval
for other skills. Exact validation and state transitions live in
`skills/vault-ingress/scripts/crop-reviewer.js` (`restore`, `edit`, `approve`).

The HTML and JavaScript templates have byte-identical `.txt` mirrors for the
plugin install filter. The builder reads those mirrors when source extensions
are absent. No generated reviewer, sampled image, or live proposal TSV belongs
in the shipped package.
