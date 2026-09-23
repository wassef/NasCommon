"""The bridge client over httpx.MockTransport: the etiquette, and which failures are which."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from nascommon.bridge.client import MAX_COMPLETE_S, BridgeClient, Health, Usage, _pct
from nascommon.bridge.errors import BridgeBusy, BridgeRejected, BridgeUnavailable, LimitReached
from nascommon.bridge.usage import UsageCache

BASE = "http://bridge:8214"


def client_for(handler) -> BridgeClient:
    return BridgeClient(
        BASE + "/", "k3y", caller="app", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


def routes(health=None, usage=None, complete=None):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        answer = {"/health": health, "/usage": usage, "/complete": complete}[path]
        if callable(answer):
            return answer(request)
        return answer or httpx.Response(404)

    return handler, seen


def ok(payload, status=200):
    return httpx.Response(status, json=payload)


async def test_health_reads_the_fields_and_defaults_auth_to_true():
    handler, _ = routes(health=ok({"ok": True, "busy": False, "version": "1.2"}))
    c = client_for(handler)
    assert await c.health() == Health(ok=True, busy=False, auth=True, version="1.2")
    assert c.base_url == BASE


@pytest.mark.parametrize(
    "answer",
    [httpx.Response(500), httpx.Response(200, text="not json"), ok(["a", "list"])],
    ids=["500", "not json", "not an object"],
)
async def test_a_health_that_cannot_be_read_is_unavailable(answer):
    handler, _ = routes(health=answer)
    with pytest.raises(BridgeUnavailable):
        await client_for(handler).health()


async def test_usage_parses_and_is_cached_and_the_key_and_caller_go_along():
    handler, seen = routes(
        usage=ok(
            {
                "ok": True,
                "session_pct": "42",
                "week_pct": 7,
                "session_reset": "4:30pm (Europe/Zurich)",
                "week_reset": "",
            }
        )
    )
    c = client_for(handler)
    first = await c.usage()
    assert first.session_pct == 42.0 and first.week_pct == 7.0
    assert first.session_reset_at is not None and first.week_reset_at is None
    assert await c.usage() is first, "a second ask inside the minute reads the cache"
    assert len(seen) == 1
    assert seen[0].headers["x-service-key"] == "k3y" and seen[0].headers["x-caller"] == "app"


@pytest.mark.parametrize(
    "answer",
    [ok({"ok": False, "error": "no cli"}), httpx.Response(502), httpx.Response(200, text="?"), ok([1])],
)
async def test_a_usage_the_bridge_cannot_give_is_unknown(answer):
    handler, _ = routes(usage=answer)
    assert await client_for(handler).usage() is None


def test_a_percentage_is_a_finite_number_or_nothing():
    assert _pct("12.5") == 12.5 and _pct(3) == 3.0
    assert _pct(True) is None and _pct(None) is None and _pct("n/a") is None and _pct(float("nan")) is None


async def test_complete_posts_once_when_free_and_returns_the_content():
    handler, seen = routes(health=ok({"ok": True, "busy": False}), complete=ok({"content": "prose"}))
    c = client_for(handler)
    assert (
        await c.complete(
            "sys", "user", model="sonnet", effort="medium", timeout_s=30, extra={"temperature": 0.2}
        )
        == "prose"
    )
    post = seen[-1]
    assert json.loads(post.content) == {
        "system": "sys",
        "user": "user",
        "model": "sonnet",
        "effort": "medium",
        "temperature": 0.2,
    }
    assert post.headers["x-service-key"] == "k3y"


async def test_nothing_is_posted_while_the_bridge_is_busy():
    handler, seen = routes(health=ok({"ok": True, "busy": True}))
    with pytest.raises(BridgeBusy):
        await client_for(handler).complete("s", "u", model="sonnet", effort="medium", timeout_s=30)
    assert [r.url.path for r in seen] == ["/health"]


async def test_a_502_limit_carries_its_reset_and_a_503_or_504_is_worth_retrying():
    handler, _ = routes(
        health=ok({"busy": False}),
        complete=httpx.Response(
            502, json={"detail": "You've hit your session limit · resets 4:30pm (Europe/Zurich)"}
        ),
    )
    with pytest.raises(LimitReached) as limit:
        await client_for(handler).complete("s", "u", model="sonnet", effort="medium", timeout_s=30)
    assert limit.value.reset_raw == "4:30pm (Europe/Zurich)" and limit.value.reset_at is not None
    for status in (503, 504):
        handler, _ = routes(health=ok({"busy": False}), complete=httpx.Response(status, text="later"))
        with pytest.raises(BridgeUnavailable):
            await client_for(handler).complete("s", "u", model="sonnet", effort="medium", timeout_s=30)


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(422, text="unknown model"),
        httpx.Response(401, text="bad key"),
        httpx.Response(502, text="claude -p crashed"),
        httpx.Response(200, text="<html>relay error</html>"),
    ],
    ids=["422", "401", "502 crash", "200 not json"],
)
async def test_what_would_fail_the_same_way_again_is_rejected(answer):
    handler, _ = routes(health=ok({"busy": False}), complete=answer)
    with pytest.raises(BridgeRejected):
        await client_for(handler).complete("s", "u", model="sonnet", effort="medium", timeout_s=30)


async def test_a_limit_notice_returned_as_content_is_a_limit_and_a_non_object_is_empty():
    handler, _ = routes(
        health=ok({"busy": False}),
        complete=ok({"content": "You've hit your weekly limit · resets Jul 7 at 5am"}),
    )
    with pytest.raises(LimitReached):
        await client_for(handler).complete("s", "u", model="opus", effort="high", timeout_s=30)
    handler, _ = routes(health=ok({"busy": False}), complete=ok(["not", "an", "object"]))
    assert await client_for(handler).complete("s", "u", model="opus", effort="high", timeout_s=30) == ""


@pytest.mark.parametrize("error", [httpx.ReadTimeout("slow"), httpx.ConnectError("refused")])
async def test_a_timeout_or_a_refused_connection_is_unavailable(error):
    def complete(request):
        raise error

    handler, _ = routes(health=ok({"busy": False}), complete=complete)
    with pytest.raises(BridgeUnavailable):
        await client_for(handler).complete("s", "u", model="sonnet", effort="medium", timeout_s=30)


async def test_the_timeout_is_capped_and_a_client_it_made_is_closed():
    timeouts = []

    def complete(request):
        timeouts.append(request.extensions["timeout"]["read"])
        return ok({"content": "x"})

    handler, _ = routes(health=ok({"busy": False}), complete=complete)
    c = client_for(handler)
    await c.complete("s", "u", model="sonnet", effort="medium", timeout_s=10_000)
    assert timeouts == [MAX_COMPLETE_S]
    await c.aclose()
    assert not c._client.is_closed, "a client it was handed is not its to close"

    own = BridgeClient(BASE, None)
    assert "X-Service-Key" not in own._headers and "X-Caller" not in own._headers
    await own.aclose()
    assert own._client.is_closed


async def test_the_usage_cache_refetches_after_its_ttl_and_on_invalidate():
    now = [100.0]
    calls = []

    async def fetch():
        calls.append(now[0])
        return Usage(session_pct=len(calls))

    cache: UsageCache[Usage] = UsageCache(fetch, ttl=60, clock=lambda: now[0])
    assert (await cache.get()).session_pct == 1
    now[0] += 30
    assert (await cache.get()).session_pct == 1
    assert (await cache.get(max_age=10)).session_pct == 2
    cache.invalidate()
    assert (await cache.get()).session_pct == 3
    now[0] += 61
    assert (await cache.get()).session_pct == 4


def test_limit_reached_is_a_runtime_error_with_its_reset():
    at = datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)
    err = LimitReached("limit", reset_at=at, reset_raw="4:30pm")
    assert isinstance(err, RuntimeError) and err.reset_at == at and err.reset_raw == "4:30pm"
