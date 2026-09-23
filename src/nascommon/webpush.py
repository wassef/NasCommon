"""VAPID Web Push: sending one message, and deciding what a browser's subscription is.

**Sending** is best-effort and never raises: `send_one` answers `(ok, gone, error)`. `gone` means
prune the subscription — 404/410 (the browser dropped it) and also 401/403, the push service
refusing this server's key for *this* subscription, which is what a subscription made under an
earlier VAPID key gets; the browser makes a new one on its next load, so pruning is the way back.
Best effort is not silence: `error` says why, for a log and a health page.

pywebpush's own default TTL is 0, "deliver now or drop", which lost a 06:30 message to a phone in
Doze while the send counted as a success. The default here holds a message an hour.

**Accepting** a subscription: an endpoint anywhere but a browser push service is not a browser's
subscription — every message would be POSTed there, off the tailnet, and the server would make a
request to wherever it pointed.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

GONE = frozenset({404, 410})
REFUSED_KEY = frozenset({401, 403})
DEFAULT_TTL_S = 3600
URGENCIES = frozenset({"very-low", "low", "normal", "high"})

PUSH_SERVICES: tuple[str, ...] = (
    "fcm.googleapis.com",  # Chrome, Android, Brave
    "push.services.mozilla.com",  # Firefox
    "push.apple.com",  # Safari, iOS
    "notify.windows.com",  # Edge
)
ENDPOINT_CHARS = 1024
KEY_CHARS = 256
_KEY = re.compile(r"^[A-Za-z0-9_-]+=*$")
"""A browser's keys are base64url: p256dh is 87 characters, auth 22."""


def send_one(
    subscription_info: dict[str, Any],
    payload: str,
    *,
    private_key: str | None,
    subject: str,
    ttl: int = DEFAULT_TTL_S,
    urgency: str | None = None,
    timeout: float = 15,
) -> tuple[bool, bool, str | None]:
    """Send `payload` to one subscription: `(ok, gone, error)`. Blocking; run it off the loop.

    pywebpush is imported here, so an app without the `push` extra still imports this module and
    is told why nothing was sent.
    """
    if not private_key:
        return False, False, "no VAPID private key is configured"
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return False, False, "pywebpush is not installed"
    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=private_key,
            vapid_claims={"sub": subject},
            ttl=ttl,
            headers={"Urgency": urgency} if urgency in URGENCIES else None,
            timeout=timeout,
        )
        return True, False, None
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in REFUSED_KEY:
            return False, True, f"push service refused the VAPID key ({status}); the subscription was dropped"
        if status in GONE:
            return False, True, None
        return False, False, f"push service answered {status}: {str(exc)[:160]}"
    except Exception as exc:  # a transport, a proxy, anything: never raised to the caller
        return False, False, f"{type(exc).__name__}: {str(exc)[:160]}"


def _split(endpoint: str) -> tuple[str, str]:
    """(scheme, lower-cased host), or ("", "") for what is not a URL at all: `urlsplit` raises on
    a malformed IPv6 bracket, and a check that raises is a 500 where a refusal was meant."""
    try:
        parts = urlsplit(endpoint)
        return parts.scheme, (parts.hostname or "").lower()
    except ValueError:
        return "", ""


def push_host(endpoint: str) -> str:
    """The push service's host, lower-cased: what may be logged, where the full endpoint may not
    (it is a capability URL — whoever holds it can message the device)."""
    return _split(endpoint)[1]


def at_a_push_service(endpoint: str) -> bool:
    """An https endpoint on one of `PUSH_SERVICES`, or a subdomain of one."""
    scheme, host = _split(endpoint)
    if scheme != "https":
        return False
    return any(host == s or host.endswith("." + s) for s in PUSH_SERVICES)


def subscription_from(body: Any) -> tuple[dict[str, Any] | None, str | None]:
    """The subscription a browser POSTed as `{"endpoint", "keys": {"p256dh", "auth"}}`, cleaned,
    or `(None, why it is not one)`."""
    if not isinstance(body, dict):
        return None, "a subscription is an object"
    endpoint = str(body.get("endpoint") or "")
    keys = body.get("keys") or {}
    if not endpoint or not isinstance(keys, dict) or not keys.get("p256dh") or not keys.get("auth"):
        return None, "a subscription needs an endpoint and both keys"
    if len(endpoint) > ENDPOINT_CHARS:
        return None, "the endpoint is too long"
    clean = {"p256dh": str(keys["p256dh"]), "auth": str(keys["auth"])}
    if any(len(v) > KEY_CHARS or not _KEY.match(v) for v in clean.values()):
        return None, "the keys are not a browser's"
    if not at_a_push_service(endpoint):
        return None, f"the endpoint must be https on a browser push service ({', '.join(PUSH_SERVICES)})"
    return {"endpoint": endpoint, "keys": clean}, None
