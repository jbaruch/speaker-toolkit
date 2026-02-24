# Talk Library Organizer

## Problem/Feature Description

A prolific conference speaker has years of talk materials scattered across directories — markdown files with talk metadata (conference, date, video link, slides link), and PowerPoint files organized by conference and year. They need a system to inventory everything: which talks exist, which have video recordings, which have slide decks, and which are ready for analysis.

The speaker wants a JSON-based tracking database that maps all their talks and presentation files, identifies which talks have enough source material for analysis, and flags which ones are incomplete. Some PowerPoint files are duplicates or static exports and should be filtered out. The system should also try to match presentation files to their corresponding talk metadata entries.

## Output Specification

Produce the following files:

1. **`tracking-database.json`** — A JSON database that tracks all discovered talks and presentation files
2. **`build_tracker.py`** — The Python script that scans the input directories and builds the database
3. **`scan_report.txt`** — A human-readable report summarizing what was found

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/talks/2024-03-15-devops-reframed.md ===============
---
title: "DevOps Reframed"
conference: "DevOps Days Chicago"
date: 2024-03-15
video_url: "https://www.youtube.com/watch?v=abc123def"
slides_url: "https://drive.google.com/file/d/1A2B3C4D5E/view"
---

A talk about rethinking DevOps culture in the age of platform engineering.

=============== FILE: inputs/talks/2024-06-20-supply-chain-security.md ===============
---
title: "Software Supply Chain Security"
conference: "KubeCon EU"
date: 2024-06-20
video_url: "https://www.youtube.com/watch?v=xyz789uvw"
---

Deep dive into securing your software supply chain with SLSA and Sigstore.

=============== FILE: inputs/talks/2024-09-10-ai-testing.md ===============
---
title: "AI-Assisted Testing"
conference: "StarEast"
date: 2024-09-10
---

Exploring how AI can transform software testing practices.

=============== FILE: inputs/talks/2023-11-05-container-myths.md ===============
---
title: "Container Myths Busted"
conference: "DockerCon"
date: 2023-11-05
video_url: "https://www.youtube.com/watch?v=dock3r456"
slides_url: "https://drive.google.com/file/d/9X8Y7Z6W5V/view"
---

Busting common misconceptions about containers.

=============== FILE: inputs/presentations/DevOps Days Chicago/2024/DevOps Reframed.pptx ===============
(Create an empty .pptx file at this path using python-pptx)

=============== FILE: inputs/presentations/DevOps Days Chicago/2024/DevOps Reframed static.pptx ===============
(Create an empty .pptx file at this path — this is a static export that should be skipped)

=============== FILE: inputs/presentations/DevOps Days Chicago/2024/DevOps Reframed (1).pptx ===============
(Create an empty .pptx file at this path — this is a Google Drive conflict copy that should be skipped)

=============== FILE: inputs/presentations/KubeCon/2024/Software Supply Chain Security.pptx ===============
(Create an empty .pptx file at this path)

=============== FILE: inputs/presentations/Templates/Presentation Template DOTCs 2023.pptx ===============
(Create an empty .pptx file at this path — this is a template that should be skipped)

=============== FILE: inputs/presentations/DockerCon/2023/Container Myths Busted.pptx ===============
(Create an empty .pptx file at this path)

Create the .pptx files using python-pptx (`pip install python-pptx`) as minimal valid presentations with at least one slide each.
