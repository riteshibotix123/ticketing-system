import threading
import uuid
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import timedelta

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Environment, Settings
from app.core.enums import Priority, TicketStatus
from app.core.errors import ApiError
from app.integrations.email import InMemorySender
from app.models import EmailOutbox, EmailStatus, EscalationEvent, Notification, Ticket, TicketEvent
from app.policy.actors import load_actor
from app.schemas.tickets import CreateTicketBody
from app.schemas.workflow import AcknowledgeBody
from app.services.handlers import register_all
from app.services.tickets import TicketService
from app.services.workflow.progress import ProgressService
from app.worker import JobContext
from app.worker.jobs import send_outbox, sla_scan
from tests.conftest import FROZEN_NOW
from tests.scenarios.helpers import Org, build_org

THREADS = 20
TIMEOUT = 60


@pytest.fixture
def committed(committed_db: Session) -> Session:
    register_all()
    return committed_db


@pytest.fixture
def committed_org(committed: Session) -> Org:
    return build_org(committed)


@pytest.fixture
def engine(test_database_url: str) -> Iterator[Engine]:
    pool = create_engine(test_database_url, pool_size=THREADS, max_overflow=0)
    yield pool
    pool.dispose()


def run_parallel(count: int, work: Callable[[int, Session], None], engine: Engine) -> list[str]:
    barrier = threading.Barrier(count, timeout=TIMEOUT)
    outcomes: list[str] = []
    lock = threading.Lock()

    def target(index: int) -> None:
        outcome = "ok"
        try:
            with Session(bind=engine, autoflush=False, expire_on_commit=False) as session:
                barrier.wait()
                work(index, session)
                session.commit()
        except ApiError as exc:
            outcome = exc.code.value
        except BaseException as exc:
            outcome = f"error: {exc!r}"
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=target, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=TIMEOUT)
    return outcomes


def create_ticket(session: Session, user_id: uuid.UUID, clock: FrozenClock) -> str:
    actor = load_actor(session, user_id)
    assert actor is not None
    body = CreateTicketBody(
        department_id="HR",
        title="Parallel",
        description="Raised in parallel",
        priority=Priority.MEDIUM,
    )
    return TicketService(session, clock, Settings(env=Environment.TEST)).create(actor, body).id


def test_twenty_parallel_creations_get_unique_numbers(
    committed: Session, committed_org: Org, engine: Engine
) -> None:
    clock = FrozenClock(FROZEN_NOW)
    requester = committed_org["asha"].id

    def work(_index: int, session: Session) -> None:
        create_ticket(session, requester, clock)

    assert run_parallel(THREADS, work, engine) == ["ok"] * THREADS
    numbers = sorted(committed.scalars(select(Ticket.ticket_no)))
    assert numbers == [f"IBX-HR-2026-{index:06d}" for index in range(1, THREADS + 1)]


def test_two_acknowledgements_one_wins(
    committed: Session, committed_org: Org, engine: Engine
) -> None:
    clock = FrozenClock(FROZEN_NOW)
    number = create_ticket(committed, committed_org["asha"].id, clock)
    committed.commit()
    spokes = [committed_org["neha"].id, committed_org["hari"].id]
    body = AcknowledgeBody(eta=FROZEN_NOW + timedelta(days=2))

    def work(index: int, session: Session) -> None:
        actor = load_actor(session, spokes[index])
        assert actor is not None
        ProgressService(session, clock).acknowledge(actor, number, body)

    outcomes = run_parallel(2, work, engine)
    assert sorted(outcomes) == ["invalid_transition", "ok"]
    committed.expire_all()
    ticket = committed.scalars(select(Ticket).where(Ticket.ticket_no == number)).one()
    assert ticket.status is TicketStatus.ACKNOWLEDGED
    assert ticket.owner_id in spokes
    events = committed.scalars(
        select(TicketEvent.action).where(
            TicketEvent.ticket_id == ticket.id, TicketEvent.action == "acknowledged"
        )
    ).all()
    assert events == ["acknowledged"]


def test_two_schedulers_record_one_escalation(
    committed: Session, committed_org: Org, engine: Engine
) -> None:
    created = FrozenClock(FROZEN_NOW)
    number = create_ticket(committed, committed_org["asha"].id, created)
    committed.commit()
    clock = FrozenClock(FROZEN_NOW + timedelta(hours=24))
    settings = Settings(env=Environment.TEST)

    def work(_index: int, session: Session) -> None:
        sla_scan.run(session, JobContext(clock=clock, settings=settings, sender=InMemorySender()))

    assert run_parallel(2, work, engine) == ["ok", "ok"]
    committed.expire_all()
    ticket = committed.scalars(select(Ticket).where(Ticket.ticket_no == number)).one()
    steps = committed.scalars(
        select(EscalationEvent.step_key).where(EscalationEvent.ticket_id == ticket.id)
    ).all()
    assert sorted(steps) == ["L1", "L2"]
    notifications = committed.scalars(
        select(Notification.user_id).where(
            Notification.ticket_id == ticket.id, Notification.kind == "escalation"
        )
    ).all()
    assert len(notifications) == len(set(notifications)) == 4


def test_two_outbox_workers_send_each_email_once(
    committed: Session, committed_org: Org, engine: Engine
) -> None:
    clock = FrozenClock(FROZEN_NOW)
    for _ in range(5):
        create_ticket(committed, committed_org["asha"].id, clock)
    committed.commit()
    rows = committed.scalars(select(EmailOutbox.id)).all()
    assert len(rows) >= 10
    sender = InMemorySender()
    settings = Settings(env=Environment.TEST)

    def work(_index: int, session: Session) -> None:
        context = JobContext(clock=clock, settings=settings, sender=sender)
        while send_outbox.run(session, context) > 0:
            pass

    assert run_parallel(2, work, engine) == ["ok", "ok"]
    assert len(sender.sent) == len(rows)
    committed.expire_all()
    statuses = Counter(committed.scalars(select(EmailOutbox.status)).all())
    assert statuses == Counter({EmailStatus.SENT: len(rows)})
