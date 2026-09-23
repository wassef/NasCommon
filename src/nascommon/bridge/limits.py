"""Telling a usage limit from any other failure of the tool-less `claude -p` bridge.

When the Claude subscription behind the bridge runs out of its rolling session or weekly budget,
`claude -p` says so in words: "You've hit your session limit · resets 4:30pm (Europe/Zurich)".
The bridge returns that as HTTP 502 with the CLI's stderr tail in `detail`; a CLI that printed it
to stdout and exited 0 would hand it back as the *content* of a successful answer. The wording is
undocumented and changes between versions, so every helper here is best-effort and pure: `now`
is a parameter.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Europe/Zurich"

LIMIT_PATTERNS = (
    "session limit",
    "hit your session limit",
    "weekly limit",
    "usage limit",
    "rate limit",
    "too many requests",
    "quota",
)
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1
    )
}
_TIME_RE = re.compile(r"\d{1,2}(?::\d{2})?\s*[ap]m", re.IGNORECASE)
_RESET_RE = re.compile(
    r"(?:(?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(?P<day>\d{1,2})\s+at\s+)?"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)"
    r"(?:\s*\((?P<tz>[^)]+)\))?",
    re.IGNORECASE,
)


def is_limit_text(text: str | None) -> bool:
    """Broad match, for an error body: a failed `claude -p` is context enough."""
    t = (text or "").lower()
    return any(p in t for p in LIMIT_PATTERNS)


def is_limit_message(text: str | None) -> bool:
    """Strict match, for successful content: a CV that mentions "rate limit" is not a limit.

    Only the explicit "hit your … limit", or "limit … resets <time>", counts.
    """
    t = (text or "").lower()
    if any(p in t for p in ("hit your session limit", "hit your weekly limit", "hit your usage limit")):
        return True
    return "limit" in t and "resets" in t and bool(_TIME_RE.search(text or ""))


def parse_reset(
    text: str | None, now: datetime | None = None, *, default_tz: str = DEFAULT_TZ
) -> tuple[datetime | None, str | None]:
    """A reset phrase → (UTC instant, the phrase as written); (None, None) on any failure.

    Shapes seen: '4:30pm (Europe/Zurich)', 'Jul 4 at 11:10pm (Europe/Zurich)', 'Jul 7 at 5am'. A
    clock time already past today is tomorrow's; a date already past (by more than an hour) is
    next year's, which is the December → January wrap.
    """
    try:
        m = _RESET_RE.search(text or "")
        if not m:
            return None, None
        try:
            tz = ZoneInfo(m.group("tz").strip()) if m.group("tz") else ZoneInfo(default_tz)
        except Exception:
            tz = ZoneInfo(default_tz)
        hour = int(m.group("hour")) % 12
        if m.group("ampm").lower() == "pm":
            hour += 12
        minute = int(m.group("minute")) if m.group("minute") else 0
        now = (now or datetime.now(tz)).astimezone(tz)
        if m.group("month"):
            month = _MONTHS[m.group("month").lower()]
            day = int(m.group("day"))
            candidate = datetime(now.year, month, day, hour, minute, tzinfo=tz)
            if candidate < now - timedelta(hours=1):
                candidate = candidate.replace(year=now.year + 1)
        else:
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc), m.group(0).strip()
    except Exception:  # reset parsing must never break limit handling
        return None, None
