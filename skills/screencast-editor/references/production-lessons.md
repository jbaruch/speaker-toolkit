# Production Lessons

Background reference for `screencast-editor`. Each entry is a rule followed by
the evidence that produced it. The evidence comes from producing narrated
product-demo videos (a 13-minute editorial cut built over several passes) and a
5.5-minute talk-to-camera screencast recorded in Camtasia. Apply the rules;
read the evidence only when a rule seems not to fit.

## Script and pacing

**One file owns the words; every other artifact is derived from it or checked against it.**
Teleprompter text, cue sheets, screen-plan sections and tests all drift when they
are maintained by hand. A test that fails when a plan section id no longer matches
a script beat caught stale beat names left behind after beats were merged.

**Open on the presenter full-frame and say what the viewer will get before any product screen.**
Two independent reviewers of a cut that opened on a website said they saw too
little of the presenter and did not know what they would learn. The opening
promise must not give away the payoff the close delivers.

**Plant the payoff early as a throwaway line and pay it off only at the close; bookend the signature line.**
A setup the viewer laughs off ("I'll add a label... we'll see") makes the reveal
land. Check mechanically that the setup appears in the setup beat and the payoff
in the close, and that a signature phrase appears in both the first and last beat
or in neither.

**Budget the backstory in seconds and let a check fail when it creeps.**
The scene between the hook and the first real work grows a sentence at a time and
nothing else notices. A reviewer clocked one scene at about three minutes and the
tape agreed to the second. Exclude the hook from the budget so shortening the
promise never counts as progress.

**State the rule in plain English with a condition before the screen shows its implementation.**
"A trigger, five queries, an agent, a gate" is a shape; "When a release is marked
shipped, it finds..." is a rule. A viewer can compare a result against a rule,
never against a shape.

**Narrate only what is legible on screen at that moment; if the interesting thing is illegible, point at the legible thing next to it.**
One close narrated four concepts over a screen whose only content was an
11,795-character prompt, while a readable tool list sat one click away. The same
check caught a count spoken three times that disagreed with the graph on screen.

**Keep stage directions out of spoken words.**
"On the left", "open the node" and "the tile" are layout, and they belong in the
screen plan. Production language ("next thirty seconds") leaking into speech is
the same failure.

**Run a sense check separate from any style check.**
Every number and named entity needs an antecedent the viewer saw; every callback
needs something behind it. A 42-pattern AI-writing checker passed a script that
said "eight out of thirteen" with thirteen never introduced and "remember me
telling you" about a deleted beat.

**Never call back to a value the product generates fresh each run; call back to the stable idea.**
A callback named "the two numbers I opened with" and quoted numbers the model had
printed in that run only. The opening had different numbers.

**Plan with a measured wall-clock speaking rate and never add a fudge multiplier.**
A planner at 150 wpm was multiplied by 1.22, then 1.11; the second factor
double-counted pauses already inside a wall-clock rate. The shipped tape ran
2,311 words in 1,027 s, 135 wpm, and that single number reproduced it to the second.
207 unscripted words (about 10%) explained a 92-second overrun: fix the rate or
the improvising, never the model.

**Model delivery mode separately from speed: roughly READ 124, NARRATE 136, ARGUE 151 wpm.**
Reading beats are slow because the viewer is reading the screen too; arguing
beats are fast because nothing on screen needs keeping up with. Treat these as
priors and replace them with a beat's measured rate only when most of its wording
survived.

**Keep two clocks: narration duration and raw capture floor. Slow software becomes screen retiming, never narration silence.**
A constant-scroll solver dropped a whole script to 88 wpm to cover one 150-second
model wait, turning 18 minutes of words into a 26-minute video. Fill slow waits
with useful navigation at 1x, accelerate only the visible wait that remains, and
mark accelerated footage.

**After a delivered take, mine the transcript back into the script.**
Keep what the delivery added and landed, drop what it skipped, correct proper
nouns, and record which takes are rejected so they never become sources.

## Teleprompter and narration take

**Timing cannot live in the prompter; use voice-following scroll, with hand-advance by paragraph as the fallback.**
Elgato Camera Hub has no cue syntax, and its constant-scroll slider is not linear:
50% read 115 wpm and 51% read 202. The target rate sat between adjacent steps.

**Emit the prompter text as short reading paragraphs, not beats: at most about 140 characters, no hard line breaks.**
A pedal press then advances one readable block when voice sync stalls. Split at
sentence, then clause boundaries, avoid hanging words, and assert the emitted text
is word-for-word identical to the script.

**Preflight voice sync by reading 30 seconds of the real script and watching the highlight move; "Active" is not proof.**
Voice Sync showed Active while the text did not move: a stale macOS microphone
permission let the UI look healthy while CoreAudio denied the helper. Resetting
the TCC grant (`tccutil reset Microphone <bundle id>`) and relaunching fixed it.

**Narration is one continuous take; that take is the audio for the whole video.**
Professionalism comes from continuous narration and invisible visual joins. The
shipped edit used the take unchanged except for head and tail trim, loudness
normalization and 50 ms / 200 ms fades.

**For an automated cut, the presenter reads closely: small omissions and ad-libs are fine, wholesale reformulation is not.**
A take delivered as understanding rather than reading had 46% word coverage, and
alignment recovered only 8 of 18 beats.

**Record which takes are rejected and exclude them from every downstream artifact, and say so in the artifact.**
One rejected take transcribed as a single sentence repeated 78 times at collapsed
timestamps; it looked like a transcript and was not one.

## Screen lane and pointer

**Write a shot contract before capture: for every spoken cue, the visible state, the pointer behavior and an observable pass condition.**
A page load is not a visual pass, and a clip's label is not its content. Encode hard stops as pass conditions, for
example "an empty notes field is a hard stop; do not say this line."

**Every graph or diagram introduction starts with a fit-to-view establishing frame; detail pans follow.**
Move the pointer off the fit button afterwards, or its tooltip stays in the shot.

**Lock window size, crop, browser zoom, app density and side-nav state before the first clip, and never change them between clips.**
Clip joins are only invisible when both sides share geometry. Record URL, scroll
position, open panel, tab order, pointer position and zoom at each end of a
join, and keep at least one second of still handle.

**Pre-fill anything typed on camera, except the one field the viewer must watch being set.**
URL query parameters can fill forms; the action the beat is about still happens
on camera.

**Check that a click target is not under an in-page overlay, not just inside the viewport.**
A node inside the viewport but under a 240 px navigation rail had its click
intercepted.

**Move the real OS pointer with a native helper at 120 Hz using absolute per-step deadlines, and post mouse-moved events rather than warping.**
`cliclick` takes about 102 ms per move and cannot animate. A 600 ms move with fixed
sleeps measured 803 ms. Warps do not reset the HID idle timer and produced 19
minutes of lock screen.

**Pointer motion should read as a hand: longer moves take longer, the pointer waits for its target to stop moving, settles before the click, and parks clear of text.**
Scrolls use the same ease-in-out curve as the pointer so content and cursor share
a feel.

**Probe the pointer helper before any take: move 100 px, read back, fail on a miss over 4 px.**
Without Accessibility permission every click is invisible. Do not re-probe after
the recorder has started; it can race the recorder's focus handoff.

**Fail closed on nondeterministic on-screen output: assert the AI answer's content before continuing.**
A clip labeled as a permission refusal actually showed the action being prepared.
The label passed; the footage contradicted the narration.

## Capture

**Record screen, camera and mic in one Camtasia session so the `.trec` holds all three in sync.**
One recording removes clap-sync and drift between lanes. The camera take stays
the audio source; screen footage is placed under it.

**Copy the recording out of Camtasia's Temporary Recordings folder into the project bundle immediately.**
`cp -c` clones on APFS, so it is instant and costs no disk. An entire screen
lane once vanished from the temporary folder, and every later edit had to work
from 1080p exports, which is why tight zooms were soft.

**The `.trec` stores the pointer separately from the screen pixels; audit its path, not just the frames.**
The pointer is not in the TSCC2 frames. The `TSCM` atom holds the pointer path.
Auditing it against the planned framing caught a pan that moved the row the
presenter was pointing at out of frame, which pixel stills could never show.

**Keep the menu bar, clock, recording timer and notifications out of the frame, and check a frame to prove it.**
Camtasia captured a 66 px menu bar strip on a Retina display; crop it or zoom it
out (see the zoom rules below).

**Convert HDR screen recordings to SDR BT.709 before mixing them with SDR footage.**
A macOS Screen Recording `.mov` came in as PQ BT.2020 and looked washed out next
to the rest. Convert through a LUT, strip inherited tags, and verify primaries,
transfer and matrix on the output.

**Capture only the target app window for any screenshot, or ask the user.**
A whole-screen screenshot captured an unrelated private chat the user had open.

## Camtasia project editing

**Never edit a project file Camtasia has open. Ask the user to save and close, back up `project.tscproj`, then edit.**
Camtasia holds the project in memory and overwrites edits on save. A
`~project.tscproj` file next to the project means it is open. Snapshot the
project before every pass; nine snapshots made every pass reversible.

**Generate the project from an edit manifest, starting from a working `project.tscproj` as a template and replacing only what you own.**
Keep narration, screens, presenter inset and full-frame speaker on separate named
tracks so each clip stays individually retimable. Copy `bookmarks.plist` and
`docPrefs` from a working bundle; the Open dialog expects them.

**Make the bundle self-contained: every source copied in and referenced by relative path, and assert every source exists before writing.**
A project that depended on the temporary recordings folder broke when that folder
was cleaned. Keep originals in the bundle so the project can be re-edited later.

**Time is in ticks at the project's `editRate`; quantize to frames with `tick` in `skills/screencast-editor/scripts/camtasia_model.py`.**
Unquantized ticks put cut points between frames. Clip `start`, `duration`,
`mediaStart` and `mediaDuration` are ticks; keyframe times are ticks relative to
the clip start.

**Retime a clip with Camtasia's native clip speed or trims, never by re-rendering.**
Native speed and trims leave the narration untouched and the edit editable; the
storage format is in `skills/screencast-editor/references/camtasia-format.md`.

**Zoom and pan are native keyframe animations; generate them with `build` in `skills/screencast-editor/scripts/build-project.py` rather than writing the JSON by hand.**
An ease-in-out ending on the cue reads well. Establish wide, enlarge the named
item, return wide.

**Translation is center-relative in canvas pixels, with `translation1` positive up; clamp so no canvas edge is ever exposed.**
The framing and its clamps, including the menu-bar floor, live in `frame` and
`min_zoom` in `skills/screencast-editor/scripts/camtasia_model.py`; call them
rather than recomputing. Compute against the visual area, never its padding.

**Push screen footage in about 6% (zoom 1.06) so the macOS menu bar and clock never show, and clamp every zoom and pan so the menu bar stays hidden.**
A pan clamped only to the canvas edge can still slide the menu bar back into view.

**Frame text views (issues, docs) as the whole text column, at a zoom that keeps the column left of a bottom-right inset.**
On a 1920x1080 canvas, 1.4 framed a GitHub issue; 2x cut words off at the left
edge.

**When swapping a higher-resolution source into a framed clip, multiply the existing scale default and every keyframe by the fit ratio.**
Framing stays identical and the clip gains source detail instead of enlarging a
reduction.

**Verify every ffmpeg-made asset opens in Camtasia, and give a replacement a new filename.**
Camtasia rejected one hardware-encoded stitched asset with OSStatus -19 and fell
back silently; a CPU-encoded version loaded. It caches media by filename.

**A circular inset is native: `RoundCorners` at half the square's size, then an alpha-aware `Border`, on a square source.**
A rectangle with a graphic over its corners breaks on every move.

**Preserve user-applied effects across regenerations, and assert the narration track is unchanged by every visual pass.**
The user added AI Noise Removal in the editor; every generated pass asserted the
narration track equaled the base project's.

**Assert invariants on every generated project: screen lane contiguous, total duration equal to the narration edit, every source path resolves, every keyframe inside its clip, every `mediaStart + duration` inside its source.**
These asserts caught gaps and overruns before the user opened the project.

**Export the final from Camtasia, not ffmpeg, once Camtasia holds effects ffmpeg does not.**
An ffmpeg reference master predates noise removal and zooms; say so in its notes.

## Editorial structure

**Speaker-first edit: the presenter owns the opening, commentary and close; the screen appears only while the words point at it.**
Arguments, jokes, recaps and the closing invitation go on camera. A 71-second
argument moved to camera and the screen returned on the sentence that named
evidence, which also fixed a stretch of thin footage.

**Cut only at sentence boundaries, using word onsets, and close on a stable frame with a one-second tail.**
Store edit rows in untrimmed source seconds so a phrase found in the
transcript pastes straight in; `build-project.py` converts them to timeline ticks.

**Find head and tail trim with `silencedetect`.**
It found 7.67 s of leading silence on one take; trimming just inside that kept the
first word's breath.

**Full-frame speaker cutaways sit on a top track using the original camera stream, with audio muted.**
The inset disappears under the cutaway without extra keyframes, and muting stops
the camera audio doubling the narration.

**Never finish a zoom-out just before a cut, and never leave a visible shot under one second.**
Six zoom-outs finished 0.1 s before camera cuts and read as twitches; hide the
reset under the cutaway instead. A 0.37 s flash of another shot was removed. For reading
time, hold a freeze; never invent motion.

**When the narration names a live counter or proof, show it, even if that means leaving the camera early.**
Cutting back to a queue on "so now we have nine open tickets" and holding the real
counter for nine seconds made the claim checkable.

**Never let footage assert a state the narration contradicts.**
"The agent is drafting now" played over a run already waiting for input. Replace
the shot with honest footage from another clip rather than keeping a wrong one.

**Move the inset out of the way of the text being read, per section, by splitting the inset clip at section boundaries.**
Keep `mediaStart` advancing with each split so the presenter stays in sync with
the audio.

## Captions

**Take word onsets from Camtasia's own speech recognition, not Whisper; then correct the words.**
Measured against the audio, the first word began at 1.45 s: Camtasia said 1.31 s,
Whisper 0.96 s. Whisper remains useful for aligning a script to a take, with an
`initial_prompt` naming the proper nouns, but its timings are too early for
highlight captions.

**Captions are corrected English, not verbatim.**
Fix misrecognitions, add punctuation (Camtasia starts a new caption block per
sentence), drop false starts and fix grammar. The presenter rejected a verbatim
pass: "I show you" must read "I showed you".

**When a false start collapses into fewer words, give the kept words the timing of the last words spoken.**
Otherwise the highlight runs ahead of the voice.

**Keep Camtasia pause markers only at sentence ends.**
Its markers include mid-sentence hesitations, and those blank the caption
mid-sentence.

**Size dynamic captions around the inset: two lines of 64 pt in a 700 px box centered near the bottom.**
The default preset (three lines, 96 pt, full width) collided with a bottom-right
inset.

## Rendering and verification

**Decode TSCC2 from the start for any frame whose timing matters; never seek with `-ss` before `-i`.**
Fast input seeking landed several seconds off, and a proxy still showed the
previous page. Use an fps filter and select by frame number, including for
scene-change detection. Input seeking is fine on h264 renders.

**Build a rendered screen lane as contiguous segments on a frame grid and throw on any gap or overlap.**
Force frame counts with `-frames:v` and verify them with `ffprobe`.

**Normalize loudness in two passes to -16 LUFS integrated and -1.5 dBTP, and verify on the final audio.**
One take measured -30.13 LUFS in and -15.98 LUFS out.

**Look at the pixels, and check the measuring instrument before concluding the measured thing regressed.**
Nine defects, including a lock screen, the wrong app and a spinner in the payoff,
passed every automated check.

**Review the settled framing of every cue (the stills `framing-stills.py` renders), and review the cut with narration over it, never the silent screen lane.**
OCR of sampled frames is a hint, not a pass; UI text OCRs as noise.

**Verify framing against source frames, then require the human's playback review in Camtasia.**
Framing math can be right while the playhead shows something else.

## Process

**Ship the first usable artifact immediately; improvements are follow-ups.**
A passing take once sat undelivered for nine hours while a better score was chased.

**Never edit a script while its interpreter runs it, and remember a syntax check is not evidence the code runs.**
Bash reads scripts incrementally; a fatal reference error passed `node --check`.

**When re-narrating over existing footage, re-align every clip to the new audio.**
Old ticks are not reusable; a longer hook changed which shot the next beat had to
open on.

**Preserve every intermediate and write each editorial variant to a new `.cmproj`; never overwrite the approved one.**
Lost raw recordings were survivable only because per-clip exports and their
manifest existed.

**A closed-out approval record says what it does not certify, with dates taken from artifacts.**
Checked rows refer to the footage they were checked against, not to a later
re-narration.

**YouTube chapters start at 0:00 and obey the length and count limits in `chapters.py`; take their times from caption words minus the head trim.**
Recheck chapters, title and thumbnail whenever the editorial timeline changes.

**When no speaker photo is configured, use a frame from the camera track for the thumbnail.**
It is a real photograph of the speaker, which the thumbnail rules require.
