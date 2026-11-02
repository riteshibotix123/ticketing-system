from collections.abc import Callable, Iterator

import pytest
from redis import Redis, RedisError
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.core.config import Environment, Settings
from app.core.redis import get_redis
from app.integrations.email import InMemorySender
from app.models import WorkerHeartbeat
from app.models.notification import HEARTBEAT_NAME
from app.worker import Job, JobContext
from app.worker.celery_app import (
    CYCLE_LOCK,
    CYCLE_TASK,
    JOB_TASK,
    celery_app,
    create_celery,
    lock_seconds,
    needs_drain,
    run_cycle,
    run_drain_job,
)
from app.worker.jobs import registered_jobs
from app.worker.main import Worker


@pytest.fixture
def celery_settings() -> Settings:
    base = Settings(env=Environment.TEST)
    return Settings(env=Environment.TEST, celery_broker_url=base.test_redis_url)


@pytest.fixture
def redis_client(celery_settings: Settings) -> Iterator[Redis]:
    client = get_redis(celery_settings.celery_broker_url)
    try:
        client.ping()
    except RedisError:
        pytest.skip("Redis is not reachable at TEST_REDIS_URL")
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture
def session_factory(migrated_engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=migrated_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def context(clock: FrozenClock, celery_settings: Settings) -> JobContext:
    return JobContext(clock=clock, settings=celery_settings, sender=InMemorySender())


def fixed_job(name: str, count: int | None, batch_size: int | None, calls: list[str]) -> Job:
    def run(_session: Session, _context: JobContext) -> int:
        calls.append(name)
        if count is None:
            raise RuntimeError("boom")
        return count

    return Job(name=name, run=run, batch_size=batch_size)


def test_celery_app_schedules_the_cycle_every_tick() -> None:
    settings = Settings(env=Environment.TEST, worker_tick_seconds=20)
    app = create_celery(settings)
    entry = app.conf.beat_schedule["worker-cycle"]
    assert entry["task"] == CYCLE_TASK
    assert entry["schedule"] == 20.0
    assert entry["options"] == {"expires": 20.0}
    assert app.conf.task_acks_late is True
    assert app.conf.worker_prefetch_multiplier == 1
    assert app.conf.task_ignore_result is True


def test_tasks_are_registered() -> None:
    assert CYCLE_TASK in celery_app.tasks
    assert JOB_TASK in celery_app.tasks


def test_every_registered_job_has_a_batch_size() -> None:
    assert all(job.batch_size is not None for job in registered_jobs())


def test_lock_outlives_slow_cycles() -> None:
    assert lock_seconds(Settings(env=Environment.TEST, worker_tick_seconds=1)) == 60
    assert lock_seconds(Settings(env=Environment.TEST, worker_tick_seconds=15)) == 150


@pytest.mark.parametrize(
    ("batch_size", "count", "expected"),
    [(20, 20, True), (20, 25, True), (20, 19, False), (20, None, False), (None, 500, False)],
)
def test_needs_drain(batch_size: int | None, count: int | None, expected: bool) -> None:
    assert needs_drain(batch_size, count) is expected


@pytest.mark.usefixtures("redis_client")
def test_cycle_runs_jobs_in_order_and_drains_full_batches(
    committed_db: Session,
    session_factory: Callable[[], Session],
    context: JobContext,
    celery_settings: Settings,
    clock: FrozenClock,
) -> None:
    calls: list[str] = []
    jobs = [
        fixed_job("full", 100, 100, calls),
        fixed_job("partial", 3, 100, calls),
        fixed_job("broken", None, 100, calls),
        fixed_job("unbatched", 900, None, calls),
    ]
    worker = Worker(session_factory, context, jobs, tick_seconds=0)
    drained: list[str] = []

    results = run_cycle(celery_settings, worker, drained.append)

    assert results == {"full": 100, "partial": 3, "broken": None, "unbatched": 900}
    assert calls == ["full", "partial", "broken", "unbatched"]
    assert drained == ["full"]
    row = committed_db.get(WorkerHeartbeat, HEARTBEAT_NAME)
    assert row is not None
    assert row.last_seen_at == clock.now()
    assert row.details == {"jobs": results, "failed": ["broken"]}


def test_cycle_releases_the_lock(
    redis_client: Redis,
    session_factory: Callable[[], Session],
    context: JobContext,
    celery_settings: Settings,
) -> None:
    worker = Worker(session_factory, context, [], tick_seconds=0)
    run_cycle(celery_settings, worker, lambda _name: None)
    assert redis_client.exists(CYCLE_LOCK) == 0


def test_cycle_is_skipped_while_another_cycle_holds_the_lock(
    redis_client: Redis,
    session_factory: Callable[[], Session],
    context: JobContext,
    celery_settings: Settings,
) -> None:
    calls: list[str] = []
    worker = Worker(session_factory, context, [fixed_job("job", 1, 10, calls)], tick_seconds=0)
    redis_client.set(CYCLE_LOCK, "other-worker", ex=60)

    assert run_cycle(celery_settings, worker, lambda _name: None) is None
    assert calls == []


@pytest.mark.parametrize(("count", "requeued"), [(20, ["outbox"]), (4, []), (None, [])])
def test_drain_job_requeues_only_while_batches_are_full(
    session_factory: Callable[[], Session],
    context: JobContext,
    count: int | None,
    requeued: list[str],
) -> None:
    calls: list[str] = []
    worker = Worker(
        session_factory, context, [fixed_job("outbox", count, 20, calls)], tick_seconds=0
    )
    requeues: list[str] = []

    assert run_drain_job(worker, "outbox", requeues.append) == count
    assert calls == ["outbox"]
    assert requeues == requeued


def test_drain_job_rejects_unknown_names(
    session_factory: Callable[[], Session], context: JobContext
) -> None:
    worker = Worker(session_factory, context, [], tick_seconds=0)
    with pytest.raises(KeyError):
        run_drain_job(worker, "missing", lambda _name: None)
