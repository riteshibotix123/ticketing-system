import logging
import signal
import threading
import time
from collections.abc import Callable, Sequence
from types import FrameType

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import SystemClock
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging
from app.core.types import JsonObject, JsonValue
from app.integrations.email import build_sender
from app.models.notification import WorkerHeartbeat
from app.worker import Job, JobContext
from app.worker.jobs import registered_jobs

HEARTBEAT_NAME = "worker"

logger = logging.getLogger("app.worker")


class Worker:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        context: JobContext,
        jobs: Sequence[Job],
        tick_seconds: float,
    ) -> None:
        self._session_factory = session_factory
        self._context = context
        self._jobs = list(jobs)
        self._tick_seconds = tick_seconds
        self._stop = threading.Event()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        logger.info("worker started")
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self._tick_seconds)
        logger.info("worker stopped")

    def tick(self) -> dict[str, int | None]:
        results: dict[str, int | None] = {}
        for job in self._jobs:
            if self._stop.is_set():
                break
            results[job.name] = self._run_job(job)
        self._beat(results)
        return results

    def _run_job(self, job: Job) -> int | None:
        started = time.perf_counter()
        with self._session_factory() as session:
            try:
                count = job.run(session, self._context)
            except Exception:
                session.rollback()
                duration_ms = _elapsed_ms(started)
                logger.exception(
                    "job %s failed after %d ms",
                    job.name,
                    duration_ms,
                    extra={"duration_ms": duration_ms},
                )
                return None
        duration_ms = _elapsed_ms(started)
        logger.info(
            "job %s processed %d items in %d ms",
            job.name,
            count,
            duration_ms,
            extra={"duration_ms": duration_ms},
        )
        return count

    def _beat(self, results: dict[str, int | None]) -> None:
        jobs: JsonObject = {}
        failed: list[JsonValue] = []
        for name, count in results.items():
            jobs[name] = count
            if count is None:
                failed.append(name)
        details: JsonObject = {"jobs": jobs, "failed": failed}
        now = self._context.clock.now()
        statement = insert(WorkerHeartbeat).values(
            name=HEARTBEAT_NAME, last_seen_at=now, details=details
        )
        statement = statement.on_conflict_do_update(
            index_elements=[WorkerHeartbeat.name],
            set_={"last_seen_at": now, "details": details},
        )
        try:
            with self._session_factory() as session:
                session.execute(statement)
                session.commit()
        except Exception:
            logger.exception("worker heartbeat failed")


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def install_signal_handlers(worker: Worker) -> None:
    def handle(signum: int, _frame: FrameType | None) -> None:
        logger.info("worker received signal %d", signum)
        worker.stop()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)


def main() -> None:
    configure_logging()
    settings = get_settings()
    context = JobContext(clock=SystemClock(), settings=settings, sender=build_sender(settings))
    worker = Worker(SessionLocal, context, registered_jobs(), settings.worker_tick_seconds)
    install_signal_handlers(worker)
    worker.run_forever()


if __name__ == "__main__":
    main()
