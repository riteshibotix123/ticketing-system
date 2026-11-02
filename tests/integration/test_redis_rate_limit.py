from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from redis import Redis, RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock, get_clock
from app.core.config import Environment, Settings
from app.core.db import get_db, transactional
from app.core.redis import get_redis
from app.main import create_app
from app.models import RateLimitHit
from app.services.rate_limit import (
    LOGIN_PER_EMAIL,
    REDIS_KEY_PREFIX,
    RateLimiter,
    RedisStore,
    window_start,
)

UNREACHABLE_REDIS = "redis://127.0.0.1:1/0"


@pytest.fixture
def redis_settings() -> Settings:
    base = Settings(env=Environment.TEST)
    return Settings(env=Environment.TEST, redis_url=base.test_redis_url)


@pytest.fixture
def redis_client(redis_settings: Settings) -> Iterator[Redis]:
    client = get_redis(redis_settings.redis_url)
    try:
        client.ping()
    except RedisError:
        pytest.skip("Redis is not reachable at TEST_REDIS_URL")
    client.flushdb()
    yield client
    client.flushdb()


def hit_rows(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(RateLimitHit)) or 0


def test_redis_store_counts_and_expires(redis_client: Redis, clock: FrozenClock) -> None:
    store = RedisStore(redis_client)
    start = window_start(clock.now(), timedelta(minutes=1))
    assert store.increment("probe", start, timedelta(minutes=1)) == 1
    assert store.increment("probe", start, timedelta(minutes=1)) == 2
    redis_key = f"{REDIS_KEY_PREFIX}:probe:{int(start.timestamp())}"
    ttl = redis_client.ttl(redis_key)
    assert isinstance(ttl, int)
    assert 0 < ttl <= 120


def test_limiter_uses_redis_and_not_postgres(
    redis_client: Redis, redis_settings: Settings, db: Session, clock: FrozenClock
) -> None:
    limiter = RateLimiter(db, clock, redis_settings)
    for _ in range(LOGIN_PER_EMAIL.limit):
        assert limiter.hit(LOGIN_PER_EMAIL, "ghost@ibotix.ai") is None
    assert limiter.hit(LOGIN_PER_EMAIL, "ghost@ibotix.ai") == 60
    assert hit_rows(db) == 0
    keys = list(redis_client.scan_iter(f"{REDIS_KEY_PREFIX}:*"))
    assert len(keys) == 1


@pytest.mark.usefixtures("redis_client")
def test_limiter_window_resets_in_redis(
    redis_settings: Settings, db: Session, clock: FrozenClock
) -> None:
    limiter = RateLimiter(db, clock, redis_settings)
    for _ in range(LOGIN_PER_EMAIL.limit + 1):
        limiter.hit(LOGIN_PER_EMAIL, "ghost@ibotix.ai")
    clock.advance(timedelta(minutes=1))
    assert limiter.hit(LOGIN_PER_EMAIL, "ghost@ibotix.ai") is None


def test_limiter_falls_back_to_postgres_when_redis_is_down(
    db: Session, clock: FrozenClock, caplog: pytest.LogCaptureFixture
) -> None:
    settings = Settings(env=Environment.TEST, redis_url=UNREACHABLE_REDIS)
    limiter = RateLimiter(db, clock, settings)
    assert limiter.hit(LOGIN_PER_EMAIL, "ghost@ibotix.ai") is None
    assert hit_rows(db) == 1
    assert "redis_unavailable_rate_limit_fallback" in caplog.text


def test_limiter_without_redis_url_uses_postgres(db: Session, clock: FrozenClock) -> None:
    limiter = RateLimiter(db, clock, Settings(env=Environment.TEST))
    limiter.hit(LOGIN_PER_EMAIL, "ghost@ibotix.ai")
    assert hit_rows(db) == 1


@pytest.mark.usefixtures("redis_client")
def test_login_is_rate_limited_through_redis(
    redis_settings: Settings, db: Session, clock: FrozenClock
) -> None:
    app = create_app(redis_settings)

    def override_db() -> Iterator[Session]:
        yield from transactional(db)

    def override_clock() -> Clock:
        return clock

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_clock] = override_clock
    body = {"email": "ghost@ibotix.ai", "password": "Wrong-password-1"}
    with TestClient(app) as client:
        for _ in range(LOGIN_PER_EMAIL.limit):
            assert client.post("/api/v1/auth/login", json=body).status_code == 401
        response = client.post("/api/v1/auth/login", json=body)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert hit_rows(db) == 0
