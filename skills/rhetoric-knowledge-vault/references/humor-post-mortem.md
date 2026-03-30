## 5A-ter. Humor Post-Mortem

The skill can identify jokes from transcripts and
slides but CANNOT hear laughter. For every talk processed in this run, compile the
humor beats detected in dimension 3 and walk through them with the speaker:

1. **List every joke/humor beat** identified in the analysis (verbatim quote or slide
   reference). For each one, ask: "Did this land? Big laugh, knowing nods, or flat?"
2. **Meme slides**: For meme-only or meme-with-text slides, ask if the audience
   visibly reacted or if the meme was more of a visual punchline the speaker talked over.
3. **Spontaneous humor**: Ask if there were jokes NOT on the slides that happened
   in the moment — audience riffs, improvised callbacks, heckler interactions, recovery
   humor from demo failures. These are invisible to the skill but often the best material.
4. **Humor grading**: For each confirmed-landed joke, tag it in the DB with
   `humor_grade: "hit"|"nod"|"flat"|"spontaneous_hit"`. Over time this builds a
   corpus-wide humor effectiveness map — which joke TYPES land (self-deprecating,
   industry snark, meme-as-punchline, callback) and which fall flat.
5. **Promote to portfolio**: If a spontaneous joke landed well, ask the speaker if
   it should be promoted to a planned beat in future deliveries (like the therapy
   analogy from QCon London 2026).

This is particularly important for recent talks where memory is fresh. For older talks
(2+ years), compress to: "Any jokes you remember landing particularly well or badly?"

Store results in `humor_postmortem` on the talk's DB entry and update the rhetoric
summary Section 3 (Humor & Wit) with confirmed effectiveness data.
