# QR Generation Rules

## ALWAYS Use generate-qr.py

ALWAYS use `generate-qr.py` for QR code generation. NEVER call the `qrcode`
library directly or generate QR images through any other means.

The script handles URL shortening, tracking DB updates, color matching, and
secrets management. Skipping it silently drops all of those.

When the target is not a .pptx deck (e.g., presenterm, PDF, or standalone PNG),
use `--png-only` mode:

```bash
python3 generate-qr.py --png-only --talk-slug SLUG --shownotes-url URL \
    --output /path/to/qr.png --bg-color "128,0,128"
```

This generates the QR PNG with proper shortening, tracking, and color matching
— without requiring a deck file.
