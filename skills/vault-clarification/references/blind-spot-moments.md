## 5A-bis. Blind Spot Moments

The skill can only analyze transcripts (speech) and
slides (visuals). It CANNOT observe audience reactions, physical performance, stage
movement, costume/prop moments, room energy, or laughter/applause. During analysis,
flag moments where the transcript or slides suggest something happened that the skill
cannot measure — then ask the speaker about each one. Examples:
- **Costume/prop moments**: Slides show a theatrical transition but transcript has no
  audience reaction — "The BTTF transition slide suggests a costume change. How did the
  audience react?"
- **Physical comedy/stage business**: Transcript shows a pause or laughter cue but no
  verbal content — "There's a gap here. Were you doing something physical on stage?"
- **Audience energy shifts**: Show-of-hands results are mentioned but enthusiasm level
  is invisible — "You asked for a show of hands on TDD. Was it enthusiastic or reluctant?"
- **Demo reactions**: Live demos create visible reactions not captured in speech —
  "The demo section has minimal dialogue. Was the audience engaged or checking phones?"
- **Room context**: Packed/empty, post-lunch slot, competing sessions, technical failures —
  "Anything about the room or timing that affected delivery?"

These blind spots are inherent to transcript+slides analysis. Asking about them captures
data that no amount of parsing can recover. Store responses as `blind_spot_observations`
in the talk's tracking DB entry and integrate into the rhetoric summary.
