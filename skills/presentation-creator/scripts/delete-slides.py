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

from _pptx_repair import NS_R, clean_viewprops


def delete_slides(prs, indices):
    """Delete slides at the given 0-based indices.

    Indices are deduplicated and processed in reverse order to preserve
    earlier indices. Out-of-range indices are skipped with a warning.

    Returns list of actually deleted indices.
    """
    indices = sorted(set(indices), reverse=True)
    xml_slides = prs.slides._sldIdLst
    deleted = []

    for idx in indices:
        slides_list = list(xml_slides)
        if idx >= len(slides_list):
            print(f"WARNING: slide index {idx} out of range (deck has {len(slides_list)} slides)", file=sys.stderr)
            continue
        slide_to_delete = slides_list[idx]
        rId = slide_to_delete.get(f'{{{NS_R}}}id')
        prs.part.drop_rel(rId)
        xml_slides.remove(slide_to_delete)
        deleted.append(idx)
        print(f"Deleted slide {idx}")

    clean_viewprops(prs)
    return deleted


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <deck.pptx> <index1> [index2] ...", file=sys.stderr)
        sys.exit(1)

    deck_path = sys.argv[1]
    indices = [int(i) for i in sys.argv[2:]]

    prs = Presentation(deck_path)
    delete_slides(prs, indices)
    prs.save(deck_path)
    print(f"Saved to {deck_path}")


if __name__ == "__main__":
    main()
