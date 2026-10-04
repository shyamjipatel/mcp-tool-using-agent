"""Timezone-aware current time."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel


class TimeError(ValueError):
    """The requested timezone is invalid."""


class TimeResult(BaseModel):
    timezone: str
    datetime: str
    formatted: str


def get_time(timezone: str) -> TimeResult:
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise TimeError(f"Unknown timezone: {timezone}") from exc
    now = datetime.now(zone)
    return TimeResult(
        timezone=timezone,
        datetime=now.isoformat(timespec="seconds"),
        formatted=now.strftime("%Y-%m-%d %H:%M:%S %Z"),
    )
