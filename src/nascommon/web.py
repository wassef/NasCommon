"""What a browser-facing app on the tailnet sends and refuses: security headers, the cookieless CSRF
check, and whether an address is inside the tailnet.

There are no cookies in these apps, so a cross-site page cannot impersonate the person. What it
can do is fire a "simple request" — a body-less POST — at any app open on a tailnet device.
Browsers stamp every request with `Sec-Fetch-Site`; a cross-site value is refused, and an
`Origin` whose host is not ours is refused too. curl and the service worker send neither, or
same-origin, and pass.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from urllib.parse import urlsplit

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def security_headers(*, inline_scripts: bool = False, microphone: bool = False) -> dict[str, str]:
    """The response headers, with the two knobs the apps differ on.

    `inline_scripts` is for templates that still carry `onclick=` handlers: it lets an injected
    inline script run, so the HTML sanitiser becomes the primary control, but the CSP still stops
    it loading remote script, posting to another origin or being framed. `microphone` is for an app
    that records audio from its own page.
    """
    script = "'self' 'unsafe-inline'" if inline_scripts else "'self'"
    return {
        "Content-Security-Policy": (
            f"default-src 'self'; script-src {script}; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; manifest-src 'self'; "
            "worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'"
        ),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "same-origin",
        "Permissions-Policy": f"camera=(), microphone=({'self' if microphone else ''}), geolocation=()",
        "Strict-Transport-Security": "max-age=31536000",
    }


def csrf_verdict(method: str, headers: Mapping[str, str]) -> tuple[int, str] | None:
    """Refuse cross-site state changes. None = allowed. `headers` is a case-insensitive mapping.

    Host names are compared, not `host:port`. A proxy that forwards `$host` drops the port while
    the browser's Origin keeps it (`:8445`), and comparing the two refused every POST the phone
    made. Ignoring the port stays safe: a page on another port of the same NAS is `same-site`, not
    `same-origin`, and the `Sec-Fetch-Site` check refuses it first.
    """
    if method.upper() in SAFE_METHODS:
        return None
    site = (headers.get("sec-fetch-site") or "").lower()
    if site and site not in ("same-origin", "none"):
        return 403, "cross-site request refused"
    origin = headers.get("origin")
    if origin:
        host = (headers.get("x-forwarded-host") or headers.get("host") or "").lower()
        try:
            same = (urlsplit(origin).hostname or "") == (urlsplit(f"//{host}").hostname or "")
        except ValueError:  # a malformed IPv6 bracket in either: not ours, and not a 500
            same = False
        if not same:
            return 403, "origin mismatch"
    return None


TAILNET = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),
)
LOCAL = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    # Docker's bridges: a Tailscale sidecar in userspace mode hands requests on from the gateway.
    ipaddress.ip_network("172.16.0.0/12"),
)


def outside_tailnet(address: str | None) -> bool:
    """True for an address that is neither the tailnet nor this machine.

    A NAS publishes a port on every interface, so a laptop on the home LAN reaches the screens
    unless a firewall rule says otherwise. That rule is the control; noticing an address outside
    these is the check that it holds. Unknown or absent is not judged: a request that did not come
    through the proxy carries no `X-Real-IP`.
    """
    if not address:
        return False
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        return False
    return not any(ip in net for net in TAILNET + LOCAL)
