"""The one definition of "now" for a Delhi audience.

Every reader is in India; the container ships configured for UTC. Anything
that asks "what day is it" or "what hour is it" must ask in IST, or it is
wrong for the five and a half hours after midnight UTC. Import ``IST``,
``now_ist`` and ``today_ist`` from here rather than rebuilding a fixed offset
locally -- two independent notions of "now" is how this class of bug spreads.

India has a single time zone and has observed no DST since 1945, so the fixed
+05:30 offset is exact and needs no zoneinfo database.
"""
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def now_ist() -> datetime:
    """Current instant as an aware datetime in IST."""
    return datetime.now(IST)


def today_ist() -> date:
    """Today's calendar date in India, regardless of server time zone."""
    return now_ist().date()


def to_ist(dt: datetime) -> datetime:
    """Convert an aware datetime to IST; naive input is read as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)
