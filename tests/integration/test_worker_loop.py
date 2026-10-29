import signal
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.events import EscalationRaised, EventBus, SlaWarningRaised, TicketClosed, bus
from app.integrations.email import InMemorySender
from app.models import EmailOutbox, EmailStatus, WorkerHeartbeat
from app.models.notification import HEARTBEAT_NAME
from app.services.handlers import register_all
from app.worker import Job, JobContext
from app.worker import main as worker_main
from app.worker.jobs import registered_jobs
from app.worker.main import Worker, install_signal_handlers
from tests.factories import make_outbox_email


@pytest.fixture
def session_factory(migrated_engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=migrated_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def sender() -> InMemorySender:
    return InMemorySender()


@pytest.fixture
def context(clock: FrozenClock, settings: Settings, sender: InMemorySender) -> JobContext:
    return JobContext(clock=clock, settings=settings, sender=sender)


def failing_job(_session: Session, _context: JobContext) -> int:
    raise RuntimeError("boom")


def heartbeat(committed_db: Session) -> WorkerHeartbeat:
    committed_db.expire_all()
    row = committed_db.get(WorkerHeartbeat, HEARTBEAT_NAME)
    assert row is not None
    return row


def test_registered_jobs_run_send_outbox_last() -> None:
    assert [job.name for job in registered_jobs()] == [
        "sla_scan",
        "reminders",
        "auto_close",
        "protected_action_expiry",
        "housekeeping",
        "digest",
        "send_outbox",
    ]


def test_tick_survives_failing_job_and_updates_heartbeat(
    committed_db: Session,
    session_factory: Callable[[], Session],
    context: JobContext,
    clock: FrozenClock,
) -> None:
    calls: list[str] = []

    def counting_job(_session: Session, _context: JobContext) -> int:
        calls.append("ran")
        return 7

    worker = Worker(
        session_factory,
        context,
        [Job(name="broken", run=failing_job), Job(name="counting", run=counting_job)],
        tick_seconds=0,
    )

    assert worker.tick() == {"broken": None, "counting": 7}
    assert calls == ["ran"]
    row = heartbeat(committed_db)
    assert row.last_seen_at == clock.now()
    assert row.details == {"jobs": {"broken": None, "counting": 7}, "failed": ["broken"]}

    clock.advance(timedelta(seconds=15))
    worker.tick()
    assert heartbeat(committed_db).last_seen_at == clock.now()


def test_run_forever_keeps_looping_until_stopped(
    committed_db: Session,
    session_factory: Callable[[], Session],
    context: JobContext,
) -> None:
    ticks: list[int] = []
    worker: Worker | None = None

    def stopper(_session: Session, _context: JobContext) -> int:
        ticks.append(len(ticks) + 1)
        if len(ticks) == 3 and worker is not None:
            worker.stop()
        return 0

    worker = Worker(
        session_factory,
        context,
        [Job(name="broken", run=failing_job), Job(name="stopper", run=stopper)],
        tick_seconds=0,
    )
    worker.run_forever()

    assert ticks == [1, 2, 3]
    assert worker.stopping
    assert heartbeat(committed_db).details["failed"] == ["broken"]


def test_tick_runs_send_outbox(
    committed_db: Session,
    session_factory: Callable[[], Session],
    context: JobContext,
    sender: InMemorySender,
    clock: FrozenClock,
) -> None:
    make_outbox_email(committed_db, "a@ibotix.ai", at=clock.now())
    committed_db.commit()
    worker = Worker(session_factory, context, registered_jobs(), tick_seconds=0)

    assert worker.tick() == {
        "sla_scan": 0,
        "reminders": 0,
        "auto_close": 0,
        "protected_action_expiry": 0,
        "housekeeping": 0,
        "digest": 0,
        "send_outbox": 1,
    }

    committed_db.expire_all()
    assert committed_db.scalars(select(EmailOutbox.status)).all() == [EmailStatus.SENT]
    assert [message.to_address for message in sender.sent] == ["a@ibotix.ai"]


def test_sigterm_stops_worker(session_factory: Callable[[], Session], context: JobContext) -> None:
    worker = Worker(session_factory, context, [], tick_seconds=0)
    original_term = signal.getsignal(signal.SIGTERM)
    original_int = signal.getsignal(signal.SIGINT)
    try:
        install_signal_handlers(worker)
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)
    finally:
        signal.signal(signal.SIGTERM, original_term)
        signal.signal(signal.SIGINT, original_int)

    assert worker.stopping


def test_main_registers_event_handlers(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    started: list[Worker] = []
    monkeypatch.setattr(worker_main, "configure_logging", lambda: None)
    monkeypatch.setattr(worker_main, "get_settings", lambda: settings)
    monkeypatch.setattr(worker_main, "install_signal_handlers", lambda _worker: None)
    monkeypatch.setattr(Worker, "run_forever", lambda self: started.append(self))
    expected = EventBus()
    register_all(expected)
    bus.clear()

    worker_main.main()

    assert len(started) == 1
    for event_type in (SlaWarningRaised, EscalationRaised, TicketClosed):
        assert bus.handler_count(event_type) == expected.handler_count(event_type) > 0
