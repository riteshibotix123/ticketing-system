from dataclasses import dataclass
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.enums import TicketStatus
from app.core.events import TicketAcknowledged, TicketStatusChanged, publish
from app.integrations.email import InMemorySender
from app.models import Category, Department, EmailOutbox, Notification, Ticket, User
from app.services.handlers import register_all
from app.worker import JobContext
from app.worker.jobs import reminders
from tests.factories import (
    FACTORY_NOW,
    make_category,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_user,
)

T0 = FACTORY_NOW


@dataclass(frozen=True)
class Desk:
    it: Department
    requester: User
    spoke: User
    secret: Category


@pytest.fixture(autouse=True)
def handlers() -> None:
    register_all()


@pytest.fixture
def desk(db: Session) -> Desk:
    it = make_department(db, "IT")
    spoke = make_user(db, it, name="Sam Spoke")
    make_spoke_assignment(db, spoke, it)
    return Desk(
        it=it,
        requester=make_user(db, it, name="Rita Requester"),
        spoke=spoke,
        secret=make_category(db, it, "Investigations", is_confidential=True),
    )


@pytest.fixture
def context(clock: FrozenClock, settings: Settings) -> JobContext:
    return JobContext(clock=clock, settings=settings, sender=InMemorySender())


def move(db: Session, desk: Desk, ticket: Ticket, to: TicketStatus, hours: float) -> None:
    old = ticket.status
    ticket.status = to
    publish(
        db,
        TicketStatusChanged(
            actor_id=desk.spoke.id,
            occurred_at=T0 + timedelta(hours=hours),
            ticket_id=ticket.id,
            from_status=old,
            to_status=to,
        ),
    )
    db.flush()


def working_ticket(db: Session, desk: Desk, *, confidential: bool = False) -> Ticket:
    ticket = make_ticket(
        db,
        desk.requester,
        desk.it,
        status=TicketStatus.IN_PROGRESS,
        owner=desk.spoke,
        assignee=desk.spoke,
        category=desk.secret if confidential else None,
    )
    publish(db, TicketAcknowledged(actor_id=desk.spoke.id, occurred_at=T0, ticket_id=ticket.id))
    db.flush()
    return ticket


def run_at(db: Session, clock: FrozenClock, context: JobContext, hours: float) -> int:
    clock.set(T0 + timedelta(hours=hours))
    return reminders.run(db, context)


def notes(db: Session, kind: str) -> list[Notification]:
    return list(db.scalars(select(Notification).where(Notification.kind == kind)))


def test_requester_reminder_once_per_cycle(
    db: Session, clock: FrozenClock, context: JobContext, desk: Desk
) -> None:
    ticket = working_ticket(db, desk)
    move(db, desk, ticket, TicketStatus.AWAITING_REQUESTER, 1)
    assert run_at(db, clock, context, 48.9) == 0
    assert run_at(db, clock, context, 49) == 1
    assert run_at(db, clock, context, 60) == 0
    [note] = notes(db, "requester_reminder")
    assert note.user_id == desk.requester.id
    assert note.text == f"Ticket {ticket.ticket_no} is waiting for your reply"
    assert note.critical is False
    email = db.scalars(select(EmailOutbox).where(EmailOutbox.notification_id == note.id)).one()
    assert email.to_address == desk.requester.email
    db.refresh(ticket)
    assert ticket.status is TicketStatus.AWAITING_REQUESTER
    move(db, desk, ticket, TicketStatus.IN_PROGRESS, 61)
    move(db, desk, ticket, TicketStatus.AWAITING_REQUESTER, 62)
    assert run_at(db, clock, context, 110) == 1
    assert len(notes(db, "requester_reminder")) == 2


def test_hold_review_notifies_owner(
    db: Session, clock: FrozenClock, context: JobContext, desk: Desk
) -> None:
    ticket = working_ticket(db, desk)
    ticket.hold_reason = "Waiting for vendor"
    ticket.hold_review_date = T0 + timedelta(days=3)
    move(db, desk, ticket, TicketStatus.ON_HOLD, 1)
    assert run_at(db, clock, context, 71) == 0
    assert run_at(db, clock, context, 72) == 1
    assert run_at(db, clock, context, 73) == 0
    [note] = notes(db, "hold_review_due")
    assert note.user_id == desk.spoke.id
    assert note.text == f"Hold review due on {ticket.ticket_no}"


def test_resumed_ticket_gets_no_reminder(
    db: Session, clock: FrozenClock, context: JobContext, desk: Desk
) -> None:
    ticket = working_ticket(db, desk)
    move(db, desk, ticket, TicketStatus.AWAITING_REQUESTER, 1)
    move(db, desk, ticket, TicketStatus.IN_PROGRESS, 2)
    assert run_at(db, clock, context, 100) == 0
    assert notes(db, "requester_reminder") == []


def test_confidential_reminder_is_masked(
    db: Session, clock: FrozenClock, context: JobContext, desk: Desk
) -> None:
    ticket = working_ticket(db, desk, confidential=True)
    move(db, desk, ticket, TicketStatus.AWAITING_REQUESTER, 1)
    assert run_at(db, clock, context, 49) == 1
    [note] = notes(db, "requester_reminder")
    assert note.text == f"Update on {ticket.ticket_no}"
    email = db.scalars(select(EmailOutbox).where(EmailOutbox.notification_id == note.id)).one()
    assert email.template == "confidential_ticket_update"
    assert ticket.title not in email.body_text
