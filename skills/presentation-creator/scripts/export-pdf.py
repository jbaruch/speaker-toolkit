#!/usr/bin/env python3
"""Export a PowerPoint deck to PDF via AppleScript (macOS + Microsoft PowerPoint).

Falls back to LibreOffice CLI if PowerPoint is not available.

Usage:
    export-pdf.py <deck.pptx> [<output.pdf>]

    If output.pdf is omitted, uses the same name with .pdf extension.

Examples:
    export-pdf.py presentation.pptx
    export-pdf.py presentation.pptx ~/exports/presentation.pdf
"""

import os
import shutil
import subprocess
import sys

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <deck.pptx> [<output.pdf>]", file=sys.stderr)
    sys.exit(1)

pptx_path = os.path.abspath(sys.argv[1])
if len(sys.argv) >= 3:
    pdf_path = os.path.abspath(sys.argv[2])
else:
    pdf_path = os.path.splitext(pptx_path)[0] + ".pdf"


def try_powerpoint_applescript():
    """Export via Microsoft PowerPoint AppleScript (macOS only)."""
    script = f'''
tell application "Microsoft PowerPoint"
    open POSIX file "{pptx_path}"
    delay 2
    save active presentation in POSIX file "{pdf_path}" as save as PDF
    close active presentation saving no
end tell
'''
    result = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True, text=True, timeout=30
    )
    return result.returncode == 0


def try_libreoffice():
    """Export via LibreOffice CLI."""
    output_dir = os.path.dirname(pdf_path) or "."
    result = subprocess.run(
        ['libreoffice', '--headless', '--convert-to', 'pdf',
         '--outdir', output_dir, pptx_path],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode == 0:
        # LibreOffice names output after the input file
        lo_output = os.path.join(output_dir, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
        if lo_output != pdf_path and os.path.exists(lo_output):
            shutil.move(lo_output, pdf_path)
    return result.returncode == 0


# Try PowerPoint first (macOS), then LibreOffice
if sys.platform == "darwin" and shutil.which("osascript"):
    if try_powerpoint_applescript():
        print(f"Exported via PowerPoint: {pdf_path}")
        sys.exit(0)
    print("PowerPoint export failed, trying LibreOffice...", file=sys.stderr)

if shutil.which("libreoffice"):
    if try_libreoffice():
        print(f"Exported via LibreOffice: {pdf_path}")
        sys.exit(0)

print("ERROR: Neither PowerPoint nor LibreOffice available for PDF export", file=sys.stderr)
sys.exit(1)
