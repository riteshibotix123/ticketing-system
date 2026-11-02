import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Any, Final

from celery import Celery
from celery.signals import setup_logging
from redis.exceptions import LockError

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.redis import get_redis
from app.services.handlers import register_all
from app.worker.main import Worker, build_worker

CYCLE_TASK: Final = "ibotix.cycle"
JOB_TASK: Final = "ibotix.job"
CYCLE_LOCK: Final = "ibotix:worker:cycle"
MIN_LOCK_SECONDS: Final = 60
LOCK_TICKS: Final = 10

logger = logging.getLogger("app.worker.celery")

Results = dict[str, int | None]


def create_celery(settings: Settings) -> Celery:
    app = Celery("ibotix", broker=settings.celery_broker_url)
    tick = float(settings.worker_tick_seconds)
    app.conf.update(
        task_ignore_result=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        worker_hijack_root_logger=False,
        broker_connection_retry_on_startup=True,
        enable_utc=True,
        timezone="UTC",
        beat_schedule={
            "worker-cycle": {
                "task": CYCLE_TASK,
                "schedule": tick,
                "options": {"expires": tick},
            }
        },
    )
    return app


celery_app = create_celery(get_settings())


@setup_logging.connect
def _configure_logging(**_kwargs: Any) -> None:
    configure_logging()


@lru_cache(maxsize=1)
def process_worker() -> Worker:
    register_all()
    return build_worker(get_settings())


def lock_seconds(settings: Settings) -> int:
    return max(MIN_LOCK_SECONDS, LOCK_TICKS * settings.worker_tick_seconds)


def needs_drain(batch_size: int | None, count: int | None) -> bool:
    return batch_size is not None and count is not None and count >= batch_size


def run_cycle(settings: Settings, worker: Worker, drain: Callable[[str], None]) -> Results | None:
    lock = get_redis(settings.celery_broker_url).lock(
        CYCLE_LOCK, timeout=lock_seconds(settings), blocking=False
    )
    if not lock.acquire():
        logger.info("worker cycle skipped because the previous cycle is still running")
        return None
    try:
        results = worker.tick()
    finally:
        try:
            lock.release()
        except LockError:
            logger.warning("worker cycle lock expired before release")
    for job in worker.jobs:
        if needs_drain(job.batch_size, results.get(job.name)):
            drain(job.name)
    return results


def run_drain_job(worker: Worker, name: str, requeue: Callable[[str], None]) -> int | None:
    job = worker.job(name)
    count = worker.run_job(job)
    if needs_drain(job.batch_size, count):
        requeue(name)
    return count


def dispatch_drain(name: str) -> None:
    for _ in range(get_settings().celery_drain_fanout):
        drain_job.apply_async(args=(name,))


def requeue_drain(name: str) -> None:
    drain_job.apply_async(args=(name,))


@celery_app.task(name=CYCLE_TASK)
def cycle() -> Results | None:
    return run_cycle(get_settings(), process_worker(), dispatch_drain)


@celery_app.task(name=JOB_TASK)
def drain_job(name: str) -> int | None:
    return run_drain_job(process_worker(), name, requeue_drain)
