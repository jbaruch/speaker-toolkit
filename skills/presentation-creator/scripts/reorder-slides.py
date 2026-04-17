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


def reorder_slide(prs, from_idx, to_idx):
    """Move a slide from one position to another (0-based indices).

    Returns the actual destination index used.
    """
    xml_slides = prs.slides._sldIdLst
    slides_list = list(xml_slides)

    if from_idx >= len(slides_list):
        raise IndexError(f"--from {from_idx} out of range (deck has {len(slides_list)} slides)")

    slide = slides_list[from_idx]
    xml_slides.remove(slide)
    if to_idx >= len(list(xml_slides)):
        xml_slides.append(slide)
    else:
        xml_slides.insert(to_idx, slide)
    return to_idx


def main():
    parser = argparse.ArgumentParser(description="Reorder a slide in a PowerPoint deck.")
    parser.add_argument("deck", help="Path to .pptx file")
    parser.add_argument("--from", dest="from_idx", type=int, required=True, help="Source index (0-based)")
    parser.add_argument("--to", dest="to_idx", type=int, required=True, help="Target index (0-based)")
    args = parser.parse_args()

    prs = Presentation(args.deck)
    try:
        reorder_slide(prs, args.from_idx, args.to_idx)
    except IndexError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    prs.save(args.deck)
    print(f"Moved slide {args.from_idx} -> {args.to_idx}. Saved to {args.deck}")


if __name__ == "__main__":
    main()
