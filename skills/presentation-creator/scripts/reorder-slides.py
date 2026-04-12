#!/usr/bin/env python3
"""Reorder a slide in a PowerPoint deck (move from one position to another).

Usage:
    reorder-slides.py <deck.pptx> --from <index> --to <index>

    Indices are 0-based.

Examples:
    reorder-slides.py presentation.pptx --from 5 --to 2
    reorder-slides.py presentation.pptx --from 0 --to 10
"""

import argparse
import sys
from pptx import Presentation

parser = argparse.ArgumentParser(description="Reorder a slide in a PowerPoint deck.")
parser.add_argument("deck", help="Path to .pptx file")
parser.add_argument("--from", dest="from_idx", type=int, required=True, help="Source index (0-based)")
parser.add_argument("--to", dest="to_idx", type=int, required=True, help="Target index (0-based)")
args = parser.parse_args()

prs = Presentation(args.deck)
xml_slides = prs.slides._sldIdLst
slides_list = list(xml_slides)

if args.from_idx >= len(slides_list):
    print(f"ERROR: --from {args.from_idx} out of range (deck has {len(slides_list)} slides)", file=sys.stderr)
    sys.exit(1)

slide = slides_list[args.from_idx]
xml_slides.remove(slide)
if args.to_idx >= len(list(xml_slides)):
    xml_slides.append(slide)
else:
    xml_slides.insert(args.to_idx, slide)

prs.save(args.deck)
print(f"Moved slide {args.from_idx} -> {args.to_idx}. Saved to {args.deck}")
