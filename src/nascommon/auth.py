"""Two shared secrets: the one a machine caller presents to an app, and the one an app presents to
the Mac services.

**Inbound.** An app on a private tailnet has two kinds of callers: the person's browser, which the
Tailscale ACL already let onto the network, and scripts. The machine-readable surface is kept
behind a key (`X-Api-Key`) so a script can be told apart from the browser and so the surface does
not silently open the day an environment variable is dropped: a configured key that is missing
from a request is refused, and a key that is *not configured* refuses everything (503), unless
the app was started with its auth explicitly `off` for local development. `/health` stays open,
because a health check that needs the secret cannot report that the secret is missing.

**Outbound.** Every MacServices service (bridge, whisper, embed, local_llm) wants the one shared
key as `X-Service-Key` and logs `X-Caller`, so its logs say which app asked.
"""

from __future__ import annotations

import hmac
from collections.abc import Iterable

API_KEY_HEADER = "x-api-key"
SERVICE_KEY_HEADER = "X-Service-Key"
CALLER_HEADER = "X-Caller"
OPEN_PATHS = frozenset({"/health"})


def api_key_ok(provided: str | None, expected: str | None) -> bool:
    """Constant-time comparison; an unconfigured key matches nothing, not everything."""
    if not expected:
        return False
    return hmac.compare_digest((provided or "").encode(), expected.encode())


def inbound_verdict(
    path: str,
    provided: str | None,
    *,
    expected: str | None,
    mode: str = "on",
    protected: Iterable[str] | None = None,
    open_paths: Iterable[str] = OPEN_PATHS,
    unset_message: str = "the API key is not configured (or set auth off for local development)",
) -> tuple[int, str] | None:
    """None when the request may pass; else `(status, message)` to refuse it with.

    `protected` is the prefixes that need the key; None protects every path, which is what an
    API-only service wants. `mode` "off" lets everything through: local development only.
    """
    if path in set(open_paths):
        return None
    if protected is not None and not path.startswith(tuple(protected)):
        return None
    if mode.lower() == "off":
        return None
    if not expected:
        return 503, unset_message
    if not api_key_ok(provided, expected):
        return 401, "unauthorized"
    return None


def service_headers(key: str | None, caller: str | None = None) -> dict[str, str]:
    """Headers for a call to a Mac service: the shared key when there is one, and who is asking."""
    headers: dict[str, str] = {}
    if caller:
        headers[CALLER_HEADER] = caller
    if key:
        headers[SERVICE_KEY_HEADER] = key
    return headers
