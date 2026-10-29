from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.clock import IST
from app.services.sla.due_time import add_business_days, calculate_due, scaled_hours
from app.services.sla.working_time import WorkingCalendar

START = datetime(2026, 10, 27, 4, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("hours", "scale", "expected"),
    [
        (24, 1.0, timedelta(hours=24)),
        (24, 0.5, timedelta(hours=12)),
        (24, 1 / 60, timedelta(minutes=24)),
        (18, 2.0, timedelta(hours=36)),
    ],
)
def test_scaled_hours(hours: int, scale: float, expected: timedelta) -> None:
    assert abs(scaled_hours(hours, scale) - expected) < timedelta(microseconds=10)


def test_calculate_due_calendar() -> None:
    assert calculate_due(START, 24, "calendar", 1.0) == START + timedelta(hours=24)
    assert calculate_due(START, 24, "calendar", 0.5) == START + timedelta(hours=12)


def test_calculate_due_business_counts_working_time() -> None:
    assert calculate_due(START, 24, "business", 1.0) == datetime(2026, 10, 29, 16, 0, tzinfo=IST)
    assert calculate_due(START, 24, "business", 1 / 60) == datetime(
        2026, 10, 27, 10, 24, tzinfo=IST
    )
    late = datetime(2026, 10, 27, 17, 50, tzinfo=IST)
    assert calculate_due(late, 24, "business", 1 / 60) == datetime(2026, 10, 28, 9, 14, tzinfo=IST)
    holiday = WorkingCalendar(holidays=frozenset({date(2026, 10, 28)}))
    assert calculate_due(late, 24, "business", 1 / 60, holiday) == datetime(
        2026, 10, 29, 9, 14, tzinfo=IST
    )


@pytest.mark.parametrize(
    ("start", "days", "expected"),
    [
        (
            datetime(2026, 10, 30, 10, 0, tzinfo=IST),
            3,
            datetime(2026, 11, 4, 10, 0, tzinfo=IST),
        ),
        (
            datetime(2026, 10, 26, 9, 0, tzinfo=IST),
            3,
            datetime(2026, 10, 29, 9, 0, tzinfo=IST),
        ),
        (
            datetime(2026, 10, 31, 12, 0, tzinfo=IST),
            1,
            datetime(2026, 11, 2, 12, 0, tzinfo=IST),
        ),
        (
            datetime(2026, 11, 1, 12, 0, tzinfo=IST),
            5,
            datetime(2026, 11, 6, 12, 0, tzinfo=IST),
        ),
        (
            datetime(2026, 10, 30, 10, 0, tzinfo=IST),
            0,
            datetime(2026, 10, 30, 10, 0, tzinfo=IST),
        ),
    ],
)
def test_add_business_days(start: datetime, days: int, expected: datetime) -> None:
    result = add_business_days(start, days)
    assert result == expected
    assert result.tzinfo is UTC


def test_add_business_days_uses_ist_weekday() -> None:
    friday_night_utc = datetime(2026, 10, 30, 19, 0, tzinfo=UTC)
    assert friday_night_utc.astimezone(IST).weekday() == 5
    assert add_business_days(friday_night_utc, 1) == datetime(2026, 11, 1, 19, 0, tzinfo=UTC)


def test_add_business_days_is_not_scaled() -> None:
    start = datetime(2026, 10, 30, 10, 0, tzinfo=IST)
    assert add_business_days(start, 3) - start == timedelta(days=5)


def test_add_business_days_uses_calendar_days_and_holidays() -> None:
    start = datetime(2026, 10, 30, 10, 0, tzinfo=IST)
    holidays = WorkingCalendar(holidays=frozenset({date(2026, 11, 2), date(2026, 11, 3)}))
    assert add_business_days(start, 1, holidays) == datetime(2026, 11, 4, 10, 0, tzinfo=IST)
    six_days = WorkingCalendar(working_days=frozenset({1, 2, 3, 4, 5, 6}))
    assert add_business_days(start, 1, six_days) == datetime(2026, 10, 31, 10, 0, tzinfo=IST)
