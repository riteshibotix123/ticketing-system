from datetime import UTC, datetime, timedelta, timezone
from typing import Protocol

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    def __init__(self, at: datetime) -> None:
        self._now = _require_aware(at).astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def set(self, at: datetime) -> None:
        self._now = _require_aware(at).astimezone(UTC)

    def advance(self, delta: timedelta) -> datetime:
        self._now = self._now + delta
        return self._now


_system_clock = SystemClock()


def get_clock() -> Clock:
    return _system_clock


def to_ist(value: datetime) -> datetime:
    return _require_aware(value).astimezone(IST)
