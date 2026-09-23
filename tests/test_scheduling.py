"""Triggers in the app's zone, windows that fire only inside themselves, a scheduler that coalesces."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nascommon.scheduling import MISFIRE_GRACE_S, Schedule, parse_hhmm

TZ = ZoneInfo("Europe/Zurich")
S = Schedule(TZ)


def fires(trigger, day: date) -> list[str]:
    at = datetime(day.year, day.month, day.day, 0, 0, tzinfo=TZ) - timedelta(microseconds=1)
    out: list[datetime] = []
    while True:
        at = trigger.get_next_fire_time(out[-1] if out else None, at + timedelta(microseconds=1))
        if at is None or at.date() != day:
            return [f"{t:%H:%M}" for t in out]
        out.append(at)


def test_a_cron_fires_in_the_apps_zone_not_the_containers():
    trigger = S.cron_at("06:30")
    assert trigger.timezone == TZ
    first = trigger.get_next_fire_time(None, datetime(2026, 7, 1, 0, 0, tzinfo=TZ))
    assert (first.hour, first.minute, first.utcoffset()) == (6, 30, timedelta(hours=2))
    assert S.cron(hour=1, timezone=ZoneInfo("UTC")).timezone == ZoneInfo("UTC"), "an explicit zone wins"
    assert S.interval(minutes=5).timezone == TZ


def test_a_window_fires_only_inside_it_on_the_hours_grid():
    assert fires(S.window("05:45", "06:30", 5), date(2026, 9, 21)) == [
        "05:45", "05:50", "05:55", "06:00", "06:05", "06:10", "06:15", "06:20", "06:25",
    ]  # fmt: skip
    assert fires(S.window("06:50", "09:00", 10), date(2026, 9, 21))[:3] == ["06:50", "07:00", "07:10"]
    assert fires(S.window("06:50", "09:00", 10), date(2026, 9, 21))[-1] == "08:50"
    assert fires(S.window("05:47", "06:02", 5), date(2026, 9, 21)) == ["05:50", "05:55", "06:00"]
    assert fires(S.window("05:00", "07:00", 60), date(2026, 9, 21)) == ["05:00", "06:00"]


def test_a_window_with_no_tick_is_refused():
    with pytest.raises(ValueError, match="no 5-minute tick"):
        S.window("06:01", "06:04", 5)


def test_the_scheduler_coalesces_with_an_hours_grace_one_at_a_time():
    scheduler = S.scheduler()
    assert scheduler.timezone == TZ
    assert scheduler._job_defaults == {
        "coalesce": True,
        "misfire_grace_time": MISFIRE_GRACE_S,
        "max_instances": 1,
    }
    assert Schedule(TZ, misfire_grace_s=60).scheduler(max_instances=2)._job_defaults == {
        "coalesce": True,
        "misfire_grace_time": 60,
        "max_instances": 2,
    }


def test_hh_mm_is_range_checked():
    assert parse_hhmm(" 06:30 ") == (6, 30)
    for bad in ("24:00", "6", "06:60", "06:30:00", "six:thirty", None):
        with pytest.raises(ValueError):
            parse_hhmm(bad)
