from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.clock import FrozenClock, SystemClock, get_clock, to_ist


def test_system_clock_returns_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_get_clock_returns_system_clock() -> None:
    assert isinstance(get_clock(), SystemClock)


def test_frozen_clock_fixture_time(clock: FrozenClock) -> None:
    assert clock.now() == datetime(2026, 10, 27, 4, 30, tzinfo=UTC)


def test_frozen_clock_is_stable(clock: FrozenClock) -> None:
    assert clock.now() == clock.now()


def test_frozen_clock_advance(clock: FrozenClock) -> None:
    result = clock.advance(timedelta(hours=2, minutes=15))
    assert result == datetime(2026, 10, 27, 6, 45, tzinfo=UTC)
    assert clock.now() == result


def test_frozen_clock_set_normalizes_to_utc(clock: FrozenClock) -> None:
    clock.set(datetime(2026, 11, 2, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))))
    assert clock.now() == datetime(2026, 11, 2, 3, 30, tzinfo=UTC)
    assert clock.now().tzinfo is UTC


def test_frozen_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FrozenClock(datetime(2026, 10, 27, 4, 30))


def test_frozen_clock_set_rejects_naive_datetime(clock: FrozenClock) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        clock.set(datetime(2026, 10, 27, 4, 30))


def test_to_ist_converts_utc() -> None:
    ist = to_ist(datetime(2026, 10, 27, 4, 30, tzinfo=UTC))
    assert (ist.year, ist.month, ist.day, ist.hour, ist.minute) == (2026, 10, 27, 10, 0)
    assert ist.utcoffset() == timedelta(hours=5, minutes=30)


def test_to_ist_crosses_date_boundary() -> None:
    ist = to_ist(datetime(2026, 12, 31, 19, 0, tzinfo=UTC))
    assert (ist.year, ist.month, ist.day, ist.hour, ist.minute) == (2027, 1, 1, 0, 30)


def test_to_ist_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        to_ist(datetime(2026, 10, 27, 4, 30))
