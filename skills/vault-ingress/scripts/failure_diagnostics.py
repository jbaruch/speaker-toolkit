#!/usr/bin/env python3
"""Path-neutral outer-boundary diagnostics shared by vault-ingress entrypoints.

Every deterministic entrypoint here has the same caller contract: a non-zero
exit without the documented document is read as a silent failure, so an
unhandled exception must not reach the caller as a traceback. Each entrypoint
therefore closes its outer boundary and emits one diagnostic through this
module (#203).

Two constraints shape what crosses that boundary:

  * `no-secrets` forbids exception messages, credentials, and host paths in any
    diagnostic. The exception TYPE and the code locations survive; the message
    does not. A `FileNotFoundError` message embeds the path it could not find,
    and a decoder message embeds the bytes it rejected.
  * A machine-readable command must leave stdout holding exactly one valid
    document or nothing at all. The diagnostic goes to stderr, never appended
    after a partial stdout write.

Entrypoints that mutate durable state pass `state` naming whether their atomic
commit landed, so an operator can tell a pre-commit abort from a post-commit
reporting failure without replaying writes.
"""

import json
import os
import sys
import traceback
from typing import Any, TextIO

# The document's identity. A caller's `state` may add fields beside these but
# never replace them — see `unexpected_failure_document`.
IDENTITY_FIELDS = frozenset({"error", "error_type", "origin"})


def sanitized_frames(exc: BaseException) -> list[str]:
    """Code locations from a traceback, with no exception text or full paths.

    Only `basename:line in function` crosses the boundary. That still points an
    operator at the failing code, which the exception type alone does not.
    """
    return [
        f"{os.path.basename(frame.filename)}:{frame.lineno} in {frame.name}"
        for frame in traceback.extract_tb(exc.__traceback__)
    ]


def unexpected_failure_document(
    exc: BaseException,
    error_code: str,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the closed failure document for an outer boundary.

    `error_code` is the entrypoint's documented failure identifier. `state`
    carries entrypoint-specific facts an operator needs before retrying —
    commit position for a mutating script, `None` for a read-only one.

    A `state` key colliding with `IDENTITY_FIELDS` loses: the identity fields
    are written last. An entrypoint that renamed its own failure code would
    make every downstream consumer misclassify the failure, and this builder
    runs inside the boundary itself — raising here would produce exactly the
    traceback the boundary exists to prevent.
    """
    document: dict[str, Any] = dict(state or {})
    document["error"] = error_code
    document["error_type"] = type(exc).__name__
    document["origin"] = sanitized_frames(exc)
    return document


def emit_unexpected_failure(
    exc: BaseException,
    error_code: str,
    recovery: str,
    state: dict[str, Any] | None = None,
    stream: TextIO | None = None,
) -> None:
    """Write one closed failure document plus its recovery note to stderr.

    `recovery` tells the operator what to do — `rules/error-handling.md`
    requires an actionable message, and "it failed" is not one.
    """
    target = sys.stderr if stream is None else stream
    print(
        json.dumps(unexpected_failure_document(exc, error_code, state), sort_keys=True),
        file=target,
    )
    print(
        f"{recovery}\n"
        "\n  `origin` above lists the code locations that failed, "
        "innermost last.",
        file=target,
    )
