"""UK-local-calendar UTC windows for fetching Agile rates.

Kept separate from notifiers/telegram.py (which knows nothing about how
slots were fetched) and from octopus_core (which only knows how to fetch an
arbitrary window, not which window to ask for). If a future project besides
this Telegram bot ends up wanting the same "today remaining" / "tomorrow"
windows, this is a reasonable candidate to promote into octopus_core --
but that's not worth doing speculatively for a single consumer.
"""

import datetime as dt
from zoneinfo import ZoneInfo

LONDON_TZ = ZoneInfo("Europe/London")


def todays_remaining_utc_window() -> tuple[dt.datetime, dt.datetime]:
    """Return (period_from, period_to) in UTC spanning from now until midnight, UK local time."""
    now_local = dt.datetime.now(LONDON_TZ)
    tomorrow_local = now_local.date() + dt.timedelta(days=1)
    end_local = dt.datetime(tomorrow_local.year, tomorrow_local.month, tomorrow_local.day, 0, 0, tzinfo=LONDON_TZ)
    return (now_local.astimezone(dt.timezone.utc), end_local.astimezone(dt.timezone.utc))


def tomorrows_utc_window() -> tuple[dt.datetime, dt.datetime]:
    """Return (period_from, period_to) in UTC spanning tomorrow, UK local time."""
    today_local = dt.datetime.now(LONDON_TZ).date()
    tomorrow_local = today_local + dt.timedelta(days=1)
    start = dt.datetime(tomorrow_local.year, tomorrow_local.month, tomorrow_local.day, 0, 0, tzinfo=LONDON_TZ)
    end = start + dt.timedelta(days=1)
    return (start.astimezone(dt.timezone.utc), end.astimezone(dt.timezone.utc))
