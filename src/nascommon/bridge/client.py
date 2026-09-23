"""An async client for the MacServices claude_bridge: a tool-less `claude -p` behind HTTP.

The etiquette it keeps, because the bridge runs one call at a time and is shared between apps:

* `/health` first, and nothing is posted while it says `busy` — a client timeout does not cancel
  the subprocess, so a second post only queues behind the first on the Mac.
* A usage limit is HTTP 502 whose `detail` carries the CLI's stderr tail: it becomes
  `LimitReached` with the reset time when the words give one. The same check runs on a 200's
  content, as a cheap safety net.
* Only a connect error, a timeout, 503 and 504 are `BridgeUnavailable` (worth retrying).
  Everything else that is not an answer is `BridgeRejected`: the same request would get the same
  answer, and a retry costs the shared bridge a call.

What to retry, when to fall back and what to record is the caller's policy, not this client's.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from nascommon.auth import service_headers

from .errors import BridgeBusy, BridgeRejected, BridgeUnavailable, LimitReached
from .limits import is_limit_message, is_limit_text, parse_reset
from .usage import UsageCache

HEALTH_TIMEOUT = httpx.Timeout(10.0)
USAGE_TIMEOUT = httpx.Timeout(35.0)
"""The bridge caps its own `/usage` subprocess at 30 s."""
MAX_COMPLETE_S = 600.0
"""Opus at a high effort can think for minutes; the bridge enforces its own kill timeout too."""


@dataclass(frozen=True, slots=True)
class Health:
    ok: bool
    busy: bool
    auth: bool = True
    version: str = ""


@dataclass(frozen=True, slots=True)
class Usage:
    session_pct: float | None = None
    week_pct: float | None = None
    session_reset_at: datetime | None = None
    week_reset_at: datetime | None = None


def _pct(value: Any) -> float | None:
    """A percentage the bridge reported, or None: never a bool, a NaN or an infinity."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class BridgeClient:
    def __init__(
        self,
        base_url: str,
        service_key: str | None,
        *,
        caller: str | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._headers = service_headers(service_key, caller)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient()
        self._usage: UsageCache[Usage] = UsageCache(self._fetch_usage)

    async def aclose(self) -> None:
        """Close the HTTP client this made; one it was handed belongs to whoever handed it."""
        if self._owns_client:
            await self._client.aclose()

    async def health(self) -> Health:
        try:
            r = await self._client.get(f"{self.base_url}/health", timeout=HEALTH_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BridgeUnavailable(f"bridge health: {exc}") from exc
        if not isinstance(data, dict):
            raise BridgeUnavailable("bridge health: the answer was not an object")
        return Health(
            ok=bool(data.get("ok")),
            busy=bool(data.get("busy")),
            auth=bool(data.get("auth", True)),
            version=str(data.get("version", "")),
        )

    async def usage(self, *, max_age: float | None = None) -> Usage | None:
        """The subscription's budget, or None when the bridge cannot say (unknown, not zero)."""
        return await self._usage.get(max_age=max_age)

    async def _fetch_usage(self) -> Usage | None:
        try:
            r = await self._client.get(f"{self.base_url}/usage", headers=self._headers, timeout=USAGE_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError):
            return None
        if not isinstance(data, dict) or not data.get("ok"):
            return None
        session_reset, _ = parse_reset(data.get("session_reset") or "")
        week_reset, _ = parse_reset(data.get("week_reset") or "")
        return Usage(
            session_pct=_pct(data.get("session_pct")),
            week_pct=_pct(data.get("week_pct")),
            session_reset_at=session_reset,
            week_reset_at=week_reset,
        )

    async def complete(
        self,
        system: str,
        user: str,
        *,
        model: str,
        effort: str,
        timeout_s: float,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """One completion. `extra` carries fields a caller's bridge contract adds (temperature…)."""
        if (await self.health()).busy:
            raise BridgeBusy("bridge busy")
        body = {"system": system, "user": user, "model": model, "effort": effort, **(extra or {})}
        try:
            r = await self._client.post(
                f"{self.base_url}/complete",
                json=body,
                headers=self._headers,
                timeout=httpx.Timeout(min(timeout_s, MAX_COMPLETE_S)),
            )
        except httpx.TimeoutException as exc:
            raise BridgeUnavailable(f"bridge timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise BridgeUnavailable(f"bridge connect: {exc}") from exc
        if r.status_code >= 400:
            text = r.text
            if r.status_code == 502 and is_limit_text(text):
                reset_at, raw = parse_reset(text)
                raise LimitReached(f"usage limit: {text[:300]}", reset_at=reset_at, reset_raw=raw)
            if r.status_code in (503, 504):
                raise BridgeUnavailable(f"bridge HTTP {r.status_code}: {text[:200]}")
            raise BridgeRejected(f"bridge HTTP {r.status_code}: {text[:200]}")
        try:
            data = r.json()
        except ValueError as exc:
            raise BridgeRejected(f"bridge answered 200 with a body that is not JSON: {r.text[:120]}") from exc
        content = str(data.get("content", "")) if isinstance(data, dict) else ""
        if is_limit_message(content):
            reset_at, raw = parse_reset(content)
            raise LimitReached(f"usage limit in content: {content[:300]}", reset_at=reset_at, reset_raw=raw)
        return content
