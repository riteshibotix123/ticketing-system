from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.core.clock import IST
from app.services.sla.working_time import (
    DEFAULT_CALENDAR,
    WorkingCalendar,
    add_working_time,
    working_time,
)

H = timedelta(hours=1)
MONDAY_HOLIDAY = WorkingCalendar(holidays=frozenset({date(2026, 11, 2)}))


def ist(day: int, hour: int, minute: int = 0, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=IST)


@pytest.mark.parametrize(
    ("start", "amount", "expected"),
    [
        (ist(27, 10), 4 * H, ist(27, 14)),
        (ist(27, 16), 4 * H, ist(28, 11)),
        (ist(30, 16), 4 * H, ist(2, 11, month=11)),
        (ist(27, 7), H, ist(27, 10)),
        (ist(27, 20), H, ist(28, 10)),
        (ist(31, 12), timedelta(0), ist(2, 9, month=11)),
        (ist(27, 9), 9 * H, ist(27, 18)),
        (ist(27, 10), 24 * H, ist(29, 16)),
        (ist(27, 17, 30), timedelta(minutes=45), ist(28, 9, 15)),
    ],
)
def test_add_working_time(start: datetime, amount: timedelta, expected: datetime) -> None:
    result = add_working_time(DEFAULT_CALENDAR, start, amount)
    assert result == expected
    assert result.tzinfo is UTC


def test_add_working_time_skips_holidays() -> None:
    assert add_working_time(MONDAY_HOLIDAY, ist(30, 16), 4 * H) == ist(3, 11, month=11)


def test_add_working_time_uses_custom_days_and_hours() -> None:
    calendar = WorkingCalendar(frozenset({1, 2, 3, 4, 5, 6}), time(10, 0), time(14, 0))
    assert add_working_time(calendar, ist(30, 13), 3 * H) == ist(31, 12)
    assert add_working_time(calendar, ist(31, 13), 2 * H) == ist(2, 11, month=11)


def test_add_working_time_rejects_negative_amount() -> None:
    with pytest.raises(ValueError, match="negative"):
        add_working_time(DEFAULT_CALENDAR, ist(27, 10), -H)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (ist(27, 10), ist(27, 14), 4 * H),
        (ist(27, 10), ist(29, 16), 24 * H),
        (ist(30, 16), ist(2, 11, month=11), 4 * H),
        (ist(27, 19), ist(28, 8), timedelta(0)),
        (ist(28, 10), ist(27, 10), timedelta(0)),
        (ist(31, 0), ist(1, 23, month=11), timedelta(0)),
    ],
)
def test_working_time(start: datetime, end: datetime, expected: timedelta) -> None:
    assert working_time(DEFAULT_CALENDAR, start, end) == expected


def test_working_time_excludes_holidays() -> None:
    assert working_time(MONDAY_HOLIDAY, ist(30, 16), ist(3, 11, month=11)) == 4 * H


def test_working_time_inverts_add_working_time() -> None:
    start = ist(29, 15, 20)
    for hours in (1, 5, 9, 24, 48, 100):
        due = add_working_time(MONDAY_HOLIDAY, start, hours * H)
        assert working_time(MONDAY_HOLIDAY, start, due) == hours * H


@pytest.mark.parametrize(
    ("days", "start", "end"),
    [
        (frozenset(), time(9, 0), time(18, 0)),
        (frozenset({0, 1}), time(9, 0), time(18, 0)),
        (frozenset({1}), time(18, 0), time(9, 0)),
    ],
)
def test_invalid_calendars_are_rejected(days: frozenset[int], start: time, end: time) -> None:
    with pytest.raises(ValueError, match="work"):
        WorkingCalendar(days, start, end)
