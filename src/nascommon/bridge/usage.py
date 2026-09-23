"""A short-lived cache over the bridge's `/usage` readout.

`claude -p "/usage"` is a free, local readout of the rolling session and weekly budget. A batch
that asks before every job would, with the Mac asleep, wait out a 35 s timeout each time, so a
failed fetch is cached too (as None): a dead Mac costs one timeout a minute, not one per caller.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

T = TypeVar("T")

CACHE_TTL_S = 60.0
"""The bridge caches its own `/usage` for a minute too: asking more often reads the same answer."""


class UsageCache(Generic[T]):
    def __init__(
        self,
        fetch: Callable[[], Awaitable[T | None]],
        ttl: float = CACHE_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetch = fetch
        self._ttl = ttl
        self._clock = clock
        # None until the first fetch, not 0.0: monotonic time counts from boot, and on a freshly
        # started machine it can be under the TTL, which made a 0.0 stamp look fresh and returned
        # None without ever asking the bridge.
        self._fetched_at: float | None = None
        self._value: T | None = None

    async def get(self, *, max_age: float | None = None) -> T | None:
        ttl = self._ttl if max_age is None else max_age
        if self._fetched_at is not None and self._clock() - self._fetched_at < ttl:
            return self._value
        self._value = await self._fetch()
        self._fetched_at = self._clock()
        return self._value

    def invalidate(self) -> None:
        self._fetched_at = None
