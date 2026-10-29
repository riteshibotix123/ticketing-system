import threading
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Environment, Settings
from app.core.enums import Priority
from app.models import Ticket
from app.policy.actors import load_actor
from app.schemas.tickets import CreateTicketBody
from app.services.ticket_numbers import TicketNumberService
from app.services.tickets import TicketService
from tests.factories import (
    FACTORY_NOW,
    make_department,
    make_spoke_assignment,
    make_ticket_counter,
    make_user,
)

THREADS = 20


def test_numbers_are_sequential_per_code_and_year(db: Session) -> None:
    service = TicketNumberService(db)
    assert service.next_number("IT", FACTORY_NOW) == "IBX-IT-2026-000001"
    assert service.next_number("IT", FACTORY_NOW) == "IBX-IT-2026-000002"
    assert service.next_number("HR", FACTORY_NOW) == "IBX-HR-2026-000001"
    next_year = datetime(2027, 3, 1, tzinfo=UTC)
    assert service.next_number("IT", next_year) == "IBX-IT-2027-000001"
    assert service.next_number("IT", FACTORY_NOW) == "IBX-IT-2026-000003"


def test_year_comes_from_ist(db: Session) -> None:
    service = TicketNumberService(db)
    assert service.next_number("IT", datetime(2026, 12, 31, 18, 29, tzinfo=UTC)).startswith(
        "IBX-IT-2026-"
    )
    assert service.next_number("IT", datetime(2026, 12, 31, 18, 30, tzinfo=UTC)) == (
        "IBX-IT-2027-000001"
    )


def test_continues_existing_counter(db: Session) -> None:
    make_ticket_counter(db, "IT", 2026, last_value=41)
    assert TicketNumberService(db).next_number("IT", FACTORY_NOW) == "IBX-IT-2026-000042"


@pytest.fixture
def committed(committed_db: Session, migrated_engine: Engine) -> Iterator[Session]:
    yield committed_db
    committed_db.close()
    with migrated_engine.begin() as connection:
        connection.execute(text('TRUNCATE "audit_log"'))


def test_concurrent_creations_get_unique_numbers(
    committed: Session, test_database_url: str
) -> None:
    it = make_department(committed, "IT")
    make_spoke_assignment(committed, make_user(committed, it), it)
    requesters = [make_user(committed, it) for _ in range(THREADS)]
    committed.commit()
    engine = create_engine(test_database_url, pool_size=THREADS, max_overflow=0)
    barrier = threading.Barrier(THREADS, timeout=60)
    errors: list[BaseException] = []
    lock = threading.Lock()
    settings = Settings(env=Environment.TEST)
    clock = FrozenClock(FACTORY_NOW)

    def create(user_id: object) -> None:
        try:
            with Session(bind=engine, autoflush=False, expire_on_commit=False) as session:
                assert isinstance(user_id, type(requesters[0].id))
                actor = load_actor(session, user_id)
                assert actor is not None
                body = CreateTicketBody(
                    department_id="IT",
                    title="Concurrent",
                    description="Created in parallel",
                    priority=Priority.MEDIUM,
                )
                barrier.wait()
                TicketService(session, clock, settings).create(actor, body)
                session.commit()
        except BaseException as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=create, args=(user.id,)) for user in requesters]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    engine.dispose()
    assert errors == []
    numbers = sorted(committed.scalars(select(Ticket.ticket_no)))
    assert numbers == [f"IBX-IT-2026-{value:06d}" for value in range(1, THREADS + 1)]
