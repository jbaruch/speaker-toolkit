# Caption Corrections

Captions show what the speaker said, cleaned of the slips that read worse than
they sound. Start from the clip's words in `words.json`, between `start` and
`end`, and change only what this page allows. The renderer aligns the result
back onto the speech and refuses captions that stray too far from it; its
limits are the named constants in
`skills/shorts-producer/scripts/render-short.py`.

## Allowed

- **Grammar slips:** "she have" becomes "she has", "you use more tokens" (meant
  as past) becomes "you used more tokens", a dropped article goes back in.
- **Stutters and repeats:** "it's it's going" becomes "it's going".
- **False starts:** "and the, the agent then" becomes "the agent then"; a
  restarted sentence keeps only the version the speaker finished.
- **Fillers:** "um", "uh", and "like" or "you know" used as filler.
- **Recognition errors:** a name, product or term the transcriber misheard
  ("Brand" for "Brent", "cloud code" for "Claude Code"). Check the deck and the
  analysis for the right spelling.
- **Spoken contractions:** "gonna", "wanna" may become "going to", "want to".
- **Punctuation and casing:** free. Sentence ends matter: a caption block
  breaks after one.

## Not Allowed

- Paraphrasing, shortening a sentence, or swapping a word for a better one.
- Reordering words or sentences.
- Adding anything the speaker did not say, beyond a dropped article or
  auxiliary.
- Removing a qualification, a hedge or a punchline.

When in doubt, keep the spoken word. After rendering, every edit appears in
the result's `caption_edits`; each one should be a correction from the
Allowed list.
