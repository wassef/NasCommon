"""Web Push with pywebpush stubbed: best effort, never silent, and only a browser's subscription."""

from __future__ import annotations

import sys
import types

import pytest

from nascommon.webpush import (
    DEFAULT_TTL_S,
    PUSH_SERVICES,
    at_a_push_service,
    push_host,
    send_one,
    subscription_from,
)

INFO = {"endpoint": "https://fcm.googleapis.com/wp/secret", "keys": {"p256dh": "k", "auth": "a"}}
P256 = "B" + "a" * 86
AUTH = "c" * 22


class _Refused(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.response = types.SimpleNamespace(status_code=status)


def _stub(monkeypatch, behaviour):
    module = types.ModuleType("pywebpush")
    module.WebPushException = _Refused
    module.webpush = behaviour
    monkeypatch.setitem(sys.modules, "pywebpush", module)


def test_a_send_holds_the_message_an_hour_by_default_and_passes_a_valid_urgency(monkeypatch):
    seen = []
    _stub(monkeypatch, lambda **kw: seen.append(kw))
    assert send_one(INFO, "{}", private_key="k", subject="mailto:x@example.invalid") == (True, False, None)
    assert seen[0]["ttl"] == DEFAULT_TTL_S and seen[0]["headers"] is None
    assert seen[0]["vapid_claims"] == {"sub": "mailto:x@example.invalid"}
    send_one(INFO, "{}", private_key="k", subject="s", ttl=60, urgency="high")
    send_one(INFO, "{}", private_key="k", subject="s", urgency="shouting")
    assert seen[1]["ttl"] == 60 and seen[1]["headers"] == {"Urgency": "high"}
    assert seen[2]["headers"] is None, "an urgency the protocol does not know is not sent"


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (410, (False, True, None)),
        (404, (False, True, None)),
        (500, (False, False, "push service answered 500: HTTP 500")),
    ],
)
def test_what_the_push_service_answered_decides_prune_or_keep(monkeypatch, status, outcome):
    def refuse(**_kw):
        raise _Refused(status)

    _stub(monkeypatch, refuse)
    assert send_one(INFO, "{}", private_key="k", subject="s") == outcome


def test_a_refused_key_prunes_and_says_so(monkeypatch):
    def refuse(**_kw):
        raise _Refused(403)

    _stub(monkeypatch, refuse)
    ok, gone, error = send_one(INFO, "{}", private_key="k", subject="s")
    assert (ok, gone) == (False, True) and "VAPID key (403)" in error


def test_a_transport_failure_is_reported_never_raised(monkeypatch):
    def boom(**_kw):
        raise ConnectionError("proxy down")

    _stub(monkeypatch, boom)
    assert send_one(INFO, "{}", private_key="k", subject="s") == (False, False, "ConnectionError: proxy down")


def test_no_key_or_no_library_is_named(monkeypatch):
    assert send_one(INFO, "{}", private_key=None, subject="s") == (
        False,
        False,
        "no VAPID private key is configured",
    )
    monkeypatch.setitem(sys.modules, "pywebpush", None)
    assert send_one(INFO, "{}", private_key="k", subject="s") == (False, False, "pywebpush is not installed")


def test_only_https_on_a_browser_push_service_is_one():
    assert at_a_push_service("https://fcm.googleapis.com/fcm/send/x")
    assert at_a_push_service("https://web.push.apple.com/abc")
    assert not at_a_push_service("http://fcm.googleapis.com/fcm/send/x")
    assert not at_a_push_service("https://evil.example/fcm.googleapis.com")
    assert not at_a_push_service("https://notfcm.googleapis.com.evil.example/x")
    assert push_host("https://FCM.googleapis.com/x") == "fcm.googleapis.com"
    assert len(PUSH_SERVICES) == 4


def test_a_browsers_subscription_is_cleaned_and_anything_else_says_why():
    body = {"endpoint": "https://fcm.googleapis.com/wp/x", "keys": {"p256dh": P256, "auth": AUTH, "extra": 1}}
    assert subscription_from(body) == (
        {"endpoint": "https://fcm.googleapis.com/wp/x", "keys": {"p256dh": P256, "auth": AUTH}},
        None,
    )
    refusals = {
        "list": ([], "a subscription is an object"),
        "no keys": ({"endpoint": "https://fcm.googleapis.com/x"}, "needs an endpoint and both keys"),
        "keys not a map": ({"endpoint": "https://fcm.googleapis.com/x", "keys": "k"}, "needs an endpoint"),
        "long": (
            {"endpoint": "https://fcm.googleapis.com/" + "x" * 1100, "keys": {"p256dh": P256, "auth": AUTH}},
            "too long",
        ),
        "bad key": (
            {"endpoint": "https://fcm.googleapis.com/x", "keys": {"p256dh": "not base64!", "auth": AUTH}},
            "not a browser's",
        ),
        "elsewhere": (
            {"endpoint": "https://collector.example/x", "keys": {"p256dh": P256, "auth": AUTH}},
            "browser push service",
        ),
    }
    for name, (body, why) in refusals.items():
        subscription, error = subscription_from(body)
        assert subscription is None and why in error, name
