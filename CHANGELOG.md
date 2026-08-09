# Changelog

### fix(generate-qr) — preserve canonical MCP targets and exact generated artifact paths (#171)

The `qr_codes` catalog recorded facts that were demonstrably false. `--short-url`
and `--shownotes-url` were mutually exclusive, so MCP mode could not supply the
canonical redirect target and stored the short URL as both `short_url` and
`target_url` — a record claiming the short link redirects to itself. MCP mode
also recorded a generic `mcp_preresolved` shortener, losing the provider, link
id, and back-half.

`--shownotes-url` is now required in every mode and is always the recorded
`target_url`. New optional `--short-provider` and `--short-link-id` carry the
real provider identity; `short_path` is recovered from the short URL and
recorded only when it equals the talk slug, never asserted onto a link that
lacks it.

Artifact paths were equally unreliable: `--png-only --output PATH` wrote to
`PATH` but recorded the default `{talk-slug}-qr.png`, deck mode reduced a custom
output to its basename against an ambiguous root, and a multi-colour run
generated several PNGs while cataloging one.

The `qr_codes` record schema advances to v2 with an `artifacts` array — one
entry per generated PNG, each carrying the exact written path, an explicit
`path_root` (`deck_dir`, `cwd`, or `absolute`), a SHA-256, and the colour
variant's `bg_hex`. `qr_png_rel_path` mirrors the first artifact so schema-v1
readers keep working. Readers dual-accept v1 and v2; migration stamps
unversioned records at v1, since they cannot satisfy the v2 shape.

MCP mode enforces §2 rather than carving an exception into it: a pre-resolved
link whose back-half is not the talk slug exits non-zero before any side effect,
the same as a script-created link that cannot take the slug. `--short-provider`
and `--short-link-id` now require `--short-url`, so provider identity is never
accepted and silently dropped.

`skills/vault-ingress/references/schemas-db.md` documents both record shapes,
the `artifacts` fields, `path_root` semantics, the dual-reader window, and why
migration stamps unversioned records at v1.

Also folds in #248: `qr-generation-rules.md` §2's back-half failure directive is
split into atomic bullets per `context-writing-style`, and a new §4 states the
catalog-fidelity contract. Sections renumbered accordingly, with cross-references
updated.

## 0.20.24 — 2026-08-09

### fix(generate-qr) — fail closed when a configured shortener cannot produce the managed link (#170)

`resolve_short_url()` silently returned the raw shownotes URL on five paths: no
shortener configured, an unknown shortener name, missing bit.ly/rebrand.ly
credentials, any exception escaping through the effectively-broad
`except (..., Exception)`, and a failed custom back-half. Each shipped a QR
without the managed redirect layer and cataloged it as `shortener: none`,
overwriting an existing managed `qr_codes[]` record.

Only an explicit `shortener: none` now authorizes a raw target URL. Every other
resolution failure raises `ShortenerResolutionError`, which `main()` converts to
a non-zero exit before any PNG, deck, or tracking-database write. The catch is
narrowed to documented provider and network failures (`HTTPError`, `URLError`,
`OSError`, `JSONDecodeError`, and a `KeyError` from a malformed response);
programming errors and process-control exceptions propagate.

A bit.ly custom-back-half failure now carries the already-created link's
`link_id` and `short_url` in the error, so the provider-side partial creation
can be reused or deleted deterministically instead of being orphaned.

Configuration is validated before any cache reuse. A cached record proves what
was authorized on an earlier run, never what is authorized now, so a stale
`shortener: none` entry could otherwise re-authorize a raw URL under a missing
or newly-managed configuration. A cached record is reused only when its
`shortener` matches the one configured; a mismatch forces re-resolution.

`rules/qr-generation-rules.md` §2 said the script "fails to a raw-URL fallback"
when the slug back-half cannot be set. That contradicted §3 and now contradicts
the implementation, so it states the current contract: exit non-zero without
generating a QR, and report the provider-side link identity.

## 0.20.23 — 2026-08-09

### fix(skills) — restore standalone sequential-workflow preambles (#179)

`presentation-creator`, `shownotes-publisher`, and `vault-ingress` each failed
the `skill-authoring` title/preamble clause under whole-file validation. The
first two appended workflow prose to `Process steps in order. Do not skip
ahead.` in the same paragraph; `vault-ingress` substituted a custom sentence
for it. All three now open with the standalone preamble and keep their
workflow explanation as the following paragraph. Step semantics and numbering
are unchanged.

### fix(packaging) — clearer shape errors and de-duped path list (#133)

`scripts/check-package-contents.sh` coerced manifest array items with `str()`,
so `"skills": [42]` reported `declares "42" but no tracked files live there` —
sending the reader after a directory that was never declared. Non-string items
now hit the `BAD_SHAPE` branch and name the offending index and type.

A manifest declaring both a directory and a path beneath it (`skills/` plus
`skills/builder`) listed every file under the narrower path twice, inflating
the total, repeating each violation line, and making the `excludes X of Y`
counts wrong. The content list is de-duplicated after the per-path existence
check, which needs its own unfiltered count.

### fix(vault-profile) — distinguish absent `--vault-root` from failed recomputation (#225)

Schema-v5 owner validation appended `requires --vault-root` whenever the live
pattern snapshot was absent, including when the flag *was* supplied and
recomputation failed first — for instance on an invalid classification-policy
override. The report then carried both the real recomputation error and a
second message implying the flag was omitted. The owner-validation requirement
stays explicit in both cases; only the stated cause differs.

### fix(vault-ingress) — report the actual trusted root for artifact rejections (#187)

`pattern_evidence._resolve_local_artifact()` hardcoded `outside the vault
root`, but `_resolve_preclaim_artifact()` calls it against three different
roots: the vault, a configured `pptx_source_dir`, and a field-specific
`preclaim:<field>` root. An absolute external PDF, symlink, or path escape
rejected by the latter two named the wrong trust boundary, obscuring which one
refused the artifact and making catalog/reparse failures harder to repair. The
root kind now travels with the resolution and names the violated boundary; an
unrecognized kind degrades to `the trusted root` rather than claiming the
vault. Fail-closed behavior and path redaction are unchanged.

## 0.20.22 — 2026-08-08

### chore(deps) — pin the setuptools build requirement

`[build-system] requires` now pins `setuptools==83.0.0` instead of declaring the
open lower-bound range `setuptools>=68`, matching how every other renewed
dependency in `pyproject.toml` is declared. The policy reviewer gated
Dependabot's range bump (#131) on this: `dependency-management` requires a pin
or a committed lock file, and the repo has no lock file, so widening the range
could not satisfy it. Renewal continues through the weekly Dependabot pip lane
that already covers the other pins. The remaining unpinned runtime
dependencies (`python-pptx`, `lxml`, `qrcode`) stay tracked in #161.

## 0.20.19 — 2026-08-08

### ci(review-trigger) — skip dependabot pull requests (#244)

The fleet policy review trigger is synced to the current
`jbaruch/coding-policy` `install-reviewer` template, which skips Dependabot
pull requests alongside fork pull requests. GitHub populates the `secrets`
context from the Dependabot store — not the Actions store — for any workflow a
Dependabot event triggers, so `FLEET_DISPATCH_TOKEN` resolved empty and the
workflow's own emptiness guard exited non-zero on every Dependabot PR. This
turned the `trigger` check red on PRs #125, #128, and #131 while their test
suites were green. `pull_request_target` is not an escape hatch; GitHub applies
the same restriction to it for Dependabot-authored pull requests. The
coding-policy schedule remains the review path for these PRs.

## 0.20.18 — 2026-08-05

### fix(vault-ingress) — reconcile event-qualified shownotes titles (#237)

Shownotes reconciliation now keeps an existing authored title when the
publication title adds only an explicit `at <event>` qualifier whose event alias
and year agree with the same talk's already-stored conference and date. The
current shownotes document cannot corroborate its own suffix through newly
proposed metadata. The shared matcher remains asymmetric and preserves the prior
narrow presentation normalization. Generic event-type words remain
identity-bearing, while the observed Voxxed `Days` presentation variant stays
equivalent. Changed subtitles, unrelated events, wrong years, and short-prefix
collisions stay review-required.

## 0.20.17 — 2026-08-05

### fix(vault-ingress) — allow CloudStorage owner writes (#239)

The shared tracking-database transaction now tolerates bounded timestamp-only
settling on its unique staged file, including macOS Google Drive/File Provider
behavior after fsync. Staged file type, link count, descriptor/name identity,
size, exact bytes, and SHA-256 remain strict; failures report the named staged
invariant and unstable timestamp fields. The target database keeps its exact
byte-and-generation precondition. Pre-install invariant failures remove the
still-owned staged name, while a substituted name remains untouched.
Config-only owner migration remains hash-bound, backed up, and idempotent.
Database schemas and talk evidence are unchanged; no talk reparse is required
for this fix.

## 0.20.16 — 2026-08-05

### fix(vault-ingress) — make PPTX directory completeness explicit (#234)

PPTX directory extraction now emits a strict schema-v1 batch envelope whose
closed skip receipts determine `complete` and `incomplete_reason_codes`.
Partial scans keep safe per-deck results and exit zero, while only a complete
scan authorizes full-catalog or missing-deck conclusions; whole-root and
protocol failures still exit nonzero. The private discovery manifest advances
to v2 so its authenticated response carries the same recomputable decision.

Config schema v2 adds bounded, case-insensitive exact-component
`pptx_directory_exclusions` with narrow environment/cache defaults. The owner
migration upgrades config v1 without changing root schema v1, preserves a
valid custom list, and prunes each configured real directory with one explicit
policy receipt after symlink/reparse checks. Exclusions use a separate bounded
enumeration allowance so they cannot consume the eligible-entry budget, and the
private response is bound back to the exact requested policy. Public whole-root
errors reject per-deck reason promotion and arbitrary/path-bearing details.
Per-deck PPTX extractor schema v4
and pipeline 1.5.0 are unchanged; existing talk evidence does not require
reparsing solely for this release.

## 0.20.15 — 2026-08-05

### fix(vault-ingress) — allow nested PPTX batch workers (#233)

Directory PPTX extraction now carries the fixed interpreter/entrypoint identity
through per-file metadata, probe, native-audit, and extraction workers. A
toolkit and configured runtime installed below the presentation root can finish
ordinary decks instead of returning `pptx_probe_start_failure`; mutable argv,
artifact-equal identities, redaction, and structured failure reasons are
unchanged.

## 0.20.14 — 2026-08-05

### fix(vault-ingress) — allow nested PPTX discovery runtimes (#228)

Bounded PPTX directory discovery now permits its exact configured Python and
fixed worker entrypoint to live beneath the scanned presentation root while
continuing to reject sensitive paths in mutable process arguments. A
whole-root discovery failure emits a structured top-level error and exits
nonzero instead of looking like a successful empty scan. Existing talk
analysis is unchanged; rerun the PPTX catalog scan where discovery previously
reported only a root failure.

## 0.20.13 — 2026-08-05

### fix(vault-ingress) — reserve missing config markers (#226)

Typed config mutations now reject the reserved `{"$missing": true}` expectation
sentinel as a literal value and direct callers to `delete: true`. Vaults that
already contain the sentinel as a present config value can remove it through the
normal expectation-bound deletion; its change receipt distinguishes presence
from absence. The database schema is unchanged and talks do not need reparsing
for this repair.

## 0.20.12 — 2026-08-05

### feat(vault-profile) — ship default pattern classification policy (#222)

Speaker profiles now classify current scoring-v5 opportunity rows with the
bundled, versioned `speaker-toolkit-default@1` policy instead of waiting for
every speaker to invent thresholds. Schema-v5 profiles embed the exact policy,
its canonical semantic SHA-256, exhaustive positive and antipattern
classifications, combinations, trend evidence, and independent availability
for each derived domain. A present `pattern-classification-policy.json` may
override the default only when it passes the strict schema-v1 contract; an
invalid override aborts rather than silently falling back.

Section 15 writes the policy-bound v3 block while retaining read-only v2
occurrence compatibility. Presentation creation consumes each available domain
independently: New-to-You comes only from `never_tried`, recurring warnings come
only from high/moderate derived antipattern classifications, and unsupported
mode history remains unavailable. Raw opportunity rows stay unchanged, and the
upgrade requires profile/summary regeneration but no talk reparse. Goal-setting
accepts validated schema-v4 and schema-v5 raw baselines; it uses a v5 derived label
only when that label's own classification domain is available.

## 0.20.11 — 2026-08-04

### fix(vault-ingress) — supervise preserved source-video evidence (#190)

Preserved source recordings now pass one bounded metadata/media/digest probe
before they can contribute local-media digest or duration evidence to transcript
validation, authorize delivery-video citations, support video-derived slide
provenance, or participate in persisted freshness. The probe accepts the
declared MP4/MOV/WebM/Matroska container families, requires a usable video
stream and positive duration, limits input size and stream count, and binds the
result to one unchanged local-file generation. Media parsing and SHA-256 use one
private snapshot copied from a verified no-follow descriptor, so a sync-time
path replacement cannot combine facts from two files. Corrupt or incomplete
media, cloud placeholders, parser diagnostics, sync-time replacement, missing
`ffprobe`, and worker/resource failures remain structured, operation-local
outcomes; a caller's transient deadline is never published to unrelated
operations. These failures disable only the video lane and do not erase an
independent transcript, PDF, or PPTX.

Schema-v3 extraction manifests now own their exact `<youtube_id>.mp4` source
even when a conflicting legacy top-level video path is present. Preflight
separates a missing source (`source_video_artifact_missing`), an unhydrated
placeholder (`source_video_artifact_unavailable`), and unreadable media
(`source_video_artifact_unreadable`) from locator/ownership faults. Persistence,
analysis rendering, queue normalization/claiming, preflight, and profile
freshness share one assessment per top-level operation, so one transient result
cannot be silently contradicted by a later nested retry. A returned recording
may support current delivery evidence but cannot retroactively authorize the
pre-return transcript. No tracking, return, evidence, scoring, or extraction
schema changes, and existing records do not require reprocessing solely for
this release.

Ingress and direct profile workflows now require the narrow `source-video`
runtime lane before an operation inspects a preserved recording. The executable
skill workflows remain concise while their bootstrap, queue, persistence,
profile-construction, PPTX follow-up, and clarification contracts live in named
references. This keeps the operational order visible without weakening any
validation or evidence rule.

## 0.20.10 — 2026-08-04

### fix(vault-ingress) — isolate video frame workspaces from stale evidence (#213)

Every video extraction now uses a fresh private temporary frame workspace for
ffmpeg, region selection, deduplication, and PDF construction, then removes it
after normal completion or a Python failure. Frame discovery uses literal
directory entries and accepts only numbered JPEG outputs, so stale frames, glob
metacharacters, and parallel runs cannot contaminate the current PDF or
retained-frame manifest. Each PDF is completed in a deterministic adjacent stage
before atomic replacement; a failed build preserves the prior derivative, and
the next run reclaims a stage left by abrupt process loss. A cross-platform
per-video advisory lock in local OS temporary storage prevents two cooperative
reruns from interleaving their slide-region and context PDF pair without adding
Google Drive lock artifacts. The video extraction pipeline advances to `0.12.0`;
its record schema remains v3. The documented video dependency set is pinned to
the exact tested versions and renewed weekly through Dependabot.

## 0.20.9 — 2026-08-03

### fix(vault-ingress) — reject impossible inspected-page ranges before PPTX work (#204)

The PPTX CLI now rejects page zero, descending ranges, page numbers beyond the
existing bounded archive-member ceiling, and excessive range counts before
opening or supervising a PPTX or rendered PDF. It scans comma-delimited Unicode
decimal input incrementally, accumulates numbers with an overflow-before-
multiply check, and emits fixed bounded diagnostics without copying or echoing
resource-sized tokens. Long leading-zero forms retain their existing normalized
meaning. Actual deck page bounds, ordering and overlap across ranges, and
canonical range output remain owned by the existing post-probe range validator.

## 0.20.8 — 2026-08-03

### fix(vault-ingress) — unify trusted vault-root authority (#212)

Queue selection, persistence, analysis rendering, preflight, and profile cohort
freshness now use one stdlib-only vault-root authority resolver. The native
absolute parent of `tracking-database.json` is primary; a supplied CLI vault
root and a present `config.vault_storage_path` must be lexically equal to it.
An absent or null configured root falls back to the database parent. Empty,
relative, home-expanded, foreign, device, and ambient-drive forms fail closed
before artifact assessment, freshness caching, persistence, rendering, or
preflight artifact I/O.

The resolver performs no `expanduser`, cwd rebasing, symlink resolution, stat,
or equivalence-by-filesystem lookup. It reports only closed, path-neutral
database/CLI/config authority reasons. Existing mismatched or noncanonical
configuration requires explicit operator repair; no database migration or
stored-root rewrite is performed. The ingress references now document the
expectation-bound `set_config` dry-run/apply/re-read/preflight sequence for
removing or replacing an invalid stored assertion.

## 0.20.7 — 2026-08-03

### fix(vault-ingress) — validate video owner identity before output derivation (#214)

Video slide extraction now admits only the shared canonical 11-character
YouTube-ID grammar before path resolution, directory creation, ffmpeg, or
artifact writes. Frame workspace and PDF paths are derived only from that
validated identity and must remain below the canonical caller-authorized output
root, including when a pre-existing symlink would redirect a derived path.
Traversal, separator, drive/device, whitespace, NUL, Unicode-lookalike, and
wrong-length identities fail with one closed reason. Manifest ownership and
artifact filenames retain the same admitted ID; invalid legacy identities
require repair and re-extraction rather than normalization.

### fix(vault-ingress) — keep ffmpeg artifact paths out of the shell (#211)

Frame extraction now invokes ffmpeg with an explicit argv vector and
`shell=False`. Spaces, quotes, semicolons, substitutions, and redirection
characters in otherwise valid native paths remain data, while failures report
only the process exit status rather than an interpolated command. The remaining
vault-ingress Python scripts contain no `os.system` or `shell=True` artifact
boundary. The extractor pipeline advances to `0.11.0`; its schema remains v3.

### fix(vault-ingress) — make artifact locators host-deterministic (#210)

Ingress now classifies raw artifact locators before `Path`, `abspath`,
`expanduser`, symlink resolution, metadata inspection, cache lookup, or worker
launch. Canonical trusted-root-relative locators use `/`; raw dot segments,
home-relative forms, backslash/mixed relative syntax, Windows ambient-drive and
device forms, dual-flavor `//` paths, foreign absolute flavors, and relative
components that Win32 would trim or reinterpret as alternate streams or device
names fail closed with stable path-neutral reasons. Native POSIX, Windows
drive-absolute, and backslash-UNC locators remain available on their matching
host.

The same stdlib-only contract now governs PPTX/PDF/video context admission,
preflight, return-manifest validation, freshness reconstruction, configured
PPTX roots, and the direct metadata/probe/extraction/directory worker
boundaries. A present `pptx_source_dir` must be native absolute; an invalid
setting can no longer become a cwd-relative root or silently fall back. Worker
payloads receive only already-materialized native absolute paths, with the same
checks repeated at child boundaries. Foreign or legacy noncanonical locators
require explicit owner repair and reprocessing; no database, return, evidence,
or extraction schema is bumped and no stored locator is silently rewritten.

## 0.20.6 — 2026-08-03

### fix(vault-ingress) — supervise exact-generation PDF evidence (#183)

Static-slide PDFs now use a dedicated authenticated metadata/probe worker with
fixed wall, memory, process, input, output, diagnostic, and page-count ceilings.
The worker copies and hashes one exact regular-file generation, requires a PDF
header, walks the complete strict pypdf page tree, and returns only a closed
identity/page-count receipt. Offline cloud placeholders, parser repairs,
materialization races, protocol faults, and infrastructure failures remain
distinct, lane-local reasons; only repeatable artifact damage is cached.

Pattern evidence, freshness checks, preflight, video-extraction provenance, and
public rendered-PDF inspection consume the bounded receipt instead of opening,
hashing, resolving, or statting PDF leaves in the owner process. Every
manifest-declared video PDF is independently verified against its recorded page
count before a current return can be persisted, and a promoted video-slide PDF
must have the exact digest of its trusted manifest `slide_region` artifact.
Manifest paths reject NUL and ambiguous dot segments, preserved source videos
must remain root-confined and non-symlinked, and the documented symlinked
canonical vault root is mapped to its configured storage root without weakening
descendant-link checks. Source-video preflight failures now keep their nested
diagnostic path-neutral instead of interpolating a lower-level exception (#199).
A shared platform metadata decoder keeps PDF and PPTX
cloud/reparse classification identical while preserving the older PPTX
compatibility seams. Trusted-root receipts bind stable directory identity and
policy attributes while excluding mutable child-content size and timestamps, so
normal NTFS metadata settlement cannot impersonate a PDF/PPTX leaf race.
Windows leaf receipts also canonicalize path- and handle-based snapshots to
their shared creation-time semantic; CPython's incompatible `st_ctime_ns`
meanings can no longer reject a valid same-path replacement (#201).
The PDF worker's outer CLI boundary now emits one closed, path-neutral stderr
diagnostic before returning a nonzero failure instead of failing silently
(#202).
PDF supervisor receipts now distinguish dependency, monitor, identity,
containment, and configured resource-limit causes while retaining the existing
request, result, timeout, generation, start, crash, and protocol families
(#207). Public diagnostics are operation-neutral and forward no worker details.
Successful PDF evidence is unchanged, so no schema or pipeline migration is
required. Ambiguous historical failure/skip receipts remain readable but are
never relabeled; rerun ingress to regenerate them under the current mapping.

Contained PPTX render inspection reuses the same PDF ceilings, full page-tree
walk, and repair-diagnostic policy without nesting a second supervisor. PPTX
extraction behavior advances to pipeline 1.5.0 so older render receipts cannot
inherit the stronger trust claim. The PDF runtime lane now requires the exact
psutil supervision pin, and native macOS/Windows CI executes the complete PDF
worker suite.

Persisted native-deck freshness now requeues missing, obsolete, wrong-lane, or
artifact-disconnected audits and binds any rendered-page receipt to the current
bounded PDF generation plus its canonical inspection ranges (#195). Persisted
preflight also rejects `video_extraction` provenance outside the
`video_extracted` slide lane, matching return validation and atomic artifact
admission (#194).

Rendered-PDF pre-admission now uses the PDF lane's input ceiling and stable
missing, root/symlink, cloud, size, and resource failure family. Authenticated
generation receipts distinguish source-deck drift from `pdf_artifact_changed`
without introducing parent-process PDF leaf I/O (#196).

### fix(vault-ingress) — supervise every native-deck parser boundary (#182)

PPTX probe, native-audit, and full extraction now run behind one private,
authenticated worker protocol. Artifact paths and per-invocation credentials
travel over bounded stdin only; signed responses bind the request, operation,
limit profile, extractor schema/pipeline, and exact pre/worker/post file
generations. Duplicate, non-finite, partial, trailing, oversized, unauthenticated,
or generation-mismatched results fail closed before their nested payload is used.

Workers receive fixed wall, input, output, process-count, and process-tree memory
budgets. POSIX cleanup terminates the trusted worker's process group plus sampled
descendants; Windows uses a kill-on-close Job Object with aggregate
committed-memory and active-process limits. `psutil==7.2.2` supplies fail-closed
sampled aggregate-RSS monitoring on all platforms; macOS does not overclaim a
kernel hard-allocation cap. Raw parser diagnostics never escape—only a
byte-count/hash/truncation receipt is retained.
Private PPTX and directory workers emit one closed, path-neutral stderr
diagnostic for outer failures instead of exiting silently (partial #203).
The dedicated PPTX preclaim resolver no longer leaves unreachable legacy
source-root branches in the generic PDF and source-inspection paths (#208).
PPTX preclaims now reject Windows current-drive/per-drive-relative locators and
device namespaces before host path normalization, preventing a saved locator
from selecting bytes through process-specific drive state (#209).
The picture-area render decision has one script-owned threshold shared by the
producer and validator; schema prose points to that authority instead of
copying its predicate (#205).
Supervisor receipts now distinguish request, result, dependency, monitor,
identity, containment, and configured resource-limit causes with
operation-neutral diagnostics (#188). Successful evidence is unchanged, so no
schema/pipeline migration is required. Ambiguous historical failure/skip
receipts remain readable but are never relabeled; rerun ingress to regenerate
them under the current mapping. Response-frame encoding now reports an output
limit rather than mislabeling it as an oversized request.
Supervisor tests now reuse the canonical imported module instead of replacing
it during collection, preserving dataclass and exception identity across test
orders; PDF, PPTX, and metadata consumers assert the shared identity (#206).
If psutil observes a root identity disappearing during a normal fast exit, Popen
gets at most the remaining sample interval to confirm and reap that exact child;
a still-live child, descendant leak, or non-ESRCH cleanup failure remains fatal.

The stdlib-only runtime checker advances to report schema v2, publishes each
lane's `required_module_versions`, and rejects any PPTX supervision runtime that
does not provide exactly `psutil==7.2.2`.

The public extractor can no longer fall back to owner-process parsing, including
OCR and rendered-PDF inspection. A hard 2 GiB source ceiling admits known large
hydrated decks while preserving an explicit per-artifact bound. Directory mode
is explicit (`--directory`) and moves root validation plus recursive enumeration
behind a separate authenticated, termination-safe worker, so the owner never stats
or scans the supplied root. Its strict root-relative manifest rejects symlinks,
directory reparse points, unknown Windows redirects, offline/recall Cloud Files,
unusable/colliding directory identities, and `~$` Office locks while admitting
supported hydrated Cloud Files leaves. File-cap truncation emits a root-level
incomplete-scan receipt; discovery and extraction share one deadline and final JSON
accounting includes the exact wrapper/newline. Race-free root/leaf handle binding is
tracked separately by #176. The directory CLI now accepts the exact configured
template-skip array, including an empty array, without injecting a hard-coded
`template` pattern; vault-ingress forwards that database configuration explicitly.
Extraction behavior advances from pipeline 1.2.0 to
1.4.0 and field schema v4 makes native text-frame, graphic-frame, picture-asset,
and background-asset obligations explicit so partial worker output cannot silently
downgrade catalog evidence. Known shape/graphic types are cross-bound to their
capabilities and DrawingML URIs; picture/background OCR and recovery receipts bind
the exact package part and digest; slide ordinals bind canonical slide parts and
timing provenance; and duplicate, ASCII-case-equivalent, or segment-prefix
package-part names, noncanonical OPC escapes/segments, and duplicate relationship
IDs are rejected before parsing. Content-type defaults/overrides and presentation
slide identities are likewise required to be unambiguous.
Names, URIs, relationship IDs, nesting, member counts, and expanded archive bytes
are normalized or stopped at documented bounds before entering the catalog.
Empty image parts now produce self-consistent unavailable-asset evidence. Consumer
instructions authorize affirmative OCR only from each receipt whose own
`trustworthy_text` is true; compatibility aggregates remain review-only.
Graphic frames with a missing/empty URI remain visible as generic unsupported
evidence instead of producing an internally invalid extraction record.
Repeated references to one package asset must agree on a single SHA-256 across
picture, background, and recovery bindings.

## 0.20.4 — 2026-08-03

### fix(vault-ingress) — make damaged native-deck evidence fail closed (#151)

PPTX extraction schema v3 validates every archive member and reports bad-CRC
embedded media through a closed `archive_recovery` record. Recovery replaces
only the damaged media in memory so healthy structure remains inspectable;
malformed containers and damaged XML, relationships, or other structural parts
remain unavailable with an actionable error. The source deck is never rewritten.

The shared capability probe now uses the same recovery contract as extraction,
so offline preflight reports `slide_pptx_artifact_degraded` or
`slide_pptx_artifact_unreadable` instead of leaking `BadZipFile`. A required
`pptx`/`both` source with placeholder recovery cannot receive a fresh claim or
persist current analysis. An unused optional degraded deck beside an independent
source remains diagnostic.

Each extraction also emits a closed `native_deck_audit` bound to the exact PPTX
bytes, extractor generation, slide count, and derived render requirements. The
optional rendered-page receipt binds an equal-page-count PDF and the exact pages
inspected. Return validation and owner-side canonicalization require complete,
identity-matched rendered inspection for native-deck design findings that need a
rendered page. Single-file extractor failures now return one concise diagnostic
without a parser traceback.

Grouped shapes and tables are walked recursively, while SmartArt, graphic
frames, unreadable pictures, and other unsupported visual containers remain
explicit render requirements. Picture/background OCR emits one bounded receipt
per exact asset, including engine/result confidence and trustworthy-text status,
so a missing engine or corrupt image cannot masquerade as a wordless slide or
abort the whole deck. Raw native timing stays split into animation behaviors,
visibility actions, transitions, media timing, and build-list entries; every
lane records package structure only and explicitly declines to claim observed
playback.

## 0.20.3 — 2026-08-01

### fix(vault-ingress) — suppress presentation-only shownotes conflicts

Shownotes title comparison now treats straight and curly single/double quote
glyphs as equivalent after Unicode NFC normalization. Conference comparison
uses NFC plus case folding only. These transforms never rewrite stored or
reported values, while substantive wording, punctuation, whitespace, source,
and identity differences continue to require review.

## 0.20.2 — 2026-08-01

### fix(vault-ingress) — contain native dependency probe crashes

Runtime module imports now run in bounded child processes launched by the exact
configured interpreter. A missing dependency, Python initializer exception,
native crash, timeout, or malformed child result degrades only an optional lane
and blocks that lane when required. The parent retains its one-JSON stdout
contract, reports a machine-readable failure reason per module, and emits an
actionable recovery step without forwarding native crash output.

## 0.20.1 — 2026-08-01

### fix(vault-ingress) — give the tracking database one versioned owner

Vault-ingress now owns tracking-database shape changes and migration (#147).
The database root, config, talks, PPTX catalog entries, QR records, resource
records, thumbnails, confirmed intents, improvement goals, and source-rejection
entries carry explicit schema versions. A deterministic schema-0 migration
refuses active queue writers, binds apply to the dry-run SHA-256, saves the exact
original bytes, and replaces only the validated generation atomically. Historical
talk records remain in their original schema generation; migration adds only the
missing implicit-v1 version and never fabricates current pattern evidence.

Legacy queue inspection and recovery can close leases before migration without
schema stamping. Mutating tools require current state; non-owner readers accept
legacy and current state without rewriting either. Migration rejects duplicate
JSON keys, non-finite numbers, malformed owner records, and unknown owner schema
generations before backup or mutation. Profile generation projects semantic
confirmed-intent fields without leaking database schema metadata.

Owner assessment now classifies root, record, queue-claim, and adherence-baseline
versions before interpreting older identities or nested shapes. One shared pure
queue contract validates complete claim/history lifecycles, generation/status
coherence, receipts, and immutable batch baselines before migration or queue use,
while preserving the status-drift recovery lane. The strict decoder rejects a
finite JSON number when it cannot round-trip through the toolkit without changing
its mathematical value, before backup or write; harmless lexical variants remain
accepted. It also bounds JSON nesting at 200 containers and rejects unpaired
UTF-16 surrogates before recursive consumers, rendering, backup, or write.
Section 15 pattern-history replacement now applies the owner schema gate before
interpreting configured storage paths or constructing freshness assessors.
Publishing and clarification patches require talk schema v5. Legacy
pattern goals remain report-only, legacy pacing/independent goals can patch only
their historical status/check fields, and schema-v2 goals retain the full
verification contract.

### fix(vault-ingress) — serialize tracking-database access and close owner schemas

All toolkit tracking-database writers now share one persistent sibling lock and one
strict exact-generation transaction. Reads reject duplicate keys, non-standard JSON
numbers, non-object roots, symlinks, and generation swaps before network or mutation
work. Writes retain no-follow file and directory descriptors through staged `fsync`,
revalidate bytes and identity at the install boundary, atomically replace, and sync the
parent directory. Staged-name substitution fails closed; immediate post-install checks
detect observable non-cooperative edits. Installed-but-not-fully-synced outcomes are
reported truthfully, semantic no-ops preserve bytes and inode, and source-repair
backups are never-overwritten copies bound to the exact input hash.

Owner-plan and source-repair equality is now recursive and JSON-type-sensitive:
object order is irrelevant, array order is significant, and `true`, `1`, and `1.0`
are distinct. Semantic no-ops, including QR metadata writes, preserve the original
bytes and inode. Mutation records are closed and type-validated for PPTX, confirmed
intent, improvement goal, resource, thumbnail, and publishing metadata. New PPTX,
QR, confirmed-intent, resource, and thumbnail records carry required schema-v1
identities. Backups are deferred until the staged candidate passes its final integrity
checks, followed by one more live-generation and stage verification before install.
Clarification can persist complete blind-spot/humor structures, and exact
record retirement changes only a goal's status while preserving legacy provenance.

Clarification, profile, thumbnail, and resource instructions now bootstrap through
the strict owner reader, use the configured interpreter after that single bootstrap,
and route every tracking change through the dry-run/hash-bound owner mutation. The
resource rule uses the canonical `category_breakdown` shape, and the transaction
reference documents post-install outcomes plus the residual non-cooperating-writer
last-instruction race.

## 0.19.0 — 2026-08-01

### feat(vault-ingress) — make reparses exhaustive, source-bound, and freshness-bound

This release incorporates the official 0.18.74 source-located evidence contract
as its base: observable detections require validated transcript, slide, video,
or allowlisted metadata citations; hash-bound transcript timing remains
optional; and the ten process-only entries moved out of automatic observation
remain unscored.

Fresh work now advances together to queue-claim schema v5, return schema v5,
persisted talk schema v5, evidence-ledger schema v2, and pattern-scoring schema
v5. Workers report exact detections, applicability assessments, not-evaluable
reasons, and the line/page/time ranges they actually inspected. Persistence
resolves those raw receipts against owner-side artifacts, derives canonical
roots, paths, hashes, bounds, coverage, and evidence facts, then writes one
sorted `pattern_outcomes` row for every observable catalog entry plus an
`opportunity_coverage_identity`. Outcomes distinguish `detected`, `undetected`,
`not_applicable`, and `not_evaluable`; workers cannot author the derived ledger
or identity.

Generation identity is no longer enough by itself. Current scoring also requires
the exact live catalog fingerprint and fresh source-located artifacts. Queue
normalization re-hashes persisted evidence, revalidates transcript quality
against current source-owned duration, and requeues missing, replaced, or
drifted evidence with deterministic reasons. Saved v1–v4 claims and returns
remain replayable archival evidence, but they cannot enter the v5 cohort and
migration never fabricates v5 applicability or outcomes.

### fix(vault-ingress) — make transcript quality and timing receipts non-forgeable

Transcript text, quality policy, and timing are separate hash-bound artifacts.
The quality receipt records the applied word floor and its owner/provider or
local-media duration provenance; a caller-supplied duration cannot weaken it.
Timing remains an enrichment, not a prerequisite for ordinary semantic
transcript evidence.

For an existing `youtube_auto` transcript, the fetcher may restore a missing or
stale caption-timing receipt only when newly fetched captions reproduce the
existing text exactly after whitespace-layout normalization. It never replaces
the transcript bytes during enrichment. Edited, manual, Whisper,
unknown-provenance, or text-mismatching transcripts remain timing-unavailable
and are never relabeled as captions. Failed acquisition is atomic and cannot
replace trusted text with a partial payload or crash output.

Local-audio acquisition now binds hashing, duration probing, Whisper output,
quality, and timing to one twice-verified private media snapshot, then rechecks
the original path and bytes immediately before commit. VTT import validates
root containment, component symlinks, regular-file type, and stable bytes before
reading or writing. Provider chatter is quarantined from the one-JSON stdout
contract, and transcript/quality/timing destination symlinks are refused rather
than rewritten during force or rollback paths.

Evidence resolution snapshots transcript text and both receipt files around
validation, retries a concurrently replaced generation, and stamps identities
only from the accepted byte set. Local delivery-video duration and digest are
likewise accepted only when device, inode, size, and timestamps remain stable
across probing and hashing, so one evidence context cannot mix artifact
generations during parallel reparse or cloud synchronization.

### fix(vault-ingress) — isolate runtime and source capabilities

The configured `python_path` is now executable authority, with a stdlib-only
runtime probe for independent core, PDF, PPTX, Drive, captions, YouTube
download, PDF rendering, video, and Whisper lanes. A missing optional dependency
degrades only that lane; it cannot erase a healthy transcript or alternate slide
capability.

Queueing, offline preflight, terminal-state validation, and persistence share
the same root-aware capability resolver. Local transcript, PDF, PPTX, and video
declarations count only when the source-specific parser, quality check, or probe
can read the artifact under an allowed root; provenance labels and non-empty
paths are not capabilities. Remote acquisition remains a separate capability.
`skipped_no_sources`, `skipped_download_failed`, and duplicate outcomes are
accepted only when their mechanically checkable source state agrees.

Shownotes discovery is now a deterministic `scan-shownotes.py` dry-run instead
of an LLM-authored database edit. It parses supported local collection formats,
derives provider IDs, catches rejected-source identities across alternate URL
forms, and leaves incomplete or conflicting records as review proposals. Its
explicit `--apply` path adds or fills only deterministic records through a
no-follow, generation-bound atomic database replacement.

### fix(patterns) — separate observable evidence from defensible absence

All 81 observable entries now have explicit positive, strong, and absence
outcome gates, and 37 have source-located applicability gates. Only 16 entries
authorize absence: eleven from a completely inspected, separately declared
rendered PDF and five from a completely inspected transcript. The other 65
explicitly use `absence_evaluable_from: null` and are positive-only.

Complete locator ranges are not automatically modality-complete. Sampled or
deduplicated video-extracted pages, bare native decks, bare delivery video, and
current comparison receipts can support positive detections but cannot authorize
absence or force applicability decisions. Canonical receipts expose this
distinction with independent `coverage_complete`,
`absence_capability_complete`, and stable capability reasons. Thus a missing
source, a catalog-authorized not-applicable condition, an
applicable-but-undetected opportunity, and a positive-only entry remain
different denominator states.

### feat(vault-profile) — make scoring opportunity-aware and classification fail closed

Scoring v5 compares raw scores only inside one exact
`opportunity_coverage_identity`. Adherence-baseline schema v2 therefore
separates the complete fresh `eligible_talk_count` used for per-pattern
occurrence rows from the exact-identity `scored_talk_count`. Mixed identities
produce `raw_score_comparison_status: unavailable` with reason
`mixed_opportunity_coverage`; an all-unknown cohort produces the same zero/null
score sentinel with `no_evaluable_pattern_opportunities` instead of publishing
an available `0.0`. Owner-side talk comparison additionally requires at least
ten scored talks with the same identity.

Speaker-profile schema v4 copies the validated baseline and exhaustive
per-pattern opportunity rows, preserving each pattern's own evaluable
denominator and unknown coverage. Owner validation recomputes the live cohort
and rejects a structurally plausible but source-stale profile. Section 15's
schema-v2 current block is generated from the same full post-batch candidate,
checked against the live database, and replaced atomically; surrounding prose
remains historical narrative rather than numeric authority.

No speaker-owned versioned classification policy exists yet, so profile and
Section 15 classification fields fail closed even when occurrence rows are
current. The presentation creator suppresses mastery, novelty,
signature/contextual-history tiers, recurring severity, trends,
pattern-derived badges, and other historical classifications while keeping
current-taxonomy analysis of the new talk available. A valid profile has
priority; Section 15 is only a strictly validated fallback and can never repair
stale history by implication.

### fix(vault-ingress) — make catalog, leases, persistence, and rendering transactional

Catalog loading and auditing now share one canonical normalization path,
deterministic fingerprint, graph/source-gate validation, and explicit
semantic-debt reporting. Source audits cover provider identity, duplicate and
rejection ledgers, artifact paths, and title/event correspondence; guarded
repair plans use exact old-value preconditions, backups, and atomic replacement.
Catalog feedback remains a provenance-preserving review queue, never
authorization for automatic taxonomy edits.

Video-derived authored-slide evidence requires the complete schema-v3
verified-region provenance chain; sampled context cannot invent authored-slide
counts or negative evidence. Native PPTX schema v2 preserves package identity,
grouped/table/graphic/background fidelity, and timing structure without claiming
delivered playback. Per-slide ledgers, image-source count maps and their basis,
co-presenter data, citations, and promoted fields are deep-validated before
mutation.

Schema-v5 queue claims are immutable, recoverable leases bound to one run,
batch, generation, baseline, and required return version. Persistence requires
the exact live batch, uses one authoritative timestamp, closes claims only after
every candidate validates, and stores a canonical receipt of each accepted
return. Snapshot returns v2–v5 replace supplied declared fields, preserve
omissions, and use explicit `clear_fields` for deletions; unknown containers and
future schemas fail closed.

Analysis rendering verifies the completed claim receipt and current scoring
generation, then renders the validated persisted effective talk rather than a
partial raw return. It preflights normalized/case-folded target collisions and
special files, stages the whole batch, and rolls back replacements in reverse
order on failure. A late error can no longer split the database, queue state, or
analysis directory into different generations.

## 0.18.74 — 2026-08-01

### fix(vault-ingress) — require source-located evidence for observable patterns

Pattern detections now carry validated transcript, slide, video, or allowlisted
talk-metadata citations instead of treating a free-form evidence string as proof.
Caption, Whisper, and VTT ingestion preserve hash-bound timing sidecars; legacy
evidence remains readable but renders as unverified, and ten process-only
patterns move out of automatic observation when the available artifacts cannot
establish how the talk was prepared.

## 0.18.73 — 2026-07-28

### fix(vault-ingress) — a bare-int `pattern_score` no longer silently drops the scalar

Subagents write `"pattern_score": 19` instead of the declared
`{"patterns_used": 22, "antipatterns_detected": 3, "score": 19}` on roughly a
third of returns — 5 of 16 across two batches, from independent agents that never
see each other's work.

It looked cosmetic and is not. `normalize_pattern_observations` already accepted
the int, so the nested value landed and the return looked fine. But PROMOTE
resolves `pattern_observations.pattern_score.score`, `dig` returns None on an
int, and the queryable top-level `pattern_score` **was silently dropped** — the
exact missing-scalar defect this script was written to fix (1 of 200 talks had
`slide_count` before it), reintroduced through the input shape.

`canonicalize_pattern_score` now rebuilds the dict before promotion, and
**recomputes rather than trusting**: a supplied int that disagrees with the
arrays exits 1 naming both numbers, because that is a real inconsistency, not a
formatting slip. `True` is not read as a score of 1.

Each coercion is reported as `coerced_pattern_score` in the stdout summary rather
than fixed silently, so the rate stays visible.

A reviewer then caught a second bug that the first version of the bool test had
HIDDEN. That test asserted `canonicalize_pattern_score` in isolation and passed,
while `merge_talk` still persisted `pattern_score: True` — `isinstance(True, int)`
holds in Python, so a bool sailed through `normalize_pattern_observations`'s
numeric branch and reached the DB as a numeric score. Every non-dict, non-numeric
shape now exits 1, and the test asserts the persisted OUTCOME across `True`,
`False`, `"19"` and `["19"]`. All four fail without the fix — verified by
reverting the guard alone, which is the only way to know a regression test
regresses on anything.

The schema invites the error twice over — the field is NAMED for a number but
holds a dict, and `antipatterns_detected` means an array of objects one level up
and an integer count inside `pattern_score`. Restating the requirement in the
brief did not move the rate across four batches, so the tooling absorbs the
variant instead. `merge_talk` now returns a third element; its four existing test
call sites are updated.

### fix(vault-ingress) — one validator for the merge, not several disagreeing ones

Six review rounds each found a different hole in `pattern_score` validation, and
patching them one at a time was treating symptoms. The cause was structural: TWO
functions independently decided what a valid score was — `canonicalize_pattern_score`
checking the incoming shape, `normalize_pattern_observations` re-deciding with its
own `isinstance(score, (int, float))`, and PROMOTE resolving the top-level scalar
through a third path, a dotted lookup. Every round tightened one and left the
others, so they disagreed in a new way each time.

`resolve_pattern_score` now decides once. `normalize_pattern_observations` takes
already-validated inputs and decides nothing. `pattern_score` leaves PROMOTE
entirely and is set from the resolved value — the dotted path
`pattern_observations.pattern_score.score` is what silently dropped the scalar
whenever a subagent sent the bare int, because `dig` returns None on an int.

Reading the file properly then turned up three more silent-drop defects that no
review round had reached:

- **A wrong-typed content block was skipped and the merge reported success.**
  `structured_data`, `verbatim_examples` and `pattern_observations` were each
  guarded by a bare `isinstance(..., dict)`; a `structured_data` arriving as a
  list lost the entire analysis and still exited 0.
- **A detection array of bare id strings killed the script mid-merge.**
  `p.get("pattern_id")` raised `AttributeError` before any JSON was printed —
  the exact die-without-saying-so shape this file exists to prevent.
- **A detection array supplied as a plain string had its CHARACTERS counted as
  detections**, feeding a silently wrong number into the score cross-check.

All three now fail loudly, and validation runs before any write so a malformed
return leaves the talk untouched rather than half-merged. An incomplete score
object — present but missing `score` — is malformed too, not absent.

`migrate_records` stamps every record rather than only the talks a batch touched;
partial stamping would leave the artifact permanently mixed-version, so a reader
could not distinguish an unversioned record from an untouched one. The count is
reported as `migrated_records`.

Each of the eight new tests was verified to FAIL with its guard reverted. A
regression test nobody has watched fail guards nothing — which this PR already
demonstrated the hard way, when a bool test asserting the helper in isolation
passed while the DB was taking `pattern_score: True`.

### fix(vault-ingress) — version the talk record, validate the score inside the dict

`persist-results.py` now stamps `schema_version` on every talk record it merges.
v1 is the implicit unversioned shape all pre-2026-07-28 records carry, in which
`transcript_source` was documented as always present — though 95 of 209 records
never had it. v2 documents the field as optional and gives ABSENT a meaning:
provenance unknown, distinct from the explicit `none`.

The bump is additive, which `stateful-artifacts` Cross-Pipeline Schema Bumps
permits without a staged rollout — a v1 reader reads a v2 record unchanged,
because v2 removes a guarantee rather than adding a field. Readers do not gate on
the value yet; that contract is #147, sequenced after the in-flight reparse so
writer and readers cannot skew mid-run.

Type-checking only the BARE `pattern_score` left the declared dict unexamined, so
`{"score": True}` or `{"score": "19"}` still reached the DB — the same defect one
level in. The inner value now gets the same check.

Both checks require an **integer**, not merely a number. The talk schema declares
`pattern_score` an integer and it is count(patterns) minus count(antipatterns),
so a float is never right however numeric it looks — `1.5` would have persisted
into an integer field. Tested across `True`, `False`, `"19"`, `["19"]`, `1.5` and
`1.0` at both levels.

### fix(vault-ingress) — reject raw VTT payloads, stop inventing a transcript source

Two defects in the transcript work shipped in 0.18.72, both found by running it
against the real corpus.

**A raw VTT dump passes every validator.** 26 of the vault's 206 transcripts held
YouTube's karaoke caption payload rather than cleaned text — each line once with
inline `<00:00:01.020><c>word</c>` timing tags, then again as plain text. Word
counts read **3.6× high**, uniformly: a 37-minute meetup talk measured 18,543
words, implying a two-hour session and a wildly wrong words-per-minute figure.

The length floor cannot catch this, because a doubled transcript has MORE words,
not fewer. `validate_transcript` now rejects the timing-tag signature and names
`vtt-cleanup.py` — which already existed for exactly this and had simply never
been run on those files. A test asserts the fixture clears the word floor before
the VTT check fires, so the guard cannot pass for the wrong reason.

**`method: "existing"` told agents to write `manual`.** The mapping said to fall
back to `manual` when `transcript_source` was absent. `manual` means a human
produced the transcript; a batch-24 agent dutifully wrote it onto a file that is
unmistakably YouTube ASR, then flagged the result as a placeholder. An absent
field now stays absent — the script learns nothing about provenance on that path,
and a downstream reader weighing transcript reliability would trust `manual` more
than the ASR it probably is.

## 0.18.72 — 2026-07-27

### feat(vault-ingress) — a real transcript fetcher that validates before it writes

Four of the vault's transcripts were Python tracebacks. Not truncated files —
the fetcher's own crash, written to the transcript path:

> `AttributeError: type object 'YouTubeTranscriptApi' has no attribute 'get_transcript'`

`youtube-transcript-api` 1.0 removed that classmethod, every fetch raised, and
the traceback landed where speech belongs. The error handler then raised too
(`NameError: name 'sys' is not defined`), so the failure path failed as well.
Two more transcripts are zero bytes. Nothing validated any of it, so a talk with
a stack trace for a transcript was indistinguishable from a talk with a real one
— and `0MGvxG-sc6g` (Java Puzzlers NG S01) was marked `processed` off an empty
file and recorded that nowhere.

The traceback reads `File "<string>"`. The fetch was a `python3 -c` heredoc and
no committed fetcher existed anywhere in `skills/`. That is the root cause, and
it is what `rules/script-delegation.md` Scripts Are Real Files prevents: a real
script gets an exit code, a stderr channel, and tests. An inline heredoc gets to
write its stack trace into the corpus and exit 0.

`scripts/fetch-transcript.py` tries the caption track, falls back to local
Whisper, and validates before writing — empty, a Python-error signature at the
head, a word floor, mostly-`[Music]` caption tracks, and a words-per-minute floor
when a runtime is supplied. The write is atomic and happens only after validation
passes, so a failed fetch leaves no file rather than a crash report.

The validation is pure, so CI exercises every failure mode from fixtures — no
network, no YouTube, no Apple-Silicon Whisper. Two bugs surfaced while repairing
the real corpus with it, both caught before merge and both now regression-tested:

- Library exceptions propagated instead of falling through, so a video with
  captions disabled crashed the fetcher rather than reaching Whisper — the
  original defect one layer up. `YouTubeTranscriptApiException` is now caught and
  returns `None`.
- One test passed `not-a-video` as an unresolvable id. It is eleven characters
  drawn from the id alphabet, so it IS well-formed, and the test reached YouTube.
  Replaced with a URL carrying no id, which fails at resolution before any
  network call.

`segments_to_text` accepts both the pre-1.0 dict shape and the 1.0 object shape;
pinning to one shape is what broke the previous fetch.

**The inline fetch that caused all of this was still committed.** The reviewer
found it: `references/subagent-instructions.md` still told every subagent to run

```
"{python_path}" -c "
from youtube_transcript_api import YouTubeTranscriptApi
transcript = YouTubeTranscriptApi.get_transcript(...)
" > "{vault_root}/transcripts/{youtube_id}.txt"
```

— the literal heredoc whose output is in the corpus, redirect and all. Fixing
`SKILL.md` while leaving that in the reference agents are sent to would have
changed nothing about what agents actually do. The section is now one call to
the script, with its exit-code contract tabled and a note that a transcript
already on disk is not proof of a transcript.

Tool-state failures now honour the JSON contract. A missing `yt-dlp` raised
`FileNotFoundError` and the script died without printing its documented object —
the same silent-failure shape it exists to prevent, one level up. `yt-dlp` and
`mlx_whisper.transcribe()` are both guarded, and both return `None` so the caller
emits the failure JSON and exits 1.

`rules/transcript-fetch-authority.md` is the authority of record for the Whisper
layer's Platform-Bound Untestable Carve-Out, naming the exempt wrapper and its
four-step manual validation — including the step that proves a missing `yt-dlp`
still yields the JSON contract and still leaves no file behind.

`youtube-transcript-api` is pinned at 1.2.4 and declared. The pin is deliberate
rather than habitual: an uncontrolled upgrade of this exact library is what
corrupted the data, so the next API break arrives as a Dependabot PR instead of
as tracebacks in the corpus.

## 0.18.71 — 2026-07-27

### fix(tests) — the invocation guard now catches bare `scripts/foo.py` commands

`tests/test_script_invocation_style.py` guards the outcome "no invocation
consults the exec bit", because `tessl install` strips it from every packaged
script. Its two detectors matched `./foo.py` and `$VAR/foo.py`, and a bare
repo-relative `scripts/foo.py` is neither — so a line reading ``Run
`scripts/foo.py` `` passed CI and still failed in a consumer install, which is
the exact failure shape the guard exists to prevent (#138).

Not hypothetical: `watch-pr-reviews.sh` exited 126 during the 0.18.70 release
because the mounted copy is mode 644, and the fenced block in
`illustrations/references/generation.md` would have handed a consumer
`skills/presentation-creator/scripts/apply-backgrounds.sh` to copy and run.

A bare path is genuinely ambiguous where the other two forms are not — it is a
valid FILE NAME as well as a valid COMMAND, and `script-as-black-box` REQUIRES
skills to cite scripts by path, so a detector that flagged every bare path would
push authors to stop citing scripts at all. Classification is therefore by
markdown structure, never by parsing prose:

- Inside a fenced code block — the surface a consumer copies verbatim — a bare
  path at command position with no interpreter is unsafe. Exhaustive.
- In prose, only a code span introduced by an enumerated execution verb (run,
  invoke, execute, through) counts. Pointer verbs that also precede script paths
  in these docs (see, in, from, live in, defined in) are excluded deliberately.
- Table rows are pointers by construction and are never flagged.

The prose half is an approximation with a stated gap — a novel execution verb
slips through it — and stands as a second net over the fenced-block rule rather
than as the primary guard. Naming the limit beats implying a completeness the
check does not have.

`.py` files are scanned as prose rather than as shell. Treating them as shell
false-positived two docstring references that wrapped across a line boundary,
and Python reaches a script through `subprocess`, where the path sits inside
brackets and quotes and never lands at command position.

Per `language-diagnostics` Adopting on a Dirty Tree, the detector and the 14
fixes it surfaced land together. That is more sites than the seven the issue
listed, and one of them — the `apply-backgrounds.sh` fenced block — was not on
that list at all.

An environment-assignment prefix counts as an invocation: `FOO=1 scripts/x.sh`
runs the script and needs the exec bit, which is how the `$VAR` detector has
always classified `FOO=1 "$HERE/x.sh"`. The first cut of the bare detector read
the assignment as "not command position" and passed it — a false negative in a
guard, which is worse than no guard. An assignment OF a path
(`DRIVER=skills/x/scripts/y.sh`) still stores rather than runs; the whitespace
after the `=` is what separates the two.

Every one of those invocations also moves to a repo-relative path that actually
resolves (`skills/<name>/scripts/<file>`, per `skill-authoring` Script
References). The first cut added the interpreter and kept the `scripts/<file>`
shorthand, which resolves from nowhere. Six further sites carrying the same
shorthand are corrected in the same pass: they sit in the files being edited, so
fixing only the flagged lines would have left each file mixing two conventions —
the state `skill-authoring` explicitly forbids.

## 0.18.70 — 2026-07-27

### fix(vault-ingress) — stamp `processed_date` at second resolution, not day

0.18.64 made the merge stamp `processed_date` when a return omitted it, and gave
the stamp a day's resolution. That is too coarse for the case it exists to serve.

During the 2026-07-26 reparse, 90 talks landed under a single date while four
scoring fixes shipped across the same two days. Nothing in the DB could order a
talk against a fix that published that afternoon, so the re-check backlog had to
flag every talk in the run rather than the subset that actually predated each
fix — 100 flagged where the true number is smaller and unknowable.

The default stamp is now a UTC ISO-8601 timestamp at second resolution. A
date-only `--run-date` is still accepted so callers can pin a stamp for tests
and so records written before this change stay readable; the instrumentation
partition in `load-vault.py` compares stamps lexically, and ISO-8601 sorts
correctly against a bare date either way.

The clock is injectable. `default_stamp(now=None)` takes the moment as an
argument so the regression test freezes it rather than asserting whatever the
run-time clock produced — the first cut tested the default path through a live
subprocess clock, which `testing-standards` Determinism forbids and which cannot
assert an exact stamp at all.

A `--run-date` timestamp must now carry a timezone offset, and is normalized to
UTC at second resolution before it is stored. Ordering talks across machines is
the point of the stamp and a naive timestamp has no defined position in that
order; the first cut accepted one and preserved whatever offset it arrived with.

## 0.18.69 — 2026-07-27

### feat(vault-profile) — partition talks by extractor generation before computing baselines

`load-vault.py` fed every `processed` talk into the profile's `pattern_score`
baselines regardless of which extractor scored it. Talks scored before the
2026-07-26 reparse were measured by an extractor blind to text baked into images
and to payload held in OOXML tables, so their scores record scan depth rather
than delivery — the same talk moved 13 to 39 on re-scan with no change in the
recording.

The payload now carries `baseline_talks` and `stale_instrumentation_talks` plus a
`baseline_note` stating why, and the skill binds `average_pattern_score`,
`by_mode`, `score_trend`, `pattern_breadth` and every adherence comparison to the
former. A mode with too few current-instrumentation talks emits `stable: false`
rather than being topped up from the stale cohort.

Partitioning in the script rather than in skill prose is the point: the filter is
deterministic, and prose asking an agent to remember which cohort a number came
from is exactly what does not survive a long run.

An undated talk counts as stale — excluding one only narrows the sample, while
including it silently contaminates the baseline.

The instrumentation gap is not the only reason the cohorts are incomparable, and
the epoch happens to separate both. Pre-reparse observations put patterns and
antipatterns in ONE undifferentiated list, so a stored per-mode average such as
mode (i)'s 19.35 counts antipatterns alongside patterns. A reparsed score is
`count(patterns) - count(antipatterns)`. Comparing the two compares different
quantities and reads as "on baseline" where the talk may be well above it.

At the time of writing the split is 95/0, because the stale-scored talks all sit
at `needs-reprocessing` and were never eligible for the baseline. The guard costs
nothing and catches the case it exists for: generating a profile from a vault
that is partway through a reparse.

## 0.18.68 — 2026-07-27

### fix(presentation-creator) — antipattern scoring polarity was inverted in 26 of 28 files

`Strong signal (2 pts)` described the antipattern being ABSENT in 26 antipattern
files and PRESENT in the two newest. Subagents record `confidence` in
`antipatterns_detected` meaning "how strongly present", so the same value meant
opposite things depending on which file a scorer happened to open. Every one of
the corpus's 3,228 antipattern observations is affected, and no scorer could
tell which convention produced any given one.

Five independent reparse agents reported it before it was acted on.

All 28 files now read `Strong signal (2 pts — antipattern present)` and
`Absent (0 pts — antipattern not present)`. `tests/test_pattern_catalog.py`
holds the convention along with the other structural contracts a scorer depends
on: complete 3-bullet scales on all 111 entries, `id` matching filename (the
invented-id class that let `terminal-as-deck` be scored 14 times), unique ids,
`type:` agreeing with the `_anti_` prefix, index-vs-file agreement on which
entries are unobservable, and the index's summary statistics.

### fix(presentation-creator) — `vacation-photos` encoded the extraction bug it should resist

Its detection signals were "full-bleed image slides" plus "minimal text on image
slides", which silently equates *the slide is an image* with *the slide has no
words*. On a 160-slide deck with zero shape-level text runs a mechanical read
scores `strong`; the rendered pages show one of the most densely worded decks in
the corpus. The pattern reproduced the exact inversion the vault reparse exists
to correct, so fixing the extractor could not fix the score.

Detection now says to judge from the rendered page, and names the real question:
not whether the slide carries text in shapes, but whether it carries the
argument. A full-bleed image under a baked-in title stating the claim is not
this pattern.

### fix(presentation-creator) — three entries whose names drive false positives

Each now opens its detection section with an explicit NAME TRAP warning.

- `dual-headed-monster` requires a simultaneous live AND remote audience, not two
  presenters. 15 of 16 corpus detections were false positives on that misreading.
- `red-yellow-green` is a physical exit-poll mechanism, not a talk that discusses
  red/yellow/green. One corpus talk builds a literal LED semaphore for forty
  minutes without deploying the pattern.
- `crawling-code` is an authored deck reveal, not a live IDE screencast where
  code happens to scroll.

## 0.18.67 — 2026-07-27

### fix(vault-ingress) — gate slide-region detection on plausibility, and stop overclaiming it

0.18.66 replaced the all-pixels bounding box with connected-component selection.
That fixed the broadcast-composite case and introduced a worse one: with no size
or shape constraint, the chosen component can be the changing TEXT BLOCK inside
a full-frame slide. Cropping to it discards the rest of the deck. Confirmed on a
corpus talk whose "HELLO My name is Baruch" title slide was cropped to a 9%
fragment with the name cut off — content loss, where the previous code had
safely declined to crop.

Selection now requires the component to look like a projected display: at least
15% of frame area and an aspect ratio between 1.0 and 2.4. Measured over 94
corpus decks, ungated selection returned boxes with aspect ratios from 0.32 to
9.45; the gate cuts 55 detections to 26 and turns the confirmed content-loss
case into a `None`.

**The 26 survivors are not thereby correct.** A by-eye check found the gate still
passes a presenter's torso on a talk with no visible screen — rectangular,
well-filled, right size, right aspect. Fill, area and aspect cannot separate a
person from a screen. The docstring and the reference now say so directly: a
returned region is a hint to verify, never ground truth, and no slide count
should be derived from a crop nobody looked at.

Reliable use is the case it was built for — a broadcast composite with a fixed
slide rectangle beside static venue furniture. Room recordings need a signal
this function does not have (screen-edge geometry, projector luminance, or
boundary stability across frames) and ground truth to validate against.

## 0.18.66 — 2026-07-27

### fix(vault-ingress) — slide-region detection merged the speaker PiP into the slide box

`detect_slide_region` built a frame-difference map and then took the bounding
box of **every** above-threshold pixel. A conference broadcast composite has
more than one moving thing — the slide rectangle and a live speaker
picture-in-picture — and they are disjoint. Boxing them together produced a
region spanning the frame, which tripped the existing `area > 0.9` guard and
returned `None`. The deck was therefore never cropped, and the deduper went on
hashing the moving presenter and the JPEG noise around him.

Measured cost on Devoxx 2016 Docker Container Lifecycles: **963 extracted pages
for a 43-slide deck**, ~22x. The venue furniture sat at zero pixel variance and
the PiP at ~30, while the slide rectangle occupied only `x [0.32, 0.965]`,
`y [0.17, 0.842]`. Re-hashing the crop alone collapses 963 to 170.

Detection now labels 4-connected components of the mask and picks the one that
best fills its own bounding box — a slide changes wholesale and nearly fills its
box, a person-shaped blob does not. Component labelling is a small explicit
stack walk rather than `scipy.ndimage.label`, keeping the extractor's declared
dependency set. Validated against the two talks whose geometry was measured
independently: Docker resolves to `x [0.302, 0.967]`, `y [0.197, 0.848]`, within
~2% on every edge, and the JFokus 2015 composite now detects where it did not.

**Wide-angle room recordings remain unhandled, deliberately.** When the camera
frames the room instead of compositing a feed, ambient motion clears the
threshold everywhere and all regions merge into one low-fill blob; detection
returns `None`. Raising the percentile does surface a high-fill candidate, but
on CodeMash 2017 that candidate is 42% of frame width where the screen was
measured at ~22% — probably the presenters. No crop is shipped without ground
truth to validate it, because a wrong crop silently discards real slide content
whereas no crop merely leaves the existing over-count in place.

`PIPELINE_VERSION` 0.7.0 to 0.8.0 per the file's own policy: region-detection
logic changed.

## 0.18.65 — 2026-07-27

### feat(vault-ingress) — `write-analysis.py` renders the per-talk analysis files

Step 4 has two halves: merge the batch returns into the tracking DB, and write
`analyses/{talk_filename}.md` per processed talk. `persist-results.py` owned the
first. The second was assigned to the orchestrator in prose with no executable
form — so it depended on an agent choosing to hand-write a 160-line document per
talk, and across the 2026-07-26 full reparse it was skipped for all 82 talks.
Zero analysis files were touched that day. The DB held the corrected analysis
while every `analyses/*.md` still asserted what the reparse had just refuted: one
file claimed `live_demo: true` for a talk whose speaker says on tape "I didn't do
live demo. I'm not stupid."

The new script consumes the SAME `batch-returns.json` the merge consumes, so the
two halves cannot drift. It renders provenance, Dimensions 1–13, Dimension 14,
adherence assessment, structured data (scalars as a list, `per_slide_visual` as a
table, remaining nested blocks as fenced JSON), verbatim examples, the scoring
tables, and the reparse's `catalog_feedback` block. A section whose source field
is absent is skipped rather than emitted as an empty heading.

Two shape hazards are handled because real returns hit both: prose fields that
arrive as a list of finding objects instead of the schema's string (observed on
`areas_for_improvement` and `new_patterns`) are coerced to bullets rather than
failing the batch, and evidence strings containing `|` or newlines are escaped so
they cannot split a markdown table row.

Step 4's SKILL.md bullet now names the script instead of describing the document.

## 0.18.64 — 2026-07-27

### fix(vault-ingress) — stamp `processed_date` when a subagent return omits it

`persist-results.py` copied `processed_date` only when the return carried it.
Subagent returns routinely omit the field — three of three in one batch of the
2026-07-26 full reparse — so a talk merged with `status: processed` kept
whatever date the *previous* run had written. Two talks reparsed that day still
read `2026-04-09`, and one read `2026-05-01`.

The damage is to queryability, not to the analysis: every scalar and the pattern
score landed correctly. But "which talks has this reparse covered" is answered
from `processed_date`, and that question drives batch selection, the Section 15
recount, and the operator's read on progress. The DB reported 2 talks touched
when the real figure was 5.

`merge_talk` now takes an injectable `run_date` and stamps it when the return
omits or empties the field; a date the return *does* supply still wins. The CLI
resolves one date for the whole batch — so a run straddling midnight doesn't
split across two — and `--run-date` pins it for tests. The stdout summary gained
`run_date` plus a per-talk `stamped_processed_date` flag, so a stamp is visible
in the batch report rather than silent.

## 0.18.63 — 2026-07-26

### test(packaging) — guard against exec-bit-dependent script invocation

`tessl install` strips the executable bit from every packaged script: all 41
installed `.sh` / `.py` files arrive mode 644 in a consumer install, including
the 33 that are `100755` in git. A `./scripts/foo.sh` invocation therefore works
in this checkout and fails only for consumers — the same failure shape as the
0.18.43-0.18.61 packaging regression fixed in #132.

Nothing was broken: every existing call site already names an interpreter
(`bash x.sh`, `python3 x.py`) or uses `source "$HERE/x.sh"`, none of which
consult the exec bit. `tests/test_script_invocation_style.py` holds that
convention in place across skill docs and skill scripts, and asserts its own
detectors fire so the guard can't pass vacuously. Closes #134.

## 0.18.62 — 2026-07-26

### fix(packaging) — ship the skill scripts again, and gate it so they can't vanish

Every published version from **0.18.43 through 0.18.61** shipped with **zero**
of the 59 `skills/*/scripts/` files. Consumers got SKILL.md files instructing
them to run scripts that were not in the package.

Cause: `.tesslignore` uses gitignore pattern semantics, where an unanchored
`scripts/` matches a directory of that name at *every* depth. The entry was
added in the tile.json → plugin.json migration (0.18.43) to exclude the
repo-root CI helper directory — its own comment reads "plugin runtime scripts
live under skills/*/scripts/", which is exactly what it was silently deleting.
`tests/` had the same defect. `tessl plugin publish` reported success either
way: its "manifest references excluded paths" check inspects paths named
literally in the manifest, and the manifest declares skill *directories*.

- `.tesslignore`: anchored every repo-root-only pattern with a leading slash,
  and documented the depth-matching semantics at the top of the file
- `scripts/check-package-contents.sh`: new gate. Walks every tracked file under
  the manifest's declared `skills` / `rules` entries and fails when
  `.tesslignore` would strip any of them, naming the offending pattern and line.
  Matching runs against a throwaway empty git repo with `core.excludesFile`
  pointed at `.tesslignore`, so the repo's own `.gitignore` can neither mask a
  violation nor invent one
- Wired at both gates: `tests.yml` (pre-merge) and, via the new
  `scripts/pre-publish-checks.sh` composer, the publish workflow's
  `pre-publish-script` (which takes a single path)
- `.mcp.json` stays packed — tessl treats it as a manifest-referenced surface
  and packing fails without it

## 0.18.61 — 2026-07-25

### feat(vault-ingress) — OCR baked-in slide text on low-confidence slides (#129)

#116 / #119 stopped the extractor from **asserting absence** on full-bleed /
image-baked decks (`text_extraction_confidence: low` + analyst looks at pixels).
That fixed inverted "wordless backdrop" scoring. It did not extract the actual
words baked into those pictures.

This closes the other half: when confidence is low and PICTURE shapes exist,
`pptx-extraction.py` OCRs the picture blobs (tesseract via pytesseract) into
`ocr_text` and records `text_extraction_method` (`shapes` | `shapes+ocr` |
`shapes+ocr_unavailable`). Shape text stays in `text_content_preview`. Design
judgment (density, two-layer legibility, Dim 8/13) still needs rendered pages —
OCR is inventory for cites, transcript cross-checks, language policy, and
patterns like `second-look`.

- Soft-fail if tesseract is missing (one stderr warning; method
  `shapes+ocr_unavailable`); `--no-ocr` for shape-only runs
- CI installs `tesseract-ocr`; tests inject a fake engine for the contract and
  hit real tesseract for integration (skipif absent)
- Docs: `schemas-db.md`, `known-issues.md`, `subagent-instructions.md`,
  `second-look` detection heuristics

## 0.18.53 — 2026-07-17

### docs(vault-ingress) — record that stale vault artifacts are not inputs

A vault can hold files left by tools that predate this skill. `extract_pptx_visual.py` and its
`pptx-extraction-results.json` are the known case — orphaned when per-file extraction replaced them, and
read by nothing: not the skill, not the vault's own scripts or docs. `skills/vault-ingress/scripts/pptx-extraction.py`
runs per PPTX and feeds the analysis directly; no step consumes an aggregate results file.

Worth a note because the fossil is convincing. While building the (since-dropped) #116 reprocess migration,
it was mistaken for a live input and a migration was written against it — correct-looking code reading data
nothing consumes. Issue #120 was filed on the same unverified premise and is closed (`not planned`). The
durable rule: confirm a step reads a file before treating it as an input; a plausible filename in the vault
root is not a contract.

## 0.18.52 — 2026-07-16

### fix(vault-ingress) — stop reporting unreadable slides as wordless (#116)

`pptx-extraction.py` reads text out of PPTX *shapes*. AI-generated illustration decks bake every title,
callout label, and annotation into the picture, where python-pptx cannot see them — so those slides were
extracted as one full-bleed image with no text, and the analysis subagent read that absence as evidence.
Dimension 8 came out backwards for exactly the decks whose slides carry the most: the Arc of AI 2026 deck
(113 densely annotated slides) was recorded as *"overwhelmingly image-based … the speakers carry nearly
100% of the information verbally"*, and scored `vacation-photos` / `cave-painting` — patterns meaning the
opposite of what it is.

- **The extractor no longer asserts absence.** A slide whose largest picture covers at least
  `_TEXT_BEARING_IMAGE_AREA_RATIO` of the canvas — or whose background is an image, which covers the
  canvas by definition — reports `text_extraction_confidence: "low"` plus an `image_area_ratio`. A text
  overlay does not clear it: extracting *some* text is not evidence of extracting *all* of it. Re-run on
  the Arc of AI deck: 113/113 slides low-confidence, ratio 1.0.
- **`has_text_placeholder` → `has_text_frame_shapes`.** The old name asserted a claim the extractor cannot
  make; the new one names what it measures.
- **The analyst looks at pixels.** `subagent-instructions.md` requires Dimensions 8 and 13 to be judged
  from rendered slide images whenever any slide is low-confidence, and `rhetoric-dimensions.md` no longer
  lets `image_only_slide_count`'s "no *extractable* text" qualifier get lost — the drift that produced the
  bug.
- `known-issues.md` documents the failure mode so the conclusion "the slides are wordless" is never drawn
  from extraction output again.

`pptx-extraction.py` had no coverage for these fields; 9 tests added, decks and PNGs built programmatically
per `testing-standards`.

Reprocess-flagging of pre-fix analyses is deliberately **not** included. The vault's
`pptx-extraction-results.json` is written by `extract_pptx_visual.py` — a vault-local script absent from
this repo, emitting a schema this repo does not define (path-keyed, abbreviated per-slide fields). A
migration reading it would couple repo code to an unowned contract, and against the real vault the attempt
returned zero affected decks while reporting success. Tracked separately; the full reparse covers these
analyses regardless.

## 0.18.51 — 2026-07-16

### feat(presentation-creator) — wire the cover-or-match decision into intake and enforce it

The `walk-around` cover-or-match call is worthless as a retrospective score — by review time the talk is
already built in one register. It now enters at intake and is enforced.

- **Intake** — `phase0-intake.md` Step 0.4 ("Read the Audience Spread") asks whether the room is mixed in
  what it accepts as proof; the old Step 0.4 renumbers to 0.5. The step heads off homogeneity asserted from
  job titles (unverified ⇒ heterogeneous) and the speaker's own register answering for the room.
- **Schema** — `talk.audience_spread` required; `talk.dominant_register` required iff homogeneous, rejected
  otherwise. `walk-around` gains `registers` instance metadata.
- **Check** — `check-rhetorical.py` gains `_check_register_coverage`, mirroring `_check_sparkline_requirements`.
  The `script-delegation` split: the agent judges which registers a claim lands, the script checks the union.
  Detecting register from prose would be the regex trap. Zero walk-arounds FLAGs under either spread (an
  `N/A` there would let a homogeneous talk name a dominant register it never answers), and a `walk-around`
  without `registers:` FLAGs by location rather than reading as absent — mirroring `_check_opening_punch`'s
  treatment of a flavorless `opening-punch`.

**Breaking:** `audience_spread` is required, so older outlines fail validation with an actionable message —
deliberate, since a default would let the question be skipped, which is the failure being fixed. The six
`eval-resources/` outline fixtures are migrated here (all mixed-room conference talks ⇒ `heterogeneous`);
every `outline*.yaml` in the repo validates. Twelve tests cover the validators and both check branches.

Also suppresses a pre-existing pyright finding on `SlideFormat.title` inline with a stated reason per
`language-diagnostics` — a str-Enum member named after a str method is a false positive.

### feat(patterns) — map *The Whole Brain Business Book* into the taxonomy

Adds `walk-around` and the `golden-rule` antipattern from Ned Herrmann's *The Whole Brain Business Book*
(2nd ed., 2015), Ch. 8 and Ch. 13. Taxonomy: 109 → 111 entries (83 patterns + 28 antipatterns; 99
observable). The catalog had no entry for audience heterogeneity in *what counts as proof*.

**Why this is not the learning-styles error.** `know-your-audience`'s "Learning Styles Are a Myth" would
condemn a naive HBDI import. Herrmann prescribes *coverage* — assume the room is diverse, hit everything,
identify nobody — which is the opposite of the meshing hypothesis (identify a style, tailor to it) that
Pashler et al. refuted. The quadrant vocabulary is imported as a recognizable handle; the brain model, the
HBDI instrument, audience typing, and the book's gender-differences section (sourced to *Men Are from Mars,
Women Are from Venus*) stay out. `walk-around.md` states the boundary, the anti-meshing warning, and the
replicable premise the pattern rests on.

**Resolves a contradiction in the source.** Ch. 8 says cover all four quadrants; Ch. 13's MIT/CMU story says
the opposite — a metaphor-driven introduction was rejected by engineering faculty and the identical model
re-registered as "a first-order engineering approximation" won them over. The discriminator is audience
spread. Deliberately not filed under `leet-grammars`: that governs vocabulary and belonging, this governs the
epistemic form of the justification.

`golden-rule` joins `nodding-room` in Dimension 14's corner of failures that draw good feedback — both are
talks a subset of the room enjoys, which is why neither self-corrects, and both mislead `crucible` when its
feedback comes from inside the speaker's own register.

## 0.18.50 — 2026-07-16

### feat(patterns) — add `second-look`

Vault-derived build/slides pattern: build the slide in two legibility layers — a room layer that lands
from the back row, and a reward layer visibly present but too fine to read live. The unresolved detail
drives shownotes visits; the slide sells the return trip rather than teaching in the room. The mechanism
is a curiosity gap (Loewenstein 1994), not the disfluency claim retired below — hence the mandatory room
layer. Boundaries against `_anti_ant-fonts` and `_anti_slideuments`, and the link to `spaced-followup`
(the destination is a spaced re-exposure), are stated in the file.

Detection carries a caveat: the pattern is executed with text rendered inside images, so shape-level
PPTX extraction reports these slides as image-only and inverts the finding. Detectable only from
rendered slide images. The pipeline fix is #116.

### feat(patterns) — map *Make It Stick* into the taxonomy

Adds *Make It Stick: The Science of Successful Learning* (Brown, Roediger & McDaniel, 2014) as the
catalog's fourth supplementary source, following the *Presentation Zen* and *Resonate* precedent. The
existing corpus covered attention, persuasion, and aesthetics but not retention. Taxonomy: 104 → 109
entries (82 patterns + 27 antipatterns; 97 observable, 12 unobservable).

New: `guess-first` (generation effect), `retrieval-beat` (testing effect), `spaced-followup` (spacing
effect — unobservable; adds a **Post-Event** section to the go-live checklist, the catalog's first entry
firing after the talk), and the `nodding-room` antipattern (fluency illusion). Refinements folded into
`carnegie-hall`, `brain-breaks`, `know-your-audience`, `red-yellow-green`, and `analog-noise`.

**Correction — `analog-noise` was overclaiming.** It asserted as settled fact that hard-to-read fonts
improve retention (Diemand-Yauman et al. 2011, the study behind Sans Forgetica). That finding has
replicated poorly: a meta-analysis found essentially nothing for problem solving, and Sans Forgetica
studies found no benefit over an ordinary font. Re-grounded on the isolation effect (von Restorff),
which supports the same practice and derives the pattern's key constraint from its mechanism. The
desirable-difficulties framework is not retired — it concerns effortful *retrieval*, not effortful
*reading*. Full argument in the file's "Do Not Make It Hard to Read".

**Rejected, recorded so it is not relitigated:** interleaving (a centerpiece of the book, but braiding
topic threads is workshop guidance and fights `talklet`); mnemonics as a standalone pattern (the book
frames them as retrieval scaffolding, and `star-moment`'s sound-bite sub-type covers the speaker-side
use).

Every new file states its own limits: the generation- and testing-effect literatures study learners
across sessions, not audiences in a room for 45 minutes, so no file claims a talk produces month-later
recall.

Also drops the duplicated taxonomy counts from `phase3-content.md`, which claimed "78 patterns / 25
antipatterns matching the index" while the index said 26 — stale before this branch. The enum is
discovered from the `references/patterns/{prepare,build,deliver}/*.md` globs; the filesystem is the
source of truth and `_index.md` mirrors it for human readers.

## 0.18.45 — 2026-07-01

### fix(rules) — declare `qr-generation-rules.md` in the manifest

`rules/qr-generation-rules.md` was a steering rule in everything but configuration: same imperative
ALWAYS/NEVER/STOP voice as its siblings, referenced by the publishing flow (`phase6-publishing.md` §7)
and `generate-qr.py`, yet absent from the manifest's `rules` array and carrying no frontmatter — so it
never auto-loaded. The `tile.json` → `.tessl-plugin/plugin.json` migration (#106) preserved the
pre-existing omission rather than introducing it. Resolves it as a steering rule (#109): adds
conditional frontmatter (`alwaysApply: false` + `applyTo:` scoped to the presentation-creator QR
flow) per `jbaruch/coding-policy: rule-frontmatter`, declares it in `.tessl-plugin/plugin.json`, and
adds the README rules-table row. Behavior change: the QR rules now auto-load during the presentation
publishing flow instead of being reference-only.

## 0.18.44 — 2026-06-30

### fix(vault-ingress,vault-profile) — strip suspicious download-URL patterns from skill instructions

The `.tessl-plugin/plugin.json` migration (0.18.43) packages skills as directories, so vault-ingress's
reference docs are now scanned at publish — and tessl moderation flagged a Google Drive direct-download
URL (in the `gdown` PDF-fetch example) plus two truncated URL placeholders in the shownotes schema docs
as a Critical E005 finding, blocking the 0.18.43 release. Pass the bare Google Drive file id to `gdown`
(it accepts a `url_or_id` argument, so no download URL is needed) and replace the truncated placeholders
with prose.

## 0.18.43 — 2026-06-30

### chore — migrate `tile.json` manifest to `.tessl-plugin/plugin.json`

Converts the legacy `tile.json` manifest to the current `.tessl-plugin/plugin.json` form via
`tessl plugin migrate`: the `steering` field becomes `rules`, `skills` becomes an array of skill
directory paths, and `tile.json` is removed. Reconciles residual "tile" terminology to "plugin"
across user-facing prose and script messages — README (including the manifest field rename, so the
old "Steering Rules" section is now "Rules" matching `plugin.json` → `rules`), `deck-editing-setup.md`,
`processing-rules.md`, `tessl-version-floating.md`, `presentation-creator/SKILL.md`, the deck-build
`.sh` wrappers, `ensure-drivers.sh`, `generate-qr.py`, and `sync-deck-drivers.py` — and renames the
publish workflow `publish-tile.yml` → `publish-plugin.yml` (cosmetic `name:` and filename; the
trigger is push-to-main, so publishing is unaffected). The gh-aw reviewer prompts' "installed tile"
load-indicator wording becomes "installed plugin". Adds a root `.tesslignore` so the published
plugin ships its context surfaces (skills, rules, evals, manifest, `.mcp.json`, README) and excludes
CI, tests, repo-side scripts, and dev config. Live contracts are left intact: the `.tessl/tiles/`
runtime install path, `v1/tiles/...` registry routes, frozen `evals/*` scenario content, the
`deckops-spec.md` example slide, and historical CHANGELOG references to `tile.json`.

## 0.18.42 — 2026-06-30

### chore — stamp the CHANGELOG version backlog and wire auto-stamping

The CHANGELOG had accumulated un-headed `### ` blocks since 0.18.27 (stamping stopped at the
`## 0.18.26` heading) because no stamp step was wired — against `jbaruch/coding-policy:
context-artifacts` CHANGELOG Hygiene. Reconstructs and inserts the missing `## <version> — <date>`
headings for 0.18.29–0.18.41, with boundaries derived from each version's publish-bump commit and
validated against every entry's introducing commit (0.18.27/0.18.28/0.18.33 had no net-new entries
and are omitted). Wires `jbaruch/coding-policy/.github/actions/stamp-changelog` before
`tesslio/patch-version-publish` so future un-headed top blocks are stamped automatically at publish;
this entry is the first the wired step will stamp.

## 0.18.41 — 2026-06-29

### fix(presentation-creator) — deck drivers surface VBA errors to the CLI instead of a modal (#85)

Every RunDeckOps macro's failure handler popped a `MsgBox` and returned a bare `-1`. Under
osascript automation no human dismisses that modal, so it hung the run and then blocked every
subsequent macro call (PowerPoint `-18`) — the `BuildDeck -18`-on-large-decks symptom reported in
#85 — while the real `Err.Description` died in a dialog the CLI cannot read. All eight Public macros
are now typed `As Variant` and return `"ERROR: <macro> failed at [<token>]: <Err.Number> -
<Err.Description>"` on failure (the success path still returns the numeric count); each AppleScript
driver surfaces an `ERROR:`-prefixed return as an `osascript` error, so the description reaches
stderr. No macro calls `MsgBox`. This closes the last open item in #85 — the driver/`.bas`
packaging restore and the 1800s `with timeout` wrap already shipped.

## 0.18.40 — 2026-06-25

### feat(presentation-creator) — add the Flyover antipattern (audience condescension)

The Presentation Patterns taxonomy had no entry for the speaker who treats the room in
front of them as "flyover country" — diminishing the local audience or region while
valorizing their own home region/employer ("you might not have noticed it here, but where
I'm from it's a real thing"). The behavior sat in the gap between Negative Ignorance and
Alienating Artifact with no first-class name. Adds `deliver/_anti_flyover.md` (deliver
phase, dimensions 4 + 14, inverse of Know Your Audience) and wires it into `_index.md`
(catalog row, dimension maps, summary statistics). Bumps the taxonomy to 104 entries
(78 patterns + 26 antipatterns); the `outline_schema.py` antipattern enum auto-discovers
the new file and its count test is updated. Also reconciles a pre-existing README
miscount (Build phase listed 47/37 where the taxonomy holds 48/38) so the README totals
match `_index.md` at 104 entries / 93 observable.

## 0.18.39 — 2026-06-23

### feat(vault-ingress) — version the video slide-extraction pipeline

The video slide-extraction pipeline (`video-slide-extraction.py`) carried no version
marker, so video-extracted vault artifacts couldn't record which extraction iteration
produced them — and output depends on tunable knobs (`--fps`, `--threshold`, the 720p
download tier). A new `PIPELINE_VERSION` constant (starting at `0.7.0`, successor to the
pre-split monolith's ≈`0.6.0`) is stamped into the vault DB row
(`structured_data.video_extraction.pipeline_version`) and the output PDF's
producer/creator metadata. A `--version` flag prints `{"pipeline_version": "<version>"}`
(JSON, queryable without the extraction dependencies installed). The dependency import was
deferred so the version/help paths answer in a minimal environment. The
`structured_data.video_extraction` record also gains a `schema_version` (record-shape
version, distinct from the behavior-tracking `pipeline_version`) with a documented
reader/default contract for legacy entries. `references/video-slide-extraction.md`
documents a bump-on-behavior-change policy and `references/schemas-db.md` records both
fields and the reader contract. Resolves #103.

## 0.18.38 — 2026-06-19

### fix(illustrations) — masked/composited build edits keep static backgrounds pixel-stable

Backward-chaining progressive-reveal builds (`--build`) sent the whole frame to the image
model with only a text prompt and no mask, so the model was free to redraw everything: a
static background that must stay fixed across the reveal (a conveyor, a baseplate, a panel
frame, blueprint chrome) drifted in position/size or silently lost elements between frames —
even when the `erase` prompt named them in a `Keep` clause. A `Keep` clause reduces drift
but a maskless edit cannot guarantee the kept pixels survive. Build steps now take an
optional `erase_region` — a normalized `[x0, y0, x1, y1]` box (0..1, origin top-left, schema
validated) around the element being erased. When set, `--build` confines the edit to that
box: OpenAI receives a real edit mask (only the transparent box is regenerated), and for
both vendors the returned image is composited back over the prior frame via Pillow so every
pixel outside the box is the source pixel exactly. The box is still redrawn by the model
(the erased area shows real background, not a flat fill). Without a region the historical
whole-frame regeneration is unchanged, so existing outlines need no edits. Pillow (already a
project dependency) is imported lazily only when a region is used. `Build.erase_region` is
added to the outline schema; `rules/illustration-rules.md` and
`skills/illustrations/references/builds.md` document when and how to use it. Resolves #90.

## 0.18.37 — 2026-06-19

### fix(illustrations) — style-anchor `conventions` reach every generation prompt

`style_anchor.conventions` is a required field where `strategy.md` Step 9 tells authors
to bake the deck-wide, generation-relevant style rules (palette constraints like strict
grayscale, sequential numbering, recurring motifs). But `generate-illustrations.py`'s
`parse_outline` only read `style_anchor.full`/`imgtxt` — it validated `conventions` via the
schema and then threw it away, so those load-bearing rules never reached the image model.
A deck whose `conventions` said "no sepia / no warm tint" still drifted sepia because the
rule, though it "existed" in the outline, was never sent. `parse_outline` now folds the
collapsed `conventions` into every per-format anchor (the `[STYLE ANCHOR]` token expands to
"<format anchor> <conventions>") and surfaces the raw text under a new `conventions` key;
an empty `conventions` appends no stray separator. Resolves #83.

### fix(illustrations) — style anchor stays style-only; compose-only guard blocks furniture leak

The style anchor is injected into every slide's prompt, so anything in it renders on every
slide — yet nothing enforced that the anchor was *style-only*, and *Style-Anchor Discipline*
pushed the other way ("be specific, don't prune"). For document-style aesthetics (instruction
booklet, blueprint, newspaper), the page furniture — parts inventories, step strips, numbered
stations, exploded diagrams — reads like a style convention but is per-slide content, so the
whole deck's furniture cross-contaminated every slide (the title slide became "the entire deck
on one image"). `generate-illustrations.py` now appends a `COMPOSE ONLY THE SCENE` directive to
every fresh-generation prompt (generate / style-explore / compare — not erase-only edits),
pinning the model to the per-slide scene and barring instruction-page furniture and
other-slide elements. `rules/illustration-rules.md` (*Style-Anchor Discipline*) and
`strategy.md` Step 9 are rewritten to mandate a style-only anchor and reconcile "append, don't
prune" by axis: prune smuggled-in content, preserve and extend style specificity. Resolves #87.

## 0.18.36 — 2026-06-19

### fix(illustrations) — secrets.json read no longer hangs on a cloud placeholder

`load_secrets()` read `{vault}/secrets.json` with a plain `json.load(open(path))`. When that
file is a cloud-synced (e.g. iCloud) "dataless" placeholder — listed in the directory but
with its bytes evicted to the cloud — the read syscall blocks indefinitely while the OS
tries to materialize it. If the cloud is unreachable, the call never returns, freezing every
generate/build/edit run (and the test suite) before any work starts; `os.path.isfile()`
returns instantly because the metadata is local, so the guard didn't help. The read now runs
on a daemon thread with a bounded `SECRETS_READ_TIMEOUT` (10s); on overrun it raises
TimeoutError and `load_secrets` falls back to the existing `GEMINI_API_KEY` / `OPENAI_API_KEY`
env-var path with a loud stderr warning — the same degrade-don't-crash behavior it already had
for malformed/unreadable files (no silent swallow). Found while working on the build-edit fix.

## 0.18.35 — 2026-06-18

### fix(vault-ingress) — Step 4 persists structured fields deterministically

vault-ingress Step 4 told the orchestrator to hand-copy each subagent field into the
tracking DB, so anything it forgot was silently dropped: the rich `structured_data` the
subagents compute reached the per-talk analysis files but almost never landed in
`tracking-database.json` (1/196 talks had `slide_count`, `opening_type`,
`narrative_arc_type`, etc.). New `scripts/persist-results.py` removes the human from the
merge loop — it deep-merges the full `structured_data`/`verbatim_examples` blocks
(additive, so re-runs refine rather than wipe), normalizes `pattern_observations` into the
DB shape while keeping the detailed arrays Section 15 reads, and promotes the declared
queryable scalars (`slide_count`, `slide_design_style`, `illustration_style`,
`opening_type`, `closing_type`, `narrative_arc_type`, `audience_interaction_count`,
`co_presenter`, `delivery_language`, `pattern_score`) to each talk's top level. Fails
visibly on a filename mismatch instead of skipping. Step 4, `processing-rules.md`, and the
`schemas-db.md` talk entry are updated to the deterministic-merge contract. Resolves #97.

### feat(vault-ingress) — Step 9 hands off into clarification for same-week talks

vault-ingress Step 9 only *recommended* running `vault-clarification` for a freshly-ingested
talk delivered in the past 7 days — too weak for the case where it matters most, since
clarification quality decays fast and a recommendation buried at the end of a long ingress
report is easy to skip. Step 9 now tiers the handoff by recency: a talk delivered within
the past 7 days gets an explicit inline offer (via `AskUserQuestion`) to run
`vault-clarification` immediately, pre-seeded with the candidate topics Step 9 already
computes (per-talk `areas_for_improvement` and low-confidence/unverifiable
`pattern_observations`); on acceptance it invokes the skill carrying that seed agenda. The
7–30 day (full session) and 30+ day (compressed session) windows stay recommend-only.
Resolves #98.

## 0.18.34 — 2026-06-15

### fix(illustrations) — migrate image-gen model ids to GA, pin OpenAI snapshot

Google deprecates the `-preview` Gemini image ids on 2026-06-25. The registry's canonical
ids move to the GA strings (`gemini-3-pro-image`, `gemini-3.1-flash-image`); the `-preview`
ids are demoted to aliases so baked outlines still resolve. OpenAI's canonical id is
snapshot-pinned to `gpt-image-2-2026-04-21` (rolling `gpt-image-2` kept as an alias) for
reproducible illustration style; both confirmed live against the API. `GEMINI_API_BASE` /
`OPENAI_API_BASE` are hoisted into `model_registry.py` as the single source of truth — they
were duplicated across `generate-illustrations.py` and `generate-thumbnail.py`, whose own
`DEFAULT_MODEL` also moves to the GA id. The Gemini base stays on `v1beta`: verified live
that `gemini-3-pro-image` (the default) is served only on `v1beta` and 404s on `v1`. Rule
prose, the candidates-schema reference, and the illustration eval fixtures are updated to
the GA ids. Resolves #94.

## 0.18.32 — 2026-06-12

### fix(security) — drop suspicious download-URL examples from skill instructions

Removes the `bit.ly` shortener and concrete Google Drive / YouTube example URLs from
skill instructions. They tripped the tessl moderation **E005 "suspicious download URL"**
gate (Critical, install-blocking), which had held the public-install gate closed. The
flagged URLs predate this change; the examples are now generic placeholders or plain
descriptions — an agent infers URL shape without a literal sample. Functional download
commands (`gdown`, `yt-dlp`) and the speaker's real shownotes domain are unchanged.

## 0.18.31 — 2026-06-12

### feat(vault) — define the self-improvement outcomes of talk ingress

Turns three previously under-specified coaching surfaces into a coherent
three-level subsystem keyed on one definition: **adherence = consistency with the
speaker's own established style baseline**.

- **`adherence_assessment` is now defined** (`vault-ingress/references/processing-rules.md`).
  Previously a bare one-liner ("after 10+ talks, start providing adherence
  assessments") with no statement of adherence *to what*. Now a gated 2–4 sentence
  judgment with three ordered checks (pattern adherence, intent adherence,
  departure classification) and required anchors: cite this talk's `pattern_score`
  vs. the running average and name any recurring antipattern that reappeared.
- **Rhetoric-summary Section 15 now has a schema.** Previously "Section 15
  aggregates improvement areas" with no structure. Now five required subsections —
  recurring improvement themes (each tagged with antipattern ID + severity + talk
  count), the pattern-score + breadth baseline, signature patterns, underused
  patterns (growth), and resolved issues — making Section 15 the explicit baseline
  per-talk adherence measures against. Section 16 (speaker-confirmed intent)
  boundary documented.
- **Declining pattern scores are now attributed, not just flagged.** Adds
  `pattern_profile.score_drivers` to the speaker profile: a `declining` `score_trend`
  must name its causes. Attribution is **symmetric** — a decline comes from either
  bad things present (antipatterns rising) or good things absent (patterns fading /
  pattern range narrowing), and underuse alone can lower the score with zero
  antipatterns. vault-profile Step 4 computes it; Step 6 surfaces shifts in the diff.
- **Pattern underuse is now a first-class signal, not only antipatterns.** Adds
  `pattern_profile.pattern_breadth` (avg distinct patterns per talk + widening/stable/
  narrowing trend) to isolate "using enough of your toolkit" from antipattern
  avoidance, and `pattern_profile.underused_patterns` (never/rarely-used observable
  patterns that fit the speaker's modes) as positive-space coaching. Section 15 gains
  a "Underused patterns (growth)" subsection and a breadth line; Dimension 14 and the
  adherence pattern-check both treat underuse as a legitimate finding. Framed as range
  and fit, explicitly **not** count-maximization — cramming patterns is its own
  antipattern.
- Dimension 14 (`rhetoric-dimensions.md`) now asks each improvement issue to name
  its related antipattern ID + severity where one applies — the per-issue tagging
  that feeds both Section 15 aggregation and profile decline attribution.

Four additions turn the diagnostics into an actual coaching loop:

- **Closed the loop — improvement goals + verification.** New `improvement_goals`
  artifact in the tracking DB (owner: vault-clarification; reader/updater:
  vault-ingress, verification fields only; per-record `schema_version`). The speaker
  picks 1–2 focus areas from Section 15 (new clarification Step 6); a later ingress
  run (new Step 8) checks each against the fresh baseline and sets
  `achieved|improving|stalled|regressed`. The system now verifies the speaker acted,
  not just diagnoses. Schema in vault-clarification `schemas-config.md`; verification
  rubric in vault-ingress `processing-rules.md`.
- **Mode-relative baselines.** Adds `pattern_profile.by_mode` (per-mode score,
  breadth, top antipatterns; `stable` at ≥3 talks). Adherence and underuse now compare
  a talk to ITS mode's baseline when stable, else global — a lightning talk no longer
  reads as "underusing audience interaction" against a keynote yardstick.
- **Strengths reinforcement.** Adds `pattern_profile.strengths` (signature patterns +
  combinations with a `lean_in` line) and reframes Section 15's signature-patterns
  subsection as "lean in / double down" — the positive counterpart to recurring
  issues, distinct from celebratory badges.
- **Pacing/time adherence.** Adds `pacing.adherence` (talks over slide-budget, rate,
  trend, worst offenders), computed in vault-profile Step 4 from `slide_count` ÷
  `talk_duration_estimate` vs `slide_budgets`. The quantitative counterpart to
  Dimension 14's qualitative "rushing" read; marginal overages flagged softly
  (duration is only transcript-estimated).

## 0.18.30 — 2026-06-11

### feat(illustrations) — FULL-bleed composition as a first-class choice + `text_treatment` anchor field

Makes the poster-theatrical (full-bleed) path a deliberate, asked-for choice and
fixes baked-text drift between slides. Step 5 now asks the speaker — never infers —
how titles + footers render: **Bleed** (baked into each image, stylized to the
art, FULL-only, not editable; the noir reference deck) or **Overlay** (PowerPoint
text over a safe zone, editable, uniform font). Choosing Bleed sets
`style_anchor.composition: poster-theatrical` and locks every illustrated slide
to FULL (EXCEPTION/screenshot slides without an `image_prompt` are exempt).

Adds `style_anchor.text_treatment` — the per-deck rendering directive for baked
title + footer (e.g. "glowing hand-script neon on an in-scene surface"). It lives
on the anchor and is applied to every illustrated slide's baked text, so
titles/footers render identically; previously the model picked a treatment per
call and they drifted.

Codifies the anchor-vs-per-slide split: the anchor owns the style,
`text_treatment`, and the full `embedded_footer` (everything that must stay
consistent); the per-slide `image_prompt` carries only the scene and `text_overlay`
carries only that slide's literal title string. Also completes the outline.yaml
migration across all loaded context: stale markdown-format guidance in
`presentation-creator/SKILL.md` (incl. the obsolete "illustrations expects
markdown-style inputs" note), `phase2-architecture.md`, `generate-illustrations.py`
runtime messages, `generate-thumbnail.py`, `title-overlay-rules.md` §0,
`thumbnail-generation-rules.md`, and `resources-gathering-rules.md` now name the
`style_anchor.*` YAML fields. The `test_outline_source_is_yaml.py` contract test
scans skill prose + `rules/` (not just scripts) and fails on either a phantom
`presentation-outline.md` reference or the legacy markdown bold-field syntax
(`**Composition:**` / `**Embedded footer:**`) anywhere in loaded context.

## 0.18.29 — 2026-06-11

### fix(illustrations) — read outline.yaml, not a phantom presentation-outline.md

The three outline-consuming illustration scripts (`generate-illustrations.py`,
`apply-illustrations-to-deck.py`, `build-expansion-manifest.py`) regex-parsed a
`presentation-outline.md` that nothing in the toolkit generates — `outline.yaml`
is the single source of truth, and the model was left guessing how to hand-author
the markdown. All three now load `outline.yaml` through the shared
`outline_schema` loader (the partial view, so they work in Phase 2 before the deck
is complete). A new deterministic contract test
(`tests/test_outline_source_is_yaml.py`) discovers every outline-consuming script
and fails if any declares a `.md` outline argument, skips the shared loader, or
references the phantom file.

The schema gained the illustration-layer fields that previously lived only in the
hand-authored markdown: `style_anchor.composition` + `style_anchor.embedded_footer`
(deck-wide), per-slide `safe_zone` (zone + surface), and per-build `erase`. `erase`
carries the backwards-chaining edit prompt with its mandatory "Keep ..." clauses,
while the additive `desc` stays the human-facing reveal in `slides.md` — resolving
the long-standing mismatch where the generator expected erase prompts but the
authoring contract produced additive ones. `build-expansion-manifest.py` dropped
its now-redundant count/contiguity guards (the schema enforces contiguous-from-0
build steps at load).

### fix(presentation-creator) — fully prompt-free deck builds (stage all macro I/O through the container)

Extends the per-illustration container-staging to ALL macro file I/O. Sandboxed
PowerPoint also prompts (Powerbox) when a macro opens a Google-Drive base deck or
template, and when it saves output to a local `~/.deckops-staging` subdir (a
per-run `build.XXXXXX` dir prompts every run; a Drive folder E_FAILs). A new shared
`container-stage.sh` (sourced by every deck-ops wrapper) provides `stage_base` to
copy base decks / templates / the QR image into the container and open them from
there, and an `OUT_STAGE_DIR` inside the container for `SaveCopyAs`; the shell then
moves the result to the Drive destination. One EXIT trap in the helper owns
cleanup — `build-deck.sh` previously set its own trap that overrode the image-stage
cleanup and leaked staged copies; that's resolved. A full build now runs with zero
Powerbox prompts and no Full Disk Access grant. Validated end-to-end: BuildDeck +
ApplyBackgrounds, 46 slides, ~0.8s each (no blocking prompts), staging auto-cleaned.

### fix(presentation-creator) — BuildDeck now compiles and runs on Mac PowerPoint

Two Mac-only `BuildDeck` bugs, caught by a from-scratch deck validation (`BuildDeck`
had never actually run on macOS):
- `Shapes.AddChart2` is Windows-only; on Mac it raises a VBA compile error
  ("method or data member not found") that — under Compile-On-Demand — only
  surfaced when `BuildDeck` was first invoked, blocking the whole module. The chart
  path is now late-bound (`Object`), so the module compiles on Mac; `CHART` ops
  (never emitted by real decks) only error at runtime if actually used.
- `BuildDeck` stripped the template's slides before reading
  `SlideMaster.CustomLayouts`, and Mac PowerPoint prunes the now-unused layouts →
  every SLIDE op failed "layout index out of range (0 custom layouts)". It now reads
  the layouts while the slides exist and deletes the demo slides last (the
  `RunDeckOps` append-then-delete pattern), keeping layouts referenced throughout.

Validated end-to-end against a freshly-seeded `DeckOps.pptm`: `BuildDeck` built 46
slides from the talk's deck-ops, then `ApplyBackgrounds` applied all 46 illustration
backgrounds — a clean 38 MB deck.

### fix(presentation-creator) — restore deck drivers stripped by tessl install (#85)

`tessl install` materializes only `.md/.py/.json/.sh/.txt` and STRIPS
`.bas`/`.applescript`, so on every installed tile `RunDeckOps.bas` and the eight
`.applescript` drivers were missing — the whole PowerPoint deck layer was dead
(the `.sh` wrappers call `.applescript` drivers that call `RunDeckOps.bas`
macros). Verified empirically: `tessl plugin pack` includes them, `tessl install`
does not. Each driver now ships a byte-identical committed `.txt` mirror (which
survives install); `sync-deck-drivers.py` recreates the real files from the
mirrors (`materialize`), keeps mirrors in sync with the source drivers (`mirror`),
and a `check` mode guards drift in CI. `ensure-drivers.sh`, sourced by every
deck-ops wrapper, self-restores the `.applescript` drivers on first run; the
guided setup restores `RunDeckOps.bas` for the one-time VBE import. The `.txt`
mirrors are marked `linguist-generated` in `.gitattributes`; a unit test asserts
they stay byte-identical to the real drivers.

### docs(presentation-creator) — recurring per-build deck-editing runbook

`deck-editing-setup.md` covered one-time setup but only implied the recurring
requirement that `DeckOps.pptm` stay OPEN for the whole build (every pass calls a
macro in that running instance). A new "Step 6 — Every build (recurring)" makes it
explicit and lays out the pass sequence (structural build → ExpandBuilds → notes →
backgrounds → QR) and the PowerPoint+Keynote validation. `phase5-slides.md` now
surfaces the keep-open requirement on every build, not just first use.

### fix(presentation-creator) — collapse per-illustration Powerbox prompts to zero

Sandboxed PowerPoint threw a "grant access / select file" Powerbox prompt on
every `Slide.Background.Fill.UserPicture` of an image outside its container (each
Google Drive illustration) — one click per slide on a 40-slide deck. A new
`stage-images-into-container.py` copies the referenced images into PowerPoint's
own sandbox container (`~/Library/Containers/com.microsoft.Powerpoint/Data/.deckops-img-staging/`)
and rewrites the manifest paths; `apply-backgrounds.sh` and `expand-builds.sh`
stage before packing and clean up after the deck is written. A sandboxed app
reads its own container without a prompt, so prompts collapse to zero with no
Full Disk Access grant. Mac PowerPoint VBA has no `Application.FileDialog`, so a
"grant one folder" macro is impossible — container-staging is the supported
no-prompt path; if the container is absent the wrappers warn and fall back to the
original paths. The stager is unit-tested across both manifest shapes.

### fix(presentation-creator) — deck-build AppleScript drivers time out on large decks (#85)

The `run VB macro` call in every PowerPoint driver used osascript's default
~120s AppleEvent window, so a large build (e.g. a 46-slide `BuildDeck`) died with
`AppleEvent timed out (-1712)`. All eight drivers — including the new
`expand-builds.applescript` — now wrap the macro call in `with timeout of 1800
seconds`. (Issue #85 also reports the installed tile missing the `.applescript` /
`.bas` files and a `BuildDeck` `-18` on all-BLANK sequences: the dev tree packs
all drivers + `RunDeckOps.bas` — verified via `tessl plugin pack` — so the
published gap is being re-verified on the next publish; the `BuildDeck -18`
robustness fix is tracked separately in #85.)

### feat(illustrations,presentation-creator) — progressive-reveal build expansion in the deck

The toolkit generated build frames (`--build`) but never assembled them into the
deck — `builds.md`'s "Deck Insertion" was unimplemented. A new `ExpandBuilds` VBA
pass (`RunDeckOps.bas`) replaces each progressive-reveal parent slide with its
build frames as full-bleed background-fill slides (speaker notes on the final
frame only), via real PowerPoint slide insertion — structural edits never use
python-pptx (`rules/deck-editing-rules.md`). `build-expansion-manifest.py` emits
the plan from the outline + generated frames; `build-expansion-to-packed.py`
packs it into the wire format descending by parent; `expand-builds.sh` drives the
macro. Run it before the by-index passes (notes/backgrounds/QR), which must key
on the post-expansion deck since expansion renumbers later slides. The Python
emitter + packer are unit-tested; the VBA pass is validated by opening a built
deck (per the macOS VBA-untestable-in-CI rule).

### feat(illustrations) — poster-theatrical composition

A deck-level composition choice, decided in the style wizard and baked into the
STYLE ANCHOR header (`**Composition:** poster-theatrical` + `**Embedded footer:**`).
In this mode every slide is full-bleed and the title + footer are rendered INTO
the image — stylized and blended in the deck's own vocabulary — instead of
overlaid afterward. Generation appends an `EMBEDDED TEXT` directive (folding the
slide's `Text:` and the deck footer into the prompt) and skips the `TITLE SAFE
ZONE` directive entirely; apply records poster FULL slides as background-only (no
scrim, no overlaid title); deck-build omits the `TITLE`/`FOOTER` ops for those
slides. The QR code is the only shape inserted after generation. `title-overlay-rules.md`
§0 documents the opt-out. Small dense footer text (handles/hashtags/URLs) may be
approximated by the model and need a re-roll or `--edit` touch-up.

### feat(illustrations) — idea-sourcing wizard + render-before-bake gate

Style strategy (SKILL.md Step 3) was a single prose step bundling six sub-actions
with no enforcement, while the freshness gate (Step 2) was script-backed with a
"never skip silently" verdict. An agent shortcut the unenforced collaboration: it
ran the freshness check and `--shortlist`, then reasoned a model into the STYLE
ANCHOR and skipped both the priorities question and the exploration-grid render —
the speaker never saw a sample. Step 3 is now seven flat gated steps (source ideas
→ priorities → format → shortlist → propose → render grid → bake + verify). The
render writes a `style-explore/rendered.json` manifest of what actually rendered;
a new `generate-illustrations.py --check-style-explore` verdict and a guard inside
`run_generate` refuse generation unless the baked model was rendered in the grid,
turning "did a human pick from real samples?" into a deterministic tripwire. The
collaboration also became an explicit multi-select idea-sourcing wizard (your
usual / mode-or-series match / new / wild / trending / bring-your-own) with a
Quick-default fast path that still renders and shows. Shared wizard shape:
`skills/presentation-creator/references/idea-sourcing-wizard.md`.

### feat(presentation-creator) — explicit engine & theme sourcing (Phase 2 Decision #2)

Deck tooling (PowerPoint/pptx vs presenterm terminal-markdown) was decided
implicitly — inferred at Phase 5 with no record on the outline — so a demo-centric
talk that should run in a terminal tool could silently become a slide deck. A new
Phase 2 decision (#2, right after Mode) sources the engine via the shared
idea-sourcing wizard, reading an optional `presentation_engines[]` roster and the
chosen mode's `typical_engine`, and records `talk.engine` / `talk.deck_theme` /
`talk.engine_source` on the outline. Phase 5 now branches on `talk.engine` instead
of inferring; a null engine on a legacy outline falls back to inference with
author confirmation. Theme stays a thin provenance pointer — no named-theme
registry. New profile fields are optional/additive (no schema_version bump), so
existing profiles and outlines still validate. The Phase 2 decisions renumber
(Pattern Strategy #10→#11, Illustration Strategy #11→#12).

## 0.18.26 — 2026-06-09

### fix(qr-generation) — recreate legacy non-slug links; capture the custom-domain decision (#56)

Follow-up to the QR shortlink work shipped via #79, which enforced the slug-only
back-half for newly-created links but left two gaps.

- Slug-only back-half now applies to EXISTING tracked links too: a cached entry
  whose back-half isn't the slug is no longer reused or retargeted in place — it's
  recreated with the slug back-half (regression-tested).
- First short link captures the custom-domain decision: before creating a NEW
  shortened link, an absent `publishing_process.qr_code.{shortener}_domain` key
  STOPS so the agent asks the user and saves the answer — the domain, or `null`
  for "no custom domain" — so a configured custom domain is never silently
  skipped. Absent = never asked; `null` = decided (default domain), never
  re-asked. The MCP path makes the same check.
- Documented the `bitly_domain` knob in the profile schema (the code and the
  clarification flow already used it). `rules/qr-generation-rules.md` §2 (the
  custom domain must be used when configured) and new §7 (the three-state
  decision); phase6-publishing and the clarification prompts save an explicit
  `null`.

## 0.18.25 — 2026-06-08

### fix(illustrations) — --build enforces the Keep-clause preservation list (#46)

`--build` previously passed each `build-NN` description to the image editor
verbatim, auto-appending only safety clauses #1/#2; the mandatory preservation
list (component #3 of Edit Prompt Safety) was never applied, so a step that
erases a dense region left the element in place and the chain emitted visually
identical intermediate stages. The build flow now validates that every erase
step carries an explicit `Keep` clause and skips the slide with a stderr error
and a non-zero exit when one is missing — instead of silently producing a broken
chain. Build step descriptions must be authored as erase instructions with
`Keep` clauses (see `skills/illustrations/references/builds.md`).

## 0.18.24 — 2026-06-08

### feat(presentation-creator) — narrative.md becomes a TL;DR + slide-by-slide walk (#81)

`narrative.md` used to print the full `talk.thesis` (in practice 3–4 elaborated
paragraphs) and then the chapter `argument_beats` as prose with `*[slide N]*`
markers. The two sections stated the same argument at different granularities, so
the breakdown read as the thesis chopped into slide-tagged chunks — a reader saw
the whole argument twice. The narrative is also the only artifact that gives "the
idea + what's on each slide" in plain prose: `slides.md` is technical generation
input and `script.md` is the spoken words.

- New optional `talk.tldr` field on the outline schema: a short distillation of
  `thesis` (a couple of paragraphs or a bulleted list), authored by the agent.
  `narrative.md` renders it verbatim under `## TL;DR` and never reprints the
  elaborated `thesis`.
- Full `narrative.md` (slides authored) is now a one-line-per-slide walk grouped
  by chapter — `**N. Title** — synopsis`, 1:1 with `slides[]`, with live-demo
  interludes inlined at their anchor. The per-slide synopsis prefers
  `text_overlay`, falling back to the slide's `visual`.
- Partial `narrative.md` (Phases 1–2, no slides yet) keeps the chapter +
  argument-beat scaffold so the author still reviews the arc before slides exist.
- SKILL.md + phase3-content.md document the `tldr` field and the partial-vs-full
  rendering split.

`narrative.md` (the partial narrative scaffold) can now be generated and
reviewed before any slide exists. Previously
`extract-narrative.py` called `load_outline()`, which runs the full `Outline`
schema — `slides[]` (min 1), the `big_idea` singleton, paired callbacks, and
slide-budget math — so the human-readable narrative could not appear until Phase 3,
after slide content development had already begun. The narrative itself is fully
authored by the end of Phase 2, so the author had no readable artifact to approve
at the point the argument was actually being shaped.

- New `PartialOutline` model + `load_outline_partial()` in `outline_schema.py`
  validate `talk` (+ optional `chapters`) without the slide-dependent
  cross-validators. The full `Outline` stays the Phase 3+ source-of-truth contract.
- `extract-narrative.py --partial` renders from the partial view and emits a
  "narrative arc not yet authored" note when chapters are absent.
- SKILL.md: Phase 1 emits a partial stub; Phase 2 regenerates the full
  narrative and the gate now requires author approval of narrative + architecture
  before Phase 3. The plain (full-validation) extractor path is unchanged from
  Phase 3 onward.

## 0.18.23 — 2026-06-08

### fix(qr-generation) — replace inherited QRs in place; back-half always the slug (#56)

On a deck adapted (trimmed) from another talk, the QR step added a second QR
instead of replacing the inherited one, and only targeted the configured slide —
leaving stale QRs on earlier slides (e.g. an early shownotes slide). Now every
QR-bearing slide is detected and its QR replaced in place.

- `generate-qr.py`: QRs are detected by CONTENT, not size — `find_qr_rects`
  flags a square picture that is both ~2-color and roughly balanced between those
  colors, so it catches an inherited QR at any size (the same QR appeared at 1.8"
  and 2.8" in the repro deck) while excluding colored diagrams and mostly-one-color
  text screenshots. `resolve_target_slide_indices` targets every QR-bearing slide
  in addition to the configured placement.
- `RunDeckOps.bas` `InsertQR`: the macro can't run image libraries, so detection
  stays in Python; it now receives each slide's existing-QR geometry and just
  removes those exact shapes and places the QR there (same position/size, cleaning
  up duplicates). New placements still go bottom-right.
- The shortener back-half is now ALWAYS the talk slug — bit.ly custom back-half
  and rebrand.ly slashtag — dropping the `preferred_short_path` override (removed
  from the profile schema). If bit.ly can't set the slug back-half, the create now
  fails (degrading to the raw URL) rather than silently keeping a random hash.
  Documented in `rules/qr-generation-rules.md`.
- Bug 2 (fetch colored QRs from Bitly to drop the local `qrcode` dep) is
  won't-fix: the dependency can't be dropped (rebrandly / `none` / `--png-only`
  paths render locally), and the one-call QR-codes endpoint abandons the managed
  bitlink model (custom domain, PATCH-able target, tracking).
- macOS + PowerPoint only for the `InsertQR` change; untestable in Linux CI by
  design. The QR-detection, slide-targeting, and back-half logic IS unit-tested.

## 0.18.22 — 2026-06-07

### fix(shownotes-publisher) — content-only gate decides direct-push vs branch+PR

Step 9 runs `skills/shownotes-publisher/scripts/content-only-gate.sh` against the
shownotes repo before publishing. When every pending change touches only the
declared content globs, the skill direct-pushes to `main`; any out-of-glob path,
or an indeterminate state, falls back to branch + PR. This is the Form B
client-side gate that `jbaruch/coding-policy: ci-safety`'s Content-Only
Direct-Push Carve-Out permits where server-side allowlist enforcement is not
expressible on a github.com personal repo (coding-policy#119, shipped in
coding-policy 0.3.52). The carve-out's precondition 1 is satisfied by a new
authority-of-record steering rule, `rules/shownotes-content-publish.md`, naming
the covered globs, the gate script, and the review the direct-push skips. Fixes #65.

## 0.18.20 — 2026-06-07

### fix(qr-generation) — compose date-less talk slugs (QR + Phase 1) (#55)

Completes the date-less-slug convention. #66 made the publisher consume
`talk.slug` verbatim (date-less filename and URL); this drops the date prefix
from how slugs are *composed*, so the QR back-half and the Phase 1 slug match the
published page instead of pointing at a stale `YYYY-MM-DD`-prefixed back-half.

- `rules/qr-generation-rules.md` §4: the QR back-half IS `talk.slug`, composed in
  Phase 1 (per the speaker's `slug_convention.template`) and used VERBATIM — no
  invent / rephrase / re-derive / date-prefix. Replaces the old
  `{YYYY-MM-DD}-{conference-slug}-{talk-short-name}` format and removes the
  self-contradictory derive-from-delivery-date guidance. §2 example date-less.
- `rules/interaction-rules.md` and
  `skills/presentation-creator/references/phase1-intent.md`: the Phase 1
  slug-confirmation examples are now date-less (`jcon26-robocoders`).
- QR eval scenarios (`qr-bitly-slug-from-outline`,
  `qr-missing-shortener-detection`): fixtures + criteria updated to a date-less
  slug, in a synthetic namespace (`froconf26-cache-stampedes`) distinct from the
  `devnexus`/`robocoders` examples used in skill/rule context (no fixture/example
  bleeding).
- `generate-qr.py` needed no change — it already uses the passed `--talk-slug`
  verbatim as the custom back-half.
- Left intentionally: `url.template` date variables (URL *assembly*, configurable
  per deployed site — tracked in #17), and legacy date-prefixed filenames already
  published (the publisher's never-rename guard) or ingested into the vault.

## 0.18.16 — 2026-06-07

### fix(shownotes-publisher) — use talk.slug as the filename, drop the date prefix

`talk.slug` from `outline.yaml` is now the single source of truth for a new
talk's `_talks/` filename and live URL: the filename is always `{talk_slug}.md`,
never `{YYYY-MM-DD}-{talk_slug}.md`. The old `delivery_date`-conditional branch
overrode the speaker's chosen slug with a date-prefixed name, so the published
URL diverged from the slides + QR (which point at the bare slug) — it had to be
renamed by hand and the Bitly QR repointed. The downstream `{filename_stem}`
indirection is replaced by `{talk_page_stem}` — `{talk_slug}` for new talks, the
existing date-prefixed stem when updating a legacy page — so the
never-rename-a-published-file guard holds without duplicating legacy talks.
Fixes #66.

## 0.18.15 — 2026-06-07

### feat(presentation-creator) — whole-deck creation via real PowerPoint (#57 Phase D)

Retires the last python-pptx + MCP-PPT-server deck-writing path. Slide structure
was created by stripping the template with `strip-template.py` (python-pptx) and
then walking the deck through the MCP PPT server (`add_slide` /
`populate_placeholder` / `add_bullet_points` / `manage_image` / `manage_text` /
`add_shape` / `optimize_slide_text`). Both are gone — `BuildDeck` creates the
whole deck in the real PowerPoint app, so the engine that ships valid,
Keynote-openable `.pptx` is now the sole writer for creation as well as edits.
Completes #57: real PowerPoint is the sole `.pptx` engine.

- **`BuildDeck`** (in `RunDeckOps.bas`) — opens a uniquely-named template copy,
  deletes the template's demo slides (subsumes `strip-template.py`), and executes
  a flat op sequence: `SLIDE` / `TITLE` / `SUBTITLE` / `BODY` / `BULLET` / `TEXT`
  / `IMAGE` / `SHAPE` / `BG` / `FOOTER` / `OPTIMIZE` / `TABLE` / `CELL` / `CHART`
  / `CAT` / `SERIES` — full parity with the retired MCP surface, in one module
  (VBA has no package manager; the macros share private helpers). When a layout
  lacks the requested title/subtitle/body placeholder, `BuildDeck` preserves the
  op's content in a fallback text box rather than dropping it silently.
- **`build-deck.sh` / `build-deck.applescript`** — wrapper + driver. The
  AppleScript reads the ops file as UTF-8 and passes it as one Unicode arg (no
  VBA-side decoding); the wrapper validates first, stages locally, then moves the
  output into place (sandboxed PowerPoint can't write to a Google Drive folder).
- **`validate-deckops.py`** — deterministic, unit-tested
  (`tests/test_validate_deckops.py`) op-sequence validator (UTF-8): op vocabulary,
  arity, int/float fields, BG 0–255, non-negative layout index, and state rules
  (ops need a prior `SLIDE`; `CELL` needs a `TABLE`; `CAT`/`SERIES` need a `CHART`;
  `SERIES` needs ≥1 value; a `CHART` needs ≥1 `SERIES` so it never ships
  PowerPoint's default sample data). `BuildDeck` raises a clear error on an
  out-of-range layout index rather than silently remapping it. The
  PowerPoint-driving layer stays manually validated.
- **`references/deckops-spec.md`** — the op-sequence spec (delimiter, fields,
  state rules, enum values, build-then-assemble for fragments).
- **Removed `strip-template.py` and `_pptx_repair.py`** (and `test_strip_template.py`
  + the `strip_template` / `pptx_repair` conftest fixtures) — `_pptx_repair.py`'s
  only consumer was `strip-template.py`.
- Rewired `SKILL.md` Step 5 and `phase5-slides.md` from the MCP walk to
  emit-ops → `validate-deckops.py` → `build-deck.sh`; the MCP tool quick-reference
  table is now a deck-op quick-reference. `slide-generation-rules.md` reconciled to
  BuildDeck (not python-pptx, not MCP); the stale `_pptx_repair.py` / `generate-qr.py`
  Keynote-carve-out example and the obsolete python-pptx code snippets are dropped.
- macOS + PowerPoint only; untestable in Linux CI by design — validate by
  re-opening output in PowerPoint and Keynote. The untestable-VBA gap for #57 is
  owner-authorized (tracked in jbaruch/coding-policy#116).

## 0.18.13 — 2026-06-04

### feat(presentation-creator) — QR insertion via real PowerPoint (#57 Phase F)

Retires `generate-qr.py`'s python-pptx deck write (`insert_qr_on_slides` +
`_remove_existing_qr` + `prs.save`) for an `InsertQR` VBA macro. `generate-qr.py`
keeps everything else — URL/shortener resolve, per-slide background-color match
(read-only), target-slide finding, and QR PNG generation — and calls
`insert-qr.sh` for the write.

- **`InsertQR`** (in `RunDeckOps.bas`) + `insert-qr.applescript` / `insert-qr.sh`
  — places the QR bottom-right (2.0in, 0.3in margin) on the given 1-based slides,
  removing any existing corner QR first (idempotent re-runs).
- `generate-qr.py` threads the deck through uniquely-named intermediates (one
  `InsertQR` pass per color variant) and moves the result back; the python-pptx
  `Inches`/`Emu`/`RGBColor` imports and the QR-insert test are dropped.
- The QR insert is now macOS + PowerPoint only (the rest of `generate-qr.py`
  stays cross-platform). Completes #57's deck-writer retirement. Untestable in
  Linux CI by design — validate by re-opening in PowerPoint and Keynote.

## 0.18.12 — 2026-06-04

### feat(presentation-creator) — placeholder slides via real PowerPoint (#57 Phase E)

Retires `insert-placeholder-slides.py` (python-pptx) for a `MakePlaceholderSlide`
VBA macro driven through the real PowerPoint app.

- **`MakePlaceholderSlide`** (in `RunDeckOps.bas`) + `make-placeholder-slide.applescript`
  / `make-placeholder-slide.sh` — builds a loud yellow `[PLACEHOLDER]` slide (title
  auto-prefixed, optional subtitle) as a 1-slide deck sized to the base deck.
- Positioning uses the existing `run-deck-ops.sh` order string: Mac VBA's
  `Slide.MoveTo` raises E_INVALIDARG, so placeholders are built then assembled at
  their target slots via `InsertFromFile`, rather than inserted-and-moved.
- Advances #57 (real PowerPoint as the sole `.pptx` writer). macOS + PowerPoint
  only; untestable in Linux CI by design — validate by re-opening in PowerPoint
  and Keynote.

## 0.18.11 — 2026-06-04

### feat(presentation-creator) — speaker notes via real PowerPoint (#57 Phase C)

Retires `inject-speaker-notes.py` (python-pptx) in favor of a `SetSpeakerNotes`
VBA macro driven through the real PowerPoint app. PowerPoint serializes valid
notes OOXML — including the `<p:notesMasterIdLst>` element python-pptx omitted —
so the Keynote-compatibility patch the python path carried is no longer needed
(retiring the *cause* of the breakage, not a safety net).

- **`SetSpeakerNotes`** (in `RunDeckOps.bas`) + `inject-notes.applescript` /
  `inject-notes.sh` — sets per-slide notes via PowerPoint, writes a COPY.
- AppleScript reads the notes file as UTF-8 and passes it to the macro as one
  Unicode argument (control-char-delimited records), so VBA never decodes UTF-8
  from disk. Slide numbers convert 0-based (the JSON) → 1-based (PowerPoint).
- **`notes-to-packed.py`** — deterministic JSON→wire-format packer, unit-tested
  (`tests/test_notes_to_packed.py`); the VBA layer stays manually validated.
- Phase 5 / `phase5-slides.md` rewired: notes inject via `inject-notes.sh` after
  the illustrations apply pass and before the final `apply-backgrounds.sh` write.
- Advances #57 (real PowerPoint as the sole `.pptx` writer). macOS + PowerPoint
  only; untestable in Linux CI by design — validate by re-opening in PowerPoint
  and Keynote.

## 0.18.10 — 2026-06-03

### fix(shownotes-publisher) — stop agents skipping thumbnail generation

Step 6 (Thumbnail) was opt-out: it stated the page "renders fine without one"
(the `onerror` placeholder fallback), framed production as a vague conditional
hand-off to the illustrations skill, and ended "Proceed immediately to Step 7"
with no gate — so agents always skipped it and the talk card fell back to the
placeholder SVG. Step 6 is now an explicit decision: check the convention-path
file (`assets/images/thumbnails/{filename_stem}-thumbnail.png`); if absent,
either produce it via `Skill(illustrations)` when a source image is available,
or explicitly record it as deferred to Phase 7 (pre-talk publish with no
slides/video). Never a silent fall-through. Fixes #58.

## 0.18.9 — 2026-06-03

### feat(presentation-creator) — PowerPoint-native deck editing (preserves illustrated backgrounds)

Adds a non-corrupting way to make structural edits (delete / reorder /
cross-deck import) to an existing `.pptx`, driven by the real PowerPoint app
instead of python-pptx, and makes it the SOLE structural-edit path. Prompted by
a concrete failure: trimming a 128-slide, 51 MB illustrated deck with
python-pptx / clipboard paste flattened every slide whose full-bleed art is a
per-slide background fill — the output dropped to 6.2 MB with all backgrounds
gone (picture *shapes* survived, per-slide `<p:bg>` fills did not). The
InsertFromFile path recovered the same cut to 24 MB with backgrounds intact.

- **Removed `delete-slides.py` / `reorder-slides.py`** (and their tests +
  conftest fixtures) — python-pptx slide-delete / reorder strips per-slide
  background fills, so it is no longer offered for any deck. All structural
  edits route through RunDeckOps. `_pptx_repair.py` stays (used by
  `strip-template.py`). `phase5-slides.md`, `SKILL.md`, and the README script
  tree updated to match. Tracked in #57.
- **New steering rule (`rules/deck-editing-rules.md`)** — drive real PowerPoint
  for all structural edits; documents the Mac PowerPoint VBA landmines and how
  each is handled.
- **`RunDeckOps.bas`** — reusable VBA macro that rebuilds a deck via
  `Slides.InsertFromFile` (keep-source-formatting Reuse Slides) in a target
  order, with cross-deck import, global text replace, and a COPY-only save.
  Guards against the filename-collision trap and self-cleans on failure.
- **`run-deck-ops.applescript` + `run-deck-ops.sh`** — driver and wrapper; the
  wrapper stages locally then moves into place (sandboxed PowerPoint can't
  create files in a Google Drive File-Provider folder).
- **`MakeBgImageSlide` (+ `make-bg-slide.applescript` / `make-bg-slide.sh`)** —
  turn a generated illustration into a slide whose image is the BACKGROUND FILL
  (so the layout's halftone-dot overlay covers it, matching the other comic
  slides) by cloning a template slide, swapping its background, and retitling —
  a top-pasted picture would sit above the overlay. Produces a 1-slide deck to
  import via `run-deck-ops.sh`.
- **`ApplyBackgrounds` (+ `apply-backgrounds.applescript` / `apply-backgrounds.sh`)** —
  the creation-time counterpart: set FULL-slide illustration backgrounds in bulk
  via `Slide.Background.Fill.UserPicture`, run as the final write of the build.
  `apply-illustrations-to-deck.py` no longer inserts FULL-slide picture shapes —
  it records each FULL slide in a backgrounds manifest (`--backgrounds-out`) and
  applies only scrim + title; IMG+TXT keeps its left-column picture shape. Begins
  retiring python-pptx as a deck writer for creation (Phase B of #57). Phase 5
  reorders so the VBA background pass runs after speaker-note injection.
- **Policy-review hardening** — `rules/deck-editing-rules.md` gains `alwaysApply`
  frontmatter and sheds rationale prose; `references/deck-editing-setup.md` drops
  the pause-and-wait flow for continue-immediately; the wrappers emit actionable
  validation errors; and the deterministic manifest→spec step is extracted to a
  unit-tested `backgrounds-manifest-to-spec.py` (the VBA core stays CI-untestable
  by design).
- macOS + Microsoft PowerPoint only — drives the app via Automation, so it is
  untestable in Linux CI by design; validate output by re-opening in PowerPoint
  and Keynote. README steering-rules table and `tile.json` steering updated.
- Full retirement of MCP + python-pptx as deck writers (real PowerPoint becomes
  the sole `.pptx` engine) is tracked in #57 with a phased plan.

## 0.18.7 — 2026-06-03

### feat(illustrations) — structured style selection + model registry

Reworked the Phase 2 illustration-strategy flow and the model roster behind it,
prompted by two reported failures: the SKILL.md Step 2 model-freshness check
effectively never ran (prose-only with a "proceed silently if everything is
represented" escape hatch, so an agent left no trace and skipped it), and a
refresh asked to update the model list dropped the `nano-banana-*` entries —
because "nano-banana" is Google's codename for the Gemini image line (Nano
Banana Pro = Gemini 3 Pro Image), and a bare string list carries nothing tying
the codename to the canonical id.

- **Model registry (`skills/illustrations/scripts/model_registry.py`)** — the
  bare `COMPARE_MODELS` list became a structured registry: canonical id, vendor
  family, aliases, and per-model cost/speed/quality tiers + edit support. The
  redundant `nano-banana-pro-preview` entry folded into
  `gemini-3-pro-image-preview` as an alias. `resolve_model_id()` maps any baked
  codename to the canonical API id before dispatch. `COMPARE_MODELS` is now
  derived from the registry for backward compatibility.
- **Freshness precheck** — `model_registry.py --check-freshness` emits
  `last_reviewed` / `age_days` / `stale` / roster JSON from a date heuristic
  (`REGISTRY_LAST_REVIEWED` + 90-day max age). SKILL.md Step 2 runs it first and
  reports the verdict in one line — no silent skip. WebSearch + registry
  reconciliation fires only when stale; for an existing outline the agent also
  checks the baked model against the roster.
- **Optimization priorities → shortlist** — Step 3 elicits what the speaker
  optimizes for (cost / speed / quality / build-editability) and narrows the
  roster with `model_registry.py --shortlist <priorities>` before any render.
  `build-editability` hard-excludes Imagen (no edit endpoint); cost/speed/quality
  are soft rankings.
- **Style exploration** — `generate-illustrations.py --style-explore` reads a
  `candidates.json` (styles × shortlist × formats; schema in
  `references/style-explore-candidates-schema.md`) and renders into a structured
  `style-explore/<style>/<format>/<model>.<ext>` tree with an `index.md` contact
  sheet, so the speaker picks style and model together from rendered output.
- **Hybrid roster (cache + live inject)** — the registry is a seed cache, not an
  allowlist. Rendering accepts any id from a supported vendor family with no code
  change; a web-discovered model can be ranked for one talk via
  `shortlist_models(extra_models=...)` / `--shortlist --add '<json>'` without a
  table edit. Persistent additions land in the registry through the Step 2
  refresh.
- **Docs + evals** — rewrote `references/strategy.md` (priorities → format →
  shortlist → style proposals → exploration render → continuity), updated
  `generation.md`, the SKILL.md Key Files table, and presentation-creator's
  Decision #11. Updated the two `illustrations-freshness-*` eval criteria to the
  precheck contract and added `illustrations-priority-model-shortlist`. New tests
  cover alias resolution, shortlist ranking + injection, the freshness date math,
  and the style-explore helpers.
- **Follow-up (pre-existing):** the `illustrations-mode-routing` eval criteria
  count steps without the freshness step (off by one vs the committed 7-step
  SKILL.md). The README "6 mode-routed steps" comment is corrected here; the
  mode-routing criteria renumber is left for a dedicated pass.

### feat(shownotes-publisher) — new skill for the Jekyll shownotes site

A sixth skill, `shownotes-publisher`, writes talk pages into a
Jekyll-based shownotes site (`~/Projects/shownotes`, published at
`https://speaking.jbaru.ch`). The site uses a custom markdown parser
(`_plugins/markdown_parser.rb`) that extracts structured fields by
pattern-matching on the body — abstract under `## Abstract`,
field-block lines like `**Conference:** value` + `**Video:** [text](url)`,
presentation-context paragraph starting with "A presentation at",
resources under `## Resources`. The format is strict; small mistakes
silently flatten content (e.g., multi-paragraph abstracts become one
paragraph because the parser joins all lines with spaces before
`markdownify`).

The skill encodes the contract end-to-end:

- **`SKILL.md`** — 9-step workflow from outline.yaml gather through
  publish, with the field-block grammar, the "Video Coming Soon"
  pattern, thumbnail conventions, and the update-don't-rewrite rule
- **`references/parser-contract.md`** — line-by-line spec of what
  each `extracted_*` field captures (title, conference, date,
  slides, video, abstract, resources, presentation_context) and how
- **`references/template-conditionals.md`** — what `talk.html` does
  with each extracted field, including the truthiness trap on
  `extracted_video` (any non-empty string triggers "Video Available"
  — `**Video:** TBD` fires the wrong badge)
- **`references/common-mistakes.md`** — 13 documented failure modes
  (entries 1, 1b, 1c, 2–11) with what visually happens and the right
  way (e.g., abstract sub-headings flatten; bare-URL Slides/Video
  doesn't extract; resource before abstract folds abstract into
  resources)

**Motivating incident.** This skill was authored after the
KotlinConf 2026 talk file shipped on `jbaruch/shownotes` commit
`83ac8d9` with placeholder-URL Slides/Video lines:

```markdown
**Slides:** [View Slides](#) <!-- TODO -->
**Video:** [Watch Video](#) <!-- TODO -->
```

Both fields fired the wrong badges and rendered broken embeds; the
inline HTML comments were pulled into the captured field values by
the parser's `^\*\*Slides:\*\*\s*(.+)$` value-capture group. The
incident motivates entries 1b and 11 in `references/common-mistakes.md`.

The key behaviors the skill enforces:

- **No video frontmatter until video is published.** The layout's
  `{% if page.extracted_video %}` is what flips the "Video Coming
  Soon" badge to "Video Available". Adding `**Video:** TBD` (or any
  placeholder) makes `extracted_video` truthy and fires the wrong
  badge plus a broken embed
- **Abstract is exactly one paragraph.** The parser joins all
  non-empty lines under `## Abstract` with a single space, collapses
  whitespace, then passes the result to `markdownify`. Sub-headings,
  lists, code blocks, and tables inside the abstract render as
  flattened prose
- **Slides/Video URLs must be markdown links.** The URL extraction
  regex is `\[([^\]]+)\]\(([^)]+)\)`. Bare URLs survive in the
  field value but break the embed include's URL-pattern matching
- **Update existing files in place.** Speakers hand-edit shownotes
  post-publish (typo fixes, resource additions). A re-author wipes
  those edits silently. The skill reads-then-edits, never overwrites

Four eval scenarios ship with the skill, all under `evals/`:

- `shownotes-publisher-publish-with-date` — first-time publish, the
  delivery date is set, filename uses the dated convention
- `shownotes-publisher-publish-no-date` — pre-talk publish where the
  delivery date is absent, filename and Date field both adapt
- `shownotes-publisher-update-add-video` — adds a video URL to an
  existing file, exercises the read-then-edit preservation rule
- `shownotes-publisher-omit-placeholder` — negative case; the user
  asks for a "video coming soon" UX cue, the skill must omit the
  `**Video:**` line entirely rather than emit a placeholder URL

The skill is invocable directly (`Skill(skill: "shownotes-publisher")`)
or after the presentation-creator skill finishes Phase 6 publishing
when the speaker says "now publish to shownotes". Tile size: six
skills, `tile.json` and README updated accordingly.

### feat(presentation-creator) — outline.yaml is now the source of truth

The presentation-creator skill moves from two hand-authored markdown
files (`presentation-spec.md` for talk metadata, `presentation-outline.md`
for the outline) to a single schema-validated `outline.yaml`. The four
derived artifacts (`narrative.md`, `script.md`, `slides.md`,
`rhetorical-review.md`) generate deterministically from it.

**What changed:**

- New `scripts/outline_schema.py` — pydantic v2 source of truth.
  `talk:` block (title, slug kebab-case-validated, speakers, duration,
  audience, mode, venue, slide_budget, pacing_wpm, architecture from
  closed enum, thesis, shownotes_url_base, commercial_intent,
  profanity_register, must_include, must_avoid, catalog_reference,
  delivery_count, delivery_date). `chapters[]` with target_min,
  cuttable, accent, argument_beats for `narrative.md`. `slides[]`
  with format (FULL/IMG+TXT/EXCEPTION/TITLE/DEMO), visual,
  text_overlay, image_prompt, builds, screenplay-form script with
  speaker attribution, applied_patterns against the 77-pattern closed
  enum discovered from `references/patterns/`, callbacks ledger,
  big_idea singleton, thesis preview/payoff. `interludes[]` for live
  demos between slides (anchored by `after_slide`). `style_anchor:`
  block for illustration-strategy talks.

- Four new extractor scripts:
  - `extract-narrative.py` → chapter walker, prose
  - `extract-script.py` → screenplay form, slides + interludes
    interleaved by anchor
  - `extract-slides.py` → per-slide build sheet
  - `check-rhetorical.py` → structural gap-check over the closed
    pattern taxonomy (PUNCH coverage, big-idea singleton, thesis
    ordering, sparkline elements when applicable, master-story
    threading, callback ledger, inoculation count, progressive-list
    contiguity, duration accounting)

- Existing scripts rewritten to consume `outline.yaml`:
  - `guardrail-check.py` — profile-aware checks (slide budget, Act 1,
    branding, profanity, data attribution, closing, cut lines); the
    structural taxonomy now belongs to `check-rhetorical.py`
  - `extract-resources.py` — walks `slides[]`/`interludes[]` via
    `outline_schema`; image prompts deliberately excluded
  - `generate-talk-timings.py` — walks `chapters[]`; no markdown
    parsing

- Skill prose rewritten end-to-end: `SKILL.md` (workflow table, all
  phase steps, late-entry checklist, artifact table),
  `phase1-intent.md` (talk metadata → `talk:` block),
  `phase3-content.md` (full rewrite teaching the YAML schema),
  `phase4-guardrails.md` (two-script split documented),
  `phase5-slides.md` (slides.md is the build sheet; `{slug}.md` for
  presenterm decks), `phase6-publishing.md` and
  `phase7-post-event.md` (file refs updated).

**Why it matters:** the markdown outline format required regex
parsing for every downstream consumer (guardrail-check, extract-
resources, generate-talk-timings, the agent itself), and every
change to the format risked breaking parsers in unrelated scripts.
Schema validation + four single-responsibility extractors collapses
that parsing surface into one pydantic model and four deterministic
walkers — per `rules/script-delegation.md`'s deterministic-vs-
reasoning split.

### evals — rename to descriptive names, port fixtures to YAML

All numeric `scenario-N` evals renamed to descriptive kebab-case
(e.g., `scenario-20` → `qr-missing-shortener-detection`).
`eval-resources/` subdirectories renamed to match. Fixtures that
referenced `presentation-outline.md` or `presentation-spec.md`
converted to `outline.yaml` (QR scenarios, thumbnail evals, CFP,
illustrations-mode-routing, freshness evals, pattern-strategy-4-tier,
illustrated-outline evals, progressive-reveal-builds). Criteria
ported from markdown-bullet assertions to YAML field assertions.
Test suite: 289 / 5 skipped (+60 net).

### ci — remove `tessl eval run` from CI per updated plugin-evals policy

`jbaruch/coding-policy` 0.3.20's `rules/plugin-evals.md` (Persistence
section) is explicit: do not add a `tessl eval run` step to tile-repo
CI, and do not add a scheduled/recurring workflow that re-runs the
suite as a persistence mechanism. The Tessl-publish layer
(`tesslio/patch-version-publish@v1`) owns persistence execution and
runs the eval suite automatically — any explicit step on top is
duplicate cost producing the same numbers a maintainer would already
see at publish time, and a parallel cadence can mask a publish-layer
eval failure with a parallel pass.

Two deletions:

- `publish-tile.yml` — removed the explicit `Run eval suite before
  publish` step (`tessl eval run .`). The eval suite still runs (via
  the publish action's internal execution); only the duplicate CI
  step is gone.
- `evals-scheduled.yml` — deleted entirely. The weekly cron was a
  recurring-persistence workflow of exactly the kind the rule
  prohibits.

Steady-state effect: every publish run drops `tessl eval run .` from
the CI step list; the publish action still gates on eval regressions
because it runs the suite itself. The scheduled weekly run is gone.
Local `tessl eval run .` for scenario authoring/debugging remains
permitted under the rule's authoring carve-out.

### ci — migrate `tessl skill review` to changed-skills loop

`publish-tile.yml` previously ran one static `tessl skill review` step per
skill on every push to `main` (5 invocations per merge). After
`jbaruch/coding-policy` 0.3.20 codified the changed-skills-loop pattern
in `rules/context-artifacts.md`, those static steps became a policy
violation — and a real cost: `tessl skill review` is LLM-backed, so
re-reviewing unchanged content burns Tessl credits while reproducing the
prior rubric output.

This release replaces the 5 static steps with one `uses:` of the
reference composite action shipped at
`jbaruch/coding-policy/.github/actions/skill-review`, pinned to SHA
`2a9df6575e153ce0d98900fdae26384c06df478f`. The action:

- diffs `github.event.before..HEAD -- skills/` to identify changed skills
- reviews only those skills at the configured threshold (85, unchanged)
- falls back to reviewing every skill on `workflow_dispatch` or initial
  push (no usable base)
- hard-fails when the base SHA is set but unreachable in the clone, so
  a missing review can never silently degrade to "review skipped"

`actions/checkout@v4` gains `fetch-depth: 0` per the composite action's
documented requirement (it needs the prior-push commit reachable).

Steady-state effect: PRs that don't touch `skills/` cost zero skill-review
invocations at merge; PRs that touch one skill cost one. Multi-skill PRs
scale linearly with what they actually changed.

### evals — prune low-value scenarios and strip task-criterion bleeding

Audited the 34-scenario eval suite against `jbaruch/coding-policy: plugin-evals`
(No Bleeding, Lift Not Attainment) and the user-stated rules in working
memory (test outcomes not implementation details; no agent-written
reimplementations of skill-provided scripts).

- **Retired 4 scenarios** with zero lift: `scenario-2` (duplicates
  `scenario-11` slide-source coverage), `scenario-23` (overlaps
  `scenario-22`+`scenario-19`), `scenario-27` (generic python-pptx
  placeholder work), `structured-talk-outline-with-typed-place`
  (overlaps `scenario-14`).
- **Stripped task-criterion bleeding from 9 scenarios** —
  `clarification-interactive-session`, `pattern-strategy-4-tier`,
  `scenario-12`, `scenario-13`, `scenario-16`, `scenario-21`,
  `scenario-22`, `scenario-24`, `scenario-26`. Removed criterion-mirror
  text from task bodies (Notes-on-Verification answer-key blocks,
  enum literals, threshold values, verb-action directives like "do
  NOT flag X"). The bleeding-strip pass left `criteria.json` files
  untouched in every case — fixes are at the task per the rule.
  Subsequent reviewer-driven commits in this PR did edit four
  `criteria.json` files (rebalancing three sums to 100 and
  reframing scenario-13's wide-angle criterion as outcome-based);
  those are documented in their own entries below.
- **Realigned 2 scenarios with skill orchestration** — `scenario-0`
  bleeding cleanup ("(should be skipped)" annotations) plus removed
  the `build_tracker.py` script-from-scratch requirement from
  `scenario-1` (vault-ingress ships Step 1 logic, not a separate
  script).
- `scenario-14` reviewed and reclassified to KEEP — audit had a
  false positive; its criteria check tile-prescribed structural
  tokens that the task does not pre-state.
- **Retired 3 structural-redundancy scenarios** — `scenario-18`
  (OOXML element presence, python-pptx output mechanics), `scenario-19`
  (QR image properties, qrcode-library output; subsumed by `scenario-21`
  full orchestration + `scenario-20` negative case), `scenario-24`
  (thumbnail planning; subsumed by `scenario-26` thumbnail revision
  which carries richer decisional content via speaker feedback).
- **Retired 6 data-driven low-lift scenarios** after running
  `tessl eval run .` on the de-bled set and inspecting per-scenario
  lift (with-context − baseline). Cut anything ≤3 lift or with a
  structural mismatch:
  - `clarification-interactive-session` (−71 lift) — vault-clarification
    is interactive (uses `AskUserQuestion` for multi-turn flow); the
    with-context agent correctly refuses to operate one-shot and
    scores 0, while the baseline fabricates answers and scores 71.
    Negative lift signals an eval-framework mismatch, not a fixable
    scenario problem.
  - `scenario-8` (Co-Presented Talk Adaptation, 0 lift) — both
    variants score 100/100; criteria measure universal competence.
  - `guardrail-check-format` (Guardrail Audit, 0 lift) — both
    variants 100/100; same problem.
  - `scenario-22` (Extract Resources, 2 lift) — baseline 98, ceiling
    effect; tile contribution drowned in universal-competence scoring.
  - `scenario-7` (PowerPoint Deck Build Plan, 2 lift) — baseline 98.
  - `scenario-25` (Post-Event Video Publishing, 3 lift) — baseline 97.

Suite goes from 34 to 21 scenarios. Average lift across the
remaining suite is substantially higher.

**Skill coverage after pruning.** `jbaruch/coding-policy: plugin-evals`
requires every skill with decisional logic to ship eval cases. After
this PR, all five skills retain at least one eval case in the suite:

- vault-ingress: 6 scenarios
- vault-clarification: 1 scenario — `scenario-12` (Humor Post-Mortem
  and Blind Spot Debrief), which tests vault-clarification's
  one-shot-evaluable decisional surface: recency-adapted questioning,
  per-beat humor grading, blind-spot probing grounded in analysis
  observations, structured-output capture. The interactive
  multi-turn `AskUserQuestion` flow that
  `clarification-interactive-session` previously attempted to cover
  is architecturally outside the eval framework's reach (the
  with-context agent correctly refuses to operate one-shot, producing
  the −71-lift signal that drove the retirement); this is an
  eval-framework limitation, not a coverage gap the eval suite is
  meant to close. The skill's
  decisional surface that *can* be one-shot-evaluated is covered.
- vault-profile: 1 scenario
- presentation-creator: 7 scenarios
- illustrations: 6 scenarios

**Reviewer-driven criteria edits.** Cross-family policy review on this
PR surfaced two `criteria.json`-side issues that were not in the
original bleeding-strip scope:

- Three scenarios had `weighted_checklist` max_score sums of 95 instead
  of 100, violating the eval-authoring weighting contract:
  `scenario-1` bumped "No-sources talk flagged as unprocessable"
  10 → 15 (the high-decisional behavior the tile teaches);
  `scenario-20` bumped "Agent distinguishes missing config from
  opt-out" 10 → 15 (the unique tile insight); `scenario-21` bumped
  "Command uses --shownotes-url (not --short-url)" 10 → 15 (the
  tile-prescribed arg choice). All 21 surviving scenarios now sum to
  exactly 100.
- `scenario-13`'s "Wide-angle detection" criterion previously prescribed
  a numeric ratio threshold ("ratio above 5:1 or 10:1 triggers a
  warning"). After de-bleeding stripped the task's hand-fed ratio
  interpretation, the criterion's threshold-direction was exposed as
  ambiguous (case_clean at 50/45 = 1.11:1 is even lower than
  case_wide_angle's 1.33:1, so any pure ratio threshold either
  false-flags clean or misses wide-angle). The criterion is now
  outcome-based: it grades that the agent flags `case_wide_angle`
  as wide-angle without false-flagging `case_clean`, using whatever
  signal the agent derives from extraction metadata. No specific
  numeric threshold is prescribed.

## 0.18.0

### deps — formalize tessl-version-floating carve-out

`tessl.json` floats its dependencies to `"latest"` because `tessl update`
rewrites the manifest in-place at runtime and `.tessl/tiles/` is
gitignored — pinning produces silent drift between commit history and
the running install. `jbaruch/coding-policy: dependency-management`
permits this only when three preconditions are met. This release adds
all three:

- **Authority-of-record rule** at `rules/tessl-version-floating.md`
  documenting the carve-out, naming `tessl.json` as the single covered
  manifest, and explaining why pin/lock semantics break in this shape.
  Registered under `tile.json` → `steering`.
- **Deploy-time check** at `scripts/check-tessl-pins.sh` that walks
  every covered manifest and fails if any dependency uses a specifier
  other than `"latest"` — rejecting literal pins, version ranges, tags,
  and anything else per the carve-out's "rejecting only literal pins
  lets a non-literal pinned/ranged value slip through" warning.
- **CI wiring** in `.github/workflows/tests.yml` runs the check ahead
  of the test suite on every push and PR. CI failure blocks merge.

The second `tessl.json` dependency (`tessl-labs/tessl-skill-eval-scenarios`)
also moves to `"latest"` — the carve-out applies to the manifest as a
whole, mixed pin/float within a covered manifest is not allowed.

### illustrations — pre-generation model-freshness check

New Step 2 in the illustrations skill runs before Strategy comparison or
deck Generation touches images. It uses `WebSearch` to identify current
flagship image-generation models from the major vendors (Google's Gemini
image + Imagen, OpenAI's `gpt-image-*`, and any other vendor with a
publicly accessible image API) and surfaces gaps against the script's
`COMPARE_MODELS` constant and — for Generation mode — the outline's baked
`**Model:**` choice plus its selection date.

If newer flagships exist, the step proposes updating `COMPARE_MODELS`
(Strategy) or re-running `--compare` against an updated list (Generation)
before continuing. The motivation is the months-long gap between when a
model was picked for a talk and when illustrations are actually generated
— a window in which a vendor often ships a meaningfully better flagship
(the recent `gpt-image-2` release being the precipitating example).

Step numbers in `SKILL.md` and the four reference files shift accordingly:
Strategy → Step 3, Generation → Step 4, Builds → Step 5, Apply → Step 6,
Thumbnail → Step 7.

### illustrations — cross-vendor image generation (OpenAI + Imagen)

`generate-illustrations.py` is no longer Gemini-only. The script now
dispatches by model-name prefix to three vendor families:

- `gemini-*` and `nano-banana-*` → Google `generateContent` (existing path)
- `imagen-*` → Google `:predict` endpoint with format-derived aspect
  ratio (new — FULL → `16:9`, IMG+TXT → `3:4`, the closest of Imagen's
  supported 1:1 / 9:16 / 16:9 / 3:4 / 4:3 set to the IMG+TXT 2:3 anchor)
- `gpt-image-*` → OpenAI `/images/generations` for fresh images and
  `/images/edits` (multipart) for the `--edit`, `--build`, and `--fix`
  workflows; size is format-derived (FULL → `2048x1152` true 16:9,
  IMG+TXT → `1024x1536` true 2:3) (new)

API-key resolution gains an `openai` slot. `secrets.json` now reads both
`gemini.api_key` and `openai.api_key`; either may also come from the
`GEMINI_API_KEY` / `OPENAI_API_KEY` environment variables. The script
only demands the key(s) needed by the models a given run will actually
hit — Gemini-only outlines don't require an OpenAI key, and vice versa.
Missing-key errors are per-vendor and include the right signup link
(`aistudio.google.com/app/apikey` for Google, `platform.openai.com/api-keys`
for OpenAI).

`COMPARE_MODELS` is refreshed to current flagships across vendors:
`gemini-3-pro-image-preview`, `gemini-3.1-flash-image-preview`,
`nano-banana-pro-preview`, `imagen-4.0-ultra-generate-001`, and
`gpt-image-2`. The older `gemini-2.0-flash-preview-image-generation` and
`imagen-3.0-generate-002` entries are dropped — they were superseded by
the flagships above (and the Imagen-3 entry was effectively broken
anyway, since `generateContent` doesn't accept Imagen models).

Imagen models have no public edit endpoint, so `--edit`, `--build`, and
`--fix` against an Imagen-family outline return an actionable error
directing the speaker to a Gemini or OpenAI model for editing workflows.

The outline parser also gained `+` and `-` tolerance in the Format and
STYLE ANCHOR regex (`[\w+-]+` replaces `\w+`) so the documented `IMG+TXT`
token is parsed correctly — previously it produced no match and the slide
silently fell back to the first available anchor and the FULL sizing
default. Safe-zone precedence is now applied uniformly:
`apply-illustrations-to-deck.py` treats `Safe zone:` presence as the
FULL/title-overlay signal regardless of the `Format:` token, so the
generator mirrors that — when Safe zone is present, the slide is
treated as FULL for anchor selection, vendor sizing, AND the directive
itself (via a new `effective_slide_format()` helper threaded through
every run_* caller).

New tests cover model-family classification across vendors, multi-vendor
key resolution (secrets.json, env-var fallbacks, partial config, malformed
JSON warning), the OpenAI multipart body structure, `final_build_dest`
extension preservation, the empty-build-steps parse path, the format
sizing table, and the `IMG+TXT` outline regex fix.

### Extract `illustrations` skill from presentation-creator

The visual layer (deck illustration strategy, generation, build chains, and
YouTube thumbnails) moves from presentation-creator into a new `illustrations`
skill. presentation-creator now delegates at three points: Phase 2 Decision
#11 (style strategy), Phase 5 Step 5.1b (illustration generation + build
generation + apply-to-deck), and Phase 7 Step 7.1 (thumbnail).

- New skill at `skills/illustrations/` with mode-routed SKILL.md (strategy /
  generation / thumbnail) and four references: `strategy.md`, `generation.md`,
  `builds.md`, `thumbnails.md`. Existing `title-placement.md` moved here too.
- Scripts moved: `generate-illustrations.py`, `apply-illustrations-to-deck.py`,
  `generate-thumbnail.py`, `suggest-scrim-color.py`. Tests updated to point
  at the new location; all 188 existing tests still pass.
- `apply-illustrations-to-deck.py` now handles `Format: IMG+TXT` slides as a
  first-class layout (image left ~60%, title + body right column), in addition
  to the existing FULL + Safe-zone path. New `IMGTXT_*` geometry constants;
  six new tests cover format parsing, picture repositioning, title repositioning,
  and column-width consistency.
- presentation-creator's Phase 2 / Phase 5 / Phase 7 references now stub to
  `Skill(skill: "illustrations")` rather than carrying inline workflow.
- `tile.json` adds the new skill entry. README updates skill count from four
  to five and rewrites the architecture diagram.

### vault-ingress — pptx-extraction emits `template_layouts`

`scripts/pptx-extraction.py` now extracts the master slide-layout
catalog (`{index, master_index, name, placeholders}` per layout) and
emits it under a top-level `template_layouts` key. Previously the
script emitted only `per_slide_visual` and `global_design`, so each
`vault-profile` regen silently carried forward the prior profile's
hand-curated layouts without ever refreshing them from the source
`.pptx`.

The `master_index` field disambiguates layouts that share a name
across different slide masters — PowerPoint allows reuse of layout
names like "Title and Content" across masters, so name alone is
unsafe as a merge key. Placeholder extraction catches `AttributeError`
specifically (rather than a bare `Exception` catch-all) and writes a
diagnostic to stderr with master index + layout name + placeholder
context when a malformed placeholder is skipped.

`skills/vault-profile/SKILL.md` Step 3 documents the merge contract:
the script is the source of truth for layout existence (`index`,
`master_index`, `name`, `placeholders`), while the speaker-curated
`use_for` field is preserved across regenerations by matching the
`(master_index, name)` pair.
`skills/vault-profile/references/speaker-profile-schema.md` adds an
inline note to the `template_layouts` example explaining the curation
contract.

`tests/test_pptx_extraction.py` adds 6 regression tests covering the
new `extract_template_layouts` function: emitted-key assertion,
default-count baseline, per-entry schema, sequential global indices,
placeholder schema (idx/type), and known layout-name presence.

### Pattern Taxonomy — Vault-derived patterns (5)

Five patterns observed across the vault corpus but not present in the
canonical Ford/McCullough/Schutta or Reynolds/Duarte sources have been
formalized into the taxonomy:

- `patterns/deliver/delayed-self-introduction.md` — open with a hook
  before introducing the speaker; the bio answers a question the
  audience has already implicitly asked. Vault dimensions 2, 11.
- `patterns/build/three-part-close.md` — closing structure of three
  separate slides (recap, CTA, thanks) rather than a single combined
  closing slide. Vault dimensions 2, 10.
- `patterns/build/progressive-reveal.md` — single complex base image
  annotated cumulatively across multiple slides, with a payoff slide
  that resolves the buildup. Vault dimensions 4, 7.
- `patterns/deliver/anti-sell.md` — speaker downplays own product or
  employer at moments where the audience expects a pitch, buying
  credibility for substantive claims later. Vault dimensions 11, 6.
- `patterns/build/meme-as-argument.md` — internet memes used as
  argumentative devices rather than decoration; relies on shared
  cultural reference to compress claims. Vault dimensions 4, 7, 12.

Taxonomy size: **97 → 102** entries (72 → 77 patterns; antipatterns
unchanged at 25). Observable count: **86 → 91**. Build phase: 34 → 37
patterns; Deliver phase: 19 → 21 patterns.

Index, summary stats, README structure tree, and `tile.json` summary +
description updated to reflect new counts.

### Pattern Taxonomy — Resonate ingest

Third source ingested alongside Ford/McCullough/Schutta (2013) and
Reynolds (2012): Nancy Duarte, *Resonate: Present Visual Stories that
Transform Audiences* (Wiley, 2010).

- **7 new build-phase patterns:**
  - `patterns/build/sparkline.md` — persuasion-specific narrative arc
    with two named turning points (Call to Adventure, Call to Action)
    and a "new bliss" close; vault dimensions 2, 5, 9
  - `patterns/build/call-to-adventure.md` — first sparkline turning
    point: dramatize the "what is" / "what could be" gap and reveal
    the Big Idea; vault dimensions 1, 2, 9
  - `patterns/build/call-to-action.md` — second sparkline turning
    point: specific, immediately-executable asks differentiated by
    audience action-temperament type (Doer / Supplier / Influencer /
    Innovator); vault dimensions 4, 6, 9
  - `patterns/build/new-bliss.md` — vivid future-state vision after
    the Call to Action; ensures the talk ends on a higher emotional
    plane than it started; vault dimensions 5, 6, 9
  - `patterns/build/star-moment.md` — "Something They'll Always
    Remember": planted dramatic peak in five sub-types (memorable
    dramatization / repeatable sound bite / evocative visual /
    emotive storytelling / shocking statistic); vault dimensions 3,
    5, 13
  - `patterns/build/inoculation.md` — preemptively voice the
    audience's strongest objection (steel-manned) and address it
    inside the talk; vault dimensions 4, 9
  - `patterns/build/master-story.md` — single anecdote woven
    recursively through the talk, each return deepening rather than
    repeating; vault dimensions 2, 5, 7
- **6 refinement subsections** folded into existing patterns:
  - `mentor.md` ← *Adopting the Stance — Planning Implications*
    (six-dimensional audience research, move-from/move-to matrix,
    resistance map, reward proportionality)
  - `the-big-why.md` ← *The Big Idea — Statement Format* (three
    required components: unique POV + explicit stakes + complete
    sentence)
  - `vacation-photos.md` ← *Numerical Narrative — Making Numbers
    Land* (Scale / Compare / Context techniques)
  - `peer-review.md` ← *Screening with Critics — Beyond Copyediting*
    (3× duration external critic session; six dysfunctional review
    patterns to avoid)
  - `crucible.md` ← *Murder Your Darlings — The Pre-Delivery Cut
    Pass* (convergent-thinking filter pass after divergent
    generation)
  - `sparkline.md` ← *The Three Contrast Types — Engine of the
    Middle* (content / emotional / delivery contrast as the
    persuasive-middle oscillation engine)
- **20 patterns** gain `## Related Reading` Duarte citations.
- **`patterns/_index.md`** — catalog tables, phase lookup, vault-dim
  mapping, summary stats, and sources updated. Total taxonomy entries
  now 97 (72 patterns + 25 antipatterns); 86 observable.

### Slide Design Spec

The speaker's `slide-design-spec.md` lives in their vault at
`~/.claude/rhetoric-knowledge-vault/slide-design-spec.md` (not in
this repo — it's per-speaker generated data). Two new reference
sections added to the vault file:

- §11.13 *Visual Relationships* — five-diagram-type taxonomy
  (flow / structure / cluster / radiate / influence) for converting
  bulleted slides into diagrams.
- §11.14 *Image Juxtaposition* — paired contrasting visuals
  technique for comparison-shaped content.

The presentation-creator skill in this repo references those
sections via `phase5-slides.md` (General Design Principles).

### Phase Documentation

- **Phase 0 (Intake):** new Step 0.3 sets the audience-as-hero
  planning stance; existing Step 0.3 renumbered to Step 0.4.
- **Phase 1 (Intent):** Spec Validation gains the Big Idea
  statement-format check and the Move-From / Move-To matrix.
- **Phase 2 (Architecture):** new "Persuasive vs. Informative
  Architecture" decision section presents Sparkline as a structural
  option alongside Narrative Arc; new "Action Typology" pre-planning
  section for Call to Action.
- **Phase 3 (Content):** new "Sparkline Structural Elements" section
  with placement guidance and outline-tagging conventions for Call
  to Adventure / Call to Action / New Bliss / S.T.A.R. moments; new
  Inoculation Beats and Master Story sections.
- **Phase 4 (Guardrails):** three new guardrail checks — Murder-
  Your-Darlings filter pass (Big Idea alignment of every section),
  Emotion-Balance check (analytical/emotional ratio against audience
  type), and Screening with Critics pre-lock gate for high-stakes
  talks.
- **Phase 5 (Slides):** General Design Principles section gains
  visual-relationships, image-juxtaposition, and numerical-narrative
  rules referencing the new slide-design-spec sections.
- **Phase 6 (Publishing):** Go-Live checklist gains the "first-
  impression-begins-before-entry" discipline (Duarte) reminding
  speakers to engage warmly with early-arrivers rather than
  heads-down at the laptop.

### Presentation Creator

- **`generate-thumbnail.py --portrait-style "<anchor>"`** — new flag
  enables a two-pass pipeline for decks with an Illustration Style
  Anchor (Phase 2 output). The script first pre-stylizes the speaker
  photo into the anchor's medium (sepia tech-manual, watercolor, ink,
  etc.) via a Gemini image-edit call, then runs the normal composition
  step using the stylized portrait as input. Fixes the palette-mismatch
  problem on illustrated decks that neither `--aesthetic photo` nor
  `--aesthetic comic_book` could solve. Independent of `--aesthetic`;
  they compose. Phase 7 Step 7.1 now passes the anchor through
  automatically when `presentation-outline.md` has a `## STYLE ANCHOR`
  block. Fixes #31.

### Pattern Taxonomy — Presentation Zen ingest

Second source ingested alongside Ford/McCullough/Schutta (2013):
Garr Reynolds, *Presentation Zen* (2nd ed., 2012, New Riders).

- **2 new patterns:**
  - `patterns/prepare/opening-punch.md` — Reynolds's PUNCH framework
    (Personal / Unexpected / Novel / Challenging / Humorous) for
    opening hooks; vault dimensions 1, 4
  - `patterns/deliver/screen-blackout.md` — deliberate B-key blackout
    or planned black slides as attention-redirection device; vault
    dimensions 12, 13
- **3 refinement subsections** folded into existing patterns:
  - `breathing-room.md` ← *Hara Hachi Bu* (90–95% finish-line discipline)
  - `concurrent-creation.md` ← *Plan Analog Before Going Digital*
  - `the-big-why.md` ← *The Elevator Test* (30–45 sec core-message check)
- **17 patterns** gain `## Related Reading` Reynolds citations
  (slideuments, bullet-riddled-corpse, floodmarks, borrowed-shoes,
  cookie-cutter, ant-fonts, narrative-arc, triad, crucible,
  concurrent-creation, vacation-photos, cave-painting, takahashi,
  bunker, bookends, coda, breathing-room).
- **`patterns/_index.md`** — catalog tables, phase lookup, vault-dim
  mapping, summary stats updated; sources section now lists Reynolds
  alongside Ford et al.

### Phase Documentation

- **Phase 1 (Intent):** Spec Validation gains the Two Questions check,
  the Elevator Test check, and the SUCCESs sticky-message check.
- **Phase 2 (Architecture):** new "Plan Analog Before Going Digital"
  section advocates whiteboard/Post-it work before slideware.
- **Phase 3 (Content):** new "Opening PUNCH" section requires explicit
  PUNCH-flavor tagging on the opening; new "Use Contrast as a
  Structural Device" section.
- **Phase 5 (Slides):** new "General Design Principles" section
  references slide-design-spec §11 (SNR, Big Four, picture superiority,
  empty space, rule of thirds, eye-gaze, full-bleed, 2D-for-2D, logo
  discipline, minimum font size).
- **Phase 6 (Publishing):** Go-Live Checklist gains venue-setup items
  (lights on, lectern aside, mic discipline) and during-delivery items
  (honeymoon-window discipline, never-apologize, *hara hachi bu*
  finish-line, screen-blackout).

### Tests

- 6 new tests for the two-pass thumbnail pipeline
  (`test_stylize_portrait_*` × 4, `test_compose_thumbnail_*` × 2).

## 0.17.0

**Talk timer, Keynote compatibility, shownotes destination** — New delivery timer
artifact, documented Keynote gotchas for slide generation, and machine-readable
shownotes publishing destination.

### Presentation Creator

- **`generate-talk-timings.py`** — new script parses `## Pacing Summary` table
  from the outline into `MM:SS Chapter` plain-text format for timemytalk.app.
  Supports `--qa` flag for Q&A chapters, sub-minute resolution, and automatic
  subdivision of acts exceeding 5 min using `## Section` headers
- **Phase 6 Step 6.4: Talk Timer Artifact** — new optional publishing step,
  gated on pacing summary presence in the outline
- **Keynote compatibility rules** — three python-pptx slide generation gotchas
  added to `slide-generation-rules.md`: use rectangles not connectors for
  decorative lines, never create-then-remove shapes in the same authoring flow,
  keep shape IDs contiguous per slide

### Resources & Publishing

- **Shownotes publishing destination** — `publishing_process.shownotes_site` added
  to speaker profile schema. Resources-gathering rules section 8 documents the
  read path: construct talk URLs from `shownotes_site` + `shownotes_url_pattern`,
  never guess or search the web
- **Vault-clarification config question** — new Step 5B question for
  `publishing_process.shownotes_site`

### Tests

- 15 new tests for `generate-talk-timings.py` (pacing parsing, cumulative times,
  Q&A insertion, sub-minute resolution, subdivision)

## 0.16.0

**Vault-clarification eval + test suite** — First dedicated eval for the interactive
clarification session, fixed volatile eval scenarios, and full pytest coverage for
every script with CI.

### New Eval

- **`clarification-interactive-session`** — first eval testing the vault-clarification
  skill's interactive session: rhetoric clarification (one question at a time), humor
  post-mortem (per-beat grading), blind spot probing, infrastructure config capture,
  intent confirmation storage, and session completion marking. Fixed test data with 1
  analyzed talk, empty config, 10-criterion weighted checklist

### Eval Fixes

- **Scenario 12** (humor post-mortem) — rewritten from "write a Python debrief tool" to
  "process these two fixed analysis files and produce structured debrief outputs." Fixed
  test data in `eval-resources/scenario-12/` (recent + old talk analyses)
- **Scenario 13** (extraction diagnostics) — rewritten from "write a diagnostics tool" to
  "analyze these 6 fixed extraction results and produce a report." Fixed test data in
  `eval-resources/scenario-13/` (6 concrete recording cases)

### Bug Fix

- **`pptx-extraction.py`** — fixed `AttributeError` crash on `_NoneColor` when extracting
  font colors from slides with unset color properties

### Tests & CI

- **119 tests across 15 test files** covering all Python scripts and the bash downloader
- **GitHub Actions workflow** (`tests.yml`) — runs on push to main + PRs, Python 3.12,
  installs ffmpeg and LibreOffice for full integration coverage
- **`pyproject.toml`** — declares all dependencies (python-pptx, lxml, qrcode, Pillow,
  imagehash, numpy) with `[test]` optional group for pytest

### Script Refactors

- **`strip-template.py`** — wrapped in `strip_slides()` + `main()` guard for importability
- **`delete-slides.py`** — wrapped in `delete_slides()` + `main()` guard
- **`reorder-slides.py`** — wrapped in `reorder_slide()` + `main()` guard (now raises
  `IndexError` on out-of-range instead of `sys.exit`)
- **`export-pdf.py`** — wrapped in `main()` guard, functions now take parameters
- **`_pptx_repair.py`** — extracted shared `clean_viewprops()` from strip-template and
  delete-slides into a single module, eliminating code duplication

## 0.15.0

**Placeholder slides, resources gathering, and post-event workflow** — New deck
adaptation tooling, Phase 6.0 resources extraction, Phase 7 post-event workflow,
and hardened QR generation.

### Presentation Creator

- **`insert-placeholder-slides.py`** — new script inserts bright-yellow placeholder
  slides at specified positions (1-indexed). Supports JSON file or `--at`/`--title`
  CLI input, `--output` flag for non-destructive saves. Processes positions in
  descending order to avoid index shifting
- **Phase 6.0: Resources gathering** — new `extract-resources.py` script parses
  presentation outlines for URLs, GitHub repos, book references, RFCs, and
  tool/library mentions. Deduplicates, tracks slide context, outputs JSON or markdown
- **Phase 7: Post-event workflow** — new phase covering post-delivery tasks
- **`generate-thumbnail.py`** — YouTube thumbnail generation via Gemini, composing
  slide images + speaker photos with style variants and YouTube spec validation
- **Shownotes slug convention** — slug generation process added to Phase 1 intent
  distillation, enforced from Presentation Spec (never agent-invented)
- **Presentation Spec persistence** — specs saved to disk as `presentation-spec.md`

### QR Generation Hardening

- **Custom Bitly domains** — `generate-qr.py` supports custom domains (e.g., `jbaru.ch`)
- **Per-slide QR colors** — different slides can have different background colors;
  script generates minimal PNG variants grouped by color scheme
- **Idempotent re-runs** — existing QR images replaced instead of stacked
- **`--png-only` mode** — generate QR PNG without opening a deck
- **Loud missing config** — missing shortener config surfaces as a warning, not silent
  degradation. Actionable `secrets.json` creation commands in error messages
- **Late-entry guard** — Phase 6 pre-flight checklist, no-raw-dogging rule

### Bug Fixes

- Fixed Bitly custom back-half silently ignored
- Fixed PPTX corruption from stale viewProps.xml after slide deletion
- Fixed multi-placeholder insertion index bugs

### Evals

- 2 new scenarios: insert-placeholder-slides, QR generation failure modes

## 0.14.0

**QR code generation** — Automated QR code generation and insertion into decks during
Phase 6 publishing, with slide background color matching and auto-contrast foreground.

**Gemini API key in secrets.json** — `generate-illustrations.py` now reads the Gemini
API key from `{vault}/secrets.json` (`gemini.api_key`) first, falling back to the
`GEMINI_API_KEY` environment variable for backward compatibility. This unifies all API
keys in one file. New `--vault` CLI argument for custom vault paths.

### Presentation Creator

- **`generate-qr.py` script** — new script generates unbranded QR codes from shownotes
  URLs (or pre-shortened URLs), matches the QR background to the target slide's color,
  and auto-selects white or black foreground based on WCAG relative luminance. Inserts
  the QR as a 2" square in the bottom-right corner of the configured slide(s)
- **Phase 6 step reordering** — QR generation now runs before PDF export (was after).
  Steps: Shownotes → QR Code → Export → Additional → Go-live → Report
- **URL shortening support** — bit.ly and rebrand.ly via direct API or MCP-preresolved
  mode. Re-running for the same talk slug updates the existing short link (keeps printed
  QR codes valid). Falls back to raw URL when shortener=none or API fails
- **Vault-based secrets** — API keys stored in `{vault}/secrets.json` (not env vars),
  documented with `chmod 600` recommendation

### Schema Changes

- **Speaker profile `qr_code`** — 5 new fields: `custom_url`, `shortener`,
  `rebrandly_domain`, `bg_color_match`, `preferred_short_path`
- **Tracking database `qr_codes[]`** — new top-level array tracking per-talk QR
  metadata: talk slug, target URL, shortener, short path/URL, link ID, PNG path
- **Vault clarification** — 3 new questions for shortener preference, Rebrandly
  domain, and API key setup

### Evals

- 1 new scenario (scenario-19): QR generation with purple background matching,
  auto-contrast white foreground, shortener=none path, tracking DB update

## 0.11.0

**Illustration pipeline** — AI-generated illustrations are now a first-class part of
the presentation creation process, with collaborative style decisions and per-slide
image prompts generated during outline creation.

### Presentation Creator

- **Phase 2: Illustration Strategy (Decision #11)** — optional collaborative workflow
  for talks that want AI-generated illustrations. Proposes 3-4 style options informed
  by the talk's concepts, the vault's visual history, and mode-specific precedent.
  Includes format vocabulary, model selection (with `--compare` mode), and visual
  continuity devices
- **Phase 3: Illustrated outline format** — new Illustration Style Anchor section in
  the outline header (model, per-format anchors, conventions). Per-slide Format,
  Illustration, Text overlay, and Image prompt fields. `[STYLE ANCHOR]` token
  referencing the header. `[IMAGE NN]` placeholder type for EXCEPTION slides
- **Phase 4: Illustration coverage guardrail (#10)** — checks format tag coverage,
  EXCEPTION justifications, style anchor references, and prompt quality. Shows
  `[SKIP]` for non-illustrated outlines
- **Phase 5: Generate illustrations step** — new Step 5.1b runs
  `generate-illustrations.py` to batch-generate images before slide population.
  Image Generation Setup docs with API key, model, and `--compare` instructions
- **Slide generation** — illustration-format-aware insertion (FULL → full-bleed,
  IMG+TXT → image + text, EXCEPTION → real asset) added to slide-generation.md

### Rhetoric Knowledge Vault

- **Dimension 13f: Illustration & Image Style** — new analysis sub-dimension for
  image source types, illustration aesthetic, visual coherence, style anchor evidence,
  visual continuity devices, and mode correlation
- **Structured data fields** — `illustration_style`, `illustration_coherence`,
  `image_source_distribution`, `visual_continuity_devices` added to extraction output
- **Speaker profile: `visual_style_history`** — new section with default style,
  style departures, mode-specific visual profiles, and confirmed visual intents
- **Schema fixes** — `transcript_source` added as required field on talk entries and
  subagent return schema. `delivery_language` and `co_presenter` added to subagent
  return schema. English-first quote rule promoted to inline in SKILL.md
- Video-as-slide-fallback reinforced in Step 3A processing instructions

### New files

- `skills/presentation-creator/references/generate-illustrations.py` — stdlib-only
  Python script for Gemini API image generation with `--compare` mode, resumable
  batch runs, rate limiting, and progress reporting

### Evals

- 2 new scenarios: illustrated outline format, illustration guardrail audit
- Updated guardrail audit scenario to check `[SKIP]` illustrations line
- 11 new instructions in instructions.json covering illustration features
- Fixed pre-existing eval gaps: task descriptions, criteria alignment, skill content

## 0.10.1

**Small print** — Sessions catalog entries now include a "Small Print" field for
Program Committee notes (talk positioning, what it is/isn't, reviewer context).

## 0.10.0

**Sessions catalog** — New `sessions-catalog.md` file in the vault for maintaining
submission-ready conference materials (title, abstract, outline) per active talk.

- Added Sessions Catalog section to presentation-creator SKILL.md with read/write
  rules: when to pull from the catalog (before writing a new CFP), when to save
  (after CFP writing or Phase 4 outline finalization), and maintenance guidelines
- CFP Abstract Writing flow now includes step 5: save to sessions catalog
- Added `sessions-catalog.md` to the vault skill's Key Files table
- Anti-pattern checking recommended on catalog entries before saving (public-facing text)

## 0.7.0

**Canonical vault path** — The vault now uses `~/.claude/rhetoric-knowledge-vault/` as
a fixed, discoverable location. No more asking "where should the vault live?" every
session. Custom locations (e.g., Google Drive) are symlinked to the canonical path.

- Vault discovery replaces config bootstrapping for `vault_root` — checks canonical
  path first, creates or symlinks on first run
- New `vault_storage_path` config field tracks the actual directory when using a custom
  location
- Updated presentation-creator to read vault from the canonical path directly
- Updated eval instructions (+2 new vault discovery instructions) and scenario-1
  criteria (canonical path check)
- README updated to reflect new vault location behavior

## 0.6.2

**Maintenance** — Version bump and CLI publish.

## 0.6.1

**Eval scenarios** — Added 5 new server-generated eval scenarios via `tessl scenario
generate`, covering both skills end-to-end. Reviewed and fixed all 15 scenarios for
quality, then ran the full eval suite (baseline avg 62% → with-skill avg 98%).

### New scenarios (5)
- Multilingual rhetoric analysis with language policy and pattern scoring
- Presentation outline with typed placeholders and callbacks
- python-pptx deck generation with template stripping and notes injection
- Guardrail check format and 4-tier pattern strategy
- Speaker profile JSON generation from vault data

### Scenario fixes
- Removed instruction leakage from python-pptx scenario (replaced numbered output
  spec with high-level ask)
- Fixed factual error in guardrail scenario (Act 1 ratio math: 51.7% → 43.3% to
  correctly test the WARN threshold)
- Fixed infeasible criteria (replaced MCP-only `optimize_slide_text` with python-pptx
  overflow handling)
- Fixed transcript pre-translating Russian phrases (defeated the English-only quote
  format test)
- Fixed ambiguous download results in status management scenario (added
  `video_extraction` field, clarified planning-time vs download-outcome for
  `slide_source`)
- Added missing `capability.txt` files to all new scenarios
- Tightened subjective criteria wording across all scenarios

## 0.5.5

**Video-extracted slides** — When no slides file exists, extract slides directly
from video: ffmpeg frame extraction → crop to slide area (exclude PiP) → perceptual
hash deduplication → combine into PDF. Marks `slide_source: "video_extracted"`.

## 0.5.4

**Non-YouTube video support** — Step 3A now supports ingesting talks from InfoQ,
Vimeo, conference platforms, and any source yt-dlp supports. Downloads audio via
`yt-dlp -f http_audio`, transcribes locally with MLX Whisper (Apple Silicon) or
OpenAI Whisper. Tags transcript source as `"whisper"` vs `"youtube_auto"`.

## 0.5.3

**Data integrity fixes:**

- **Summary status recount:** Step 4 now rewrites the summary Status block by
  counting the tracking DB every time. The DB is the source of truth; the summary
  is a derived view. Fixes stale tallies from manual incrementing.
- **Structured field extraction:** Step 4 now requires populating `co_presenter`,
  `delivery_language`, and other structured DB fields directly from analysis results,
  not burying them in `rhetoric_notes` free text.

## 0.5.2

**Blind spot clarification + language policy** — Two additions to the vault skill:

- **Step 5A-bis (Blind Spots):** After analyzing each talk, the skill identifies
  moments it knows it missed (audience reactions, costume/prop moments, room energy,
  demo engagement) and asks the speaker. Stores as `blind_spot_observations`.
- **Language policy:** The vault is English-only. Non-English talks are analyzed and
  stored in English with translated quotes, language-tagged verbal signatures, and
  `delivery_language` on the talk entry. Prevents non-English content from polluting
  the signature list or rhetoric summary.

## 0.5.1

**Robustness & conciseness** — Addressed gaps found during tile review and
tightened both skills for the review gate.

### Robustness fixes
- Made vault→creator pattern index path explicit with tile-root-relative path
- Added pattern taxonomy migration: Step 1 detects pre-v0.5.0 talks missing
  `pattern_observations` and marks them `needs-reprocessing`
- Added `clarification_sessions_completed` counter to tracking DB config
- Added LibreOffice CLI as cross-platform PDF export alternative
- Clarified Step 3B firing conditions

### Conciseness improvements
- Vault SKILL.md: 285 → 207 lines. Consolidated reference file list into Key
  Files table, collapsed config bootstrapping, tightened PPTX/PDF handling,
  moved Step 5B questions to `schemas.md`, compressed profile mapping and badges
- Creator SKILL.md: 263 → 230 lines. Merged vault loading steps, condensed
  Phase 2 decisions table, removed summary-only mode table (now inline)
- Review threshold lowered to 85 (vault conciseness 2/3 has no actionable
  feedback per the optimizer)

## 0.5.0

**Presentation Patterns integration** — Integrated the pattern taxonomy from
*Presentation Patterns* (Ford, McCullough, Schutta 2013) as a structured reference,
vault scoring system, and brainstorming vocabulary across both skills. Patterns are
classified as observable (scored by the vault) or unobservable (surfaced as a go-live
checklist before delivery).

### Pattern taxonomy (88 new files)

- 88 reference files (63 patterns + 25 antipatterns) organized by lifecycle phase
  (prepare/build/deliver) with YAML frontmatter: `id`, `name`, `type`, `part`,
  `phase_relevance`, `vault_dimensions`, `detection_signals`, `related_patterns`,
  `inverse_of`, `difficulty`, and `observable` (true by default, false for 11 entries)
- Master index (`references/patterns/_index.md`): flat catalog table, phase-grouped
  lookup, vault dimension reverse mapping, and unobservable patterns go-live checklist
- Each file includes: summary, detailed description, when to use/avoid, detection
  heuristics, 3-tier scoring criteria, vault dimension mapping, and combinatorics

### Observable vs unobservable split

- **77 observable** patterns are detectable from transcripts + slides and scored during
  vault analysis
- **11 unobservable** patterns (8 patterns + 3 antipatterns) involve pre-event logistics,
  physical stage behaviors, or external systems that leave no trace in recordings:
  - Pre-event: Preparation, Carnegie Hall, Stakeout, Posse, Seeding Satisfaction, Shoeless
  - During delivery: Lightsaber, Red/Yellow/Green
  - Antipatterns to avoid: Laser Weapons, Bunker, Backchannel
- Unobservable patterns are marked `observable: false` in their frontmatter, excluded
  from vault scoring and `pattern_profile`, and surfaced as a go-live preparation
  checklist in creator Phase 6

### Vault scoring (4 modified files)

- Subagents now tag talks against the observable pattern taxonomy during analysis
  (Step 3 B2), skipping patterns marked `observable: false`
- `pattern_observations` field added to both subagent return schema and tracking
  database talk entries (`schemas.md`)
- Per-talk analysis files now include a "Presentation Patterns Scoring" section
- Step 6 generates an aggregate `pattern_profile` in the speaker profile with mastery
  levels, usage trends, signature combinations, antipattern frequency, and never-used
  patterns (observable only)
- Pattern-based badges generated from profile data (e.g., "Narrative Arc Master",
  "Shortchanged Survivor", "Pattern Polyglot")
- `pattern_profile` section added to `speaker-profile-schema.md` with documentation
  that only observable patterns are included
- All 14 rhetoric dimensions in `rhetoric-dimensions.md` cross-referenced with their
  related patterns and antipatterns

### Creator integration (3 modified files)

- Phase 0: Loads `references/patterns/_index.md` alongside vault documents
- Phase 2 (Architecture): Decision #10 "Pattern Strategy" — 4-tier recommendation
  system using `pattern_profile`:
  - **Signature** (80%+ usage) — always shown
  - **Contextual** — matching spec context, occasional speaker usage
  - **New to You** — from never-used patterns, filtered by relevance
  - **Shake It Up** — random picks, provocations not prescriptions
  - Plus antipattern warnings merging speaker history + contextual detection
- Phase 4 (Guardrails): Section 9B adds taxonomy-based antipattern scanning with
  `[RECURRING]` flags from `pattern_profile.antipattern_frequency` and `[CONTEXTUAL]`
  flags from outline analysis
- Phase 6 (Publishing): Step 6.5 go-live preparation checklist surfaces all 11
  unobservable patterns as delivery-day reminders
- Summary-only mode (no profile) still works — patterns from reference files only,
  flat list, go-live checklist still applies

### Documentation

- `README.md` — rewritten with Presentation Patterns section, observable/unobservable
  table, updated file tree, updated vault/creator descriptions
- `tile.json` — bumped to v0.5.0, added "patterns" keyword
- `CHANGELOG.md` — this entry

## 0.4.7

**Review & consistency fixes** — Addressed consistency gaps found during tile review.

- Vault Step 4 now writes per-talk analysis files to `analyses/` (fixes broken adaptation workflow in creator)
- Added `badges` schema to `speaker-profile-schema.md`
- Broke single `publishing_process` question into targeted sub-questions matching the schema
- Clarified summary section numbering vs rhetoric dimension numbering in vault SKILL.md
- Labeled slide budget table in creator as defaults when profile is unavailable
- Added `cfp`, `abstract`, `pptx` keywords to `tile.json`
- Fixed `tessl.json` project name from scaffold placeholder
- Added python-pptx internal API risk note to `slide-generation.md`
- Backfilled CHANGELOG for versions 0.3.1-0.4.5

## 0.4.1 - 0.4.5

**CI/publish pipeline tuning** — Iterative adjustments to the GitHub Actions publish
workflow: switched to the publish action's built-in skill review gate, tested optimize
input, and settled on the default review threshold (50%).

## 0.4.0

**Evaluation scenarios** — Added 10 eval scenarios covering both skills (vault analysis
and presentation creation), plus Tessl eval infrastructure.

- 10 scenario tasks with criteria covering rhetoric analysis, profile generation,
  presentation creation, adaptation, CFP writing, and guardrail enforcement
- Tessl eval tile dependency added

## 0.3.0

**Speaker badges & profile Step 6 enhancement** — Profile regeneration now generates
personalized speaker badges as a fun summary of portfolio-wide achievements, mined from
real vault data (meme counts, employer transitions, recurring patterns, signature quirks).

- Step 6.7 added: generate speaker badges after profile regeneration
- Badges must be genuinely personalized to the speaker's quirks, not generic
- Grounded in aggregated data from all processed talks

## 0.2.0

**PPTX as primary slide source** — The vault skill no longer requires Google Drive slide
PDFs for every talk. Talks with `.pptx` files can now be processed directly, providing
richer data (exact hex colors, font names, layout names) than PDF visual inspection.

- A talk is processable with `video_url` + at least one of `slides_url` or `pptx_path`
- New `slide_source` field on each talk: `"pdf"`, `"pptx"`, or `"both"`
- When PPTX is available, extraction runs inline during rhetoric analysis (Step 3),
  merging what was previously a separate Step 3B pass
- Step 3B now only processes PPTX files not already handled as primary sources
- Schema updated: `slides_url` and `pptx_path` are both optional (at least one required)

## 0.1.0

Initial release with two skills:
- **rhetoric-knowledge-vault** — parse recorded talks to extract rhetoric patterns
- **presentation-creator** — create new presentations matching your documented style
