from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Final

from app.core.clock import IST, to_ist

DEFAULT_WORKING_DAYS: Final = frozenset({1, 2, 3, 4, 5})
DEFAULT_WORK_START: Final = time(9, 0)
DEFAULT_WORK_END: Final = time(18, 0)
ONE_DAY: Final = timedelta(days=1)
MIDNIGHT: Final = time(0, 0)


@dataclass(frozen=True, slots=True)
class WorkingCalendar:
    working_days: frozenset[int] = DEFAULT_WORKING_DAYS
    work_start: time = DEFAULT_WORK_START
    work_end: time = DEFAULT_WORK_END
    holidays: frozenset[date] = frozenset()

    def __post_init__(self) -> None:
        if not self.working_days or not self.working_days <= frozenset(range(1, 8)):
            raise ValueError("working days must be ISO weekdays and not empty")
        if self.work_start >= self.work_end:
            raise ValueError("work_start must be before work_end")

    def is_working_day(self, day: date) -> bool:
        return day.isoweekday() in self.working_days and day not in self.holidays

    def hours_of(self, day: date) -> tuple[datetime, datetime]:
        return (
            datetime.combine(day, self.work_start, IST),
            datetime.combine(day, self.work_end, IST),
        )


DEFAULT_CALENDAR: Final = WorkingCalendar()


def add_working_time(calendar: WorkingCalendar, start: datetime, amount: timedelta) -> datetime:
    if amount < timedelta(0):
        raise ValueError("amount must not be negative")
    current = to_ist(start)
    remaining = amount
    day = current.date()
    while True:
        if calendar.is_working_day(day):
            opens, closes = calendar.hours_of(day)
            begin = max(current, opens)
            if begin < closes:
                available = closes - begin
                if remaining <= available:
                    return (begin + remaining).astimezone(UTC)
                remaining -= available
        day += ONE_DAY
        current = datetime.combine(day, MIDNIGHT, IST)


def working_time(calendar: WorkingCalendar, start: datetime, end: datetime) -> timedelta:
    if end <= start:
        return timedelta(0)
    begin = to_ist(start)
    finish = to_ist(end)
    total = timedelta(0)
    day = begin.date()
    while day <= finish.date():
        if calendar.is_working_day(day):
            opens, closes = calendar.hours_of(day)
            low = max(begin, opens)
            high = min(finish, closes)
            if high > low:
                total += high - low
        day += ONE_DAY
    return total
