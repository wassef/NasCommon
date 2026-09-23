from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from nascommon.bridge.limits import is_limit_message, is_limit_text, parse_reset

TZ = ZoneInfo("Europe/Zurich")
NOW = datetime(2026, 9, 21, 10, 0, tzinfo=TZ)


def test_limit_text_broad():
    assert is_limit_text("claude -p exited 1: You've hit your session limit · resets 4:30pm (Europe/Zurich)")
    assert is_limit_text("429 too many requests")
    assert not is_limit_text("claude -p exited 1: command not found")


def test_limit_message_strict():
    assert is_limit_message("You've hit your session limit · resets 4:30pm")
    assert not is_limit_message("Your CV mentions a rate limit on the API you built")
    assert is_limit_message("Usage limit reached, resets 5pm")


def test_parse_reset_same_day():
    at, raw = parse_reset("resets 4:30pm (Europe/Zurich)", now=NOW)
    assert raw == "4:30pm (Europe/Zurich)"
    assert at == datetime(2026, 9, 21, 16, 30, tzinfo=TZ).astimezone(timezone.utc)


def test_parse_reset_rolls_to_tomorrow():
    at, _ = parse_reset("resets 5am", now=NOW)
    assert at == datetime(2026, 9, 22, 5, 0, tzinfo=TZ).astimezone(timezone.utc)


def test_parse_reset_with_date():
    at, _ = parse_reset("resets Sep 23 at 11:10pm (Europe/Zurich)", now=NOW)
    assert at == datetime(2026, 9, 23, 23, 10, tzinfo=TZ).astimezone(timezone.utc)


def test_parse_reset_garbage():
    assert parse_reset("nothing here", now=NOW) == (None, None)


def test_parse_reset_with_a_date_already_past_is_next_year():
    at, _ = parse_reset("resets Jan 2 at 9am (Europe/Zurich)", now=datetime(2026, 12, 30, 10, 0, tzinfo=TZ))
    assert at == datetime(2027, 1, 2, 9, 0, tzinfo=TZ).astimezone(timezone.utc)


def test_an_unknown_zone_falls_back_to_the_default():
    at, raw = parse_reset("resets 4pm (Mars/Olympus)", now=NOW)
    assert raw == "4pm (Mars/Olympus)"
    assert at == datetime(2026, 9, 21, 16, 0, tzinfo=TZ).astimezone(timezone.utc)


def test_twelve_am_and_pm_and_the_default_now():
    assert parse_reset("resets 12am", now=NOW)[0] == datetime(2026, 9, 22, 0, 0, tzinfo=TZ).astimezone(
        timezone.utc
    )
    assert parse_reset("resets 12pm", now=NOW)[0] == datetime(2026, 9, 21, 12, 0, tzinfo=TZ).astimezone(
        timezone.utc
    )
    at, _ = parse_reset("resets 4:30pm")
    assert at is not None and at > datetime.now(timezone.utc)


def test_an_impossible_date_is_no_reset_rather_than_an_error():
    assert parse_reset("resets Feb 31 at 5pm", now=NOW) == (None, None)
    assert parse_reset(None) == (None, None)
    assert not is_limit_text(None) and not is_limit_message(None)
