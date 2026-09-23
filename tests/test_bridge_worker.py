"""The line in front of the bridge: one call at a time, most urgent first, no key twice."""

from __future__ import annotations

import asyncio

from nascommon.bridge import BridgeWorker

URGENT, LATER, LAST = 1, 2, 3


async def test_a_key_already_waiting_is_not_queued_twice():
    worker, ran = BridgeWorker(), []
    worker.hold()

    async def job(tag):
        ran.append(tag)

    assert worker.submit("narration", LAST, lambda: job("first")) is True
    assert worker.submit("narration", LAST, lambda: job("second")) is False
    assert worker.pending("narration") and worker.waiting == ["narration"]
    assert worker.held
    worker.release()
    await worker.drain()
    assert ran == ["first"] and not worker.pending("narration") and not worker.held


async def test_what_is_most_urgent_runs_first_and_a_failure_stops_nothing():
    worker, ran = BridgeWorker(), []
    worker.hold()

    async def job(tag):
        ran.append(tag)
        if tag == "later":
            raise RuntimeError("the bridge fell over")

    worker.submit("c", LAST, lambda: job("last"))
    worker.submit("b", LATER, lambda: job("later"))
    worker.submit("a", URGENT, lambda: job("urgent"))
    worker.release()
    await worker.drain()
    assert ran == ["urgent", "later", "last"]


async def test_nothing_new_starts_while_held_and_what_arrived_keeps_its_order():
    worker, ran = BridgeWorker(), []

    async def job(tag):
        ran.append(tag)

    worker.hold()
    worker.submit("c", LAST, lambda: job("last"))
    for _ in range(5):
        await asyncio.sleep(0)
    assert ran == [] and worker.running is None
    worker.submit("b", LATER, lambda: job("later"))
    worker.release()
    await worker.drain()
    assert ran == ["later", "last"]


async def test_a_hold_taken_while_the_loop_waits_for_work_sends_the_next_item_back_in_line():
    """The loop is parked in `queue.get()` when the hold is taken: the item that wakes it must not
    start, and must still be first when the hold is released."""
    worker, ran = BridgeWorker(), []

    async def job(tag):
        ran.append(tag)

    worker.submit("one", URGENT, lambda: job("one"))
    await worker.drain()
    for _ in range(3):
        await asyncio.sleep(0)  # the loop is back at `get()`, waiting for work
    worker.hold()
    worker.submit("two", LATER, lambda: job("two"))
    for _ in range(5):
        await asyncio.sleep(0)
    assert ran == ["one"] and worker.running is None and worker.waiting == ["two"]
    worker.release()
    await worker.drain()
    assert ran == ["one", "two"]


async def test_drain_and_release_before_any_work_do_nothing():
    worker = BridgeWorker()
    await worker.drain()
    worker.release()
    assert worker.waiting == [] and worker.running is None and not worker.held


async def test_the_lock_is_one_call_in_flight():
    worker, active, peak = BridgeWorker(), 0, 0

    async def call():
        nonlocal active, peak
        async with worker.lock:
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1

    await asyncio.gather(*(call() for _ in range(4)))
    assert peak == 1
