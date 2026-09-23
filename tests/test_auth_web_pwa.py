"""The two shared secrets, the CSRF check and headers, the tailnet check, and the worker's version."""

from __future__ import annotations

from nascommon.auth import (
    CALLER_HEADER,
    SERVICE_KEY_HEADER,
    api_key_ok,
    inbound_verdict,
    service_headers,
)
from nascommon.pwa import PLACEHOLDER, WORKER_HEADERS, asset_version, render_worker
from nascommon.web import csrf_verdict, outside_tailnet, security_headers


class Headers(dict):
    """A case-insensitive mapping, as Starlette's is."""

    def __init__(self, **items):
        super().__init__({k.replace("_", "-").lower(): v for k, v in items.items()})

    def get(self, key, default=None):
        return super().get(key.lower(), default)


# ── inbound ───────────────────────────────────────────────────────────────────
def test_an_unconfigured_key_matches_nothing():
    assert not api_key_ok("anything", None) and not api_key_ok(None, "")
    assert api_key_ok("s3cret", "s3cret") and not api_key_ok("s3cre", "s3cret") and not api_key_ok(None, "x")


def test_everything_is_protected_unless_prefixes_say_otherwise():
    assert inbound_verdict("/jobs", None, expected="k") == (401, "unauthorized")
    assert inbound_verdict("/jobs", "k", expected="k") is None
    assert inbound_verdict("/health", None, expected="k") is None, "health stays open"
    api = ("/api/", "/doctor")
    assert inbound_verdict("/", None, expected="k", protected=api) is None, "a screen is not the API"
    assert inbound_verdict("/api/state", None, expected="k", protected=api) == (401, "unauthorized")


def test_a_missing_configuration_fails_closed_unless_auth_is_off():
    assert inbound_verdict("/jobs", "k", expected=None, unset_message="set APP_KEY") == (503, "set APP_KEY")
    assert inbound_verdict("/jobs", None, expected=None, mode="OFF") is None


def test_service_headers_carry_the_key_and_the_caller_when_there_are_some():
    assert service_headers("k", "asturlab") == {CALLER_HEADER: "asturlab", SERVICE_KEY_HEADER: "k"}
    assert service_headers(None, "asturlab") == {CALLER_HEADER: "asturlab"}
    assert service_headers("k") == {SERVICE_KEY_HEADER: "k"}
    assert service_headers(None) == {}


# ── CSRF and headers ──────────────────────────────────────────────────────────
def test_reads_pass_and_a_cross_site_write_is_refused():
    assert csrf_verdict("GET", Headers(sec_fetch_site="cross-site")) is None
    assert csrf_verdict("POST", Headers(sec_fetch_site="cross-site")) == (403, "cross-site request refused")
    assert csrf_verdict("POST", Headers(sec_fetch_site="same-site")) == (403, "cross-site request refused")
    assert csrf_verdict("POST", Headers(sec_fetch_site="same-origin")) is None
    assert csrf_verdict("POST", Headers()) is None, "curl sends neither header"


def test_the_origin_is_compared_by_host_name_so_a_proxy_that_drops_the_port_still_passes():
    assert csrf_verdict("POST", Headers(origin="https://nas.example:8445", host="nas.example")) is None
    assert (
        csrf_verdict("POST", Headers(origin="https://nas.example:8445", x_forwarded_host="nas.example:8445"))
        is None
    )
    assert csrf_verdict("POST", Headers(origin="https://evil.example", host="nas.example")) == (
        403,
        "origin mismatch",
    )


def test_headers_differ_only_where_the_apps_do():
    strict = security_headers()
    assert "script-src 'self';" in strict["Content-Security-Policy"]
    assert strict["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    loose = security_headers(inline_scripts=True, microphone=True)
    assert "script-src 'self' 'unsafe-inline';" in loose["Content-Security-Policy"]
    assert loose["Permissions-Policy"] == "camera=(), microphone=(self), geolocation=()"
    assert (
        strict["X-Frame-Options"] == "DENY" and "frame-ancestors 'none'" in strict["Content-Security-Policy"]
    )


def test_the_tailnet_and_this_machine_are_inside_and_the_lan_is_not():
    for inside in ("100.64.0.1", "fd7a:115c:a1e0::1", "127.0.0.1", "::1", "172.18.0.1"):
        assert not outside_tailnet(inside), inside
    assert outside_tailnet("192.168.1.20") and outside_tailnet(" 10.0.0.5 ")
    assert not outside_tailnet(None) and not outside_tailnet("") and not outside_tailnet("not an ip")


# ── the PWA shell ─────────────────────────────────────────────────────────────
def test_the_version_is_a_digest_of_the_files_and_moves_when_one_changes(tmp_path):
    static, templates = tmp_path / "static", tmp_path / "templates"
    static.mkdir()
    (static / "app.js").write_text("one")
    (static / ".DS_Store").write_text("ignored")
    first = asset_version([static, templates])
    assert len(first) == 12 and first == asset_version([static, templates, tmp_path / "missing"])
    (static / ".DS_Store").write_text("still ignored")
    assert asset_version([static]) == first
    (static / "app.js").write_text("two")
    assert asset_version([static]) != first
    assert len(asset_version([static], length=8)) == 8


def test_the_worker_is_stamped_and_served_uncached_from_the_root():
    assert render_worker(f"const V = '{PLACEHOLDER}';", "abc123") == "const V = 'abc123';"
    assert WORKER_HEADERS == {"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"}
