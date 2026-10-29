import threading
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.enums import Role, TicketStatus
from app.core.events import TicketCreated, TicketResolved, publish
from app.integrations.email import InMemorySender
from app.models import EscalationEvent, Notification, Ticket, TicketEvent
from app.services.handlers import register_all
from app.services.policy import PolicyService
from app.services.sla.timers import Timers
from app.worker import JobContext
from app.worker.jobs import auto_close, reminders, sla_scan
from tests.factories import (
    FACTORY_NOW,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_user,
)

T0 = FACTORY_NOW

type JobRun = Callable[[Session, JobContext], int]


@pytest.fixture(autouse=True)
def handlers() -> None:
    register_all()


def context_at(clock: FrozenClock, settings: Settings, hours: float) -> JobContext:
    clock.set(T0 + timedelta(hours=hours))
    return JobContext(clock=clock, settings=settings, sender=InMemorySender())


def new_ticket(session: Session) -> Ticket:
    it = make_department(session, "IT")
    spoke = make_user(session, it, name="Sam Spoke")
    make_spoke_assignment(session, spoke, it)
    make_user(session, it, role=Role.ADMIN, name="Ada Admin")
    requester = make_user(session, it, name="Rita Requester")
    ticket = make_ticket(session, requester, it)
    publish(session, TicketCreated(actor_id=requester.id, occurred_at=T0, ticket_id=ticket.id))
    session.flush()
    return ticket


def escalation_count(session: Session) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(EscalationEvent)) or 0


def notification_count(session: Session, kind: str) -> int:
    session.expire_all()
    statement = select(func.count()).select_from(Notification).where(Notification.kind == kind)
    return session.scalar(statement) or 0


def run_concurrently(engine: Engine, job: JobRun, context: JobContext) -> list[int]:
    barrier = threading.Barrier(2, timeout=30)
    results: list[int] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def work() -> None:
        try:
            with Session(bind=engine, autoflush=False, expire_on_commit=False) as session:
                barrier.wait()
                outcome = job(session, context)
            with lock:
                results.append(outcome)
        except BaseException as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert errors == []
    return results


def test_scan_twice_records_each_step_once(
    db: Session, clock: FrozenClock, settings: Settings
) -> None:
    new_ticket(db)
    context = context_at(clock, settings, 25)
    assert sla_scan.run(db, context) == 1
    assert sla_scan.run(db, context) == 0
    assert escalation_count(db) == 2
    assert notification_count(db, "escalation") == 2


def test_concurrent_scans_escalate_once(
    committed_db: Session, migrated_engine: Engine, clock: FrozenClock, settings: Settings
) -> None:
    new_ticket(committed_db)
    committed_db.commit()
    results = run_concurrently(migrated_engine, sla_scan.run, context_at(clock, settings, 25))
    assert sorted(results) == [0, 1]
    assert escalation_count(committed_db) == 2
    assert notification_count(committed_db, "sla_warning") == 1
    assert notification_count(committed_db, "escalation") == 2


def test_concurrent_auto_close_closes_once(
    committed_db: Session, migrated_engine: Engine, clock: FrozenClock, settings: Settings
) -> None:
    ticket = new_ticket(committed_db)
    ticket.status = TicketStatus.RESOLVED
    ticket.resolved_at = T0
    publish(committed_db, TicketResolved(actor_id=None, occurred_at=T0, ticket_id=ticket.id))
    committed_db.commit()
    results = run_concurrently(migrated_engine, auto_close.run, context_at(clock, settings, 24 * 8))
    assert sorted(results) == [0, 1]
    committed_db.expire_all()
    closed = committed_db.scalar(
        select(func.count())
        .select_from(TicketEvent)
        .where(TicketEvent.ticket_id == ticket.id, TicketEvent.action == "closed")
    )
    assert closed == 1


def test_concurrent_reminders_notify_once(
    committed_db: Session, migrated_engine: Engine, clock: FrozenClock, settings: Settings
) -> None:
    ticket = new_ticket(committed_db)
    ticket.status = TicketStatus.AWAITING_REQUESTER
    ticket.awaiting_since = T0
    timers = Timers(committed_db, ticket, PolicyService(committed_db).current(), 1.0)
    timers.start_requester_reminder(T0)
    committed_db.commit()
    results = run_concurrently(migrated_engine, reminders.run, context_at(clock, settings, 49))
    assert sorted(results) == [0, 1]
    assert notification_count(committed_db, "requester_reminder") == 1
