"""APScheduler triggers that fire when they say, in a container that runs on UTC.

A `CronTrigger` built without `timezone=` fires in the machine's zone, and Docker's is UTC: a
06:30 brief went out at 08:30 in summer. So every trigger here carries the app's zone. And a NAS
drops its network while its disks hibernate, so the scheduler coalesces missed runs into one and
gives each an hour's grace instead of silently dropping a once-a-day job.

    schedule = Schedule(ZoneInfo("Europe/Zurich"))
    scheduler = schedule.scheduler()
    scheduler.add_job(send_brief, schedule.cron_at("06:30"))
    scheduler.add_job(poll, schedule.window("05:45", "06:30", 5))
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

MISFIRE_GRACE_S = 3600


def parse_hhmm(value: object) -> tuple[int, int]:
    """ "06:30" → (6, 30). `ValueError` for anything that is not a real time of day: "24:00" is two
    integers and no time of day, and it reached APScheduler's cron fields as a scheduler that
    refused to start."""
    parts = str(value).strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"{value!r} is not hh:mm")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"{value!r} is not a time of day")
    return hour, minute


class Schedule:
    """Trigger builders bound to one zone. Import APScheduler only when a trigger is built."""

    def __init__(self, tz: ZoneInfo, *, misfire_grace_s: int = MISFIRE_GRACE_S):
        self.tz = tz
        self.misfire_grace_s = misfire_grace_s

    def cron(self, **fields: Any) -> Any:
        from apscheduler.triggers.cron import CronTrigger

        fields.setdefault("timezone", self.tz)
        return CronTrigger(**fields)

    def cron_at(self, hhmm: str, **fields: Any) -> Any:
        hour, minute = parse_hhmm(hhmm)
        return self.cron(hour=hour, minute=minute, **fields)

    def interval(self, **fields: Any) -> Any:
        from apscheduler.triggers.interval import IntervalTrigger

        fields.setdefault("timezone", self.tz)
        return IntervalTrigger(**fields)

    def window(self, start_hhmm: str, end_hhmm: str, every_min: int) -> Any:
        """Every `every_min` minutes from `start` up to, not including, `end`, on the hour's grid.

        A job gated to 05:45–06:30 on `cron(hour="5-6", minute="*/5")` fired 24 times to run 9 and
        logged a skip for each of the other 15. One cron per hour of the window fires only inside
        it. A window does not cross midnight.
        """
        from apscheduler.triggers.combining import OrTrigger

        sh, sm = parse_hhmm(start_hhmm)
        eh, em = parse_hhmm(end_hhmm)
        crons = []
        for hour in range(sh, eh + 1):
            first = sm if hour == sh else 0
            first = -(-first // every_min) * every_min  # up to the grid
            last = em - 1 if hour == eh else 59
            minutes = range(first, last + 1, every_min)
            if minutes:  # a list, not `a-b/step`: cron refuses a step wider than its range
                crons.append(self.cron(hour=hour, minute=",".join(str(m) for m in minutes)))
        if not crons:
            raise ValueError(f"the window {start_hhmm}-{end_hhmm} holds no {every_min}-minute tick")
        return OrTrigger(crons)

    def scheduler(self, **job_defaults: Any) -> Any:
        """An `AsyncIOScheduler` in this zone: missed runs coalesce, with the grace, one at a time."""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        defaults = {"coalesce": True, "misfire_grace_time": self.misfire_grace_s, "max_instances": 1}
        defaults.update(job_defaults)
        return AsyncIOScheduler(timezone=self.tz, job_defaults=defaults)
