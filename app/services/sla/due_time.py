from datetime import UTC, datetime, timedelta
from typing import Literal

from app.core.clock import to_ist
from app.services.sla.working_time import DEFAULT_CALENDAR, WorkingCalendar, add_working_time

SlaModeName = Literal["calendar", "business"]


def scaled_hours(hours: float, scale: float) -> timedelta:
    return timedelta(hours=hours * scale)


def calculate_due(
    start: datetime,
    hours: float,
    mode: SlaModeName,
    scale: float,
    calendar: WorkingCalendar = DEFAULT_CALENDAR,
) -> datetime:
    amount = scaled_hours(hours, scale)
    if mode == "business":
        return add_working_time(calendar, start, amount)
    return start + amount


def add_business_days(
    start: datetime, days: int, calendar: WorkingCalendar = DEFAULT_CALENDAR
) -> datetime:
    if days < 0:
        raise ValueError("days must not be negative")
    current = to_ist(start)
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if calendar.is_working_day(current.date()):
            remaining -= 1
    return current.astimezone(UTC)
