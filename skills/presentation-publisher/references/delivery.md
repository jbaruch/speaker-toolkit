# Delivery Preparation

**Optional step:** generate a plain-text timing file from `outline.yaml`'s
`chapters[]` (each chapter has `target_min`). Run unless the author opts out.

Source: `chapters[].title` and `chapters[].target_min` in `outline.yaml`.

Generate a plain-text timing file for [timemytalk.app](https://timemytalk.app)
by running:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/generate-talk-timings.py" \
  outline.yaml --output talk-timings.txt

# If the talk slot includes Q&A time:
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/generate-talk-timings.py" \
  outline.yaml --qa 5 --output talk-timings.txt
```

**Format:** one line per chapter, `MM:SS Label`, using cumulative start times.
The final line is always `MM:SS FINISH` where the timestamp equals the total
talk duration (including Q&A if applicable).

**Granularity guidelines:**
- 25-min talks: 8-13 chapters
- 45-60 min talks: 10-15 chapters
- Subdivide chapters exceeding ~5 min into multiple chapters in `outline.yaml`

**Q&A:** if the talk slot includes Q&A time, pass `--qa MINUTES` to append a
Q&A chapter before FINISH.

The speaker uploads the resulting `.txt` file to timemytalk.app before delivery.

## Additional Steps

Read `publishing_process.additional_steps[]`. For each entry:

- If `automated` is true and `script` is provided, run it
- If `automated` is false, present the step to the author as a manual TODO
- Report completion status for each step

## Go-Live Preparation Checklist

Before delivery, surface a delivery-readiness checklist composed of two strands:

1. **Unobservable patterns** from [pattern-menu.md](../../presentation-creator/references/pattern-menu.md) (select phase `publishing`; open only relevant pattern files). These are patterns the vault
   **cannot score retroactively** because they involve pre-event logistics, hidden
   authoring/provenance processes, physical stage behaviors, post-event follow-up,
   or external systems the current artifacts cannot prove.
2. **Observable delivery reminders** that the speaker can decide to apply on the day —
   venue setup choices (lights, lectern, mic), opening discipline, time discipline,
   and screen-blackout tactics. These *are* observable post-talk, but the speaker
   benefits from a pre-talk reminder regardless of the vault's ability to score them
   later.

Both strands matter for delivery quality and belong in the same checklist.

```
GO-LIVE CHECKLIST — {talk title}
==================================
VENUE SETUP:
[ ] Lights ON — keep light on the speaker (Reynolds: audience must see your face;
    they cannot read facial expressions in the dark; dim only the screen-area lights
    if the projector requires it)
[ ] Lectern moved aside — step out from behind any podium or table; place computer
    on the floor in front of the stage so you don't have to turn back to advance slides
[ ] Mic test — wireless lavalier or headset preferred over handheld; do not rely on
    shouting

PRE-EVENT:
[ ] Know Your Audience — audience/organizer research captured; concrete adaptations noted
[ ] Required — mandatory/assigned context confirmed and used deliberately as practice
[ ] Fourthought — ideation/capture/organization completed before slide authoring
[ ] Proposed — accepted CFP artifact retained; final scope checked against its promises
[ ] Concurrent Creation — one Slide Wrangler named; collaboration history retained
[ ] Peer Review — colleague/editor review completed; comments retained
[ ] Social Media Advertising — dated promotional posts published and retained, if relevant
[ ] Preparation — backups, cables, hydration, room layout check
[ ] Carnegie Hall — completed 4 rehearsals (pace, delivery, fixes, groove)
[ ] The Stakeout — staging area identified near venue
[ ] Posse — supporter(s) confirmed for front row
[ ] Seeding Satisfaction — plan to arrive early and mingle
[ ] First Impression — pre-event communications (invitation tone, agenda
    framing, bio wording) have already shaped the audience's view of you
    before you walk in; the room you walk into builds on that. Do NOT
    arrive heads-down at the laptop fixing slides. Engage warmly with
    early-arrivers, shake hands, ask questions. The mood you project
    before the talk starts is part of the talk.
[ ] Shoeless — comfort ritual ready

DURING DELIVERY:
[ ] Honeymoon-window discipline — first 1–2 minutes earn the talk; do NOT spend
    them on agenda slides, "let me introduce myself," or "thanks for the invitation"
    filler. Open with the planned PUNCH hook (see outline)
[ ] Never apologize, never confess nerves — both are self-focused at a moment that
    should be audience-focused. Acknowledge nerves to yourself; do not share them
    with the audience
[ ] Hara hachi bu — finish at 90–95% of the allotted time, never run over;
    "leave them slightly hungry, not stuffed"
[ ] Screen Blackout — use the B key (or planned black slides) at section boundaries,
    personal stories, and audience-question moments to redirect attention
[ ] Lightsaber — if laser pointer needed, max 2-3 steady moments
[ ] Red/Yellow/Green — exit feedback cards set up (if venue supports)

AVOID:
[ ] Abstract Attorney — compare the final talk directly with the accepted abstract
[ ] Borrowed Shoes — confirm authorship and substantially adapt borrowed material
[ ] Laser Weapons — don't wave the pointer; use built-in highlights
[ ] Bunker — step out from behind the podium
[ ] Backchannel — don't monitor social media during the talk

POST-EVENT:
[ ] Crucible — record feedback and the concrete revisions made before the next delivery
[ ] Spaced Follow-Up — after 1–2 weeks, send opt-in attendees 2–3 recall questions
==================================
```
