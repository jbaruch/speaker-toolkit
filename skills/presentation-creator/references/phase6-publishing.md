# Phase 6: Publishing — Detail

The publishing workflow is speaker-specific. Read `publishing_process` from
`speaker-profile.json`. If the section is missing or empty, fall back to asking
the author interactively and document their answers for next time.

### Step 6.1: Export

Read `publishing_process.export_format` and `publishing_process.export_method`.

- If `export_script` is provided, run it (substituting the deck path)
- If `export_method` is a description, follow its instructions
- Common pattern: PowerPoint AppleScript for PDF (see [phase5-slides.md](phase5-slides.md))
- If no export info, ask: "How do you want to export? PDF, keep .pptx only, or both?"

### Step 6.2: Shownotes

Read `publishing_process.shownotes_publishing`. If `enabled`:

- Follow the `method` description (git push, CMS, manual)
- If `shownotes_repo_path` and `shownotes_template` are provided, generate the page
- Include: title, abstract, slide embed/download link, resource links, speaker bio
- Use the `shownotes_url_pattern` from `speaker` to construct the final URL

If not enabled, skip.

### Step 6.3: QR Code

Read `publishing_process.qr_code`. If `enabled`:

- Generate QR code pointing to the shownotes URL (or `target` URL)
- If `insert_into_deck` is true, add to the deck at the specified `slide_position`
- Re-save the deck after insertion

### Step 6.4: Additional Steps

Read `publishing_process.additional_steps[]`. For each entry:

- If `automated` is true and `script` is provided, run it
- If `automated` is false, present the step to the author as a manual TODO
- Report completion status for each step

### Step 6.5: Go-Live Preparation Checklist

Before delivery, surface unobservable patterns from [patterns/_index.md](patterns/_index.md)
(the "Unobservable Patterns — Go-Live Checklist" section) as a preparation reminder.
These are patterns the vault **cannot score retroactively** because they involve
pre-event logistics, physical stage behaviors, or external systems — but they still
matter for delivery quality.

```
GO-LIVE CHECKLIST — {talk title}
==================================
PRE-EVENT:
[ ] Preparation — backups, cables, hydration, room layout check
[ ] Carnegie Hall — completed 4 rehearsals (pace, delivery, fixes, groove)
[ ] The Stakeout — staging area identified near venue
[ ] Posse — supporter(s) confirmed for front row
[ ] Seeding Satisfaction — plan to arrive early and mingle
[ ] Shoeless — comfort ritual ready

DURING DELIVERY:
[ ] Lightsaber — if laser pointer needed, max 2-3 steady moments
[ ] Red/Yellow/Green — exit feedback cards set up (if venue supports)

AVOID:
[ ] Laser Weapons — don't wave the pointer; use built-in highlights
[ ] Bunker — step out from behind the podium
[ ] Backchannel — don't monitor social media during the talk
==================================
```

### Step 6.6: Publishing Report

```
PUBLISHING REPORT — {talk title}
==================================
[DONE/SKIP] Export: {format} → {output path}
[DONE/SKIP] Shownotes: {url or "not configured"}
[DONE/SKIP] QR code: {inserted at slide N or "not configured"}
[DONE/SKIP/TODO] {additional step name}: {status}
[INFO] Go-live checklist: {presented above}
==================================
```
