#!/usr/bin/env python3
"""Point Ubuntu archive and security apt pockets at chosen mirror hosts.

CI installs system dependencies from Ubuntu's archives, and a degraded archive
host stalls the whole job. Retrying needs the sources rewritten to a different
official host — but only the Ubuntu ones: a PPA or third-party repo on the
runner must be left exactly as it was.

The archive and security pockets are rewritten independently, because they can
fail independently and a runner may serve both from the same host. That makes
the URI useless as a discriminator, so the pocket is read from the SUITE:

- deb822 (`*.sources`): a stanza's `URIs:` belongs to the `Suites:` beside it,
  so stanzas are parsed as units rather than matched line by line.
- legacy (`*.list`): `deb [opts] <uri> <suite> ...`, where the options are one
  bracketed group that may contain spaces. The field after the URI is the
  suite; the first non-bracket token is the URI, not the suite.

Stdout is one JSON object naming the chosen hosts and the files actually
changed. Exit 0 on success; a path that does not exist is skipped rather than
treated as an error, since the caller passes globs that may not match on every
runner image.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Official Ubuntu archive and security hosts, with or without a regional or
# cloud prefix (`azure.archive.ubuntu.com`). Nothing else is ever rewritten.
OFFICIAL = re.compile(
    r"https?://(?:[a-z0-9.-]*\.)?(?:archive|security)\.ubuntu\.com/ubuntu/?"
)
LEGACY = re.compile(r"^\s*(?:deb|deb-src)\s+(?:\[[^\]]*\]\s+)?\S+\s+(?P<suite>\S+)")


def host_for(suites: str, archive: str, security: str) -> str:
    """Return the host serving a stanza, decided by its suite names."""
    return security if any(s.endswith("-security") for s in suites.split()) else archive


def rewrite_deb822(text: str, archive: str, security: str) -> str:
    stanzas = []
    for stanza in text.split("\n\n"):
        suites = ""
        for line in stanza.splitlines():
            if line.lower().startswith("suites:"):
                suites = line.split(":", 1)[1]
        if suites:
            stanza = OFFICIAL.sub(host_for(suites, archive, security), stanza)
        stanzas.append(stanza)
    return "\n\n".join(stanzas)


def rewrite_legacy(text: str, archive: str, security: str) -> str:
    lines = []
    for line in text.splitlines():
        match = LEGACY.match(line)
        if match:
            line = OFFICIAL.sub(host_for(match.group("suite"), archive, security), line)
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def rewrite_file(path: Path, archive: str, security: str) -> bool:
    """Rewrite one source file in place; return whether it changed."""
    if not path.is_file():
        return False
    body = path.read_text(encoding="utf-8")
    rewriter = rewrite_deb822 if path.suffix == ".sources" else rewrite_legacy
    rewritten = rewriter(body, archive, security)
    if rewritten == body:
        return False
    path.write_text(rewritten, encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "usage: apt_set_mirror.py <archive-host> <security-host> <source-file>...",
            file=sys.stderr,
        )
        return 2
    archive, security = argv[0], argv[1]
    rewritten = [
        str(path)
        for path in (Path(raw) for raw in argv[2:])
        if rewrite_file(path, archive, security)
    ]
    print(
        json.dumps(
            {
                "schema_version": 1,
                "archive": archive,
                "security": security,
                "rewritten": rewritten,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
