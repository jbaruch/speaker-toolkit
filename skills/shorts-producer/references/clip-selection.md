# Picking Takes

A take is one complete thought from the talk that works with no context: a
claim with an edge, a story with a payoff, or a joke that landed. There is no
quota. Three strong takes beat six padded ones; a talk with one good take gets
one short.

## Where to Look

The vault already marks the moments worth a second look:

- `humor_postmortem[]` entries graded `hit`, with the speaker's own read of
  the laugh. The strongest single source.
- `pattern_observations.patterns_detected[].evidence_citations[]`. Each
  carries `start_seconds`, `end_seconds`, the `quote` and its `slide_numbers`,
  so a citation for a hook-like pattern is a ready-made candidate window.
- `verbatim_examples` `signature_phrases`, `jokes` and `opening_lines`. They
  carry no timestamps: find them in `transcripts/<youtube_id>.segments.json`.
- `structured_data.per_slide_visual[]` entries whose `content_type` is
  `hot_take`.
- The analysis Markdown's rhetoric notes, for why a moment works.

## What Makes a Take

- **Standalone.** A viewer who saw nothing before it follows it. Drop takes
  that lean on a callback, an earlier definition or "as I said".
- **Opens on the hook.** The first two seconds decide whether anyone stays.
  Start on the provocative line, not the setup before it.
- **Pays off.** It ends on a conclusion, a result or a laugh, never mid-build.
- **Faithful.** One continuous excerpt. Never splice two statements into a
  claim the speaker did not make, and keep a qualification the speaker
  attached ("not because I'm going to punish you").
- **Short.** 20 to 60 seconds. Longer is fine only when the payoff needs it.
- **Has a visual.** A slide that carries the point on its own reads better in
  the top panel than a title slide or a wall of text.

## Hook, Title, Rationale

- `hook`: one or two lines of on-screen text, about six words or fewer each,
  uppercase. The second line is the punch and renders in the accent color.
  Write a thought with an edge, not a topic ("YOUR AI BUDGET / NEEDS A STOP
  BUTTON.", not "AI COST MANAGEMENT"). No clickbait: the clip must deliver
  what the hook promises.
- `title`: the hook as a sentence, for the upload title and file metadata.
- `rationale`: one sentence on why this take stands alone and lands.
- `id`: `NN-slug`, numbered in the order you rank them.
