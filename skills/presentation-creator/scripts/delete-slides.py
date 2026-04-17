#!/usr/bin/env python3
"""Delete slides from a PowerPoint deck by index (0-based).

Usage:
    delete-slides.py <deck.pptx> 5 12 15

    Indices are 0-based. Deletes in reverse order to preserve indices.

Examples:
    delete-slides.py presentation.pptx 0 5 10
"""

import sys
from lxml import etree
from pptx import Presentation

NS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'


def clean_viewprops(prs):
    """Remove stale slide references from viewProps.xml after deleting slides.

    PowerPoint stores last-viewed slide lists in viewProps.xml with their own
    relationship entries. If these aren't cleaned up after slide deletion,
    PowerPoint reports the file as corrupted on open.
    """
    for rel in prs.part.rels.values():
        if "viewProps" in rel.reltype:
            vp_part = rel.target_part
            vp_xml = etree.fromstring(vp_part.blob)
            # Remove all <p:sldLst> elements (inside outlineViewPr, slideViewPr, etc.)
            for sld_lst in vp_xml.findall(f'.//{{{NS_P}}}sldLst'):
                sld_lst.getparent().remove(sld_lst)
            vp_part._blob = etree.tostring(vp_xml, xml_declaration=True,
                                           encoding='UTF-8', standalone=True)
            # Remove slide relationships from viewProps rels
            to_drop = [rId for rId, vp_rel in vp_part.rels.items()
                       if "slide" in vp_rel.reltype.lower()]
            for rId in to_drop:
                vp_part.rels.pop(rId)
            break


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
    rId = slide_to_delete.get(f'{{{NS_R}}}id')
    prs.part.drop_rel(rId)
    xml_slides.remove(slide_to_delete)
    print(f"Deleted slide {idx}")

clean_viewprops(prs)

prs.save(deck_path)
print(f"Saved to {deck_path}")
