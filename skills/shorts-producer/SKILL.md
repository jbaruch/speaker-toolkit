---
name: shorts-producer
description: >
  Turn a processed talk into vertical shorts: pick its most shareable takes
  from the finished vault analysis, then render each as a 1080x1920 video with
  the hook headline, the deck slide timed to the talk, a face-tracked crop of
  the speaker, a shownotes QR code, and live captions that highlight each word
  as it is spoken, lightly corrected while still matching the speech. Use when
  the user asks for shorts, reels, TikToks, vertical clips, social clips or
  viral moments from a talk, or wants captions fixed on one.
user_invocable: true
---

# Shorts Producer

Process steps in order. Do not skip ahead.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
vault, recording, and output paths remain consumer-owned.

This skill runs on macOS: it needs ffmpeg, pdftoppm, swift (Apple Vision) and
the vault venv's mlx-whisper. Every script prints diagnostics on stderr, exits
2 on a usage error, and on a refusal prints `{"ok": false, "error"}` and exits
1; the error says what to change.

## Step 1 — Resolve the interpreter

```bash
python3 "{speaker_toolkit_root}/skills/screencast-recorder/scripts/resolve-interpreter.py" <vault_root>
```

Stdout: `{"ok": true, "python_path", "vault_root", "database"}`. Use
`python_path` for every command below. On exit 1, repair through
`Skill(skill: "vault-ingress")`. Proceed immediately to Step 2.

## Step 2 — Read the talk

```bash
{python_path} "{speaker_toolkit_root}/skills/vault-ingress/scripts/read-tracking-database.py" <database>
```

Find the talk the user named in `database.talks[]`. It must have `status`
`processed`; otherwise finish here and tell the user to process it with
`Skill(skill: "vault-ingress")` first. Note `filename`, `title`, `conference`,
`video_url`, `shownotes_url`, `slides_local_path`, `pattern_observations`,
`humor_postmortem` and `verbatim_examples`, the matching `qr_codes[]` entry
(`talk_slug`, `short_url`), and the speaker profile's `speaker.handle` and
`speaker.website` from `<vault_root>/speaker-profile.json`. A talk without a
deck PDF at `slides_local_path` cannot be rendered; finish here and say so.
Proceed immediately to Step 3.

## Step 3 — Get the recording

Pick a local work folder, `~/Library/Caches/speaker-toolkit/shorts/<talk
filename stem>/`, never a cloud-synced one. When the user has a local
recording of the talk, use it. Otherwise download the best stream up to 2160p
with the vault's yt-dlp:

```bash
{python_path} -m yt_dlp -f "bv*[height<=2160]+ba/b[height<=2160]" --merge-output-format mkv -o "<work_dir>/source.%(ext)s" <video_url>
```

The face crop is cut from this file, so take the highest resolution offered.
Proceed immediately to Step 4.

## Step 4 — Pick the takes

Read the talk's analysis at `<vault_root>/analyses/<filename>` and its timed
transcript at `<vault_root>/transcripts/<youtube_id>.segments.json`, then
choose takes as [skills/shorts-producer/references/clip-selection.md](references/clip-selection.md)
describes. Write `plan.json` in a `shorts/` folder inside the talk's own
working folder (the folder that holds its deck build); ask the user where that
is when the record does not make it clear. Its shape is the docstring of
`{speaker_toolkit_root}/skills/shorts-producer/scripts/shorts_plan.py`. Fill
the plan's top level and each clip's `id`, `title`, `hook`, `start`, `end` and
`rationale` now. Set `qr_url` to the `qr_codes[]` `short_url`, else
`shownotes_url`, else null. Proceed immediately to Step 5.

## Step 5 — Prepare each clip

```bash
{python_path} "{speaker_toolkit_root}/skills/shorts-producer/scripts/prepare-clip.py" --plan <plan.json> --clip <id>
```

Run it once per clip. Stdout names `words` (measured word timings in source
seconds), `frames`, `faces`, `contact` (a frame every two seconds with a 10%
grid and red boxes on detected faces) and `deck_contact` (numbered deck
pages). Proceed immediately to Step 6.

## Step 6 — Finish each plan entry

For every clip, look at its `contact.jpg` and the deck's `contact.jpg`, read
its `words.json`, and fill in:

- `start` and `end` on word boundaries from `words.json`, so the clip opens on
  its first word and ends after its payoff. A boundary outside the prepared
  window means re-running Step 5 for that clip.
- `speaker_region`: the normalized `[x, y, w, h]` box the speaker stays inside
  for the whole clip, leaving out faces on the projected slides and in the
  audience.
- `slides`: `[clip offset seconds, deck page]` pairs, starting at 0, for each
  slide shown on the stage screen. Open individual `frames/<seconds>.jpg` to
  pin a change to the half second.
- `captions`: the spoken words, corrected as
  [skills/shorts-producer/references/caption-corrections.md](references/caption-corrections.md)
  allows.

Proceed immediately to Step 7.

## Step 7 — Render each clip

```bash
{python_path} "{speaker_toolkit_root}/skills/shorts-producer/scripts/render-short.py" --plan <plan.json> --clip <id>
```

Stdout: `{"ok": true, "video", "srt", "txt", "duration", "caption_edits",
"crop"}`, the files landing in the plan's `out_dir`. Read `caption_edits`:
every entry must be a correction you meant. A refusal that says the captions
stray from the speech means correcting less, then re-running this step.
Proceed immediately to Step 8.

## Step 8 — Verify each clip

```bash
{python_path} "{speaker_toolkit_root}/skills/shorts-producer/scripts/verify-short.py" --plan <plan.json> --clip <id>
```

Exit 0 means every check passed; exit 1 lists `failures`. Open `review` (six
frames) and check that the speaker stays framed, the slide matches what was on
stage, and nothing overlaps the captions. Fix the plan entry and return to
Step 7 for any clip that fails or looks wrong. Proceed immediately to Step 9.

## Step 9 — Present the shorts

List each short with its file path, hook, duration and caption edits, and the
`review.jpg` path. Uploading and posting stay with the user. Finish here.
