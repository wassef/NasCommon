"""What a call to the bridge can end in, as types a caller can act on.

Each is a `RuntimeError`, so a caller that already catches broadly keeps behaving as before; only
code that catches one of these by name gets the specific handling — a limit pauses until its
reset, busy waits, rejected is not retried, unavailable is.
"""

from __future__ import annotations

from datetime import datetime


class BridgeError(RuntimeError):
    """Anything the bridge ended in that was not an answer."""


class BridgeBusy(BridgeError):
    """`/health` says a `claude -p` is running. The bridge runs one at a time and is shared, and a
    client timeout does not cancel the subprocess, so a call is never posted while it is busy."""


class BridgeUnavailable(BridgeError):
    """Worth retrying: the connection failed, it timed out, or the bridge answered 503 or 504."""


class BridgeRejected(BridgeError):
    """The same request gets the same answer next time: a bad model name, a wrong key, a crash
    that is not a limit, a 200 whose body is not the bridge's JSON. Retrying costs the shared
    bridge a call and the caller its window."""


class LimitReached(BridgeError):
    """The subscription's session or weekly budget is spent until `reset_at` (UTC), when known."""

    def __init__(self, message: str, *, reset_at: datetime | None = None, reset_raw: str | None = None):
        super().__init__(message)
        self.reset_at = reset_at
        self.reset_raw = reset_raw
