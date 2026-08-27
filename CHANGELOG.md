# Changelog

### fix(vault-ingress) — a failed video download is now visible, and uses the pinned yt-dlp

`batch-download-videos.sh` discarded yt-dlp's stderr and never checked its exit
code, so a failed download produced no line at all rather than a failure line
(#370). It also invoked `yt-dlp` by bare name, resolving whatever `PATH`
offered (#371) — on the host that surfaced this, a Homebrew 2026.06.09 that 403s
on every video, while the pinned 2026.08.19 in the venv succeeds on the same
command in the same minute. Together the two turned 34 of 35 failed downloads
into silence, and the talks behind them read downstream as thin rather than
unprocessed.

It is now `batch-download-videos.py`. The bash version was the directory's lone
shell script among fifty Python ones, and `rules/script-delegation.md` requires
a script to produce structured data — which meant hand-rolling JSON escaping in
bash for strings that arrive as arbitrary yt-dlp error text. Python removes that
along with the `set -e` carve-out gymnastics and two portability traps a
reviewer found in the shell draft: an unset `VIRTUAL_ENV` expanding to
`/bin/yt-dlp`, and an unchecked `mktemp -d`.

The script resolves `yt-dlp` in an explicit order — `$YT_DLP`, then the console
script beside the running interpreter (#371's own proposal), then
`$VIRTUAL_ENV`, then the toolkit's `.venv`, then `PATH` — and announces the
resolved path and version on stderr before the first download, so a stale binary
is visible up front rather than after the batch. A binary that cannot answer
`--version` is a resolution failure, not an unnamed version.

Stdout is one JSON report: a `results` entry per requested id in the order
given, each `ok`, `skip`, or `fail` with its bytes or its exit code, yt-dlp
reason, and log path. The file on disk is the verdict rather than the exit code,
since yt-dlp can exit zero having produced nothing after a failed merge. Ids
already downloaded are skipped, so a 78-video batch resumes instead of
restarting, and every id is checked against the shared ingress YouTube grammar
before becoming a directory name or a URL. Exit 0 when every id ended `ok` or
`skip`, 1 when any failed, 2 on a usage or resolution error.

`references/video-slide-extraction.md` taught the bare `yt-dlp` invocation in
three places, which is where the habit came from; all three now point at the
script, and the reference names the behavioral contract while leaving binary
resolution and concurrency to the script's own docstring.

#371's other two halves are unaddressed: the Python call sites in
`fetch-transcript.py` and `audit-source-identities.py` still resolve from
`PATH`, and `check-runtime.py` still reports the lane available on presence
alone rather than asserting the pinned version.

## 0.20.108 — 2026-08-27

### fix(vault-ingress) — the "fresh v6 claim" example declared version 5

The canonical return example in `references/subagent-instructions.md` is headed
"Minimal processed structure for a fresh v6 claim" and carried
`"return_schema_version": 5`. `return_validation.py` rejects that outright: a v6
claim "requires return schema version 6, got 5".

Every per-talk worker reads this file, and this is the block it copies. A worker
following it produced a rejected return, and the rejection surfaced as the
worker being wrong rather than the instruction being wrong — the expensive
direction to debug, since the fix looks like it belongs in the analysis.

A test held the error in place. `test_ingress_adherence_docs.py` asserted the
worker doc *contains* `"return_schema_version": 5`, so correcting the example
failed CI; the guard required the bug to stay. That assertion now parses the
fenced example and compares its version against the validator's own
`WEIGHTED_SCORE_RETURN_SCHEMA_VERSION`, so it tracks the code instead of a
string. The `schemas-db.md` assertion stays at 5, which that document's
compatibility table calls a still-valid return at the flat scoring generation.

The block also omitted `pattern_score_basis`, which a v6 return requires.
Documenting the object meant reproducing `DETECTION_WEIGHTS` in reference prose,
and no script-owned operation existed that a worker could call instead — so the
only paths were a mirrored constant or a worker deriving it from the validator's
source. `build-score-basis.py` closes that: the basis is a pure function of a
return's own detection lanes and not-evaluable ledger, and the script is a thin
entry point onto `return_validation.pattern_score_basis`, which keeps one owner
for both the weight table and the shape. The reference names the command instead
of the values.

The example no longer carries the basis at all. Printing it there would restate
computed values the script owns, and a static copy drifts; the block now stops
where a worker's own writing stops, and the reference names the command that
completes it.

It also claimed all five evidence sources to show each lane's syntax, which no
return may do without the audits behind them — so it could never have been
copied. It claims the one source it can back.

The builder emits completed returns rather than a fragment to paste. Inserting
the field is as deterministic as computing it, and leaving that merge to the
worker invites an incorrectly placed or wrongly associated basis. Its stdout is
the same returns with the field set, ready for `validate-returns.py`. It exits
`0` on success and `2` on unreadable, malformed, or duplicate-filename input,
with a diagnostic on stderr and nothing on stdout; the reference states that
contract and tells the worker to stop on nonzero. A malformed detection reaches
the owner function as a `TypeError` or `KeyError`, which is converted to the
documented exit rather than leaking a traceback into a caller that is parsing
stdout.

The builder rejects duplicate talk filenames rather than keying past them.
Building the result as a filename map would drop every return but the last, and
a caller merging that output would hand one talk another talk's basis — worse
than no output. `validate-returns.py` rejects duplicates across its inputs for
the same reason.

The guard follows the same line. Rather than re-deriving fields by hand or
comparing against a pasted copy, it runs the documented sequence: parse the
example, pass it through `build-score-basis.py` for the completed return, and
validate that through `validate-returns.py`. What is under test is the flow a worker is told
to follow, and it asserts the example does *not* contain the generated field.

Found while preparing the first hand-run batch of a 250-talk reparse, before
launching parallel workers against the same instructions.

### fix(vault-ingress) — stop a final-cue overhang discarding a talk's timing

A caption cue carries display time, not speech time, so the last one routinely
outlives the recording by a second or two. `TIMING_BOUND_TOLERANCE_SECONDS` was
1.0s, so those talks lost their timed segments — and with them
`timed_transcript` as a citable evidence source — over a rendering artifact.

Measured across a 12-talk sample of this vault's caption-sourced transcripts:

```
-10.88  -4.12  -0.78  0.00  +0.97          kept timing
+1.40  +1.52  +1.52  +1.68  +1.88  +2.24  +2.32   lost it
```

**Seven of twelve.** Not an edge case — the majority of talks that had timing at
all were losing it. Negative overhang is equally ordinary: captions often stop
before the video does. The bound is now 5.0s, above the observed maximum of
2.32s with room, and every loss in the sample sat between 1.4s and 2.32s.

Raising it costs nothing in detection, but only because the identity question
moved to where it can be answered. `FOREIGN_TIMING_EXTENT_RATIO` shipped the
release before and ran solely in the caption lane, so the receipt write and
load paths never asked it. On a **short** recording that gap is the whole
story: cues running to 14s on a 10s video overhang by 4s — inside the new
tolerance — while describing a recording 1.4x this one's length. Seconds cannot
see it; only the ratio can. The extent check now runs beside the tolerance in
`_validate_timing_semantics`, so both verdicts reach every path, and the more
specific one is reported first.

Captions only, for the same reason the caption lane already had that
restriction: Whisper transcribes the audio in hand and cannot be a foreign
track. Its imprecise timestamps are sloppy, not foreign, and rejecting them
would tell the operator to re-run the transcription that produced them.

The rejection also stated the wrong thing. `receipt write failed: timed
segments extend beyond the source-owned duration bound` reads as a write fault
plus a serious identity problem; the write had not failed and the bound was
exceeded by 1.6s. It now names the measured overhang, the tolerance it
crossed, and what to do about it — so an operator can tell a rounding artifact
from the genuine foreign-track case and knows which one they are looking at.

The caller compounded it, catching `OSError` and `ValueError` together and
labelling both a write failure. An `OSError` is one; a `ValueError` means the
timing was read and rejected. They are separate handlers now, so a validation
failure carries its own reason instead of a fault that never happened.

Found on the first batch of the 250-talk reparse, where
`2013-devcontlv-modules-hell` lost 18 minutes of timing to a 1.6s overhang.

## 0.20.106 — 2026-08-23

### feat(vault-ingress) — catch a caption track that belongs to a longer recording

Timed cues running far past the source-owned duration mean the track describes
a different recording. The signal was already computed on every fetch and then
thrown away: it dropped `timed_path`, wrote a prose reason, and let the text
through. `timing_extent_is_foreign` now measures the overrun as a ratio, and
the caption lane falls through to Whisper when it fires — so a rejected track
becomes a real transcript instead of nothing.

**It does not catch the track that motivated it, and that is worth recording.**
`Kl6tLcQ5hGI`'s contaminated captions overrun by 1.213x — under the threshold —
and were caught by the word-rate ceiling at 296 wpm instead. The assumption
behind this work, that a session-block track shows up as a long timeline, was
wrong: that track's cues barely overrun while its *text* is roughly double.
The contamination was dense, not long.

The two detectors cover different shapes, which is why this still ships:

| contamination | ceiling | extent |
|---|---|---|
| dense text, short cues (observed) | catches at 296 wpm | misses at 1.21x |
| long cues, dense text | catches — a 3000s block's words over a 318s divisor reads ~1400 wpm | catches |
| long cues, sparse text | misses — 800 words over 5.3 min reads a normal 151 wpm | catches at 11x |

The third row is the whole justification. The ceiling divides words by the
*video's* duration, so it can never learn that the track disagrees about how
long the recording is. That shape has not been seen in this vault.

The check runs on the caption lane only. Whisper cannot be foreign — it
transcribes the audio in hand — and its timestamps are merely sometimes sloppy;
this same talk produced `malformed or zero-duration segments` from that lane.
Applying the guard to the final fallback would discard a sound transcript over
bad timing and leave the talk with nothing.

Segments are materialized inside the caption lane, not at the call site. Two
readers consume them — the extent check and the timing bundle — so a one-shot
track would hand the second an exhausted iterator, disabling the guard and the
timing both. `segments_to_text` is a third reader and runs first, so the lane
was already returning a spent iterable to anyone who received a lazy track.
Consuming it inside the lane also keeps the consumption within the caller's
expected-error boundary: a track that raises mid-read is a caption-lane
failure that falls through to Whisper, where materializing at the call site
would have let the same exception reach the process boundary and end the run.

The threshold is loose on purpose — its verdict discards a transcript, and a
cue trailing an hour-long talk by three seconds reads 1.0008.

## 0.20.105 — 2026-08-23

### fix(vault-ingress) — declare yt-dlp, and stop one refusal ending the Whisper lane

The Whisper fallback was dead and blamed the wrong component. `yt-dlp` returned
`HTTP 403: Forbidden`, the script reported `whisper: unavailable`, and
mlx-whisper was installed and working the whole time. What failed was the
download.

**The root cause was staleness, not YouTube.** `yt-dlp` was never declared in
`pyproject.toml`. It resolved from `PATH` — a Homebrew binary at 2026.06.09,
two and a half months old — with no floor, no pin, and no renewal path.
Nothing broke when it rotted, which is the whole problem: a stale yt-dlp does
not fail the build, it quietly removes the ability to transcribe. Declaring
`yt-dlp==2026.8.19` puts it under the `pip` Dependabot ecosystem the repo
already runs weekly, so the renewal that was missing now happens on its own.
Verified: 2026.8.19 downloads on the default player client, where 2026.06.09
403s.

That makes the second change defense in depth rather than the fix. YouTube
blocks its player clients unevenly and a pin will always lag the adversary by
up to a renewal cycle, so a single refusal should not end the lane. Measured
against `Kl6tLcQ5hGI` on the stale version: default, `web_safari`, `ios` and
`tv` all 403, `mweb` served it. `fetch_whisper` now walks
`YOUTUBE_PLAYER_CLIENTS`, `None` first so a healthy environment runs yt-dlp's
own default chain and pays nothing, and on exhaustion names every client tried.

Each attempt downloads into its own directory. Sharing one output path let a
refused attempt leave a partial file behind, and the next attempt's
existence check would accept those bytes as its own success — the chain would
stop early and transcribe the failure's leftovers. A zero-byte artifact is
likewise a failed extraction wearing a filename, not a download.

This blocked recovery from the previous entry: a contaminated caption track now
fails closed, and Whisper is the intended fallback. Between the two, a talk with
bad captions had no path to a transcript at all.

The same change carries the local-audio half of the receipt-preservation guard,
which landed for YouTube only. In `_handle_local_audio` a failed
`probe_local_media_duration` still overwrote a valid `local_media_duration`
receipt with the fixed default, destroying the duration a later run needs for
either word-rate bound. That branch adds one condition the YouTube branch does
not need: a stored receipt is the stronger one only while its `media_sha256`
still names the bytes in hand. A receipt describing other media is stale, not
strong.

Found during the reparse of a 250-talk vault; #360 and #361.

### fix(vault-ingress) — bound the transcript word rate from above, and stop the bound erasing itself

The first talk of a full-vault reparse returned `ok: true`, exit 0, and a
transcript holding two speakers. `Kl6tLcQ5hGI` is a 5.3-minute DevOpsDays
segment; YouTube served it the whole session block's caption track. The text
opens as the right talk ("my name is Baruch Sadogursky") and closes inside
somebody else's ("how can we break Brooks' law?"). Rhetoric analysis reads
verbatim examples, hiccup words, pacing and closing type straight off that
text, so the wrong speaker's delivery would have been scored as this one's.

Three defects stacked to let it through, and each hid the next.

**The policy had a floor and no ceiling.** `min_words` is derived from
`duration_seconds`, and the receipt carried both numbers while only ever
comparing them upward. 1609 words over 318s is 304 wpm. Every genuine receipt
in the vault sits at 110-132 wpm, so the separation is not marginal.
`MAX_WORDS_PER_MINUTE` is deliberately loose at 240 — it exists to catch a
track belonging to a different recording, never to police a fast talker.

**The duration was modelled as a floor-relaxation input, so the bound could
only be reached from below.** `needs_duration_probe` fired when a transcript
looked too *short*; a long one never got a duration, and the new ceiling would
have been inert on exactly the path a reparse takes most — the transcript is
already on disk. The probe stays off the offline fast path: a stored receipt
whose own duration cannot hold the words now buys a probe, and the verdict
still comes from the probed value, never the stored one.

**A re-validation that declined to probe wrote the weaker receipt back.** The
run that found no duration replaced `{youtube_duration, 318.0}` with
`{fixed_default, null}`, destroying the evidence the next run needed — and
defeating the screening above. A receipt claiming a source-owned duration now
triggers a probe, and a probe that cannot reach the provider leaves the
stronger receipt alone.

Found by #355 during the reparse of a 250-talk vault where
`transcript_quality_receipt_unverified` fires on 193 talks — nearly every
receipt in that vault was about to be written for the first time.

The ceiling catches gross contamination, not subtle: a caption track only
moderately longer than its talk still lands under 240 wpm. Promoting the
timing-overrun rejection ("timed segments extend beyond the source-owned
duration bound") from a dropped `timed_path` to a transcript-level verdict is
the precise detector and stays open on #355.

## 0.20.103 — 2026-08-21

### feat(vault-ingress) — name the deck a rendered PDF came from

Issue #318, item (1)'s second half, and the last piece of it. `slide_source:
"markdown"` (0.20.86) made a markdown-authored talk a valid record, and
`render-markdown-deck.py` (0.20.101) made its deck readable. Between them sat a
quiet data loss: registering the render sets `slide_source` to `"pdf"`, which is
correct — the talk now has real slides — and in doing so erases the only field
that said the deck was ever markdown. Nothing on the record named the file. The
second render, after the speaker added three slides, started with a hunt.

`markdown_decks` is a new top-level collection at record v1, one record per
talk, holding `talk_filename` and `deck_source_path`. It is written by a new
`record_markdown_deck` mutation kind, which upserts rather than appends — the
equivalence ledger beside it is an audit trail of owner judgments and only ever
grows, while a deck registration is current state and a repo that moves
re-points it.

**Why a collection and not a field on the talk record.** The first attempt added
`deck_source_path` as an optional talk field and left
`TALK_RECORD_SCHEMA_VERSION` alone, on the reasoning that a never-before-defined
optional field cannot be misread by an older reader. `stateful-artifacts`
requires a version bump for any persisted shape change, additive included, and
the policy review blocked it. The rule is right and the bump was still wrong,
which is the whole reason this landed where it did:

The constant means analysis generation, not record shape — the #333 entry says
so outright: "the contradiction is real, and it comes from
`TALK_RECORD_SCHEMA_VERSION` carrying two meanings at once: the analysis
generation, which is why a v1 record can never migrate forward, and the record
shape." That is why v7 is today a bump for a field that no longer lives on the
talk record at all; `_restamp_talk_records` says "v7 adds no field a v6 record
lacks."

A bump would not have reached the records that need the field. 209 of the 215
live talk records are schema v1, non-restampable by design, and they are
precisely the transcript-only markdown talks #318 is about. A v8 stamp lifts the
six modern records and leaves the other 209 where they were.

And the bump is not free. Talk versions are accepted as `range(1, CURRENT + 1)`,
so a v8-stamped database read by any older toolkit is not one unreadable record:
it is `talks_schema_version_unsupported`, `usable: false`, the whole vault.

#333 hit this exact wall — an owner ledger bound to the analysis generation,
unreachable for 97% of the corpus — and resolved it by moving the field off the
talk into its own versioned collection. Same wall, same resolution. The nested
alternative is closed for the same reason #333 closed it: "the nested record's
own version does not version its parent."

The collection is optional, absent means no registered deck, and no migration
owns it — it is deliberately absent from `_RECORD_COUNT_KEYS`, since a deck is
registered by an owner who knows where the file is and is never inferred.

**The root schema goes to v2.** A top-level key is part of the ROOT record's
shape, and a version on each nested deck record does not version its parent
database — the same principle #333 stated one level down. So
`TRACKING_DATABASE_SCHEMA_VERSION` moves 1 → 2, root v1 becomes
`PRE_MARKDOWN_DECKS_TRACKING_DATABASE_SCHEMA_VERSION`, and a v0 or v1 database
reaches v2 through the migration tail that already existed. Every step in that
tail is idempotent for a v1 database — its records already carry the versions
the v0 path stamps — so v1 needs no branch of its own; what it did need was for
the tail to stop reporting a hardcoded `from_schema_version: 0`, which would
have misnamed what was migrated.

The collection is not usable on a pre-v2 root, and the way that is enforced
matters. The first attempt raised from the assessment — which turned out to be a
dead end, because `migrate_tracking_database` assesses before it stamps, so the
diagnostic sent an owner at the one command that would refuse them. Usability is
gated one level up instead: a pre-v2 root is never `current`, so every reader
and writer requiring current state refuses it, and the migration advances the
root while preserving the records. Which is what a preservation migration is
for.

Two holes the review caught in this PR's own new code. An absolute locator may
carry a trailing slash — `classify_artifact_locator` accepts it and
`PurePosixPath(value).name` then strips it — so `/repos/slides.md/` reached the
suffix check looking like a file and passed, and the renderer would have been
handed a directory. And the malformed-owner-state diagnostic hardcoded "schema
v1", so after the bump it sent readers at the wrong generation. Both now carry
regression tests.

`record_markdown_deck` takes an `expect`, the same optimistic precondition every
other talk-touching mutation carries: the plan states the `deck_source_path` it
believes is registered, or `{"$missing": true}` when nothing is, and a
registration that moved under the plan fails the write instead of being
overwritten without anyone noticing.

The writer/reader contract moved with it. `references/schemas-db.md` carries the
schema-version table and one access-contract row per consumer, and a root bump
that leaves those rows saying "require database schema 1" documents a flow that
rejects the state the owner now writes. Every row is updated, along with the
five consumer pages outside vault-ingress that state the same requirement —
`illustrations/references/thumbnails.md`,
`vault-ingress/references/bootstrap-and-preflight.md`,
`presentation-creator/references/phase6-publishing.md` and `phase7-post-event.md`,
and `vault-clarification/SKILL.md`.

Fixture fallout worth naming, because it is the argument for the shared
constant now in `tests/conftest.py`: seventeen fixtures pinned the root
generation by literal, and each one failed as `assert 2 == 1` with nothing in
the message naming a generation. Three tests turned out to read
`~/.claude/rhetoric-knowledge-vault` — the developer's real vault — because
they passed no `--vault`, so the argument-validation they assert was being
decided by whatever generation that machine happened to be at. They now pass a
`tmp_path`. And a strict-reader case pinned a "future" root of literal 2, which
this bump turned into the current one; it is derived now, the same way the
talk-record case beside it already warned it should be.

`deck_source_path` goes through `classify_artifact_locator`, the same lexical
contract every other persisted artifact path uses, so a NUL byte (which used to
reach `Path.stat()` and raise outside the renderer's `OSError` diagnostic), a
`~`, a `..` segment, an ambiguous `//server/share`, and a Windows reserved name
are refused by one shared reader rather than by a private opinion about paths. A
markdown-suffix check sits on top. Existence is never checked: the deck's repo
need not be on this machine, so an absent file is the renderer's loud failure at
render time.

Two documentation faults fixed in the same pass. The register-the-render plan in
`references/markdown-decks.md` set `status` and `reprocess_reason` without
declaring them in `expect`, and `validate_plan` refuses a repair that changes a
field it did not declare — so the recipe could never be applied by a reader
following it. Both documented plans are now executed verbatim by a test. And the
page now says that a vault-relative deck path must be resolved against the vault
root before it reaches a renderer, which resolves a relative CLI path from its
own working directory and would otherwise report a missing deck for a good
locator.

Not done here, deliberately: a return claiming `slide_source: "markdown"` is not
required to have a registered deck, though the symmetry with `"pdf"` requiring
`has_pdf` is tempting. Workers analyse; they do not discover decks. Making it a
return precondition would block reprocessing a known-markdown talk whose deck
nobody has registered yet, which is the state every such talk starts in. There
is also no unregister mutation — a deck that moves is re-pointed, which is the
case that actually occurs.

## 0.20.102 — 2026-08-21

### fix(vault-ingress) — close a code fence only with one long enough to close it

Issue #351, both advisories from #349's review, deferred at the time because the
PR was green and `review-severity` says not to burn a re-review round on a lone
advisory.

`_fence_mask` tracked which character opened a fence and not how many of them
there were. CommonMark closes a fence only with the same character, at least as
long — which is the entire reason four backticks exist, since that is how a deck
quotes markdown that itself contains a three-backtick block. Matching on the
character alone closed the outer block on the inner one, and everything after
that point read as deck source: the `---` inside the quoted sample became a
slide break, a quoted `<!-- pause -->` became a reveal. Measured on the test
deck, a three-slide deck read as five and one reveal read as two.

The render's page count was never wrong — it does not consult this reader. The
symptom was `source_slide_count` disagreeing with it, which flips
`slide_count_agrees_with_source` to `false` and tells the operator the deck uses
a construct the source reader does not model. It did not. It used four
backticks.

The same pass takes the adjacent CommonMark rule, for the same reason: a closing
fence carries no info string, so a ```` ```yaml ```` line inside a quoted block is
content rather than a close.

Second advisory, presentation only: a half-installed lane told the operator to
install the whole lane. With presenterm on PATH and weasyprint missing, "Install
presenterm and weasyprint" sends them to check a box that is already checked.
The install clause now names what is absent, which is what the clause before it
already said.

## 0.20.101 — 2026-08-20

### feat(vault-ingress) — render markdown-authored decks as slide evidence

Issue #318, items (2) and (3). Seven of twenty-one talks in a real vault had an
authored deck on disk that this toolkit could not see, because the deck was a
`slides.md` and every `slide_source` value assumed a binary artifact. Exactly
one talk in that cohort had a PDF and therefore got slide evidence at all.
`slide_source: "markdown"` (shipped in 0.20.86) stopped those records being
invalid; it did not make the deck readable. This does.

`render-markdown-deck.py` detects which of the four tools wrote the deck,
renders it to `slides/{talk}.pdf`, and hands back a receipt. The PDF then binds
as an ordinary `static_slides` artifact — no parallel evidence path, no new
artifact identity, nothing downstream needs to know the deck started as
markdown. `references/markdown-decks.md` carries the register-and-requeue plan,
which pairs with the `source_added` reprocess reason from the previous release.

**Four lanes, not one.** The issue proposed a single `markdown-deck` lane. A
lane is an AND over its commands, and no vault authors decks in four tools at
once, so one lane would report a presenterm-only vault as degraded for three
renderers it will never call. `markdown-deck-presenterm`,
`markdown-deck-slidev`, `markdown-deck-marp`, and `markdown-deck-reveal-md`
each degrade on their own, and the renderer requires exactly the one the
detected flavor names.

**The per-click trap, avoided rather than corrected.** The issue documents
Slidev exports where pages 4, 5 and 6 are cumulative build states of one
authored slide, and decks of far fewer real slides exporting at 96, 137, 140,
185 and 228 pages. Item (4) asked for those build runs to be collapsed when
deriving `slide_count`. The cheaper answer is not to create them: Slidev's
`--with-clicks` is off by default, and every renderer here is invoked in its
one-page-per-slide mode, so the page count IS the authored slide count and no
collapsing is needed. The build structure a per-click export would have carried
comes from the source instead — the author's own `<!-- pause -->`, `v-click`,
and `fragment` markers, counted per slide. That is honest
`progressive-reveal` evidence, and the reference file is explicit that it is
neither `crawling-code` nor observed motion.

A deck ending on a separator used to invent a slide out of it — an empty span
starting one line past the end of the file, inflating the very count the page
count is checked against. The trailing separator closes the slide before it.

The source's own slide count is still computed and reported beside the page
count as a cross-check, never reconciled with it. A deck using a construct the
source reader does not model shows up as `slide_count_agrees_with_source:
false` rather than as a confidently wrong number. One such construct is named
outright: a Slidev `src:` key imports slides from another file, so the source
reading is a floor and says so — found by running the reader over the real
Slidev demo deck, where slide 14 is an import.

The render is staged and probed before it is committed. A renderer that exits 0
over a corrupt PDF would otherwise replace a valid earlier render with an
unreadable one and then report the failure, which is the worst of both.

**presenterm's pty, solved rather than documented.** The issue found
`presenterm --export-pdf` failing non-interactively with `Inappropriate ioctl
for device (os error 25)`. `script -qec` gets past that and then hits
`render: screen is too small`, because presenterm reads its export canvas size
from the terminal's window size and `script` leaves it at 0x0. The renderer
attaches a stdlib pty sized 45x160, which presenterm reports as a 2560x1440
canvas — exactly 16:9. Verified against presenterm 0.16.1, which is also where
the headmatter intro-slide rule came from: `author:` alone adds a page,
`theme:` and `options:` alone do not.

**CI installs all four and renders through each.** The first cut shipped
stand-in renderers only, on the reasoning that the real tools are not on the
runners. `ci-safety` Install, Don't Skip says that is backwards: they are
installable, so install them. `scripts/install_deck_renderers.py` puts
presenterm on the runner from its pinned release tarball, checksum-verified,
and the three npm CLIs plus `playwright-chromium` at exact versions;
`tests/test_markdown_deck_renderers.py` then renders a three-slide deck through
each and asserts three pages. That is the only place the claim this design
rests on is actually testable — a tool that starts exporting per click fails
there and nowhere else.

The npm side installs from a committed manifest and lock file with `npm ci`,
not from four top-level versions: exact tops leave the several thousand
packages beneath them free to move between runs, which is not a pin at all. The
cache key hashes the lock file's own bytes, so a transitive version that shifts
under an unchanged manifest misses the cache rather than silently reusing a
different graph.

The install is otherwise cached on the pin set, so a renewed pin reinstalls and
an edited comment does not, and both halves are idempotent against a restored
cache. Three paths are cached, and the two extra ones are the point:
Slidev drives playwright's chromium and reveal-md drives puppeteer's chrome,
each downloaded by its own postinstall into its own cache root. Caching the npm
tree alone would restore a tree whose postinstalls never run again, leaving
reveal-md with no browser on precisely the runs the cache was meant to speed
up. `test_ci_carries_every_renderer` fails rather than skips when the
install left a renderer absent, so a broken install cannot pass as a quiet
green — a per-flavor `skipif` alone would have hidden exactly that.

Verified before shipping by rendering through the real presenterm 0.16.1,
Marp 4.5.0 and Slidev 52.19.1: three pages for three authored slides each,
`<v-clicks>` counted once. reveal-md could not be verified locally — it refuses
a Node outside `^18.18 || ^20.9 || ^22` and this machine runs 26, which is why
the workflow pins 22 and a test asserts the runner honours it.

The stand-in renderers stay for what they are good at: a corrupt render, a
renderer that exits 0 writing nothing, a process that closes its terminal and
hangs. Those are reproducible against a stand-in and nothing else.

Two cache defects the reviewer found that a green run never would: a present
`presenterm` binary was taken as the pinned one, and the npm tree counted as
restored on the strength of Slidev's shim alone. Either would have run an
unreviewed version and reported a cache hit doing it. Both halves write a stamp
naming exactly what was installed — presenterm's version, the lock file's
digest — and a hit now requires the stamp to match and every renderer
executable to be present.

Two things the live runs found that no amount of local testing would have.
`tar` told to extract the member `presenterm` failed with `Not found in
archive`, because the release nests its binary under a version-stamped
directory and the fixtures were flat. And reveal-md's chromium died with `No
usable sandbox!`: Ubuntu 23.10 restricts unprivileged user namespaces through
AppArmor. Chromium suggests `--no-sandbox`, which would have shipped a weakened
browser to every operator to work around one CI image, so the installer lifts
the restriction on the runner instead and the renderer stays sandboxed
everywhere else.

Finding the second one at all took a change worth keeping: reveal-md catches
every puppeteer failure and prints exactly `Error while generating PDF for
"<deck>"`. A `RendererSpec` can now declare the environment its tool needs, and
reveal-md's declares its debug channel — so the wrapper's diagnostic carries
the real exception rather than that one line.

And once reveal-md could render at all, it rendered the per-click export this
whole design exists to avoid: reveal.js puts every fragment on its own PDF
page, so the three-slide fixture with one fragment came back as four. There is
no flag for it — reveal-md reads `pdfSeparateFragments` only from a
`reveal-md.json` in its working directory — so a spec can also declare files to
drop in the staging directory it runs from. Slidev's `--with-clicks` was off by
default; reveal.js's equivalent is on, and only a live render says which.

Also fixed while in `tests/test_check_runtime.py`: a child-process traceback
assertion that failed under an inherited `FORCE_COLOR`, which Python 3.13+
reads as permission to colorize. The child now runs with `PYTHON_COLORS=0`.
## 0.20.100 — 2026-08-20

### fix(ci) — renew the Chocolatey ffmpeg pin to 9.0.1

Third time, same mechanism, and the step's own comment called it: "Chocolatey
serves only the current version of a package, so expect this pin to need
renewing again." The feed withdrew 9.0.0, `choco install ffmpeg
--version=9.0.0` stopped resolving, and the Windows platform-contracts job went
red on every branch with no source change behind it.

Its own bump rather than a ride-along on whatever PR happened to notice, per
`dependency-management` Freshness. Nothing but the three version literals
moved.

The renewal stays manual because no Dependabot ecosystem covers Chocolatey. The
current version is one query away, and the comment already carries it:

    https://community.chocolatey.org/api/v2/Packages()?$filter=Id eq 'ffmpeg' and IsLatestVersion

## 0.20.99 — 2026-08-20

### feat(vault-ingress) — `source_added` is its own requeue reason

Issue #318 found the workaround at the end of a real 21-talk reparse: after
exporting a Slidev deck to PDF and registering it on an already-`processed`
talk, there was no supported way to get the talk back into the queue.
`apply-source-repairs.py` refused the status change with `completed claim
result_status 'processed_partial' disagrees with talk status
'needs-reprocessing'`, and `queue-state.py normalize` reported `changed: 0`
because normalization requeues evidence that *drifted*, and evidence that
newly *arrived* has not drifted.

The path that worked was `reprocess_reason: "source_identity_correction"` — a
`LEGACY_REPROCESS_REASONS` member, so `is_deliberate_reprocess_reason` accepted
it and the claim/status disagreement was allowed. It worked for the wrong
reason. Nothing about the talk's identity was corrected: the video is the same
video, the deck is the same deck, and the only thing that changed is that one
of them became readable. A vault audited a year from now would show a run of
identity corrections that never happened.

`source_added` now says what actually happened, and
`DELIBERATE_REPROCESS_REASONS` is the set `is_deliberate_reprocess_reason`
checks — `LEGACY_REPROCESS_REASONS` keeps its own meaning as the two reasons
that predate the structured `pattern_scoring_generation:` form rather than
quietly growing a third member that is not legacy at all.

`references/bootstrap-and-preflight.md` documents the register-then-requeue
plan next to the source-repair commands, which is where the reparse looked for
it and did not find it.

## 0.20.98 — 2026-08-20

### fix(ci) — the apt cache key names the suite it was built for

The key was `apt-<os>-<package-digest>-<week>`, and `runner.os` is `Linux` for
every Ubuntu image GitHub has ever shipped. So when `ubuntu-latest` rolls to the
next LTS, the first run on the new image computes a key identical to one the old
image saved, restores that entry, and gets indices and `.deb` archives for the
suite it is no longer on. `actions/cache` does not save on an exact key hit, so
the new suite would not get an entry of its own until the week stamp rotated.

Narrow and self-limiting, which is why #344 deferred it rather than folding it
in: the pins in `PACKAGES` are suite-specific (`4:24.2.7-0ubuntu0.24.04.6` is a
noble build), so the same image move makes them unresolvable and the install
fails loudly on the pin long before anyone wonders about the cache. Two failure
modes, one trigger, and the loud one lands first.

`VERSION_CODENAME` from `/etc/os-release` is in the key now, read through the
`--codename` mode of `scripts/install_system_deps.py` rather than a second
parse in shell — `read_codename` already existed for the mirror probe URL and
already had tests. That mode sits outside the entry point's report contract on
purpose: the install path answers an unreadable `/etc/os-release` with a failure
report, but a cache key has nothing to fall back on, and a swallowed error there
keys every run on the empty string, which is one shared entry across every
suite. It raises instead.

The step's shell went with it. `echo "k=$(cmd)" >> "$GITHUB_OUTPUT"` discards
`cmd`'s exit status — `echo` succeeds, the output is written empty, and the
`set -e` the runner gives the block never sees a thing. The three values are
assigned first and echoed after, so a failing resolver takes the step down.

Closes #345.

## 0.20.97 — 2026-08-19

### fix(ci) — the apt cache stops being decorative

The dependency install cached apt's `.deb` archives and hit that cache every
run — 185 MiB restored, logged as `Cache restored successfully` — and then went
to a mirror anyway. Nothing in the step consulted what it had just restored:
`fetch_deps()` ran `apt-get update` unconditionally, and the archives only ever
save work inside `apt-get install`, which the run never reached. The bytes were
cached, the package indices were not, and fetching the indices is what hung.

So the network trip was not a cache miss. It was unconditional by construction,
and a perfect cache would not have avoided one second of it.

The indices are cached beside the archives now, and a restored pair installs
with `--no-download` — no probe, no `apt-get update`, no mirror. Both halves are
checked rather than the cache-hit flag, because an entry saved before this
change holds only the archives and cannot resolve anything offline. A cached set
that cannot satisfy the install — a runner image that gained or lost a
preinstalled library — falls through to the mirror path instead of failing.

The second failure is what the 20-minute stall actually was. Four mirrors, each
given a 300s `apt-get update` timeout, each timing out at exactly 300.0s with no
`Err:` or `Failed to fetch` line anywhere in the log. Canonical, kernel.org and
Oregon State do not go dark in five-minute lockstep; four identical timeouts are
the runner's side of the connection. A HEAD of each mirror's `InRelease` now
runs ahead of it: an unreachable host is skipped in seconds, and every host
unreachable fails the step immediately naming the runner's network as the
diagnosis. A mirror that answers the probe and then fails the update is still a
real mirror failure and still walks the fallback chain, so the two shapes stay
distinguishable in the report.

Every package now carries an exact version. `tesseract-ocr` was already pinned;
`ffmpeg` and `libreoffice-impress` were not, so the tested toolchain could change
between two runs of the same commit. No scanner tracks an apt version baked into
a script, so the renewal mechanism is stated beside the pins: ffmpeg and
tesseract sit in the static `noble` pocket, libreoffice-impress ships from
`noble-updates` on Ubuntu's roughly monthly security cadence, and the archive
serves only the current version of each — a superseded pin fails the install
loudly rather than drifting quietly. The madison query that yields the current
versions is recorded with them.

The cache key binds to a digest of the pinned set plus a week stamp, rather than
to the installer file. Hashing the file invalidated 185 MiB of archives whenever
a comment or the fallback order changed, and the thing a cache entry actually
depends on is which package versions it holds. The week stamp is what keeps a
set nobody touches from being pinned forever: it is refetched on the next
rotation instead of being served from a cache indefinitely.

Moving the step out of shell nearly broke the fallback it exists for. The old
form passed `/etc/apt/sources.list.d/*.list` to the mirror rewriter and the
shell expanded it first; Python does not, so the rewriter received a path with
an asterisk in it, found nothing there, and skipped it — silently, since a
missing source file is a legitimate skip. Every retry would have repointed
nothing and fetched from the mirror that had just failed. The caller enumerates
the matching files now, and the tests run the real rewriter against real source
files and read the mirror back out of them, because a fake that reports success
for a rewrite that changed nothing is what let the bug pass in the first place.
The deb822-only layout — what 24.04 actually ships, and where a missed rewrite
leaves no other file to cover for it — has its own fallback test.

`main` catches at the process boundary under the `error-handling` outer-boundary
carve-out. The workflow step reads stdout as the report and a non-zero exit as
"not installed", so an unreadable `/etc/os-release` or a subprocess that will not
launch has to come back as that report rather than a traceback over empty
stdout, which a parser reads as a malformed contract instead of a failed
install. Interrupts still propagate.

The cache locations are the caller's throughout. `configure_apt` and the apt
config body read the module constants while accepting the arguments, so passing
a cache path redirected nothing and the tests wrote `/tmp/apt-cache` on whatever
machine ran them. The fake now refuses any path outside its sandbox, which turns
that class of leak into a failing test rather than a directory left behind.

The probe covers both hosts of a pair. Only Canonical's splits archive from
security, and probing the archive alone let a pair with a dead security host
through to the update that then burned its full timeout — the stall the probe
exists to avoid. The suites differ with the host: security.ubuntu.com carries
`<codename>-security` and does not serve the plain suite, so probing it for that
would report a healthy host as unreachable and skip Canonical permanently.

The step moved out of the workflow into `scripts/install_system_deps.py`, whose
side effects all route through an injected runner — the command sequence is the
whole behaviour, and it is now assertable without a runner, sudo, or a network.
Both original failures are pinned by a test that fails if the cache is consulted
and the mirror contacted anyway, or if a single `apt-get update` is issued when
no mirror answered.

## 0.20.96 — 2026-08-19

### fix(vault-ingress) — the equivalence ledger becomes its own collection (#333)

The catalog repair was freed from the current-generation gate; the equivalence
writer beside it was not. Registering the four talks the ledger exists for then
failed on the first one:

```
talks['2026-02-02-jfokus-2026-robocoders-...'].schema_version must be
exact current talk schema 7 before this mutation
```

All four are schema v1, like 209 of the 215 live records. The ledger was
unreachable for every talk it was built to serve — the same gap as the catalog
repair, one writer over, and only visible when the records were finally written.

Relaxing the writer's gate would have written a v7-shape field onto a v1 record
— the ledger cannot be both "the v7 shape addition" and reachable on v1. The
contradiction is real, and it comes from `TALK_RECORD_SCHEMA_VERSION` carrying
two meanings at once: the analysis generation, which is why a v1 record can
never migrate forward, and the record shape, which is all an owner ledger needs.

`source_title_equivalences` moves out to its own top-level versioned collection,
keyed by `talk_filename`. The talk record's shape stops changing, so the
generation question does not arise and no record carries a field it does not
declare. The collection is optional — absent means no equivalences — so every
database written before it existed stays valid.

The equivalence record goes to **v2** and the owner migration lifts any v1 entry
off its talk into the collection, stamped v2 and carrying the owning filename.
It validates every legacy ledger before removing anything — assessment no longer
inspects the nested shape, so a malformed one discarded there would be destroyed
with nothing left to report it — and counts an empty ledger's removal as a
change, because altering the database while reporting no change breaks the
no-op contract callers rely on.

Each nested record is validated as a v1 record before it is lifted, and the
lifted collection is validated again in its new shape. Stamping the current
generation onto an unchecked record would coerce a malformed one into apparent
validity and silently rewrite a newer generation this reader cannot interpret —
a newer generation is unusable state, not something to convert.
The nested shape shipped in a release, so a consumer can hold one: readers now
consult the collection only, and an unmigrated entry would be ignored — the talk
re-gating on a mismatch its owner had already approved, with nothing to show the
approval was lost.

v7 was introduced for this ledger and no longer carries it. The bump is
published and stays; the migration docstring now says what it actually does.

## 0.20.95 — 2026-08-19

### fix(vault-ingress) — the upload comparison respects the venue's timezone (#333)

#333 listed `2025-11-01-churconf-...` among eleven talks whose recording appeared
to predate its own delivery: cataloged `2025-11-02`, uploaded `2025-11-01`. It
called the one-day gap "almost certainly a timezone slip rather than a wrong
delivery", and it was right — but the check had no way to say so.

ChurConf 2025 ran on Sunday 2 November in Auckland. Auckland is UTC+13 in
November, so a talk delivered there and uploaded straight after carries a UTC
upload date of the previous day. The catalog was correct; the comparison was
wrong.

That is not a ChurConf quirk. A provider upload date is UTC and a cataloged
delivery date is the local day at the venue, so the two are not measured on the
same clock. Every delivery east of UTC can produce this, and the gate would keep
reporting a wrong delivery for a correctly cataloged talk.

Day-precision comparison now allows one day. The extremes are UTC-12 and UTC+14,
so a single day absorbs every real offset, while a recording genuinely from an
earlier delivery is off by far more — the ten talks corrected under this issue
were off by one to two YEARS.

The same grace covers a bare-year record's boundary, compared against 1 January
of the year it names. "A bare year already spans the year, so it needs no grace"
is true about the span and wrong about the edge: a talk delivered on 1 January
in a UTC+13 venue is uploaded on 31 December UTC, which is the identical offset.
An upload from 30 December or earlier still gates, which is the shape of every
genuine finding this issue corrected.

## 0.20.94 — 2026-08-19

### fix(vault-ingress) — catalog repair reaches legacy talk records (#333)

#336 gave the delivery date an owner writer. Applying #333's corrections against
the live vault then failed on all ten:

```
talks['2018-java-8-puzzlers.md'].schema_version must be exact current
talk schema 7 before this mutation
```

**209 of the 215 live talk records are schema v1.** The other six are analysed
records at the current generation. Every talk #333 set out to correct is legacy,
and so is 97% of the catalog.

No migration lifts them. `_restamp_talk_records` promotes only records that
already hold the analysis the current shape implies, because the generations
below carry analysis a migration is forbidden to fabricate — recomputing a score
under arithmetic its worker never used is the silent reinterpretation
`stateful-artifacts` exists to prevent. A v1 record reaches the current shape by
being reanalyzed, not by being restamped. That function's own docstring names
the failure this produced:

> Without the restamp every stored talk would be unmutatable: the owner writer
> requires the exact current talk schema before any mutation, so the bump alone
> would lock the database until this ran.

Which is the state the v1 records were in: unmutatable through every sanctioned
path, with the only route to a date correction being a full reanalysis of a talk
whose transcript and slides were never in question.

The current-generation gate is right for a writer that assumes the current
record shape. `apply_reviewed_metadata` assumes nothing about it — it reads and
writes `title`, `conference`, and `date`, none of which any talk-record
generation has changed. It now accepts any generation the database assessment
can read, and leaves the record's version alone: repairing a catalog fact must
not claim the record was reanalyzed. Every other writer keeps the strict gate.

## 0.20.93 — 2026-08-19

### feat(vault-ingress) — owner-reviewed provider-title equivalence (#333)

Four talks in #333 could not register a source identity because `titles_agree`
could not reach their provider titles. Two are Russian-language JavaDay Kiev
2014 recordings whose catalog titles are English summaries carrying a `(Ru)`
marker. Two are RoboCoders deliveries the uploader published as "AI-Assisted
Engineering Applied: The Battle of Agents".

Neither is a comparator bug. `битва конфигураций` is "battle of
configurations", and no deterministic overlap test crosses that gap without also
matching things it must not. The comparator is right to refuse, and it must stay
right — it is the same test that catches a video from the wrong delivery.

The alternative was rewriting four catalog titles to whatever the provider
published: Russian titles in an otherwise-English catalog, and two RoboCoders
entries that stop matching the ten around them. That discards the speaker's own
naming to satisfy a string comparison.

`source_title_equivalence` records the judgment as data instead — both titles
the owner read, why the pair was accepted from a closed two-value reason set,
and when. It is consulted only after the deterministic comparison fails, and it
pins BOTH sides of the pair. An approval says these two names name one talk; it
says nothing about a name the owner never read. So a provider that retitles the
video re-gates, and so does a catalog title edited after the review — pinning
only the provider side would have left an edited catalog title riding an
approval granted for a different one. The
writer appends only and refuses a duplicate, so the ledger stays an audit trail
rather than a mutable override.

The record's own `schema_version` is validated exactly, and both the reader and
the writer refuse a generation they cannot name — `_require_closed_shape` ignores
that field for every record, so a ledger whose whole purpose is suppressing a
blocking finding checks it itself. Reader and writer canonicalize the pinned
title through one shared normalizer, so two records the reader would treat as a
single approval cannot be stored as two.

`TALK_RECORD_SCHEMA_VERSION` goes to **7**, because the ledger changes the
persisted talk-record shape and the nested record's own version does not version
its parent. The migration restamps v5 and v6 forward — both already hold the
analysis v7 implies — and leaves earlier generations alone, since those reach the
current shape by being reanalysed, never by being stamped. On the live vault that
is 6 records restamped and 209 legacy records untouched. Migration never invents
the field: absence means "no equivalences", which is the correct default.

The writer binds each approval to what the talk actually holds when it is
recorded: its current catalog title, its recorded provider title, and its video.
Without that, a plan could pre-authorize an identity the talk does not have — a
title it might be renamed to later, or another video's — and that record would
sit dormant until the catalog drifted onto it, suppressing the gate for a pair
no owner ever compared.

When an equivalence applies the check passes silently. A warning on every run
would be noise about a decision the owner already made and recorded, and the
record itself carries the evidence and the timestamp.

## 0.20.91 — 2026-08-19

### feat(vault-ingress) — owner-reviewed delivery-date repair (#333)

Correcting the eleven catalog dates #333 measured turned out to be impossible
with the writers that existed. `apply-source-repairs.py` owns the source lanes
and rejects a catalog field outright. `apply_reviewed_metadata` owns catalog
identity, but its closed field set was `{title, conference}` — so a delivery
date the provider evidence disproves had no owner path at all, and the SKILL
forbids editing the database directly. The measurement landed with no way to act
on it.

`date` joins that closed set, classified metadata-only alongside `title` and
`conference`: rhetoric analysis derives from transcript and slide content, so a
corrected delivery date cannot stale it, and the writer proves that rather than
assuming it.

One extra condition rides on `date` that the other two do not carry — the value
must be readable by `parse_catalog_date`. Writing `"October 2013"` would trade a
wrong date for an uncheckable one: preflight would stop comparing source
evidence against the record and report `source_identity_date_uncheckable`
instead of gating. A repair that silently disables the gate it was meant to
satisfy is worse than the wrong date it replaced.

## 0.20.90 — 2026-08-18

### fix(vault-ingress) — one owner for the catalog-date comparison (#333)

Registering source identities across the live vault surfaced a number that made
no sense: `audit-source-identities.py` reported **1** `provider_upload_predates_catalog`,
and preflight — reading the same records, minutes later — reported **11**
`source_identity_upload_predates_talk`. Same comparison, same facts, two
answers, and only the preflight number gates. The operator ran the pre-check,
read it as clean, and met the other ten at the gate.

Both scripts had a function named `parse_catalog_date`. They were not the same
function:

```python
# audit-source-identities.py — ISO days only
date.fromisoformat(value.strip())  # "2014" -> ValueError -> None

# preflight-vault.py — year-aware
if re.fullmatch(r"\d{4}", value):  # "2014" -> (None, 2014)
    return None, int(value)
```

Nine of the eleven withheld talks are `playlist-*` records whose `date` is a
bare year. To the auditor every one of them read as "no catalog date", so the
upload comparison was not failed — it was never attempted. A record too coarse
to compare precisely is still a record that names a year, and an upload from
the year before is still evidence of the wrong delivery.

`parse_catalog_date` and `upload_predates_catalog` now live in
`source_identity_matching.py`, alongside the `titles_agree` contract both
scripts already shared, and both callers compare at whichever precision the
catalog record actually carries.

Worth recording, because #333 assumed otherwise: the title predicate never
diverged. The auditor's 4 `provider_title_mismatch` against preflight's 2 is a
population difference, not a predicate one — the two "Battle of Agents" videos
were withheld before registration, so preflight had no stored title to compare
and never evaluated them. Both scripts call the same `titles_agree`.

`expected_duration_seconds` was also copied into both scripts. The copies agree
today, which is precisely where the date predicate started; it moved to the
shared module too, unchanged.

## 0.20.89 — 2026-08-18

### docs(vault-ingress) — record which assessor owns persisted citations (#167)

`persisted_pattern_observations.py` audits container shape, detection shape,
catalog identity, confidence, evidence text, and dimensions, and stops there.
#167's second acceptance criterion also names evidence citations and source
inspection, so the module reads as if it forgot two checks, and the obvious fix
is to reuse the return path's `validate_evidence_citations` and
`validate_source_inspection` — one implementation cannot drift from itself.

That fix is wrong, and wrong in a way the reader only discovers by shipping it.
Those validators enforce the worker-side field sets. A canonically persisted
citation is the worker's citation plus what the engine resolved onto it:

```
{"source": "transcript", "channel": "transcript", "quote": "...",
 "line_start": 1, "line_end": 1, "artifact_root": "vault",
 "artifact_path": "transcripts/talk.txt", "artifact_sha256": "aaaa..."}
```

Everything after `quote` is an unknown field to `EVIDENCE_CITATION_FIELDS`, and
persisted `source_inspection` gains `line_count`, artifact identity, and
`coverage_complete` the same way. The check would have reported
`detection_evidence_citations_invalid` on every correctly persisted talk in the
vault, and #294's fail-closed writer would then have refused to render any of
them. `tests/test_write_analysis.py::test_cli_renders_persisted_locations_not_model_locations`
is what caught it.

The persisted contract already exists in `_v5_projection_freshness_reasons`
inside `assess_persisted_pattern_evidence_freshness`, and is stricter than the
duplicate would have been: citations present and non-empty, each falling within
the recorded `source_inspection`, each bound to the artifact identity it was
read from, and an `evidence_sources` that disagrees with the inspection
rejected. It is required at `EVIDENCE_BOUND_SCORING_SCHEMA_VERSION` — a caller
that omits it raises rather than silently passing, the fail-open shape #304
recorded.

The split is now in the module docstring and pinned by
`test_source_location_defects_belong_to_the_freshness_assessor`, which asserts
both halves: the structural classifier stays silent on a source-location
defect, and the freshness assessor reports `source_inspection_missing` for the
same talk. Asserting only the silence would pin a hole rather than a boundary.


## 0.20.88 — 2026-08-18

### feat(vault-ingress) — bind video derivatives to the exact source bytes (#216)

A schema-v3 video-extraction manifest named its source by id and path. Both
survive a replacement at that path, so a vault whose `AbCdEfGhI_1.mp4` was
re-downloaded, re-encoded, or swapped for a different recording kept PDFs that
passed every structural owner check while describing bytes that were no longer
there. The record could not tell a re-acquisition from a substitution, and #190's
runtime probe cannot close it after the fact: the strong claim is historical
("these pages came from these bytes"), and no digest observed today can supply it
retroactively.

Schema v4 advances the manifest only when the producer can stamp an engine-owned
source receipt captured around the same extraction run. The receipt is built by
`build_video_source_receipt` in `skills/vault-ingress/scripts/video_evidence.py`
from the bounded #190 probe, and carries the source digest, size,
duration/container/stream evidence, the bound file generation, and the probe
contract version. It is path-neutral and bounded — no locator, no raw ffprobe
document, no parser stderr. It rides on the manifest head AND byte-identically on
every `artifacts[]` entry, so each derivative's own record names its source and
two derivatives from two runs cannot be merged under one head. The receipt lives
in the record, not in the PDF file.

The extractor probes before sampling a frame and again after the last PDF lands,
sharing one assessment so the closing probe costs a stat when the generation held
and a full re-probe exactly when it did not. Drift removes every PDF the run
produced and exits non-zero with a closed reason: a half-bound result is worse
than none. Derivatives stay staged until the closing probe passes, then publish
as a set: each destination's prior version moves aside first, and a failure
part-way puts every already-replaced destination back. A failed run — for any
reason, not only drift — leaves the destination PDFs exactly as it found them.
Rollback covers interrupts, not only I/O errors. A publish a process the host
killed outright left half-applied is undone on the next run: a stranded prior
version is restored, and a destination that held nothing before the publish is
recorded by an absence marker so its orphan can be told from an artifact worth
keeping. An unprobeable source — missing, corrupt, or a dataless cloud
placeholder — produces no record at all rather than one bound to a stub.

Readers compare the receipt's content fields against a fresh probe;
`source_generation` is deliberately outside that comparison, because device,
inode, and mtime are host-local and change on a byte-identical vault move while
the digest already proves the bytes. Preflight gained two findings:
`video_extraction_source_lineage_mismatch` (blocking — the source reads but is not
what the PDFs came from) and `video_extraction_source_receipt_missing` for
archival v3 records. The second is deliberately not `provenance_invalid`: a v3
record was valid under its own contract, and naming the repair (reacquire the
source, re-extract) beats calling correct history corrupt. Nothing migrates a v3
record in place.

The manifest schema version moves to `ingress_contract.py` so the producer and
every reader gate on one number instead of three literals. Every surface that
told an agent a completed video return needs a schema-v3 manifest — the return
validator's messages, `schemas-db.md`, `processing-rules.md`,
`source-identity-preflight.md`, `subagent-instructions.md` — now says v4, with v3
wording kept only where it describes the archival path.

`PIPELINE_VERSION` 0.12.0 → 0.13.0: a run now requires a probeable source, which
is an extraction-behavior change, not only a record-shape one.

## 0.20.87 — 2026-08-18

### feat(vault-ingress) — a standalone persisted-observation audit (#167)

`assess_persisted_pattern_observations` was reachable only in-flow. Seven
consumers call it — migration, preflight, analysis rendering, queue
normalization, persistence, the adherence baseline, the cohort snapshot — and
every one assesses a talk to decide something about that talk, then moves on.
None could answer what is wrong with a corpus in total, which is this issue's
last acceptance criterion: run the validator against a copy of the live database
and attach the deterministic counts to the repair/reparse report.

`skills/vault-ingress/scripts/audit-persisted-pattern-observations.py` is that
entry point. It emits per-reason-code counts and the filenames behind each, so a
count can be acted on rather than only reported.

Read-only, and pointing it at a copy is the intended use: the reparse decision
wants the counts BEFORE the migration restamps anything. Exit 1 means the corpus
has defects and the report is still on stdout — a finding, not a failure. Exit 3
is a broken audit with empty stdout, so the two can never be confused.

A talk carrying no `pattern_observations` reports `observations_absent` rather
than being skipped: 9 of 209 live talks had no block, and silence would have read
as nine clean talks. A talk whose own filename is unusable is named by index, so
a malformed record is not the one entry the report cannot identify.

Reports are byte-identical across runs over one database, so a diff between two
runs is a real change rather than dict ordering.

Wired into `bootstrap-and-preflight.md` AHEAD of the migration command rather
than beside the other preflight audits. That reference executes in order, so an
audit placed with its siblings would run after `migrate-tracking-database.py`
had already restamped and possibly repaired the observations it is meant to
describe — a report about the repaired corpus, not the one the reparse decision
is about.

## 0.20.86 — 2026-08-18

### feat(vault-ingress) — admit `markdown` as a slide source (#318)

`slide_source` accepted binary artifacts only — `pptx|pdf|both|video_extracted|none`
— so a speaker who authors decks in Slidev, presenterm, Marp, reveal-md or
remark had no honest value to record. A real vault recorded
`slide_source: "markdown"` on 24 talks and preflight blocked every one as
`slide_source_unsupported`, forcing a rewrite to `none`. Those records were
right and the enum was wrong: `none` discards the fact that an authored deck
exists, and the resulting transcript-only reading then looks like a speaker with
no slides rather than a deck the toolkit cannot read.

`markdown` is provenance, deliberately absent from `USABLE_SLIDE_SOURCES`.
Nothing here renders markdown, so the talk supplies no slide evidence until the
deck is exported to PDF and re-registered as `pdf` — the manual path that
already works. Admitting it to the usable set would gate slide-evidence entries
on an artifact no reader can open, trading a wrong blocking finding for a wrong
passing one. It requires no binary artifact, so it raises no
`slide_pptx_*` / `slide_pdf_*` / `slide_video_*` fault either.

Every rule that treated `none` as "no readable slides" now keys on
`SLIDE_SOURCES_WITHOUT_READABLE_SLIDES` instead: rejecting authored-slide
evidence in `structured_data`, rejecting `static_slides` / `native_deck` in
`evidence_sources`, and refusing `processed` status. Adding the enum value
without those would have been worse than leaving it out — a markdown return
could have claimed slide evidence and a `processed` terminal state while the
contract says it supplies none, replacing a wrong blocking finding with a wrong
passing one. Raised by the policy reviewer on #330. The set is pinned by test to
the complement of `pattern_evidence.USABLE_SLIDE_SOURCES`, so the two modules
cannot drift into a source claiming evidence it cannot produce.

This is item (1) of the issue. Auto-rendering (a `markdown-deck` runtime lane,
build-run collapsing for `slide_count`) is not attempted here, and the issue
stays open for it.

## 0.20.85 — 2026-08-18

### fix(vault-ingress) — bind a deck's identity assessment to the bytes it read (#176)

`binding_refusal` pinned an assessment to its deck by `pptx_path` — a path
string. Replace the file at that path and the stored `matched` verdict still
stood, so the new deck's slide counts, OCR and pattern observations became that
talk's evidence under a proof made about different bytes. That is the exact
failure this issue exists to stop, surviving its own fix.

`PPTX_TALK_IDENTITY_SCHEMA_VERSION` is 2, and an assessment now records the
`source_identity` it was reached against, in the same
`{algorithm, digest, size_bytes}` shape `visual_evidence.source_fingerprint`
already uses. A v1 assessment cannot be upgraded — nothing recorded which bytes
it read — so it refuses as `identity_assessment_schema_unsupported` and reads as
unproven, the position `unassessed_legacy_binding` already takes for the same
reason: a proof that was not witnessed cannot be manufactured.

The observation is a REQUIRED argument, never defaulted, so a caller states
which case it is in:

- `preflight-vault.py` digests the deck and compares, catching the swap. A deck
  it cannot read is its own blocking finding,
  `pptx_talk_binding_source_unobservable` — passing `None` there would read as
  "no observation available" and fall through.
- `mutate-tracking-database.py` takes a database and a plan and never touches
  the vault, so it passes `None`. That still requires the assessment to name a
  generation, and cross-checks it against the record's own extraction
  fingerprint when the record has one — two independent producers disagreeing
  about which deck a row is means one describes a different file.

Identity is still verified BEFORE extraction: a freshly catalogued row carries
no `visual_evidence`, so there is nothing to cross-check and the requirement
narrows to the assessment naming a generation at all. Requiring the extraction
fingerprint would have inverted the order this issue establishes.

A `source_identity` is held to the same contract as the extractor's
fingerprint — algorithm `sha256`, a 64-character lowercase hex digest, a
positive integer size. The two are compared to each other, so a looser reading
would have let an assessment claim a generation the database itself refuses;
`{"algorithm": "x", "digest": "x", "size_bytes": 0}` is not a deck anything
could have read. `tracking_database` imports this module, so the contract is
mirrored rather than imported, and a test pins the two together.

`read_deck_identity_facts` copies the deck into a private spool once, digesting
as it copies, and parses that snapshot. The digest and the facts are then the
same bytes by construction.

Three weaker versions were tried and each was defeated, all three caught by the
policy reviewer:

- fingerprinting the path in a second open — a deck replaced between the opens
  hands generation B's digest to facts parsed from A;
- bracketing the read with a fingerprint on each side — an A→B→A replacement
  walks straight through it, since `before == after` while the facts came
  from B;
- digest-then-seek-then-parse on one descriptor — survives the path being
  repointed, but a descriptor does not freeze the inode, so a writer that
  truncates and overwrites the same file between the two reads still yields an
  identity describing different bytes from the facts.

The window is not narrowable by comparing more, because every version above
reads the live file twice. Copying once removes the second read instead of
racing it.

The generation check runs last in the refusal order. Everything above it asks
whether the assessment is a coherent proof; this asks whether it is a proof
about the bytes that are there now, and running it earlier would mask a
malformed assessment behind a generation complaint.

## 0.20.84 — 2026-08-18

### chore(ci) — pin the publish workflow to the registry-aware bump (#324)

The publish pin was `af116eb` (2026-08-16). `smart-publish.sh` became
REGISTRY-aware in coding-policy#298 the following day, so this repo was still
computing the next version from the manifest alone — which collides the moment a
credit-outage run skips the manifest commit-back and `main` falls behind the
registry.

That is the whole of the #324 chore. The manual per-release resync was working
around a stale pin, not an unfixable pipeline: the new bump reads
registry-empty -> manifest, manifest-strictly-ahead -> manifest, otherwise
registry latest + one patch, so a lagging manifest stops being able to collide.

Inputs are backward compatible (the new revision only adds `node-version`, with
a default), and coding-policy publishes itself on this revision. Manifest
resynced to `0.20.83` in the same change so the state is honest either way.

## 0.20.83 — 2026-08-18

### fix(vault-ingress) — a boolean weight no longer passes the freshness replay (#322)

`_basis_projection_drifted` type-checked the persisted basis's `schema_version`,
its `not_evaluable_count`, and both lane count maps, then settled the `weights`
map on value equality alone. `True == 1.0` in Python, so a basis carrying
`{"strong": true, "moderate": 0.5, "weak": 0.25}` compared equal to the weight
table the lanes require and the record reported fresh — and every reader
afterwards believed the shape had been verified.

The write side already refused it: `return_validation._validate_score_basis_types`
loops the same map rejecting bools. This is the read-side half of that guard,
which is the half that matters for a record already in the database, since a
persisted record is a hint and not authority. Raised by Copilot on #321.

### docs(vault-ingress) — six comments describing the flat contract as universal (#313)

Two comments were reported; four more of the same shape turned up in the same
audit. Both claims had been true of the flat generation and were left
unqualified when the weighted split landed:

- "the score is count(patterns) minus count(antipatterns), so it is an INTEGER
  by construction" now names the flat generation, in `persist-results.py`.
- "confidence-weighted, and therefore fractional" now reads "MAY be
  fractional", in `adherence_baseline.py` (twice), `pattern_evidence.py`
  (twice), `persist-results.py`, and `return_validation.py`.

A weighted aggregate may be whole — two strong patterns against one strong
antipattern is exactly `1.0`, and
`test_weighted_score_persistence.py::TestResolveAWeightedScore::test_a_whole_weighted_score_stays_valid`
pins that case, so the comments contradicted a test shipped in the same change.

### test(vault-ingress) — name the branch that accepts a persisted weighted record (#299)

The activation's last open bullet asked for integration coverage through
`validate_persisted_v2_analysis_state`. That chain was already running:
`merge_talk` calls `validate_effective_v2_state` before it returns, so every
existing v6 merge test reached the validator transitively.

What no test said is WHICH of its four accepted field sets took the record. The
v6 set is the v5 set plus `pattern_score_basis`, so a weighted record that lost
its basis validates cleanly as a v5 one and the merge still passes.

The new class states the v6 observation field set as a literal — not as a
comparison against `V6_PERSISTED_PATTERN_OBSERVATION_FIELDS`, which is what the
validator itself reads, so that comparison passes whenever the record and the
validator agree, including when both drop the basis and the weighted contract
quietly stops being required. A second test pins the constant to the literal, so
moving it fails loudly instead of redefining what v6 means.

It also proves the v6 branch is a closed set rather than "v5 plus whatever else
arrived", runs the production gate `validate_effective_v2_state` directly, and
pins what a basis-less v6 record actually hits: losing the basis leaves exactly
the v5 field set, so the FLAT contract applies and the weighted fraction the
record still carries is refused as a non-integer. Removing the basis from the v6
constant fails the class; so does removing the v6 branch from the validator.

### chore(release) — resync the manifest to the registry (#324)

Registry `0.20.82`, manifest `0.20.81`. The out-of-credits publish exits
non-zero after the artifact lands, so `smart-publish.sh` returns on the tolerated
credit signature before its commit-back runs and `main` keeps the old version.
The next auto-bump then resolves a version the registry already has and the
publish dies.

The resync rides on this PR's own diff rather than getting a PR of its own: a
bump-only PR is itself a release, so it re-arms the condition it repaired —
which is what #325 demonstrated. Whoever opens the next PR here checks
`capture-registry-baseline.sh` against `.tessl-plugin/plugin.json` first, until
the upstream commit-back runs on the tolerated path or the org's credits reset.

## 0.20.81 — 2026-08-17

### fix(vault-ingress) — a persisted weighted score is no longer read as drift (#317)

The #299 activation let a v6 return reach the database. Every consumer that
read it back then rejected it, because the freshness replay in
`pattern_evidence._v5_projection_freshness_reasons` cross-checked every
persisted `pattern_score` against `len(patterns) - len(antipatterns)` and
demanded an `int`. A weighted aggregate is a sum of 1.0/0.5/0.25 terms, so five
talks reprocessed under a fresh v6 claim validated, canonicalized, persisted
with `pattern_scoring_generation_status: "current"` — and came back
`pattern_score_projection_drift` plus `promoted_pattern_score_drift`, with
every other artifact, citation, coverage and outcome check passing.

That is worse than v6 never persisting. The four consumers gated on freshness
are the renderer, the scoring cohort, `queue-state normalize`, and the
post-batch baseline, so a full reparse wrote talks the profile could not read
and the normalizer requeued the talks it had just processed. The database was
never corrupt — the scores were arithmetically right under their own
`pattern_score_basis` — and nothing downstream would take them.

The replay now picks its arithmetic from the record's own
`pattern_scoring_schema_version`, exactly as `adherence_baseline` and
`opportunity_coverage_identity` already do. At the weighted generation it
recomputes the aggregate from the detection lanes' confidences, admits the
fraction, and recomputes `pattern_score_basis` from those same lanes rather
than trusting the stored one — a stored basis agreeing with a stored score
proves only that whoever wrote them agreed with themselves. A flat record keeps
the count difference and the integer requirement. A record whose stamp is
missing or malformed is replayed under neither: guessing the generation lets a
record match by coincidence and report as fresh.

Three reason codes join the set: `pattern_score_basis_projection_drift` (a
weighted record without its basis, a basis its lanes do not produce, or a flat
record carrying one — a v5 record with a basis and a v6 record without one are
both malformed), `pattern_detection_confidence_invalid` (no confidence, no
weight, no aggregate to compare against, so calling it score drift would name
the wrong defect), and `pattern_scoring_schema_version_unusable`, reusing the
code the wrapper already emits for the same condition.

`pattern_evidence` restates `DETECTION_WEIGHTS` because it sits below
`return_validation` in the import graph and cannot import its own consumer —
the same reason `adherence_baseline` restates the scoring version. A test pins
the two tables to each other, so a weight change landing in one file and not
the other fails CI instead of splitting the arithmetic in half.

### fix(vault-profile) — pattern trends accept a weighted cohort (#317)

Unblocking the cohort exposed the next consumer to demand an integer:
`classify-pattern-profile._talk_score` raised `pattern_score must be an
integer` on the first weighted talk, and `Fraction(sum(values), len(values))`
would not have averaged them anyway — the two-argument form takes integers
only. The classifier now reads the score under the generation its talk is
stamped with, and averages the trend window through `Fraction(str(value))`,
which is exact for a two-decimal weighted score and for a count difference
alike. An absent or malformed stamp still gets the flat contract: that refuses
a fraction rather than admitting one, so nothing is filed under arithmetic it
was not scored with.

## 0.20.80 — 2026-08-17

### fix(packaging) — the dimension registry now reaches consumers (#316)

`tessl install` materializes only `.md/.py/.sh/.txt/.json` and drops every
other extension in silence. Nothing in the toolchain says so: `tessl plugin
pack` includes the file, `tessl plugin publish` reports success, and `tessl
install --verbose` logs not one word about what it threw away.

So `_dimensions.yaml`, authored in #290, was never on a consumer's disk.
`audit-pattern-catalog.py` exited 1 with `dimension_registry_invalid` on every
clean install from 0.20.57 on — a hard stop in vault-ingress Step 1, which
meant no talk could be processed or reprocessed on the released plugin.

The registry now ships a byte-identical `_dimensions.yaml.txt` mirror and
`registry_path` reads it when the real file is absent. The real file still
wins when both exist, so a stale mirror can never shadow a dev-tree edit.

The diagnosis corrects the issue's premise twice over. The drop is not at
publish — the pack contains the file — it is at install. And it is not a
`.yaml` rule but an extension allowlist, which is the same mechanism that ate
`RunDeckOps.bas` and the eight `*.applescript` drivers in #85. That fix worked,
but `sync-deck-drivers.py` only ever guarded two extensions in one directory,
so a third extension in a different directory walked straight past it.

`scripts/check_shipped_extensions.py` is the repo-wide guard that closes the
class: every tracked file under the manifest's declared content whose extension
is outside the allowlist must carry a current mirror. It reports missing
mirrors, drifted mirrors, orphan mirrors whose source was deleted, and mirrors
not declared generated in `.gitattributes`, and runs in both `tests.yml` and
`pre-publish-checks.sh`. `check_package_contents.py` could not have caught this
— it tests `.tesslignore` stripping, which is a pack-stage concern, and the
loss happens a stage later.

The `.gitattributes` marking is enforced per file rather than trusted to a
glob, because a directory-scoped pattern is precisely what covered the deck
mirrors and missed `_dimensions.yaml.txt` beside them. Its patterns are now
path-globs across `skills/**` rather than one skill's `scripts/` directory.

Also `.DS_Store` is now ignored in both `.gitignore` and `.tesslignore`. Pack
reads the working tree rather than the git index, so five untracked ones were
riding along into the published package.

## 0.20.78 — 2026-08-14

### fix(vault-ingress) — a weighted score can now be stored and read back (#299)

#293 defined the weighted return and #308 got one through canonicalization. It
still could not land: every writer that touched a persisted `pattern_score`
demanded an integer, and a weighted aggregate is a sum of 1.0/0.5/0.25 terms.
A worker's return validated clean, canonicalized clean, and died at the merge.

`resolve_pattern_score` now takes the contract its generation declares.
`merge_talk` selects it from the return schema version, so a v6 return persists
its fraction. The cross-check moves with it: a bare weighted number is compared
against `expected_weighted_score`, not against count-minus-count, which for a
strong pattern and a weak antipattern is 0.75 rather than 0. The flat generation
still refuses a float — a float there means arithmetic other than the count
difference produced it.

The same split reaches the adherence baseline, and this is where it got
interesting. Converting only the cohort selector left `build_adherence_baseline`
admitting a fractional score into the cohort on one line and raising on it a few
lines later, in the same function. Every weighted baseline would have been
unbuildable, and the symptom is a population reported as too small rather than
a contract mismatch — the same half-converted path as #308, found this time by
pyright rather than by a reparse. The sum, the average, and
`validate_adherence_baseline` all key on the generation now.

`_require_number` returns its value rather than widening it to float. A weighted
score that happens to be whole is still that number, and coercing restated it as
`5.0` in divergence messages and stored `12.0` where the flat generation stores
`12`.

Coverage in `tests/test_weighted_score_persistence.py`: the writer-side
contract, the cohort and baseline read-back, and an end-to-end validate →
canonicalize → `merge_talk` pass, since the last two fixes each got a different
link in that chain wrong. Every test admitting a fraction at the weighted
generation has a sibling proving the flat generation still refuses one.

## 0.20.77 — 2026-08-14

### fix(catalog) — an entry evaluable from a transcript can now cite one

Eleven observable entries declared `transcript` in `evaluable_from` — ten of
them in `strong_evaluable_from` as well — while omitting `transcript` from
`evidence_channels`. `call-to-action` names a transcript as an evaluable source
three times and its `evidence_requirements` says "the spoken source must cover
the complete closing zone", then offers only `timed_transcript` and `video` to
cite one through.

A worker holding a plain transcript therefore had no legal citation, while
canonicalization still demanded an assessment because the applicability gate
read as complete. The two fields contradict each other, and the contradiction is
only visible across both, which is why nothing caught it.

Affected: `call-to-action`, `call-to-adventure`, `concrete-before-abstract`,
`delayed-self-introduction`, `guess-first`, `new-bliss`, `opening-punch`,
`retrieval-beat`, `shortchanged`, `sparkline`, `talklet`.

Only 3 of 215 talks carry a timing sidecar, so these entries were effectively
unscorable corpus-wide — recorded as "the speaker does not do this" rather than
"the catalog cannot see it". `guess-first` is the sharpest case: a twelve-round
commit-then-reveal quiz recorded as not evaluable.

A new catalog guard fails when any observable entry admits a transcript source
without a transcript channel, so the pairing cannot drift apart again.

Found by running the reparse (#309).

## 0.20.76 — 2026-08-14

### fix(vault-ingress) — a probe may run the interpreter the vault configures

`video_evidence` and `pdf_evidence` invoked their bounded workers without
`immutable_process_identity`, so the supervisor's sensitive-metadata guard saw
the trusted root inside the worker's own `argv[0]` and refused to start it:
`unsafe_worker_process_metadata` → `video_probe_start_failure` /
`pdf_probe_start_failure`.

The interpreter and the module's own path are fixed process identity, not
leaked secrets. Every PPTX worker already declared them as `command[:2]`; these
four call sites did not.

It fires whenever `config.python_path` lives inside the vault — the layout
`check-runtime` recommends and the live vault uses — which made every
`video_extracted` talk unpersistable. Found by running the reparse: batch 1
failed at persistence on the first talk.

## 0.20.75 — 2026-08-14

### fix(vault-ingress) — a v6 return canonicalizes like a v5 one (#299)

The activation admitted v6 to `CANONICALIZABLE_RETURN_SCHEMA_VERSIONS` and left
three `== EXHAUSTIVE_OUTCOME_RETURN_SCHEMA_VERSION` tests inside
`canonicalize_return_evidence`. A v6 return therefore reached canonicalization
and was read as pre-v5, which rejects the `applicability_assessments` its own
contract REQUIRES: `return schema v4 cannot carry applicability_assessments`.

v6 validated on the way in and died on the way to the database. Nothing caught
it because every canonicalization test built a v5 return — the equality tests
were only ever exercised at the one version that satisfied them.

`pattern_evidence` now carries `EXHAUSTIVE_OUTCOME_RETURN_SCHEMA_VERSIONS`,
mirroring the set of the same name in `return_validation`, and the three sites
test membership. Found by running the reparse: the first worker produced a
return that validated clean and could not be persisted.

## 0.20.74 — 2026-08-14

### fix(vault-ingress) — an invalid legacy manifest is warned about, not deadlocked on

`_validate_video_extraction_provenance` took a `severity` from its caller and
used it for an ABSENT manifest, then hardcoded `blocking` for an INVALID one.
Those are the same situation on a legacy record: `_artifact_severity` already
decides that a completed record with a usable repair lane reports actionable
work rather than deadlocking the repair that would fix it.

The asymmetry held the whole vault's reparse hostage to two pre-contract
(`schema_version: 0`) video manifests on talks already queued for reprocessing —
state the reparse itself regenerates. The invalid branch now uses the caller's
severity, like the absent branch beside it.

Live vault: blocking preflight findings 2 → 0.

## 0.20.73 — 2026-08-14

### feat(vault-ingress) — sever a binding nothing proved (#176)

The sweep could prove a binding wrong and nothing could act on the proof. A
binding is a pair — the catalog row's `talk_filename` and the talk's own
`pptx_path` — and `record_pptx` writes the talk side on a match and never
clears it.

`sever_pptx_talk_binding` is that writer. Both sides move together because
severing one is worse than severing neither: clearing only the catalog row
leaves the talk still naming the deck, and every reader that resolves slides
through `talks[].pptx_path` keeps drawing evidence from it, now with an audit
trail saying it was handled.

`sweep-pptx-talk-identity.py --emit-mutations` writes two plans. `mutation_plan`
severs the unproven bindings; `proof_plan` stores the assessment behind the
confirmed ones through `record_pptx`. Separate because keeping a binding and
breaking one are different owner decisions, and one file carrying both invites
applying half of what was reviewed.

Both plans carry exact-old-value preconditions on both sides, and those
preconditions found two defects in the live catalog that per-deck assessment
cannot see:

- **Two unproven rows naming one talk.** Two UberConf 2024 decks bind the same
  delivery, so the second sever would fail a precondition the first made false.
  The plan expects the missing marker for every sever after the first on a
  given talk.
- **Two confirmed rows claiming one talk.** `IJ Conference/2025/PDD.pptx` and
  `PDD for GS.pptx` both confirm `2025-03-20-ij-2025-prompt-driven.md`. Two
  decks cannot both be one talk's delivery deck; each is assessed alone and each
  agrees, so the contradiction is only visible across rows. Proving either would
  assert what the other disproves, so the plan proves neither and both stay
  blocking for owner review.

The talk side is cleared only when it names the deck being severed. A talk can
carry a `pptx_path` pointing at a correctly-bound deck while some other catalog
row wrongly claims it; clearing unconditionally destroyed that right binding
while removing the wrong one. On the live catalog this is five talk-side clears
that should never have happened.

Each plan is exactly the `{schema_version, mutations}` envelope
`mutate-tracking-database.py`'s `load_plan` accepts — it validates a CLOSED key
set, so a reporting key inside the envelope makes an otherwise healthy plan
un-applyable. `unseverable[]` sits beside the plans in the report, never inside
one.

`binding_unassessable` is severable too: "the assessment could not run" is the
strongest form of "not proven", and leaving those bound while the plan reads as
complete is the failure the plan exists to prevent. Rows the plan cannot address
are named in `unseverable[]` rather than skipped.

Every writer precondition is checked while BUILDING the plan — a nonempty
trimmed `pptx_path`, a talk some record actually carries — so a row that
survives is a row `mutate-tracking-database.py` accepts. A plan is a file a
human reviews and then runs; one that looks actionable and dies partway through
on a precondition the builder could have seen is worse than one that says up
front what it cannot address. `proof_plan` applies the same checks, because a
proof the owner writer would refuse is not a proof.

Rows resolve to their catalog record by INDEX, never by path. A row's
`pptx_path` is the deck-facts reading's normalized text — whitespace collapsed,
length-capped — so a stored path with internal double spaces would not match a
path-keyed lookup and would drop out of the plan without a word.

Measured end to end on a copy of the live database — sever, re-sweep, prove,
migrate — blocking preflight findings go **1550 → 4**: the two decks contesting
one talk, and two unrelated `video_extraction_provenance_invalid` findings.

## 0.20.72 — 2026-08-14

### feat(vault-ingress) — activate weighted scoring (#299)

#293 defined the weighted return contract and stopped: v6 validated but could
not reach the database. This is the activation, and it moves as one change
because `queue-state.py` asserts the claim, queue-claim, and return schema
versions equal at import time — staged separately, the module does not load.

Advanced together: `RETURN_SCHEMA_VERSION`, `QUEUE_CLAIM_SCHEMA_VERSION`,
`CURRENT_QUEUE_CLAIM_SCHEMA_VERSION`, `PATTERN_SCORING_SCHEMA_VERSION`,
`CURRENT_PATTERN_SCORING_SCHEMA_VERSION`, and `TALK_RECORD_SCHEMA_VERSION`,
plus v6 joining `CANONICALIZABLE_RETURN_SCHEMA_VERSIONS`.

**The current-version pointers are derived, not written.** `RETURN_SCHEMA_VERSION`
is now `WEIGHTED_SCORE_RETURN_SCHEMA_VERSION` and `PATTERN_SCORING_SCHEMA_VERSION`
is `WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION`, with
`EXHAUSTIVE_OUTCOME_RETURN_SCHEMA_VERSION` and
`FLAT_PATTERN_SCORING_SCHEMA_VERSION` naming v5 for the sets that mean v5. The
four generation sets named v5 *through the current-version pointer*, so bumping
it would have dropped v5 out of `SUPPORTED_RETURN_SCHEMA_VERSIONS`,
`SNAPSHOT_*`, `OUTCOME_GATE_*` and `SOURCE_LOCATED_*` — a validator that
silently stops accepting the generation it accepted yesterday.

**A production defect the bump exposed.** `queue_claim_contract` chose the
expected adherence-baseline schema with
`version == CURRENT_QUEUE_CLAIM_SCHEMA_VERSION`. Advancing the claim schema
therefore demanded the *legacy* baseline of every already-stored v5 claim and
rejected the lot. The rule now keys on
`OPPORTUNITY_QUEUE_CLAIM_SCHEMA_VERSION`, the generation that introduced
baseline v2, so it belongs to that generation and every later one.

**The migration restamps; it never rescores.** `_restamp_talk_records` moves a
v5 record to the v6 shape and leaves `pattern_scoring_schema_version` alone.
Computing a basis from stored detections would recompute a score under
arithmetic its worker never used — the reinterpretation `_validate_score`
refuses on the way in. The talk keeps the truth about its own number, the
cohort selector excludes it as a generation mismatch, and it requeues. That is
the reparse, made mechanical rather than remembered. Without the restamp the
bump alone would lock the database: the owner writer requires the exact current
talk schema before any mutation.

Measured on the live vault: 6 talks restamp v5→v6; the other 209 are schema v1
and stay v1, as they already did. No talk carries a scoring-generation stamp at
all, so the whole corpus requeues on generation grounds regardless.

The canonicalizer emits `pattern_score_basis` for a weighted return,
recomputed from the canonical detection lanes rather than copied from the
return. Without it a v6 return canonicalized to the v5 field set, and the
fractional score it carries is rejected at that shape — v6 that validates and
cannot be stored.

`migrate_tracking_database`'s root-v1 branch derives `changed` from every record
count instead of a hand-listed subset. A flag that names the collections it
knows about goes stale the moment a migration touches one it does not, and a
caller trusting it skips persisting a migration that already rewrote the records
it was handed.

`SKILL.md`, `schemas-db.md`, `queue-selection.md`, and
`subagent-instructions.md` describe v6: a contract the docs still call v5 sends
workers to emit returns that fresh v6 claims reject.

Test fixtures that pinned version literals now derive them. Several had gone
silently wrong rather than loudly stale — `_write_db` in the queue tests
enriched only talks stamped at the literal 5, so at any other generation it
skipped them and they failed a later opportunity-identity check as though the
fixture had never been valid.

## 0.20.71 — 2026-08-14

### feat(vault-ingress) — a score is only as current as the block it came from (#167)

#285 classified persisted pattern observations, #286 made preflight block on
them, and #294 made the migration repair or requeue them. Everything downstream
of a claim still scored whatever the database said. A talk's `pattern_score` is
computed FROM its observations, so a current generation stamp over a
structurally invalid block is a number derived from a shape nothing validated —
and 78 of the live vault's 80 processed talks carry exactly that after the
#290/#292 dimension remap.

The gate goes in `partition_pattern_scoring_cohort`, not in each consumer. That
function is the one authority the queue and the profile already share, so
`persisted_observations_invalid` excludes a talk from the scoring cohort and
requeues it in the same act. Two rules would drift, and the direction they
drift is a profile scoring a talk the queue already called unusable.

What that reaches, through one change:

- `queue-state.py normalize` requeues with
  `pattern_scoring_generation:persisted_observations_invalid`
- `persist-results.py`'s post-batch cohort, which spans talks merged under
  older contracts as well as the ones this run validated
- `queue-state.py claim`'s preclaim baseline
- every profile surface, since `load-vault.py`, `validate-profile.py`, and
  Section 15's `section15_pattern_history.py` all build through
  `build_current_pattern_snapshot`

Required at `OBSERVATION_BOUND_SCORING_SCHEMA_VERSION` (5, the active
generation) rather than optional. An assessor a caller may forget is a gate
that reads "nothing to check" exactly when nobody wired it — the same fail-open
shape the evidence-freshness assessor was made required to avoid at v4.

The adapter turning an assessment into reason codes lives in
`persisted_pattern_observations.persisted_observation_assessor`, beside the
classifier. Three callers need it, and three copies of "usable means empty" is
three chances to invert it.

An archival finding is not a defect. An entry the catalog no longer observes is
a catalog move, and requeueing every talk that ever cited one would requeue the
whole vault forever.

Stale evidence is still reported ahead of invalid observations when a talk has
both: an artifact that moved is what an owner repairs first, and the claim
contract admits one ordered reason sequence per exclusion, not two.

## 0.20.70 — 2026-08-13

### feat(vault-ingress) — assess the bindings that predate the assessment (#176)

`_apply_record_pptx` refuses a new talk binding nothing proved, and preflight
blocks a catalog row whose binding is unproven. Neither could say anything about
the rows already stored: the live vault's 82 catalog rows are all schema v1, its
74 bound rows carry no `identity_assessment` at all, and migration deliberately
leaves v1 rows alone rather than inventing one. So every one of them blocks, and
nothing in the toolkit could tell a correct binding from a wrong one.

`skills/vault-ingress/scripts/sweep-pptx-talk-identity.py` is the catalog-wide
assessment. It runs every row against every talk in the vault and reports one
disposition each — `binding_confirmed`, `binding_contradicted`,
`binding_review_required`, `binding_unproven`, `unbound_row`. Read-only: a
disposition is evidence for an owner decision, never a decision.

`skills/vault-ingress/scripts/pptx_deck_facts.py` is the observer it needed.
`pptx_talk_identity` decides from facts someone else gathered, and no one
gathered them for a deck already on disk. It reads `docProps/core.xml`,
`docProps/app.xml`, and the title slide out of the OPC package — stdlib only,
bounded per part, and never fatal, so a damaged deck is still assessed from its
path rather than skipped.

Only the title slide supplies rendered text, and that is load-bearing. Feeding
in `app.xml`'s full slide-title list instead made 69 of the live vault's 74
bound decks `identity_ambiguous_candidates`: a deck that mentions another talk's
title on an interior slide agrees with that talk, and a deck agreeing with
everything is indistinguishable from one carrying no evidence. Measured, not
reasoned about.

Which part IS the title slide comes from `ppt/presentation.xml`'s `sldIdLst`
resolved through the presentation's relationships — never from the part name
`ppt/slides/slide1.xml`. OPC leaves slide order to that list, so a reordered
deck can hold an interior slide in `slide1.xml`, and reading it would feed
interior text in as the deck's own title: the same defect the title-slide rule
exists to avoid, arriving by a different door. When the chain cannot be
resolved no slide is opened at all, and `app.xml`'s slide-title list — which is
already in presentation order — supplies the title instead. Guessing a part
name is what this replaced.

Against the live vault the sweep resolves 30 bindings, contradicts 7, and leaves
37 for review. The 7 are real: `UberConf/2023/DevOps Reframed.pptx` was bound to
a BaselOne talk, `Devoxx/Ukraine/2023/DPE with LLM.pptx` to a 2024 Devoxx one,
and `DeveloperWeek/CA 2024/Sadogursky, Baruch, Fri.pptx` — same venue, same day
as the talk it was bound to, so only the deck's own title slide could tell them
apart — to the wrong one of two Developer Week 2024 talks.

The candidate table is serialized down to material candidates. 215 talks against
82 rows means a row's table is mostly six-`unknown` verdicts, and emitting those
buries the handful that decided the verdict. Every candidate that could have
contested the winner had to agree with something, so it survives the trim; a
test asserts the trimmed assessment still satisfies `binding_refusal`.

`pptx_catalog_selection._open_contained` becomes `open_contained_descriptor`,
public in its owner module, so the deck reader shares one containment rule with
the evidence classifier rather than copying it. The sweep must not be able to
read a file the classifier would have refused.

An absent or blank `config.pptx_source_dir` falls back to the vault root, as
`schemas-db.md` documents. Passing the absent value through would report every
deck in such a vault unreadable — a configuration default read as universal
damage, putting every binding into `binding_unproven` on evidence nobody
looked for.

The published-PDF signal is not observed. The vault's talk-referenced PDFs live
under the vault's own `slides/`, never beside a deck, so no deterministic
deck-to-PDF binding exists to read — and guessing one would manufacture exactly
the evidence this contract exists to require. The signal stays covered by a
contract regression so a future producer inherits it.

Carries this issue's synthetic regressions: same-title decks across venues and
years, unrelated decks in nearby directories, master/static pairs with different
slide counts, and a published PDF that disambiguates two candidates.

## 0.20.69 — 2026-08-13

### docs — the guardrail rule references the contract instead of repeating it

`rules/guardrail-rules.md` had grown a copy of the prose scan's invocation,
suppression, classification, and absent-scanner steps, which
`phase4-guardrails.md` already carries. Rules state the contract; skills carry
the executable form, and two copies of one contract drift.

Also renames `test_a_high_finding_alone_leaves_pass` — its assertion is that a
single high finding does NOT leave PASS, so the name said the opposite of the
test.

### feat(presentation-creator) — defer the prose scan to blog-writer (#287)

Every prose surface this workflow produces — speaker notes, the abstract, section
descriptions, the outline's connective text — is LLM-drafted, and LLM prose has
tells. Nothing checked for them.

Guardrail 14 does, by delegating to `Skill(skill: "blog-writer")`, which owns the
AI-writing-pattern catalog. It is not reimplemented here: a partial copy drifts
from the catalog blog-writer maintains and then reports confident findings from a
stale one. When the skill is absent the check reports SKIP and points the author
at `tessl install jbaruch/blog-writer` rather than approximating it — which is
also what the CFP abstract check now does, where it previously skipped in silence.

`classify-prose-scan.py` owns the PASS/WARN/FAIL mapping. It is a total function
of two integers, and a threshold sentence in skill prose drifts from the one
anybody actually applies. `--unavailable` emits the SKIP report with the install
command, so an absent scanner is never mistaken for clean prose.

Order is part of the contract: voice-matching findings are suppressed before the
counts are taken, so a speaker's own register never drives the status.

Findings flag, never rewrite. A pattern the scan calls a tell may be the
speaker's deliberate voice, so vault-documented voice traits are suppressed: a
speaker whose profile shows heavy em-dash use is writing in their own register.

Closes #287. The unlanded `skills/humanizer/` branch was an early copy of
blog-writer's detector; deferring to the original beats maintaining a fork of it.

### feat(vault-ingress) — weight the aggregate score, versioned not retrofitted (#153)

Implements the #153 aggregate-score decision. `DETECTION_WEIGHTS` are
`{strong: 1.0, moderate: 0.5, weak: 0.25}`, and every weighted score carries a
required `pattern_score_basis` with per-lane confidence counts, the applied
weights, and the `not_evaluable` count. Flat `+1/-1` counting made a slides-only
talk and a full-evidence talk emit scores that read as equivalent, which was the
issue's original complaint. The `weak` weight is an owner decision taken with
this work: `CONFIDENCE_LEVELS` admits `weak`, so the table had to be total.

**Weighting is a v6 return contract, not a reinterpretation of v5.** A v5 return
was produced by a worker counting `+1/-1`; rescoring it under the weight table
would restate what that worker meant rather than validate what it said. Each
schema is checked against the arithmetic in force when it was written, so a v5
return carrying a `pattern_score_basis` is rejected outright.

v6 keeps every v5 semantic and joins each version set v5 belongs to. Its
`pattern_observations` gains `pattern_score_basis` on the return, and the
validator checks the basis object's types before comparing its values — Python
equality makes `True == 1` and `6.0 == 6`, so a boolean lane count or a float
schema version would otherwise pass. The supplied score is compared exactly
rather than rounded: `expected_weighted_score` already rounds the canonical
result, so rounding the untrusted value too admitted `1.504` as `1.5`.

A v6 adherence comparison restates the block's own score, so it takes that
generation's type — finite and possibly fractional under weighted arithmetic,
integer under a count difference. Requiring an integer of both would have
rejected every valid weighted return reporting a comparison, which would mean v6
did not retain the v5 adherence contract it inherits.

**Not yet persisted.** v6 validates and nothing further. Persisting a weighted
score is a new talk-record shape, and `mutate-tracking-database` requires the
exact current talk schema before any mutation — so admitting it alone would leave
every stored talk unmutatable until a migration restamped it. Persistence, the
talk schema bump, the claim contract, and the migration advance together in one
activation change, alongside the reparse.

`PATTERN_SCORING_SCHEMA_VERSION` stays 5. `scoring_schema_version_for_return`
records which generation a return's score belongs to, so that change has the rule
ready: weighted and flat scores are not comparable and must not share a cohort.

**Migration.** None. Weights are part of the scoring schema version, so changing
one is a generation bump rather than a tuning knob.

### fix(vault-ingress) — an old block is old, not corrupt (#167)

The persisted-observation classifier reported a block carrying both detection
lanes but no `not_evaluable` as `detection_collection_absent` — the same code it
uses for a writer that stopped halfway.

That shape is what the writer emitted before exhaustive outcomes existed, and it
is the live vault's dominant state: all 80 talks claiming completed analysis are
in it. Reporting them as corrupt sends the owner hunting for damage in records
that are merely old.

They now classify as `outcome_collection_predates_contract`, which stays blocking
— the evidence still is not current and the reparse is still required — but names
the cause and the remedy. The older-generation reading requires both detection
lanes to be well-formed containers, so neither an unfinished writer nor a
block holding a malformed lane can launder itself as a legacy record.

### feat(vault-profile) — the denominator behind a never-used claim (#160)

Part of #160 section 3, implementing the #153 null-absence-gate decision.

`absence_evaluable_from: null` means absence is not provable for that pattern and
never falls back to the presence gate, so never-used and underused are computed
over the populated-gate entries only. Against the live catalog that is **16 of 81
observable entries** — 65 are unknowable. Without that denominator beside it, a
short never-used list reads as a statement about the speaker when it is mostly a
statement about coverage. `absence_provability` reports both counts plus the
observable total, computed from the catalog rather than hardcoded, so populating
a gate moves the numbers instead of dating a constant. An unobservable entry
lands in neither count: it is not scored at all, so it belongs to no denominator.

`classify-pattern-profile.py` emits it beside `never_used_patterns`, so the list
and its denominator always travel together.

**The version boundary.** The classification contract bumps to **v2** to carry
the field, since this is a shape change to a persisted artifact. Presence follows
that generation rather than the outer v5 contract: required at classification v2,
forbidden at v1 and on the v4 contract, which carries no classification block at
all. A v1 block that omits it stays readable — the counts are a fact about the
catalog, not a claim the older block got anything wrong, and refusing v1 outright
would strand every profile on disk to gain nothing. A v1 block that *carries* it
is rejected: the stamp and the payload disagree. The schema reference states the
output contract and points at `_validate_absence_provability` for the predicate
rather than restating it, so the two cannot drift.

A v1 block is nonetheless a superseded classification generation, so a reader
takes the no-usable-prior-state path on it — every derived domain is withheld and
the assessment carries `pattern_classification_schema_superseded`, distinct from
`pattern_classification_policy_unavailable`, which marks a v4 contract that never
had a policy stamp. Nothing upgrades the block in place; vault-profile
regenerates the profile wholesale, so the next owner run replaces it. Occurrence
rows stay readable across the boundary — they belong to the pattern-profile
contract, not to the classification generation.

**What the reader checks.** Allowlisting a field without checking it is how a
malformed object reaches a reader that believes the shape was verified, and a
wrong count here misreports coverage as speaker behaviour — the exact confusion
the field exists to prevent. So: exact field set; nonnegative integer counts with
booleans excluded; a type-checked `schema_version`, since Python's `True == 1`
would otherwise admit a boolean stamp; the sum invariant; and the counts
recomputed from the active catalog. `1 + 2 = 3` sums perfectly and describes a
three-entry catalog nobody has, so internal consistency alone would let a
fabricated denominator present as current coverage — including a correct total
split the wrong way, since the split is the whole point.

`_PATTERN_HISTORY_KEYS` in `validate-profile.py` learned the field too. That set
keeps catalog-derived history inside `pattern_profile`, and a field the writer
emits but the set never learned about could sit duplicated under
`rhetoric_defaults` unchallenged. A regression derives its expectation from what
the writer actually emits, so the next omission fails in the suite rather than in
a profile.

**On the tests.** Review found the first revision comparing the outer contract
version (4 or 5) against a classification floor of 2, so the gate admitted every
block it existed to reject. That defect survived because the tests called the
private validator and supplied the version by hand — a shape the real call path
cannot produce. They run through `assess_pattern_profile` now, and both
version-gate cases fail against the original code. The writer's coverage moved
off `inspect.getsource` for the same reason: matching a call expression in source
text passes for code that never runs and fails for a correct refactor. The floor
is pinned to the generation that introduced the field rather than to the current
one, so a later classification bump does not start rejecting version 2.

### test — assert the lint gate's outcome, not tessl's wording (#265)

`test_an_over_length_description_fails_the_gate` matched the literal string
`Frontmatter validation failed`. tessl 0.96.0 phrases the same rejection as
`SKILL.md frontmatter field "description" must be at most 1024 characters.`, so
the test failed locally while the gate it covers worked correctly.

Three PR bodies carried this as a pre-existing environmental failure. It was
neither: CI passed only because its pinned tessl still emitted the old wording,
so the next bump would have broken the gate's own test there too.

The assertion now names the outcome and the offending skill — the gate failed
and the error identifies `demo` — rather than any sentence the external tool
happened to phrase it with. Matching the new wording would only have swapped
which CLI version it broke on; the two truncate the message at different points.
The old wording stays covered by the fake-CLI classification test, which owns a
captured transcript rather than a live tool.

### feat(vault-ingress) — refuse a talk binding nothing proved (#176)

The candidate table's `signals` map is the evidence; `agreeing` and `conflicting`
are its summary. The gate read the summary and trusted it, so a fabricated
candidate could claim `agreeing: ["venue"]` over a signal map where venue
conflicts, or carries no venue reading at all — and authorize the binding on a
standing its own readings never supported.

`derive_candidate_standing` is now the single rule, used by the producer that
writes a candidate and by the owner gate that reads one back. The gate validates
the complete signal map and recomputes both arrays from it, refusing on
`identity_candidate_signals_invalid` or
`identity_candidate_standing_contradicts_signals`. That also makes
`identity_candidate_agreement_not_selecting` unreachable: the derivation admits
only selecting signals to `agreeing`, so the state it named cannot be
represented.

`schemas-db.md`'s matched example carried `candidates: []` — a record the new
writer rejects outright, so the schema reference was telling agents to build
mutations that cannot persist. It now shows a complete selectable candidate,
including the non-selecting `delivery_year` and `filename_similarity` readings
that report without electing. Two tests parse that example straight out of the
reference and run it through the gate, so the document cannot drift from the
contract again.

Part of #176.

The assessment landed with no caller. `pptx_catalog` records advance to v3,
where a matched record carries the assessment that proves its deck belongs to
the talk it names, and `record_pptx` refuses to persist one that does not.

Four things must hold together, and checking fewer is checking none: the
verdict is `matched`, the assessment is about this record's deck, it names this
record's talk, and the artifact is a delivery deck. A `review_required` verdict
naming the right talk is still an owner decision nobody has made yet, so it
cannot bind either.

Both endpoints are checked because an assessment binds a pair. Verifying the
talk alone leaves the deck free: a real, correctly-decided assessment for deck A
pasted onto deck B's record would pass every other check and bind B's contents
to A's talk — the same defect running the other way.

Readers accept v1, v2, and v3, and check v3 shape only — the field is null
exactly when `talk_filename` is null. The binding's semantics stay the writer's
gate, matching how `visual_evidence` is already handled: a malformed receipt is
per-record trouble for a reader, but a record that cannot be proven is a record
that must not be persisted.

Existing v2 records migrate rather than linger. Migration cannot prove a binding
it did not witness, and forging a `matched` verdict would manufacture exactly the
evidence v3 exists to require — so a v2 record upgrades carrying a
`review_required` assessment with reason `identity_unassessed_legacy_binding`.
The binding survives; only its provenance is marked unproven, and nothing
downstream may treat it as current until someone looks. v1 records stay at v1,
matching the established position that migration preserves such a record rather
than inventing a binding for it.

Preflight consumes the stamp, which is what keeps it from being inert. Every
unproven binding blocks, the migration's own stamp included. A warning would let
Step 1's blocking-only gate proceed on state the database itself marks unproven,
which is the whole failure this exists to stop.

The cost is real and deliberate: **a vault carrying legacy catalog rows stays
blocked until those rows are assessed.** That makes assessing them reparse
prerequisite work rather than something to discover mid-run.

One predicate decides whether an assessment authorizes a binding —
`binding_refusal` — and both the writer and preflight call it. Two copies would
drift, and the direction they drift is a reader trusting what a writer would
have refused. It checks the evidence, not just the verdict: a `matched` verdict
over an empty candidate table is a conclusion with nothing under it, so the
table must show the talk winning the way the assessor makes it win —
corroborated by a selecting signal, contradicted by none, with no rival equally
corroborated.

Identity is deliberately not currency. A row can hold a perfectly current
extraction receipt for the wrong talk, so none of this touches
`classify_pptx_visual_evidence` — a wrong binding is not stale evidence, it is
evidence filed against the wrong talk, and conflating them would send every
migrated deck back through extraction to fix a problem extraction cannot fix.

Fixing that also closed a bypass: `migrate_tracking_database` returned early
whenever the database ROOT was current, which is true of every live database. A
record-level shape bump would have been skipped for all of them. Record
migrations now run before that check, and only a genuinely unchanged database
takes the no-op path.

### feat(vault-ingress) — migration repairs or requeues, never stamps (#167)

Closes the migration-integration half of #167.

`#147` migration stamped a talk as current record schema without ever reading
its nested detection objects, so a block with `evidence` and `dimensions`
swapped, an unknown pattern id, or a missing dimensions array became "current"
on the strength of its container's shape. The classifier that finds those
landed in #285 and preflight consumed it in #286; migration still did not.

`migrate-tracking-database.py` now gates every talk claiming completed analysis,
between the stamp and the write. Two outcomes, and no third:

- an exact inverse-schema swap is undone in place, because both original values
  live in the repair record and putting them back is reversible;
- everything else keeps its original bytes and goes back on the queue with
  `reprocess_reason: persisted_observation_invalid`.

A repair counts only when re-assessment says the block it produced would have
passed on its own — a talk can carry a repairable swap AND an unrelated defect,
and the repair fixes only the swap. The report gains a `persisted_observations`
object with both counts, since a silent repair is indistinguishable from no
corruption at all.

The analysis writer now fails closed on the same classifier. Rendering is where
persisted corruption becomes a document a human reads and a profile aggregates,
so a block the classifier calls unusable no longer reaches it.

That gate could only land after the repair path. Wired before it, it failed
closed on every legacy talk at once — the block was corrupt and nothing existed
to repair or requeue it, so no analysis could be re-rendered until each was fixed
by hand. It is scoped to source-located returns: a legacy return predates the
detection contract, and judging one against it would refuse a render for
breaking a rule that did not exist when it was written.

A talk with no observation block is skipped. Absence is incompleteness, not
corruption — the boundary preflight already draws, and requeueing every talk
that predates pattern scoring would flood a queue that is working.
### ci — renew the Chocolatey ffmpeg pin

`main` went red with no source change: `choco install ffmpeg --version=8.1.2`
stopped resolving because the Chocolatey feed withdrew that version. A re-run
cannot fix a pin that no longer exists.

The pin moves to 9.0.0, the feed's current version. Renewal is manual — no
Dependabot ecosystem covers Chocolatey — so the step's comment states the
cadence and the trigger: check the feed whenever this fails to resolve, or
quarterly, whichever comes first. Chocolatey serves only the current version, so
expect to renew again.

Renewing exposed a second assumption: the step hardcoded
`tools\ffmpeg\bin\ffprobe.exe`, and the newer package moved it, so the install
succeeded and the very next line threw. The step now searches the package tree
for the real binary and verifies ffmpeg.exe sits beside it, with failure
messages that name the fix.

The macOS lane keeps its pin: evermeet.cx serves immutable archives and each is
checksum-verified, so that pin still resolves and still proves what it fetched.

### fix(catalog) — resolve the last three dimension labels (#156)

Closes #156.

The remap left three labels unresolved because no owner had approved a mapping
for them, so each preserved the number written beside it and the auditor kept
reporting it. All three are now decided:

- `Visual Storytelling` → D13. `_anti_photomaniac`'s failure is in how images
  are chosen and composed, which is slide design.
- `Content Depth / Value` → D14. Polish outrunning substance is an
  overall-impression judgement, not a slide-to-speech mismatch.
- `Overall Quality Indicators` → D14, joining `Overall Impression/Polish` in the
  lane it already shares. No number changes.

Two prose claims and two entries' frontmatter moved; four index rows followed.
The catalog auditor now reports **0 errors and 0 semantic debts** — the first
time both have been clean since the dimension contract was written.
## 0.20.58 — 2026-08-12

### feat(catalog) — remap the dimension numbers to what the prose says (#156)

Closes the mechanical half of #156.

`vault_dimensions` is a list of bare integers, so a range check was the only
validation a number could carry — and a range check cannot tell that `4` means
Audience Interaction while the prose beside it says humor. Entries filed
evidence under dimensions they are not about, and every downstream aggregation
inherited it.

Per the 2026-08-09 owner decision the prose is the intent of record, so
`_dimensions.yaml` makes the labels resolvable and the numbers follow them. 42
prose claims and 38 entries' frontmatter were remapped; the index's per-entry
column and reverse map are regenerated from the approved frontmatter rather than
maintained by hand. The catalog auditor reports 0 errors, down from 37 semantic
debts of the drift kind; the 11 debts it now reports are the unresolved-label
findings the newly-wired registry check surfaces, listed below. Both worked examples in the issue land exactly as specified:
`progressive-reveal` becomes `[3, 13]` and `three-part-close` becomes `[2, 6]`.

No pattern's meaning changes. This is a renumbering, not a re-classification.

`audit-pattern-catalog.py` enforces the registry, so this is a deterministic
gate rather than a one-time script run. A prose label that resolves to a
different number than its claim states is an ERROR — two things the entry itself
asserts disagree. A label the registry cannot resolve is a semantic DEBT, since
turning an unreviewed alias into a build break would be the wrong lever and
resolving it by guess would make this an automatic renumbering. A malformed
registry is an error: without it every dimension claim becomes uncheckable.

A label with no owner-approved alias does not resolve, and an unresolved claim
KEEPS the number written beside it — preserved, not endorsed. Dropping a
membership on the strength of a missing alias would be a bigger change than the
drift being fixed. Three labels remain unresolved and need an owner decision:
`Content Depth / Value`, `Overall Quality Indicators`, and `Visual Storytelling`.

The catalog fingerprint moves, so this belongs in the same revalidation pass as
#167 rather than triggering a second one.

## 0.20.57 — 2026-08-12

### fix(catalog) — one bullet threshold, not two (#153)

`_anti_bullet-riddled-corpse` disagreed with itself. Line 56 counted slides with
"three or more text bullets" toward the bullet-slide proportion, while line 59
set the strong signal at four or more and line 60 excluded "a compact list of
three or fewer short items" from standalone signals. A three-bullet slide was
simultaneously counted and excluded, so every reader had to learn which number
applied where.

Per the 2026-08-09 owner decision it is four or more, everywhere in the entry. A
three-bullet slide is never antipattern evidence — not standalone, and not
toward the proportion.

The catalog fingerprint moves, so this belongs in the same revalidation pass as
#156 and #167.

Still open on #153: the weighted aggregate score (strong 1.0, moderate 0.5) and
its `pattern_score_basis` sibling. Runtime scoring is still flat +1/-1 in
`return_validation._validate_score`; changing it is a scoring-schema bump that
lands with #160's provenance object.

## 0.20.56 — 2026-08-11

### feat(vault-ingress) — prove which talk a deck belongs to before it becomes evidence (#176)

Part of #176.

`pptx_catalog` would bind a talk to any syntactically valid deck. Everything
that guards deck evidence runs after that binding, so a deck attached to the
wrong talk fed it slide counts, design evidence, OCR, and pattern observations
with nothing downstream able to notice. The read-only audit found 25 stored
catalog/talk path disagreements across 15 talks and nine unrelated decks
assigned to a single talk.

`pptx_talk_identity.py` assesses the binding instead of assuming it, from facts
both sides already carry: the catalog's title, conference, and delivery date
against the deck's path, document properties, and rendered title, footer, and
hashtag text. Title and event comparison delegate to `source_identity_matching`
— the same authority the video source-identity audit uses — so a deck cannot be
matched by a weaker rule than a recording.

Two signals report but never elect. Filename similarity is excluded because
reused talk families produce near-identical filenames, which is what mis-assigned
these decks in the first place. Delivery year is excluded because every talk
delivered that year satisfies it equally — it narrows a candidate set without
identifying anything in it. A year MISmatch still contradicts: vetoing and
electing are separate powers, and a wrong year proves the wrong delivery while a
right year proves nothing.

A directory counts as a venue claim only when it names an event some talk in the
vault actually uses. Without that vocabulary gate every generic folder —
`Decks/`, `Downloads/` — parses as an unrecognized venue and contradicts every
candidate, turning the discriminator into a blanket refusal.

Ambiguity is a review finding, never a silent choice. Two corroborated
candidates, a contradicted one, and a filename-only hit all route to
`review_required`, and a master, backup, or static export never carries a bare
`matched` verdict into persistence.

This is the assessment only; wiring it into the apply path and preflight
follows. Sequenced before the reparse — repairing observations derived from a
mis-assigned deck is careful work on the wrong deck.

## 0.20.55 — 2026-08-11

### feat(vault-ingress) — block a corrupt persisted block before anything claims the talk (#167)

Part of #167.

The classifier landed with no caller. Preflight now runs it on every talk whose
status claims analysis, so the swapped-field signature, an unknown pattern ID, a
polarity-inverted lane, or a missing one is a blocking finding before a claim
rather than a surprise in a rendered analysis.

Two cases are deliberately not blocking. A detection of an entry the catalog no
longer observes warns: the catalog moved, the record did not, and a cohort can
exclude it without the talk being wrong. And a talk carrying no block at all is
skipped entirely — absence is incompleteness, not corruption, and whether an
unscored talk belongs in a cohort is the scoring-generation fields' question,
not this gate's. Blocking, or even warning on, every talk that predates pattern
scoring would flood a queue that is working.

Each finding names the field a repair would edit. A root-level finding already
names the block and a lane finding is relative to it, so prefixing both produced
`pattern_observations.pattern_observations` — a path pointing at a field that
does not exist.

## 0.20.54 — 2026-08-11

### feat(vault-ingress) — classify what is already stored, not just what arrives (#167)

Part of #167.

Return validation guards what a subagent hands in. Nothing guarded what was
already persisted, and the live vault shows why that matters: across 209 talks
and 5,222 detection objects, `pattern_observations` is a dict on 119 talks, a
legacy list on 81, and absent on 9; 28 detections in one talk have `evidence`
and `dimensions` swapped; 1,129 carry legacy or missing dimension arrays; 3 name
IDs no catalog entry claims; and 641 reference entries since marked
`observable: false`. A record-schema migration stamps any of those as current
without ever looking inside the nested block, so the corruption survives into
rendered analyses and derived profile state.

`persisted_pattern_observations.py` is the read-only classifier the migration,
preflight, rendering, profile, and queue paths will share. It reports stable
reason codes for the container shape, the detection object, and the dimensions
array, and it separates the cases by what an owner can actually do about them:

- order-only drift is mechanical but still reported — the catalog owns the order
- membership drift is a semantic claim, routed to the #156 catalog review and
  never auto-mapped
- an unknown ID is an owner decision about what the observation meant, never a
  spelling correction to a near neighbour
- a detection of an entry the catalog no longer observes is archival, not
  malformed: reported so a caller can exclude it from the current cohort,
  without making the talk unusable

Two things the record cannot leave unsaid. A current block carries every lane
the canonical writer emits, so an absent `patterns_detected`,
`antipatterns_detected`, or `not_evaluable` is a writer that never finished
rather than a leaner block — reading an absent lane as an empty one reported
`{}` as clean current evidence. And the lane is itself the claim: a catalog
`pattern` filed under `antipatterns_detected` inverts what the record says the
speaker did, and no field inside the detection says otherwise.

One defect is losslessly repairable: the exact inverse field swap, where
`evidence` holds a valid dimensions array and `dimensions` holds the evidence
text. The repair carries both original values, so applying it is a swap rather
than a reconstruction, and it refuses a target that moved since it was assessed.
Every other case stays a review or reparse finding. A half-swap — a malformed
list on one side — is two defects, not a repair: guessing at one side would
destroy the other.

The classifier is a pure function of (talk, catalog) with no filesystem, clock,
or network. Wiring it into migration, preflight, the writers, and queue
normalization is the rest of #167.

## 0.20.53 — 2026-08-11

### ci — fail the build on a committed conflict marker (#272)

Closes #272.

A diff3 base marker (`||||||| <sha>`) survived a merge resolution and was
committed to `CHANGELOG.md`, which ships in the plugin package. Nothing caught
it: `ruff` does not read Markdown, and `git diff --check` only inspects the
working diff, so a marker that is already committed passes silently. The
resolution had stripped `<<<<<<<`, `=======`, and `>>>>>>>`;
`merge.conflictStyle = diff3` adds a fourth, and the leftover line does not
start with `#`, so a heading-level review of the diff never saw it.

`scripts/check_conflict_markers.py` scans every tracked text file for all four
forms and fails the `lint` job and the publish run. Binary files are counted and
skipped — a marker is a line of text, and the repo's binaries are eval fixtures.

Marker length comes from each path's own `conflict-marker-size` attribute rather
than a hardcoded seven: git writes markers at the configured length, so a repo
that raises it for a file full of `=======` lines still gets real markers, just
longer ones. Matching the exact configured length — never "seven or more" —
keeps a here-doc delimiter and a long rule legal, since those run to arbitrary
lengths and a marker does not.

The separator is the one marker ordinary prose also writes: a Markdown setext
heading rule of exactly the marker length is byte-identical to it. Flagging it
outright would fail the build on legitimate content, so it counts only between a
start marker and its end marker, where a heading rule cannot be. The start, base,
and end markers are unambiguous and always count.

A tracked file missing from the working tree is read from the index instead of
skipped: an unstaged deletion must not buy a clean scan of a file the gate never
read, and the staged blob is what a commit would ship.

No exclusion list: the tests build markers from repeated characters rather than
writing them out, so the suite is not its own violation.

## 0.20.52 — 2026-08-11

### test(vault-ingress) — assert the probe's promise, not the allocator's (#277)

Closes #277.

`test_same_size_replacement_invalidates_cached_probe` failed once in a local
full-suite run and passed every time it was run alone. Its first assertion
required the replacement's inode to differ from the original's — an allocation
outcome the test does not control, and a claim about the filesystem rather than
about the probe.

The test now asserts what the probe promises: after a same-size replacement, the
second probe reports the replacement's SHA-256 and the same byte count. A cache
that served the stale entry fails that digest assertion, so the defect worth
catching is still caught — without a pass/fail that depends on which inode the
allocator handed back.

The original failure was never reproduced, so which assertion broke is not
recorded. The inode assertion was the only one in the file whose outcome came
from the filesystem rather than the code under test; the remaining assertions in
`tests/test_pdf_evidence.py` compare against pinned synthetic generations.

## 0.20.51 — 2026-08-10

### docs(vault-ingress) — point the candidate-mode reference at its script (#278)

Closes #278.

The candidate-mode section of `source-identity-audit.md` restated what
`audit-source-identities.py` implements: the accepted report generation, the
closed disposition set, the lane allowlist, the dedupe behaviour, and the
per-fault classification. Two copies of a predicate drift, and the reference is
the copy nobody runs.

It now carries the contract only — input, output shape, exit conditions, side
effects — and each internal is a table row pointing at the constant or function
that owns it: `CANDIDATE_REPORT_SCHEMA_VERSION`, `CANDIDATE_DISPOSITIONS`,
`CANDIDATE_LANES`, `CANDIDATE_LANE_LOCAL_CODES`, and `candidate_bindings()`. The
reasoning stays where the constants are, which is where it can be checked
against the code that reads them. Naming a predicate and then restating it is
still two copies; the reference states what a caller observes and stops there.

Raised as an advisory on PR #276 and deferred rather than folded in: the PR was
otherwise green, and `review-severity` spends a re-review round on a
presentation-only change only when a blocking round is already happening.

## 0.20.50 — 2026-08-10

### fix(vault-ingress) — stop echoing tracking-database decoder text (#275)

Closes #275.

`read-tracking-database.py` printed `str(exc)` on its failure path, to both
stdout and stderr. A `TrackingDatabaseIOError` message names the host database
path, and a decoder failure interpolates the rejected content verbatim — a
duplicate object key, a non-round-trippable number. That is input data, and
`no-secrets` → Logging forbids putting it in output. This is the script every
agent-driven read of the tracking database goes through, so its failure path is
the one every agent sees.

Every public reader now routes its typed reason code through the closed
vocabulary that already existed for exactly this in `tracking_database_io`:
`read-tracking-database.py`, `write-analysis.py`, `load-vault.py`,
`validate-profile.py`, and the Section 15 reader, plus
`audit-source-identities.py`, which was writing the decoder's text into a report
other agents read. The regression tests assert the printed message is a member
of that fixed set — membership is itself the leak guard, since a message drawn
from a dozen constants cannot carry an offending key or value.

Redaction cost actionability until the vocabulary grew to cover the failures
that never reach the decoder. A symlinked database, a missing one, a directory
in its place: those raised untyped, fell through to the fallback, and reported
"tracking database could not be read" with no next step. Each now carries a
typed code and prose naming what to fix. The public finding codes are unchanged
— the new reasons map onto `database_unreadable` — so no consumer routing on
code has to change.

Schema-assessment messages (`TrackingDatabaseError`) are untouched. Those
describe the database's own structure rather than echoing its content, and the
readers that print them stay as they were.

## 0.20.49 — 2026-08-10

### feat(vault-ingress) — derive the rhetoric-summary status block from the database (#168)

Closes #168.

`rhetoric-style-summary.md` is narrative prose, but its status line is read as
current operational fact — and it was hand-maintained, so it drifted. A verified
snapshot had the summary claiming `199 / 208` with 195 processed while the
tracking database held 209 talks: 116 `needs-reprocessing`, 9 `pending`, 78
`processed`, 2 `processed_partial`, 3 `reprocessing-inflight`, 1
`skipped_duplicate`. Queue normalization and reparse move statuses without
touching prose, so an obsolete cohort reads as live — most misleadingly during a
long reparse, which is exactly when someone checks.

`render-vault-status.py` derives that one block and nothing else. Every count
comes from a single strict snapshot through the shared reader; none is
hand-calculated. The block is delimited and schema-versioned, so replacing it
cannot disturb a narrative section, and it carries the database SHA-256,
generated timestamp, database schema version, active scoring/catalog generation
identity, total talks, exact status counts, and the active-claim count.

It reports historically-analysed separately from the current cohort, and reads
the two from different places. Eligibility is a status question; whether a talk
was ever analysed is not. Normalization flips `status` to `needs-reprocessing`
and leaves the analysis evidence in place, so reading history off the status
would erase every requeued talk's past work — the exact misreading this block
exists to stop. History is counted from the persisted evidence instead.

The compare-and-swap is one critical section, not a check and a later hope. A
digest checked at read time and a rename issued afterwards are two operations,
and a writer landing between them is overwritten by a tool that promised to
refuse exactly that. The read, the check, and the install now all run inside the
summary's persistent cooperative lock, so no second toolkit writer can occupy
that window; the bytes are rechecked once more immediately before the rename,
which is what catches a human editor, who holds no lock. That lock is the
primitive the tracking database already used — extracted to `cooperative_lock.py`
and shared, rather than reimplemented beside it, so both owner files serialize
through one audited implementation. Duplicate delimiters are malformed rather
than first-match spliced, and the whole retained-stage error family is
translated into the JSON failure contract instead of only its invariant
subclass.

The summary has two toolkit writers, not one: `section15_pattern_history.py`
replaces the Section 15 pattern-history block in the same file, and it read,
spliced, and renamed holding no lock at all — so either writer could drop the
other's update, whichever renamed first. Both now enter through
`summary_lock.py`, one seam that owns the summary's writer lock, and the Section
15 writer rechecks the target's bytes immediately before its rename the same
way. A label is diagnostics; agreeing on the lock is the contract, and a third
writer that imports that seam cannot invent its own.

Every summary failure now names its recovery, not just its fault: which file to
create, which flag supplies an alternate path, what to re-save as UTF-8. The
messages stay path-neutral — a host path in a failure line is the leak this
tool's diagnostics contract exists to prevent — so recovery is named by the
file's canonical basename and by the flag that overrides it.

`--apply` requires `--expected-sha256` from a dry run. The summary is a file a
human also edits, so an apply that cannot prove it read the current bytes
refuses rather than overwriting an edit it never saw. Replacement goes through
the shared retained-stage lifecycle, so an interruption leaves the prior
complete summary, and a no-op render installs nothing rather than churning the
file's identity for consumers watching it.

An absent scoring generation is reported absent, never defaulted — a default
would let a database with no recorded generation render a block claiming one.

## 0.20.48 — 2026-08-10

### feat(vault-ingress) — an owner writer for reviewed shownotes catalog conflicts (#236)

Closes #236.

`scan-shownotes.py` correctly reports a title or conference conflict as
`review_required`, and `--apply` deliberately refuses those entries. Nothing
could then install the reviewed decision: `apply-source-repairs.py` does not
allow `title` or `conference`, and `mutate-tracking-database.py` limited talk
updates to publishing and clarification fields. A vault operator had to either
leave a known-wrong catalog fact in place or bypass the database ownership
contract by hand. The 2026-08-05 rhetoric-vault reconciliation hit exactly that
with two conflicts — `DevOps Nashville 2024` versus `DevOps Days Nashville
2024`, and a base title versus its event-qualified form.

`apply_reviewed_metadata` is that writer, and it stays narrow:

- A closed writable set (`title`, `conference`) — a reviewed metadata decision
  is not a licence to edit arbitrary talk fields, and source lanes stay with
  `apply-source-repairs.py`.
- An exact old-value precondition per changed field, so a decision reviewed
  against one value cannot silently install over another.
- The full current talk/database shape validated before atomic replacement; a
  stale precondition, unsupported field, unknown or duplicate filename, or
  legacy talk schema installs nothing.
- Every unrelated field preserved, and the shownotes candidate never made
  authoritative on its own.

Whether a repair invalidates derived analysis is proven rather than assumed:
each writable field is classified metadata-only or analysis-invalidating, and
an import-time guard refuses to start if a field is left unclassified — a new
field cannot default to "safe". `title` and `conference` are metadata-only,
since rhetoric analysis derives from transcript and slide content. An
analysis-invalidating field requires the status and `reprocess_reason`
transition in the same plan, applied atomically with the value: a plan that
repaired the field and left the talk `processed` would leave stale analysis
looking current.

## 0.20.47 — 2026-08-10

### feat(vault-ingress) — audit shownotes conflict candidates alongside the active source (#230)

Closes #230.

`scan-shownotes.py` can report a competing source URL as `review_required`, but
`audit-source-identities.py` could only inspect the source already active in the
tracking database. Choosing between them meant an ad hoc provider lookup —
outside the identity auditor's bounded fetching, stable evidence shape,
deduplication, redaction, and no-write guarantee, and outside the documented
ingress workflow entirely.

`--candidates-from <scan-report.json>` closes that. Review-required conflicts
bind to talks and audit beside the active source:

- **The report is validated whole, all-or-nothing.** Only `schema_version: 3`
  with `ok: true` is accepted, and one malformed entry, malformed issue, or
  unbindable candidate discards every candidate binding — a partly malformed
  report is not a complete conflict set, so auditing the well-formed remainder
  would report an unknown subset as "these are the conflicts". The active lane
  still audits. An unsupported lane is not a malformed report and stays
  lane-local.
- **An unknown `disposition` is malformed, not skippable.** The scan report's
  set is closed (`add`, `update`, `unchanged`, `review_required`); passing over
  an unrecognized value would let a typo hide a conflict behind an apparently
  clean audit. A report file containing JSON `null` is a supplied-but-invalid
  report rather than "no report given" — the two shared a sentinel, so a
  malformed file could disable candidate validation and still report success.
- **Bindings resolve before any provider request.** A report that is not an
  object, carries no `entries`, or names an unknown or ambiguous talk is refused
  without spending a fetch. The active lane still audits.
- **Candidate identities share the fetch dedupe, not the active-source map.** A
  candidate repeated across conflicts, or one equal to some talk's active
  source, is fetched once. It never enters the assignment the cross-talk
  collision analysis reads — a candidate shared by two talks would otherwise
  fabricate a collision between active identities that share nothing.
  `sources[].lanes` names which lane claimed each fetched identity.
- **Both sides carry the same evidence shape.** `candidates[]` holds
  `provider_evidence` and `active_provider_evidence` with identical keys, so the
  comparison is field-for-field, plus `same_source_as_active`.
- **Failures stay lane-local, and that is measured by `complete`.** A
  `slides_url` candidate has no auditable provider identity, a malformed
  YouTube URL cannot be fetched, and an unavailable or rate-limited candidate
  is a structured finding. Each carries a `candidate_`-prefixed code outside
  `ERROR_CODES`, so the audit stays `complete` and the CLI exit stays clean — a
  candidate the provider would not serve says nothing about the sources already
  stored. The same fault on an identity the active lane also claims keeps its
  blocking code.

The audit still writes nothing, candidates included: a candidate is never
promoted or persisted here. Report schema goes to v2 for `candidates[]` and
`candidate_count`.

## 0.20.46 — 2026-08-10

### feat(vault-ingress) — bind PPTX catalog visual evidence to its extractor generation (#229)

Closes #229.

`pptx_catalog` schema v1 persisted `visual_extracted` as a bare boolean and
nothing about which extractor produced it, so a stored `true` could refer to
extractor schema v0, v1, v2, v3, or current v4. Selection was undecidable from
owner state: trusting the flag silently skips stale evidence, distrusting it
forces repeated full extraction because the catalog still cannot remember that
regeneration produced current output. Preflight and profile consumers could not
bind a visual claim to the deck generation that was actually inspected.

Catalog record v2 adds `visual_evidence` — `null` for a deck no extraction has
been attempted on, otherwise a receipt carrying `outcome`,
`extractor_schema_version`, `pipeline_version`, the exact `source_fingerprint`
of the PPTX bytes, and the produced `artifact` identity and digest. `artifact`
is required on success and forbidden on failure: a success naming no artifact
cannot be proven to still exist, which is the ambiguity being removed.
`visual_extracted` stays as the schema-v1 reader's mirror of the outcome, the
same arrangement `qr_codes` v2 uses for `qr_png_rel_path`.

Selection is derived, never stored. `classify_pptx_visual_evidence` returns
`current`, `stale`, `pending`, `failed`, or `unknown_legacy`, and
`pptx_visual_evidence_needs_extraction` says which of those regenerate — every
consumer classifies through the same function, so owner writes, migration,
preflight, queue selection, and profile reads cannot disagree. A legacy record's
bare claim classifies as `unknown_legacy`, so migration preserves it without
inventing a binding it never had.

The `record_pptx` writer now requires v2 and is validated per kind, since
`pptx_catalog` left the shared `OWNER_RECORD_SCHEMA_VERSION` behind. Readers
dual-accept v1 and v2 and nothing else: a record newer than the classifier
accepts raises rather than falling through to a legacy reading, because a
lagging reader must not send a deck back through extraction on the strength of
a shape it cannot read (`stateful-artifacts` → Migration Policy).

What is on disk is the authority, so the classifier takes two live observations
as required arguments with no defaults: the deck's fingerprint and the
extraction artifact's SHA-256. A caller must state what it saw; one that cannot
make an observation passes `None` and gets `unverified`, never `current`.
Stored metadata alone can no longer claim currency, and a deleted or replaced
artifact cannot stay authoritative (`stateful-artifacts` → Hints, Not
Authority). `artifact.path` is vault-root-relative.

`preflight-vault.py` is the wired consumer: it hashes each catalog deck under
`config.pptx_source_dir` and each artifact under the vault root, then raises a
`warning` for every record that is not current — stale bytes, a replaced
artifact, an older extractor, a legacy claim, a file it could not read — plus a
distinct one for a receipt it cannot parse. The finding names which observation
was missing. Neither blocks, because stale evidence is work to schedule rather
than a reason to refuse the vault.
`read-tracking-database.py` deliberately does not classify: it is a pure
strict-snapshot reader with no filesystem authority, and a classification it
could not verify against the live deck would be exactly the unverified claim
this change removes.

Containment is enforced by the open itself, not by a check before it. A
resolved-path check followed by `open(path)` is two lookups, and a symlink
swapped in between them redirects the read outside the root. Each component
below the root is now opened relative to the previous descriptor with
`O_NOFOLLOW`, and the descriptor that passed the walk is the one that gets
hashed. The root itself is opened by name and may be a symlink — it is trusted
configuration, as the artifact-metadata contract already documents. A
non-regular file, a symlinked component, and a platform missing any of the
primitives all read as not-observed. The primitives are required explicitly
rather than through `getattr(os, "O_NOFOLLOW", 0)`: the usual
degrade-gracefully idiom would have silently dropped the no-follow guarantee on
a platform that has `dir_fd` but not the flag.

Catalog locators are enforced as root-relative before anything is opened. The
locator layer accepts a native absolute path even when a trusted root is
supplied, so a persisted record naming `/etc/passwd` would have had preflight
hash it: persisted state is a hint, never a licence to read an arbitrary host
file. An absolute locator, one that resolves outside the declared root through
a symlink, or one that cannot be resolved now reads as not-observed — for the
deck and the artifact alike.

The governing skill follows. `SKILL.md` Step 6 and `pptx-followup.md` told the
agent to "skip already extracted entries" from the boolean — the exact read this
change exists to stop, and a directive that contradicted the new one on a
second loaded surface.

Both now name what the classifier actually gates. The bounded directory
extraction walks every eligible deck and takes no include list, so the
classifier cannot filter the walk and never claimed to: it decides which
results become receipts. A `current` record keeps the receipt it has, because
rewriting it would replace a proven binding with an identical one.

Rejected receipts report a closed code too. A receipt-validation message names
the rejected value — an `algorithm`, an `outcome` — and that value came out of
the database, so a reader surfacing it discloses persisted content.
`PptxVisualEvidenceError` carries a reason code, the reader and preflight
report its neutral prose, and the writer keeps the detailed message because
there the rejected value is operator input being refused, not stored data being
echoed.

Read failures report a closed code, never the exception text. A decoder message
carries the host database path and the rejected key or value verbatim, so
echoing `str(exc)` leaks both (`no-secrets` → Logging). The reason-code
vocabulary preflight already used moves to `tracking_database_io`, beside the
error type that raises those codes, and both consumers import it — the wording
and the redaction now hold in one place instead of two.

The ingress workflow gets an executable rather than a function to reproduce:
`classify-pptx-evidence.py` takes a vault root, makes both observations,
and prints one JSON object naming every record's class and whether it needs
extraction. Observation and classification live in `pptx_catalog_selection.py`,
shared with preflight, so the two surfaces cannot drift.

The classifier validates a v2 receipt before trusting it. A receipt is the
licence to SKIP extraction, so a malformed one — `succeeded` with a null
artifact, a bogus fingerprint, a mirror flag disagreeing with the outcome —
raises instead of classifying as current.

That validation is fatal at the writer and the classifier, never at the
database assessment. Validating it during `assess_tracking_database` made one
bad extraction record read as unusable owner state, so preflight refused the
whole vault with a blocking finding — the opposite of the non-blocking contract
this feature is built on. `record_pptx` refuses to persist a malformed receipt
and the classifier refuses to trust one; the database stays usable and
preflight reports a single warning.

Found while wiring this up: the assessor validated collection-record shapes
under an `elif version == 1` cascade, so a collection lost its shape validation
the moment it bumped past the version named there — `qr_codes` v2 had already
needed a hand-written special case for exactly this. The cascade is now a lookup
against the same accepted-version sets the version gate above it uses, so a v2
record cannot slip through unvalidated and the next bump cannot reintroduce the
hole.

## 0.20.45 — 2026-08-10

### ci — gate every pull request on `tessl plugin lint` (#265)

Closes #265.

`tessl plugin lint` ran nowhere before merge. The publish workflow runs it, but
only after the merge commit lands, so a frontmatter or manifest error aborted a
release instead of failing the pull request that introduced it. That is the
shape `context-artifacts` → Plugin Structure means by "validate before every
publish", and `language-diagnostics` → Gate It Deterministically is explicit
that a check nobody runs does not exist. The over-length `description` this
issue names was caught during PR #263 only because a maintainer happened to run
lint by hand.

`scripts/check_plugin_lint.py` now runs in the `lint` job on every PR. The
advisory policy is explicit, because the CLI's exit code does not express it:

- `✘` fails the build. The CLI already exits non-zero for these; the gate also
  fails on a printed `✘` with a zero exit, so a future CLI that stops exiting
  non-zero cannot silently un-gate the repo.
- `⚠` does not fail, and is surfaced as a GitHub warning annotation plus a step
  summary entry. The only advisory lint currently raises here is entrypoint
  size, which `scripts/check_skill_entrypoints.py` already gates deterministically
  and more conservatively. Failing on `⚠` would double-gate that one and turn
  any advisory a future CLI adds into an instant build break with no owner
  decision behind it.

The CLI version is pinned in both jobs, with the renewal cadence recorded beside
the pin: no Dependabot ecosystem tracks a CLI version named in an action input,
so `dependency-management` → Freshness wants the cadence documented there, the
way the ffmpeg and tesseract pins already are. Renew quarterly, or when the
publish workflow's own lint disagrees with this gate. No token is passed — lint
needs no auth, so the gate also runs on fork pull requests, where secrets are
unavailable.

Workflow annotations go to stderr. stdout carries the single JSON report and
the CI step redirects it to `/dev/null`, so a `::warning::` printed there would
both break the stdout contract and be swallowed.

Not added to `scripts/pre-publish-checks.sh`: the publish workflow already runs
lint as its own step, and it runs the composer before installing the CLI
precisely because the composer's gates are self-contained.

## 0.20.44 — 2026-08-10

### chore(scripts) — bring the two sibling pre-publish gates up to policy (#264)

Closes #264.

`scripts/check-package-contents.sh` and `scripts/check-tessl-pins.sh` were the
two gates #263 left behind: no entry-point guard (`file-hygiene` → Standalone
Scripts), and prose on stdout where `script-delegation` → Script Requirements
wants a structured result. Both are now Python, matching the sibling
`check_skill_entrypoints.py` the review brought into line — `scripts/
check_package_contents.py` and `scripts/check_tessl_pins.py`, each with the
canonical `if __name__ == "__main__"` guard, one JSON object on stdout every
run, and actionable diagnostics on stderr.

Python rather than a bash `main` + guard because both scripts already embedded
a python3 heredoc for the JSON work, and the guard's stated purpose is making a
script importable for testing. `check_tessl_pins.py` had no test suite at all —
it now has 17 cases covering ranges, tags, missing `version` keys, non-object
entries, and every unreadable-manifest shape. The package-contents suite keeps
all 20 of its cases, re-pointed from prose stdout to the JSON report, plus the
one-JSON-object-on-every-failure-path contract and an importability case.

Gate semantics and exit codes are unchanged: same covered manifests, same
`.tesslignore` scratch-repo matching, same de-duplication of overlapping
declared paths, same 279-file result on this repo. One behavior change:
`check_tessl_pins.py` resolves its manifests against the repo root rather than
the caller's working directory, so the publish composer no longer depends on
where it was invoked from.

`scripts/pre-publish-checks.sh` gets a bash `main` + `BASH_SOURCE` guard and
keeps its exit-code-only contract. The two `tests.yml` steps invoke the renamed
gates; that CI edit is the rename, nothing else.

The port also closes a vacuous pass the shell version shipped with:
`dependencies` was read as `manifest.get("dependencies") or {}`, so a
present-but-malformed container — `[]`, `""`, `null`, `0`, `false` — collapsed
into an empty mapping and the gate reported every dependency floating. Absence
of the key is now the only thing that means nothing was declared; a
present-but-malformed container is a violation. An empty object still passes,
being a well-formed container that declares nothing.

All three gates' crash-path guidance now names `sys.executable` and the
resolved script path, so the suggested re-run command works from any working
directory and under the interpreter that actually failed.

A second inherited gap closes with it: the shell gate returned success the
moment no `.tesslignore` existed, before parsing the manifest or checking that
every declared path holds tracked files. A malformed manifest or a stale
declaration reached publish unexamined whenever the repo had no ignore file.
The manifest and declared-path checks now run on every invocation; only the
exclusion matching depends on the ignore file.

## 0.20.43 — 2026-08-10

### fix(tests) — choose the supervisor exit-vs-monitor ordering instead of racing it (#268)

Closes #268.

`test_fast_exit_race_is_confirmed_by_popen_and_cleanup_does_not_mask` failed
intermittently on the macOS artifact-contracts job, asserting `worker_exit` but
getting `worker_monitor_identity_changed`. The test injected a monitor that
always raises and then relied on the real worker exiting inside the
supervisor's settle window (`sample_interval_seconds`, 0.5 s there) for the
confirmed exit to win. On a loaded runner the interpreter took longer than that
to start and die, so the monitor's complaint surfaced first — a wall-clock
dependency `testing-standards` → Determinism forbids.

The precedence itself was already correct and stays in `artifact_supervisor`: a
Popen-confirmed exit outranks a monitor identity complaint, either at the
re-poll after `sample()` raises or through the bounded settle wait, and a
worker still live when that window closes keeps the monitor's error. No
production change — the tests now choose the observation order rather than race
it.

The end-to-end test's monitor waits for the real worker's exit event before
complaining, so the assertion no longer depends on how fast an interpreter can
start. Three stub-process tests assert the full ordering matrix explicitly:
exit confirmed at the re-poll, exit confirmed inside the settle window, and a
settle window that confirms nothing. Each fails under a mutation that removes
the matching `break`.

`_run` now defaults to a frozen clock, so no assertion in the file can be
preempted by the 5-second wall deadline when a runner stalls; the four tests
that exercise the deadline still pass advancing clocks of their own.

Every remaining real-time bound in the file is gone with it — the FIFO
handshake `select`, the descendant-handshake `wait`, the cleanup-thread
`Event.wait`/`join`, and the two import-probe `subprocess.run` timeouts all
block on their event instead. A bound there decides the outcome by runner
speed: a stalled runner misses the deadline and reports a failure that never
happened. A step that truly never completes is now a hang the job's own
timeout catches, which is a louder signal than a false assertion failure.

## 0.20.42 — 2026-08-10

### fix(vault-ingress) — share one retained named-stage across owner writers (#243)

Closes #243, and folds in #240.

`write-analysis.py` had a live defect, not a duplicated invariant.
`_stage_text` created its stage with `tempfile.mkstemp`, wrote the body,
**closed the descriptor**, and returned a pathname; `atomic_write_batch` then
installed it with `os.replace(name, target)`. Between those two steps the staged
name was just a name in a directory, so anything able to write there could
substitute it and have the writer install those bytes. Reproduced before the
fix: the batch returned normally while the target held attacker-supplied
content. The writer had no byte verification of its stage at all — every
`sha256` in that file was citation rendering.

`retained_stage.py` now owns the staged-file lifecycle for both writers: unique
no-follow creation with a retained file and directory descriptor, regular-file
and single-link validation, exact descriptor/name device and inode identity at
every preinstall observation, exact size/bytes/SHA-256 binding, and bounded
same-view `mtime_ns`/`ctime_ns` stabilization. Each owner keeps its own
compare-and-swap and backup behavior, which is what differs between them;
`tracking_database_io` maps the shared `StagedInvariantError` into its existing
`StagedCandidateConflictError` so its public error contract is unchanged.

The analysis writer re-verifies immediately before each replace rather than only
at stage time, so the staging-plus-preflight window is covered too, and runs a
post-install check whose failure is reported as installed-but-unverified — never
as a pre-install failure, because the replace already happened.

Cleanup is truthful (#240). `close_retained_stage` returns a report carrying a
disposition and stable reason codes — `staged_cleanup_unlink_failed`,
`staged_cleanup_descriptor_close_failed`,
`staged_cleanup_directory_close_failed`, `staged_cleanup_name_not_owned` — so a
pre-install failure can no longer discard them on the way out. A name that now
resolves to a different inode or file type is left untouched rather than
unlinked: it is someone else's data, and removing it to tidy up after ourselves
would be the second bug. `KeyboardInterrupt` and `SystemExit` still propagate.

The policy reviewer caught the same failure shape inside the new module: the
incomplete-stage path used `except OSError: pass`, so a failed unlink orphaned
a temp with no diagnostic — the exact bug this primitive exists to stop, one
layer down, and a violation of Never Suppress Errors besides. Cleanup now
returns what it could not do; a `RetainedStageError` carries that detail in its
message with its type and `reason_code` intact, and anything else surfaces on
stderr. The interrupt path cleans up and warns without trapping the interrupt.
`_stage_candidate`'s `except BaseException` narrowed to `except Exception` with
a `finally` for interrupt-safe release, since it is an inner helper and none of
the Outer-Boundary Carve-Out's preconditions apply.

A second review round caught four more, three of them in the error contract I
had just written. The enrichment path rebuilt the failure with
`type(exc)(message, reason_code=...)`, which is the wrong constructor for
`StagedInvariantError` — a cleanup failure would have raised `TypeError` in
place of the real diagnostic. Each type is now rebuilt through its own
constructor, and both helpers catch only their anticipated typed failure with a
cleanup-only `finally` for everything else, interrupts included. A failed
inspection of the staged name no longer reports `already_absent`, since absence
was never established and an orphan may remain; it gets its own
`staged_cleanup_inspect_failed` disposition. The test fixture stopped
suppressing cleanup errors.

A third round found the analysis writer still exiting 0 after a failed
post-install proof: the warning was collected, the batch marked committed, and
the CLI reported success over a target that might hold substituted bytes. That
now raises `AnalysisBatchUnverifiedError` — a distinct type, because rolling
back would be wrong here (the replace already happened and the target holds the
new file). The batch completes, the recovery backup for each unproven target is
retained rather than deleted, and the run fails so an operator inspects instead
of trusting it. The staging-failure path also released its stages inside a
`finally` that ran after the error was constructed, so those cleanup warnings
went nowhere; cleanup now happens first and the detail rides out on the error.

Two more cleanup dispositions stopped lying. A failed `os.unlink` reported
`already_absent` — the same untruth already fixed for a failed inspection, but
missed one branch over — so a consumer could record a clean cleanup over a
confirmed orphan. It gets `staged_cleanup_unlink_failed`, and only `removed`
and `already_absent` now assert the name is gone. The tracking-DB helper's
interrupt path also discarded its report; those warnings go to stderr rather
than nowhere.

Two Copilot findings folded in. `_stage_candidate` ran cleanup on a
verification failure and dropped the report, reintroducing the vanished-warning
problem one level up; the cleanup detail now rides out inside the typed
conflict's `detail`. And the module docstring claimed no-follow for the
directory open, which is deliberately not the case — the vault root is
documented as possibly being a symlink, so refusing a symlinked component there
would break supported installs. The no-follow guarantee covers the staged file
and every later name resolution, which is anchored to the retained directory
descriptor. The docstring now says that instead of over-claiming. A dead
`_visible_descriptor_identity` wrapper left by the extraction is gone.

Test seams followed the implementation. Five injection points that patched
`tracking_database_io` internals now patch `retained_stage` where the
observation loop actually lives; the two that wrap the owner's typed-error
mapping keep patching the owner, because that mapping is the owner's. All 342
existing writer race, interrupt, backup, durability, analysis-body-preservation,
and CloudStorage migration tests stay green unchanged.

## 0.20.41 — 2026-08-10

### feat(vault-ingress) — carry the matched rejection into scan reports (#177)

Closes #177. `scan-shownotes.py` blocked a reappearing known-bad source but
reported only that it had; recovering the reason, evidence, timestamp, and
stored identity meant a second trip into the tracking database before anyone
could judge whether the candidate was still wrong.

A `rejected_source_reappeared` issue now carries the ledger record that matched
— `source_type`, stored `url`, parsed `provider_id`, `reason`, `evidence`,
`verified_at` — plus a `match` object naming how the match was established
(`exact_url` or `provider_id`) and the candidate identity compared against.
Only the matched record travels; unrelated `source_rejections` entries stay
private to the talk, asserted by a test that greps the serialized report for
the other two URLs.

Report schema goes to v3, documented in `references/schemas-db.md`. Two tests
that hardcoded `2` now read `REPORT_SCHEMA_VERSION`, so the next bump does not
touch them.

The acceptance criterion about validating the record before reporting it turned
out to be satisfied more strictly upstream: `_load_database` refuses the whole
scan when any `source_rejections` entry fails
`tracking_database._validate_source_rejection`, so a partially trusted record
cannot reach a report at all. A re-check inside the matcher would have been
unreachable, so the matcher points at that owner instead of restating it, and
the test asserts the loader-level refusal across a blank reason, a missing
evidence field, a naive timestamp, and an unparseable one.

Mutation behavior is unchanged: a reappeared source stays `review_required` and
is never reactivated.

## 0.20.40 — 2026-08-10

### test(vault-ingress) — pin the return-self-validation boundary (#159)

Closes #159. The enforcement it asked for is already in the tree: it landed
with the video and PDF supervision work that reworked `build_evidence_context`.
`context["metadata"]` is copied from the persisted talk record alone, and slide
bounds come from probing real artifacts, so `structured_data.slide_count` and a
return's `slide_source` reach neither. What was missing is the issue's last
acceptance criterion — the regression tests, without which nothing stops a
future refactor from quietly reconnecting the return to its own validation.

Four outcome-level tests in `tests/test_pattern_evidence.py` lock both
directions:

- a return-supplied `slide_count` stays out of the evidence metadata, so a
  `talk_metadata` citation on it fails as an absent pre-return field;
- a return-supplied `slide_source: pdf` produces no slide count, so `slides` and
  `slide_sequence` citations fail for want of a readable local artifact;
- a persisted `slide_count` still validates and stamps from owner state, not
  from the return's competing value;
- a real PDF on disk still bounds citations at its actual page count, and an
  inflated returned count buys nothing past it.

The remaining criterion — partial timing and video citations rendering without
internal `None` — was already covered by
`test_partial_citation_bounds_render_without_internal_none` across all seven
single-sided cases.

One path still reads the return: `delivery_language` falls back to
`structured_data.delivery_language` when the persisted record has none. That is
not a self-validation hole, because the value can only add the English-
translation requirement to transcript citations, never remove one.

## 0.20.39 — 2026-08-10

### chore(ci) — hold skill entrypoints inside Tessl's token budget (#163)

Closes #163. `tessl plugin lint` flagged `presentation-creator/SKILL.md` at
~8,749 tokens against Tessl's 5,000 recommendation; the entrypoint loads in full
the moment the skill triggers, so every consumer paid that context before a
single task-specific reference was selected. It is now ~4,700.

The issue also named `vault-ingress/SKILL.md` at ~10,939 tokens. That one had
already come in under budget through unrelated work, so only the creator
entrypoint needed the split — the issue text was stale by the time it was picked
up.

Most of the removed bulk was duplication rather than unique content: the `talk:`
block, the outline schema, the guardrail-report contract, and the deck-build
passes were each already documented in `references/phase{1,3,4,5}-*.md`. Two
genuinely new reference files carry what was only in SKILL.md:

- `references/pattern-history-authorization.md` — the `pattern_history_status.py`
  payload shape, the six domain contracts, source selection, profile schema
  tiers, Section 15 eligibility, summary-only mode, and the cross-generation
  comparison rules. SKILL.md keeps the invocation and routes here.
- `references/alternate-entry-flows.md` — late entry, adapting an existing talk,
  CFP abstracts, and the sessions catalog. These are alternate entry points, not
  phases of the linear flow, and each names its own trigger condition.

Three fixes fell out of the split. `phase3-content.md`'s `talk:` table was
missing `engine`, `deck_theme`, and `engine_source`, so those rows moved rather
than evaporated. `phase5-slides.md` pointed at "the presenterm branch in SKILL.md
Step 5" for content SKILL.md pointed back at it for — the circular reference is
now a real Step 5.1c. The poster-theatrical `TITLE`/`FOOTER` omit rule and the
load-bearing `expand-builds` → `inject-notes` → `apply-backgrounds` ordering also
landed in `phase5-slides.md`, where the rest of the build detail lives.

`scripts/check_skill_entrypoints.py` makes both properties deterministic instead
of remembered, per `language-diagnostics` Gate It Deterministically. It fails on
an over-budget entrypoint and on a relative link resolving to nothing — the
second failure mode being the one the split itself introduces, since a dangling
pointer is silent at runtime: the agent follows it, finds nothing, and proceeds
without the routing contract. Links inside code fences and inline code spans are
sample output the skill emits, not pointers, so they are excluded. Code spans
close on a matching delimiter run, not on the next backtick: pairing single
backticks split ``[x](missing.md)`` at its first two characters and leaked the
link back into the scanned text, failing the gate on a valid skill. The token
estimate is chars/4, which rounds against us (8,791 estimated vs Tessl's 8,749
reported on the same file), so a pass here implies a pass in lint.

The gate is `scripts/check_skill_entrypoints.py`. It started as shell and moved
to Python across two review rounds, because three separate rule findings all
pointed the same way: `file-hygiene` Standalone Scripts wants an entry-point
guard (`if __name__ == "__main__"` is its own named example),
`script-delegation` Script Requirements wants JSON on stdout, and the Regex
Trap rules out matching Markdown links with `\]\([^)]+\)`. That regex breaks on
`[a](notes.md "title")`, on `[a](refs/note_(draft).md)`, and on the
angle-bracket form — each a valid link the gate would have reported as dangling,
blocking the publish of a correct skill. The destination scanner now implements
the CommonMark grammar it needs: angle-bracket form, balanced parentheses,
backslash escapes, and a title the path must not absorb.

The scanner also requires the closing `)`. Returning a destination as soon as
the path ended meant `[x](<missing.md>` and `[x](missing.md "title"` — neither
of which is a link — produced a target that was then reported as a dangling
reference, the same false publish block from the other direction. A malformed
construct now yields nothing, and a later well-formed link on the same line is
still found.

Resolution asks whether the target *ships*, not whether it exists. A link
reaching through `..` into `tests/`, into the repo-root `scripts/`, or out of
the repo entirely names a file present in the working tree and absent from
every package — which dangles at runtime exactly like a missing one, and which
the first version of this gate passed. A target must now resolve inside the
repo, sit under a path `.tessl-plugin/plugin.json` declares, and survive
`.tesslignore`. The ignore test runs through the same throwaway-repo
`core.excludesFile` technique `check-package-contents.sh` uses, so the two
gates cannot disagree about what a pattern matches. Each failure carries its
reason: `missing`, `escapes the repository`, `not declared plugin content`, or
`excluded from the package by .tesslignore`.

Token math is a ceiling, not truncation: integer division reported 20,001
through 20,003 characters as exactly 5,000 tokens and passed a file that was
over budget. The boundary test is parametrized across every excess below the
divisor so the gap cannot reopen.

The first shell draft ended its link-extraction pipeline in `|| true`, which
`error-handling` forbids — it collapsed each stage's exit 1 (filtered everything
out, legitimate) with exit 2 (bad regex) and with an unreadable file, so a
broken checker would have reported success. The Python reader raises on a real
read failure and returns an empty list for "no links", which are different
outcomes.

Reference-style links are collected too. Matching only inline `](...)` meant a
`[notes][n]` usage with a `[n]: references/missing.md` definition walked past
the gate. Definitions are validated; usages are deliberately not matched
against them, because CommonMark's shortcut form makes any `[text]` a potential
reference and these skills carry literal bracketed tags in prose (`[RECURRING]`,
`[NEW]`, `[CONTEXTUAL]`) that would then fail a correct file.

Every run emits one JSON object, failures included. Validation errors raised
`SystemExit` from inside the checks, so a missing `skills/`, an unreadable
entrypoint, a malformed manifest, or a `git check-ignore` failure left stdout
empty — which contradicted the script's own documented contract and made "the
gate said no" indistinguishable from "the gate crashed" without parsing stderr.
A typed `GateError` now carries the actionable message to the outer boundary,
where it becomes a structured failure object on stdout, the diagnostic on
stderr, and a non-zero exit. `main()` also takes `error-handling`'s
Outer-Boundary Carve-Out (`outer-boundary-process-contract`) so a bug in the
gate itself still emits that shape instead of a traceback — `except Exception`,
never `BaseException`, so interrupts keep working.

Both file reads catch `UnicodeError` explicitly. `UnicodeDecodeError` is a
`ValueError`, so it slipped past the `OSError` handler and surfaced as a
traceback — and the entrypoint handler's message had been promising to cover
encoding all along.

`pyproject.toml` adds `scripts` to Pyright's `include` and to the `tests`
execution environment, so repo-root gate scripts are type-checked and importable
by their tests the same way skill scripts already are. `tests/conftest.py`
splices the directory onto `sys.path` alongside the four skill script roots.

The gate joins `scripts/pre-publish-checks.sh` and is covered by
`tests/test_skill_entrypoints.py`: both budget boundaries, the destination
grammar, the unreadable-file path, and a guard that the composer actually
invokes it.

`phase5-slides.md` drops its `Step 5.0` / `5.1b` / `5.1c` / `5.2`… headings for
descriptive ones. `skill-authoring` Step Structure bans decimal and lettered
sub-steps, and its `applyTo` covers `skills/**/*.md`, not only `SKILL.md`;
phase5 was the last reference file still numbering that way, so it now reads
like `phase3-content.md` and `phase6-publishing.md` do. Descriptive headings
also avoid a `Step 1` in the reference colliding with a different `Step 1` in
the entrypoint.

That surfaced a pre-existing dangling internal pointer: the file's directory
map credited `builds/` to "Phase 5 Step 5.1c", a heading that did not exist,
and progressive-reveal builds come from the illustrations pass regardless.

Every step gate in the creator SKILL.md now states its continuation explicitly,
per `skill-authoring` Step Continuity. Steps 2 through 6 ended at a bare
`Gate:` line, which reads as an implicit pause; Step 6 now says it finishes
there because Step 7 is triggered separately.

The preamble stays the sequential one. An intermediate revision phrased the
alternate entries as routing, which read as an action router, and a router
preamble ("execute only that step; do not run other steps") would be wrong
here: three of the four alternates are entry *offsets* into the same ordered
workflow, not standalone actions, so a router instruction would have the agent
run one phase and stop. The preamble now says the workflow is sequential and
that a request may enter at a later step; a "Where to enter" note in the body
names the four and points at `alternate-entry-flows.md`. The frontmatter
`description` lists them so runtime discovery can match those intents — it had
been missing single post-authoring tasks and sessions-catalog work — and the
surrounding prose tightened to stay inside the 1024-character cap.

The two sibling gates (`check-package-contents.sh`, `check-tessl-pins.sh`) have
the same entry-point-guard and prose-stdout gaps. They are out of scope here and
tracked separately.

Seven doc-contract assertions in `test_presentation_pattern_history.py` and
`test_section15_pattern_history.py` read the authorization contract out of
SKILL.md. They now read it from the reference file that owns it, plus a new
assertion that SKILL.md routes there — so content vanishing from both still
fails rather than passing on a union.

## 0.20.38 — 2026-08-09

### chore(ci) — enforce the Ruff, format, and Pyright gates (#162)

Closes #162, and it is the last step of the adoption sequence by design:
`language-diagnostics` Adopting on a Dirty Tree wires the gate only once the
tree reports zero, in its own change. Four PRs cleared the baseline first
(#257 Ruff lint, #258 `ruff format`, #259 Pyright resolution, #260 and #261 the
findings); this one turns them into a gate.

`.github/workflows/tests.yml` gains a `lint` job running `ruff check`,
`ruff format --check`, and `pyright`. `test` and `supervisor-platform` declare
`needs: lint`, so the checks run BEFORE tests as `code-formatting` CI
Integration requires — a style or type regression reports in about a minute
and never pays for `test`'s multi-minute apt install of
ffmpeg/libreoffice/tesseract.

The job installs `.[test,lint]` even though it executes nothing: Pyright
resolves third-party imports against the active interpreter, and without the
runtime dependencies it reports ~94 resolution false-positives and stops
deep-checking the code underneath.

Branch protection is untouched. Promoting `lint` to a required check is a
repo-settings decision, not a file in this change.

## 0.20.37 — 2026-08-09

### fix — clear the Pyright test baseline (#162)

Fifth of the #162 adoption sequence. Pyright reports **0 errors across all 153
files**. The CI gate is the next and final PR: `language-diagnostics` Adopting
on a Dirty Tree wants the tree green before the gate is wired, in its own
change.

The 242 test-file findings were resolved by proving invariants once rather than
suppressing them at each use, per `language-diagnostics`. Seven `conftest.py`
helpers now carry what was previously re-derived or ignored at ~90 call sites:
`deck_width` / `deck_height` (python-pptx types slide extents Optional),
`slide_title` (a layout may have no title placeholder), `slide_element` /
`graphic_frame_element` (`element` is typed as the union of every CT_* shape),
and `background_fill_element` / `background_properties` /
`clear_background_fill`.

`_load_vault_payload` in `test_validate_profile.py` is the same move at the
test layer: `_run_load_vault` legitimately returns None when the command wrote
nothing — three tests assert exactly that — so the six tests that go on to read
the payload now assert its presence once instead of subscripting an Optional 24
times.

Mechanical shapes handled in bulk: 34 `Path` arguments where python-pptx
declares `str | IO[bytes]`, 41 zero-valued `Length` positions, and JSON-document
fixtures annotated `dict[str, Any]` — `object` values forced every nested
subscript to be re-narrowed, while `Any` is what `json.loads` returns anyway.

Exactly two suppressions survive, both in one `conftest.py` helper and both
naming their cause: python-pptx annotates `CT_Background.bgPr` as Optional but
leaves `CT_BackgroundProperties.eg_fillProperties` unannotated, so a reader sees
the `ZeroOrOneChoice` descriptor instead of the element it returns.

Verified against a clean venv built the way CI builds one: `ruff check` clean,
`ruff format --check` 359 files already formatted, `pyright` 0 errors.

## 0.20.36 — 2026-08-09

### fix — clear every Pyright finding in shipped scripts (#162)

Fourth of the #162 adoption sequence. With resolution correct, the 16 findings
Pyright reported against shipped code were real signal rather than import
noise. All 16 are gone; the remaining baseline is entirely in tests.

Two were latent bugs the type checker surfaced:

- `generate-qr.py` bound `bg_hex` only in the multi-variant branch, then read it
  behind `None if len(color_groups) == 1 else bg_hex` — correct only because
  that condition was re-derived identically three statements later. `bg_hex` is
  now `None` in the single-variant branch, so the binding carries the answer.
- `extract-script.py` read `ev.script if hasattr(ev, "script") else []` off a
  variable still typed `object`. Both `Slide` and `Interlude` declare `script`
  with a `default_factory`, so the guard could never fire and the `else []`
  branch was unreachable. Each branch now reads off its own narrowed model.

Two were defensive code asserting something untrue:

- `preflight-vault.py` looked up `getattr(exc, "reason_code", None)`, implying
  the attribute might be absent. `TrackingDatabaseIOError.__init__` declares it
  with a default, so it is always a `str`.
- `backgrounds-manifest-to-spec.py` and `notes-to-packed.py` passed an arbitrary
  `object` to `int()` and caught `TypeError`. They now narrow to `str | int`
  first — JSON object keys are strings, and every other input takes the same
  rejection path with the same message.

The rest were API drift and typing gaps: `Image.LANCZOS` →
`Image.Resampling.LANCZOS` (Pillow's own stubs dropped the old alias), a
`dict[str, str | None]` annotation on the secrets map, and `lxml-stubs` added
to the `lint` group because lxml ships no inline types.

`__doc__.splitlines()[0]` needed two passes. `__doc__` is `None` under
`python -OO`, and the first fix — `(__doc__ or "").splitlines()[0]` — still
raised `IndexError`, because `"".splitlines()` is `[]` while `"".split("\n")`
is `[""]`. All 13 argparse descriptions now use the `split("\n")` form the
repo already used in five of them, and
`tests/test_cli_docstring_descriptions.py` runs each CLI's `--help` under a
real `-OO` interpreter.

That test asserts exit 0, not the absence of a traceback: `check-runtime.py`'s
outer failure boundary (#203) converted the `IndexError` into a clean stderr
diagnostic and exit 2, so a traceback check passed while `--help` was broken.
A boundary that hides a crash from a test is worse than no boundary.

`_validate_qr_artifacts` now returns the validated paths instead of `None`, so
its caller reads a proven value rather than re-indexing into a raw record — the
typed-helper form `language-diagnostics` prefers over an ignore at each use.

Still open on #162: 242 findings in test modules, then wiring Ruff check, Ruff
format check, and Pyright into pull-request CI.

## 0.20.35 — 2026-08-09

### chore(ci) — resolve Pyright's module graph and pin the checker (#162)

Third of the #162 adoption sequence. `language-diagnostics` Resolve Modules
First: configure resolution before raising strictness, because unresolved
modules stop deep checking and real null-flow bugs hide behind import
false-positives. This PR does the resolution and nothing else — no gate, no
finding fixes.

Every script directory is its own `sys.path` root at runtime: each script runs
directly so its own directory leads `sys.path`, `conftest.py` inserts all of
them for the tests, and vault-clarification, vault-profile, and illustrations
splice a sibling skill's scripts on to share its validators.
`[tool.pyright].executionEnvironments` now models that per root.

Unresolved imports went 116 → 0. The one remaining suppression is targeted and
states its cause: `tests/test_pyproject_pins.py` imports `tomli` on Python 3.10
only, and Pyright analyzes at the declared 3.10 floor while resolving against a
3.11+ environment that correctly has no `tomli`.

`pyright==1.1.411` joins the `lint` group beside Ruff. The pip distribution
bundles its own Node runtime, so the CI gate will need no Node setup step.

Resolution changes what the checker reports, so the baseline is now
measured, not guessed: **223 findings — 16 in shipped scripts, 207 in tests**,
concentrated in four test modules. `reportArgumentType` (122),
`reportOptionalSubscript` (30), and `reportIndexIssue` (24) lead. Fixing those
by shape, then wiring Ruff check, Ruff format check, and Pyright into CI, are
what remain on #162.

## 0.20.34 — 2026-08-09

### chore(ci) — clear the `ruff format` baseline (#162)

Second of the #162 adoption sequence. `ruff format` rewrites 94 of the repo's
153 tracked Python files; landing that alongside anything else would bury the
"anything else". This PR is the reformat and nothing but.

`code-formatting` Separation of Concerns is enforced at the commit level here,
not just the PR level. The reformat is one commit whose 94 files are each
AST-identical to their prior form — `ast.dump(ast.parse(before)) ==
ast.dump(ast.parse(after))`, checked file by file rather than asserted.

One docstring needed a prior commit to make that hold. `""""Repair the
condition..."""` opens with a quote character, so the formatter inserts a
disambiguating space and changes the string's value. Rewording it first keeps
the formatting commit provably mechanical instead of "mechanical except for
one thing".

Still open on #162: the Pyright baseline, and wiring Ruff check, Ruff format
check, and Pyright into pull-request CI.

## 0.20.33 — 2026-08-09

### chore(ci) — clear the Ruff lint baseline and configure the linter (#162)

First of the #162 adoption sequence. `language-diagnostics` Adopting on a Dirty
Tree wants the config and the fixes landed before the gate, in their own PR —
so this one turns nothing red in CI yet.

Ruff is declared and pinned in a new `lint` optional group (`ruff==0.16.2`),
on the same weekly Dependabot pip lane. Its own group because the test runner
does not need it and a linter bump is its own change.

`[tool.ruff]` now pins `line-length = 88` and `target-version = "py310"`
explicitly, and `[tool.ruff.lint]` selects Ruff's default set plus `BLE`.
E501 stays off on purpose: the formatter owns line width, and running both
makes the linter argue with the formatter over lines the formatter cannot split.

The baseline this cleared:

- `generate-qr.py` caught bare `Exception` twice, both inner helpers, neither an
  outer process boundary. `_two_color_metrics` now catches `(OSError, ValueError)`
  — Pillow raises `UnidentifiedImageError` (an `OSError`) for a format it cannot
  read and `ValueError` for an unsupported convert mode. `_picture_is_qr` catches
  `(ValueError, KeyError)` — python-pptx raises the first for a picture with no
  embedded image and the second for a missing relationship. Anything else was
  a bug in the script being swallowed as "not a QR".
- `test_video_slide_extraction.py` built its distinct-frame fixture with
  `np.random.RandomState(42)`. Seeded is not the same as fixed, and
  `testing-standards` Determinism's carve-out covers property-based generators,
  not a numpy RNG shaping a fixture. Three index-arithmetic patterns replace it
  — vertical stripes, a diagonal sawtooth, concentric rings — with a second test
  asserting their pairwise phash distances (31, 31, 38) really do clear the
  threshold 8 the first test relies on. Solid fills would not work: phash reads
  structure, so three flat colors hash alike. The ring pattern derives its
  center from the frame's own extent, so the distances hold at any size.
- Nine mechanical findings in tests: three unused imports, one dead local whose
  stale comment went with it, one multi-import line, six semicolon statements.

Still open on #162: the `ruff format` baseline, the Pyright baseline, and
wiring all three into pull-request CI.

## 0.20.32 — 2026-08-09

### chore(deps) — pin the last four Python requirements and gate the rule (#161)

`python-pptx`, `lxml`, `qrcode`, and `pytest` were still unpinned, so every
clean install resolved whatever PyPI served that day. All four now pin exactly
and ride the same weekly Dependabot pip lane as their already-pinned siblings.

`tests/test_pyproject_pins.py` is the gate. `dependency-management` said "pin
versions" and nothing checked it, which is how four requirements drifted past
in the first place — a deterministic check nobody runs does not exist. The test
walks every requirement group in the manifest, including optional extras, and
parses each entry as PEP 508 rather than pattern-matching its text: a substring
search for `==` calls `pkg===1.0`, `pkg==1.*`, `pkg==1.0,>=0.9`, and
`pkg @ https://host/a==b.whl` pinned. Fixed negative cases cover each. The
Dependabot half is parsed too — it asserts one active pip entry on the
manifest's directory with its weekly schedule, because a commented-out entry
leaves the text present while no bump PR is ever opened again.

`packaging` and (below Python 3.11) `tomli` join the test extra for that
parsing. `tomllib` entered the stdlib in 3.11 and `requires-python` still
admits 3.10.

`project.version = "0.0.0"` now says beside itself why it is a sentinel: the
registry version lives in `.tessl-plugin/plugin.json` and is bumped by the
publish workflow. This package is never uploaded to PyPI. A real number here
would be a second versioning scheme with nothing keeping it in step with the
one that ships.

Verified by building a clean venv from the manifest alone and running the full
suite on Python 3.11 and 3.13, bracketing CI's 3.12.

## 0.20.31 — 2026-08-09

### fix(vault-ingress) — close the last four deterministic entrypoint boundaries (#203)

`write-analysis.py`, `validate-returns.py`, `audit-pattern-catalog.py`, and
`aggregate-catalog-feedback.py` had no process-wide unexpected-failure boundary.
An unexpected exception reached the caller as a traceback carrying return paths,
catalog entry text, and vault locations — and for `write-analysis.py`, which
installs files before emitting its receipt, with no way to tell whether the
batch had committed.

Each now runs behind a `run_cli()` that emits one closed, path-neutral JSON
document on stderr and exits non-zero. `write-analysis.py` reports
`analyses_written` the way `persist-results.py` reports `database_written`, so
an operator can distinguish a rolled-back batch from a committed one whose
receipt died. The two catalog gates exit 3 rather than 2 because argparse
already owns 2 there; a caller can still tell a malformed invocation from a
broken tool.

All four pre-render their reports with `json.dumps` before writing. A
`json.dump` straight to stdout that fails partway leaves a truncated document a
caller would try to parse.

`skills/vault-ingress/scripts/failure_diagnostics.py` is the new home of the
diagnostic shape, which `persist-results.py` and `preflight-vault.py` had each
copied. A sixth entrypoint would have been a third copy. The document's
identity fields are written after a caller's `state`, so an entrypoint cannot
shadow its own `error` code and make consumers misclassify the failure —
raising instead would produce the traceback the boundary exists to prevent.

`references/entrypoint-failure-contracts.md` inventories every entrypoint's
stdout, stderr, exit-code, and commit-position contract — #203's first
acceptance criterion, and previously nowhere written down. The exit-2 shapes
#251 introduced were undocumented too; the reference and the four call sites in
`batch-persistence.md`, `bootstrap-and-preflight.md`, and
`pattern-catalog-contract.md` now name them.

Closes the deterministic-entrypoint scope of #203. The earlier audit
(PR #251) established the three PPTX sites were already compliant and that
`check-runtime.py`'s traceback is a deliberate, tested contract.

## 0.20.30 — 2026-08-09

### fix(vault-ingress) — say which failure the unreadable transcript hit (#253)

`transcript_artifact_unreadable` always read "transcript artifact cannot be
decoded as UTF-8 speech text", but the handler catches `(OSError, UnicodeError)`
— a permission denial or a vanished file got a message asserting the wrong
cause. #252 already split `actual` into `not_utf8` versus
`unreadable:<ExceptionType>`; the message now follows the same branch, staying
free of the errno prose and host path that `artifact_path` already carries
(#200). Both messages name the recovery — re-fetch or re-save for a decode
failure, restore and make readable for a read failure — because a diagnostic
that only describes the fault leaves the operator to guess (`error-handling`
Actionable Messages).

Found by Copilot's advisory review of #252. Advisories never gate
(`rules/review-severity.md`), so it was deferred here rather than burning a
re-review round.

## 0.20.29 — 2026-08-09

### fix(vault-ingress) — route preflight diagnostics off typed reasons, not exception prose (#200)

Three preflight paths published raw exception text across a public diagnostic
boundary, and one chose the public finding code by substring-matching that text.

`TrackingDatabaseIOError` and `ReturnValidationError` now carry a
`reason_code`. The top-level database read derives BOTH its finding code and
its public message from that reason, so rewording an upstream message can no
longer silently reclassify a failure, and the decoder's text — which embeds the
database path, the offending duplicate key, and rejected numeric literals —
never reaches the report. An unmapped reason falls back to
`database_unreadable` rather than inventing a code.

`_validate_decoded_json_tree` runs after a successful decode, so its
deep-nesting and unpaired-surrogate rejections are typed too — without codes
they degraded to the generic `database_unreadable` and defeated the routing. A
test asserts every `reason_code` the decoder emits has a mapping, so a new
reason cannot silently fall through.

Three existing tests asserted the report echoed the offending key or literal.
They now assert the message belongs to the closed set of seven constants, which
is a stronger guard: a message drawn from fixed strings cannot carry input at
all.

`transcript_artifact_unreadable` reports `not_utf8` or
`unreadable:<ExceptionType>` instead of the raw `OSError`/`UnicodeError`
string, which carried the host path and decoder byte offset. The video-manifest
rejection reports the schema field path instead of the validator's message,
which can quote the value it rejected; where a narrower classification already
exists — an artifact-locator reason — that code survives to the diagnostic
rather than being flattened to the field path.

Two further leaks surfaced while testing: `pattern_evidence.py` embedded the
decoder's message in `source_reasons`, which preflight publishes as a
`capability_fact`. Both now state the condition without the offset or path.

The documented structured `artifact_path` field is unchanged — it exposes
absolute paths by design, and this issue never covered it.

## 0.20.28 — 2026-08-09

### fix(vault-ingress) — close the deterministic diagnostics gap in two CLI entrypoints (#203)

`persist-results.py` and `preflight-vault.py` had no process-wide
unexpected-failure boundary, so an outer failure surfaced as a traceback with no
machine-readable document — indistinguishable, to a caller, from the script
never having run.

`persist-results.py` is mutation-capable, so its boundary reports commit
position: the failure document carries `database_written`, stating whether the
atomic write installed. Without it an operator cannot tell a pre-commit abort
from a post-commit reporting failure, and a blind retry could re-persist the
batch. stdout stays empty and the JSON goes to stderr.

`preflight-vault.py` emits one closed report in the real schema shape, carrying
a `preflight_unexpected_failure` blocking finding whose keys match the canonical
finding shape, so consumers that gate claiming on `blocking_count` keep working.
Only the exception type crosses the boundary — never its message or any path.

Both documents carry an `origin` list — the traceback's code locations as
`basename:line in function`. `no-secrets` forbids exception messages and
credentials from reaching any diagnostic at any level, so the message itself
never crosses the boundary, but an exception type alone identifies no condition
to repair. The frames do. The preflight guidance also names likely causes and
points at `check-runtime.py` for the dependency case.

The issue named five sites; three were already compliant. Both PPTX worker
guards already carry `outer-boundary-process-contract` catches, `pptx-extraction`'s
`main()` already has its boundary, and `check-runtime.py`'s child result-write
traceback is a deliberate contract with a test defending it — stdout stays clean
and the traceback is the actionable signal.

## 0.20.27 — 2026-08-09

### fix(generate-qr) — make publication recoverable when the tracking-database CAS rejects (#172)

QR publication snapshotted the database, then created or retargeted a remote
link, wrote PNGs, and mutated the deck before committing against that original
snapshot. Any unrelated concurrent writer therefore caused finalization to
reject *after* every external effect had already succeeded, leaving the link,
PNGs, deck, and `qr_codes[]` in disagreement — and a blind retry could repeat
the effects.

The commit now re-reads the current generation and rebases this run's single
`qr_codes` upsert onto it. Only a conflicting change to the same talk's record
can reject; the CAS generation check still protects against a lost update, and
an unrelated writer's change survives rather than being clobbered.

Publication holds a per-slug advisory lock at `{vault}/.qr-{talk-slug}.lock`
spanning link resolution, PNG generation, and deck mutation, so two runs for the
same talk cannot interleave their external effects. The lock is keyed per slug,
so unrelated talks still publish concurrently, and it is never held across an
unrelated writer's commit.

`--talk-slug` is validated as lowercase kebab-case at the CLI boundary, before
it reaches the lock path, the default PNG filename, or the short link's
back-half. A path-shaped slug now fails on the slug contract with a message
naming it, instead of surfacing later as a confusing lock-open error.

State loaded before the lock is re-read after acquiring it, before short-link
resolution. Without that, two same-slug processes both load the old view,
serialize at the lock, and the second still cannot see the first's committed
link — so it creates a duplicate instead of retargeting it, which is the
failure the lock exists to prevent. A lock-acquisition failure exits with an
`ERROR:` line rather than a traceback, matching the script's other early-failure
paths.

The rebase is not a blind overwrite. This talk's `qr_codes` record is captured
under the lock at publication start and compared against the fresh read at
commit; a same-talk change landing meanwhile is another owner's decision, so
the commit rejects rather than discarding it. The slug lock keeps competing QR
runs out, but non-QR writers do not take it.

A commit that still rejects no longer looks side-effect-free. The run exits
non-zero and names every effect that landed — short-link provider and link id,
each PNG path, the mutated deck — plus how a retry behaves against them.

A bit.ly back-half failure creates the link before it fails, so
`ShortenerResolutionError` now carries that partial creation as structured
`partial_link` data rather than only in its message text. The receipt records
it and the run emits the effects payload, instead of the previous claim that no
PNG, deck, or tracking-database change was made — which was false whenever the
link had already been created.

`retry.idempotent` reflects how the link came to be. A retry finds an existing
link through the committed `qr_codes` record, so a link this run created with no
record behind it cannot be found — the payload says so and tells the operator to
delete it or recreate the record first. A retargeted or pre-resolved link keeps
the idempotent path.

The lock-failure guidance no longer suggests deleting a stale lock file. An
advisory lock belongs to the open inode, so unlinking the path lets a second
process create a new inode and publish concurrently — the opposite of what the
lock is for. It now points at waiting for or stopping the holder, and at
filesystems without flock support.

A rejected commit writes one JSON document to stderr —
`{"error": "qr_publication_unfinalized", ...}` carrying `retry`,
`atomic_rollback`, and an `effects[]` entry per landed effect with its own
`rollback` action — and the skill renders it, per `script-delegation`. The
payload covers every landed effect, and says plainly that there is no atomic
rollback. The link action differs by how it came to be: a link this run
created can be deleted, a retargeted link predates the run and must be pointed
back at its recorded prior target, and a pre-resolved link was never this run's
to remove. Each written PNG is named, and the deck is reported as modified in
place with no backup kept — restoring it means version control, not a promised
restore the script cannot deliver.

## 0.20.25 — 2026-08-09

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

`--short-provider` and `--short-link-id` are an all-or-neither pair: a provider
without its link id would catalog an incomplete identity. Schema v2 also
enforces the contract its documentation states — `qr_png_rel_path` must equal
`artifacts[0].path`, so the schema-v1 reader's view cannot contradict the
artifact it points at.

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
