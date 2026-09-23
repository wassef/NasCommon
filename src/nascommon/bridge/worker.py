"""One line in front of the Claude bridge, so nothing that asks it waits on anything else.

The bridge runs one `claude -p` at a time and is shared between apps. Reactions that need it —
a summary, an investigation, a narration — are *submitted* here and run one at a time on a single
background task, in priority order (lowest number first). A key already waiting is not queued
twice, so a burst of the same reaction is one call. `lock` is for the calls that do not come
through the queue, so a process never has two in flight; `hold()` is for the one call that must
not wait behind the line (a scheduled brief): while held, nothing new starts, and what was queued
waits until it is released.

Nothing here knows what the work is; it runs awaitables and logs what they raise.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass(order=True)
class _Item:
    priority: int
    seq: int
    key: str = field(compare=False)
    run: Callable[[], Awaitable[Any]] = field(compare=False)


class BridgeWorker:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self._queue: asyncio.PriorityQueue[_Item] | None = None
        self._open: asyncio.Event | None = None
        self._idle: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        self._keys: set[str] = set()
        self._seq = itertools.count()
        self._running: str | None = None

    # ── the three doors ───────────────────────────────────────────────────────
    def submit(self, key: str, priority: int, run: Callable[[], Awaitable[Any]]) -> bool:
        """Queue `run` unless the same `key` is already waiting or running. True when queued."""
        if key in self._keys:
            return False
        self._start()
        assert self._queue is not None and self._idle is not None
        self._keys.add(key)
        self._idle.clear()
        self._queue.put_nowait(_Item(priority, next(self._seq), key, run))
        return True

    def hold(self) -> None:
        """Start nothing new until `release()`. What is running finishes; what waits, waits."""
        self._primitives()
        assert self._open is not None
        self._open.clear()

    def release(self) -> None:
        if self._open is not None:
            self._open.set()

    async def drain(self) -> None:
        """Until nothing is queued and nothing runs: for tests, the CLI and a clean shutdown."""
        if self._idle is not None:
            await self._idle.wait()

    # ── what /doctor and a test may ask ───────────────────────────────────────
    @property
    def waiting(self) -> list[str]:
        return sorted(self._keys - ({self._running} if self._running else set()))

    @property
    def running(self) -> str | None:
        return self._running

    @property
    def held(self) -> bool:
        """True between `hold()` and `release()`."""
        return self._open is not None and not self._open.is_set()

    def pending(self, key: str) -> bool:
        return key in self._keys

    # ── the loop ──────────────────────────────────────────────────────────────
    def _primitives(self) -> None:
        """Created on first use, inside the running loop: a container is built before one exists."""
        if self._queue is None:
            self._queue = asyncio.PriorityQueue()
            self._open = asyncio.Event()
            self._open.set()
            self._idle = asyncio.Event()
            self._idle.set()

    def _start(self) -> None:
        self._primitives()
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._loop(), name="bridge-worker")

    async def _loop(self) -> None:
        assert self._queue is not None and self._open is not None and self._idle is not None
        while True:
            await self._open.wait()
            item = await self._queue.get()
            if not self._open.is_set():
                # Held while this waited for work: back in line, in order,
                # so what is most urgent when it lets go is what runs first.
                self._queue.put_nowait(item)
                self._queue.task_done()
                continue
            self._running = item.key
            try:
                await item.run()
            except Exception as exc:  # one failed reaction must never stop the line behind it
                log.warning(
                    "bridge_worker.failed key=%s %s: %s", item.key, type(exc).__name__, str(exc)[:200]
                )
            finally:
                self._running = None
                self._keys.discard(item.key)
                self._queue.task_done()
                if self._queue.empty():
                    self._idle.set()
