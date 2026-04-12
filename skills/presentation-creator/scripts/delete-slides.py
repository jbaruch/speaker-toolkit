#!/usr/bin/env python3
"""Delete slides from a PowerPoint deck by index (0-based).

Usage:
    delete-slides.py <deck.pptx> 5 12 15

    Indices are 0-based. Deletes in reverse order to preserve indices.

Examples:
    delete-slides.py presentation.pptx 0 5 10
"""

import sys
from pptx import Presentation

if len(sys.argv) < 3:
    print(f"Usage: {sys.argv[0]} <deck.pptx> <index1> [index2] ...", file=sys.stderr)
    sys.exit(1)

deck_path = sys.argv[1]
indices = sorted(set(int(i) for i in sys.argv[2:]), reverse=True)

prs = Presentation(deck_path)
xml_slides = prs.slides._sldIdLst

for idx in indices:
    slides_list = list(xml_slides)
    if idx >= len(slides_list):
        print(f"WARNING: slide index {idx} out of range (deck has {len(slides_list)} slides)", file=sys.stderr)
        continue
    slide_to_delete = slides_list[idx]
    rId = slide_to_delete.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
    prs.part.drop_rel(rId)
    xml_slides.remove(slide_to_delete)
    print(f"Deleted slide {idx}")

prs.save(deck_path)
print(f"Saved to {deck_path}")
