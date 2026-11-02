import hashlib
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from redis import Redis, RedisError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.redis import get_redis
from app.models.identity import RateLimitHit

logger = logging.getLogger("app.rate_limit")

REDIS_KEY_PREFIX = "ratelimit"


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


class RateLimitStore(Protocol):
    def increment(self, key: str, start: datetime, window: timedelta, /) -> int: ...


class DatabaseStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def increment(self, key: str, start: datetime, _window: timedelta, /) -> int:
        statement = (
            insert(RateLimitHit)
            .values(id=uuid.uuid4(), key=key, window_start=start, count=1)
            .on_conflict_do_update(
                index_elements=[RateLimitHit.key, RateLimitHit.window_start],
                set_={"count": RateLimitHit.count + 1},
            )
            .returning(RateLimitHit.count)
        )
        return self._session.execute(statement).scalar_one()


class RedisStore:
    def __init__(self, client: Redis) -> None:
        self._client = client

    def increment(self, key: str, start: datetime, window: timedelta, /) -> int:
        redis_key = f"{REDIS_KEY_PREFIX}:{key}:{int(start.timestamp())}"
        pipeline = self._client.pipeline()
        pipeline.incr(redis_key)
        pipeline.expire(redis_key, 2 * int(window.total_seconds()), nx=True)
        count, _ = pipeline.execute()
        return int(count)


class RateLimiter:
    def __init__(self, session: Session, clock: Clock, settings: Settings | None = None) -> None:
        self._clock = clock
        self._database: RateLimitStore = DatabaseStore(session)
        self._redis: RateLimitStore | None = (
            RedisStore(get_redis(settings.redis_url))
            if settings is not None and settings.redis_url
            else None
        )

    def hit(self, rule: RateLimit, subject: str) -> int | None:
        now = self._clock.now()
        start = window_start(now, rule.window)
        key = f"{rule.name}:{hashlib.sha256(subject.encode()).hexdigest()}"
        count = self._increment(key, start, rule.window)
        if count <= rule.limit:
            return None
        remaining = (start + rule.window - now).total_seconds()
        return max(1, math.ceil(remaining))

    def _increment(self, key: str, start: datetime, window: timedelta) -> int:
        if self._redis is not None:
            try:
                return self._redis.increment(key, start, window)
            except RedisError:
                logger.warning("redis_unavailable_rate_limit_fallback")
        return self._database.increment(key, start, window)
