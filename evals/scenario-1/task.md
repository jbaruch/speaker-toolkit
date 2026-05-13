# Talk Library Organizer

## Problem/Feature Description

A prolific conference speaker has years of talk materials scattered across directories — markdown files with talk metadata (conference, date, video link, slides link), and PowerPoint files organized by conference and year. They need a system to inventory everything: which talks exist, which have video recordings, which have slide decks, and which are ready for analysis.

The speaker wants a JSON-based tracking database that maps all their talks and presentation files, identifies which talks have enough source material for analysis, and flags which ones are incomplete. The directory also contains some PowerPoint files that aren't real presentations. The system should match presentation files to their corresponding talk metadata entries where possible.

The tracking database should be a single JSON file that inventories all discovered talks, catalogs presentation files, stores configuration, and tracks processing readiness.

## Output Specification

Produce the following files:

1. **`tracking-database.json`** — A JSON database that tracks all discovered talks and presentation files
2. **`scan_report.txt`** — A human-readable report summarizing what was found

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

Download the presentation files from the project repository before scanning:
```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-1"
mkdir -p "inputs/presentations/DevOps Days Chicago/2024" "inputs/presentations/KubeCon/2024" "inputs/presentations/DockerCon/2023" "inputs/presentations/Templates"
curl -L -o "inputs/presentations/DevOps Days Chicago/2024/DevOps Reframed.pptx" "$BASE/DevOps%20Days%20Chicago/2024/DevOps%20Reframed.pptx"
curl -L -o "inputs/presentations/DevOps Days Chicago/2024/DevOps Reframed static.pptx" "$BASE/DevOps%20Days%20Chicago/2024/DevOps%20Reframed%20static.pptx"
curl -L -o "inputs/presentations/DevOps Days Chicago/2024/DevOps Reframed (1).pptx" "$BASE/DevOps%20Days%20Chicago/2024/DevOps%20Reframed%20(1).pptx"
curl -L -o "inputs/presentations/KubeCon/2024/Software Supply Chain Security.pptx" "$BASE/KubeCon/2024/Software%20Supply%20Chain%20Security.pptx"
curl -L -o "inputs/presentations/Templates/Presentation Template DOTCs 2023.pptx" "$BASE/Templates/Presentation%20Template%20DOTCs%202023.pptx"
curl -L -o "inputs/presentations/DockerCon/2023/Container Myths Busted.pptx" "$BASE/DockerCon/2023/Container%20Myths%20Busted.pptx"
```

The presentations directory contains 6 `.pptx` files across conference/year subdirectories.
