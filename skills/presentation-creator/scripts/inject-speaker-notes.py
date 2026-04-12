#!/usr/bin/env python3
"""Inject speaker notes into a PowerPoint deck from a JSON map.

The JSON file maps slide indices (0-based) to notes text:
  {"0": "", "1": "Brief intro.", "2": "Core argument starts here."}

Usage:
    inject-speaker-notes.py <deck.pptx> <notes.json>

Examples:
    inject-speaker-notes.py presentation.pptx speaker-notes.json
"""

import json
import sys
from pptx import Presentation

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <deck.pptx> <notes.json>", file=sys.stderr)
    sys.exit(1)

deck_path, notes_path = sys.argv[1], sys.argv[2]

with open(notes_path) as f:
    notes_map = json.load(f)

prs = Presentation(deck_path)
injected = 0

for idx_str, notes_text in notes_map.items():
    idx = int(idx_str)
    if notes_text and idx < len(prs.slides):
        slide = prs.slides[idx]
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = notes_text
        injected += 1

prs.save(deck_path)
print(f"Injected speaker notes into {injected} slides. Saved to {deck_path}")
