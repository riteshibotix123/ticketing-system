import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.models.identity import RateLimitHit


@dataclass(frozen=True, slots=True)
class RateLimit:
    name: str
    limit: int
    window: timedelta


LOGIN_PER_IP = RateLimit("login:ip", 10, timedelta(minutes=1))
LOGIN_PER_EMAIL = RateLimit("login:email", 10, timedelta(minutes=1))
FORGOT_PER_EMAIL = RateLimit("forgot:email", 3, timedelta(hours=1))


def window_start(now: datetime, window: timedelta) -> datetime:
    seconds = int(window.total_seconds())
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, UTC)


class RateLimiter:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def hit(self, rule: RateLimit, subject: str) -> int | None:
        now = self._clock.now()
        start = window_start(now, rule.window)
        key = f"{rule.name}:{hashlib.sha256(subject.encode()).hexdigest()}"
        statement = (
            insert(RateLimitHit)
            .values(id=uuid.uuid4(), key=key, window_start=start, count=1)
            .on_conflict_do_update(
                index_elements=[RateLimitHit.key, RateLimitHit.window_start],
                set_={"count": RateLimitHit.count + 1},
            )
            .returning(RateLimitHit.count)
        )
        count = self._session.execute(statement).scalar_one()
        if count <= rule.limit:
            return None
        remaining = (start + rule.window - now).total_seconds()
        return max(1, math.ceil(remaining))
