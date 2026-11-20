# Publishing Workflow

Input: approved talk directory, deck path, requested outputs, and supplied URLs.
Read `publishing_process` from the profile. Ask for missing workflow choices one
at a time. Load each action reference only when that action is enabled/in scope.
Before paired external/tracking effects, resolve the shared runtime without
`--read-only`, re-read current inputs, and use the owner mutation contract.
Never require all services' secrets as a global pre-flight.

1. Curate requested resources with [resources.md](resources.md); the speaker
   approves candidates before a page consumes them. Extraction alone is local.
2. If the shownotes destination needs an exported/uploaded deck first, invoke
   `Skill(skill: "presentation-builder")` for that prerequisite export and wait
   for its verified output. For Jekyll slide PDFs, follow
   [Slide PDF Hosting](../../shownotes-publisher/SKILL.md#slide-pdf-hosting).
3. If shownotes are enabled, read [shownotes.md](shownotes.md). For Jekyll, invoke
   `Skill(skill: "shownotes-publisher")` with the approved resources, the PDF
   export path, and any known Drive file ID or URL. Resume here at live-URL
   verification and tracking persistence.
4. If QR is enabled, read [qr.md](qr.md); use the verified destination, confirmed
   slug, configured provider, and final post-build deck. Replace existing QRs.
5. If export is configured/requested, invoke `Skill(skill: "presentation-builder")`
   with action export after QR insertion. This final export includes the QR;
   update a previously uploaded export if the configured publication requires it.
   For a final export replacing a Jekyll slide PDF, follow
   [slide PDF verification](../../shownotes-publisher/references/slide-pdf-verification.md)
   before reporting the slides published.
6. Read [delivery.md](delivery.md) for requested timing files, authorized additional
   steps, and the go-live checklist. A reminder to send follow-up messages does
   not authorize sending them.

Finish with a report covering each requested action's DONE/SKIP/TODO status,
verified live URLs, deck/PNG/export/timer paths, shortener used, tracking outcome,
and remaining speaker actions. A failed URL, provider call or tracking commit
remains an explicit incomplete result; preserve the script's landed-effect and
rollback receipts. Do not report an unverified destination as published.

Post-event requests enter `Skill(skill: "illustrations")` for a thumbnail or
`Skill(skill: "shownotes-publisher")` for a Jekyll recording update directly.
Other shownotes systems use [recording.md](recording.md) for that action alone.
